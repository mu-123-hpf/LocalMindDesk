// ============================================================
//  LocalMindDesk — 会话管理模块
//  L1 localStorage 恢复 + L2/L3 后端冷启动 + 会话 CRUD
// ============================================================

// ============================================================
//  L1: localStorage 瞬时状态恢复
// ============================================================
function saveLocalState() {
  try {
    const state = {
      currentSessionId,
      timestamp: Date.now(),
    };
    localStorage.setItem('lmd_state', JSON.stringify(state));
  } catch (e) { /* localStorage 不可用 */ }
}

function restoreLocalState() {
  try {
    const raw = localStorage.getItem('lmd_state');
    if (!raw) return;
    const saved = JSON.parse(raw);
    // 24 小时内的状态才恢复
    if (saved.timestamp && Date.now() - saved.timestamp < 86400000) {
      if (saved.currentSessionId) {
        currentSessionId = saved.currentSessionId;
        console.log('[L1] 从 localStorage 恢复会话:', currentSessionId);
      }
    }
  } catch (e) { /* ignore */ }
}

// ============================================================
//  L2+L3: 后端冷启动恢复
// ============================================================
async function bootFromServer() {
  try {
    const r = await fetch(API + '/api/boot');
    if (!r.ok) return;
    bootData = await r.json();
    console.log('[Boot] 冷启动数据:', bootData);

    // 恢复 Agent Profile (L1)
    if (bootData.profile) {
      if (bootData.profile.identity) {
        const id = bootData.profile.identity;
        document.querySelector('.brand-icon').textContent = id.icon || '🧠';
        document.querySelector('.brand-name').textContent = id.name || 'LocalMindDesk';
      }
      if (bootData.profile.ui_preferences) {
        applyUIPreferences(bootData.profile.ui_preferences);
      }
    }

    // 恢复上次会话 (L2)
    if (bootData.lastSession && !currentSessionId) {
      currentSessionId = bootData.lastSession.id;
      console.log('[Boot] 恢复会话:', currentSessionId, bootData.lastSession.title);
    }

    // 如果有上次会话，加载对话内容
    if (currentSessionId && bootData.hotContext && bootData.hotContext.length > 0) {
      $welcome.style.display = 'none';
      chatHistory = [];
      $msg.innerHTML = '';
      bootData.hotContext.forEach(m => {
        appendMsg(m.role, m.content);
        chatHistory.push({ role: m.role, content: m.content });
      });
      console.log(`[Boot] 恢复 ${bootData.hotContext.length} 条热对话`);
    }

    // 更新记忆状态指示器
    const stats = {
      hotCount: bootData.hotContext ? bootData.hotContext.length : 0,
      vectorCount: bootData.vectorMemoryCount || 0,
      sessionCount: bootData.sessions ? bootData.sessions.length : 0,
    };
    updateMemoryStatus(stats);
    updateAllDashboards(stats);

  } catch (e) {
    console.warn('[Boot] 冷启动失败（后端可能未启动）:', e.message);
  }
}

// ============================================================
//  会话管理
// ============================================================
async function loadSessions() {
  try {
    const r = await fetch(API + '/api/sessions');
    const d = await r.json();
    const list = document.getElementById('chatList');
    if (!d.sessions || d.sessions.length === 0) {
      list.innerHTML = '<div class="chat-list-empty">暂无对话历史</div>';
      return;
    }
    list.innerHTML = '';
    d.sessions.forEach(s => {
      const item = document.createElement('div');
      item.className = 'chat-item' + (s.id === currentSessionId ? ' active' : '');
      const title = document.createElement('span');
      title.className = 'chat-item-title';
      title.textContent = s.title;
      title.onclick = () => loadSession(s.id);
      const del = document.createElement('button');
      del.className = 'chat-item-del';
      del.textContent = '\u2715';
      del.title = '\u5220\u9664\u5bf9\u8bdd';
      del.onclick = (e) => { e.stopPropagation(); deleteSession(s.id); };
      item.appendChild(title);
      item.appendChild(del);
      list.appendChild(item);
    });
  } catch (e) { /* ignore */ }
}

async function deleteSession(sid) {
  if (!confirm('\u786e\u5b9a\u5220\u9664\u8fd9\u6761\u5bf9\u8bdd\u8bb0\u5f55\u5417\uff1f')) return;
  try {
    await fetch(API + '/api/sessions/' + sid, { method: 'DELETE' });
    if (currentSessionId === sid) {
      currentSessionId = null;
      chatHistory = [];
      $msg.innerHTML = '';
      $welcome.style.display = '';
    }
    await loadSessions();
    // 刷新会话计数
    const sr2 = await fetch(API + '/api/sessions');
    const sd2 = await sr2.json();
    const sessEl = document.getElementById('memSessVal');
    if (sessEl) sessEl.textContent = sd2.sessions ? sd2.sessions.length : 0;
  } catch (e) { alert('\u5220\u9664\u5931\u8d25: ' + e.message); }
}
async function loadSession(sid) {
  currentSessionId = sid;
  chatHistory = [];
  $msg.innerHTML = '';
  $welcome.style.display = 'none';

  try {
    const r = await fetch(API + `/api/sessions/${sid}/messages`);
    const d = await r.json();
    d.messages.forEach(m => {
      appendMsg(m.role, m.content);
      chatHistory.push({ role: m.role, content: m.content });
    });
  } catch (e) { /* ignore */ }
  await loadSessions();
  saveLocalState();  // 切换会话时保存状态
}

async function newChat() {
  currentSessionId = null;
  chatHistory = [];
  $msg.innerHTML = '';
  $msg.appendChild($welcome);
  $welcome.style.display = 'flex';
  saveLocalState();
}

async function ensureSession(firstMsg) {
  if (!currentSessionId) {
    const r = await fetch(API + '/api/sessions', { method: 'POST' });
    const d = await r.json();
    currentSessionId = d.session_id;
  }
  // 保存用户消息
  fetch(API + `/api/sessions/${currentSessionId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role: 'user', content: firstMsg }),
  });
}

