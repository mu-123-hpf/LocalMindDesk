/**
 * LocalMindDesk — Electron 主进程
 * 无边框窗口 + Python 后端生命周期管理
 */
const { app, BrowserWindow, ipcMain, dialog, screen } = require('electron');
const path = require('path');
const fs = require('fs');
const PythonBridge = require('./python-bridge');

let mainWindow = null;
let petWindow = null;
let pythonBridge = null;
const isDev = process.argv.includes('--dev');

// ============================================================
//  创建主窗口（无边框）
// ============================================================
function createWindow() {
  const { width, height } = screen.getPrimaryDisplay().workAreaSize;

  mainWindow = new BrowserWindow({
    width: Math.min(1600, width - 100),
    height: Math.min(1000, height - 60),
    minWidth: 900,
    minHeight: 600,
    frame: false,            // 无边框
    titleBarStyle: 'hidden',
    transparent: false,
    backgroundColor: '#0a0a0f',
    icon: path.join(__dirname, '..', 'assets', 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: false,  // 允许 file:// 下 fetch 本地资源
    },
    show: false,
  });

  // 加载前端（file:// 协议，webSecurity: false 允许 fetch 本地文件）
  const frontendPath = path.join(__dirname, '..', 'frontend', 'index.html');
  mainWindow.loadFile(frontendPath);

  // 窗口准备好后再显示
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    if (isDev) {
      mainWindow.webContents.openDevTools({ mode: 'detach' });
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  // 窗口最大化状态变化 → 通知渲染进程
  mainWindow.on('maximize', () => {
    mainWindow.webContents.send('window-state', 'maximized');
  });
  mainWindow.on('unmaximize', () => {
    mainWindow.webContents.send('window-state', 'normal');
  });
}

// ============================================================
//  IPC: 窗口控制
// ============================================================
ipcMain.handle('window:minimize', () => {
  mainWindow?.minimize();
});

ipcMain.handle('window:maximize', () => {
  if (mainWindow?.isMaximized()) {
    mainWindow.unmaximize();
  } else {
    mainWindow?.maximize();
  }
});

ipcMain.handle('window:close', () => {
  mainWindow?.close();
});

ipcMain.handle('window:isMaximized', () => {
  return mainWindow?.isMaximized() || false;
});

// IPC: 原生文件夹选择对话框
ipcMain.handle('dialog:openFolder', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory'],
    title: '选择项目文件夹',
  });
  if (result.canceled || !result.filePaths.length) return null;
  return result.filePaths[0];
});

// IPC: 获取 Python 后端状态
ipcMain.handle('python:status', () => {
  return pythonBridge ? pythonBridge.getStatus() : 'stopped';
});

// ============================================================
//  IPC: 桌宠桌面模式（透明独立窗口）
// ============================================================
ipcMain.handle('pet:createWindow', (_, opts) => {
  if (petWindow) {
    petWindow.focus();
    return;
  }

  const { width: screenW, height: screenH } = screen.getPrimaryDisplay().workAreaSize;
  const petSize = opts?.size || 128;

  petWindow = new BrowserWindow({
    width: petSize + 40,
    height: petSize + 40,
    x: screenW - petSize - 80,
    y: screenH - petSize - 80,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    resizable: false,
    skipTaskbar: true,
    hasShadow: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  const petHtmlPath = path.join(__dirname, '..', 'frontend', 'pet-desktop.html');
  petWindow.loadFile(petHtmlPath);
  petWindow.setIgnoreMouseEvents(false);

  petWindow.on('closed', () => {
    petWindow = null;
    // 通知主窗口宠物已回归
    mainWindow?.webContents.send('pet:desktop-closed');
  });

  console.log('[Electron] 桌宠桌面窗口已创建');
});

ipcMain.handle('pet:closeWindow', () => {
  if (petWindow) {
    petWindow.close();
    petWindow = null;
  }
});

ipcMain.handle('pet:moveWindow', (_, dx, dy) => {
  if (petWindow) {
    const [x, y] = petWindow.getPosition();
    petWindow.setPosition(x + Math.round(dx), y + Math.round(dy));
  }
});

// ============================================================
//  IPC: 宠物文件管理
// ============================================================
const petsDir = () => path.join(__dirname, '..', 'frontend', 'assets', 'pets');

ipcMain.handle('pet:list', async () => {
  const dir = petsDir();
  if (!fs.existsSync(dir)) return [];
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  const pets = [];
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    const petJsonPath = path.join(dir, entry.name, 'pet.json');
    if (fs.existsSync(petJsonPath)) {
      try {
        const data = JSON.parse(fs.readFileSync(petJsonPath, 'utf-8'));
        pets.push({
          id: entry.name,
          name: data.displayName || entry.name,
          description: data.description || '',
        });
      } catch { /* ignore */ }
    }
  }
  return pets;
});

ipcMain.handle('pet:saveAsset', async (_, petId, fileName, bufferData) => {
  const dir = path.join(petsDir(), petId);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  const filePath = path.join(dir, fileName);
  fs.writeFileSync(filePath, Buffer.from(bufferData));
  return filePath;
});

ipcMain.handle('pet:delete', async (_, petId) => {
  if (petId === 'default') return false; // 不允许删除默认宠物
  const dir = path.join(petsDir(), petId);
  if (fs.existsSync(dir)) {
    fs.rmSync(dir, { recursive: true, force: true });
    return true;
  }
  return false;
});

// ============================================================
//  应用生命周期
// ============================================================
app.whenReady().then(async () => {
  // 启动 Python 后端
  pythonBridge = new PythonBridge({
    port: 8000,
    projectDir: path.join(__dirname, '..'),
    isDev,
  });

  try {
    await pythonBridge.start();
    console.log('[Electron] Python 后端已启动');
  } catch (err) {
    console.error('[Electron] Python 后端启动失败:', err.message);
    // 仍然创建窗口，让用户看到错误信息
  }

  createWindow();
});

app.on('window-all-closed', async () => {
  // 关闭 Python 后端
  if (pythonBridge) {
    await pythonBridge.stop();
  }
  app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

// 防止多实例
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
}
