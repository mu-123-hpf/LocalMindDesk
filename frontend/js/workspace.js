// ============================================================
//  LocalMindDesk — 项目工作区模块
//  文件树浏览、代码预览、操作日志
// ============================================================

// ============================================================
//  项目工作区（始终显示）
// ============================================================
let wsCurrentFile = null;
let _oplogTimer = null;
let _lastLogCount = 0;

// 打开文件夹（调用后端弹出系统原生文件夹选择对话框）
async function promptOpenFolder() {
  try {
    // 调用后端弹出 Windows 原生文件夹选择器
    showToast('📂 正在打开文件夹选择器...', '', 'info');
    const r = await fetch(API + '/api/workspace/pick-folder', { method: 'POST' });
    const d = await r.json();
    if (d.success && d.path) {
      openWorkspace(d.path);
    } else if (d.error && d.error !== '未选择文件夹') {
      showToast('打开失败', d.error, 'error');
    }
  } catch (e) {
    // 后端不可用时降级到手动输入
    const saved = localStorage.getItem('lmd_ws_path') || '';
    const folder = prompt('请输入项目文件夹的完整路径:', saved);
    if (folder && folder.trim()) {
      openWorkspace(folder.trim());
    }
  }
}

async function openWorkspace(folderPath) {
  try {
    const r = await fetch(API + '/api/workspace/open', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: folderPath }),
    });
    const d = await r.json();
    if (!d.success) { alert('打开失败: ' + d.error); return; }
    document.getElementById('wsProjectName').textContent = d.path.split(/[\\/]/).pop();
    document.getElementById('app').classList.add('ws-open');
    // 持久化路径
    localStorage.setItem('lmd_ws_path', d.path);
    loadFileTree();
    startOpLogPolling();
  } catch (e) { alert('打开项目失败: ' + e.message); }
}

// 启动时自动恢复上次工作区
async function restoreWorkspace() {
  const savedPath = localStorage.getItem('lmd_ws_path');
  if (savedPath) {
    try {
      const r = await fetch(API + '/api/workspace/open', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: savedPath }),
      });
      const d = await r.json();
      if (d.success) {
        document.getElementById('wsProjectName').textContent = d.path.split(/[\\/]/).pop();
        document.getElementById('app').classList.add('ws-open');
        loadFileTree();
        startOpLogPolling();
        console.log('[WS] 已恢复工作区:', savedPath);
      }
    } catch (e) {
      console.warn('[WS] 恢复工作区失败:', e.message);
    }
  }
}

async function loadFileTree() {
  try {
    const r = await fetch(API + '/api/workspace/tree?depth=3');
    const d = await r.json();
    if (!d.success) return;
    const $tree = document.getElementById('wsTree');
    $tree.innerHTML = renderTreeNodes(d.tree);
  } catch (e) { console.warn('[WS] 文件树加载失败:', e); }
}

function renderTreeNodes(nodes) {
  if (!nodes || !nodes.length) return '';
  return nodes.map(n => {
    if (n.is_dir) {
      return `
        <div>
          <div class="ws-node" onclick="toggleDir(this)">
            <span class="ws-dir-toggle">▼</span>
            <span class="ws-node-icon">📁</span>
            <span class="ws-node-name">${n.name}</span>
          </div>
          <div class="ws-children">${renderTreeNodes(n.children)}</div>
        </div>`;
    }
    const icon = getFileIcon(n.name);
    return `<div class="ws-node" data-path="${n.path}" onclick="openFile('${n.path}', this)">
      <span class="ws-node-icon">${icon}</span>
      <span class="ws-node-name">${n.name}</span>
    </div>`;
  }).join('');
}

function getFileIcon(name) {
  const ext = name.split('.').pop().toLowerCase();
  const icons = {
    py:'🐍', js:'📜', ts:'📘', html:'🌐', css:'🎨', json:'📋',
    md:'📝', yaml:'⚙', yml:'⚙', toml:'⚙', txt:'📄',
    png:'🖼', jpg:'🖼', svg:'🖼', gif:'🖼',
    pptx:'📊', docx:'📝', xlsx:'📊', pdf:'📕',
    c:'🔧', cpp:'🔧', h:'🔧', java:'☕', go:'🐹', rs:'🦀',
  };
  return icons[ext] || '📄';
}

function toggleDir(el) {
  const toggle = el.querySelector('.ws-dir-toggle');
  const children = el.nextElementSibling;
  if (toggle) toggle.classList.toggle('collapsed');
  if (children) children.style.display = children.style.display === 'none' ? '' : 'none';
}

