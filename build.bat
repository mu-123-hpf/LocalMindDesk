@echo off
echo ============================================
echo   LocalMindDesk - 一键打包
echo ============================================
echo.

REM Step 1: 安装 PyInstaller
echo [1/4] 检查 PyInstaller...
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo 安装 PyInstaller...
    pip install pyinstaller
)
echo OK

REM Step 2: 打包 Python 后端
echo.
echo [2/4] 打包 Python 后端 (PyInstaller)...
pyinstaller --noconfirm --clean pyinstaller.spec
if errorlevel 1 (
    echo [错误] PyInstaller 打包失败！
    pause
    exit /b 1
)

REM Step 3: 复制打包结果到 python-dist
echo.
echo [3/4] 复制后端到 python-dist...
if exist python-dist rmdir /s /q python-dist
xcopy /E /I /Y dist\localminddesk-backend python-dist\localminddesk-backend
echo OK

REM Step 4: 打包 Electron 安装包
echo.
echo [4/4] 打包 Electron 安装包 (electron-builder)...
call npx electron-builder --win
if errorlevel 1 (
    echo [错误] electron-builder 打包失败！
    pause
    exit /b 1
)

echo.
echo ============================================
echo   打包完成！
echo   安装包位于: dist\
echo ============================================
pause
