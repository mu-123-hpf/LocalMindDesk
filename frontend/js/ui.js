// ============================================================
//  LocalMindDesk — UI 组件模块
//  活动流、确认弹窗、UI热更新、记忆指示器、Dashboard、
//  Agent时间线、侧边栏折叠、粒子背景、主题切换
// ============================================================

// ============================================================
//  活动流渲染 (Mission Control)
// ============================================================
function renderActivityFeed(activities) {
  const $msgs = document.getElementById('messages');

  // 计算思考耗时（从第一个活动到最后一个活动的时间差）
  let durationText = '';
  if (activities.length >= 2) {
    try {
      const t0 = new Date(activities[0].timestamp).getTime();
      const tN = new Date(activities[activities.length - 1].timestamp).getTime();
      const sec = Math.max(0.1, (tN - t0) / 1000).toFixed(1);
      durationText = ` for ${sec}s`;
    } catch (e) {
      durationText = '';
    }
  }

  // 构建活动列表 HTML
  let itemsHtml = '';
  activities.forEach(a => {
    const statusIcons = { working: '🔄', done: '✅', error: '❌', confirm: '⏳' };
    const icon = statusIcons[a.status] || '📋';
    itemsHtml += `
      <div class="activity-item activity-${a.status}">
        <span class="activity-icon">${icon}</span>
        <span class="activity-agent">[${a.agent}]</span>
        <span class="activity-msg">${a.message}</span>
      </div>`;
  });

  // 折叠容器
  const feedDiv = document.createElement('div');
  feedDiv.className = 'activity-feed activity-collapsed';
  feedDiv.innerHTML = `
    <div class="activity-feed-header" onclick="this.parentElement.classList.toggle('activity-collapsed')">
      <span class="activity-toggle-icon">▶</span>
      <span class="activity-feed-label">💭 Thought${durationText}</span>
      <span class="activity-summary">${activities.length} steps</span>
    </div>
    <div class="activity-feed-body">${itemsHtml}</div>
  `;

  $msgs.appendChild(feedDiv);
  document.getElementById('messagesWrap').scrollTop = 999999;
}

// ============================================================
//  操作确认弹窗
// ============================================================
let pendingActions = [];

