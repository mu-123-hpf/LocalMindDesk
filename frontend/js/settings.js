// ============================================================
//  LocalMindDesk — 设置面板模块
//  端点管理、全局参数、集成、沙盒、技能库、个性化
// ============================================================

// ============================================================
//  设置面板
// ============================================================
function openSettings() {
  document.getElementById('settingsPanel').style.display = 'block';
  loadConfig();
}
function closeSettings() {
  document.getElementById('settingsPanel').style.display = 'none';
  document.getElementById('addEndpointForm').style.display = 'none';
}

function renderEndpoints() {
  const list = document.getElementById('endpointList');
  list.innerHTML = '';
  if (!configCache || !configCache.models) return;

  configCache.models.forEach(m => {
    const card = document.createElement('div');
    card.className = 'ep-card' + (m.name === configCache.active_model ? ' active' : '');
    card.innerHTML = `
      <div class="ep-info">
        <div class="ep-name">${m.model || m.name}</div>
        <div class="ep-detail">${m.provider} · ${m.base_url}</div>
      </div>
      <div class="ep-actions">
        ${m.name === configCache.active_model
          ? '<span class="btn-tiny active-tag">主模型</span>'
          : `<button class="btn-tiny" onclick="switchModel('${m.name}')">切换</button>`}
        <button class="btn-tiny danger" onclick="deleteModel('${m.name}')">✕</button>
      </div>`;
    list.appendChild(card);
  });
}

function autoFillUrl() {
  const p = document.getElementById('epProvider').value;
  const url = document.getElementById('epUrl');
  const defaults = {
    lmstudio: 'http://127.0.0.1:1234/v1',
    ollama: 'http://127.0.0.1:11434/v1',
    deepseek: 'https://api.deepseek.com/v1',
    openai: 'https://api.openai.com/v1',
    custom: '',
  };
  url.value = defaults[p] || '';
}

async function saveNewEndpoint() {
  const data = {
    name: document.getElementById('epName').value.trim(),
    provider: document.getElementById('epProvider').value,
    base_url: document.getElementById('epUrl').value.trim(),
    api_key: document.getElementById('epKey').value.trim(),
    model: document.getElementById('epModel').value.trim(),
  };
  if (!data.name || !data.base_url) return alert('名称和 URL 不能为空');

  try {
    await fetch(API + '/api/models/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    document.getElementById('addEndpointForm').style.display = 'none';
    // 清空表单
    ['epName','epUrl','epKey','epModel'].forEach(id => document.getElementById(id).value = '');
    await loadConfig();
    await checkHealth();
  } catch (e) { alert('添加失败: ' + e.message); }
}

async function switchModel(name) {
  await fetch(API + '/api/models/switch/' + encodeURIComponent(name), { method: 'POST' });
  await loadConfig();
  await checkHealth();
}

async function deleteModel(name) {
  if (!confirm(`确定删除模型 "${name}"？`)) return;
  await fetch(API + '/api/models/' + encodeURIComponent(name), { method: 'DELETE' });
  await loadConfig();
}

async function saveGlobalSettings() {
  const data = {
    temperature: parseFloat(document.getElementById('tempRange').value),
    system_prompt: document.getElementById('sysPrompt').value,
  };
  await fetch(API + '/api/config/update', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  alert('设置已保存');
}

async function testConnection() {
  const el = document.getElementById('connResult');
  el.textContent = '正在测试...';
  el.style.color = 'var(--text-2)';
  try {
    const r = await fetch(API + '/api/health');
    const d = await r.json();
    if (d.status === 'ok') {
      el.textContent = `✅ 连接成功！模型: ${d.model}`;
      el.style.color = 'var(--success)';
      $dot.classList.add('online');
    } else {
      el.textContent = `⚠️ 连接异常: ${d.error}`;
      el.style.color = 'var(--warning)';
    }
  } catch (e) {
    el.textContent = `❌ 无法连接: ${e.message}`;
    el.style.color = 'var(--error)';
  }
}


// ============================================================
//  Settings Tab 切换
// ============================================================
document.querySelectorAll('.stab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.stab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    tab.classList.add('active');
    const target = document.getElementById(tab.dataset.tab);
    if (target) target.classList.add('active');

    // 切到个性化时加载 profile
    if (tab.dataset.tab === 'tabPersona') loadPersonaForm();
    // 切到技能时加载列表
    if (tab.dataset.tab === 'tabSkills') loadSkills();
  });
});

