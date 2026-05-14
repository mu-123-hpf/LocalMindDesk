// ============================================================
//  LocalMindDesk — 桌宠引擎 v3
//  精灵图帧动画 · Canvas 渲染 · 自动帧检测 · 状态机 · localStorage
//  完全兼容 community-pet-assets 格式
// ============================================================

class PetStateMachine {
  constructor(stateMap) {
    // stateMap: { idle: {row,frames,loop}, walk: {row,frames,loop}, ... }
    this.stateMap = stateMap || { idle: { row: 0, frames: 1, loop: true } };
    this.current = 'idle';
    this.previous = 'idle';
    this.stateTime = 0;
    this.listeners = [];
  }

  get config() {
    return this.stateMap[this.current] || this.stateMap.idle || { row: 0, frames: 1, loop: true };
  }

  transition(state, force = false) {
    if (!this.stateMap[state]) state = 'idle';
    if (this.current === state && !force) return;
    this.previous = this.current;
    this.current = state;
    this.stateTime = 0;
    this.listeners.forEach(fn => fn(state, this.previous));
  }

  update(dt) {
    this.stateTime += dt;
    const cfg = this.config;
    if (!cfg.loop) {
      const dur = (cfg.frames / 6) * 1000; // ~6fps for non-loop
      if (this.stateTime >= dur) this.transition('idle');
    }
  }

  onChange(fn) { this.listeners.push(fn); }
}

class PetBehaviorEngine {
  constructor(sm) {
    this.sm = sm;
    this.timer = 0;
    this.nextAction = 8000 + Math.random() * 15000;
    this.enabled = true;
  }

  update(dt) {
    if (!this.enabled) return;
    this.timer += dt;
    if (this.sm.current === 'idle' && this.timer >= this.nextAction) {
      this.timer = 0;
      this.nextAction = 8000 + Math.random() * 15000;
      const pool = ['walk', 'sit', 'idle', 'idle'];
      this.sm.transition(pool[Math.floor(Math.random() * pool.length)]);
    }
  }
}

