"""Verify iLink-based WeChat bridge modules"""
import sys
sys.path.insert(0, ".")

print("=" * 50)
print("Testing iLink WeChat Bridge")
print("=" * 50)

# 1. Imports
from app.wechat_bridge import (
    get_bridge, WeChatBridge, qr_login,
    _ilink_post, _extract_text, _split_message,
    _generate_qr_b64, Credentials, QRState,
    _save_credentials, _load_credentials, _delete_credentials,
)
print("[OK] wechat_bridge imports")

from app.integrations.wechat import WeChatIntegration, WeChatSendTool
print("[OK] wechat integration imports")

# 2. Bridge instance
bridge = get_bridge()
assert isinstance(bridge, WeChatBridge)
print(f"[OK] bridge instance: {type(bridge).__name__}")

# 3. Status before start
status = bridge.get_status()
print(f"[OK] status: online={status['online']}, has_creds={status['has_credentials']}")

# 4. Message splitting
chunks = _split_message("a" * 8000)
assert len(chunks) == 2
print(f"[OK] split_message: 8000 chars -> {len(chunks)} chunks")

# 5. Text extraction
msg = {
    "item_list": [
        {"type": 1, "text_item": {"text": "hello"}},
        {"type": 1, "text_item": {"text": "world"}},
    ]
}
text = _extract_text(msg)
assert text == "hello\nworld"
print(f"[OK] extract_text: '{text}'")

# 6. QR generation
qr_b64 = _generate_qr_b64("https://test.example.com")
assert qr_b64.startswith("data:image/png;base64,")
print(f"[OK] QR generation: {len(qr_b64)} chars")

# 7. Credential persistence
test_cred = Credentials(
    account_id="test_id_123",
    token="test_token_abc",
    base_url="https://test.weixin.qq.com",
    user_id="test_user@im.wechat",
    saved_at="2026-05-03T01:00:00",
)
_save_credentials(test_cred)
loaded = _load_credentials()
assert loaded is not None
assert loaded.account_id == "test_id_123"
assert loaded.token == "test_token_abc"
print(f"[OK] credential save/load: {loaded.account_id}")
_delete_credentials()
assert _load_credentials() is None
print("[OK] credential delete")

# 8. Integration
wc = WeChatIntegration()
print(f"[OK] integration: id={wc.id}, name={wc.name}")
print(f"     install_commands: {len(wc.install_commands)}")
print(f"     auto_detect: {wc.auto_detect()}")
print(f"     tools: {[t.name for t in wc.get_tools()]}")

# 9. Scheduler still works
from app.scheduler import get_scheduler
s = get_scheduler()
print(f"[OK] scheduler: templates={len(s.get_templates())}")

print()
print("=" * 50)
print("ALL TESTS PASSED!")
print("=" * 50)
print()
print("API Endpoints:")
print("  GET  /api/wechat/qr-login  -> SSE QR code login")
print("  POST /api/wechat/start     -> start bridge")
print("  POST /api/wechat/stop      -> stop bridge")
print("  GET  /api/wechat/status    -> bridge status")
print("  POST /api/wechat/logout    -> logout + clear creds")
