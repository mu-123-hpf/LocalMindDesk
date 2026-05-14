// ============================================================
//  LocalMindDesk — 桌宠 UI 交互
// ============================================================

// ============================================================
//  🐾 桌宠 UI 交互
// ============================================================
function initPetWidget() {
  const canvas = document.getElementById('petCanvas');
  const widget = document.getElementById('petWidget');
  if (!canvas || !widget || !window.petManager) {
    console.warn('[Pet] 宠物引擎未加载 (canvas:', !!canvas, 'widget:', !!widget, 'petManager:', !!window.petManager, ')');
    return;
  }

  // 初始化宠物管理器
  window.petManager.init(canvas, widget);

  // 更新活动栏按钮状态
  const petToggle = document.getElementById('petToggleBtn');
  if (petToggle && window.petManager.petEnabled) {
    petToggle.classList.add('pet-active');
  }

  // 活动栏按钮：切换宠物显示
  petToggle?.addEventListener('click', () => {
    const pm = window.petManager;
    pm.setEnabled(!pm.petEnabled);
    petToggle.classList.toggle('pet-active', pm.petEnabled);
  });

  // Canvas 点击交互
  canvas.addEventListener('click', () => {
    window.dispatchEvent(new CustomEvent('LocalMindDesk:pet', { detail: { action: 'user-click' } }));
  });

  // 宠物菜单
  const menuBtn = document.getElementById('petMenuBtn');
  const menu = document.getElementById('petMenu');
  menuBtn?.addEventListener('click', (e) => {
    e.stopPropagation();
    menu?.classList.toggle('show');
  });
  document.addEventListener('click', () => menu?.classList.remove('show'));

  // 菜单项：释放到桌面 / 回到应用内
  document.getElementById('petDesktopToggle')?.addEventListener('click', () => {
    window.petManager.toggleDesktopMode();
    menu?.classList.remove('show');
    const label = document.querySelector('#petDesktopToggle span:last-child');
    if (label) {
      label.textContent = window.petManager.displayMode === 'desktop' ? '回到应用内' : '释放到桌面';
    }
  });

  // 菜单项：隐藏宠物
  document.getElementById('petHideBtn')?.addEventListener('click', () => {
    window.petManager.setEnabled(false);
    petToggle?.classList.remove('pet-active');
    menu?.classList.remove('show');
  });

  // 菜单项：桌宠设置
  document.getElementById('petSettingsBtn')?.addEventListener('click', () => {
    menu?.classList.remove('show');
    document.getElementById('settingsPanel').style.display = 'block';
    document.querySelectorAll('.stab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(p => p.classList.remove('active'));
    document.querySelector('[data-tab="tabPet"]')?.classList.add('active');
    document.getElementById('tabPet')?.classList.add('active');
  });

  // 菜单项：切换宠物（打开设置面板宠物选择）
  document.getElementById('petChangeBtn')?.addEventListener('click', () => {
    document.getElementById('petSettingsBtn')?.click();
  });

  // Electron: 监听桌面窗口关闭事件
  if (window.electronAPI?.onPetDesktopClosed) {
    window.electronAPI.onPetDesktopClosed(() => {
      window.petManager.displayMode = 'inapp';
      window.petManager._showWidget();
      window.petManager.start();
      const label = document.querySelector('#petDesktopToggle span:last-child');
      if (label) label.textContent = '释放到桌面';
    });
  }

  // ---- 设置面板桌宠标签页 ----
  const petEnabledToggle = document.getElementById('petEnabledToggle');
  const petSizeRange = document.getElementById('petSizeRange');
  const petReactToggle = document.getElementById('petReactToggle');
  const petSizeVal = document.getElementById('petSizeVal');

  if (petEnabledToggle) {
    petEnabledToggle.checked = window.petManager.petEnabled;
    petEnabledToggle.addEventListener('change', () => {
      window.petManager.setEnabled(petEnabledToggle.checked);
      petToggle?.classList.toggle('pet-active', petEnabledToggle.checked);
      document.getElementById('petEnabledLabel').textContent = petEnabledToggle.checked ? '已启用' : '已禁用';
    });
  }

  if (petSizeRange) {
    petSizeRange.value = window.petManager.petSize;
    petSizeVal.textContent = window.petManager.petSize;
    petSizeRange.addEventListener('input', () => {
      petSizeVal.textContent = petSizeRange.value;
      window.petManager.setSize(parseInt(petSizeRange.value));
    });
  }

  if (petReactToggle) {
    petReactToggle.checked = window.petManager.reactToAI;
    petReactToggle.addEventListener('change', () => {
      window.petManager.setReactToAI(petReactToggle.checked);
    });
  }

  // ---- 社区宠物导入 ----
  document.getElementById('petImportBtn')?.addEventListener('click', async () => {
    const input = document.getElementById('petImportUrl');
    const status = document.getElementById('petImportStatus');
    const petSlug = input?.value.trim();
    if (!petSlug) {
      status.textContent = '⚠️ 请输入宠物 ID';
      return;
    }

    status.textContent = '⏳ 正在导入...';
    try {
      // 从 awesome-codex-pet 下载 pet.json 和 spritesheet.webp
      const baseUrl = `https://raw.githubusercontent.com/legeling/awesome-codex-pet/main/pets/${petSlug}`;

      const petJsonResp = await fetch(`${baseUrl}/pet.json`);
      if (!petJsonResp.ok) throw new Error('找不到该宠物的 pet.json');
      const petJson = await petJsonResp.json();

      const sheetResp = await fetch(`${baseUrl}/spritesheet.webp`);
      if (!sheetResp.ok) throw new Error('找不到该宠物的 spritesheet.webp');
      const sheetBlob = await sheetResp.blob();
      const sheetBuffer = await sheetBlob.arrayBuffer();

      if (window.electronAPI?.savePetAsset) {
        // Electron 环境：保存到文件系统
        const petJsonStr = JSON.stringify(petJson, null, 2);
        await window.electronAPI.savePetAsset(petSlug, 'pet.json', new TextEncoder().encode(petJsonStr));
        await window.electronAPI.savePetAsset(petSlug, 'spritesheet.webp', new Uint8Array(sheetBuffer));
      }

      status.innerHTML = `✅ 成功导入 <strong>${petJson.displayName || petSlug}</strong>`;
      input.value = '';

      // 刷新宠物网格
      refreshPetGrid();
    } catch (err) {
      status.textContent = `❌ 导入失败: ${err.message}`;
    }
  });

  console.log('[Pet] 桌宠 UI 已初始化');
}

async function refreshPetGrid() {
  const grid = document.getElementById('petGrid');
  if (!grid) return;

  let pets = [{ id: 'default', name: 'LocalMindDesk', description: 'LocalMindDesk AI 助手吉祥物' }];
  if (window.electronAPI?.listPets) {
    try {
      pets = await window.electronAPI.listPets();
    } catch {}
  }

  grid.innerHTML = '';
  for (const pet of pets) {
    const item = document.createElement('div');
    item.className = 'pet-grid-item' + (pet.id === window.petManager.currentPetId ? ' selected' : '');
    item.dataset.petId = pet.id;
    item.innerHTML = `
      <div style="font-size:48px">🐾</div>
      <span class="pet-grid-name">${pet.name}</span>
    `;
    item.addEventListener('click', async () => {
      grid.querySelectorAll('.pet-grid-item').forEach(i => i.classList.remove('selected'));
      item.classList.add('selected');
      try {
        await window.petManager.loadPet(pet.id);
        window.petManager.start();
      } catch (err) {
        console.error('[Pet] 切换宠物失败:', err);
      }
    });
    grid.appendChild(item);
  }
}

