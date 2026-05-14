/**
 * LocalMindDesk — Electron Preload Script
 * 安全地暴露窗口控制和原生对话框 API 到渲染进程
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  // 窗口控制
  minimize: () => ipcRenderer.invoke('window:minimize'),
  maximize: () => ipcRenderer.invoke('window:maximize'),
  close: () => ipcRenderer.invoke('window:close'),
  isMaximized: () => ipcRenderer.invoke('window:isMaximized'),

  // 监听窗口状态变化
  onWindowState: (callback) => {
    ipcRenderer.on('window-state', (_, state) => callback(state));
  },

  // 原生文件夹选择
  openFolderDialog: () => ipcRenderer.invoke('dialog:openFolder'),

  // Python 后端状态
  getPythonStatus: () => ipcRenderer.invoke('python:status'),

  // 桌宠相关
  createPetWindow: (opts) => ipcRenderer.invoke('pet:createWindow', opts),
  closePetWindow: () => ipcRenderer.invoke('pet:closeWindow'),
  movePetWindow: (dx, dy) => ipcRenderer.invoke('pet:moveWindow', dx, dy),
  listPets: () => ipcRenderer.invoke('pet:list'),
  savePetAsset: (petId, fileName, buffer) => ipcRenderer.invoke('pet:saveAsset', petId, fileName, buffer),
  deletePet: (petId) => ipcRenderer.invoke('pet:delete', petId),
  onPetDesktopClosed: (callback) => {
    ipcRenderer.on('pet:desktop-closed', () => callback());
  },

  // 标识 Electron 环境
  isElectron: true,
});
