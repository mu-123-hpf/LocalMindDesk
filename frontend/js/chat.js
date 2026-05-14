// ============================================================
//  LocalMindDesk — 聊天消息模块
//  发送/接收/渲染消息，中断，模式命令
//  v2: 支持 SSE 流式输出
// ============================================================

// --- 时间戳工具 ---
let _lastMsgTimestamp = 0;

function maybeInsertTimeDivider() {
  const now = Date.now();
  if (_lastMsgTimestamp && (now - _lastMsgTimestamp) > 5 * 60 * 1000) {
    const divider = document.createElement('div');
    divider.className = 'time-divider';
    const time = new Date(now);
    const h = String(time.getHours()).padStart(2, '0');
    const m = String(time.getMinutes()).padStart(2, '0');
    divider.innerHTML = `<span>${h}:${m}</span>`;
    $msg.appendChild(divider);
  }
  _lastMsgTimestamp = now;
}

function appendMsg(role, content) {
  maybeInsertTimeDivider();

  const div = document.createElement('div');
  div.className = `msg ${role}`;

  const avatar = role === 'user' ? '👤' : '🐾';
  const label = role === 'user' ? 'You' : 'LocalMindDesk';

  let html = content;
  if (role === 'assistant' && typeof marked !== 'undefined') {
    try { html = marked.parse(content); } catch { html = esc(content); }
  } else {
    html = esc(content);
  }

  // 构建消息操作按钮（仅 AI 消息）
  const actionsHtml = role === 'assistant' ? `
      <div class="msg-actions">
        <button class="msg-action-btn" data-action="copy" title="复制">📋</button>
        <button class="msg-action-btn" data-action="regenerate" title="重新生成">🔄</button>
      </div>` : '';

  div.innerHTML = `
    <div class="msg-avatar">${avatar}</div>
    <div class="msg-body">
      <div class="msg-role">${label}</div>
      <div class="msg-content">${html}</div>
      ${actionsHtml}
    </div>`;

  // 绑定操作按钮事件
  if (role === 'assistant') {
    div.querySelectorAll('.msg-action-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const action = btn.dataset.action;
        if (action === 'copy') {
          const text = div.querySelector('.msg-content').textContent;
          navigator.clipboard.writeText(text).then(() => {
            btn.textContent = '✅';
            setTimeout(() => { btn.textContent = '📋'; }, 1500);
          });
        } else if (action === 'regenerate') {
          // 移除最后一条 AI 消息并重新发送
          if (chatHistory.length >= 2) {
            chatHistory.pop(); // 移除 AI 回复
            const lastUserMsg = chatHistory[chatHistory.length - 1];
            div.remove(); // 移除 DOM
            $input.value = lastUserMsg.content;
            sendMessage();
          }
        }
      });
    });
  }

  $msg.appendChild(div);

  // 给代码块注入复制按钮
  injectCodeCopyButtons(div);

  $wrap.scrollTop = $wrap.scrollHeight;
}

/**
 * 创建空的 AI 消息 DOM（用于流式填充）
 * 返回 { div, contentEl }
 */
function createEmptyAssistantMsg() {
  maybeInsertTimeDivider();

  const div = document.createElement('div');
  div.className = 'msg assistant';
  div.innerHTML = `
    <div class="msg-avatar">🐾</div>
    <div class="msg-body">
      <div class="msg-role">LocalMindDesk</div>
      <div class="msg-content"><span class="stream-cursor">▍</span></div>
      <div class="msg-actions">
        <button class="msg-action-btn" data-action="copy" title="复制">📋</button>
        <button class="msg-action-btn" data-action="regenerate" title="重新生成">🔄</button>
      </div>
    </div>`;

  $msg.appendChild(div);
  $wrap.scrollTop = $wrap.scrollHeight;

  return {
    div,
    contentEl: div.querySelector('.msg-content'),
  };
}

/**
 * 流式完成后的收尾：绑定按钮事件、注入代码复制、移除光标
 */
