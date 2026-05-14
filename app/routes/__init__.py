"""
LocalMindDesk — 路由模块入口
提供 APIRouter 蓝图注册机制
新增路由建议在对应的 routes/*.py 中注册
"""
from fastapi import APIRouter

# 已提取的路由模块
from app.routes.metrics import router as metrics_router
from app.routes.vector import router as vector_router

# 将来增量拆分的模块（占位）
# from app.routes.sessions import router as sessions_router
# from app.routes.workspace import router as workspace_router
# from app.routes.personas import router as personas_router

# 导出所有路由，供 main.py include
all_routers: list[APIRouter] = [
    metrics_router,
    vector_router,
]
