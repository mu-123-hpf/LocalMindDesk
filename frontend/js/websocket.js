// ============================================================
//  LocalMindDesk — WebSocket 实时通信模块
//  替代部分轮询，实现推送式更新
// ============================================================

let _ws = null;
let _wsReconnectTimer = null;
const WS_HANDLERS = {};  // event -> [handler, handler, ...]

/**
 * 注册 WebSocket 事件处理器
 * @param {string} event - 事件名
 * @param {function} handler - 处理函数(data)
 */
function onWsEvent(event, handler) {
  if (!WS_HANDLERS[event]) WS_HANDLERS[event] = [];
  WS_HANDLERS[event].push(handler);
}

/**
 * 初始化 WebSocket 连接
 */
function initWebSocket() {
  if (_ws && (_ws.readyState === WebSocket.OPEN || _ws.readyState === WebSocket.CONNECTING)) {
    return;  // 已连接
  }

  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${protocol}//${location.host}/ws`;

  try {
    _ws = new WebSocket(url);

    _ws.onopen = () => {
      console.log('[WS] 已连接');
      // 心跳：每 30s ping 一次
      if (_wsReconnectTimer) clearInterval(_wsReconnectTimer);
      _wsReconnectTimer = setInterval(() => {
        if (_ws && _ws.readyState === WebSocket.OPEN) {
          _ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, 30000);
    };

    _ws.onmessage = (e) => {
      try {
        const { event, data } = JSON.parse(e.data);
        if (event === 'pong') return;  // 心跳回复，忽略
        // 分发到注册的处理器
        const handlers = WS_HANDLERS[event] || [];
        handlers.forEach(h => { try { h(data); } catch (err) { console.warn('[WS] handler error:', err); } });
      } catch { /* ignore */ }
    };

    _ws.onclose = () => {
      console.log('[WS] 断开，5s 后重连...');
      _ws = null;
      setTimeout(initWebSocket, 5000);
    };

    _ws.onerror = (err) => {
      console.warn('[WS] 连接错误');
      _ws.close();
    };

  } catch (err) {
    console.warn('[WS] 初始化失败:', err.message);
    setTimeout(initWebSocket, 10000);
  }
}

/**
 * 发送消息到服务端
 */
function wsSend(type, data) {
  if (_ws && _ws.readyState === WebSocket.OPEN) {
    _ws.send(JSON.stringify({ type, ...data }));
  }
}

// 页面加载时自动连接
if (typeof window !== 'undefined') {
  window.addEventListener('DOMContentLoaded', () => {
    setTimeout(initWebSocket, 1000);  // 延迟 1s，等其他模块初始化
  });
}

// 暴露到全局
window.initWebSocket = initWebSocket;
window.onWsEvent = onWsEvent;
window.wsSend = wsSend;