function finalizeStreamMsg(div, fullReply) {
  const contentEl = div.querySelector('.msg-content');

  // ★ Preserve any step blocks before re-rendering markdown
  const stepBlocks = Array.from(contentEl.querySelectorAll('.step-block'));
  stepBlocks.forEach(b => b.remove());

  // 最终渲染（确保完整 markdown）
  if (typeof marked !== 'undefined') {
    try { contentEl.innerHTML = marked.parse(fullReply); } catch { }
  }

  // Re-insert step blocks at the top of the content
  if (stepBlocks.length > 0) {
    const firstChild = contentEl.firstChild;
    stepBlocks.reverse().forEach(b => {
      contentEl.insertBefore(b, firstChild);
    });
  }

  // 注入代码复制按钮
  injectCodeCopyButtons(div);

  // 绑定操作按钮
  div.querySelectorAll('.msg-action-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const action = btn.dataset.action;
      if (action === 'copy') {
        navigator.clipboard.writeText(fullReply).then(() => {
          btn.textContent = '✅';
          setTimeout(() => { btn.textContent = '📋'; }, 1500);
        });
      } else if (action === 'regenerate') {
        if (chatHistory.length >= 2) {
          chatHistory.pop();
          const lastUserMsg = chatHistory[chatHistory.length - 1];
          div.remove();
          $input.value = lastUserMsg.content;
          sendMessage();
        }
      }
    });
  });
}


function esc(t) {
  const d = document.createElement('div');
  d.textContent = t;
  return d.innerHTML.replace(/\n/g, '<br>');
}

// 给代码块注入复制按钮
function injectCodeCopyButtons(container) {
  if (!container) return;
  const pres = container.querySelectorAll('pre');
  pres.forEach(pre => {
    // 避免重复注入
    if (pre.querySelector('.code-copy-btn')) return;
    const btn = document.createElement('button');
    btn.className = 'code-copy-btn';
    btn.textContent = '📋 复制';
    btn.onclick = function(e) {
      e.stopPropagation();
      const code = pre.querySelector('code');
      const text = code ? code.textContent : pre.textContent;
      navigator.clipboard.writeText(text).then(() => {
        btn.textContent = '✓ 已复制';
        btn.classList.add('copied');
        setTimeout(() => {
          btn.textContent = '📋 复制';
          btn.classList.remove('copied');
        }, 2000);
      }).catch(() => {
        // fallback
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        btn.textContent = '✓ 已复制';
        btn.classList.add('copied');
        setTimeout(() => {
          btn.textContent = '📋 复制';
          btn.classList.remove('copied');
        }, 2000);
      });
    };
    pre.appendChild(btn);
  });
}

// ============================================================
//  Collapsible Workflow Steps (Antigravity-style)
// ============================================================

const STEP_ICONS = {
  thinking: '💭',
  search:   '🔍',
  file:     '📁',
  command:  '🔧',
  tool:     '⚙️',
  default:  '▸',
};

/**
 * Create a collapsible step block inside the AI message content area.
 * Returns the step block DOM element.
 */
function createStepBlock(contentEl, stepId, stepType, summary) {
  const block = document.createElement('div');
  block.className = 'step-block step-active';
  block.dataset.stepId = stepId;
  block.dataset.type = stepType || 'default';
  block.setAttribute('data-type', stepType || 'default');

  const icon = STEP_ICONS[stepType] || STEP_ICONS.default;

  block.innerHTML = `
    <div class="step-header">
      <svg class="step-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="9 18 15 12 9 6"></polyline>
      </svg>
      <span class="step-icon">${icon}</span>
      <span class="step-summary">${escStep(summary)}</span>
      <span class="step-spinner"></span>
    </div>
    <div class="step-body"></div>
  `;

  // Toggle expand/collapse on header click
  block.querySelector('.step-header').addEventListener('click', () => {
    block.classList.toggle('step-expanded');
  });

  // Insert before the stream cursor (or at end)
  const cursor = contentEl.querySelector('.stream-cursor');
  if (cursor) {
    contentEl.insertBefore(block, cursor);
  } else {
    contentEl.appendChild(block);
  }

  return block;
}

/**
 * Append content to an existing step block's body.
 */
function updateStepContent(contentEl, stepId, text) {
  const block = contentEl.querySelector(`.step-block[data-step-id="${stepId}"]`);
  if (!block) return;
  const body = block.querySelector('.step-body');
  if (body) {
    body.textContent += text;
  }
}

/**
 * Finalize a step block: remove spinner, update summary, set duration.
 */
