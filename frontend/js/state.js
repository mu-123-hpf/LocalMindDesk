// ============================================================
//  LocalMindDesk — 共享状态
//  所有模块共享的可变状态，通过 getter/setter 管理
// ============================================================

// ---- 核心状态 ----
let isGenerating = false;
let currentAbortController = null;
let chatHistory = [];
let configCache = null;
let currentSessionId = null;
let bootData = null;
let currentMode = 'collaborate';

// ---- DOM 引用（init 时绑定） ----
let $msg, $wrap, $input, $send, $welcome, $typing, $modelSelect, $dot, $modelLabel;

function initDOM() {
  $msg = document.getElementById('messages');
  $wrap = document.getElementById('messagesWrap');
  $input = document.getElementById('chatInput');
  $send = document.getElementById('sendBtn');
  $welcome = document.getElementById('welcome');
  $typing = document.getElementById('typingIndicator');
  $modelSelect = document.getElementById('modelSelect');
  $dot = document.getElementById('statusDot');
  $modelLabel = document.getElementById('modelLabel');
}

// ---- Setter 函数（避免直接赋值导入绑定） ----
function setGenerating(v) { isGenerating = v; }
function setAbortController(v) { currentAbortController = v; }
function setChatHistory(v) { chatHistory = v; }
function pushChatHistory(msg) { chatHistory.push(msg); }
function popChatHistory() { return chatHistory.pop(); }
function setConfigCache(v) { configCache = v; }
function setCurrentSessionId(v) { currentSessionId = v; }
function setBootData(v) { bootData = v; }
function setCurrentMode(v) { currentMode = v; }

// 模式配置
const MODE_CONFIG = {
  plan:        { icon: '📋', label: 'Plan',        desc: '先制定计划，确认后执行' },
  execute:     { icon: '🎯', label: 'Execute',     desc: '直接执行，快速完成' },
  collaborate: { icon: '🤝', label: 'Collaborate', desc: '协作讨论方案后行动' },
  review:      { icon: '🔍', label: 'Review',      desc: '深度审查与改进建议' },
};
