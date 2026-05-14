// ============================================================
//  LocalMindDesk — 前端性能优化模块
//  消息懒加载 + 滚动优化 + 资源节流
// ============================================================

/**
 * 消息懒加载：当对话超过 MAX_VISIBLE 条时，只渲染可视区域附近的消息
 * 旧消息折叠为"加载更多"按钮
 */
const MSG_LAZY_THRESHOLD = 50;  // 超过此数量启用懒加载

function applyLazyMessages() {
  if (!$msg) return;
  const msgs = $msg.querySelectorAll('.msg');
  if (msgs.length <= MSG_LAZY_THRESHOLD) return;

  // 折叠前 N 条消息
  const hideCount = msgs.length - MSG_LAZY_THRESHOLD;

  // 如果已有折叠按钮，更新计数
  let collapseBtn = $msg.querySelector('.msg-lazy-expand');
  if (collapseBtn) {
    collapseBtn.textContent = `⬆ 加载更早的 ${hideCount} 条消息`;
    return;
  }

  // 隐藏旧消息
  for (let i = 0; i < hideCount; i++) {
    msgs[i].style.display = 'none';
    msgs[i].dataset.lazyHidden = 'true';
  }

  // 插入展开按钮
  collapseBtn = document.createElement('div');
  collapseBtn.className = 'msg-lazy-expand';
  collapseBtn.textContent = `⬆ 加载更早的 ${hideCount} 条消息`;
  collapseBtn.style.cssText = `
    text-align: center; padding: 10px; cursor: pointer;
    color: var(--accent); font-size: 13px; font-weight: 500;
    border-radius: var(--radius); margin: 8px 0;
    background: var(--bg-3); border: 1px dashed var(--border);
    transition: all 0.2s ease;
  `;
  collapseBtn.onmouseenter = () => { collapseBtn.style.background = 'var(--bg-hover)'; };
  collapseBtn.onmouseleave = () => { collapseBtn.style.background = 'var(--bg-3)'; };
  collapseBtn.onclick = () => {
    // 展开所有隐藏消息
    $msg.querySelectorAll('[data-lazy-hidden]').forEach(m => {
      m.style.display = '';
      delete m.dataset.lazyHidden;
    });
    collapseBtn.remove();
  };
  $msg.insertBefore(collapseBtn, msgs[hideCount]);
}

/**
 * 防抖滚动：减少滚动事件处理频率
 */
function debounce(fn, ms) {
  let timer;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), ms);
  };
}

/**
 * 智能滚动：只在用户在底部时自动滚动
 */
let _userScrolledUp = false;

function initSmartScroll() {
  if (!$wrap) return;
  $wrap.addEventListener('scroll', debounce(() => {
    const atBottom = $wrap.scrollHeight - $wrap.scrollTop - $wrap.clientHeight < 100;
    _userScrolledUp = !atBottom;
  }, 100));
}

function smartScrollToBottom() {
  if (!_userScrolledUp && $wrap) {
    $wrap.scrollTop = $wrap.scrollHeight;
  }
}

// 在 DOM 加载后初始化
if (typeof window !== 'undefined') {
  window.addEventListener('DOMContentLoaded', () => {
    setTimeout(initSmartScroll, 500);
  });
}

// 暴露到全局
window.applyLazyMessages = applyLazyMessages;
window.smartScrollToBottom = smartScrollToBottom;
window.debounce = debounce;