// ============================================================
//  个性化面板
// ============================================================
async function loadPersonaForm() {
  try {
    const r = await fetch(API + '/api/profile');
    const p = await r.json();
    document.getElementById('pIcon').value = p.identity?.icon || '🧠';
    document.getElementById('pName').value = p.identity?.name || '';
    document.getElementById('pRole').value = p.identity?.role || '';
    document.getElementById('pSysPrompt').value = p.identity?.system_prompt || '';
    document.getElementById('pStyle').value = p.behavior?.response_style || 'balanced';
    document.getElementById('pLength').value = p.behavior?.response_length || 'medium';
    document.getElementById('pLang').value = p.behavior?.language || 'zh-CN';
  } catch (e) { console.warn('[Persona] 加载失败:', e); }
}

document.getElementById('savePersona')?.addEventListener('click', async () => {
  const delta = {
    'identity.icon': document.getElementById('pIcon').value,
    'identity.name': document.getElementById('pName').value,
    'identity.role': document.getElementById('pRole').value,
    'identity.system_prompt': document.getElementById('pSysPrompt').value,
    'behavior.response_style': document.getElementById('pStyle').value,
    'behavior.response_length': document.getElementById('pLength').value,
    'behavior.language': document.getElementById('pLang').value,
  };
  try {
    const r = await fetch(API + '/api/profile/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ delta }),
    });
    const d = await r.json();
    if (d.success) {
      // 热更新 UI
      document.querySelector('.brand-icon').textContent = delta['identity.icon'];
      document.querySelector('.brand-name').textContent = delta['identity.name'];
      const $pn = document.getElementById('profileName');
      const $pr = document.getElementById('profileRole');
      if ($pn) $pn.textContent = delta['identity.name'];
      if ($pr) $pr.textContent = delta['identity.role'];
      alert('✅ 个性化已保存');
    }
  } catch (e) { alert('保存失败: ' + e.message); }
});

document.getElementById('resetPersona')?.addEventListener('click', async () => {
  if (!confirm('确定要重置为默认配置？')) return;
  try {
    await fetch(API + '/api/profile/reset', { method: 'POST' });
    loadPersonaForm();
    alert('✅ 已重置');
  } catch (e) { alert('重置失败'); }
});

// ============================================================
//  技能库
// ============================================================
async function loadSkills() {
  try {
    const r = await fetch(API + '/api/skills');
    const d = await r.json();
    renderSkillList('globalSkillList', d.global || [], 'global');
    renderSkillList('localSkillList', d.local || [], 'local');
  } catch (e) { console.warn('[Skills] 加载失败:', e); }
}

function renderSkillList(containerId, skills, scope) {
  const $el = document.getElementById(containerId);
  if (!$el) return;
  if (!skills.length) {
    $el.innerHTML = `<div class="skill-empty">${scope === 'local' ? '未打开项目或无局部技能' : '暂无全局技能'}</div>`;
    return;
  }
  $el.innerHTML = skills.map(s => `
    <div class="skill-card">
      <div class="skill-card-icon">🧩</div>
      <div class="skill-card-body">
        <div class="skill-card-title">
          ${s.title}
          <span class="skill-scope-badge ${scope}">${scope === 'global' ? '全局' : '项目'}</span>
        </div>
        <div class="skill-card-desc">${s.description || ''}</div>
        <div class="skill-card-meta">${s.source ? '📎 ' + s.source : ''}${s.date ? ' · ' + s.date : ''}</div>
      </div>
      <button class="skill-card-del" onclick="deleteSkill('${s.filename}','${scope}')" title="删除">🗑</button>
    </div>
  `).join('');
}

