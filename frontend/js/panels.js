// ============================================================
//  LocalMindDesk — 面板模块 (v3.0)
//  Activity Bar + Soul/蒸馏 + Privacy + Insights + Scheduler + Toast
// ============================================================

// ============================================================
//  v3.0 — Activity Bar + Side Panel + Status Bar + Toast
// ============================================================

// ---- Activity Bar Tab 切换 ----
let currentPanel = 'chat';

document.querySelectorAll('#activityBar .ab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const panel = btn.dataset.panel;
    if (!panel) return;

    // 设置按钮弹出模态框
    if (panel === 'settings') {
      openSettings();
      return;
    }

    // 再次点击同一个 Tab → 折叠侧边栏
    if (panel === currentPanel) {
      document.getElementById('sidebar').classList.toggle('collapsed');
      return;
    }

    // 切换 Activity Bar 高亮
    document.querySelectorAll('#activityBar .ab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    // 切换 Side Panel 内容
    document.querySelectorAll('.side-panel').forEach(p => p.classList.remove('active'));
    const targetPanel = document.getElementById('panel' + panel.charAt(0).toUpperCase() + panel.slice(1));
    if (targetPanel) targetPanel.classList.add('active');

    // 确保侧边栏展开
    document.getElementById('sidebar').classList.remove('collapsed');

    currentPanel = panel;

    // 加载面板数据
    if (panel === 'soul') loadSoulPanel();
    if (panel === 'insights') loadInsightsPanel();
    if (panel === 'scheduler') loadSchedulerPanel();
    if (panel === 'privacy') loadPrivacyPanel();
  });
});

// ---- Soul 面板 (多角色管理 + 蒸馏) ----
let _currentPersonaSlug = null;
let _personaList = [];
let _distillResult = null;  // 蒸馏预览缓存
let _chatFileContent = '';  // 上传的聊天记录内容
let _chatFileName = '';     // 上传的文件名（用于格式检测）

async function loadSoulPanel() {
  try {
    // 1. 加载角色列表
    const r = await fetch(API + '/api/personas');
    if (!r.ok) return;
    const data = await r.json();
    _personaList = data.personas || [];
    renderPersonaList(_personaList);

    // 2. 如果有激活角色，加载编辑器
    const active = _personaList.find(p => p.active);
    if (active) {
      loadPersonaEditor(active.slug);
    } else if (_personaList.length > 0) {
      loadPersonaEditor(_personaList[0].slug);
    }

    // 3. 加载用户事实
    try {
      const fr = await fetch(API + '/api/facts');
      if (fr.ok) {
        const facts = await fr.json();
        renderUserFacts(facts.facts || []);
      }
    } catch(e) {}

    // 4. 填充蒸馏模型选择器
    populateDistillModelSelect();

  } catch(e) { console.warn('[Soul] 加载失败:', e.message); }
}

function renderUserFacts(facts) {
  const container = document.getElementById('userFactsList');
  if (!container) return;
  if (!facts || facts.length === 0) {
    container.innerHTML = '<div class="sp-facts-empty">暂无用户事实</div>';
    return;
  }
  container.innerHTML = facts.slice(0, 20).map(f =>
    `<div class="sp-fact-item">
      <span class="sp-fact-cat">${f.category || '未分类'}</span>
      <span>${f.value || f.fact || ''}</span>
    </div>`
  ).join('');
}

function populateDistillModelSelect() {
  const sel = document.getElementById('distillModelSelect');
  if (!sel) return;

  // 保留第一个 "使用当前模型" 选项
  sel.innerHTML = '<option value="">使用当前模型</option>';

  // 从 configCache 读取可用模型
  if (configCache && configCache.models) {
    configCache.models.forEach(m => {
      const opt = document.createElement('option');
      opt.value = m.name;
      opt.textContent = `${m.model || m.name} (${m.provider})`;
      sel.appendChild(opt);
    });
  }
}

function renderPersonaList(personas) {
  const container = document.getElementById('personaList');
  if (!container) return;

  if (!personas || personas.length === 0) {
    container.innerHTML = '<div class="persona-empty">暂无角色<br><span style="font-size:11px;opacity:0.6">使用下方蒸馏功能创建</span></div>';
    return;
  }

  container.innerHTML = personas.map(p => {
    const isActive = p.active ? 'active' : '';
    const initial = (p.name || p.slug || '?')[0].toUpperCase();
    const desc = p.description || p.slug;
    return `
      <div class="persona-card ${isActive}" data-slug="${p.slug}" onclick="selectPersona('${p.slug}')">
        <div class="persona-avatar">${initial}</div>
        <div class="persona-info">
          <div class="persona-name">${p.name || p.slug}</div>
          <div class="persona-meta">
            <span>${desc.slice(0, 30)}</span>
            ${p.active ? '<span class="persona-channel-tag pc">激活</span>' : ''}
          </div>
        </div>
        <button class="persona-correct-btn" onclick="event.stopPropagation();showCorrectDialog('${p.slug}','${(p.name||p.slug).replace(/'/g,"\\\\'")}')" title="纠正角色">✏️</button>
        <button class="persona-delete-btn" onclick="event.stopPropagation();deletePersona('${p.slug}','${(p.name||p.slug).replace(/'/g,'\\\'')}')" title="删除">🗑</button>
      </div>
    `;
  }).join('');
}

