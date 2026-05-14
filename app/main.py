"""
LocalMindDesk — FastAPI 入口
提供聊天 API + 模型管理 API + 静态文件服务
"""
# ★ UTF-8 安全措施：不强制改编码，只确保遇到 emoji 等字符不崩溃
import sys, os
os.environ.setdefault("PYTHONUTF8", "1")
# 让 print() 遇到 GBK 无法编码的字符时用 ? 替代，而不是崩溃
try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass  # 某些环境下 reconfigure 不可用
import json
from datetime import datetime
import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional

from app.config import (
    load_config, get_config, save_config, get_active_endpoint,
    add_model_endpoint, remove_model_endpoint, set_active_model,
    ModelEndpoint, AppConfig
)
from app import llm_provider
from app import agent_router
from app import memory

# ============================================================
#  FastAPI 应用
# ============================================================
app = FastAPI(title="LocalMindDesk", version="2.0")

# ── 注册模块化路由（新增路由走 APIRouter 模式）──
from app.routes import all_routers
for r in all_routers:
    app.include_router(r)

# ============================================================
#  数据模型
# ============================================================
class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []
    session_id: Optional[str] = None
    system_prompt: Optional[str] = None
    temperature: Optional[float] = None
    mode: Optional[str] = None  # plan / execute / collaborate / review

class ModelAddRequest(BaseModel):
    name: str
    provider: str = "custom"
    base_url: str
    api_key: str = ""
    model: str = ""

# ============================================================
#  聊天 API
# ============================================================
@app.post("/api/chat")
async def api_chat(req: ChatRequest):
    try:
        cfg = get_config()

        # 记录用户活动（供主动对话引擎检测空闲）
        try:
            from app.proactive_engine import get_proactive_engine
            get_proactive_engine().record_user_activity()
        except Exception:
            pass

        # 构建历史
        history = []
        for m in req.history[-20:]:
            role = m.get("role", "user")
            content = m.get("content", "")
            if content:
                history.append({"role": role, "content": content})

        # System prompt——用三层记忆组装
        from app.context_manager import assemble_prompt, auto_archive
        session_id = req.session_id if hasattr(req, 'session_id') and req.session_id else None

        if session_id:
            sys_prompt, context_msgs = assemble_prompt(session_id, req.message)
            # 使用 L2 热窗口作为历史，而不是前端传过来的全量
            history = context_msgs
            # ★ 正常聊天不注入 skills（节省 context），只在 action 路由时按需加载
        else:
            sys_prompt = req.system_prompt or cfg.system_prompt
            from app.memory import get_memory_text
            mem_text = get_memory_text()
            if mem_text:
                sys_prompt += f"\n\n[长期记忆]:\n{mem_text}"
            # 非会话模式注入技能（API 直调等场景）
            from app.skills_manager import load_all_skills
            ws_path_for_skills = _workspace_state.get("path")
            skills_text = load_all_skills(ws_path_for_skills)
            if skills_text:
                sys_prompt += f"\n\n{skills_text}"

        # 注入工作区上下文（如果有打开的项目）
        ws_path = _workspace_state.get("path")
        if ws_path and os.path.isdir(ws_path):
            ws_context = _build_workspace_context(ws_path)
            if ws_context:
                sys_prompt += f"\n\n{ws_context}"

        # 走 Agent 路由（传递前端选择的模式）
        result = agent_router.route(req.message, history, sys_prompt,
                                    workspace_path=ws_path if ws_path else None,
                                    mode=req.mode)

        response = {"reply": result.get("reply", "")}
        if result.get("file_path"):
            response["file_path"] = result["file_path"]
            response["file_name"] = result.get("file_name", "")
        if result.get("profile_update"):
            response["profile_update"] = True
            response["profile_snapshot"] = result.get("profile_snapshot", {})
        if result.get("action_confirm"):
            response["action_confirm"] = result["action_confirm"]
        if result.get("activities"):
            response["activities"] = result["activities"]
        if result.get("file_changed"):
            response["file_changed"] = True
        if result.get("route_info"):
            response["route_info"] = result["route_info"]

        # 自动归档冷数据到 L3
        if session_id:
            try:
                auto_archive(session_id)
            except Exception as ae:
                print(f"[WARN] auto_archive: {ae}")

        # 附加 context_stats 给前端仪表盘
        try:
            from app.memory import get_hot_context, estimate_tokens
            hot = get_hot_context(session_id) if session_id else []
            hot_tokens = sum(estimate_tokens(m['content']) for m in hot)
            sys_tokens = estimate_tokens(sys_prompt) if sys_prompt else 0
            response["context_stats"] = {
                "totalTokens": sys_tokens + hot_tokens,
                "hotCount": len(hot),
                "vectorCount": 0,  # TODO: 从 L3 获取
            }
        except Exception:
            pass

        return response

    except Exception as e:
        print(f"[ERROR] /api/chat: {e}")
        return {"reply": f"⚠️ 系统错误: {str(e)}"}