async function deleteSkill(filename, scope) {
  if (!confirm(`确定删除技能 ${filename}？`)) return;
  try {
    await fetch(API + `/api/skills/${filename}?scope=${scope}`, { method: 'DELETE' });
    loadSkills();
  } catch (e) { alert('删除失败'); }
}

// ============================================================
//  GitHub Skill 学习
// ============================================================
document.getElementById('ghLearnBtn')?.addEventListener('click', async () => {
  const url = document.getElementById('ghLearnUrl')?.value?.trim();
  const scope = document.getElementById('ghLearnScope')?.value || 'global';
  const $status = document.getElementById('ghLearnStatus');
  if (!url) { $status.textContent = '请输入 GitHub URL'; $status.className = 'gh-learn-status error'; return; }

  $status.textContent = '⏳ 正在从 GitHub 获取...';
  $status.className = 'gh-learn-status loading';

  try {
    const r = await fetch(API + '/api/skills/learn', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, scope }),
    });
    const d = await r.json();
    if (d.success) {
      $status.textContent = `✅ 已学习: ${d.title || url}`;
      $status.className = 'gh-learn-status success';
      document.getElementById('ghLearnUrl').value = '';
      loadSkills();
    } else {
      $status.textContent = `❌ ${d.error || '学习失败'}`;
      $status.className = 'gh-learn-status error';
    }
  } catch (e) {
    $status.textContent = `❌ 请求失败: ${e.message}`;
    $status.className = 'gh-learn-status error';
  }
});

// ============================================================
//  应用集成管理
// ============================================================
async function loadIntegrations() {
  const list = document.getElementById('integrationList');
  if (!list) return;
  try {
    const res = await fetch(`${API}/api/integrations`);
    const data = await res.json();
    renderIntegrations(data.integrations || []);
  } catch (e) {
    list.innerHTML = '<div class="integration-loading">加载失败</div>';
  }
}

function renderIntegrations(integrations) {
  const list = document.getElementById('integrationList');
  if (!integrations.length) {
    list.innerHTML = '<div class="integration-loading">暂无可用集成</div>';
    return;
  }
  list.innerHTML = integrations.map(ig => `
    <div class="integration-card ${ig.enabled ? 'enabled' : ''}" data-id="${ig.id}">
      <div class="integration-icon">${ig.icon}</div>
      <div class="integration-info">
        <div class="integration-header">
          <span class="integration-name">${ig.name}</span>
          <span class="integration-status ${ig.connected ? 'connected' : 'disconnected'}">
            ${ig.connected ? '● 已连接' : '○ 未连接'}
          </span>
        </div>
        <div class="integration-desc">${ig.description}</div>
        <div class="integration-actions">
          <button class="btn-outline btn-sm" onclick="detectIntegration('${ig.id}')">🔍 自动检测</button>
          <button class="btn-outline btn-sm" onclick="testIntegration('${ig.id}')">🔌 测试连接</button>
          <button class="btn-outline btn-sm" onclick="toggleIntegrationConfig('${ig.id}')">⚙ 配置</button>
        </div>
        <div class="integration-config" id="config-${ig.id}">
          ${ig.config_schema.map(f => `
            <div class="form-group">
              <label>${f.label}</label>
              ${f.type === 'toggle'
                ? `<label class="toggle-switch">
                     <input type="checkbox" data-config-key="${f.key}" ${ig.config[f.key] ? 'checked' : ''}>
                     <span class="toggle-slider"></span>
                   </label>`
                : `<input type="${f.type === 'password' ? 'password' : 'text'}"
                     data-config-key="${f.key}"
                     value="${ig.config[f.key] || f.default || ''}"
                     placeholder="${f.placeholder || ''}">`
              }
            </div>
          `).join('')}
          <button class="btn-primary btn-sm" onclick="saveIntegrationConfig('${ig.id}')">保存配置</button>
          <div id="detect-result-${ig.id}"></div>
        </div>
      </div>
      <div class="integration-toggle">
        <label class="toggle-switch">
          <input type="checkbox" ${ig.enabled ? 'checked' : ''} onchange="toggleIntegration('${ig.id}', this.checked)">
          <span class="toggle-slider"></span>
        </label>
      </div>
    </div>
  `).join('');
}