function showActionConfirmModal(actions) {
  pendingActions = actions;

  // ====== 内联卡片（嵌入聊天流），不再全屏弹窗 ======
  const div = document.createElement('div');
  div.className = 'msg assistant';

  let itemsHtml = '';
  actions.forEach((a) => {
    const isCritical = a.danger_level === 'critical';
    const levelTag = isCritical
      ? '<span class="acf-tag acf-critical">高危</span>'
      : '<span class="acf-tag acf-moderate">需确认</span>';
    const icon = isCritical ? '🔴' : '🟡';

    let descHtml = '<div class="acf-desc">' + icon + ' ' + (a.description || '未知操作') + '</div>';
    if (a.reason) {
      descHtml += '<div class="acf-reason">\u26a0\ufe0f ' + a.reason + '</div>';
    }

    // ===== 标注具体改动 =====
    const params = a.params || {};
    let detailHtml = '';
    if (a.tool === 'file_op') {
      const act = params.action || '';
      const src = params.source || params.path || '';
      if (act === 'write' && params.content) {
        detailHtml = '<div class="acf-detail"><span class="acf-label">\ud83d\udcdd 写入:</span> <code>' + esc(src) + '</code></div>';
        const preview = params.content.length < 500
          ? esc(params.content)
          : esc(params.content.substring(0, 400)) + '...\n(共 ' + params.content.length + ' 字符)';
        detailHtml += '<pre class="acf-preview">' + preview + '</pre>';
      } else if (act === 'edit') {
        detailHtml = '<div class="acf-detail"><span class="acf-label">\u270f\ufe0f 编辑:</span> <code>' + esc(src) + '</code></div>';
        if (params.find) detailHtml += '<div class="acf-detail acf-diff-del">\u2796 ' + esc(params.find) + '</div>';
        if (params.replace) detailHtml += '<div class="acf-detail acf-diff-add">\u2795 ' + esc(params.replace) + '</div>';
      } else if (act === 'delete') {
        detailHtml = '<div class="acf-detail"><span class="acf-label">\ud83d\uddd1\ufe0f 删除:</span> <code>' + esc(src) + '</code></div>';
      } else if (act === 'append') {
        detailHtml = '<div class="acf-detail"><span class="acf-label">\u2795 追加到:</span> <code>' + esc(src) + '</code></div>';
        if (params.content) {
          const preview2 = params.content.length < 300 ? esc(params.content) : esc(params.content.substring(0, 250)) + '...';
          detailHtml += '<pre class="acf-preview">' + preview2 + '</pre>';
        }
      } else {
        detailHtml = '<div class="acf-detail"><span class="acf-label">' + act + ':</span> <code>' + esc(src) + '</code></div>';
      }
    } else if (a.tool === 'shell_exec') {
      detailHtml = '<div class="acf-detail"><span class="acf-label">\ud83d\udcbb 命令:</span> <code>' + esc(params.command || '') + '</code></div>';
    } else if (a.tool === 'gui_action') {
      detailHtml = '<div class="acf-detail"><span class="acf-label">\ud83d\uddb1\ufe0f GUI:</span> ' + esc(params.action || '') + '</div>';
    } else if (a.tool === 'browser') {
      const act = params.action || '';
      if (act === 'open') {
        detailHtml = '<div class="acf-detail"><span class="acf-label">\ud83c\udf10 打开:</span> <code>' + esc(params.url || '') + '</code></div>';
      } else if (act === 'search') {
        detailHtml = '<div class="acf-detail"><span class="acf-label">\ud83d\udd0d 搜索:</span> ' + esc(params.query || '') + ' <span style="opacity:0.5">(' + esc(params.engine || 'google') + ')</span></div>';
      } else if (act === 'click') {
        detailHtml = '<div class="acf-detail"><span class="acf-label">\ud83d\uddb1\ufe0f 点击:</span> ' + esc(params.text || params.selector || '') + '</div>';
      } else if (act === 'type') {
        detailHtml = '<div class="acf-detail"><span class="acf-label">\u2328\ufe0f 输入:</span> ' + esc(params.text || '') + '</div>';
      } else if (act === 'close') {
        detailHtml = '<div class="acf-detail"><span class="acf-label">\u274c</span> 关闭 AI 浏览器</div>';
      } else {
        detailHtml = '<div class="acf-detail"><span class="acf-label">\ud83c\udf10 浏览器:</span> ' + esc(act) + '</div>';
      }
    }

    itemsHtml += '<div class="acf-item ' + (isCritical ? 'acf-item-critical' : '') + '">'
      + '<div class="acf-item-header">' + descHtml + levelTag + '</div>'
      + detailHtml
      + '</div>';
  });

  div.innerHTML = '<div class="msg-avatar">🧠</div>'
    + '<div class="msg-body">'
    + '  <div class="msg-role">LocalMindDesk</div>'
    + '  <div class="msg-content">'
    + '    <div class="acf-card">'
    + '      <div class="acf-header">'
    + '        <span class="acf-header-icon">\u26a1</span>'
    + '        <span class="acf-header-text">\u3010Action-Agent\u3011</span>'
    + '      </div>'
    + '      <div class="acf-title">\ud83d\udd12 以下操作需要确认：</div>'
    + '      <div class="acf-items">' + itemsHtml + '</div>'
    + '      <div class="acf-actions">'
    + '        <button class="acf-btn acf-approve">\u2705 确认执行</button>'
    + '        <button class="acf-btn acf-deny">\u274c 取消</button>'
    + '      </div>'
    + '    </div>'
    + '  </div>'
    + '</div>';

  $msg.appendChild(div);
  $wrap.scrollTop = $wrap.scrollHeight;

  // 绑定按钮
  const approveBtn = div.querySelector('.acf-approve');
  const denyBtn = div.querySelector('.acf-deny');
  const actionsDiv = div.querySelector('.acf-actions');

  approveBtn.onclick = async () => {
    const execAbort = new AbortController();
    actionsDiv.innerHTML = '<div class="acf-executing">\u23f3 正在执行...<button class="acf-btn acf-deny acf-cancel-exec" style="margin-left:8px;padding:3px 10px;font-size:11px">\u23f9 中断</button></div>';
    const cancelBtn = actionsDiv.querySelector('.acf-cancel-exec');
    if (cancelBtn) cancelBtn.onclick = () => execAbort.abort();
    try {
      // ★ 如果有沙盒被拦截的路径，先授权
      const sandboxBlocked = pendingActions.filter(a => a.sandbox_blocked && a.blocked_path);
      for (const sb of sandboxBlocked) {
        try {
          await fetch(API + '/api/sandbox/grant', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: sb.blocked_path, reason: sb.reason || '', action: sb.description || '' }),
          });
          console.log('[Sandbox] 已授权路径:', sb.blocked_path);
        } catch (e) {
          console.error('[Sandbox] 授权失败:', sb.blocked_path, e);
        }
      }

      const actionsToExec = pendingActions.map(a => ({ tool: a.tool, params: a.params }));
      const hasForce = sandboxBlocked.length > 0;
      const r = await fetch(API + '/api/actions/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ actions: actionsToExec, force_allow: hasForce }),
        signal: execAbort.signal,
      });
      const d = await r.json();

      // ★ 沙盒权限升级: 需要用户批准 (AI assistant 模式)
      if (d.needs_approval && d.pending_permissions) {
        let permHtml = '<div class="acf-result" style="border-left:3px solid #f59e0b; padding:8px; margin:4px 0;">';
        permHtml += '<div style="font-weight:600; color:#f59e0b; margin-bottom:6px;">🔒 以下路径超出沙盒范围，需要您的授权：</div>';
        d.pending_permissions.forEach(p => {
          permHtml += '<div style="margin:4px 0; font-size:12px;">';
          permHtml += '<code style="color:var(--accent)">' + esc(p.path) + '</code>';
          permHtml += ' <span style="opacity:0.6">(' + esc(p.action) + ')</span>';
          permHtml += '</div>';
        });
        permHtml += '<div style="display:flex; gap:8px; margin-top:10px;">';
        permHtml += '<button class="acf-btn acf-approve sandbox-allow-btn" style="background:rgba(16,185,129,0.15); border:1px solid #10b981; color:#10b981; padding:5px 16px; border-radius:6px; cursor:pointer; font-weight:500;">✅ 允许访问</button>';
        permHtml += '<button class="acf-btn acf-deny sandbox-deny-btn" style="background:rgba(239,68,68,0.1); border:1px solid #ef4444; color:#ef4444; padding:5px 16px; border-radius:6px; cursor:pointer; font-weight:500;">❌ 拒绝 (结束此操作)</button>';
        permHtml += '</div></div>';
        actionsDiv.innerHTML = permHtml;

        // Allow → 重新执行 with force_allow
        actionsDiv.querySelector('.sandbox-allow-btn').onclick = async () => {
          actionsDiv.innerHTML = '<div class="acf-executing">\u23f3 已授权，正在重新执行...</div>';
          try {
            const r2 = await fetch(API + '/api/actions/execute', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ actions: actionsToExec, force_allow: true }),
            });
            const d2 = await r2.json();
            let html2 = '<div class="acf-result acf-result-ok">\u2705 授权后执行完成</div>';
            (d2.results || []).forEach(res => {
              const rr = res.result || {};
              if (rr.success) {
                html2 += '<div class="acf-result-item acf-result-success">\u2713 ' + esc(res.tool) + ': ' + esc(rr.message || '成功') + '</div>';
              } else {
                html2 += '<div class="acf-result-item acf-result-fail">\u2717 ' + esc(res.tool) + ': ' + esc(rr.error || '失败') + '</div>';
              }
            });
            actionsDiv.innerHTML = html2;
            if (d2.results && d2.results.some(r => r.result && r.result.success)) {
              setTimeout(() => loadFileTree(), 500);
            }
          } catch (e2) {
            actionsDiv.innerHTML = '<div class="acf-result acf-result-fail">\u26a0\ufe0f 执行失败: ' + esc(e2.message) + '</div>';
          }
        };

        // Deny → 结束此操作
        actionsDiv.querySelector('.sandbox-deny-btn').onclick = () => {
          actionsDiv.innerHTML = '<div class="acf-result acf-result-cancelled">\u274c 已拒绝 — AI 将停止此操作</div>';
          pendingActions = [];
        };
        return;
      }

      let resultHtml = '<div class="acf-result acf-result-ok">\u2705 执行完成</div>';
      (d.results || []).forEach((res) => {
        const rr = res.result || {};
        if (rr.success) {
          const m = rr.message || rr.stdout?.substring(0, 200) || '成功';
          resultHtml += '<div class="acf-result-item acf-result-success">\u2713 ' + esc(res.tool) + ': ' + esc(m) + '</div>';
        } else {
          resultHtml += '<div class="acf-result-item acf-result-fail">\u2717 ' + esc(res.tool) + ': ' + esc(rr.error || '失败') + '</div>';
        }
      });
      actionsDiv.innerHTML = resultHtml;

      // 刷新文件树（延迟确保文件写入完成）
      if (d.results && d.results.some(r => r.result && r.result.success)) {
        setTimeout(() => loadFileTree(), 500);
        if (wsCurrentFile) setTimeout(() => openFile(wsCurrentFile), 800);
      }
    } catch (e) {
      if (e.name === 'AbortError') {
        actionsDiv.innerHTML = '<div class="acf-result acf-result-cancelled">\u23f9 已中断执行</div>';
      } else {
        actionsDiv.innerHTML = '<div class="acf-result acf-result-fail">\u26a0\ufe0f 执行失败: ' + esc(e.message) + '</div>';
      }
    }
    pendingActions = [];
  };

  denyBtn.onclick = () => {
    actionsDiv.innerHTML = '<div class="acf-result acf-result-cancelled">\u274c 已取消</div>';
    pendingActions = [];
  };
}