function finalizeStepBlock(contentEl, stepId, finalSummary, durationMs) {
  const block = contentEl.querySelector(`.step-block[data-step-id="${stepId}"]`);
  if (!block) return;

  block.classList.remove('step-active');

  // Remove spinner
  const spinner = block.querySelector('.step-spinner');
  if (spinner) spinner.remove();

  // Update summary
  if (finalSummary) {
    const summaryEl = block.querySelector('.step-summary');
    if (summaryEl) summaryEl.textContent = finalSummary;
  }

  // Add duration badge
  if (durationMs != null) {
    const durEl = document.createElement('span');
    durEl.className = 'step-duration';
    durEl.textContent = durationMs >= 1000
      ? `${(durationMs / 1000).toFixed(1)}s`
      : `${Math.round(durationMs)}ms`;
    block.querySelector('.step-header').appendChild(durEl);
  }

  // Auto-collapse completed steps (unless user expanded)
  if (block.classList.contains('step-expanded')) return;
  // Keep collapsed by default
}

function escStep(t) {
  const d = document.createElement('span');
  d.textContent = t;
  return d.innerHTML;
}

// ============================================================
//  Sandbox Permission Request UI
// ============================================================
function createPermissionBlock(contentEl, reqId, path, reason, action) {
  const block = document.createElement('div');
  block.className = 'step-block step-active permission-block';
  block.dataset.stepId = reqId;
  block.dataset.type = 'permission';
  block.setAttribute('data-type', 'command');

  block.innerHTML = `
    <div class="step-header" style="border-left-color: #f59e0b;">
      <svg class="step-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="9 18 15 12 9 6"></polyline>
      </svg>
      <span class="step-icon">🔒</span>
      <span class="step-summary">请求沙盒外访问权限</span>
      <span class="step-spinner"></span>
    </div>
    <div class="step-body" style="max-height:200px; padding: 8px 14px 10px 26px;">
      <div style="margin-bottom:8px; color: var(--text-2); font-family: inherit; font-size: 12.5px;">
        <div><strong>操作:</strong> ${escStep(action)}</div>
        <div><strong>路径:</strong> <code style="color:var(--accent)">${escStep(path)}</code></div>
        ${reason ? `<div><strong>原因:</strong> ${escStep(reason)}</div>` : ''}
      </div>
      <div class="permission-actions" style="display:flex; gap:8px; margin-top:6px;">
        <button class="perm-btn perm-allow" data-req-id="${reqId}" data-path="${escStep(path)}"
                style="padding:4px 14px; border-radius:6px; border:1px solid #10b981; background:rgba(16,185,129,0.1); color:#10b981; cursor:pointer; font-size:12px; font-weight:500;">
          ✅ 允许
        </button>
        <button class="perm-btn perm-deny" data-req-id="${reqId}"
                style="padding:4px 14px; border-radius:6px; border:1px solid #ef4444; background:rgba(239,68,68,0.08); color:#ef4444; cursor:pointer; font-size:12px; font-weight:500;">
          ❌ 拒绝
        </button>
      </div>
    </div>
  `;

  // Expand by default (user needs to see and act)
  block.classList.add('step-expanded');

  // Toggle header
  block.querySelector('.step-header').addEventListener('click', (e) => {
    if (e.target.closest('.perm-btn')) return;
    block.classList.toggle('step-expanded');
  });

  // Allow button
  block.querySelector('.perm-allow').addEventListener('click', async () => {
    try {
      const resp = await fetch('/api/sandbox/grant', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: path, reason: reason, action: action }),
      });
      const data = await resp.json();
      _resolvePermission(block, reqId, data.granted, data.reason || '已授权');
    } catch (err) {
      _resolvePermission(block, reqId, false, '授权请求失败');
    }
  });

  // Deny button
  block.querySelector('.perm-deny').addEventListener('click', () => {
    _resolvePermission(block, reqId, false, '用户拒绝访问');
  });

  const cursor = contentEl.querySelector('.stream-cursor');
  if (cursor) {
    contentEl.insertBefore(block, cursor);
  } else {
    contentEl.appendChild(block);
  }

  return block;
}

