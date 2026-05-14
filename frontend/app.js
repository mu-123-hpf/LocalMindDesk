// ============================================================
//  LocalMindDesk v2 — 前端逻辑
//  LobeChat 风格聊天 + 多模型管理 + 三层记忆集成
// ============================================================

const isElectron = !!(window.electronAPI && window.electronAPI.isElectron);
const API = isElectron ? 'http://localhost:8000' : '';
let isGenerating = false;
let currentAbortController = null;  // 用于中断对话/操作
let chatHistory = [];
let configCache = null;
let currentSessionId = null;
let bootData = null;  // 冷启动数据缓存
let currentMode = 'collaborate';  // 当前对话模式

// 模式配置
const MODE_CONFIG = {
  plan:        { icon: '📋', label: 'Plan',        desc: '先制定计划，确认后执行' },
  execute:     { icon: '🎯', label: 'Execute',     desc: '直接执行，快速完成' },
  collaborate: { icon: '🤝', label: 'Collaborate', desc: '协作讨论方案后行动' },
  review:      { icon: '🔍', label: 'Review',      desc: '深度审查与改进建议' },
};

// ---- DOM ----
const $msg = document.getElementById('messages');
const $wrap = document.getElementById('messagesWrap');
const $input = document.getElementById('chatInput');
const $send = document.getElementById('sendBtn');
const $welcome = document.getElementById('welcome');
const $typing = document.getElementById('typingIndicator');
const $modelSelect = document.getElementById('modelSelect');
const $dot = document.getElementById('statusDot');
const $modelLabel = document.getElementById('modelLabel');

// ---- Markdown ----
if (typeof marked !== 'undefined') {
  marked.setOptions({
    highlight: (code, lang) => {
      if (typeof hljs !== 'undefined' && lang && hljs.getLanguage(lang))
        return hljs.highlight(code, { language: lang }).value;
      return code;
    },
    breaks: true,
  });
}

// ============================================================
//  初始化（三层记忆冷启动）
// ============================================================
async function init() {
  // Electron 标题栏控制
  initTitlebar();

  // L1: 从 localStorage 瞬时恢复 UI 状态（< 1ms）
  restoreLocalState();

  // 先绑定事件（保证按钮可交互，不依赖后端）
  bindEvents();

  // L2+L3: 从后端恢复（串行避免请求洪水）
  try { await bootFromServer(); } catch(e) { console.warn('[init] boot:', e.message); }
  try { await loadSessions(); } catch(e) { console.warn('[init] sessions:', e.message); }

  // 定期保存 UI 状态到 localStorage
  setInterval(saveLocalState, 10000);

  // 延迟启动非关键轮询（避免启动时请求洪水）
  setTimeout(() => {
    startWeChatSync();
    try { checkHealth(); } catch {}
    try { loadConfig(); } catch {}
  }, 3000);

  // 🐾 初始化桌宠
  initPetWidget();

  // 后端连接重试（loadFile 模式下后端可能还未就绪）
  _startBackendRetry();
}

// 后端连接自动重试（独立函数）
function _startBackendRetry() {
  let retries = 0;
  const retryInterval = setInterval(async () => {
    retries++;
    try {
      const r = await fetch(API + '/api/health');
      const d = await r.json();
      if (d.status === 'ok') {
        clearInterval(retryInterval);
        console.log(`[Boot] 后端连接成功 (尝试${retries}次)`);
        try { await loadConfig(); } catch {}
        try { await checkHealth(); } catch {}
        try { await loadSessions(); } catch {}
      }
    } catch {
      if (retries >= 30) {
        clearInterval(retryInterval);
        console.warn('[Boot] 后端连接超时（60s），请手动刷新页面');
      }
    }
  }, 2000);
}

