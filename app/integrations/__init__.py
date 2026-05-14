"""
LocalMindDesk — 应用集成系统
"""
from app.integrations.manager import get_manager, IntegrationManager
from app.integrations.base import BaseIntegration

__all__ = ["get_manager", "IntegrationManager", "BaseIntegration"]
