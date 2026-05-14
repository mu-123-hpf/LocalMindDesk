// ============================================================
//  LocalMindDesk — 微信同步模块
//  微信消息实时同步 + 微信桥接状态
// ============================================================

// ============================================================
//  微信消息实时同步
// ============================================================
let _lastWeChatMsgCount = 0;
let _weChatSyncTimer = null;

function startWeChatSync() {
  // 每 3 秒轮询微信消息
  _weChatSyncTimer = setInterval(pollWeChatMessages, 10000);
}

async function pollWeChatMessages() {
  try {
    const r = await fetch(API + '/api/wechat/messages');
    if (!r.ok) return;
    const data = await r.json();
    const messages = data.messages || [];

    // 只处理新增的消息
    if (messages.length > _lastWeChatMsgCount) {
      const newMsgs = messages.slice(_lastWeChatMsgCount);
      for (const msg of newMsgs) {
        appendWeChatMsg(msg);
      }
      _lastWeChatMsgCount = messages.length;
    }
  } catch (e) {
    // 后端未启动或网络错误，静默忽略
  }
}

function appendWeChatMsg(msg) {
  // msg: {time, from/to, text, direction: "in"/"out"}
  const isIn = msg.direction === 'in';
  const role = isIn ? 'user' : 'assistant';
  const icon = isIn ? '📩' : '📤';
  const sender = isIn ? (msg.from || '微信用户') : 'LocalMindDesk';
  const text = msg.text || '';
  if (!text) return;

  // 隐藏欢迎页
  $welcome.style.display = 'none';

  const div = document.createElement('div');
  div.className = `msg ${role} wechat-msg`;

  const avatar = isIn ? '💬' : '🧠';
  div.innerHTML = `
    <div class="msg-avatar">${avatar}</div>
    <div class="msg-body">
      <div class="msg-role">${icon} ${sender} <span class="wechat-tag">微信</span></div>
      <div class="msg-content">${esc(text)}</div>
    </div>`;

  $msg.appendChild(div);
  $wrap.scrollTop = $wrap.scrollHeight;
}


// ============================================================
//  微信桥接状态
// ============================================================
function openWeChatLogin() {
  const url = (API || '') + '/wechat-login';
  // 尝试弹窗，失败则直接跳转
  const win = window.open(url, '_blank');
  if (!win || win.closed || typeof win.closed === 'undefined') {
    // 弹窗被拦截，改为当前 tab 跳转
    window.location.href = url;
  }
}

async function checkWeChatStatus() {
  try {
    const r = await fetch(API + '/api/wechat/status');
    const d = await r.json();
    updateWeChatUI(d);
  } catch (e) {
    updateWeChatUI({ online: false, has_credentials: false });
  }
}

function updateWeChatUI(status) {
  // 侧边栏小圆点
  const dot = document.getElementById('wechatDot');
  if (dot) {
    dot.className = 'wechat-dot ' + (status.online ? 'online' : 'offline');
  }

  // 侧边栏按钮 title
  const btn = document.getElementById('wechatBtn');
  if (btn) {
    btn.title = status.online
      ? `微信在线 | ${status.account_id || ''} | 收${status.stats?.received || 0} 发${status.stats?.replied || 0}`
      : (status.has_credentials ? '微信离线（点击重连）' : '微信未登录（点击扫码）');
  }

  // 欢迎页卡片
  const val = document.getElementById('welcomeWechatVal');
  const sub = document.getElementById('welcomeWechatSub');
  const icon = document.getElementById('welcomeWechatIcon');
  if (val) {
    if (status.online) {
      val.textContent = '在线';
      val.style.color = '#07c160';
      if (sub) sub.textContent = `收${status.stats?.received || 0} | 发${status.stats?.replied || 0}`;
      if (icon) icon.classList.add('online-icon');
    } else if (status.has_credentials) {
      val.textContent = '离线';
      val.style.color = '';
      if (sub) sub.textContent = '点击重新连接';
      if (icon) icon.classList.remove('online-icon');
    } else {
      val.textContent = '未连接';
      val.style.color = '';
      if (sub) sub.textContent = '点击扫码登录';
      if (icon) icon.classList.remove('online-icon');
    }
  }

  // 最近消息（如果 status 包含 recent_messages）
  if (status.recent_messages && status.recent_messages.length > 0) {
    const last = status.recent_messages[status.recent_messages.length - 1];
    const preview = last.direction === 'in'
      ? `📩 ${last.text || ''}`.slice(0, 30)
      : `📤 ${last.text || ''}`.slice(0, 30);
    if (sub && status.online) {
      sub.textContent = preview;
    }
  }
}

// 初始化时检查一次 + 每 15 秒轮询
checkWeChatStatus();
setInterval(checkWeChatStatus, 15000);