async function selectPersona(slug) {
  // 切换激活角色
  try {
    const r = await fetch(API + '/api/personas/switch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slug }),
    });
    if (r.ok) {
      showToast('🎭 已切换角色', slug);
      loadSoulPanel();  // 刷新整个面板
    }
  } catch(e) {
    showToast('⚠️ 切换失败', e.message, 'error');
  }
}
window.selectPersona = selectPersona;

async function loadPersonaEditor(slug) {
  _currentPersonaSlug = slug;
  const card = document.getElementById('personaEditorCard');
  if (!card) return;

  try {
    // 加载角色的 persona 内容
    const r = await fetch(API + '/api/soul');
    if (!r.ok) return;
    const data = await r.json();

    const editor = document.getElementById('soulEditor');
    if (editor) editor.value = data.content || '';

    // 加载 memories (如果有)
    const memEditor = document.getElementById('memoriesEditor');
    if (memEditor) {
      // memories 在 soul API 的 response 里可能没有，需要单独获取
      try {
        const mr = await fetch(API + `/api/personas/${slug}/memories`);
        if (mr.ok) {
          const mdata = await mr.json();
          memEditor.value = mdata.content || '';
        } else {
          memEditor.value = '';
        }
      } catch(e) {
        memEditor.value = '';
      }
    }

    // 更新标题
    const p = _personaList.find(x => x.slug === slug);
    const title = document.getElementById('personaEditorTitle');
    if (title) title.textContent = `编辑: ${p?.name || slug}`;

    card.style.display = 'block';
  } catch(e) {
    console.warn('[Soul] 加载编辑器失败:', e.message);
  }
}

async function deletePersona(slug, name) {
  if (!confirm(`确定删除角色「${name}」？此操作不可恢复。`)) return;
  try {
    const r = await fetch(API + `/api/personas/${slug}`, { method: 'DELETE' });
    if (r.ok) {
      showToast('🗑 已删除', name);
      loadSoulPanel();
    } else {
      showToast('⚠️ 删除失败', '', 'error');
    }
  } catch(e) {
    showToast('⚠️ 删除失败', e.message, 'error');
  }
}
window.deletePersona = deletePersona;

// Soul 保存 (更新到新 API)
document.getElementById('savePersonaBtn')?.addEventListener('click', async () => {
  const content = document.getElementById('soulEditor')?.value || '';
  if (!_currentPersonaSlug) return showToast('⚠️ 没有选中角色', '', 'error');
  try {
    const r = await fetch(API + '/api/soul/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    });
    if (r.ok) showToast('💾 角色已保存', 'Persona 已更新');
    else showToast('⚠️ 保存失败', '请检查后端连接', 'error');
  } catch(e) { showToast('⚠️ 保存失败', e.message, 'error'); }
});

// 新建角色按钮 → 滚动到蒸馏区域
document.getElementById('newPersonaBtn')?.addEventListener('click', () => {
  const distillCard = document.querySelector('.distill-card');
  if (distillCard) {
    distillCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
    // 聚焦到名称输入
    setTimeout(() => {
      document.getElementById('distillName')?.focus();
    }, 300);
  }
});

// ---- 蒸馏功能 ----
document.getElementById('startDistillBtn')?.addEventListener('click', startDistill);

async function startDistill() {
  const name = document.getElementById('distillName')?.value?.trim();
  const tags = document.getElementById('distillTags')?.value?.trim();
  const desc = document.getElementById('distillDesc')?.value?.trim();
  const chatPasted = document.getElementById('distillChat')?.value?.trim();
  const chatText = _chatFileContent || chatPasted || '';
  const modelName = document.getElementById('distillModelSelect')?.value || '';

  if (!name) {
    showToast('⚠️ 请输入人物名称', '', 'error');
    document.getElementById('distillName')?.focus();
    return;
  }
  if (!desc && !chatText) {
    showToast('⚠️ 请提供描述或聊天记录', '至少需要一种原材料', 'error');
    return;
  }

  const btn = document.getElementById('startDistillBtn');
  btn.classList.add('loading');
  btn.innerHTML = '<span class="distill-btn-icon">⏳</span> 蒸馏中...';
  btn.disabled = true;

  try {
    const r = await fetch(API + '/api/distill', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        target_name: name,
        chat_text: chatText,
        chat_filename: _chatFileName || '',
        description: desc || '',
        personality_tags: tags || '',
        model_name: modelName,
        auto_create: false,  // 先预览
      }),
    });

    const data = await r.json();

    if (data.success || data.persona) {
      _distillResult = data;
      showDistillPreview(data);
    } else {
      showToast('⚠️ 蒸馏失败', data.error || '未知错误', 'error');
    }
  } catch(e) {
    showToast('⚠️ 蒸馏失败', e.message, 'error');
  }

  btn.classList.remove('loading');
  btn.innerHTML = '<span class="distill-btn-icon">🧪</span> 开始蒸馏';
  btn.disabled = false;
}