function toggleIntegrationConfig(id) {
  const el = document.getElementById(`config-${id}`);
  if (el) el.classList.toggle('show');
}

async function toggleIntegration(id, enable) {
  try {
    if (enable) {
      // 收集配置
      const config = collectIntegrationConfig(id);
      const res = await fetch(`${API}/api/integrations/${id}/enable`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({config})
      });
      const data = await res.json();
      if (!data.success) {
        const errMsg = data.error || '启用失败';
        if (errMsg.includes('未安装') || errMsg.includes('pip install') || errMsg.includes('ImportError')) {
          const doInstall = confirm(errMsg + '\n\n是否自动安装所需依赖？');
          if (doInstall) {
            await installIntegrationDeps(id);
          }
        } else {
          alert(errMsg);
        }
      }
    } else {
      await fetch(`${API}/api/integrations/${id}/disable`, {method: 'POST'});
    }
    loadIntegrations();
  } catch (e) {
    alert('操作失败: ' + e.message);
  }
}

async function detectIntegration(id) {
  const resultEl = document.getElementById(`detect-result-${id}`);
  // 展开配置面板
  const configEl = document.getElementById(`config-${id}`);
  if (configEl) configEl.classList.add('show');
  
  if (resultEl) resultEl.innerHTML = '<div class="integration-detect-result">检测中...</div>';
  try {
    const res = await fetch(`${API}/api/integrations/${id}/detect`, {method: 'POST'});
    const data = await res.json();
    if (data.found) {
      if (resultEl) resultEl.innerHTML = `<div class="integration-detect-result found">✅ ${data.info}</div>`;
      // 自动填入路径
      const pathInput = document.querySelector(`#config-${id} input[data-config-key]`);
      if (pathInput && data.path) pathInput.value = data.path;
    } else {
      if (resultEl) resultEl.innerHTML = `<div class="integration-detect-result not-found">⚠️ ${data.info}</div>`;
    }
  } catch (e) {
    if (resultEl) resultEl.innerHTML = `<div class="integration-detect-result not-found">检测失败</div>`;
  }
}

async function testIntegration(id) {
  const config = collectIntegrationConfig(id);
  // 在卡片内显示检测中状态
  const detectEl = document.getElementById(`detect-result-${id}`);
  const configEl = document.getElementById(`config-${id}`);
  if (configEl) configEl.classList.add('show');
  if (detectEl) detectEl.innerHTML = '<div class="integration-detect-result">🔄 正在测试连接...</div>';

  try {
    const res = await fetch(`${API}/api/integrations/${id}/test`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({config})
    });
    const data = await res.json();
    if (data.success) {
      if (detectEl) detectEl.innerHTML = `<div class="integration-detect-result found">✅ ${data.message}</div>`;
    } else {
      const errMsg = data.error || '测试失败';
      // 检测是否是依赖未安装的错误 → 显示安装按钮
      if (errMsg.includes('未安装') || errMsg.includes('pip install') || errMsg.includes('ImportError') || errMsg.includes('No module')) {
        if (detectEl) detectEl.innerHTML = `
          <div class="integration-detect-result not-found">
            ⚠️ ${errMsg}
          </div>
          <button class="btn-primary btn-sm" style="margin-top:8px;width:100%" onclick="installIntegrationDeps('${id}')">
            📦 一键安装依赖
          </button>
        `;
      } else {
        if (detectEl) detectEl.innerHTML = `<div class="integration-detect-result not-found">❌ ${errMsg}</div>`;
      }
    }
  } catch (e) {
    if (detectEl) detectEl.innerHTML = `<div class="integration-detect-result not-found">❌ 请求失败: ${e.message}</div>`;
  }
}

