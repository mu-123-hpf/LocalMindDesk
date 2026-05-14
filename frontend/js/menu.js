// ============================================================
//  LocalMindDesk — 菜单模块
//  模式选择菜单 + VSCode 风格三点菜单系统
// ============================================================

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


// ============================================================
//  通用三点菜单系统 (VSCode 风格)
// ============================================================
(function initContextMenus() {
  const menuMap = {
    chatPanelMoreBtn: 'chatPanelMenu',
    chatHeaderMoreBtn: 'chatHeaderMenu',
    wsMoreBtn: 'wsMenu',
  };

  function toggleMenu(menuId, btnEl) {
    document.querySelectorAll('.ctx-menu.show').forEach(m => {
      if (m.id !== menuId) m.classList.remove('show');
    });
    const menu = document.getElementById(menuId);
    if (!menu) return;
    const wasShown = menu.classList.contains('show');
    if (wasShown) {
      menu.classList.remove('show');
      return;
    }
    // 用按钮位置动态定位
    const rect = btnEl.getBoundingClientRect();
    menu.style.top = (rect.bottom + 6) + 'px';
    menu.style.left = rect.left + 'px';
    menu.classList.add('show');
    // 检查是否超出右边界
    requestAnimationFrame(() => {
      const menuRect = menu.getBoundingClientRect();
      if (menuRect.right > window.innerWidth - 8) {
        menu.style.left = (window.innerWidth - menuRect.width - 8) + 'px';
      }
    });
  }

  Object.entries(menuMap).forEach(([btnId, menuId]) => {
    const btn = document.getElementById(btnId);
    btn?.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleMenu(menuId, btn);
    });
  });

  // 把菜单 DOM 挪到 body，避免被父容器 overflow:hidden 裁切
  document.querySelectorAll('.ctx-menu').forEach(menu => {
    document.body.appendChild(menu);
  });

  document.addEventListener('click', () => {
    document.querySelectorAll('.ctx-menu.show').forEach(m => m.classList.remove('show'));
  });

  document.querySelectorAll('.ctx-menu').forEach(menu => {
    menu.addEventListener('click', e => e.stopPropagation());
  });

  document.querySelectorAll('.ctx-menu-item').forEach(item => {
    item.addEventListener('click', async () => {
      const action = item.dataset.action;
      item.closest('.ctx-menu')?.classList.remove('show');
      await handleCtxAction(action);
    });
  });

  async function handleCtxAction(action) {
    switch (action) {
      // ---- 左侧面板 ----
      case 'export-chat': {
        if (!currentSessionId) return showToast('没有活跃会话', '', 'error');
        try {
          const r = await fetch(API + `/api/sessions/${currentSessionId}/messages`);
          const data = await r.json();
          const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url; a.download = `chat_${currentSessionId}.json`; a.click();
          URL.revokeObjectURL(url);
          showToast('✅ 对话已导出');
        } catch (e) { showToast('导出失败', e.message, 'error'); }
        break;
      }
      case 'clear-all-chats': {
        if (!confirm('确定要清空所有对话吗？此操作不可恢复。')) return;
        try {
          const r = await fetch(API + '/api/sessions');
          const data = await r.json();
          for (const s of (data.sessions || [])) {
            await fetch(API + `/api/sessions/${s.id}`, { method: 'DELETE' });
          }
          loadSessions();
          showToast('✅ 所有对话已清空');
        } catch (e) { showToast('清空失败', e.message, 'error'); }
        break;
      }
      case 'open-settings': {
        openSettings();
        break;
      }

      // ---- 中间头部 ----
      case 'personalize': {
        openSettings();
        // 切到个性化 tab
        setTimeout(() => {
          document.querySelectorAll('.stab').forEach(t => t.classList.remove('active'));
          document.querySelectorAll('.tab-content').forEach(p => p.classList.remove('active'));
          document.querySelector('[data-tab="tabPersona"]')?.classList.add('active');
          document.getElementById('tabPersona')?.classList.add('active');
          if (typeof loadPersonaForm === 'function') loadPersonaForm();
        }, 50);
        break;
      }
      case 'model-settings': {
        openSettings();
        // 切到端点 tab
        setTimeout(() => {
          document.querySelectorAll('.stab').forEach(t => t.classList.remove('active'));
          document.querySelectorAll('.tab-content').forEach(p => p.classList.remove('active'));
          document.querySelector('[data-tab="tabEndpoints"]')?.classList.add('active');
          document.getElementById('tabEndpoints')?.classList.add('active');
        }, 50);
        break;
      }
      case 'copy-chat': {
        const msgs = document.getElementById('messages');
        if (!msgs) return;
        const text = Array.from(msgs.querySelectorAll('.msg'))
          .map(m => {
            const role = m.classList.contains('user') ? 'You' : 'AI';
            return `[${role}] ${m.querySelector('.msg-text')?.innerText || ''}`;
          }).join('\n\n');
        await navigator.clipboard.writeText(text);
        showToast('✅ 对话已复制到剪贴板');
        break;
      }
      case 'regenerate': {
        const lastAi = document.querySelector('#messages .msg.assistant:last-of-type');
        if (lastAi) lastAi.remove();
        if (chatHistory.length && chatHistory[chatHistory.length - 1].role === 'assistant') {
          chatHistory.pop();
        }
        const lastUserMsg = [...chatHistory].reverse().find(m => m.role === 'user');
        if (lastUserMsg) {
          document.getElementById('chatInput').value = lastUserMsg.content;
          document.getElementById('sendBtn')?.click();
        }
        break;
      }
      case 'session-stats': {
        const msgCount = chatHistory.length;
        const userCount = chatHistory.filter(m => m.role === 'user').length;
        const aiCount = chatHistory.filter(m => m.role === 'assistant').length;
        const totalChars = chatHistory.reduce((sum, m) => sum + (m.content || '').length, 0);
        showToast(`📊 会话统计`, `消息 ${msgCount} 条 (你: ${userCount}, AI: ${aiCount}) · 约 ${Math.ceil(totalChars/4)} tokens`);
        break;
      }

      // ---- 右侧工作区 ----
      case 'ws-refresh': {
        loadFileTree();
        showToast('✅ 文件树已刷新');
        break;
      }
      case 'ws-reveal': {
        const wsPath = localStorage.getItem('lmd_ws_path');
        if (!wsPath) {
          // 没有打开项目 → 提示打开
          showToast('📂 请先打开一个项目文件夹', '', 'info');
          promptOpenFolder();
          break;
        }
        try {
          const r = await fetch(API + '/api/workspace/reveal', { method: 'POST' });
          const data = await r.json();
          if (!data.success) {
            if (data.error === '未打开项目') {
              showToast('📂 请先打开一个项目文件夹', '', 'info');
              promptOpenFolder();
            } else {
              showToast(data.error || '打开失败', '', 'error');
            }
          }
        } catch (e) { showToast('打开资源管理器失败', e.message, 'error'); }
        break;
      }
      case 'ws-copy-path': {
        const pathEl = document.getElementById('wsProjectName');
        const path = pathEl?.textContent?.trim();
        if (path && path !== 'FILES & PROJECT') {
          await navigator.clipboard.writeText(path);
          showToast('✅ 路径已复制');
        } else {
          showToast('未打开项目', '', 'error');
        }
        break;
      }
      case 'ws-close': {
        document.getElementById('wsTree').innerHTML = `
          <div class="ws-tree-empty" id="wsEmptyState">
            <div class="ws-empty-icon">📂</div>
            <div class="ws-empty-text">尚未打开项目</div>
            <button id="wsOpenBtnMain" class="sp-new-chat-btn ws-open-btn" onclick="promptOpenFolder()">📁 打开文件夹</button>
          </div>`;
        document.getElementById('wsProjectName').textContent = 'FILES & PROJECT';
        document.getElementById('wsViewer').style.display = 'none';
        showToast('✅ 工作区已关闭');
        break;
      }
    }
  }
})();

// 技能库快捷按钮 → 直接打开设置面板的技能 tab
document.getElementById('skillsShortcutBtn')?.addEventListener('click', () => {
  document.getElementById('settingsPanel').style.display = 'block';
  // 切到技能库 tab
  document.querySelectorAll('.stab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(p => p.classList.remove('active'));
  document.querySelector('[data-tab="tabSkills"]')?.classList.add('active');
  document.getElementById('tabSkills')?.classList.add('active');
  if (typeof loadSkills === 'function') loadSkills();
});