# ============================================================
#  流式聊天 API (SSE)
# ============================================================
@app.post("/api/chat/stream")
async def api_chat_stream(req: ChatRequest):
    """
    流式聊天端点 (Server-Sent Events)
    - 纯聊天意图 → SSE 流式输出 (data: {"delta": "..."})
    - 非纯聊天意图 → 降级返回 JSON（与 /api/chat 相同）
    """
    from fastapi.responses import StreamingResponse
    from app.router.intent import analyze_intents
    from app.router.chat_handler import exec_chat_stream

    try:
        cfg = get_config()

        # 意图分析
        intents = analyze_intents(req.message)

        # 非纯聊天 → 降级到同步
        if intents != ["chat"]:
            result = await api_chat(req)
            return JSONResponse(content=result if isinstance(result, dict) else result)

        # ---- 纯聊天 → SSE 流式 ----

        # 构建历史
        history = []
        for m in req.history[-20:]:
            role = m.get("role", "user")
            content = m.get("content", "")
            if content:
                history.append({"role": role, "content": content})

        # System prompt 组装
        session_id = req.session_id if hasattr(req, 'session_id') and req.session_id else None

        # ★ v4.0: 使用 SystemPromptBuilder 构建增强 prompt (replaces old assemble_prompt)
        from app.agent_profile import load_profile
        from app.thinking_engine import detect_mode
        from app.prompt_builder import SystemPromptBuilder
        from app.action_engine import SANDBOX_ROOTS

        ws_path = _workspace_state.get("path")
        mode = req.mode if req.mode and req.mode in ('plan', 'execute', 'collaborate', 'review') else detect_mode(req.message)
        profile = load_profile()

        builder = SystemPromptBuilder(
            profile=profile,
            workspace_path=ws_path,
            mode=mode,
            user_message=req.message,
            sandbox_roots=list(SANDBOX_ROOTS),
        )
        effective_prompt = builder.build()

        # Keep history lean — last 10 messages max to stay within context budget
        history = history[-10:]

        # SSE 生成器
        full_reply_parts = []

        def generate():
            nonlocal history
            import time as _time

            # ★ Step 0.5: Auto-compact (compress history if too long)
            try:
                from app.compact import get_compactor
                compactor = get_compactor()
                if compactor.should_compact(history):
                    yield f"data: {json.dumps({'step_start': {'id': 's_compact', 'type': 'thinking', 'summary': 'Compressing context...'}}, ensure_ascii=False)}\n\n"
                    _tc0 = _time.time()

                    yield f"data: {json.dumps({'step_update': {'id': 's_compact', 'content': f'History has {len(history)} messages — compacting to fit context window...'}}, ensure_ascii=False)}\n\n"

                    history = compactor.compact(history)

                    _tc1 = _time.time()
                    compact_summary = f"Compressed to {len(history)} messages ({(_tc1 - _tc0):.1f}s)"
                    yield f"data: {json.dumps({'step_end': {'id': 's_compact', 'summary': compact_summary}}, ensure_ascii=False)}\n\n"
            except Exception as e:
                print(f"[Stream] compact error: {e}")

            # ★ Step 1: Thinking step (model selection already done above)
            yield f"data: {json.dumps({'step_start': {'id': 's_think', 'type': 'thinking', 'summary': 'Thinking...'}}, ensure_ascii=False)}\n\n"
            _t0 = _time.time()

            # Simulate brief thinking delay (prompt was already assembled above)
            yield f"data: {json.dumps({'step_update': {'id': 's_think', 'content': 'Analyzing intent and assembling context...'}}, ensure_ascii=False)}\n\n"

            _t1 = _time.time()
            _think_ms = int((_t1 - _t0) * 1000)
            think_summary = f"Thought for {(_t1 - _t0):.1f}s" if (_t1 - _t0) >= 1 else "Analyzed context"
            yield f"data: {json.dumps({'step_end': {'id': 's_think', 'summary': think_summary}}, ensure_ascii=False)}\n\n"

            # ★ Step 1.5: Coordinator plan (for complex tasks)
            try:
                from app.coordinator import get_coordinator
                coord = get_coordinator(ws_path)
                if coord.is_complex_task(req.message):
                    steps = coord.decompose(req.message)
                    for evt in coord.emit_plan_events(steps):
                        yield evt
            except Exception:
                pass

            # ★ Step 2: Generating step
            yield f"data: {json.dumps({'step_start': {'id': 's_gen', 'type': 'tool', 'summary': 'Generating response...'}}, ensure_ascii=False)}\n\n"

            token_count = 0
            for token in exec_chat_stream(req.message, history, effective_prompt):
                full_reply_parts.append(token)
                token_count += 1
                yield f"data: {json.dumps({'delta': token}, ensure_ascii=False)}\n\n"

            _t2 = _time.time()
            gen_summary = f"Generated {token_count} tokens in {(_t2 - _t1):.1f}s"
            yield f"data: {json.dumps({'step_end': {'id': 's_gen', 'summary': gen_summary}}, ensure_ascii=False)}\n\n"

            # ★ Record turn metrics (Claude Code-inspired token budget tracking)
            try:
                from app.metrics import get_metrics
                m = get_metrics()
                m.record_turn_tokens(token_count, duration_ms=(_t2 - _t1) * 1000)
                token_stats = m.get_session_token_stats()
            except Exception:
                token_stats = {}


            yield f"data: {json.dumps({'done': True, 'token_stats': token_stats})}\n\n"

            # ★ Post-turn hooks (fire-and-forget)
            full_reply = "".join(full_reply_parts)
            try:
                from app.post_processor import get_post_processor
                pp = get_post_processor()
                pp.run_async(
                    reply=full_reply,
                    user_message=req.message,
                    history=history,
                    session_id=session_id,
                )
            except Exception:
                pass

        response = StreamingResponse(generate(), media_type="text/event-stream",
                                     headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

        return response

    except Exception as e:
        print(f"[ERROR] /api/chat/stream: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(content={"reply": f"⚠️ 系统错误: {str(e)}"})

# ============================================================
#  冷启动 Boot API
# ============================================================
@app.get("/api/boot")
async def api_boot():
    """前端冷启动时调用，返回上次状态快照"""
    from app.context_manager import get_boot_context
    return get_boot_context()

# ============================================================
#  模型管理 API
# ============================================================
@app.get("/api/config")
async def api_config():
    cfg = get_config()
    endpoint = get_active_endpoint()
    from app.agent_profile import load_profile
    profile = load_profile()
    identity = profile.get("identity", {})
    return {
        "active_model": cfg.active_model,
        "temperature": cfg.temperature,
        "max_tokens": cfg.max_tokens,
        "system_prompt": cfg.system_prompt,
        "current_provider": endpoint.provider if endpoint else None,
        "current_model": endpoint.model if endpoint else None,
        "models": [m.model_dump() for m in cfg.models],
        "persona": {
            "name": identity.get("name", "LocalMindDesk"),
            "icon": identity.get("icon", "🧠"),
            "role": identity.get("role", ""),
        },
        "ui_preferences": profile.get("ui_preferences", {}),
        "behavior": profile.get("behavior", {}),
    }

@app.get("/api/health")
async def api_health():
    result = llm_provider.health_check()
    return result

# ============================================================
#  沙盒权限管理 API（Sandbox Permission Flow）
# ============================================================
class SandboxPermissionRequest(BaseModel):
    path: str
    reason: str = ""
    action: str = "read"  # read, write, execute, delete

@app.post("/api/sandbox/check")
async def api_sandbox_check(req: SandboxPermissionRequest):
    """
    检查路径是否在沙盒内。
    前端用此 API 在执行操作前确认权限。
    """
    from app.action_engine import _is_path_in_sandbox, SANDBOX_ROOTS, FORBIDDEN_PATHS
    allowed = _is_path_in_sandbox(req.path)
    norm_path = os.path.normpath(os.path.abspath(req.path))
    is_forbidden = any(norm_path.startswith(f) for f in FORBIDDEN_PATHS)
    return {
        "allowed": allowed,
        "path": norm_path,
        "is_forbidden": is_forbidden,
        "sandbox_roots": list(SANDBOX_ROOTS),
        "reason": f"路径 {norm_path} {'在' if allowed else '不在'}沙盒范围内",
    }

@app.get("/api/sandbox/roots")
async def api_sandbox_roots():
    """获取当前沙盒白名单"""
    from app.action_engine import SANDBOX_ROOTS, FORBIDDEN_PATHS
    return {
        "sandbox_roots": list(SANDBOX_ROOTS),
        "forbidden_paths": list(FORBIDDEN_PATHS),
    }

@app.put("/api/sandbox/grant")
async def api_sandbox_grant(req: SandboxPermissionRequest):
    """
    用户批准后，临时将路径添加到沙盒白名单。
    此变更仅在当前会话有效。
    """
    from app.action_engine import add_sandbox_root
    norm_path = os.path.normpath(os.path.abspath(req.path))
    # 检查是否是绝对禁止的路径
    from app.action_engine import FORBIDDEN_PATHS
    for f in FORBIDDEN_PATHS:
        if norm_path.startswith(f):
            return {"granted": False, "reason": f"路径 {norm_path} 属于系统保护目录，无法授权"}
    add_sandbox_root(norm_path)
    return {"granted": True, "path": norm_path, "reason": f"已临时授权访问: {norm_path}"}

# ★ 权限决定记录（Claude Code PermissionContext 模式）
_permission_decisions: dict[str, dict] = {}  # permission_id → {granted, path, ...}
_denied_paths: set = set()  # 用户拒绝的路径集合

@app.post("/api/sandbox/resolve")
async def api_sandbox_resolve(request: Request):
    """
    用户决定后的回调。
    记录权限决定，如果拒绝，则将路径加入拒绝集合，
    后续 AI 尝试访问同一路径时直接拒绝，不再重复询问。
    """
    data = await request.json()
    perm_id = data.get("permission_id", "")
    granted = data.get("granted", False)
    message = data.get("message", "")

    _permission_decisions[perm_id] = {
        "granted": granted,
        "message": message,
        "timestamp": datetime.now().isoformat(),
    }

    if not granted:
        # 提取路径并加入拒绝集合
        path = data.get("path", "")
        if path:
            _denied_paths.add(os.path.normpath(os.path.abspath(path)))
        print(f"[Sandbox] 用户拒绝访问: {path or perm_id}")

    return {"ok": True, "decision": "granted" if granted else "denied"}

@app.get("/api/sandbox/denied")
async def api_sandbox_denied():
    """获取当前会话中被用户拒绝的路径列表"""
    return {"denied_paths": list(_denied_paths)}

# ============================================================
#  便签本 API（Scratchpad）
# ============================================================
class ScratchpadRequest(BaseModel):
    session_id: str
    key: str
    value: str = ""

@app.get("/api/scratchpad/{session_id}")
async def api_scratchpad_get(session_id: str):
    """获取会话的所有便签"""
    from app.scratchpad import Scratchpad
    pad = Scratchpad(session_id)
    return {"entries": pad.get_all()}

@app.put("/api/scratchpad")
async def api_scratchpad_set(req: ScratchpadRequest):
    """设置便签条目"""
    from app.scratchpad import Scratchpad
    pad = Scratchpad(req.session_id)
    pad.set(req.key, req.value)
    return {"ok": True, "key": req.key}

@app.delete("/api/scratchpad/{session_id}/{key}")
async def api_scratchpad_delete(session_id: str, key: str):
    """删除便签条目"""
    from app.scratchpad import Scratchpad
    pad = Scratchpad(session_id)
    deleted = pad.delete(key)
    return {"ok": deleted}

# ============================================================
#  后台任务 API（Background Tasks）
# ============================================================
@app.get("/api/tasks")
async def api_tasks_list():
    """列出所有后台任务"""
    from app.background_tasks import get_task_manager
    tm = get_task_manager()
    return {"tasks": tm.list_tasks()}

@app.get("/api/tasks/{task_id}")
async def api_task_status(task_id: str):
    """获取单个任务状态"""
    from app.background_tasks import get_task_manager
    tm = get_task_manager()
    task = tm.get_task(task_id)
    if not task:
        return JSONResponse(status_code=404, content={"error": "Task not found"})
    return task

@app.delete("/api/tasks/{task_id}")
async def api_task_kill(task_id: str):
    """终止后台任务"""
    from app.background_tasks import get_task_manager
    tm = get_task_manager()
    killed = tm.kill_task(task_id)
    return {"ok": killed}

# ============================================================
#  对话压缩 API（Compact）
# ============================================================
class CompactRequest(BaseModel):
    session_id: Optional[str] = None
    messages: list[dict] = []

@app.post("/api/compact")
async def api_compact(req: CompactRequest):
    """手动触发对话压缩"""
    from app.compact import get_compactor
    compactor = get_compactor()

    if not req.messages or len(req.messages) < 3:
        return {"ok": False, "reason": "消息太少，无需压缩"}

    compacted = compactor.compact(req.messages)
    return {
        "ok": True,
        "original_count": len(req.messages),
        "compacted_count": len(compacted),
        "messages": compacted,
        "stats": compactor.get_stats(),
    }

@app.get("/api/compact/stats")
async def api_compact_stats():
    """获取压缩统计"""
    from app.compact import get_compactor
    return get_compactor().get_stats()

@app.get("/api/models")
async def api_models():
    """获取当前端点可用的模型列表"""
    models = llm_provider.list_available_models()
    return {"models": models}

@app.post("/api/models/add")
async def api_add_model(req: ModelAddRequest):
    """添加新模型端点"""
    endpoint = ModelEndpoint(
        name=req.name,
        provider=req.provider,
        base_url=req.base_url,
        api_key=req.api_key,
        model=req.model,
    )
    add_model_endpoint(endpoint)
    return {"status": "ok", "message": f"已添加模型: {req.name}"}

@app.delete("/api/models/{name}")
async def api_remove_model(name: str):
    """删除模型端点"""
    remove_model_endpoint(name)
    return {"status": "ok", "message": f"已删除模型: {name}"}

@app.post("/api/models/switch/{name}")
async def api_switch_model(name: str):
    """切换主模型"""
    ok = set_active_model(name)
    if ok:
        endpoint = get_active_endpoint()
        return {
            "status": "ok",
            "active_model": name,
            "provider": endpoint.provider if endpoint else None,
            "model": endpoint.model if endpoint else None,
        }
    return {"status": "error", "message": f"未找到模型: {name}"}

@app.post("/api/models/route")
async def api_model_route(req: ChatRequest):
    """测试智能路由：查看消息会被路由到哪个模型"""
    from app.model_router import select_model, estimate_complexity
    complexity = estimate_complexity(req.message)
    endpoint = select_model(req.message)
    return {
        "message": req.message[:100],
        "complexity": complexity,
        "selected_model": endpoint.name if endpoint else None,
        "selected_provider": endpoint.provider if endpoint else None,
    }

@app.post("/api/config/update")
async def api_update_config(request: Request):
    """更新配置"""
    data = await request.json()
    cfg = get_config()
    if "temperature" in data:
        cfg.temperature = float(data["temperature"])
    if "max_tokens" in data:
        cfg.max_tokens = int(data["max_tokens"])
    if "system_prompt" in data:
        cfg.system_prompt = data["system_prompt"]
    save_config(cfg)
    return {"status": "ok"}

# ============================================================
#  文件下载 API
# ============================================================
@app.get("/api/files/{filename}")
async def download_file(filename: str):
    """下载生成的文件"""
    filepath = os.path.join("data", "files", filename)
    if os.path.exists(filepath):
        return FileResponse(filepath, filename=filename)
    return JSONResponse({"error": "文件不存在"}, status_code=404)

# ============================================================
#  Agent Profile API
# ============================================================
@app.get("/api/profile")
async def api_get_profile():
    from app.agent_profile import load_profile
    return load_profile()

@app.post("/api/profile/reset")
async def api_reset_profile():
    from app.agent_profile import reset_profile
    profile = reset_profile()
    return {"status": "ok", "profile": profile}

@app.post("/api/profile/evolve")
async def api_evolve_profile(request: Request):
    data = await request.json()
    instruction = data.get("instruction", "")
    if not instruction:
        return JSONResponse({"error": "缺少 instruction"}, status_code=400)
    from app.meta_agent import apply_evolution
    result = apply_evolution(instruction)
    return result

# ============================================================
#  操作执行 API
# ============================================================
@app.post("/api/actions/execute")
async def api_execute_action(request: Request):
    """
    前端确认后执行操作。
    
    沙盒权限升级流程 (学习 Claude Code PermissionContext):
    1. 操作路径在沙盒内 → 直接执行
    2. 操作路径在黑名单内 → 永久拒绝
    3. 操作路径在沙盒外 → 返回 pending_permission，前端显示 Allow/Deny
    4. 用户允许 → 临时加入沙盒白名单，重新执行
    5. 用户拒绝 → 返回拒绝结果，AI 应停止该话题
    """
    data = await request.json()
    actions = data.get("actions", [])
    force_allow = data.get("force_allow", False)  # 用户已批准时设为 true
    
    from app.action_engine import SafetyGate, execute_action, FORBIDDEN_PATHS, add_sandbox_root
    results = []
    pending_permissions = []
    
    for action in actions:
        tool = action.get("tool", "")
        params = action.get("params", {})
        
        assessment = SafetyGate.assess(tool, params)
        
        if assessment.get("blocked"):
            # 提取被阻止的路径
            blocked_path = ""
            for k in ("source", "destination", "path", "cwd"):
                if k in params and params[k]:
                    blocked_path = params[k]
                    break
            
            norm_path = os.path.normpath(os.path.abspath(blocked_path)) if blocked_path else ""
            
            # 检查是否在黑名单内（永久禁止）
            is_forbidden = any(norm_path.startswith(f) for f in FORBIDDEN_PATHS)
            
            if is_forbidden:
                # 黑名单路径 → 绝对拒绝
                results.append({
                    "tool": tool,
                    "result": {
                        "success": False,
                        "error": f"🚫 系统保护路径，无法访问: {norm_path}",
                        "permanently_blocked": True,
                    }
                })
            elif force_allow and blocked_path:
                # 用户已批准 → 临时加入白名单并执行
                add_sandbox_root(norm_path)
                result = execute_action(tool, params)
                results.append({"tool": tool, "result": result})
            else:
                # 沙盒外 → 需要用户批准
                perm_id = f"perm_{tool}_{len(pending_permissions)}"
                pending_permissions.append({
                    "id": perm_id,
                    "tool": tool,
                    "path": norm_path,
                    "action": params.get("action", tool),
                    "reason": assessment.get("reason", f"路径 {norm_path} 不在沙盒范围内"),
                })
                results.append({
                    "tool": tool,
                    "result": {
                        "success": False,
                        "error": f"需要权限: {norm_path} 超出沙盒范围",
                        "pending_permission": True,
                        "permission_id": perm_id,
                    }
                })
        else:
            result = execute_action(tool, params)
            results.append({"tool": tool, "result": result})
    
    response = {"results": results}
    if pending_permissions:
        response["pending_permissions"] = pending_permissions
        response["needs_approval"] = True
    return response

@app.get("/api/actions/history")
async def api_action_history():
    from app.action_engine import get_action_log
    return {"log": get_action_log()}

@app.get("/api/activities")
async def api_activity_feed():
    from app.agent_router import get_activity_feed
    return {"activities": get_activity_feed(30)}

@app.get("/api/agents")
async def api_list_agents():
    from app.prompt_loader import list_agents
    return {"agents": list_agents()}

# ============================================================
#  会话管理 API
# ============================================================
@app.get("/api/sessions")
async def api_list_sessions():
    sessions = memory.list_sessions()
    return {"sessions": sessions}

@app.post("/api/sessions")
async def api_create_session():
    sid = memory.create_session()
    return {"session_id": sid}

@app.get("/api/sessions/{sid}/messages")
async def api_get_messages(sid: str):
    msgs = memory.get_session_messages(sid)
    return {"messages": msgs}

@app.post("/api/sessions/{sid}/messages")
async def api_add_message(sid: str, request: Request):
    data = await request.json()
    role = data.get("role", "user")
    content = data.get("content", "")
    memory.add_message(sid, role, content)
    if role == "user" and len(memory.get_session_messages(sid)) <= 2:
        memory.auto_title(sid, content)
    return {"status": "ok"}

@app.delete("/api/sessions/{sid}")
async def api_delete_session(sid: str):
    memory.delete_session(sid)
    return {"status": "ok"}

# ============================================================
#  向量记忆 API
# ============================================================
@app.post("/api/vector/rebuild")
async def api_vector_rebuild():
    """手动触发嵌入向量重建"""
    from app.vector_memory import get_vector_store
    store = get_vector_store()
    count = store.rebuild_embeddings()
    return {"status": "ok", "rebuilt": count, "total": store.count()}

@app.get("/api/vector/status")
async def api_vector_status():
    """查看向量记忆状态"""
    from app.vector_memory import get_vector_store
    store = get_vector_store()
    return {
        "total_documents": store.count(),
        "use_embedding": store.use_embedding,
        "has_cached_embeddings": any(len(e) > 0 for e in store._embeddings),
        "embedding_count": sum(1 for e in store._embeddings if len(e) > 0),
    }

# ============================================================
#  可观测性 API (Metrics)
# ============================================================
@app.get("/api/metrics")
async def api_metrics():
    """获取系统指标"""
    from app.metrics import get_metrics
    return get_metrics().get_summary()

# ============================================================
#  配置热重载 API
# ============================================================
@app.post("/api/config/reload")
async def api_config_reload():
    """热重载配置（不重启后端）"""
    from app.config import load_config
    cfg = load_config()
    return {"status": "ok", "message": "配置已重新加载", "active_model": cfg.active_model}

# ============================================================
#  WebSocket 实时通信
# ============================================================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket 实时推送通道
    前端连接后自动接收：proactive 消息、状态更新、微信消息
    前端也可发送心跳 {"type": "ping"}
    """
    from app.ws_manager import ws_manager
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await ws_manager.send(websocket, "pong", {"ts": __import__("time").time()})
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)

# ============================================================
#  工具函数
# ============================================================
def _read_file(path: str) -> str:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
    except Exception:
        pass
    return ""


def _build_workspace_context(root: str, max_total_chars: int = 30000) -> str:
    """构建工作区上下文：文件树 + 关键文件内容，注入到 system prompt"""
    SKIP_DIRS = {'.git', '__pycache__', 'node_modules', '.venv', 'venv',
                 '.idea', '.vs', '.vscode', 'dist', 'build', '.next'}
    TEXT_EXTS = {'.py', '.js', '.ts', '.jsx', '.tsx', '.c', '.cpp', '.h',
                 '.java', '.go', '.rs', '.rb', '.php', '.cs', '.swift',
                 '.html', '.css', '.scss', '.json', '.yaml', '.yml',
                 '.toml', '.md', '.txt', '.sh', '.bat', '.ps1', '.sql',
                 '.xml', '.ini', '.cfg', '.env', '.gitignore', '.makefile'}
    BINARY_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.ico', '.woff', '.woff2',
                   '.ttf', '.otf', '.zip', '.tar', '.gz', '.exe', '.dll',
                   '.so', '.pyc', '.pptx', '.docx', '.xlsx', '.pdf', '.db',
                   '.sqlite', '.bin', '.o', '.obj', '.class'}

    # 1. 构建文件树
    tree_lines = [f"[当前工作区] 路径: {root}", "文件结构:"]
    file_list = []  # (相对路径, 绝对路径, 大小)

    def walk_tree(dirpath, prefix="", depth=0):
        if depth > 4:
            return
        try:
            entries = sorted(os.listdir(dirpath))
        except PermissionError:
            return
        dirs = [e for e in entries if os.path.isdir(os.path.join(dirpath, e)) and e not in SKIP_DIRS and not e.startswith('.')]
        files = [e for e in entries if os.path.isfile(os.path.join(dirpath, e))]

        for f in files:
            full = os.path.join(dirpath, f)
            rel = os.path.relpath(full, root).replace("\\", "/")
            size = os.path.getsize(full)
            ext = os.path.splitext(f)[1].lower()
            tree_lines.append(f"  {prefix}📄 {f} ({size} bytes)")
            if ext in TEXT_EXTS and ext not in BINARY_EXTS and size < 50000:
                file_list.append((rel, full, size))

        for d in dirs:
            full = os.path.join(dirpath, d)
            tree_lines.append(f"  {prefix}📁 {d}/")
            walk_tree(full, prefix + "  ", depth + 1)

    walk_tree(root)

    # 2. 读取文件内容（按大小排序，优先小文件，控制总量）
    file_list.sort(key=lambda x: x[2])
    content_parts = []
    total_chars = 0

    for rel, full, size in file_list:
        if total_chars >= max_total_chars:
            break
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as f:
                text = f.read(10000)  # 单文件最多读 10000 字符
            if text.strip():
                remaining = max_total_chars - total_chars
                if len(text) > remaining:
                    text = text[:remaining] + "\n... (文件过长，已截断)"
                content_parts.append(f"--- 文件: {rel} ---\n{text}")
                total_chars += len(text)
        except Exception:
            pass

    # 3. 组装
    result = "\n".join(tree_lines)
    if content_parts:
        result += "\n\n[工作区文件内容]\n" + "\n\n".join(content_parts)
    result += "\n\n[指令] 用户已打开上述工作区项目。当用户询问项目相关问题时，请直接基于上述文件内容回答，无需再向用户索要路径。如需修改文件，使用 file_op 工具并指定完整路径。"

    return result


# ============================================================
#  Skill 管理 API（全局 + 项目局部，用 MD5 哈希标识项目）
# ============================================================
@app.get("/api/skills")
async def api_list_skills():
    """列出全局 + 当前项目局部技能"""
    from app.skill_manager import list_skills as legacy_list
    ws = _workspace_state.get("path")
    # 使用旧的 list_skills 保持前端兼容（含解析元数据）
    result = legacy_list(project_dir=ws)
    # 追加项目哈希标识
    if ws:
        from app.skills_manager import _project_hash
        result["project_hash"] = _project_hash(ws)
        result["project_path"] = ws
    return result

@app.delete("/api/skills/{filename}")
async def api_delete_skill(filename: str, scope: str = "global"):
    from app.skill_manager import delete_skill
    ws = _workspace_state.get("path")
    return delete_skill(filename, scope, project_dir=ws)

@app.post("/api/skills/learn")
async def api_learn_skill(request: Request):
    from app.skill_manager import learn_from_github
    data = await request.json()
    url = data.get("url", "")
    scope = data.get("scope", "global")
    ws = _workspace_state.get("path")
    return learn_from_github(url, scope, project_dir=ws)

@app.post("/api/skills/save")
async def api_skills_save(request: Request):
    """保存技能（支持 scope=global/project）"""
    from app.skills_manager import save_global_skill, save_project_skill
    data = await request.json()
    name = data.get("name", "").strip()
    content = data.get("content", "").strip()
    scope = data.get("scope", "global")
    if not name or not content:
        return {"success": False, "error": "name 和 content 必填"}
    if scope == "project":
        ws = _workspace_state.get("path")
        if not ws:
            return {"success": False, "error": "未打开项目"}
        path = save_project_skill(ws, name, content)
    else:
        path = save_global_skill(name, content)
    return {"success": True, "path": path, "scope": scope}

# ============================================================
#  Profile 更新 API
# ============================================================
@app.post("/api/profile/update")
async def api_update_profile(request: Request):
    from app.agent_profile import load_profile, merge_delta
    data = await request.json()
    delta = data.get("delta", {})
    if not delta:
        return {"success": False, "error": "delta 为空"}
    profile = load_profile()
    updated = merge_delta(profile, delta, trigger="UI settings")
    return {"success": True, "profile": updated}

# ============================================================
#  项目工作区 API
# ============================================================
_workspace_state = {"path": None}

@app.post("/api/workspace/open")
async def api_workspace_open(request: Request):
    """打开一个项目文件夹"""
    data = await request.json()
    folder = data.get("path", "")
    if not folder or not os.path.isdir(folder):
        return {"success": False, "error": f"目录不存在: {folder}"}
    # 动态添加工作区到沙盒
    from app.action_engine import add_sandbox_root
    add_sandbox_root(folder)
    _workspace_state["path"] = os.path.normpath(folder)
    return {"success": True, "path": _workspace_state["path"]}

@app.post("/api/workspace/reveal")
async def api_workspace_reveal():
    """在系统资源管理器中打开工作区文件夹"""
    root = _workspace_state.get("path")
    if not root or not os.path.isdir(root):
        return {"success": False, "error": "未打开项目"}
    import subprocess
    try:
        subprocess.Popen(["explorer", os.path.normpath(root)])
        return {"success": True, "path": root}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/workspace/pick-folder")
async def api_workspace_pick_folder():
    """弹出系统文件夹选择对话框，返回用户选择的路径"""
    import threading

    result = {"path": None}

    def _pick():
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()  # 隐藏主窗口
            root.attributes("-topmost", True)  # 置顶
            folder = filedialog.askdirectory(
                title="选择项目文件夹",
                mustexist=True,
            )
            root.destroy()
            if folder:
                result["path"] = os.path.normpath(folder)
        except Exception as e:
            print(f"[Workspace] 文件夹选择失败: {e}")

    # tkinter 必须在主线程或独立线程中运行
    t = threading.Thread(target=_pick)
    t.start()
    t.join(timeout=120)  # 最多等 2 分钟

    if result["path"]:
        return {"success": True, "path": result["path"]}
    else:
        return {"success": False, "error": "未选择文件夹"}


@app.get("/api/workspace/tree")
async def api_workspace_tree(depth: int = 3):
    """获取文件树"""
    root = _workspace_state.get("path")
    if not root:
        return {"success": False, "error": "未打开项目"}

    def _walk(dirpath, cur_depth):
        if cur_depth > depth:
            return []
        items = []
        try:
            for entry in sorted(os.listdir(dirpath)):
                # 跳过隐藏/缓存目录
                if entry.startswith('.') or entry in ('__pycache__', 'node_modules', '.git', 'venv', '.venv'):
                    continue
                full = os.path.join(dirpath, entry)
                rel = os.path.relpath(full, root).replace("\\", "/")
                if os.path.isdir(full):
                    children = _walk(full, cur_depth + 1)
                    items.append({"name": entry, "path": rel, "is_dir": True, "children": children})
                else:
                    size = os.path.getsize(full)
                    items.append({"name": entry, "path": rel, "is_dir": False, "size": size})
        except PermissionError:
            pass
        return items

    tree = _walk(root, 1)
    return {"success": True, "root": os.path.basename(root), "root_path": root, "tree": tree}

@app.get("/api/workspace/file")
async def api_workspace_file(path: str):
    """读取项目文件内容"""
    root = _workspace_state.get("path")
    if not root:
        return {"success": False, "error": "未打开项目"}
    full = os.path.normpath(os.path.join(root, path))
    # 安全检查
    if not full.startswith(os.path.normpath(root)):
        return {"success": False, "error": "路径越权"}
    if not os.path.isfile(full):
        return {"success": False, "error": "文件不存在"}
    # 二进制文件检查
    ext = os.path.splitext(full)[1].lower()
    binary_exts = {'.png','.jpg','.jpeg','.gif','.ico','.woff','.woff2','.ttf','.otf',
                   '.zip','.tar','.gz','.exe','.dll','.so','.pyc','.pptx','.docx','.xlsx','.pdf','.db','.sqlite'}
    if ext in binary_exts:
        return {"success": True, "content": f"[二进制文件: {ext}]", "binary": True, "size": os.path.getsize(full)}
    try:
        with open(full, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(100000)
        return {"success": True, "content": content, "binary": False,
                "size": os.path.getsize(full), "language": _guess_lang(ext)}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/workspace/log")
async def api_workspace_log():
    """获取 AI 操作日志"""
    from app.action_engine import get_action_log
    return {"log": get_action_log()[-20:]}

@app.get("/api/workspace/state")
async def api_workspace_state():
    return _workspace_state



def _guess_lang(ext: str) -> str:
    mapping = {'.py':'python','.js':'javascript','.ts':'typescript','.html':'html',
               '.css':'css','.json':'json','.md':'markdown','.yaml':'yaml','.yml':'yaml',
               '.toml':'toml','.sh':'bash','.ps1':'powershell','.cpp':'cpp','.c':'c',
               '.h':'c','.rs':'rust','.go':'go','.java':'java','.rb':'ruby','.sql':'sql'}
    return mapping.get(ext, 'text')

# ============================================================
#  应用集成 API
# ============================================================
@app.get("/api/integrations")
async def api_get_integrations():
    """获取所有可用集成及其状态"""
    from app.integrations.manager import get_manager
    mgr = get_manager()
    return {"integrations": mgr.get_all_status()}

@app.post("/api/integrations/{integration_id}/enable")
async def api_enable_integration(integration_id: str, request: Request):
    """启用集成"""
    from app.integrations.manager import get_manager
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    config = body.get("config", {})
    mgr = get_manager()
    result = mgr.enable(integration_id, config)
    return result

@app.post("/api/integrations/{integration_id}/disable")
async def api_disable_integration(integration_id: str):
    """禁用集成"""
    from app.integrations.manager import get_manager
    mgr = get_manager()
    return mgr.disable(integration_id)

@app.post("/api/integrations/{integration_id}/test")
async def api_test_integration(integration_id: str, request: Request):
    """测试集成连接"""
    from app.integrations.manager import get_manager
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    config = body.get("config", {})
    mgr = get_manager()
    return mgr.test_connection(integration_id, config if config else None)

@app.post("/api/integrations/{integration_id}/detect")
async def api_detect_integration(integration_id: str):
    """自动检测应用安装信息"""
    from app.integrations.manager import get_manager
    mgr = get_manager()
    return mgr.auto_detect(integration_id)

@app.put("/api/integrations/{integration_id}/config")
async def api_update_integration_config(integration_id: str, request: Request):
    """更新集成配置"""
    from app.integrations.manager import get_manager
    body = await request.json()
    config = body.get("config", {})
    mgr = get_manager()
    return mgr.update_config(integration_id, config)

@app.post("/api/integrations/{integration_id}/install-deps")
async def api_install_deps(integration_id: str):
    """
    根据集成定义的 install_commands 模板执行安装。
    自动读取集成对象上的命令列表，逐条执行。
    """
    import subprocess, sys, shlex

    from app.integrations.manager import get_manager
    mgr = get_manager()
    integration = mgr._integrations.get(integration_id)
    if not integration:
        return {"success": False, "error": f"未知集成: {integration_id}"}

    commands = integration.install_commands
    if not commands:
        return {"success": False, "error": f"{integration.name} 未定义安装命令"}

    results = []
    all_success = True

    for step in commands:
        cmd_str = step.get("cmd", "")
        label = step.get("label", cmd_str)
        required = step.get("required", True)
        fallback = step.get("fallback", "")

        if not cmd_str:
            continue

        # 执行主命令
        success, output = _run_terminal_cmd(cmd_str, timeout=180)

        if not success and fallback:
            # 尝试备选命令
            output += f"\n--- 尝试备选命令: {fallback} ---\n"
            success, fb_output = _run_terminal_cmd(fallback, timeout=180)
            output += fb_output

        results.append({
            "label": label,
            "cmd": cmd_str,
            "success": success,
            "output": output,
        })

        if not success and required:
            all_success = False

    return {
        "success": all_success,
        "message": f"{'✅ 所有依赖安装成功' if all_success else '⚠️ 部分安装失败'}",
        "results": results,
    }


@app.post("/api/terminal/exec")
async def api_terminal_exec(request: Request):
    """
    通用终端命令执行 API。
    前端可以发送任意终端命令，用于：
    - 安装依赖
    - 执行集成相关任务
    - 检查环境

    请求体: {"cmd": "pip install xxx", "timeout": 60, "cwd": ""}
    返回: {"success": true, "output": "...", "return_code": 0}
    """
    body = await request.json()
    cmd_str = body.get("cmd", "").strip()
    timeout = min(body.get("timeout", 120), 300)  # 最长 5 分钟
    cwd = body.get("cwd", None)

    if not cmd_str:
        return {"success": False, "error": "命令不能为空", "output": ""}

    # 安全检查：拦截危险命令
    BLOCKED_PATTERNS = [
        "rm -rf /", "format c:", "del /s /q c:",
        "shutdown", "mkfs", "dd if=",
    ]
    cmd_lower = cmd_str.lower()
    for pattern in BLOCKED_PATTERNS:
        if pattern in cmd_lower:
            return {"success": False, "error": f"危险命令被拦截: {pattern}", "output": ""}

    success, output = _run_terminal_cmd(cmd_str, timeout=timeout, cwd=cwd)
    return {
        "success": success,
        "output": output,
        "cmd": cmd_str,
    }


def _run_terminal_cmd(cmd_str: str, timeout: int = 120, cwd: str = None) -> tuple:
    """
    执行终端命令的通用辅助函数。
    返回 (success: bool, output: str)
    """
    import subprocess, sys

    try:
        # 处理 pip/python 命令，确保用当前 Python 环境
        if cmd_str.startswith("pip "):
            cmd_parts = [sys.executable, "-m"] + cmd_str.split()
        else:
            cmd_parts = cmd_str

        proc = subprocess.run(
            cmd_parts,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            shell=isinstance(cmd_parts, str),  # 非列表时用 shell
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        return (proc.returncode == 0, output)
    except subprocess.TimeoutExpired:
        return (False, f"命令执行超时（{timeout}秒）")
    except FileNotFoundError:
        return (False, f"命令未找到: {cmd_str}")
    except Exception as e:
        return (False, f"执行异常: {str(e)}")

# ============================================================
#  定时任务 API
# ============================================================
@app.get("/api/schedules")
async def api_get_schedules():
    from app.scheduler import get_scheduler
    s = get_scheduler()
    return {
        "tasks": s.get_all(),
        "templates": s.get_templates(),
        "running": s._running,
    }

@app.post("/api/schedules")
async def api_create_schedule(request: Request):
    from app.scheduler import get_scheduler
    body = await request.json()
    return get_scheduler().add_task(body)

@app.put("/api/schedules/{task_id}")
async def api_update_schedule(task_id: str, request: Request):
    from app.scheduler import get_scheduler
    body = await request.json()
    return get_scheduler().update_task(task_id, body)

@app.delete("/api/schedules/{task_id}")
async def api_delete_schedule(task_id: str):
    from app.scheduler import get_scheduler
    return get_scheduler().delete_task(task_id)

@app.post("/api/schedules/{task_id}/toggle")
async def api_toggle_schedule(task_id: str):
    from app.scheduler import get_scheduler
    return get_scheduler().toggle_task(task_id)

@app.post("/api/schedules/{task_id}/run-now")
async def api_run_schedule_now(task_id: str):
    from app.scheduler import get_scheduler
    return get_scheduler().run_now(task_id)

@app.get("/api/schedules/log")
async def api_get_schedule_log():
    from app.scheduler import get_scheduler
    return {"log": get_scheduler().get_log()}

# ============================================================
#  v2.0: 主动对话引擎 API
# ============================================================
@app.get("/api/proactive/messages")
async def api_proactive_messages():
    """前端轮询：获取待推送的主动消息"""
    try:
        from app.proactive_engine import get_proactive_engine
        pe = get_proactive_engine()
        return {"messages": pe.get_pending_messages()}
    except Exception:
        return {"messages": []}

@app.get("/api/proactive/status")
async def api_proactive_status():
    """获取主动对话引擎状态"""
    try:
        from app.proactive_engine import get_proactive_engine
        return get_proactive_engine().get_status()
    except Exception:
        return {"running": False, "error": "引擎未初始化"}

@app.get("/api/proactive/history")
async def api_proactive_history():
    """获取主动对话历史"""
    try:
        from app.proactive_engine import get_proactive_engine
        return {"history": get_proactive_engine().get_history()}
    except Exception:
        return {"history": []}

# ============================================================
#  v2.0: 角色管理 API
# ============================================================
@app.get("/api/soul")
async def api_get_soul():
    """获取当前角色定义"""
    from app.soul_manager import get_soul_manager
    sm = get_soul_manager()
    return {
        "has_soul": sm.has_soul,
        "content": sm.get_soul_raw(),
        "status": sm.get_status(),
    }

@app.post("/api/soul/save")
async def api_save_soul(request: Request):
    """保存角色定义"""
    from app.soul_manager import get_soul_manager
    body = await request.json()
    content = body.get("content", "")
    slug = body.get("slug")  # 可选：指定角色
    if not content:
        return {"success": False, "error": "内容不能为空"}
    return get_soul_manager().save_soul(content, slug)

@app.post("/api/soul/generate")
async def api_generate_soul(request: Request):
    """用 LLM 从描述生成 5 层角色"""
    from app.soul_manager import get_soul_manager
    body = await request.json()
    description = body.get("description", "")
    slug = body.get("slug")
    name = body.get("name")
    if not description:
        return {"success": False, "error": "请提供角色描述"}
    return get_soul_manager().soul_generate(description, slug, name)

@app.get("/api/soul/user")
async def api_get_user_md():
    """获取自动渲染的 USER.md"""
    from app.soul_manager import get_soul_manager
    return {"content": get_soul_manager().render_user_md()}

# ── 多角色管理 API ──
@app.get("/api/personas")
async def api_list_personas():
    """列出所有角色"""
    from app.soul_manager import get_soul_manager
    sm = get_soul_manager()
    return {"personas": sm.list_personas(), "active": sm.get_active_slug()}

@app.post("/api/personas/switch")
async def api_switch_persona(request: Request):
    """切换激活的角色"""
    from app.soul_manager import get_soul_manager
    body = await request.json()
    slug = body.get("slug", "")
    return get_soul_manager().switch_persona(slug)

@app.post("/api/personas/create")
async def api_create_persona(request: Request):
    """创建新角色"""
    from app.soul_manager import get_soul_manager
    body = await request.json()
    slug = body.get("slug", "")
    name = body.get("name", slug)
    persona = body.get("persona_content", "")
    memories = body.get("memories_content", "")
    desc = body.get("description", "")
    if not slug or not persona:
        return {"success": False, "error": "slug 和 persona_content 必填"}
    return get_soul_manager().create_persona(slug, name, persona, memories, desc)

@app.delete("/api/personas/{slug}")
async def api_delete_persona(slug: str):
    """删除角色"""
    from app.soul_manager import get_soul_manager
    return get_soul_manager().delete_persona(slug)

@app.get("/api/personas/{slug}/versions")
async def api_list_versions(slug: str):
    """列出角色的历史版本"""
    from app.soul_manager import get_soul_manager
    return {"versions": get_soul_manager().list_versions(slug)}

@app.post("/api/personas/{slug}/rollback")
async def api_rollback_persona(slug: str, request: Request):
    """回滚到指定版本"""
    from app.soul_manager import get_soul_manager
    body = await request.json()
    version = body.get("version", "")
    return get_soul_manager().rollback(slug, version)

@app.get("/api/personas/{slug}/memories")
async def api_get_memories(slug: str):
    """获取角色的共同记忆"""
    from app.soul_manager import get_soul_manager
    sm = get_soul_manager()
    content = sm._load_memories(slug)
    return {"content": content}

# ============================================================
#  蒸馏引擎 API
# ============================================================
@app.post("/api/distill")
async def api_distill(request: Request):
    """
    蒸馏角色 — 从聊天记录/描述生成 5 层 Persona + Memories

    Body:
      target_name: 目标人物名称（必填）
      chat_text: 聊天记录文本（可选）
      description: 人物描述（可选）
      personality_tags: 性格标签（可选）
      model_name: 指定蒸馏用的模型名称（可选，默认用当前激活模型）
      auto_create: 是否自动创建角色（默认 false，仅预览）
    """
    from app.distill_engine import get_distill_engine
    from app.soul_manager import get_soul_manager
    from app.config import get_endpoint_by_name

    body = await request.json()
    name = body.get("target_name", "")
    chat = body.get("chat_text", "")
    chat_filename = body.get("chat_filename", "")
    desc = body.get("description", "")
    tags = body.get("personality_tags", "")
    model_name = body.get("model_name", "")
    auto_create = body.get("auto_create", False)

    if not name:
        return {"success": False, "error": "target_name 必填"}

    # 如果有聊天文本，先通过解析器预处理（支持多格式）
    if chat and chat_filename:
        from app.chat_parser import ChatParser
        parser = ChatParser()
        parse_result = parser.parse(chat, target_name=name, filename=chat_filename)
        if parse_result.total_messages > 0:
            chat = parse_result.summary_text(max_chars=8000)

    # 解析用户选择的模型端点
    endpoint = get_endpoint_by_name(model_name) if model_name else None

    engine = get_distill_engine()
    result = engine.distill(name, chat, desc, tags, endpoint=endpoint)

    if result.success and auto_create:
        sm = get_soul_manager()
        create_result = sm.create_persona(
            result.slug, result.name, result.persona,
            result.memories, desc
        )
        if create_result.get("success"):
            sm.switch_persona(result.slug)
            result.stats["created"] = True
            result.stats["slug"] = result.slug

    return result.to_dict()

@app.post("/api/distill/correct")
async def api_distill_correct(request: Request):
    """对话纠正 — 用户说"她不会这样"时触发"""
    from app.distill_engine import get_distill_engine
    body = await request.json()
    slug = body.get("slug", "")
    feedback = body.get("feedback", "")
    if not slug or not feedback:
        return {"success": False, "error": "slug 和 feedback 必填"}
    return get_distill_engine().evolve_correct(slug, feedback)

@app.post("/api/distill/append")
async def api_distill_append(request: Request):
    """追加材料 — 增量进化角色"""
    from app.distill_engine import get_distill_engine
    body = await request.json()
    slug = body.get("slug", "")
    material = body.get("material", "")
    target = body.get("target_name", "")
    if not slug or not material:
        return {"success": False, "error": "slug 和 material 必填"}
    return get_distill_engine().evolve_append(slug, material, target)

# ============================================================
#  v2.0: 行为洞察 API
# ============================================================
@app.get("/api/insights")
async def api_get_insights():
    """获取行为洞察报告"""
    from app.insights_engine import get_insights_engine
    engine = get_insights_engine()
    report = engine.generate(days=7)
    return {
        "summary": engine.format_summary(report),
        "detail": engine.format_detail(report),
        "raw": report,
    }

# ============================================================
#  v3.0: 隐私保护 API
# ============================================================
@app.get("/api/privacy/status")
async def api_privacy_status():
    """获取隐私保护状态和统计"""
    from app.privacy_filter import get_filter, get_model_router
    f = get_filter()
    stats = f.get_stats()
    history = f.get_history(limit=20)
    # 路由统计
    try:
        router_stats = get_model_router().get_stats()
    except Exception:
        router_stats = {}
    return {
        "stats": stats,
        "history": history,
        "blacklist": f._custom_blacklist,
        "router_stats": router_stats,
    }

@app.post("/api/privacy/blacklist")
async def api_privacy_blacklist(request: Request):
    """添加自定义敏感词"""
    from app.privacy_filter import get_filter
    body = await request.json()
    words = body.get("words", [])
    if not words:
        return {"success": False, "error": "words 不能为空"}
    f = get_filter()
    f.add_blacklist(words)
    return {
        "success": True,
        "blacklist": f._custom_blacklist,
        "count": len(f._custom_blacklist),
    }

@app.delete("/api/privacy/blacklist/{word}")
async def api_privacy_blacklist_remove(word: str):
    """移除自定义敏感词"""
    from app.privacy_filter import get_filter
    f = get_filter()
    if word in f._custom_blacklist:
        f._custom_blacklist.remove(word)
        return {"success": True, "blacklist": f._custom_blacklist}
    return {"success": False, "error": "该词不在黑名单中"}

# ============================================================
#  v2.0: FactMemory API
# ============================================================
@app.get("/api/facts")
async def api_get_facts():
    """获取所有用户事实"""
    from app.fact_memory import get_fact_memory
    fm = get_fact_memory()
    return {
        "facts": fm.get_all_facts(100),
        "stats": fm.get_stats(),
    }

@app.get("/api/facts/search")
async def api_search_facts(q: str = ""):
    """搜索用户事实"""
    from app.fact_memory import get_fact_memory
    if not q:
        return {"facts": []}
    return {"facts": get_fact_memory().search_facts(q)}

# ============================================================
#  沙盒环境 API
# ============================================================
@app.get("/api/sandbox")
async def api_get_sandbox():
    """获取当前沙盒配置"""
    from app.action_engine import SANDBOX_ROOTS, FORBIDDEN_PATHS
    return {
        "sandbox_roots": SANDBOX_ROOTS,
        "forbidden_paths": FORBIDDEN_PATHS,
    }

@app.post("/api/sandbox/update")
async def api_update_sandbox(request: Request):
    """更新沙盒配置"""
    from app.action_engine import SANDBOX_ROOTS, FORBIDDEN_PATHS
    body = await request.json()

    new_roots = body.get("sandbox_roots")
    if new_roots is not None:
        SANDBOX_ROOTS.clear()
        SANDBOX_ROOTS.extend([os.path.normpath(p) for p in new_roots if p.strip()])

    new_forbidden = body.get("forbidden_paths")
    if new_forbidden is not None:
        FORBIDDEN_PATHS.clear()
        FORBIDDEN_PATHS.extend([os.path.normpath(p) for p in new_forbidden if p.strip()])

    # 持久化到 data/sandbox.json
    sandbox_data = {
        "sandbox_roots": SANDBOX_ROOTS,
        "forbidden_paths": FORBIDDEN_PATHS,
    }
    os.makedirs("data", exist_ok=True)
    with open("data/sandbox.json", "w", encoding="utf-8") as f:
        json.dump(sandbox_data, f, ensure_ascii=False, indent=2)

    return {"success": True, "message": "沙盒配置已更新"}

# ============================================================
#  微信 iLink Bot API
# ============================================================
from starlette.responses import StreamingResponse

@app.get("/api/wechat/qr-login")
async def api_wechat_qr_login():
    """
    QR 码扫描登录（SSE 流式推送）

    前端通过 EventSource 连接，接收 QR 状态:
      - pending:   附带 qrcode_url (base64 图片)
      - scanned:   用户已扫码
      - confirmed: 登录成功，自动启动桥接
      - expired:   QR 已过期
      - error:     登录失败
    """
    from app.wechat_bridge import qr_login, get_bridge

    async def sse_stream():
        async for state in qr_login():
            data = {
                "status": state.status,
                "qrcode_url": state.qrcode_url or "",
                "error": state.error or "",
            }
            # 登录成功 → 自动启动桥接
            if state.status == "confirmed" and state.credentials:
                bridge = get_bridge()
                await bridge.start_with_credentials(state.credentials)
                data["account_id"] = state.credentials.account_id[:8] + "***"
                data["message"] = "login success, bridge started"

            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

        yield "data: {\"status\": \"done\"}\n\n"

    return StreamingResponse(sse_stream(), media_type="text/event-stream")

# ── QR 登录 REST 方式（Edge 兼容）──────────────────────────
import threading
_qr_login_state = {"qrcode": "", "qrcode_url": "", "status": "idle", "error": ""}
_qr_login_lock = threading.Lock()

@app.post("/api/wechat/qr-get")
async def api_wechat_qr_get():
    """获取 QR 码（非 SSE，普通 REST）"""
    import httpx
    from app.ilink_client import (
        ilink_post, generate_qr_b64, _random_uin,
        EP_GET_BOT_QR, QR_TIMEOUT,
    )
    global _qr_login_state
    base_url = "https://ilinkai.weixin.qq.com"

    try:
        async with httpx.AsyncClient() as client:
            qr_resp = await ilink_post(
                client, base_url,
                f"{EP_GET_BOT_QR}?bot_type=3",
                {}, None, QR_TIMEOUT,
            )
            if qr_resp.get("ret", -1) != 0 or not qr_resp.get("qrcode"):
                return {"success": False, "error": qr_resp.get("errmsg", "get QR failed")}

            qrcode = qr_resp["qrcode"]

            # 获取图片
            qr_img_b64 = qr_resp.get("qrcode_img_content_base64", "") \
                or qr_resp.get("img_content", "")
            qr_img_url = qr_resp.get("qrcode_img_url", "") \
                or qr_resp.get("qrcode_url", "") \
                or qr_resp.get("qrcode_img_content", "")

            if qr_img_b64:
                qrcode_url = qr_img_b64 if qr_img_b64.startswith("data:") \
                    else f"data:image/png;base64,{qr_img_b64}"
            elif qr_img_url:
                try:
                    resp = await client.get(qr_img_url, timeout=10)
                    ct = resp.headers.get("content-type", "").split(";")[0].strip()
                    if ct.startswith("image/"):
                        import base64
                        qrcode_url = f"data:{ct};base64,{base64.b64encode(resp.content).decode()}"
                    else:
                        qrcode_url = generate_qr_b64(qr_img_url)
                except Exception:
                    qrcode_url = generate_qr_b64(qr_img_url)
            else:
                qrcode_url = ""

            with _qr_login_lock:
                _qr_login_state = {
                    "qrcode": qrcode,
                    "qrcode_url": qrcode_url,
                    "status": "pending",
                    "error": "",
                    "base_url": base_url,
                }

            return {"success": True, "qrcode_url": qrcode_url, "status": "pending"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/wechat/qr-check")
async def api_wechat_qr_check():
    """检查扫码状态（前端轮询调用）"""
    import httpx
    from app.ilink_client import (
        ilink_post, Credentials,
        EP_GET_QR_STATUS, QR_TIMEOUT,
    )
    from app.wechat_bridge import get_bridge
    global _qr_login_state

    with _qr_login_lock:
        qrcode = _qr_login_state.get("qrcode", "")
        base_url = _qr_login_state.get("base_url", "https://ilinkai.weixin.qq.com")

    if not qrcode:
        return {"status": "idle", "error": "no QR code, call /api/wechat/qr-get first"}

    try:
        async with httpx.AsyncClient() as client:
            st_resp = await ilink_post(
                client, base_url,
                f"{EP_GET_QR_STATUS}?qrcode={qrcode}",
                {}, None, QR_TIMEOUT,
            )
            status = st_resp.get("status", "wait")

            if status == "scaned":
                return {"status": "scanned"}
            elif status == "scaned_but_redirect":
                if st_resp.get("redirect_host"):
                    with _qr_login_lock:
                        _qr_login_state["base_url"] = f"https://{st_resp['redirect_host']}"
                return {"status": "scanned"}
            elif status == "confirmed":
                from datetime import datetime
                creds = Credentials(
                    account_id=st_resp.get("ilink_bot_id", ""),
                    token=st_resp.get("bot_token", ""),
                    base_url=st_resp.get("baseurl", base_url),
                    user_id=st_resp.get("ilink_user_id", ""),
                    saved_at=datetime.now().isoformat(),
                )
                if creds.account_id and creds.token:
                    bridge = get_bridge()
                    await bridge.start_with_credentials(creds)
                    with _qr_login_lock:
                        _qr_login_state["status"] = "confirmed"
                    return {"status": "confirmed", "message": "login success, bridge started"}
                return {"status": "error", "error": "incomplete credentials"}
            elif status == "expired":
                with _qr_login_lock:
                    _qr_login_state["status"] = "expired"
                return {"status": "expired"}
            else:
                return {"status": "pending"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/api/wechat/start")
async def api_wechat_start():
    """启动微信桥接（需已有凭证）"""
    from app.wechat_bridge import get_bridge
    return await get_bridge().start()

@app.post("/api/wechat/stop")
async def api_wechat_stop():
    """停止微信桥接"""
    from app.wechat_bridge import get_bridge
    return await get_bridge().stop()

@app.get("/api/wechat/status")
async def api_wechat_status():
    """获取桥接状态"""
    from app.wechat_bridge import get_bridge
    return get_bridge().get_status()

@app.get("/api/wechat/messages")
async def api_wechat_messages():
    """获取最近微信消息（供前端实时同步）"""
    from app.wechat_bridge import get_bridge
    bridge = get_bridge()
    return {"messages": list(bridge._recent_messages)}

@app.post("/api/wechat/logout")
async def api_wechat_logout():
    """登出并清除凭证"""
    from app.wechat_bridge import get_bridge
    return await get_bridge().logout()

@app.get("/api/file/download")
async def api_file_download(path: str):
    """文件下载（供微信截图等使用）"""
    import os
    norm = os.path.normpath(path)
    abs_norm = os.path.abspath(norm)
    # 安全检查：允许项目内 data/ 目录下的文件
    project_data = os.path.abspath("data")
    if not abs_norm.startswith(project_data):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    if not os.path.isfile(abs_norm):
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(abs_norm, filename=os.path.basename(abs_norm))

@app.get("/wechat-login")
async def wechat_login_page():
    """微信 QR 扫码登录页面"""
    from starlette.responses import HTMLResponse
    return HTMLResponse("""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>LocalMindDesk — 微信登录</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    min-height: 100vh; display: flex; align-items: center; justify-content: center;
    background: #f5f7fa;
    font-family: 'DM Sans', -apple-system, 'Segoe UI', sans-serif; color: #1a2332;
  }
  .card {
    background: #fff; border: 1px solid #e4e7ec;
    border-radius: 20px; padding: 40px; text-align: center;
    box-shadow: 0 8px 32px rgba(0,0,0,0.08); max-width: 420px; width: 90%;
  }
  h1 { font-size: 24px; margin-bottom: 8px; color: #059669; }
  .subtitle { color: #8896a6; font-size: 14px; margin-bottom: 24px; }
  #qr-container {
    width: 260px; height: 260px; margin: 0 auto 20px;
    background: #f7f8fa; border-radius: 12px; padding: 10px;
    display: flex; align-items: center; justify-content: center;
    border: 1px solid #e4e7ec;
  }
  #qr-container img { max-width: 100%; max-height: 100%; border-radius: 4px; }
  #status {
    padding: 12px 20px; border-radius: 10px; font-size: 15px; font-weight: 500;
    margin-top: 16px; transition: all 0.3s;
  }
  .pending { background: rgba(5,150,105,0.08); color: #059669; }
  .scanned { background: rgba(5,150,105,0.12); color: #059669; }
  .confirmed { background: rgba(5,150,105,0.15); color: #059669; }
  .error { background: rgba(231,76,60,0.08); color: #e74c3c; }
  .expired { background: rgba(241,196,15,0.08); color: #d4a617; }
  .spinner { display: inline-block; width: 20px; height: 20px; border: 2px solid #059669;
    border-top-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite;
    vertical-align: middle; margin-right: 8px; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .tip { color: #8896a6; font-size: 12px; margin-top: 16px; }
  #retry-btn { display: none; margin-top: 16px; padding: 10px 24px; border: none;
    background: #059669; color: white; border-radius: 8px; font-size: 14px;
    cursor: pointer; transition: background 0.2s; }
  #retry-btn:hover { background: #047857; }
  #debug { display: none; margin-top: 12px; padding: 8px; background: #f4f5f7;
    border-radius: 6px; font-size: 11px; color: #666; text-align: left;
    max-height: 100px; overflow-y: auto; word-break: break-all; }
</style>
</head>
<body>
<div class="card">
  <h1>🐾 微信登录</h1>
  <p class="subtitle">LocalMindDesk — iLink Bot</p>
  <div id="qr-container"><span class="spinner"></span> 加载中...</div>
  <div id="status" class="pending"><span class="spinner"></span> 正在获取二维码...</div>
  <button id="retry-btn" onclick="startLogin()">重新获取</button>
  <p class="tip">请使用微信扫描二维码登录</p>
  <div id="debug"></div>
</div>
<script>
var pollTimer = null;

async function startLogin() {
  var qrC = document.getElementById('qr-container');
  var stEl = document.getElementById('status');
  var retryBtn = document.getElementById('retry-btn');
  var dbg = document.getElementById('debug');

  // 清理
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  retryBtn.style.display = 'none';
  dbg.style.display = 'none';
  qrC.innerHTML = '<span class="spinner"></span> 加载中...';
  stEl.className = 'pending';
  stEl.innerHTML = '<span class="spinner"></span> 正在获取二维码...';

  try {
    // 1. 获取 QR 码
    var r = await fetch('/api/wechat/qr-get', { method: 'POST' });
    var d = await r.json();

    // 调试信息
    dbg.style.display = 'block';
    dbg.textContent = 'API Response: ' + JSON.stringify(d).substring(0, 500);

    if (d.success && d.qrcode_url) {
      qrC.innerHTML = '<img src="' + d.qrcode_url + '" alt="QR">';
      stEl.className = 'pending';
      stEl.textContent = '📱 请用微信扫描二维码';

      // 2. 轮询扫码状态（每 2 秒）
      pollTimer = setInterval(checkStatus, 2000);
    } else {
      stEl.className = 'error';
      stEl.textContent = '❌ ' + (d.error || '获取二维码失败');
      retryBtn.style.display = 'inline-block';
    }
  } catch (e) {
    stEl.className = 'error';
    stEl.textContent = '❌ 请求失败: ' + e.message;
    retryBtn.style.display = 'inline-block';
  }
}

async function checkStatus() {
  var stEl = document.getElementById('status');
  var retryBtn = document.getElementById('retry-btn');

  try {
    var r = await fetch('/api/wechat/qr-check');
    var d = await r.json();

    if (d.status === 'scanned') {
      stEl.className = 'scanned';
      stEl.textContent = '✅ 已扫码，请在手机上确认';
    } else if (d.status === 'confirmed') {
      stEl.className = 'confirmed';
      stEl.textContent = '🎉 登录成功！桥接已启动';
      clearInterval(pollTimer); pollTimer = null;
      setTimeout(function() { stEl.textContent += ' — 可以在微信中对话了'; }, 1500);
    } else if (d.status === 'expired') {
      stEl.className = 'expired';
      stEl.textContent = '⏰ 二维码已过期';
      retryBtn.style.display = 'inline-block';
      clearInterval(pollTimer); pollTimer = null;
    } else if (d.status === 'error') {
      stEl.className = 'error';
      stEl.textContent = '❌ ' + (d.error || '检查状态失败');
      retryBtn.style.display = 'inline-block';
      clearInterval(pollTimer); pollTimer = null;
    }
    // pending → 继续轮询
  } catch (e) {
    // 网络错误，不停止轮询，静默重试
  }
}

startLogin();
</script>
</body>
</html>""")

# ============================================================
#  静态文件 + SPA 路由
# ============================================================
# 挂载前端静态文件
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dir, "assets")), name="assets") if os.path.exists(os.path.join(frontend_dir, "assets")) else None

@app.get("/")
async def serve_index():
    index_path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "LocalMindDesk API is running. Frontend not found."}

@app.get("/{path:path}")
async def serve_static(path: str):
    """兜底：尝试返回前端静态文件"""
    file_path = os.path.join(frontend_dir, path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)
    # SPA 回退
    index_path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse({"error": "not found"}, status_code=404)

# ============================================================
#  启动
# ============================================================
def main():
    print(r"""
  _                    _ __  __ _           _ ____            _    
 | |    ___   ___ __ _| |  \/  (_)_ __   __| |  _ \  ___  ___| | __
 | |   / _ \ / __/ _` | | |\/| | | '_ \ / _` | | | |/ _ \/ __| |/ /
 | |__| (_) | (_| (_| | | |  | | | | | | (_| | |_| |  __/\__ \   < 
 |_____\___/ \___\__,_|_|_|  |_|_|_| |_|\__,_|____/ \___||___/_|\_\
                                          v2 (Python)
    """)

    cfg = load_config()
    endpoint = get_active_endpoint()

    print(f"[CONFIG] 主模型: {cfg.active_model}")
    if endpoint:
        print(f"[CONFIG] Provider: {endpoint.provider}")
        print(f"[CONFIG] Base URL: {endpoint.base_url}")
        print(f"[CONFIG] Model ID: {endpoint.model}")
    print(f"[CONFIG] Temperature: {cfg.temperature}")
    print(f"[CONFIG] 已配置 {len(cfg.models)} 个模型端点")

    # 确保数据目录存在
    os.makedirs("data", exist_ok=True)
    for f in ["data/skills.md", "data/memory.md"]:
        if not os.path.exists(f):
            open(f, "w").close()

    print(f"\n{'='*50}")
    print(f"  LocalMindDesk v2 已启动")
    print(f"  聊天界面: http://localhost:{cfg.server_port}")
    print(f"{'='*50}\n")

    # 初始化应用集成管理器
    from app.integrations.manager import get_manager
    integration_mgr = get_manager()
    print(f"[Integration] 已加载 {len(integration_mgr._integrations)} 个集成模块")

    # 初始化定时任务调度器
    from app.scheduler import get_scheduler
    scheduler = get_scheduler()

    def _scheduler_handler(action: str, params: dict, safety: str, tags: list = None) -> dict:
        """定时任务执行回调"""
        tags = tags or []

        def _send_wechat_sync(user, message):
            """发送微信消息（同步版，兼容所有调用上下文）"""
            from app.wechat_bridge import get_bridge
            bridge = get_bridge()
            if not bridge.is_online:
                print(f"[Scheduler] 微信未连接，消息: {message[:30]}")
                return False
            # 如果 user 不是 iLink 格式的 user_id，替换为 owner
            if not user.startswith("o") or len(user) < 10:
                real_user = bridge._owner_user_id
                if real_user:
                    print(f"[Scheduler] 用户映射: {user} → {real_user}")
                    user = real_user
                else:
                    print(f"[Scheduler] 无法确定发送目标用户")
                    return False
            bridge.send_text_sync(user, message)
            print(f"[Scheduler] ✅ 微信已发送给 {user}: {message[:30]}")
            return True

        if action in ("send_wechat", "send_message"):
            user = params.get("user", "文件传输助手")
            message = params.get("message", "")
            try:
                ok = _send_wechat_sync(user, message)
                if ok:
                    return {"success": True, "message": f"已发送到微信: {message}"}
                else:
                    return {"success": False, "message": f"微信未连接，消息: {message}"}
            except Exception as e:
                print(f"[Scheduler] 微信发送失败: {e}")
                return {"success": False, "message": str(e)}
        elif action == "reminder":
            # 本地提醒 — 通过 proactive engine 推送到前端 Toast
            msg = params.get("message", "提醒")
            print(f"[Scheduler] 📢 提醒: {msg}")

            # 如果带 wechat 标签，同时发送到微信
            if "wechat" in tags:
                try:
                    user = params.get("user", "文件传输助手")
                    _send_wechat_sync(user, msg)
                except Exception as e:
                    print(f"[Scheduler] 微信发送失败: {e}")

            return {"success": True, "message": msg}
        elif action == "terminal":
            # 执行终端命令
            if safety == "sensitive":
                return {"success": False, "message": "敏感操作需要确认，请在界面上手动执行"}
            cmd = params.get("cmd", "")
            if cmd:
                success, output = _run_terminal_cmd(cmd)
                return {"success": success, "message": output}
            return {"success": False, "message": "命令为空"}
        else:
            return {"success": False, "message": f"未知动作: {action}"}

    scheduler.set_action_handler(_scheduler_handler)
    scheduler.start()
    print(f"[Scheduler] {len(scheduler._tasks)} 个定时任务已加载")

    # 启动主动对话引擎（空闲问候、定时通知推送等）
    from app.proactive_engine import get_proactive_engine
    pe = get_proactive_engine()
    pe.start()
    print("[ProactiveEngine] 主动对话引擎已启动")

    # 微信桥接自动重连（有已保存凭证则免扫码）
    import asyncio
    async def _auto_start_wechat():
        await asyncio.sleep(1)  # 等 uvicorn 就绪
        from app.wechat_bridge import auto_start
        await auto_start()

    @app.on_event("startup")
    async def _on_startup():
        asyncio.create_task(_auto_start_wechat())

    uvicorn.run(app, host="0.0.0.0", port=cfg.server_port, log_level="info")

if __name__ == "__main__":
    main()
