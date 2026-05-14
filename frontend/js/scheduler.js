// ============================================================
//  LocalMindDesk — 定时任务管理模块
// ============================================================

// ============================================================
//  定时任务管理
// ============================================================
async function loadSchedules() {
  try {
    const res = await fetch(`${API}/api/schedules`);
    const data = await res.json();
    renderScheduleList(data.tasks || []);
    renderScheduleTemplates(data.templates || []);
    loadScheduleLog();
  } catch (e) {
    const el = document.getElementById('scheduleList');
    if (el) el.innerHTML = '<div class="skill-empty">加载失败</div>';
  }
}

function renderScheduleList(tasks) {
  const el = document.getElementById('scheduleList');
  if (!el) return;
  if (!tasks.length) {
    el.innerHTML = '<div class="skill-empty">暂无定时任务，点击下方按钮新建或从模板添加</div>';
    return;
  }
  el.innerHTML = tasks.map(t => {
    const safetyBadge = t.safety === 'safe'
      ? '<span style="color:#4ecdc4;font-size:0.75rem">🟢 安全</span>'
      : '<span style="color:#ffa726;font-size:0.75rem">🟡 敏感</span>';
    const statusDot = t.enabled ? '🟢' : '⚪';
    const actionIcons = {send_wechat: '💬', reminder: '📢', terminal: '💻'};
    const actionIcon = actionIcons[t.action] || '⚡';
    return `
      <div class="integration-card" style="margin-bottom:10px">
        <div class="integration-info">
          <div class="integration-header">
            <span style="font-size:1.4rem">${actionIcon}</span>
            <div>
              <div class="integration-name">${statusDot} ${t.name}</div>
              <div class="integration-desc">
                🕐 ${t.cron_description} · ${safetyBadge} · 已执行 ${t.run_count} 次
                ${t.last_run ? ' · 上次: ' + new Date(t.last_run).toLocaleString() : ''}
              </div>
            </div>
          </div>
          <div class="integration-actions" style="margin-top:8px">
            <button class="btn-outline btn-sm" onclick="toggleSchedule('${t.id}')">
              ${t.enabled ? '⏸ 暂停' : '▶ 启用'}
            </button>
            <button class="btn-outline btn-sm" onclick="runScheduleNow('${t.id}')">⚡ 立即执行</button>
            <button class="btn-outline btn-sm" onclick="deleteSchedule('${t.id}')" style="color:#ef5350">🗑 删除</button>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

function renderScheduleTemplates(templates) {
  const el = document.getElementById('scheduleTemplates');
  if (!el) return;
  el.innerHTML = templates.map(t => `
    <button class="btn-outline btn-sm" style="margin:4px" onclick='addFromTemplate(${JSON.stringify(t).replace(/'/g, "&#39;")})'>
      ${t.name}
    </button>
  `).join('');
}

function showAddScheduleForm() {
  const el = document.getElementById('scheduleFormSection');
  if (el) el.style.display = 'block';
}

function hideAddScheduleForm() {
  const el = document.getElementById('scheduleFormSection');
  if (el) el.style.display = 'none';
}

async function createSchedule() {
  const name = document.getElementById('schedName')?.value?.trim();
  const cron = document.getElementById('schedCron')?.value?.trim();
  const action = document.getElementById('schedAction')?.value;
  const user = document.getElementById('schedUser')?.value?.trim();
  const message = document.getElementById('schedMessage')?.value?.trim();

  if (!name) return alert('请输入任务名称');
  if (!cron) return alert('请输入 cron 表达式');

  const params = action === 'terminal'
    ? {cmd: message}
    : {user: user || '文件传输助手', message: message};

  try {
    const res = await fetch(`${API}/api/schedules`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name, cron, action, params})
    });
    const data = await res.json();
    if (data.success) {
      hideAddScheduleForm();
      loadSchedules();
      addSystemMessage(`✅ 定时任务「${name}」已创建！\n\n🕐 触发时间: \`${cron}\`\n📌 动作: ${action}`);
    } else {
      alert(data.error || '创建失败');
    }
  } catch (e) {
    alert('创建失败: ' + e.message);
  }
}

async function addFromTemplate(tpl) {
  try {
    const res = await fetch(`${API}/api/schedules`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(tpl)
    });
    const data = await res.json();
    if (data.success) {
      loadSchedules();
      addSystemMessage(`✅ 已添加预设任务「${tpl.name}」`);
    }
  } catch (e) {
    alert('添加失败');
  }
}

async function toggleSchedule(id) {
  try {
    await fetch(`${API}/api/schedules/${id}/toggle`, {method: 'POST'});
    loadSchedules();
  } catch (e) {}
}

async function deleteSchedule(id) {
  if (!confirm('确定删除这个定时任务？')) return;
  try {
    await fetch(`${API}/api/schedules/${id}`, {method: 'DELETE'});
    loadSchedules();
  } catch (e) {}
}

async function runScheduleNow(id) {
  try {
    const res = await fetch(`${API}/api/schedules/${id}/run-now`, {method: 'POST'});
    const data = await res.json();
    addSystemMessage(
      data.success
        ? `⚡ 任务已执行: ${data.output || '完成'}`
        : `⚠️ 执行失败: ${data.output || data.error || '未知错误'}`
    );
    loadSchedules();
  } catch (e) {
    alert('执行失败');
  }
}

async function loadScheduleLog() {
  try {
    const res = await fetch(`${API}/api/schedules/log`);
    const data = await res.json();
    const el = document.getElementById('scheduleLog');
    if (!el) return;
    const logs = data.log || [];
    if (!logs.length) {
      el.innerHTML = '<div class="skill-empty" style="font-size:0.82rem">暂无执行记录</div>';
      return;
    }
    el.innerHTML = logs.slice(-10).reverse().map(l => `
      <div style="padding:4px 0;border-bottom:1px solid var(--border);display:flex;justify-content:space-between">
        <span>${l.success ? '✅' : '❌'} ${l.task_name}</span>
        <span style="opacity:0.5">${new Date(l.time).toLocaleString()}</span>
      </div>
    `).join('');
  } catch (e) {}
}


// ---- 全局暴露（兼容 onclick 调用）----
window.toggleSchedule = toggleSchedule;
window.deleteSchedule = deleteSchedule;
window.runScheduleNow = runScheduleNow;
window.addFromTemplate = addFromTemplate;