// ============================================================
//  UI 热更新
// ============================================================
function applyUIPreferences(prefs) {
  const root = document.documentElement;
  if (!prefs) return;

  // 色调 — Cursor 主题统一使用翡翠绿，跳过 hue 覆盖
  // if (prefs.accent_hue !== undefined) {
  //   ... hue 覆盖已禁用，使用 CSS 默认品牌色
  // }

  // 直接指定 accent_color — 已禁用，统一使用翡翠绿
  // if (prefs.accent_color) {
  //   root.style.setProperty('--accent', prefs.accent_color);
  // }

  // 字号
  if (prefs.font_size) {
    root.style.setProperty('--base-font-size', prefs.font_size + 'px');
    document.querySelectorAll('.msg-content').forEach(el => {
      el.style.fontSize = prefs.font_size + 'px';
    });
  }

  // 主题
  if (prefs.theme === 'hacker') {
    // hacker 主题现在使用 Cursor 风格 — VS Code 灰 + 翡翠绿
    root.style.setProperty('--bg-0', '#1e1e1e');
    root.style.setProperty('--bg-1', '#1e1e1e');
    root.style.setProperty('--bg-2', '#252526');
    root.style.setProperty('--bg-3', '#2d2d30');
    root.style.setProperty('--accent', '#10b981');
    root.style.setProperty('--accent-hover', '#34d399');
    root.style.setProperty('--accent-muted', 'rgba(16,185,129,0.12)');
  } else if (prefs.theme === 'light') {
    root.style.setProperty('--bg-0', '#ffffff');
    root.style.setProperty('--bg-1', '#f8f9fa');
    root.style.setProperty('--bg-2', '#f0f1f3');
    root.style.setProperty('--bg-3', '#e8e9eb');
    root.style.setProperty('--text-1', '#1a1a1a');
    root.style.setProperty('--text-2', '#555');
    root.style.setProperty('--text-3', '#999');
    root.style.setProperty('--border', '#ddd');
    root.style.setProperty('--surface', '#fff');
  } else {
    // dark (default) — 使用 CSS 文件中的 Cursor 默认值
    root.style.setProperty('--bg-0', '#1e1e1e');
    root.style.setProperty('--bg-1', '#1e1e1e');
    root.style.setProperty('--bg-2', '#252526');
    root.style.setProperty('--bg-3', '#2d2d30');
    root.style.setProperty('--accent', '#10b981');
    root.style.setProperty('--accent-hover', '#34d399');
    root.style.setProperty('--accent-muted', 'rgba(16,185,129,0.12)');
  }
  // 无论哪个主题，都统一设置翡翠绿品牌色
  if (prefs.theme !== 'light') {
    root.style.setProperty('--text-1', '#cccccc');
    root.style.setProperty('--text-2', '#9d9d9d');
    root.style.setProperty('--text-3', '#6e6e6e');
    root.style.setProperty('--border', '#333333');
    root.style.setProperty('--surface', '#252526');
  }

  console.log('[UI] 偏好已热更新', prefs);
}

