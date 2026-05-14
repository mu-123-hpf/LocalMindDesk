"""
LocalMindDesk — IntegrationManager
管理所有外部应用集成的注册、启用/禁用、配置持久化
"""
import json
import os
from typing import Optional
from app.integrations.base import BaseIntegration


DATA_FILE = "data/integrations.json"


class IntegrationManager:
    """
    集成管理器 — 统一管理外部应用集成

    用法:
        mgr = get_manager()
        mgr.register(WeChatIntegration())
        mgr.enable("wechat", {"path": "C:/WeChat/WeChat.exe"})
        status = mgr.get_all_status()
    """

    def __init__(self):
        self._integrations: dict[str, BaseIntegration] = {}
        self._configs: dict[str, dict] = {}       # {id: {config...}}
        self._enabled: dict[str, bool] = {}        # {id: True/False}
        self._connected: dict[str, bool] = {}      # {id: True/False}
        self._load()

    def register(self, integration: BaseIntegration) -> None:
        """注册一个集成模块"""
        self._integrations[integration.id] = integration
        # 如果已有保存的配置，不覆盖
        if integration.id not in self._configs:
            self._configs[integration.id] = {}
        if integration.id not in self._enabled:
            self._enabled[integration.id] = False

    def get(self, integration_id: str) -> Optional[BaseIntegration]:
        """获取集成实例"""
        return self._integrations.get(integration_id)

    def get_all_status(self) -> list[dict]:
        """获取所有集成的状态（供前端渲染）"""
        result = []
        for iid, integration in self._integrations.items():
            result.append(integration.to_dict(
                config=self._configs.get(iid, {}),
                enabled=self._enabled.get(iid, False),
                connected=self._connected.get(iid, False),
            ))
        return result

    def enable(self, integration_id: str, config: dict = None) -> dict:
        """启用集成并连接"""
        integration = self._integrations.get(integration_id)
        if not integration:
            return {"success": False, "error": f"未知集成: {integration_id}"}

        # 更新配置
        if config:
            self._configs[integration_id] = config

        cfg = self._configs.get(integration_id, {})

        # 连接
        try:
            result = integration.connect(cfg)
            if result.get("success"):
                self._enabled[integration_id] = True
                self._connected[integration_id] = True
                # 注册工具到 ToolRegistry
                self._register_tools(integration)
                self._save()
                return {"success": True, "message": result.get("message", "已启用")}
            else:
                return result
        except Exception as e:
            return {"success": False, "error": f"连接失败: {str(e)}"}

    def disable(self, integration_id: str) -> dict:
        """禁用集成"""
        integration = self._integrations.get(integration_id)
        if not integration:
            return {"success": False, "error": f"未知集成: {integration_id}"}

        try:
            integration.disconnect()
        except Exception:
            pass

        self._enabled[integration_id] = False
        self._connected[integration_id] = False
        # 从 ToolRegistry 注销工具
        self._unregister_tools(integration)
        self._save()
        return {"success": True, "message": "已禁用"}

    def test_connection(self, integration_id: str, config: dict = None) -> dict:
        """测试连接"""
        integration = self._integrations.get(integration_id)
        if not integration:
            return {"success": False, "error": f"未知集成: {integration_id}"}

        cfg = config or self._configs.get(integration_id, {})
        try:
            return integration.test_connection(cfg)
        except Exception as e:
            return {"success": False, "error": f"测试失败: {str(e)}"}

    def update_config(self, integration_id: str, config: dict) -> dict:
        """更新配置"""
        if integration_id not in self._integrations:
            return {"success": False, "error": f"未知集成: {integration_id}"}
        self._configs[integration_id] = config
        self._save()
        return {"success": True, "message": "配置已保存"}

    def auto_detect(self, integration_id: str) -> dict:
        """自动检测应用安装信息"""
        integration = self._integrations.get(integration_id)
        if not integration:
            return {"found": False, "info": f"未知集成: {integration_id}"}
        try:
            return integration.auto_detect()
        except Exception as e:
            return {"found": False, "info": f"检测失败: {str(e)}"}

    def init_enabled_integrations(self):
        """启动时自动连接已启用的集成"""
        for iid, enabled in self._enabled.items():
            if enabled and iid in self._integrations:
                cfg = self._configs.get(iid, {})
                try:
                    result = self._integrations[iid].connect(cfg)
                    if result.get("success"):
                        self._connected[iid] = True
                        self._register_tools(self._integrations[iid])
                        print(f"[Integration] ✅ {iid} 已自动连接")
                    else:
                        print(f"[Integration] ⚠️ {iid} 自动连接失败: {result.get('error', '')}")
                except Exception as e:
                    print(f"[Integration] ⚠️ {iid} 自动连接异常: {e}")

    def _register_tools(self, integration: BaseIntegration):
        """将集成的工具注册到 ToolRegistry"""
        from app.tools.registry import get_registry
        registry = get_registry()
        for tool in integration.get_tools():
            registry.register(tool)
            # 同时加入 VALID_TOOLS
            from app.agent_router import VALID_TOOLS
            VALID_TOOLS.add(tool.name)
        print(f"[Integration] 已注册 {integration.id} 的工具: "
              f"{[t.name for t in integration.get_tools()]}")

    def _unregister_tools(self, integration: BaseIntegration):
        """从 ToolRegistry 注销工具"""
        from app.tools.registry import get_registry
        registry = get_registry()
        for tool in integration.get_tools():
            registry.unregister(tool.name)
            from app.agent_router import VALID_TOOLS
            VALID_TOOLS.discard(tool.name)

    def _save(self):
        """持久化到 data/integrations.json"""
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        data = {
            "configs": self._configs,
            "enabled": self._enabled,
        }
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load(self):
        """从文件加载配置"""
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._configs = data.get("configs", {})
                self._enabled = data.get("enabled", {})
            except Exception as e:
                print(f"[Integration] 加载配置失败: {e}")


# ============================================================
#  全局单例
# ============================================================
_manager: Optional[IntegrationManager] = None


def get_manager() -> IntegrationManager:
    """获取全局 IntegrationManager 单例"""
    global _manager
    if _manager is None:
        _manager = IntegrationManager()
        _register_builtin_integrations(_manager)
        _manager.init_enabled_integrations()
    return _manager


def _register_builtin_integrations(mgr: IntegrationManager):
    """注册内置集成"""
    from app.integrations.wechat import WeChatIntegration
    mgr.register(WeChatIntegration())
    print(f"[Integration] 已注册 {len(mgr._integrations)} 个集成: "
          f"{list(mgr._integrations.keys())}")
