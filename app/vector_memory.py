"""
LocalMindDesk — 向量记忆 (L3 冷存储) v2
混合策略：优先使用 LM Studio Embedding，降级到 TF-IDF
"""
import os
import json
import re
import math
import numpy as np
from datetime import datetime
from collections import Counter
from typing import Optional

VECTOR_STORE_PATH = "data/vector_memory.json"
EMBEDDING_CACHE_PATH = "data/vector_embeddings.npy"

# ============================================================
#  Embedding 提供者（LM Studio / OpenAI 兼容）
# ============================================================
class EmbeddingProvider:
    """通过 OpenAI 兼容 API 获取文本嵌入向量"""

    def __init__(self):
        self._client = None
        self._model = None
        self._available = None  # None = 未检测

    def _init_client(self):
        if self._client is not None:
            return
        try:
            from app.config import get_active_endpoint
            endpoint = get_active_endpoint()
            if endpoint is None:
                self._available = False
                return
            from openai import OpenAI
            self._client = OpenAI(
                base_url=endpoint.base_url,
                api_key=endpoint.api_key or "not-needed",
                timeout=30.0,
            )
            # 自动检测 embedding 模型
            try:
                models = self._client.models.list()
                for m in models.data:
                    if "embed" in m.id.lower():
                        self._model = m.id
                        break
            except Exception:
                pass

            self._available = self._model is not None
            if self._available:
                print(f"[Vector L3] Embedding 模型: {self._model}")
            else:
                print("[Vector L3] 未发现 Embedding 模型，使用 TF-IDF 降级")
        except Exception as e:
            print(f"[Vector L3] Embedding 初始化失败: {e}")
            self._available = False

    @property
    def available(self) -> bool:
        if self._available is None:
            self._init_client()
        return self._available

    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量嵌入文本，返回向量列表"""
        if not self.available:
            return []
        try:
            # 分批处理（避免超 token 限制）
            batch_size = 32
            all_vectors = []
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                # 截断过长文本
                batch = [t[:512] for t in batch]
                response = self._client.embeddings.create(
                    model=self._model,
                    input=batch,
                )
                for item in response.data:
                    all_vectors.append(item.embedding)
            return all_vectors
        except Exception as e:
            print(f"[Vector L3] Embedding 调用失败: {e}")
            return []

    def embed_single(self, text: str) -> list[float] | None:
        """嵌入单条文本"""
        results = self.embed([text])
        return results[0] if results else None


# ============================================================
#  TF-IDF 引擎（降级方案，纯 Python）
# ============================================================
class TFIDFEngine:
    """零依赖 TF-IDF 向量搜索"""

    def __init__(self):
        self.idf: dict[str, float] = {}

    def tokenize(self, text: str) -> list[str]:
        """中英文分词（极简）"""
        tokens = []
        tokens.extend(re.findall(r'[a-zA-Z]{2,}', text.lower()))
        cn = re.findall(r'[\u4e00-\u9fff]', text)
        tokens.extend(cn)
        for i in range(len(cn) - 1):
            tokens.append(cn[i] + cn[i + 1])
        return tokens

    def compute_tf(self, tokens: list[str]) -> dict[str, float]:
        counter = Counter(tokens)
        total = len(tokens) or 1
        return {t: c / total for t, c in counter.items()}

    def rebuild_idf(self, all_token_lists: list[list[str]]):
        n = len(all_token_lists) or 1
        df = Counter()
        for tokens in all_token_lists:
            for t in set(tokens):
                df[t] += 1
        self.idf = {t: math.log(n / (1 + c)) for t, c in df.items()}

    def tfidf_vec(self, tokens: list[str]) -> dict[str, float]:
        tf = self.compute_tf(tokens)
        return {t: tf[t] * self.idf.get(t, 0) for t in tf}

    def cosine_sim(self, a: dict, b: dict) -> float:
        common = set(a) & set(b)
        if not common:
            return 0.0
        dot = sum(a[t] * b[t] for t in common)
        mag_a = math.sqrt(sum(v ** 2 for v in a.values()))
        mag_b = math.sqrt(sum(v ** 2 for v in b.values()))
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)


# ============================================================
#  混合向量记忆引擎 v2
# ============================================================
class HybridVectorMemory:
    """
    混合向量搜索：
    - 优先使用 LM Studio Embedding (语义级精度)
    - 降级到 TF-IDF (零依赖，仍可工作)
    """

    def __init__(self):
        self.documents: list[dict] = []
        self._embeddings: list[list[float]] = []  # 嵌入向量缓存
        self._tfidf = TFIDFEngine()
        self._embed_provider = EmbeddingProvider()
        self._loaded = False
        self._load()

    @property
    def use_embedding(self) -> bool:
        return self._embed_provider.available

    # ── 公开 API ──

    def add(self, text: str, metadata: dict = None):
        """添加文档"""
        tokens = self._tfidf.tokenize(text)
        doc = {
            "text": text[:500],
            "meta": metadata or {},
            "timestamp": datetime.now().isoformat(),
            "_tokens": tokens,
        }
        self.documents.append(doc)

        # 尝试获取嵌入向量
        if self.use_embedding:
            vec = self._embed_provider.embed_single(text[:512])
            self._embeddings.append(vec if vec else [])
        else:
            self._embeddings.append([])

        self._tfidf.rebuild_idf([d.get("_tokens", []) for d in self.documents])
        self._save()

    def add_batch(self, items: list[dict]):
        """批量添加 [{"text": "...", "meta": {...}}]"""
        texts = []
        for item in items:
            tokens = self._tfidf.tokenize(item["text"])
            doc = {
                "text": item["text"][:500],
                "meta": item.get("meta", {}),
                "timestamp": datetime.now().isoformat(),
                "_tokens": tokens,
            }
            self.documents.append(doc)
            texts.append(item["text"][:512])

        # 批量嵌入
        if self.use_embedding:
            vecs = self._embed_provider.embed(texts)
            if vecs and len(vecs) == len(texts):
                self._embeddings.extend(vecs)
            else:
                self._embeddings.extend([[] for _ in texts])
        else:
            self._embeddings.extend([[] for _ in texts])

        self._tfidf.rebuild_idf([d.get("_tokens", []) for d in self.documents])
        self._save()

    def search(self, query: str, top_k: int = 3, min_score: float = 0.05) -> list[dict]:
        """混合搜索：embedding 优先，TF-IDF 降级"""
        if not self.documents:
            return []

        # 尝试 Embedding 搜索
        if self.use_embedding and any(len(e) > 0 for e in self._embeddings):
            results = self._search_embedding(query, top_k, min_score)
            if results:
                return results

        # 降级到 TF-IDF
        return self._search_tfidf(query, top_k, min_score)

    def _search_embedding(self, query: str, top_k: int, min_score: float) -> list[dict]:
        """使用嵌入向量搜索"""
        q_vec = self._embed_provider.embed_single(query[:512])
        if not q_vec:
            return []

        q_np = np.array(q_vec)
        q_norm = np.linalg.norm(q_np)
        if q_norm == 0:
            return []

        scored = []
        for i, doc in enumerate(self.documents):
            if i >= len(self._embeddings) or not self._embeddings[i]:
                continue
            d_np = np.array(self._embeddings[i])
            d_norm = np.linalg.norm(d_np)
            if d_norm == 0:
                continue
            score = float(np.dot(q_np, d_np) / (q_norm * d_norm))
            if score > min_score:
                scored.append({
                    "text": doc["text"],
                    "score": round(score, 4),
                    "meta": doc.get("meta", {}),
                    "method": "embedding",
                })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def _search_tfidf(self, query: str, top_k: int, min_score: float) -> list[dict]:
        """使用 TF-IDF 搜索（降级）"""
        q_tokens = self._tfidf.tokenize(query)
        q_vec = self._tfidf.tfidf_vec(q_tokens)

        scored = []
        for doc in self.documents:
            d_vec = self._tfidf.tfidf_vec(doc.get("_tokens", []))
            score = self._tfidf.cosine_sim(q_vec, d_vec)
            if score > min_score:
                scored.append({
                    "text": doc["text"],
                    "score": round(score, 4),
                    "meta": doc.get("meta", {}),
                    "method": "tfidf",
                })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def count(self) -> int:
        return len(self.documents)

    # ── 持久化 ──

    def _save(self):
        os.makedirs("data", exist_ok=True)
        data = []
        for doc in self.documents:
            data.append({
                "text": doc["text"],
                "meta": doc.get("meta", {}),
                "timestamp": doc.get("timestamp", ""),
            })
        with open(VECTOR_STORE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)

        # 保存嵌入缓存
        if any(len(e) > 0 for e in self._embeddings):
            try:
                # 对齐长度
                dim = len(self._embeddings[0]) if self._embeddings and self._embeddings[0] else 0
                if dim > 0:
                    padded = []
                    for e in self._embeddings:
                        padded.append(e if len(e) == dim else [0.0] * dim)
                    np.save(EMBEDDING_CACHE_PATH, np.array(padded, dtype=np.float32))
            except Exception as e:
                print(f"[Vector L3] 嵌入缓存保存失败: {e}")

    def _load(self):
        if self._loaded:
            return
        self._loaded = True
        if not os.path.exists(VECTOR_STORE_PATH):
            return
        try:
            with open(VECTOR_STORE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                tokens = self._tfidf.tokenize(item["text"])
                self.documents.append({
                    "text": item["text"],
                    "meta": item.get("meta", {}),
                    "timestamp": item.get("timestamp", ""),
                    "_tokens": tokens,
                })
            self._tfidf.rebuild_idf([d["_tokens"] for d in self.documents])

            # 加载嵌入缓存
            if os.path.exists(EMBEDDING_CACHE_PATH):
                try:
                    cached = np.load(EMBEDDING_CACHE_PATH)
                    self._embeddings = [row.tolist() for row in cached]
                    # 对齐（缓存可能比文档少）
                    while len(self._embeddings) < len(self.documents):
                        self._embeddings.append([])
                    print(f"[Vector L3] 加载 {len(self.documents)} 条记忆 + {sum(1 for e in self._embeddings if e)} 条嵌入缓存")
                except Exception:
                    self._embeddings = [[] for _ in self.documents]
                    print(f"[Vector L3] 加载 {len(self.documents)} 条记忆（嵌入缓存损坏，将使用 TF-IDF）")
            else:
                self._embeddings = [[] for _ in self.documents]
                print(f"[Vector L3] 加载 {len(self.documents)} 条向量记忆")

        except Exception as e:
            print(f"[Vector L3] 加载失败: {e}")

    def rebuild_embeddings(self):
        """重建所有嵌入向量（手动触发）"""
        if not self.use_embedding:
            print("[Vector L3] Embedding 不可用，跳过重建")
            return 0
        texts = [d["text"] for d in self.documents]
        if not texts:
            return 0
        print(f"[Vector L3] 正在重建 {len(texts)} 条嵌入...")
        vecs = self._embed_provider.embed(texts)
        if vecs and len(vecs) == len(texts):
            self._embeddings = vecs
            self._save()
            print(f"[Vector L3] 重建完成: {len(vecs)} 条嵌入")
            return len(vecs)
        return 0


# ============================================================
#  全局实例（向后兼容旧接口名）
# ============================================================
_vector_store: HybridVectorMemory = None
# 向后兼容 — 旧代码使用 LocalVectorMemory
LocalVectorMemory = HybridVectorMemory


def get_vector_store() -> HybridVectorMemory:
    global _vector_store
    if _vector_store is None:
        _vector_store = HybridVectorMemory()
    return _vector_store


# ============================================================
#  便捷函数
# ============================================================
def archive_to_vector(messages: list[dict]):
    """
    将冷对话归档到向量库
    合并相邻 user+assistant 为一条记忆
    """
    store = get_vector_store()
    pairs = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        if msg["role"] == "user":
            text = f"Q: {msg['content'][:200]}"
            if i + 1 < len(messages) and messages[i + 1]["role"] == "assistant":
                text += f"\nA: {messages[i + 1]['content'][:200]}"
                i += 1
            pairs.append({
                "text": text,
                "meta": {"msg_id": msg.get("id", 0), "role": "qa_pair"},
            })
        else:
            pairs.append({
                "text": msg["content"][:300],
                "meta": {"msg_id": msg.get("id", 0), "role": msg["role"]},
            })
        i += 1

    if pairs:
        store.add_batch(pairs)
        print(f"[Vector L3] 归档 {len(pairs)} 条记忆碎片")


def recall_memories(query: str, top_k: int = 3) -> list[dict]:
    """语义召回：搜索向量库中最相关的记忆"""
    store = get_vector_store()
    results = store.search(query, top_k=top_k)
    if results:
        method = results[0].get("method", "unknown")
        print(f"[Vector L3] 召回 {len(results)} 条 (最高分: {results[0]['score']}, 方法: {method})")
    return results