function hslToHex(h, s, l) {
  s /= 100; l /= 100;
  const a = s * Math.min(l, 1 - l);
  const f = n => {
    const k = (n + h / 30) % 12;
    const c = l - a * Math.max(Math.min(k - 3, 9 - k, 1), -1);
    return Math.round(255 * c).toString(16).padStart(2, '0');
  };
  return `#${f(0)}${f(8)}${f(4)}`;
}

// ============================================================
//  记忆状态指示器
// ============================================================
function updateMemoryStatus({ hotCount = 0, vectorCount = 0, sessionCount = 0 }) {
  const $indicator = document.getElementById('memoryStatus');
  if (!$indicator) return;

  $indicator.innerHTML = `
    <div class="mem-stat" title="L2 热窗口消息数">
      <span class="mem-icon">🔥</span>
      <span class="mem-val">${hotCount}</span>
    </div>
    <div class="mem-stat" title="L3 向量记忆条数">
      <span class="mem-icon">🧬</span>
      <span class="mem-val">${vectorCount}</span>
    </div>
    <div class="mem-stat" title="历史会话数">
      <span class="mem-icon">💬</span>
      <span class="mem-val">${sessionCount}</span>
    </div>
  `;
  $indicator.style.display = 'flex';
}

// ============================================================
//  Dashboard 统一更新
// ============================================================
function updateAllDashboards({ hotCount = 0, vectorCount = 0, sessionCount = 0, totalTokens = 0 }) {
  const MAX_TOKENS = 131072;

  // 侧边栏 Memory 面板
  const $memHot = document.getElementById('memHotVal');
  const $memVec = document.getElementById('memVecVal');
  const $memSess = document.getElementById('memSessVal');
  const $memBar = document.getElementById('memTokenBar');
  const $memLabel = document.getElementById('memTokenLabel');
  if ($memHot) $memHot.textContent = hotCount;
  if ($memVec) $memVec.textContent = vectorCount;
  if ($memSess) $memSess.textContent = sessionCount;
  if ($memBar) $memBar.style.width = Math.min(100, (totalTokens / MAX_TOKENS) * 100) + '%';
  if ($memLabel) $memLabel.textContent = `${totalTokens} / ${MAX_TOKENS}`;

  // 欢迎页记忆状态卡片
  const $wmv = document.getElementById('welcomeMemVal');
  const $wms = document.getElementById('welcomeMemSub');
  if ($wmv) $wmv.textContent = `${hotCount} 条热记忆`;
  if ($wms) $wms.textContent = `${sessionCount} 会话 · ${vectorCount} 向量`;

  // Context Bar（顶栏）
  updateContextBar({ totalTokens, hotCount, vectorCount });
}

