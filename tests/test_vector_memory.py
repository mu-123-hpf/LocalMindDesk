"""向量记忆引擎单元测试"""
import os
import json
import tempfile
from app.vector_memory import HybridVectorMemory, TFIDFEngine


class TestTFIDFEngine:
    """TF-IDF 引擎基础测试"""

    def setup_method(self):
        self.engine = TFIDFEngine()

    def test_tokenize_english(self):
        tokens = self.engine.tokenize("Hello World test")
        assert "hello" in tokens
        assert "world" in tokens
        assert "test" in tokens

    def test_tokenize_chinese(self):
        tokens = self.engine.tokenize("你好世界")
        assert "你" in tokens
        assert "好" in tokens
        # bigram
        assert "你好" in tokens
        assert "好世" in tokens

    def test_tokenize_mixed(self):
        tokens = self.engine.tokenize("Hello 你好")
        assert "hello" in tokens
        assert "你" in tokens

    def test_cosine_sim_identical(self):
        """相同向量相似度应为 1.0"""
        vec = {"a": 1.0, "b": 2.0}
        assert abs(self.engine.cosine_sim(vec, vec) - 1.0) < 0.001

    def test_cosine_sim_orthogonal(self):
        """正交向量相似度应为 0"""
        a = {"x": 1.0}
        b = {"y": 1.0}
        assert self.engine.cosine_sim(a, b) == 0.0


class TestHybridVectorMemory:
    """混合向量记忆集成测试"""

    def setup_method(self):
        """每个测试用临时存储"""
        import app.vector_memory as vm
        vm.VECTOR_STORE_PATH = os.path.join(tempfile.mkdtemp(), "test_vec.json")
        vm.EMBEDDING_CACHE_PATH = os.path.join(tempfile.mkdtemp(), "test_embed.npy")
        vm._vector_store = None  # 重置全局实例
        self.store = HybridVectorMemory()

    def test_add_and_count(self):
        self.store.add("Hello world test document")
        assert self.store.count() == 1
        self.store.add("Another document")
        assert self.store.count() == 2

    def test_search_relevance(self):
        self.store.add("Python 编程语言教程")
        self.store.add("Java 开发框架")
        self.store.add("烹饪美食食谱")
        results = self.store.search("Python 编程", top_k=2)
        assert len(results) >= 1
        # 最相关的应该是 Python 相关
        assert "Python" in results[0]["text"]

    def test_search_empty(self):
        results = self.store.search("anything")
        assert results == []

    def test_batch_add(self):
        items = [
            {"text": "文档一"},
            {"text": "文档二"},
            {"text": "文档三"},
        ]
        self.store.add_batch(items)
        assert self.store.count() == 3

    def test_method_field(self):
        """搜索结果应包含 method 字段"""
        self.store.add("测试文档内容")
        results = self.store.search("测试")
        if results:
            assert "method" in results[0]
            assert results[0]["method"] in ("tfidf", "embedding")