function showDistillPreview(data) {
  const preview = document.getElementById('distillPreview');
  if (!preview) return;

  // 统计信息
  const stats = data.stats || {};
  document.getElementById('previewStats').innerHTML = `
    <span class="preview-stat">📝 Persona: ${(data.persona || '').length} 字</span>
    <span class="preview-stat">💭 Memories: ${(data.memories || '').length} 字</span>
    ${stats.has_chat ? '<span class="preview-stat">💬 含聊天记录</span>' : ''}
    ${stats.has_description ? '<span class="preview-stat">📄 含描述</span>' : ''}
  `;

  // 内容
  document.getElementById('previewPersonaText').textContent = data.persona || '(无内容)';
  document.getElementById('previewMemoriesText').textContent = data.memories || '(无记忆数据)';

  // 显示预览面板
  preview.style.display = 'block';
  preview.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// 预览 Tab 切换
document.querySelectorAll('.preview-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.preview-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.preview-content').forEach(c => c.classList.remove('active'));
    tab.classList.add('active');
    const target = document.getElementById(tab.dataset.target);
    if (target) target.classList.add('active');
  });
});

// 确认创建角色
document.getElementById('confirmDistillBtn')?.addEventListener('click', async () => {
  if (!_distillResult) return;

  const name = _distillResult.name || document.getElementById('distillName')?.value?.trim();
  const slug = _distillResult.slug || name.toLowerCase().replace(/[^\w]/g, '_').slice(0, 30);

  try {
    const r = await fetch(API + '/api/personas/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: name,
        slug: slug,
        persona_content: _distillResult.persona,
        memories_content: _distillResult.memories || '',
        description: document.getElementById('distillDesc')?.value?.trim() || '',
      }),
    });

    const data = await r.json();
    if (data.success) {
      showToast('✅ 角色已创建', name);
      // 清空表单
      resetDistillForm();
      // 刷新角色列表
      loadSoulPanel();
    } else {
      showToast('⚠️ 创建失败', data.error || '', 'error');
    }
  } catch(e) {
    showToast('⚠️ 创建失败', e.message, 'error');
  }
});

// 取消预览
document.getElementById('cancelDistillBtn')?.addEventListener('click', () => {
  document.getElementById('distillPreview').style.display = 'none';
  _distillResult = null;
});
document.getElementById('closePreviewBtn')?.addEventListener('click', () => {
  document.getElementById('distillPreview').style.display = 'none';
  _distillResult = null;
});

function resetDistillForm() {
  document.getElementById('distillName').value = '';
  document.getElementById('distillTags').value = '';
  document.getElementById('distillDesc').value = '';
  document.getElementById('distillChat').value = '';
  document.getElementById('distillPreview').style.display = 'none';
  _distillResult = null;
  _chatFileContent = '';
  _chatFileName = '';
  // 重置文件上传
  const info = document.getElementById('chatFileInfo');
  const content = document.querySelector('#chatDropZone .dropzone-content');
  if (info) info.style.display = 'none';
  if (content) content.style.display = 'flex';
}

// ---- 追加材料功能 ----
let _appendFileContent = '';
let _appendFileName = '';

