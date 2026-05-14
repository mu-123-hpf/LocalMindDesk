// ============================================================
//  LocalMindDesk — API 基础层
//  统一 API 调用封装，零依赖
// ============================================================

const isElectron = !!(window.electronAPI && window.electronAPI.isElectron);
const API = isElectron ? 'http://localhost:8000' : '';

/**
 * 统一 API 调用 — 自动加 base URL，返回 JSON
 * @param {string} path  API 路径 (如 '/api/chat')
 * @param {object} opts  fetch options
 * @returns {Promise<any>}
 */
async function fetchAPI(path, opts = {}) {
  const url = API + path;
  const r = await fetch(url, opts);
  return r.json();
}

/**
 * POST JSON 请求
 */
async function postJSON(path, body, extraOpts = {}) {
  return fetchAPI(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    ...extraOpts,
  });
}

/**
 * 安全的 Markdown 渲染（兼容 marked 库未加载）
 */
function renderMarkdown(text) {
  if (typeof marked !== 'undefined' && marked.parse) {
    return marked.parse(text);
  }
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>');
}

/**
 * HTML 转义
 */
function esc(t) {
  const d = document.createElement('div');
  d.textContent = t;
  return d.innerHTML.replace(/\n/g, '<br>');
}
