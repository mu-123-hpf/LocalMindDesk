/**
 * LocalMindDesk — Python 后端进程管理
 * 启动 / 监控 / 停止 FastAPI 后端
 */
const { spawn } = require('child_process');
const path = require('path');
const http = require('http');

class PythonBridge {
  constructor({ port = 8000, projectDir, isDev = false }) {
    this.port = port;
    this.projectDir = projectDir;
    this.isDev = isDev;
    this.process = null;
    this.status = 'stopped'; // stopped | starting | running | error
  }

  /**
   * 启动 Python FastAPI 后端
   */
  async start() {
    if (this.process) return;
    this.status = 'starting';

    let cmd, args, cwd;

    // 打包模式: 使用 PyInstaller 打包后的 exe
    const isPackaged = require('electron').app.isPackaged;
    if (isPackaged) {
      const backendDir = path.join(process.resourcesPath, 'python-backend');
      cmd = path.join(backendDir, 'localminddesk-backend.exe');
      args = [];
      cwd = backendDir;
      console.log(`[PythonBridge] 打包模式, 使用: ${cmd}`);
    } else {
      // 开发模式: 使用 Python 解释器
      cmd = await this._findPython();
      args = ['-m', 'app.main'];
      cwd = this.projectDir;
      console.log(`[PythonBridge] 开发模式, 使用 Python: ${cmd}`);
    }

    this.process = spawn(cmd, args, {
      cwd: cwd,
      env: {
        ...process.env,
        PYTHONIOENCODING: 'utf-8',
        PYTHONUNBUFFERED: '1',
      },
      stdio: ['ignore', 'pipe', 'pipe'],
      ...(process.platform === 'win32' ? { shell: false } : {}),
    });

    // 捕获输出
    this.process.stdout.on('data', (data) => {
      const msg = data.toString().trim();
      if (msg) console.log(`[Python] ${msg}`);
    });

    this.process.stderr.on('data', (data) => {
      const msg = data.toString().trim();
      if (msg) console.error(`[Python:ERR] ${msg}`);
    });

    this.process.on('exit', (code) => {
      console.log(`[PythonBridge] Python 进程退出, code=${code}`);
      this.process = null;
      this.status = code === 0 ? 'stopped' : 'error';
    });

    this.process.on('error', (err) => {
      console.error(`[PythonBridge] Python 启动失败:`, err.message);
      this.status = 'error';
    });

    // 等待后端就绪
    await this._waitForReady(30000);  // 最多等 30 秒
    this.status = 'running';
    console.log(`[PythonBridge] 后端已就绪 http://localhost:${this.port}`);
  }

  /**
   * 停止 Python 后端
   */
  async stop() {
    if (!this.process) return;
    console.log('[PythonBridge] 正在停止 Python 后端...');

    return new Promise((resolve) => {
      const timeout = setTimeout(() => {
        // 超时强制终止
        console.warn('[PythonBridge] 强制终止 Python 进程');
        try {
          if (process.platform === 'win32') {
            spawn('taskkill', ['/pid', this.process.pid.toString(), '/f', '/t']);
          } else {
            this.process.kill('SIGKILL');
          }
        } catch (e) { /* ignore */ }
        resolve();
      }, 5000);

      this.process.once('exit', () => {
        clearTimeout(timeout);
        resolve();
      });

      // 优雅终止
      try {
        if (process.platform === 'win32') {
          spawn('taskkill', ['/pid', this.process.pid.toString(), '/t']);
        } else {
          this.process.kill('SIGTERM');
        }
      } catch (e) { /* ignore */ }
    });
  }

  getStatus() {
    return this.status;
  }

  /**
   * 查找 Python 可执行文件
   */
  async _findPython() {
    // 优先使用项目 venv
    const venvPaths = [
      path.join(this.projectDir, '.venv', 'Scripts', 'python.exe'),
      path.join(this.projectDir, 'venv', 'Scripts', 'python.exe'),
      path.join(this.projectDir, '.venv', 'bin', 'python'),
      path.join(this.projectDir, 'venv', 'bin', 'python'),
    ];

    const fs = require('fs');
    for (const p of venvPaths) {
      if (fs.existsSync(p)) return p;
    }

    // 回退到系统 Python
    return process.platform === 'win32' ? 'python' : 'python3';
  }

  /**
   * 轮询等待后端就绪
   */
  _waitForReady(timeout = 30000) {
    const startTime = Date.now();
    return new Promise((resolve, reject) => {
      const check = () => {
        if (Date.now() - startTime > timeout) {
          reject(new Error(`Python 后端在 ${timeout / 1000}s 内未就绪`));
          return;
        }

        const req = http.get(`http://localhost:${this.port}/api/health`, (res) => {
          if (res.statusCode === 200) {
            resolve();
          } else {
            setTimeout(check, 500);
          }
        });

        req.on('error', () => {
          setTimeout(check, 500);
        });

        req.setTimeout(2000, () => {
          req.destroy();
          setTimeout(check, 500);
        });
      };

      // 先等 1 秒让 Python 进程启动
      setTimeout(check, 1000);
    });
  }
}

module.exports = PythonBridge;