// 打开/关闭追加面板
document.getElementById('appendMaterialBtn')?.addEventListener('click', () => {
  const panel = document.getElementById('appendPanel');
  if (!panel) return;
  const isVisible = panel.style.display !== 'none';
  panel.style.display = isVisible ? 'none' : 'block';
  if (!isVisible) {
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
});

document.getElementById('closeAppendBtn')?.addEventListener('click', () => {
  const panel = document.getElementById('appendPanel');
  if (panel) panel.style.display = 'none';
  resetAppendForm();
});

function resetAppendForm() {
  _appendFileContent = '';
  _appendFileName = '';
  const text = document.getElementById('appendText');
  if (text) text.value = '';
  const info = document.getElementById('appendFileInfo');
  const content = document.querySelector('#appendDropZone .dropzone-content');
  if (info) info.style.display = 'none';
  if (content) content.style.display = 'flex';
  const input = document.getElementById('appendFileInput');
  if (input) input.value = '';
  const result = document.getElementById('appendResult');
  if (result) result.style.display = 'none';
}

// 追加材料文件上传
(function initAppendFileUpload() {
  const dropZone = document.getElementById('appendDropZone');
  const fileInput = document.getElementById('appendFileInput');
  const fileBtn = document.getElementById('appendFileBtn');
  const fileInfo = document.getElementById('appendFileInfo');
  const fileName = document.getElementById('appendFileName');
  const fileRemove = document.getElementById('appendFileRemove');

  if (!dropZone) return;

  fileBtn?.addEventListener('click', (e) => {
    e.stopPropagation();
    fileInput?.click();
  });

  fileInput?.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) handleAppendFile(file);
  });

  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    e.stopPropagation();
    dropZone.classList.add('drag-over');
  });
  dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('drag-over');
  });
  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    e.stopPropagation();
    dropZone.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file) handleAppendFile(file);
  });
  dropZone.addEventListener('click', () => {
    fileInput?.click();
  });

  fileRemove?.addEventListener('click', (e) => {
    e.stopPropagation();
    _appendFileContent = '';
    _appendFileName = '';
    if (fileInfo) fileInfo.style.display = 'none';
    const content = dropZone.querySelector('.dropzone-content');
    if (content) content.style.display = 'flex';
    if (fileInput) fileInput.value = '';
  });

  function handleAppendFile(file) {
    if (file.size > 10 * 1024 * 1024) {
      showToast('⚠️ 文件太大', '最大支持 10MB', 'error');
      return;
    }
    const ext = file.name.split('.').pop().toLowerCase();
    const allowed = ['txt', 'html', 'htm', 'json', 'csv', 'mht', 'log'];
    if (!allowed.includes(ext)) {
      showToast('⚠️ 不支持的文件格式', `支持: ${allowed.join(', ')}`, 'error');
      return;
    }
    const fmtNames = {
      txt: 'TXT 文本', html: 'HTML 页面', htm: 'HTML 页面',
      json: 'JSON 数据', csv: 'CSV 表格', mht: 'MHT 网页', log: '日志文件',
    };
    const reader = new FileReader();
    reader.onload = (e) => {
      _appendFileContent = e.target.result;
      _appendFileName = file.name;
      const sizeKB = (file.size / 1024).toFixed(1);
      const fmtLabel = fmtNames[ext] || ext.toUpperCase();
      if (fileName) fileName.textContent = `📄 ${file.name} (${sizeKB}KB · ${fmtLabel})`;
      if (fileInfo) fileInfo.style.display = 'flex';
      const content = dropZone.querySelector('.dropzone-content');
      if (content) content.style.display = 'none';
      showToast('📎 文件已加载', `${file.name} — ${fmtLabel}`);
    };
    reader.onerror = () => showToast('⚠️ 读取失败', '', 'error');
    reader.readAsText(file, 'utf-8');
  }
})();

// 提交追加材料
document.getElementById('submitAppendBtn')?.addEventListener('click', async () => {
  const slug = _currentPersonaSlug;
  if (!slug) {
    showToast('⚠️ 没有选中角色', '请先选择一个角色', 'error');
    return;
  }

  const pastedText = document.getElementById('appendText')?.value?.trim() || '';
  const material = _appendFileContent || pastedText;
  if (!material) {
    showToast('⚠️ 请提供材料', '上传文件或粘贴文本', 'error');
    return;
  }

  // 找到目标人物名称（从角色列表获取）
  const persona = _personaList.find(p => p.slug === slug);
  const targetName = persona?.name || slug;

  const btn = document.getElementById('submitAppendBtn');
  const resultEl = document.getElementById('appendResult');

  btn.classList.add('loading');
  btn.innerHTML = '<span class="append-btn-icon">⏳</span> 进化中...';
  btn.disabled = true;
  if (resultEl) resultEl.style.display = 'none';

  try {
    // 如果有文件，先通过解析器预处理
    let processedMaterial = material;
    if (_appendFileContent && _appendFileName) {
      // 前端传原始内容，后端会自动解析
      processedMaterial = material;
    }

    const r = await fetch(API + '/api/distill/append', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        slug: slug,
        material: processedMaterial,
        target_name: targetName,
      }),
    });

    const data = await r.json();

    if (data.success) {
      showToast('✅ 增量进化完成', `${targetName} 的记忆已更新`);
      if (resultEl) {
        resultEl.className = 'append-result success';
        resultEl.innerHTML = `
          <strong>✅ 进化成功</strong><br>
          记忆已更新：${data.memories_length || 0} 字<br>
          <span style="opacity:0.6;font-size:11px">角色记忆已自动合并保存</span>
        `;
        resultEl.style.display = 'block';
      }
      // 刷新编辑器里的 memories
      loadPersonaEditor(slug);
    } else {
      showToast('⚠️ 进化失败', data.error || '未知错误', 'error');
      if (resultEl) {
        resultEl.className = 'append-result error';
        resultEl.innerHTML = `<strong>❌ 失败</strong>: ${data.error || '未知错误'}`;
        resultEl.style.display = 'block';
      }
    }
  } catch (e) {
    showToast('⚠️ 请求失败', e.message, 'error');
    if (resultEl) {
      resultEl.className = 'append-result error';
      resultEl.innerHTML = `<strong>❌ 网络错误</strong>: ${e.message}`;
      resultEl.style.display = 'block';
    }
  }

  btn.classList.remove('loading');
  btn.innerHTML = '<span class="append-btn-icon">🧬</span> 开始增量进化';
  btn.disabled = false;
});