function updateContextBar({ totalTokens = 0, hotCount = 0, vectorCount = 0, maxTokens = 0 }) {
  // Use model's actual context window, default to 4096 for Gemma
  const MAX_TOKENS = maxTokens || window._modelContextSize || 4096;
  const pct = Math.min(100, (totalTokens / MAX_TOKENS) * 100);

  const $ctxTokens = document.getElementById('ctxTokens');
  const $ctxBar = document.getElementById('ctxProgressBar');
  const $ctxHot = document.getElementById('ctxHot');
  const $ctxVec = document.getElementById('ctxVec');
  const $ctxWrap = document.querySelector('.ctx-progress-wrap');

  if ($ctxTokens) $ctxTokens.textContent = totalTokens;
  if ($ctxHot) $ctxHot.textContent = hotCount;
  if ($ctxVec) $ctxVec.textContent = vectorCount;

  if ($ctxBar) {
    $ctxBar.style.width = pct + '%';
    // Color zones: green (0-60%), yellow (60-85%), red (85%+)
    if (pct > 85) {
      $ctxBar.className = 'ctx-progress-bar danger';
    } else if (pct > 60) {
      $ctxBar.className = 'ctx-progress-bar warn';
    } else {
      $ctxBar.className = 'ctx-progress-bar';
    }
  }

  // Update the "/ N tok" label dynamically
  const $ctxMax = document.querySelector('.context-bar .ctx-stat span:last-child');
  if ($ctxMax && $ctxMax.textContent.includes('tok')) {
    $ctxMax.textContent = `/ ${MAX_TOKENS.toLocaleString()} tok`;
  }

  // Tooltip on progress bar
  if ($ctxWrap) {
    $ctxWrap.title = `${pct.toFixed(1)}% used (${totalTokens} / ${MAX_TOKENS.toLocaleString()} tokens)`;
  }
}

