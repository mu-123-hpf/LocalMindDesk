"""
可观测性路由 — /api/metrics
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["metrics"])


@router.get("/metrics")
async def api_metrics():
    """获取系统指标"""
    from app.metrics import get_metrics
    return get_metrics().get_summary()