async function openFile(filePath, nodeEl) {
  document.querySelectorAll('.ws-node.active').forEach(n => n.classList.remove('active'));
  if (nodeEl) nodeEl.classList.add('active');

  try {
    const r = await fetch(API + `/api/workspace/file?path=${encodeURIComponent(filePath)}`);
    const d = await r.json();
    if (!d.success) return;

    const $viewer = document.getElementById('wsViewer');
    const $code = document.getElementById('wsCode').querySelector('code');
    const $name = document.getElementById('wsFileName');

    $name.textContent = filePath.split('/').pop();
    $code.textContent = d.content;
    $viewer.style.display = 'flex';

    if (typeof hljs !== 'undefined' && d.language && !d.binary) {
      $code.className = `language-${d.language}`;
      hljs.highlightElement($code);
    }
    wsCurrentFile = filePath;
  } catch (e) { console.warn('[WS] 文件读取失败:', e); }
}

// 工作区按钮事件
document.getElementById('wsOpenBtn')?.addEventListener('click', promptOpenFolder);
document.getElementById('wsOpenBtnMain')?.addEventListener('click', promptOpenFolder);
document.getElementById('wsViewerClose')?.addEventListener('click', () => {
  document.getElementById('wsViewer').style.display = 'none';
  wsCurrentFile = null;
});

// 聊天中的"打开项目"指令检测
function detectWorkspaceCommand(text) {
  const match = text.match(/打开['"‘“]*(?:项目|文件夹|目录)['"’”]*\s*[：:]?\s*(.+)/);
  if (match) {
    const folder = match[1].trim().replace(/['"]/g, '');
    openWorkspace(folder);
    return true;
  }
  return false;
}

// ============================================================
//  操作日志轮询
// ============================================================
function startOpLogPolling() {
  stopOpLogPolling();
  _lastLogCount = 0;
  pollOpLog();
  _oplogTimer = setInterval(pollOpLog, 8000);
}

function stopOpLogPolling() {
  if (_oplogTimer) { clearInterval(_oplogTimer); _oplogTimer = null; }
}

async function pollOpLog() {
  try {
    const r = await fetch(API + '/api/workspace/log');
    const d = await r.json();
    const logs = d.log || [];
    renderOpLog(logs);

    // 检测新操作 → 高亮被修改的文件
    if (logs.length > _lastLogCount) {
      const newLogs = logs.slice(_lastLogCount);
      for (const log of newLogs) {
        if (log.tool === 'file_op' && log.params) {
          const p = log.params;
          const filePath = p.source || p.path || p.destination || '';
          highlightModifiedFile(filePath);
        }
      }
      // 如果正在查看的文件被修改了，自动刷新
      if (wsCurrentFile) {
        const changed = newLogs.some(l =>
          l.tool === 'file_op' && (l.params?.source?.includes(wsCurrentFile) || l.params?.path?.includes(wsCurrentFile))
        );
        if (changed) {
          const activeNode = document.querySelector('.ws-node.active');
          openFile(wsCurrentFile, activeNode);
        }
      }
      _lastLogCount = logs.length;
    }
  } catch (e) { /* silent */ }
}

function renderOpLog(logs) {
  const $list = document.getElementById('wsOpLogList');
  if (!$list || !logs.length) { if($list) $list.innerHTML = '<div class="ws-oplog-item"><span style="color:var(--text-3)">暂无操作</span></div>'; return; }

  $list.innerHTML = logs.slice(-10).reverse().map(l => {
    const icon = l.success ? '✅' : '❌';
    const cls = l.success ? 'success' : 'fail';
    const tool = l.tool || '?';
    const param = l.params ? Object.values(l.params).join(' ').substring(0, 40) : '';
    const time = l.timestamp ? new Date(l.timestamp).toLocaleTimeString('zh-CN', {hour:'2-digit', minute:'2-digit', second:'2-digit'}) : '';
    return `<div class="ws-oplog-item ${cls}">
      <span class="ws-oplog-icon">${icon}</span>
      <span class="ws-oplog-tool">${tool}</span>
      <span>${param}</span>
      <span class="ws-oplog-time">${time}</span>
    </div>`;
  }).join('');
}

function highlightModifiedFile(filePath) {
  if (!filePath) return;
  // 标准化路径
  const normalized = filePath.replace(/\\/g, '/');
  const nodes = document.querySelectorAll('.ws-node[data-path]');
  nodes.forEach(node => {
    const nodePath = node.getAttribute('data-path');
    if (normalized.includes(nodePath) || nodePath.includes(normalized.split('/').pop())) {
      node.classList.add('modified');
      setTimeout(() => node.classList.remove('modified'), 2500);
    }
  });
}


// ---- 全局暴露（兼容 onclick 调用）----
window.openFile = openFile;
window.promptOpenFolder = promptOpenFolder;
window.toggleDir = toggleDir;
