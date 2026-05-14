@echo off
chcp 65001 >nul
echo.
echo  ╔══════════════════════════════════════════╗
echo  ║   LocalMindDesk — 启动菜单          ║
echo  ╚══════════════════════════════════════════╝
echo.
echo   [1]  启动后端服务 (FastAPI, 端口 8000)
echo   [2]  启动网页版  (后端 + 浏览器)
echo   [3]  启动 Electron App
echo   [4]  启动 CLI 对话
echo   [5]  CLI 对话 (指定角色)
echo   [6]  退出
echo.
set /p choice=请选择 [1-6]: 

if "%choice%"=="1" goto backend
if "%choice%"=="2" goto web
if "%choice%"=="3" goto electron
if "%choice%"=="4" goto cli
if "%choice%"=="5" goto cli_persona
if "%choice%"=="6" goto end

:backend
echo.
echo  ▶ 启动 FastAPI 后端 (http://localhost:8000)...
echo  ▶ 按 Ctrl+C 停止
echo.
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
goto end

:web
echo.
echo  ▶ 启动后端...
start "LocalMindDesk Backend" cmd /k "python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
timeout /t 2 /nobreak >nul
echo  ▶ 打开网页版...
start http://localhost:8000
echo  ▶ 后端运行中，关闭弹出的命令窗口即可停止
goto end

:electron
echo.
echo  ▶ 启动 Electron App (开发模式)...
call npm run dev
goto end

:cli
echo.
echo  ▶ 启动 CLI 对话模式...
echo  ▶ 输入 /help 查看命令, 输入 exit 退出
echo.
python cli.py
goto end

:cli_persona
echo.
set /p slug=  请输入角色 slug (留空使用默认): 
if "%slug%"=="" (
    python cli.py
) else (
    python cli.py --persona %slug%
)
goto end

:end
pause