// 自动安装集成依赖 + 在卡片和聊天框中显示进度
async function installIntegrationDeps(id) {
  const detectEl = document.getElementById(`detect-result-${id}`);
  // 在卡片内显示安装中
  if (detectEl) detectEl.innerHTML = `
    <div class="integration-detect-result" style="border-left:3px solid var(--brand)">
      <div style="display:flex;align-items:center;gap:8px">
        <span class="install-spinner"></span>
        ⏳ 正在执行安装命令，请稍候...（可能需要 30-60 秒）
      </div>
    </div>
  `;

  // 在聊天框中也插入进度消息
  const msgId = addSystemMessage('⏳ 正在安装 **' + id + '** 的依赖包...\n\n`终端命令执行中...`');

  try {
    const res = await fetch(`${API}/api/integrations/${id}/install-deps`, {
      method: 'POST'
    });
    const data = await res.json();

    if (data.success) {
      let summary = '';
      let chatDetail = '';
      if (data.results) {
        summary = data.results.map(r => (r.label || r.cmd) + ': ' + (r.success ? '✅' : '❌')).join(', ');
        chatDetail = data.results.map(r => {
          const logSnippet = (r.output || '').trim().split('\n').slice(-8).join('\n');
          return '**' + (r.label || r.cmd) + '**: ' + (r.success ? '✅ 成功' : '❌ 失败') +
                 '\n```\n' + logSnippet + '\n```';
        }).join('\n\n');
      }
      // 更新卡片
      if (detectEl) detectEl.innerHTML = `
        <div class="integration-detect-result found">
          ✅ 安装完成！${summary}<br>
          <span style="font-size:0.78rem;opacity:0.7">现在可以点击「测试连接」或开启开关了</span>
        </div>
      `;
      updateSystemMessage(msgId, '✅ **依赖安装完成！**\n\n' + chatDetail + '\n\n💡 现在可以重新点击「测试连接」或开启开关了。');
      loadIntegrations();
    } else {
      let errDetail = data.error || '';
      let chatDetail = '';
      if (data.results) {
        errDetail = data.results.map(r => (r.label || r.cmd) + ': ' + (r.success ? '✅' : '❌')).join('\n');
        chatDetail = data.results.map(r => {
          const logSnippet = (r.output || '').trim().split('\n').slice(-12).join('\n');
          return '**' + (r.label || r.cmd) + '**: ' + (r.success ? '✅' : '❌') +
                 '\n```\n' + logSnippet + '\n```';
        }).join('\n\n');
      }
      if (detectEl) detectEl.innerHTML = `
        <div class="integration-detect-result not-found">
          ⚠️ 安装失败<br><pre style="font-size:0.75rem;margin-top:6px;white-space:pre-wrap">${errDetail}</pre>
        </div>
        <button class="btn-outline btn-sm" style="margin-top:8px" onclick="installIntegrationDeps('${id}')">🔄 重试</button>
      `;
      updateSystemMessage(msgId, '⚠️ **依赖安装失败**\n\n' + (chatDetail || errDetail));
    }
  } catch (e) {
    if (detectEl) detectEl.innerHTML = `<div class="integration-detect-result not-found">❌ 请求失败: ${e.message}</div>`;
    updateSystemMessage(msgId, '❌ **安装请求失败**: ' + e.message);
  }
}

