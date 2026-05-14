"""
向量记忆路由 — /api/vector/*
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/vector", tags=["vector"])


@router.post("/rebuild")
async def api_vector_rebuild():
    """手动触发嵌入向量重建"""
    from app.vector_memory import get_vector_store
    store = get_vector_store()
    count = store.rebuild_embeddings()
    return {"status": "ok", "rebuilt": count, "total": store.count()}


@router.get("/status")
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