// ============================================================
//  Electron 标题栏
// ============================================================
function initTitlebar() {
  const titlebar = document.getElementById('titlebar');
  if (!titlebar) return;

  // 非 Electron 环境隐藏标题栏
  if (!isElectron) {
    titlebar.style.display = 'none';
    document.getElementById('app').style.height = 'calc(100vh - 28px)';
    return;
  }

  document.getElementById('tbMinimize')?.addEventListener('click', () => {
    window.electronAPI.minimize();
  });

  document.getElementById('tbMaximize')?.addEventListener('click', () => {
    window.electronAPI.maximize();
  });

  document.getElementById('tbClose')?.addEventListener('click', () => {
    window.electronAPI.close();
  });

  // 监听最大化状态 → 切换图标
  window.electronAPI.onWindowState?.((state) => {
    const btn = document.getElementById('tbMaximize');
    if (!btn) return;
    if (state === 'maximized') {
      btn.innerHTML = '<svg width="12" height="12" viewBox="0 0 12 12"><rect x="3" y="0.5" width="8" height="8" rx="1" fill="none" stroke="currentColor" stroke-width="1.2"/><rect x="0.5" y="3" width="8" height="8" rx="1" fill="none" stroke="currentColor" stroke-width="1.2"/></svg>';
      btn.title = '还原';
    } else {
      btn.innerHTML = '<svg width="12" height="12" viewBox="0 0 12 12"><rect x="1.5" y="1.5" width="9" height="9" rx="1" fill="none" stroke="currentColor" stroke-width="1.2"/></svg>';
      btn.title = '最大化';
    }
  });
}

async function loadConfig() {
  try {
    const r = await fetch(API + '/api/config');
    if (!r.ok) return;
    configCache = await r.json();

    // 填充模型选择器
    $modelSelect.innerHTML = '';
    if (configCache.models) {
      configCache.models.forEach(m => {
        const opt = document.createElement('option');
        opt.value = m.name;
        opt.textContent = `${m.model || m.name} (${m.provider})`;
        if (m.name === configCache.active_model) opt.selected = true;
        $modelSelect.appendChild(opt);
      });
    }

    // 填充设置面板
    document.getElementById('tempRange').value = configCache.temperature || 0.7;
    document.getElementById('tempVal').textContent = configCache.temperature || 0.7;
    document.getElementById('sysPrompt').value = configCache.system_prompt || '';

    renderEndpoints();

    // 更新人格显示
    if (configCache.persona) {
      const p = configCache.persona;
      document.querySelector('.brand-icon').textContent = p.icon || '🧠';
      document.querySelector('.brand-name').textContent = p.name || 'LocalMindDesk';
    }

    // 应用 UI 偏好
    if (configCache.ui_preferences) {
      applyUIPreferences(configCache.ui_preferences);
    }
  } catch (e) { /* 后端未启动 */ }
}

async function checkHealth() {
  function setHealthUI(online, modelText, subText) {
    $dot.classList.toggle('online', online);
    $modelLabel.textContent = modelText;
    const $wm = document.getElementById('welcomeModelName');
    const $ws = document.getElementById('welcomeModelSub');
    const $wi = document.getElementById('welcomeModelIcon');
    if ($wm) $wm.textContent = modelText;
    if ($ws) $ws.textContent = subText || '';
    if ($wi) $wi.textContent = online ? '🟢' : '🔴';
  }

  try {
    const r = await fetch(API + '/api/health');
    const d = await r.json();
    if (d.status === 'ok') {
      const label = d.model || d.provider;
      const sub = d.provider === 'lmstudio' ? 'LM Studio 本地推理' : d.provider;
      setHealthUI(true, label, sub);
    } else {
      setHealthUI(false, '未连接');
    }
  } catch {
    setHealthUI(false, '未连接');
  }
}

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
//  事件绑定
// ============================================================
function bindEvents() {
  // 发送
  $input.addEventListener('input', () => {
    $input.style.height = 'auto';
    $input.style.height = Math.min($input.scrollHeight, 160) + 'px';
    $send.disabled = !$input.value.trim() || isGenerating;
  });

  $input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });

  $send.addEventListener('click', () => {
    if (isGenerating) {
      stopGenerating();
    } else {
      sendMessage();
    }
  });

  // 快捷按钮
  document.querySelectorAll('.quick-card').forEach(b => {
    b.addEventListener('click', () => { $input.value = b.dataset.p; sendMessage(); });
  });

  // 清空
  document.getElementById('clearBtn').addEventListener('click', () => {
    chatHistory = [];
    $msg.innerHTML = '';
    $msg.appendChild($welcome);
    $welcome.style.display = 'flex';
  });

  // 新对话
  document.getElementById('newChatBtn').addEventListener('click', newChat);

  // 模型切换
  $modelSelect.addEventListener('change', async () => {
    const name = $modelSelect.value;
    try {
      await fetch(API + '/api/models/switch/' + encodeURIComponent(name), { method: 'POST' });
      await loadConfig();
      await checkHealth();
    } catch (e) { console.error(e); }
  });

  // 侧边栏
  document.getElementById('toggleSidebar').addEventListener('click', () => {
    document.getElementById('sidebar').classList.toggle('open');
  });

  // 设置面板
  document.getElementById('settingsBtn').addEventListener('click', openSettings);
  document.getElementById('closePanel').addEventListener('click', closeSettings);
  document.getElementById('panelBackdrop').addEventListener('click', closeSettings);

  // 添加端点
  document.getElementById('addEndpointBtn').addEventListener('click', () => {
    document.getElementById('addEndpointForm').style.display = 'block';
    // 自动填充 URL
    const prov = document.getElementById('epProvider');
    prov.addEventListener('change', autoFillUrl);
    autoFillUrl();
  });

  document.getElementById('cancelEndpoint').addEventListener('click', () => {
    document.getElementById('addEndpointForm').style.display = 'none';
  });

  document.getElementById('saveEndpoint').addEventListener('click', saveNewEndpoint);

  // 全局设置
  document.getElementById('tempRange').addEventListener('input', e => {
    document.getElementById('tempVal').textContent = e.target.value;
  });
  document.getElementById('saveGlobal').addEventListener('click', saveGlobalSettings);
  document.getElementById('testConn').addEventListener('click', testConnection);

  // 模式菜单
  initModeMenu();
}