// ============================================================
//  侧边栏折叠
// ============================================================
function toggleSection(id) {
  const el = document.getElementById(id);
  if (el) el.classList.toggle('collapsed');
}

// ============================================================
//  Agent 活动时间线
// ============================================================
function renderAgentTimeline(stats) {
  // 删除旧的时间线
  const old = document.querySelector('.agent-timeline');
  if (old) old.remove();

  const tl = document.createElement('div');
  tl.className = 'agent-timeline';

  const items = [
    { icon: '✅', cls: 'tl-done', agent: 'CEO', text: '用户意图分析完成' },
    { icon: '✅', cls: 'tl-done', agent: 'Memory', text: `L2 热窗口: ${stats.hotCount || 0} 条` },
  ];
  if (stats.vectorCount > 0) {
    items.push({ icon: '🧬', cls: 'tl-info', agent: 'L3', text: `召回 ${stats.vectorCount} 条向量记忆` });
  }
  items.push(
    { icon: '✅', cls: 'tl-done', agent: 'LLM', text: `回复生成 (${stats.totalTokens || '?'} tokens)` },
  );

  tl.innerHTML = `
    <div class="agent-timeline-title">
      <span class="pulse-dot"></span>
      Agent 活动流
    </div>
    ${items.map(i => `
      <div class="tl-item ${i.cls}">
        <span class="tl-icon">${i.icon}</span>
        <span class="tl-agent">${i.agent}</span>
        <span class="tl-text">${i.text}</span>
      </div>
    `).join('')}
  `;

  // 插入到最后一条消息后面
  const lastMsg = $msg.querySelector('.msg:last-of-type');
  if (lastMsg) {
    lastMsg.after(tl);
    $wrap.scrollTop = $wrap.scrollHeight;
  }
}