// ---- 版本历史功能 ----
document.getElementById('personaVersionBtn')?.addEventListener('click', () => {
  const panel = document.getElementById('versionPanel');
  if (!panel) return;
  const isVisible = panel.style.display !== 'none';
  if (isVisible) {
    panel.style.display = 'none';
  } else {
    panel.style.display = 'block';
    loadVersionHistory();
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
});

document.getElementById('closeVersionBtn')?.addEventListener('click', () => {
  const panel = document.getElementById('versionPanel');
  if (panel) panel.style.display = 'none';
});

async function loadVersionHistory() {
  const slug = _currentPersonaSlug;
  if (!slug) return;

  const container = document.getElementById('versionList');
  if (!container) return;

  container.innerHTML = '<div class="sp-facts-empty">加载中...</div>';

  try {
    const r = await fetch(API + `/api/personas/${slug}/versions`);
    if (!r.ok) {
      container.innerHTML = '<div class="version-empty">加载失败</div>';
      return;
    }
    const data = await r.json();
    const versions = data.versions || [];

    // 获取当前版本号
    const persona = _personaList.find(p => p.slug === slug);
    const currentVersion = persona?.version || 'v1';

    if (versions.length === 0) {
      container.innerHTML = '<div class="version-empty">📜 暂无历史版本<br><span style="font-size:11px;opacity:0.6">保存角色后会自动存档</span></div>';
      return;
    }

    container.innerHTML = versions.map((v, i) => {
      const date = new Date(v.date);
      const dateStr = date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
      const timeStr = date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
      const sizeKB = (v.size / 1024).toFixed(1);
      const isCurrent = v.version === currentVersion;
      return `
        <div class="version-item ${isCurrent ? 'current' : ''}">
          <div class="version-info">
            <div class="version-label">
              ${v.version}
              ${isCurrent ? '<span class="version-current-tag">当前</span>' : ''}
            </div>
            <div class="version-meta">${dateStr} ${timeStr} · ${sizeKB}KB</div>
          </div>
          <div class="version-actions">
            <button class="btn-outline btn-sm" onclick="previewVersion('${slug}','${v.version}')" title="查看内容">👁</button>
            ${!isCurrent ? `<button class="btn-outline btn-sm" onclick="rollbackVersion('${slug}','${v.version}')" title="回滚到此版本">⏪</button>` : ''}
          </div>
        </div>
      `;
    }).join('');
  } catch (e) {
    container.innerHTML = `<div class="version-empty">加载失败: ${e.message}</div>`;
  }
}

async function previewVersion(slug, version) {
  try {
    // 读取版本文件内容（通过下载 API 或直接用 soul API）
    // 这里用简单方式：提示用户版本信息
    const r = await fetch(API + `/api/personas/${slug}/versions`);
    if (!r.ok) return;
    const data = await r.json();
    const v = (data.versions || []).find(x => x.version === version);
    if (v) {
      const date = new Date(v.date).toLocaleString('zh-CN');
      const sizeKB = (v.size / 1024).toFixed(1);
      showToast(`📜 ${version}`, `${date} · ${sizeKB}KB\n点击 ⏪ 回滚到此版本`);
    }
  } catch (e) {
    showToast('⚠️ 查看失败', e.message, 'error');
  }
}
window.previewVersion = previewVersion;

async function rollbackVersion(slug, version) {
  if (!confirm(`确定回滚角色到版本 ${version}？\n当前版本将被存档后替换。`)) return;

  try {
    const r = await fetch(API + `/api/personas/${slug}/rollback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ version }),
    });
    const data = await r.json();
    if (data.success) {
      showToast('✅ 已回滚', `${slug} → ${version}（新版本 ${data.version || ''}）`);
      // 刷新编辑器和版本列表
      loadPersonaEditor(slug);
      loadVersionHistory();
      loadSoulPanel();
    } else {
      showToast('⚠️ 回滚失败', data.error || '', 'error');
    }
  } catch (e) {
    showToast('⚠️ 回滚失败', e.message, 'error');
  }
}
window.rollbackVersion = rollbackVersion;

// ---- 隐私保护面板 ----
let _privacyBlacklist = [];

async function loadPrivacyPanel() {
  try {
    const r = await fetch(API + '/api/privacy/status');
    if (!r.ok) return;
    const data = await r.json();

    // 更新统计数据
    const stats = data.stats || {};
    const el = (id, val) => {
      const e = document.getElementById(id);
      if (e) e.textContent = val;
    };
    el('pvStatScanned', stats.total_scanned || 0);
    el('pvStatSanitized', stats.total_sanitized || 0);
    el('pvStatBlacklist', stats.blacklist_count || 0);

    // 路由统计
    const rs = data.router_stats || {};
    el('pvStatLocal', rs.local_calls || 0);
    el('pvStatCloud', rs.cloud_calls || 0);
    el('pvStatFiltered', rs.filtered_calls || 0);

    // 更新黑名单标签
    _privacyBlacklist = data.blacklist || [];
    renderBlacklistTags();

    // 更新脱敏日志
    renderPrivacyLog(data.history || []);

  } catch (e) {
    console.warn('[Privacy] 加载失败:', e.message);
  }
}

function renderBlacklistTags() {
  const container = document.getElementById('blacklistTags');
  if (!container) return;
  if (_privacyBlacklist.length === 0) {
    container.innerHTML = '<span style="font-size:11px;color:var(--text-3);opacity:0.6">暂无自定义敏感词</span>';
    return;
  }
  container.innerHTML = _privacyBlacklist.map(word =>
    `<span class="blacklist-tag">
      ${word}
      <button onclick="removeBlacklistWord('${word.replace(/'/g, "\\'")}')" title="删除">✕</button>
    </span>`
  ).join('');
}

function renderPrivacyLog(history) {
  const container = document.getElementById('privacyLog');
  if (!container) return;
  if (!history || history.length === 0) {
    container.innerHTML = '<div class="sp-facts-empty">暂无脱敏记录<br><span style="font-size:11px;opacity:0.6">发送消息后会自动记录</span></div>';
    return;
  }
  container.innerHTML = history.slice().reverse().map(item => {
    const date = new Date(item.time * 1000);
    const timeStr = date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    const types = (item.types || []).join(', ');
    return `
      <div class="privacy-log-item">
        <span class="log-level ${item.sensitivity}">${item.sensitivity}</span>
        <span class="log-types">${types} (${item.count}项, 分值${item.score})</span>
        <span class="log-time">${timeStr}</span>
      </div>
    `;
  }).join('');
}

// 添加敏感词
document.getElementById('addBlacklistBtn')?.addEventListener('click', addBlacklistWord);
document.getElementById('blacklistInput')?.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') addBlacklistWord();
});

async function addBlacklistWord() {
  const input = document.getElementById('blacklistInput');
  const word = input?.value?.trim();
  if (!word) return;

  try {
    const r = await fetch(API + '/api/privacy/blacklist', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ words: [word] }),
    });
    const data = await r.json();
    if (data.success) {
      _privacyBlacklist = data.blacklist || [];
      renderBlacklistTags();
      input.value = '';
      document.getElementById('pvStatBlacklist').textContent = data.count || _privacyBlacklist.length;
      showToast('🛡️ 已添加敏感词', word);
    } else {
      showToast('⚠️ 添加失败', data.error || '', 'error');
    }
  } catch (e) {
    showToast('⚠️ 添加失败', e.message, 'error');
  }
}

async function removeBlacklistWord(word) {
  try {
    const r = await fetch(API + `/api/privacy/blacklist/${encodeURIComponent(word)}`, {
      method: 'DELETE',
    });
    const data = await r.json();
    if (data.success) {
      _privacyBlacklist = data.blacklist || [];
      renderBlacklistTags();
      document.getElementById('pvStatBlacklist').textContent = _privacyBlacklist.length;
      showToast('🗑 已移除', word);
    }
  } catch (e) {
    showToast('⚠️ 移除失败', e.message, 'error');
  }
}
window.removeBlacklistWord = removeBlacklistWord;

// ---- 文件上传处理 ----
(function initFileUpload() {
  const dropZone = document.getElementById('chatDropZone');
  const fileInput = document.getElementById('chatFileInput');
  const fileBtn = document.getElementById('chatFileBtn');
  const fileInfo = document.getElementById('chatFileInfo');
  const fileName = document.getElementById('chatFileName');
  const fileRemove = document.getElementById('chatFileRemove');

  if (!dropZone) return;

  // 选择文件按钮
  fileBtn?.addEventListener('click', (e) => {
    e.stopPropagation();
    fileInput?.click();
  });

  // 文件选择
  fileInput?.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) handleFile(file);
  });

  // 拖拽
  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    e.stopPropagation();
    dropZone.classList.add('drag-over');
  });
  dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('drag-over');
  });
  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    e.stopPropagation();
    dropZone.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  });

  // 点击区域也选择文件
  dropZone.addEventListener('click', () => {
    fileInput?.click();
  });

  // 移除文件
  fileRemove?.addEventListener('click', (e) => {
    e.stopPropagation();
    _chatFileContent = '';
    _chatFileName = '';
    if (fileInfo) fileInfo.style.display = 'none';
    const content = dropZone.querySelector('.dropzone-content');
    if (content) content.style.display = 'flex';
    if (fileInput) fileInput.value = '';
  });

  function handleFile(file) {
    // 校验文件大小
    if (file.size > 10 * 1024 * 1024) {
      showToast('⚠️ 文件太大', '最大支持 10MB', 'error');
      return;
    }

    // 校验文件扩展名
    const ext = file.name.split('.').pop().toLowerCase();
    const allowed = ['txt', 'html', 'htm', 'json', 'csv', 'mht', 'log'];
    if (!allowed.includes(ext)) {
      showToast('⚠️ 不支持的文件格式', `支持: ${allowed.join(', ')}`, 'error');
      return;
    }

    const fmtNames = {
      txt: 'TXT 文本', html: 'HTML 页面', htm: 'HTML 页面',
      json: 'JSON 数据', csv: 'CSV 表格', mht: 'MHT 网页', log: '日志文件',
    };

    const reader = new FileReader();
    reader.onload = (e) => {
      _chatFileContent = e.target.result;
      _chatFileName = file.name;
      const sizeKB = (file.size / 1024).toFixed(1);
      const fmtLabel = fmtNames[ext] || ext.toUpperCase();
      if (fileName) fileName.textContent = `📄 ${file.name} (${sizeKB}KB · ${fmtLabel})`;
      if (fileInfo) fileInfo.style.display = 'flex';
      const content = dropZone.querySelector('.dropzone-content');
      if (content) content.style.display = 'none';
      showToast('📎 文件已加载', `${file.name} — ${fmtLabel}`);
    };
    reader.onerror = () => {
      showToast('⚠️ 读取失败', '', 'error');
    };
    reader.readAsText(file, 'utf-8');
  }
})();

// ---- Insights 面板 ----
async function loadInsightsPanel() {
  try {
    const r = await fetch(API + '/api/insights');
    if (!r.ok) return;
    const data = await r.json();

    // 工具排行
    const toolList = document.getElementById('toolRankList');
    if (toolList && data.tool_ranking) {
      const maxCount = Math.max(...data.tool_ranking.map(t => t.count), 1);
      toolList.innerHTML = data.tool_ranking.slice(0, 8).map(t =>
        `<div class="sp-rank-item">
          <span style="min-width:60px">${t.name}</span>
          <div class="sp-rank-bar"><div class="sp-rank-fill" style="width:${(t.count/maxCount*100)}%"></div></div>
          <span class="sp-rank-count">${t.count}</span>
        </div>`
      ).join('') || '<div class="sp-facts-empty">暂无数据</div>';
    }

    // 技能排行
    const skillList = document.getElementById('skillRankList');
    if (skillList && data.skill_ranking) {
      const maxCount = Math.max(...data.skill_ranking.map(s => s.count), 1);
      skillList.innerHTML = data.skill_ranking.slice(0, 8).map(s =>
        `<div class="sp-rank-item">
          <span style="min-width:60px">${s.name}</span>
          <div class="sp-rank-bar"><div class="sp-rank-fill" style="width:${(s.count/maxCount*100)}%"></div></div>
          <span class="sp-rank-count">${s.count}</span>
        </div>`
      ).join('') || '<div class="sp-facts-empty">暂无数据</div>';
    }

    // AI 洞察
    const summaryEl = document.getElementById('insightsSummary');
    if (summaryEl) summaryEl.textContent = data.summary || '暂无洞察';

  } catch(e) { console.warn('[Insights] 加载失败:', e.message); }
}

// ---- Scheduler 面板 ----
async function loadSchedulerPanel() {
  try {
    const r = await fetch(API + '/api/schedules');
    if (!r.ok) return;
    const data = await r.json();
    const tasks = data.tasks || [];
    const container = document.getElementById('scheduleQuickList');
    if (!container) return;

    if (tasks.length === 0) {
      container.innerHTML = '<div class="sp-facts-empty">暂无定时任务<br><span style="font-size:11px;color:var(--text-3)">试试在聊天中说「每天6点提醒我跑步」</span></div>';
      return;
    }

    container.innerHTML = tasks.map(t => `
      <div class="sp-sched-item">
        <span class="sp-sched-name">${t.name || '未命名'}</span>
        <span class="sp-sched-cron">${t.cron || ''}</span>
        <button class="sp-sched-toggle ${t.enabled ? 'on' : ''}"
                onclick="toggleScheduleTask('${t.id}', this)"
                title="${t.enabled ? '暂停' : '启用'}"></button>
      </div>
    `).join('');
  } catch(e) { console.warn('[Scheduler] 加载失败:', e.message); }
}

// 开关定时任务
async function toggleScheduleTask(id, btn) {
  try {
    await fetch(API + `/api/schedules/${id}/toggle`, { method: 'POST' });
    btn.classList.toggle('on');
  } catch(e) {}
}
// 暴露到全局
window.toggleScheduleTask = toggleScheduleTask;

// 新建定时任务按钮 → 打开设置面板的定时任务 tab
document.getElementById('addScheduleQuickBtn')?.addEventListener('click', () => {
  openSettings();
  // 切换到定时任务 tab
  setTimeout(() => {
    document.querySelectorAll('.stab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelector('[data-tab="tabSchedules"]')?.classList.add('active');
    document.getElementById('tabSchedules')?.classList.add('active');
    loadSchedules();
  }, 100);
});

// ---- 底部状态栏更新 ----
async function updateStatusBar() {
  try {
    const r = await fetch(API + '/api/health');
    if (!r.ok) return;
    const d = await r.json();

    const sbModel = document.getElementById('sbModel');
    const sbModelDot = document.getElementById('sbModelDot');
    if (sbModel && d.status === 'ok') {
      sbModelDot?.classList.add('online');
      sbModel.innerHTML = `<span class="status-dot online"></span> ${d.model || d.provider}`;
    }
  } catch(e) {}

  try {
    const r = await fetch(API + '/api/facts');
    if (!r.ok) return;
    const d = await r.json();
    const sbFacts = document.getElementById('sbFacts');
    if (sbFacts) sbFacts.textContent = `🧩 ${(d.facts || []).length} facts`;
  } catch(e) {}
}

// 30 秒更新一次状态栏
setTimeout(updateStatusBar, 5000);
setInterval(updateStatusBar, 60000);

// ---- Toast 通知系统 ----
function showToast(title, body, type = 'info') {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = 'toast';
  if (type === 'error') toast.style.borderColor = 'var(--error)';

  toast.innerHTML = `
    <div class="toast-header">
      <span class="toast-title" ${type === 'error' ? 'style="color:var(--error)"' : ''}>${title}</span>
      <button class="toast-close" onclick="this.closest('.toast').remove()">✕</button>
    </div>
    <div class="toast-body">${body}</div>
  `;

  container.appendChild(toast);

  // 5 秒后自动消失
  setTimeout(() => {
    toast.classList.add('toast-exit');
    setTimeout(() => toast.remove(), 300);
  }, 5000);
}

// 暴露到全局
window.showToast = showToast;

// ========== 1. 主动消息全局通知 ==========
// 不管用户在哪个会话，都能收到定时任务/空闲关怀等通知
// 同时把提醒消息直接追加到当前聊天
(function startProactiveNotifier() {
  setInterval(async () => {
    try {
      const resp = await fetch(API + '/api/proactive/messages');
      if (!resp.ok) return;
      const data = await resp.json();
      const messages = data.messages || data;
      if (!Array.isArray(messages) || messages.length === 0) return;

      for (const msg of messages) {
        const text = msg.content || msg.message || '新通知';
        // Toast 通知
        showToast('🔔 ' + text, 'info');

        // 直接追加到当前聊天（不需要刷新）
        if (typeof appendMsg === 'function' && currentSessionId) {
          appendMsg('assistant', '⏰ ' + text);
          chatHistory.push({ role: 'assistant', content: '⏰ ' + text });
        }
      }
    } catch (e) { /* 静默 */ }
  }, 15000);
})();