// 在聊天框中插入系统消息
function addSystemMessage(markdownContent) {
  const msgContainer = document.getElementById('messages');
  if (!msgContainer) return null;

  const msgId = 'sys-msg-' + Date.now();
  const wrapper = document.createElement('div');
  wrapper.className = 'msg assistant';
  wrapper.id = msgId;
  wrapper.innerHTML = `
    <div class="msg-avatar"><div class="avatar-icon">🔧</div></div>
    <div class="msg-content">
      <div class="msg-sender">SYSTEM</div>
      <div class="msg-bubble">
        <div class="msg-text">${renderMarkdown(markdownContent)}</div>
      </div>
    </div>
  `;
  msgContainer.appendChild(wrapper);
  injectCodeCopyButtons(wrapper);
  const wrap = document.getElementById('messagesWrap');
  if (wrap) wrap.scrollTop = wrap.scrollHeight;
  return msgId;
}

// 更新已插入的系统消息内容
function updateSystemMessage(msgId, markdownContent) {
  if (!msgId) return;
  const el = document.getElementById(msgId);
  if (!el) return;
  const textEl = el.querySelector('.msg-text');
  if (textEl) {
    textEl.innerHTML = renderMarkdown(markdownContent);
    injectCodeCopyButtons(textEl);
  }
  const wrap = document.getElementById('messagesWrap');
  if (wrap) wrap.scrollTop = wrap.scrollHeight;
}

// 安全的 markdown 渲染（兼容 marked 库可能未加载的情况）
function renderMarkdown(text) {
  if (typeof marked !== 'undefined' && marked.parse) {
    return marked.parse(text);
  }
  // 简单降级：转义 HTML + 处理 **加粗** 和 `代码`
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>');
}


async function saveIntegrationConfig(id) {
  const config = collectIntegrationConfig(id);
  try {
    const res = await fetch(`${API}/api/integrations/${id}/config`, {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({config})
    });
    const data = await res.json();
    if (data.success) {
      alert('配置已保存');
      loadIntegrations();
    }
  } catch (e) {
    alert('保存失败: ' + e.message);
  }
}

function collectIntegrationConfig(id) {
  const config = {};
  const configEl = document.getElementById(`config-${id}`);
  if (!configEl) return config;
  configEl.querySelectorAll('[data-config-key]').forEach(el => {
    const key = el.getAttribute('data-config-key');
    config[key] = el.type === 'checkbox' ? el.checked : el.value;
  });
  return config;
}

// ============================================================
//  沙盒配置管理
// ============================================================
let sandboxData = { sandbox_roots: [], forbidden_paths: [] };

async function loadSandbox() {
  try {
    const res = await fetch(`${API}/api/sandbox`);
    sandboxData = await res.json();
    renderSandboxPaths();
    updateSandboxStatus();
  } catch (e) {
    console.error('加载沙盒配置失败:', e);
  }
}

function updateSandboxStatus() {
  const icon = document.getElementById('sandboxStatusIcon');
  const text = document.getElementById('sandboxStatusText');
  if (!icon || !text) return;
  const roots = sandboxData.sandbox_roots || [];
  const forbidden = sandboxData.forbidden_paths || [];
  if (roots.length > 0) {
    icon.textContent = '🛡️';
    text.textContent = `已允许 ${roots.length} 个目录` + (forbidden.length > 0 ? `，禁止 ${forbidden.length} 个路径` : '');
    text.style.color = '#4ecdc4';
  } else {
    icon.textContent = '🔒';
    text.textContent = '默认拒绝所有访问（打开文件夹后可访问该目录）';
    text.style.color = '#ff6b6b';
  }
}

function renderSandboxPaths() {
  renderPathList('sandboxRoots', sandboxData.sandbox_roots || []);
  renderPathList('forbiddenPaths', sandboxData.forbidden_paths || []);
}

function renderPathList(containerId, paths) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = paths.map((p, i) => `
    <div class="path-item">
      <span class="path-text">${p}</span>
      <button class="path-remove" onclick="removePath('${containerId}', ${i})" title="移除">✕</button>
    </div>
  `).join('') || '<div style="color:var(--text-muted);font-size:0.82rem;padding:4px 0">暂无路径</div>';
}

