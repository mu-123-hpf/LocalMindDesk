# -*- mode: python ; coding: utf-8 -*-
"""
LocalMindDesk — PyInstaller 打包配置
将 Python FastAPI 后端打包为独立 exe
"""

import os
import sys

block_cipher = None

# 项目根目录
project_dir = os.path.abspath('.')

a = Analysis(
    ['app/main.py'],
    pathex=[project_dir],
    binaries=[],
    datas=[
        ('config.json', '.'),
        ('data', 'data'),
        ('.agents', '.agents'),
        ('agents.json', '.'),
    ],
    hiddenimports=[
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'uvicorn.lifespan.off',
        'fastapi',
        'fastapi.staticfiles',
        'fastapi.responses',
        'starlette',
        'starlette.routing',
        'starlette.middleware',
        'starlette.middleware.cors',
        'pydantic',
        'pydantic.deprecated',
        'pydantic.deprecated.decorator',
        'httpx',
        'openai',
        'pptx',
        'docx',
        'PIL',
        'pyautogui',
        'app',
        'app.main',
        'app.config',
        'app.llm_provider',
        'app.agent_router',
        'app.action_planner',
        'app.action_engine',
        'app.agent_profile',
        'app.meta_agent',
        'app.prompt_loader',
        'app.memory',
        'app.context_manager',
        'app.skill_manager',
        'app.tools',
        'app.tools.web_search',
        'app.tools.ppt_maker',
        'app.tools.doc_maker',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        'numpy',
        'pandas',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='localminddesk-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # 需要控制台输出
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon='assets/icon.png',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='localminddesk-backend',
)