// ============================================================
//  模式选择菜单
// ============================================================
function initModeMenu() {
  const $menuBtn = document.getElementById('modeMenuBtn');
  const $menuPopup = document.getElementById('modeMenuPopup');
  if (!$menuBtn || !$menuPopup) return;

  // 切换菜单显示
  $menuBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    const isOpen = $menuPopup.classList.contains('show');
    if (isOpen) {
      closeModeMenu();
    } else {
      $menuPopup.classList.add('show');
      $menuBtn.classList.add('menu-open');
    }
  });

  // 菜单项点击
  $menuPopup.querySelectorAll('.mode-menu-item').forEach(item => {
    item.addEventListener('click', (e) => {
      e.stopPropagation();
      const mode = item.dataset.mode;
      switchMode(mode);
      closeModeMenu();
      // 聚焦输入框
      $input.focus();
    });
  });

  // 点击外部关闭菜单
  document.addEventListener('click', (e) => {
    if (!$menuPopup.contains(e.target) && e.target !== $menuBtn) {
      closeModeMenu();
    }
  });

  // ESC 关闭菜单
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeModeMenu();
    }
  });
}

function closeModeMenu() {
  const $menuPopup = document.getElementById('modeMenuPopup');
  const $menuBtn = document.getElementById('modeMenuBtn');
  if ($menuPopup) $menuPopup.classList.remove('show');
  if ($menuBtn) $menuBtn.classList.remove('menu-open');
}

function switchMode(mode) {
  if (!MODE_CONFIG[mode]) return;
  currentMode = mode;

  // 更新菜单项高亮
  document.querySelectorAll('.mode-menu-item').forEach(item => {
    item.classList.toggle('active', item.dataset.mode === mode);
  });

  // 更新底部指示器
  const $indicator = document.getElementById('currentModeIndicator');
  if ($indicator) {
    const cfg = MODE_CONFIG[mode];
    $indicator.textContent = `${cfg.icon} ${cfg.label}`;
  }

  // 更新 placeholder 提示
  const placeholders = {
    plan:        '描述你的需求，AI 会先制定计划...',
    execute:     '输入明确指令，AI 直接执行...',
    collaborate: '发送消息给 LocalMindDesk...',
    review:      '粘贴代码或描述要审查的内容...',
  };
  $input.placeholder = placeholders[mode] || placeholders.collaborate;

  console.log(`[Mode] 切换到 ${MODE_CONFIG[mode].label} 模式`);
}


// ---- 启动 ----
init();
restoreWorkspace();

// 延迟加载集成、沙盒和定时任务（不阻塞主界面）
setTimeout(() => {
  loadIntegrations();
  loadSandbox();
  initSandboxEvents();
  loadSchedules();
}, 500);