function _resolvePermission(block, reqId, granted, message) {
  block.classList.remove('step-active');
  const spinner = block.querySelector('.step-spinner');
  if (spinner) spinner.remove();

  // Remove buttons
  const actions = block.querySelector('.permission-actions');
  if (actions) {
    actions.innerHTML = `<span style="font-size:12px; color: ${granted ? '#10b981' : '#ef4444'};">
      ${granted ? '✅ 已允许' : '❌ 已拒绝'} — ${escStep(message)}
      ${!granted ? '<br><span style="opacity:0.6; font-size:11px;">AI 将停止此路径的相关操作</span>' : ''}
    </span>`;
  }

  // Update summary
  const summary = block.querySelector('.step-summary');
  if (summary) {
    summary.textContent = granted ? '权限已授予' : '权限已拒绝 — AI 将停止此操作';
  }

  // Collapse after resolution
  setTimeout(() => block.classList.remove('step-expanded'), 1500);

  // Store result for backend to pick up
  window._permissionResults = window._permissionResults || {};
  window._permissionResults[reqId] = { granted, message };

  // ★ 通知后端用户的决定
  fetch('/api/sandbox/resolve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      permission_id: reqId,
      granted: granted,
      message: message,
    }),
  }).catch(() => {});

  // ★ 如果授权了，刷新沙盒配置
  if (granted && typeof loadSandbox === 'function') {
    setTimeout(loadSandbox, 500);
  }
}

function appendFileCard(fileName, filePath) {
  const ext = fileName.split('.').pop().toLowerCase();
  const icons = { pptx: '📊', docx: '📄', pdf: '📕', xlsx: '📗' };
  const icon = icons[ext] || '📎';

  const div = document.createElement('div');
  div.className = 'msg assistant';
  div.innerHTML = `
    <div class="msg-avatar">🧠</div>
    <div class="msg-body">
      <div class="file-card">
        <div class="file-icon">${icon}</div>
        <div class="file-info">
          <span class="file-name">${fileName}</span>
          <span class="file-ext">${ext.toUpperCase()} 文件</span>
        </div>
        <a href="/api/files/${encodeURIComponent(fileName)}" download="${fileName}" class="btn-download">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          下载
        </a>
      </div>
    </div>`;
  $msg.appendChild(div);
  $wrap.scrollTop = $wrap.scrollHeight;
}

// ============================================================
//  发送消息（职责分离重构）
// ============================================================

// 停止生成
function stopGenerating() {
  if (currentAbortController) {
    currentAbortController.abort();
    currentAbortController = null;
  }
  isGenerating = false;
  $typing.classList.remove('show');
  setSendButtonState('idle');
  appendMsg('assistant', '⏹ 已中断输出');
}

// 切换发送按钮状态
function setSendButtonState(state) {
  if (state === 'generating') {
    $send.disabled = false;
    $send.classList.add('btn-stop');
    $send.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>';
    $send.title = '停止生成';
  } else {
    $send.classList.remove('btn-stop');
    $send.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/></svg>';
    $send.title = '发送';
    $send.disabled = !$input.value.trim();
  }
}

// --- 1. 提取并处理输入文本 ---
function extractAndProcessInput() {
  let text = $input.value.trim();
  if (!text || isGenerating) return null;

  // 检测模式切换命令（/plan, /execute, /collaborate, /review）
  const modeCmd = text.match(/^\/(plan|execute|exec|collaborate|collab|review)\b/i);
  if (modeCmd) {
    const modeMap = { plan: 'plan', execute: 'execute', exec: 'execute', collaborate: 'collaborate', collab: 'collaborate', review: 'review' };
    const newMode = modeMap[modeCmd[1].toLowerCase()];
    switchMode(newMode);
    const rest = text.slice(modeCmd[0].length).trim();
    if (!rest) {
      $input.value = '';
      $input.style.height = 'auto';
      appendMsg('assistant', `${MODE_CONFIG[newMode].icon} 已切换到 **${MODE_CONFIG[newMode].label}** 模式\n> ${MODE_CONFIG[newMode].desc}`);
      return null;
    }
    text = rest;
  }

  detectWorkspaceCommand(text);
  return text;
}

// --- 2. 准备 UI 状态（发送前） ---
async function prepareForGeneration(text) {
  $welcome.style.display = 'none';
  appendMsg('user', text);
  chatHistory.push({ role: 'user', content: text });
  await ensureSession(text);

  $input.value = '';
  $input.style.height = 'auto';
  isGenerating = true;
  setSendButtonState('generating');
  $typing.classList.add('show');

  window.dispatchEvent(new CustomEvent('LocalMindDesk:pet', { detail: { action: 'ai-thinking' } }));
  currentAbortController = new AbortController();
}

// --- 3. 调用 Chat API (同步，降级用) ---
async function callChatAPI(text) {
  const r = await fetch(API + '/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: text,
      history: chatHistory.slice(-20),
      session_id: currentSessionId,
      mode: currentMode,
    }),
    signal: currentAbortController.signal,
  });
  return r.json();
}