function removePath(containerId, index) {
  if (containerId === 'sandboxRoots') {
    sandboxData.sandbox_roots.splice(index, 1);
  } else {
    sandboxData.forbidden_paths.splice(index, 1);
  }
  renderSandboxPaths();
  updateSandboxStatus();
  // ★ 自动保存到后端
  saveSandboxToBackend();
}

function initSandboxEvents() {
  const addRootBtn = document.getElementById('addSandboxRoot');
  const addForbidBtn = document.getElementById('addForbiddenPath');
  const saveBtn = document.getElementById('saveSandbox');
  const browseRootBtn = document.getElementById('browseSandboxRoot');
  const browseForbidBtn = document.getElementById('browseForbiddenPath');

  // 在 Electron 模式下显示文件夹浏览按钮
  if (isElectron) {
    if (browseRootBtn) browseRootBtn.style.display = '';
    if (browseForbidBtn) browseForbidBtn.style.display = '';
  }

  if (addRootBtn) addRootBtn.addEventListener('click', () => {
    const input = document.getElementById('newSandboxRoot');
    const val = input.value.trim();
    if (val) {
      sandboxData.sandbox_roots.push(val);
      input.value = '';
      renderSandboxPaths();
      updateSandboxStatus();
      // ★ 自动保存到后端
      saveSandboxToBackend();
    }
  });

  if (addForbidBtn) addForbidBtn.addEventListener('click', () => {
    const input = document.getElementById('newForbiddenPath');
    const val = input.value.trim();
    if (val) {
      sandboxData.forbidden_paths.push(val);
      input.value = '';
      renderSandboxPaths();
      updateSandboxStatus();
      // ★ 自动保存到后端
      saveSandboxToBackend();
    }
  });

  // Electron 文件夹浏览
  if (browseRootBtn) browseRootBtn.addEventListener('click', async () => {
    if (isElectron && window.electronAPI && window.electronAPI.openFolderDialog) {
      const folder = await window.electronAPI.openFolderDialog();
      if (folder) {
        sandboxData.sandbox_roots.push(folder);
        renderSandboxPaths();
        updateSandboxStatus();
      }
    }
  });

  if (browseForbidBtn) browseForbidBtn.addEventListener('click', async () => {
    if (isElectron && window.electronAPI && window.electronAPI.openFolderDialog) {
      const folder = await window.electronAPI.openFolderDialog();
      if (folder) {
        sandboxData.forbidden_paths.push(folder);
        renderSandboxPaths();
        updateSandboxStatus();
      }
    }
  });

  if (saveBtn) saveBtn.addEventListener('click', () => saveSandboxToBackend(true));
}

// ★ 统一保存沙盒到后端（自动调用 + 手动调用共用）
async function saveSandboxToBackend(showAlert = false) {
  try {
    const res = await fetch(`${API}/api/sandbox/update`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(sandboxData)
    });
    const data = await res.json();
    if (data.success) {
      if (showAlert) alert('✅ 沙盒设置已保存并立即生效！');
      console.log('[Sandbox] 配置已自动保存');
      updateSandboxStatus();
    } else {
      if (showAlert) alert('保存失败');
    }
  } catch (e) {
    console.error('[Sandbox] 保存失败:', e);
    if (showAlert) alert('保存失败: ' + e.message);
  }
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


// ---- 全局暴露（兼容 onclick 调用）----
window.switchModel = switchModel;
window.deleteModel = deleteModel;
window.saveIntegrationConfig = saveIntegrationConfig;
window.toggleIntegrationConfig = toggleIntegrationConfig;
window.detectIntegration = detectIntegration;
window.testIntegration = testIntegration;
window.installIntegrationDeps = installIntegrationDeps;
window.removePath = removePath;
window.deleteSkill = deleteSkill;