class PetManager {
  constructor() {
    this.spritesheet = null; // HTMLImageElement
    this.petConfig = null;
    this.stateMachine = null;
    this.behavior = null;

    this.canvas = null;
    this.ctx = null;
    this.widgetEl = null;

    // 帧参数
    this.frameW = 192;
    this.frameH = 208;
    this.cols = 8;
    this.rows = 9;
    this.fps = 6;
    this.currentFrame = 0;
    this.elapsed = 0;
    this.flipX = false;

    // 控制
    this.loaded = false;
    this.running = false;
    this.lastTime = 0;
    this.animId = null;

    // 设置
    this.petSize = 128;
    this.currentPetId = 'default'; // 默认宠物
    this.petEnabled = true;
    this.reactToAI = true;
    this.displayMode = 'inapp';

    this._restoreState();

    window.addEventListener('LocalMindDesk:pet', (e) => this._onAIEvent(e.detail));
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) this._pause();
      else if (this.petEnabled && this.loaded) this._resume();
    });
  }

  async init(canvas, widgetEl) {
    this.canvas = canvas;
    this.widgetEl = widgetEl;
    this.ctx = canvas.getContext('2d');

    // 强制回到应用内模式（防止上次桌面模式卡死）
    this.displayMode = 'inapp';

    if (!this.petEnabled) {
      console.log('[Pet] 桌宠已禁用');
      this._hideWidget();
      return;
    }

    console.log(`[Pet] 开始加载宠物: ${this.currentPetId}`);
    try {
      await this.loadPet(this.currentPetId);
      this.start();
    } catch (e) {
      console.warn('[Pet] 加载失败:', e.message, '尝试 fallback 到 default');
      try {
        await this.loadPet('default');
        this.start();
      } catch (e2) {
        console.error('[Pet] default 也加载失败:', e2.message);
      }
    }
  }

  async loadPet(petId) {
    // 智能路径：file:// 协议用相对路径，http:// 用绝对路径
    const isFileProtocol = window.location.protocol === 'file:';
    const basePath = isFileProtocol
      ? `assets/pets/${petId}`
      : `/assets/pets/${petId}`;
    const resp = await fetch(`${basePath}/pet.json`);
    if (!resp.ok) throw new Error(`pet.json 不存在: ${petId}`);
    this.petConfig = await resp.json();

    const sheetFile = this.petConfig.spritesheetPath || 'spritesheet.webp';
    this.spritesheet = await this._loadImg(`${basePath}/${sheetFile}`);

    // 自动检测帧尺寸
    this._detectFrameLayout();

    // 构建状态映射
    const stateMap = this._buildStateMap();
    this.stateMachine = new PetStateMachine(stateMap);
    this.stateMachine.onChange(() => { this.currentFrame = 0; this.elapsed = 0; this._showTooltip(); });

    this.behavior = new PetBehaviorEngine(this.stateMachine);

    // 设置 canvas 分辨率（CSS 控制显示大小）
    this.canvas.width = this.frameW;
    this.canvas.height = this.frameH;
    this.ctx = this.canvas.getContext('2d');
    this.ctx.imageSmoothingEnabled = false;

    this.currentPetId = petId;
    this.loaded = true;
    this._applySize();
    this._showWidget();
    this._saveState();
    console.log(`[Pet] 已加载: ${this.petConfig.displayName || petId} (${this.cols}×${this.rows} 帧, ${this.frameW}×${this.frameH}px)`);
  }

  _loadImg(src) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error(`图片加载失败: ${src}`));
      img.src = src;
    });
  }

  /**
   * 自动检测精灵图帧布局
   * 精灵图标准: 精灵图由等宽等高的帧组成网格
   */
  _detectFrameLayout() {
    const img = this.spritesheet;
    if (this.petConfig.frameWidth && this.petConfig.frameHeight) {
      this.frameW = this.petConfig.frameWidth;
      this.frameH = this.petConfig.frameHeight;
    } else {
      // 列数检测：尝试 4-8 列，取整除且帧宽≥64的
      for (let c = 8; c >= 4; c--) {
        const fw = img.width / c;
        if (fw === Math.floor(fw) && fw >= 64) {
          this.frameW = fw;
          break;
        }
      }
      // 行数检测：找到宽高比最接近 1:1 的整除行数
      let bestRow = 0, bestRatio = Infinity;
      for (let r = 4; r <= 12; r++) {
        const fh = img.height / r;
        if (fh !== Math.floor(fh)) continue;
        const ratio = fh / this.frameW;
        if (ratio < 0.7 || ratio > 1.6) continue;
        const diff = Math.abs(ratio - 1.0);
        if (diff < bestRatio) {
          bestRatio = diff;
          bestRow = r;
        }
      }
      this.frameH = bestRow > 0 ? img.height / bestRow : this.frameW;
    }
    this.cols = Math.floor(img.width / this.frameW);
    this.rows = Math.floor(img.height / this.frameH);
    this.fps = this.petConfig.fps || 6;
  }

  /**
   * 构建状态 → 行映射
   * 如果 pet.json 有 states 字段就用它，否则按行自动分配
   */
  _buildStateMap() {
    if (this.petConfig.states) return this.petConfig.states;

    // 自动分配：每行扫描实际帧数（检测空帧）
    const defaultNames = ['idle', 'walk', 'run', 'sit', 'sleep', 'attack', 'excited', 'confused', 'typing'];
    const map = {};
    for (let r = 0; r < this.rows; r++) {
      const name = defaultNames[r] || `action_${r}`;
      const framesInRow = this._countFramesInRow(r);
      if (framesInRow > 0) {
        map[name] = { row: r, frames: framesInRow, loop: r < 5 };
      }
    }
    return map;
  }

  /**
   * 统计某行实际有多少非空帧
   */
  _countFramesInRow(row) {
    // 使用临时 canvas 检测每帧是否有内容
    const tmpCanvas = document.createElement('canvas');
    tmpCanvas.width = this.frameW;
    tmpCanvas.height = this.frameH;
    const tmpCtx = tmpCanvas.getContext('2d');

    let count = 0;
    for (let c = 0; c < this.cols; c++) {
      tmpCtx.clearRect(0, 0, this.frameW, this.frameH);
      tmpCtx.drawImage(this.spritesheet,
        c * this.frameW, row * this.frameH, this.frameW, this.frameH,
        0, 0, this.frameW, this.frameH
      );
      const data = tmpCtx.getImageData(0, 0, this.frameW, this.frameH).data;
      // 检查是否有非透明像素
      let hasContent = false;
      for (let i = 3; i < data.length; i += 16) { // 采样检测，每4个像素查一个
        if (data[i] > 10) { hasContent = true; break; }
      }
      if (hasContent) count++;
      else break; // 遇到空帧就停
    }
    return count;
  }

  // ---- 动画循环 ----
  start() {
    if (this.running || !this.loaded) return;
    this.running = true;
    this.lastTime = performance.now();
    this._loop();
  }

  stop() {
    this.running = false;
    if (this.animId) { cancelAnimationFrame(this.animId); this.animId = null; }
  }

  _pause() { if (this.running) this.stop(); }
  _resume() { if (this.loaded && this.petEnabled && !this.running) this.start(); }

  _loop() {
    if (!this.running) return;
    const now = performance.now();
    const dt = now - this.lastTime;
    this.lastTime = now;

    // 更新逻辑
    this.stateMachine.update(dt);
    this.behavior.update(dt);

    // 更新帧
    this.elapsed += dt;
    const interval = 1000 / this.fps;
    if (this.elapsed >= interval) {
      this.elapsed -= interval;
      const cfg = this.stateMachine.config;
      this.currentFrame++;
      if (this.currentFrame >= cfg.frames) {
        this.currentFrame = cfg.loop ? 0 : cfg.frames - 1;
      }
    }

    // 渲染
    this._render();

    this.animId = requestAnimationFrame(() => this._loop());
  }

  _render() {
    const ctx = this.ctx;
    const cfg = this.stateMachine.config;
    const fw = this.frameW;
    const fh = this.frameH;

    ctx.clearRect(0, 0, fw, fh);
    ctx.save();

    if (this.flipX) {
      ctx.translate(fw, 0);
      ctx.scale(-1, 1);
    }

    const sx = this.currentFrame * fw;
    const sy = cfg.row * fh;
    ctx.drawImage(this.spritesheet, sx, sy, fw, fh, 0, 0, fw, fh);
    ctx.restore();
  }

  // ---- AI 事件 ----
  _onAIEvent(detail) {
    if (!this.reactToAI || !this.loaded) return;
    const map = {
      'ai-thinking': 'typing',
      'ai-done': 'excited',
      'ai-error': 'confused',
      'user-click': null, // 随机
    };
    let target = map[detail.action];
    if (detail.action === 'user-click') {
      const opts = Object.keys(this.stateMachine.stateMap).filter(s => s !== 'idle');
      target = opts.length ? opts[Math.floor(Math.random() * opts.length)] : 'idle';
    }
    if (target) this.stateMachine.transition(target);
  }

  // ---- UI 控制 ----
  _showWidget() { this.widgetEl?.classList.add('visible'); }
  _hideWidget() { this.widgetEl?.classList.remove('visible'); }

  _applySize() {
    if (this.canvas) {
      this.canvas.style.width = this.petSize + 'px';
      this.canvas.style.height = (this.petSize * this.frameH / this.frameW) + 'px';
    }
  }

  _showTooltip() {
    const el = document.getElementById('petTooltip');
    if (!el) return;
    const labels = {
      idle: '💤 发呆中...', walk: '🚶 散步中~', run: '🏃 跑步！',
      sit: '🪑 坐着休息', sleep: '😴 睡着了...', excited: '🎉 好开心！',
      attack: '⚔️ 出招！', typing: '⌨️ 思考中...', confused: '😵 困惑',
    };
    el.textContent = labels[this.stateMachine.current] || this.stateMachine.current;
    el.classList.add('show');
    clearTimeout(this._tipTimer);
    this._tipTimer = setTimeout(() => el.classList.remove('show'), 2500);
  }

  setEnabled(en) {
    this.petEnabled = en;
    if (en && !this.loaded) this.loadPet(this.currentPetId).then(() => this.start());
    else if (en) { this._showWidget(); this.start(); }
    else { this._hideWidget(); this.stop(); }
    this._saveState();
  }

  setSize(s) {
    this.petSize = Math.max(64, Math.min(256, s));
    this._applySize();
    this._saveState();
  }

  setReactToAI(en) { this.reactToAI = en; this._saveState(); }

  // ---- 混合模式 ----
  toggleDesktopMode() {
    if (this.displayMode === 'inapp') {
      this.displayMode = 'desktop';
      if (window.electronAPI?.createPetWindow) {
        window.electronAPI.createPetWindow({ petId: this.currentPetId, size: this.petSize });
        this._hideWidget(); this.stop();
      } else { this.displayMode = 'inapp'; }
    } else {
      this.displayMode = 'inapp';
      if (window.electronAPI?.closePetWindow) window.electronAPI.closePetWindow();
      this._showWidget(); this.start();
    }
    this._saveState();
  }

  // ---- localStorage ----
  _saveState() {
    try {
      localStorage.setItem('lmd_pet_state', JSON.stringify({
        petEnabled: this.petEnabled, currentPetId: this.currentPetId,
        petSize: this.petSize, reactToAI: this.reactToAI,
        displayMode: this.displayMode, timestamp: Date.now(),
      }));
    } catch {}
  }

  _restoreState() {
    try {
      const raw = localStorage.getItem('lmd_pet_state');
      if (!raw) return;
      const s = JSON.parse(raw);
      if (s.timestamp && Date.now() - s.timestamp < 72 * 3600000) {
        this.petEnabled = s.petEnabled ?? true;
        this.currentPetId = s.currentPetId || 'default';
        this.petSize = s.petSize || 128;
        this.reactToAI = s.reactToAI ?? true;
        this.displayMode = s.displayMode || 'inapp';
      }
    } catch {}
  }

  async getInstalledPets() {
    if (window.electronAPI?.listPets) return await window.electronAPI.listPets();
    return [{ id: 'default', name: 'Default', description: 'LocalMindDesk mascot' }];
  }
}

window.petManager = new PetManager();
