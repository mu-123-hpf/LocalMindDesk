// ============================================================
//  LocalMindDesk — 国际化 (i18n) 模块
//  支持中英文切换，可扩展更多语言
// ============================================================

const I18N = {
  zh: {
    // 侧边栏
    'chats': '对话',
    'recent_conversations': '最近的对话',
    'no_history': '暂无对话历史',
    'new_chat': '新对话',

    // 聊天
    'send_placeholder': '发送消息给 LocalMindDesk...',
    'thinking': '正在思考',
    'stop': '停止',
    'copy': '复制',
    'regenerate': '重新生成',
    'you': 'You',

    // 欢迎
    'welcome_subtitle': 'Your mind, locally amplified.',
    'privacy_badge': '数据全在本地',
    'model_status': '模型状态',
    'memory_system': '记忆系统',

    // 设置
    'settings': '设置',
    'general': '通用',
    'models': '模型',
    'skills': '技能',
    'privacy': '隐私',
    'save': '保存',
    'cancel': '取消',
    'confirm_delete': '确定删除这条对话记录吗？',

    // 状态
    'connected': '已连接',
    'disconnected': '未连接',
    'online': '在线',
    'offline': '离线',

    // 工作区
    'files_project': '文件与项目',
    'open_folder': '打开文件夹',
    'no_project': '尚未打开项目',
  },

  en: {
    'chats': 'Chats',
    'recent_conversations': 'Recent Conversations',
    'no_history': 'No conversation history',
    'new_chat': 'New Chat',

    'send_placeholder': 'Send a message to LocalMindDesk...',
    'thinking': 'Thinking',
    'stop': 'Stop',
    'copy': 'Copy',
    'regenerate': 'Regenerate',
    'you': 'You',

    'welcome_subtitle': 'Your mind, locally amplified.',
    'privacy_badge': 'All data stays local',
    'model_status': 'Model Status',
    'memory_system': 'Memory System',

    'settings': 'Settings',
    'general': 'General',
    'models': 'Models',
    'skills': 'Skills',
    'privacy': 'Privacy',
    'save': 'Save',
    'cancel': 'Cancel',
    'confirm_delete': 'Delete this conversation?',

    'connected': 'Connected',
    'disconnected': 'Disconnected',
    'online': 'Online',
    'offline': 'Offline',

    'files_project': 'Files & Project',
    'open_folder': 'Open Folder',
    'no_project': 'No project opened',
  }
};

// 当前语言
let _currentLang = localStorage.getItem('lmd_lang') || 'zh';

/**
 * 获取翻译文本
 * @param {string} key - 翻译键
 * @param {string} fallback - 未找到时的回退文本
 */
function t(key, fallback) {
  const dict = I18N[_currentLang] || I18N['zh'];
  return dict[key] || fallback || key;
}

/**
 * 切换语言
 * @param {string} lang - 语言代码 ('zh' / 'en')
 */
function setLanguage(lang) {
  if (!I18N[lang]) return;
  _currentLang = lang;
  localStorage.setItem('lmd_lang', lang);
  applyLanguage();
}

/**
 * 获取当前语言
 */
function getLanguage() {
  return _currentLang;
}

/**
 * 应用语言到页面中带 data-i18n 属性的元素
 * 用法: <span data-i18n="chats">对话</span>
 */
function applyLanguage() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.dataset.i18n;
    const text = t(key);
    if (text) {
      if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
        el.placeholder = text;
      } else {
        el.textContent = text;
      }
    }
  });
}

/**
 * 获取可用语言列表
 */
function getAvailableLanguages() {
  return Object.keys(I18N).map(code => ({
    code,
    name: code === 'zh' ? '中文' : 'English',
  }));
}

// 页面加载时应用
if (typeof window !== 'undefined') {
  window.addEventListener('DOMContentLoaded', () => {
    applyLanguage();
  });
}

// 暴露到全局
window.t = t;
window.setLanguage = setLanguage;
window.getLanguage = getLanguage;
window.getAvailableLanguages = getAvailableLanguages;
window.applyLanguage = applyLanguage;