// ============================================================
//  欢迎页粒子背景
// ============================================================
function initWelcomeParticles() {
  const canvas = document.getElementById('welcomeParticles');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  function resize() {
    const rect = canvas.parentElement.getBoundingClientRect();
    canvas.width = rect.width;
    canvas.height = rect.height;
  }
  resize();
  window.addEventListener('resize', resize);

  const particles = [];
  const COUNT = 40;
  const CONNECT_DIST = 120;

  // 读取当前主题的粒子颜色
  function getThemeColors() {
    const style = getComputedStyle(document.documentElement);
    return {
      c1: style.getPropertyValue('--particle-color-1').trim() || 'rgba(16,185,129,0.6)',
      c2: style.getPropertyValue('--particle-color-2').trim() || 'rgba(6,182,212,0.6)',
    };
  }

  function createParticle(x, y, opts = {}) {
    const colors = getThemeColors();
    return {
      x: x ?? Math.random() * canvas.width,
      y: y ?? Math.random() * canvas.height,
      vx: opts.vx ?? (Math.random() - 0.5) * 0.5,
      vy: opts.vy ?? (Math.random() - 0.5) * 0.5,
      r: opts.r ?? Math.random() * 2 + 1,
      color: Math.random() > 0.5 ? colors.c1 : colors.c2,
      life: opts.life ?? Infinity,  // 无限寿命 = 常驻粒子
      maxLife: opts.life ?? Infinity,
    };
  }

  for (let i = 0; i < COUNT; i++) {
    particles.push(createParticle());
  }

  // 🎆 点击爆发粒子
  canvas.style.pointerEvents = 'auto';
  canvas.addEventListener('click', (e) => {
    const rect = canvas.getBoundingClientRect();
    const cx = e.clientX - rect.left;
    const cy = e.clientY - rect.top;
    const BURST = 8;
    for (let i = 0; i < BURST; i++) {
      const angle = (Math.PI * 2 / BURST) * i + Math.random() * 0.5;
      const speed = 1.5 + Math.random() * 2;
      particles.push(createParticle(cx, cy, {
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed,
        r: 1.5 + Math.random() * 2.5,
        life: 80 + Math.random() * 40,  // 80-120 帧后消失
      }));
    }
  });

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // 移除已消亡的粒子（保留常驻粒子）
    for (let i = particles.length - 1; i >= 0; i--) {
      if (particles[i].life <= 0) particles.splice(i, 1);
    }

    // 获取当前主题的连线颜色基调
    const isDark = !document.documentElement.dataset.theme || document.documentElement.dataset.theme === 'dark' || document.documentElement.dataset.theme === 'black';
    const lineBase = isDark ? '16,185,129' : '5,150,105';

    // 连线
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < CONNECT_DIST) {
          const alpha = (1 - dist / CONNECT_DIST) * 0.3;
          ctx.strokeStyle = `rgba(${lineBase},${alpha})`;
          ctx.lineWidth = 0.5;
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.stroke();
        }
      }
    }

    // 粒子
    for (const p of particles) {
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < 0 || p.x > canvas.width) p.vx *= -1;
      if (p.y < 0 || p.y > canvas.height) p.vy *= -1;

      // 短命粒子逐渐消失
      let opacity = 1;
      if (p.life !== Infinity) {
        p.life--;
        opacity = Math.max(0, p.life / p.maxLife);
        p.vx *= 0.98;  // 减速
        p.vy *= 0.98;
      }

      ctx.globalAlpha = opacity;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = p.color;
      ctx.fill();

      // 短命粒子带发光
      if (p.life !== Infinity && opacity > 0.3) {
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r * 3, 0, Math.PI * 2);
        ctx.fillStyle = p.color.replace(/[\d.]+\)$/, (opacity * 0.15).toFixed(2) + ')');
        ctx.fill();
      }
      ctx.globalAlpha = 1;
    }

    requestAnimationFrame(draw);
  }
  draw();
}

// ============================================================
//  主题切换
// ============================================================
const THEMES = ['light', 'dark', 'black'];
const THEME_ICONS = { light: '☀️', dark: '🌙', black: '🖤' };

function setTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('lmd_theme', theme);
  const btn = document.getElementById('tbThemeToggle');
  if (btn) btn.title = `当前: ${theme === 'dark' ? '暗色' : theme === 'light' ? '白色' : '纯黑'} (点击切换)`;
}

function cycleTheme() {
  const current = document.documentElement.getAttribute('data-theme') || 'light';
  const idx = THEMES.indexOf(current);
  const next = THEMES[(idx + 1) % THEMES.length];
  setTheme(next);
}

// 在 DOMContentLoaded 后初始化
document.addEventListener('DOMContentLoaded', () => {
  // 恢复主题
  const saved = localStorage.getItem('lmd_theme');
  if (saved && THEMES.includes(saved)) setTheme(saved);
  else setTheme('light');  // 默认白色主题

  // 主题切换按钮
  const themeBtn = document.getElementById('tbThemeToggle');
  if (themeBtn) themeBtn.addEventListener('click', cycleTheme);

  // 粒子系统
  setTimeout(initWelcomeParticles, 200);
});

