"""FastAPI 端点冒烟测试"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """创建测试客户端"""
    from app.main import app
    return TestClient(app)


class TestHealthEndpoints:
    """健康检查端点"""

    def test_health(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert "status" in r.json()

    def test_boot(self, client):
        r = client.get("/api/boot")
        assert r.status_code == 200


class TestSessionEndpoints:
    """会话 CRUD"""

    def test_list_sessions(self, client):
        r = client.get("/api/sessions")
        assert r.status_code == 200
        assert "sessions" in r.json()

    def test_create_and_delete_session(self, client):
        # 创建
        r = client.post("/api/sessions")
        assert r.status_code == 200
        sid = r.json()["session_id"]
        assert sid

        # 删除
        r = client.delete(f"/api/sessions/{sid}")
        assert r.status_code == 200


class TestVectorEndpoints:
    """向量记忆 API"""

    def test_vector_status(self, client):
        r = client.get("/api/vector/status")
        assert r.status_code == 200
        data = r.json()
        assert "total_documents" in data
        assert "use_embedding" in data


class TestMetricsEndpoint:
    """指标 API"""

    def test_metrics(self, client):
        r = client.get("/api/metrics")
        assert r.status_code == 200
        data = r.json()
        assert "uptime_seconds" in data
        assert "llm" in data


class TestConfigReload:
    """配置热重载"""

    def test_config_reload(self, client):
        r = client.post("/api/config/reload")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