// --- 3b. 调用流式 Chat API (SSE) ---
async function callChatStreamAPI(text) {
  const r = await fetch(API + '/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: text,
      history: chatHistory.slice(-20),
      session_id: currentSessionId,
      mode: currentMode,
    }),
    signal: currentAbortController.signal,
  });
  return r;
}

// --- 4. 处理 API 响应 (同步) ---
function handleChatResponse(d) {
  const reply = d.reply || '(空回复)';
  $typing.classList.remove('show');

  appendMsg('assistant', reply);
  chatHistory.push({ role: 'assistant', content: reply });
  window.dispatchEvent(new CustomEvent('LocalMindDesk:pet', { detail: { action: 'ai-done' } }));

  // 保存到数据库
  if (currentSessionId) {
    fetch(API + `/api/sessions/${currentSessionId}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role: 'assistant', content: reply }),
    });
    loadSessions();
    saveLocalState();
  }

  // 配置进化 → 热更新 UI
  if (d.profile_update && d.profile_snapshot) {
    const snap = d.profile_snapshot;
    if (snap.identity) {
      document.querySelector('.brand-icon').textContent = snap.identity.icon || '🎭';
      document.querySelector('.brand-name').textContent = snap.identity.name || '助手';
    }
    if (snap.ui_preferences) applyUIPreferences(snap.ui_preferences);
  }

  // 附加内容（文件、操作确认、活动流等）
  if (d.file_name) appendFileCard(d.file_name, d.file_path);
  if (d.action_confirm && d.action_confirm.length > 0) showActionConfirmModal(d.action_confirm);
  if (d.activities && d.activities.length > 0) renderActivityFeed(d.activities);

  if (d.file_changed) {
    loadFileTree();
    if (wsCurrentFile) {
      const activeNode = document.querySelector('.ws-node.active');
      setTimeout(() => openFile(wsCurrentFile, activeNode), 500);
    }
  }

  if (d.context_stats) {
    updateContextBar(d.context_stats);
    renderAgentTimeline(d.context_stats);
  }

  // 智能路由标签
  if (d.route_info) appendRouteTag(d.route_info);
}

// --- 4b. 渲染路由信息标签 ---
function appendRouteTag(ri) {
  const lastMsg = document.querySelector('.msg:last-child .msg-content');
  if (!lastMsg) return;
  const routeIcons = { local: '🏠', cloud: '☁️', filtered: '🛡️' };
  const sensIcons = { safe: '🟢', low: '🟡', high: '🟠', critical: '🔴' };
  const tag = document.createElement('div');
  tag.className = 'route-info-tag';
  tag.title = `模型: ${ri.model_used || 'default'}\n路由: ${ri.route}\n敏感度: ${ri.sensitivity}${ri.sanitized ? '\n已脱敏' : ''}`;
  tag.textContent = `${routeIcons[ri.route] || '🔧'} ${ri.route} ${sensIcons[ri.sensitivity] || ''}`;
  lastMsg.appendChild(tag);
}

// --- 5. 处理错误 ---
function handleChatError(err) {
  $typing.classList.remove('show');
  if (err.name === 'AbortError') return; // 用户主动中断
  appendMsg('assistant', `⚠️ 请求失败: ${err.message}\n\n请检查后端和 LM Studio 是否运行中。`);
  window.dispatchEvent(new CustomEvent('LocalMindDesk:pet', { detail: { action: 'ai-error' } }));
}

// --- 6. 清理生成状态 ---
function finishGeneration() {
  currentAbortController = null;
  isGenerating = false;
  setSendButtonState('idle');
}

// --- Markdown 渲染节流器（流式时避免频繁重排） ---
let _streamRenderTimer = null;
let _streamRenderPending = false;

function throttledRender(contentEl, fullText) {
  _streamRenderPending = true;
  if (_streamRenderTimer) return;
  _streamRenderTimer = setTimeout(() => {
    _streamRenderTimer = null;
    if (_streamRenderPending) {
      _streamRenderPending = false;

      // ★ Preserve step blocks during re-render
      const savedSteps = Array.from(contentEl.querySelectorAll('.step-block'));
      savedSteps.forEach(b => b.remove());

      if (typeof marked !== 'undefined') {
        try {
          contentEl.innerHTML = marked.parse(fullText) + '<span class="stream-cursor">▍</span>';
        } catch {
          contentEl.textContent = fullText;
        }
      } else {
        contentEl.textContent = fullText;
      }

      // Re-insert step blocks at the top
      if (savedSteps.length > 0) {
        const firstChild = contentEl.firstChild;
        savedSteps.reverse().forEach(b => contentEl.insertBefore(b, firstChild));
      }

      $wrap.scrollTop = $wrap.scrollHeight;
    }
  }, 80); // 每 80ms 最多渲染一次
}

// --- 主函数（编排器）— 流式优先 ---
async function sendMessage() {
  const text = extractAndProcessInput();
  if (!text) return;

  await prepareForGeneration(text);

  try {
    // ★ 优先尝试流式 API
    const response = await callChatStreamAPI(text);
    const contentType = response.headers.get('content-type') || '';

    if (contentType.includes('text/event-stream')) {
      // ---- SSE 流式模式 ----
      $typing.classList.remove('show');  // 隐藏"正在思考"

      const { div: aiDiv, contentEl } = createEmptyAssistantMsg();
      let fullReply = '';

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      const _stepTimers = {};  // track step start times

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // 保留不完整的最后一行

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(trimmed.slice(6));
            if (data.done) {
              // ★ Capture token stats from done event
              if (data.token_stats) {
                window._lastTokenStats = data.token_stats;
                // ★ Update context bar with real token data
                if (typeof updateContextBar === 'function') {
                  updateContextBar({
                    totalTokens: data.token_stats.total_tokens || data.token_stats.output_tokens || 0,
                    hotCount: data.token_stats.output_tokens || 0,
                  });
                }
              }
              break;
            }

            // ★ Step events (collapsible workflow blocks)
            if (data.step_start) {
              const s = data.step_start;
              _stepTimers[s.id] = Date.now();
              createStepBlock(contentEl, s.id, s.type || 'default', s.summary || 'Working...');
              $wrap.scrollTop = $wrap.scrollHeight;
            } else if (data.step_update) {
              const s = data.step_update;
              updateStepContent(contentEl, s.id, s.content || '');
            } else if (data.step_end) {
              const s = data.step_end;
              const elapsed = _stepTimers[s.id] ? Date.now() - _stepTimers[s.id] : null;
              finalizeStepBlock(contentEl, s.id, s.summary || null, elapsed);
              $wrap.scrollTop = $wrap.scrollHeight;
            } else if (data.permission_request) {
              // ★ Sandbox permission request
              const p = data.permission_request;
              createPermissionBlock(contentEl, p.id, p.path, p.reason || '', p.action || 'access');
              $wrap.scrollTop = $wrap.scrollHeight;
            } else if (data.delta) {
              // ★ Regular text delta
              fullReply += data.delta;
              throttledRender(contentEl, fullReply);
            }
          } catch { /* 忽略解析错误 */ }
        }
      }

      // 流式完成 → 最终渲染 + 收尾
      chatHistory.push({ role: 'assistant', content: fullReply });
      finalizeStreamMsg(aiDiv, fullReply);

      // ★ Show token usage badge on message
      if (window._lastTokenStats && window._lastTokenStats.session_total_tokens) {
        const ts = window._lastTokenStats;
        const badge = document.createElement('div');
        badge.className = 'token-stats-badge';
        badge.innerHTML = `<span title="本次: ${ts.last_turn_tokens} tokens | 会话累计: ${ts.session_total_tokens} tokens | 平均: ${ts.avg_tokens_per_turn}/轮">📊 ${ts.last_turn_tokens} tok</span>`;
        contentEl.appendChild(badge);
      }

      window.dispatchEvent(new CustomEvent('LocalMindDesk:pet', { detail: { action: 'ai-done' } }));
      $wrap.scrollTop = $wrap.scrollHeight;

      // 保存到数据库
      if (currentSessionId) {
        fetch(API + `/api/sessions/${currentSessionId}/messages`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ role: 'assistant', content: fullReply }),
        });
        loadSessions();
        saveLocalState();
      }

    } else {
      // ---- 非流式（多 Agent / 降级）→ 同步处理 ----
      const d = await response.json();
      handleChatResponse(d);
    }

  } catch (err) {
    handleChatError(err);
  } finally {
    finishGeneration();
  }
}

// 暴露到全局（HTML onclick 需要）
window.sendMessage = sendMessage;
window.stopGenerating = stopGenerating;
window.appendMsg = appendMsg;
window.appendFileCard = appendFileCard;
