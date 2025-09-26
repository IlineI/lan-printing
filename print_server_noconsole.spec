# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 配置文件（无控制台版本）
使用方法: pyinstaller print_server_noconsole.spec
"""

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# 获取脚本目录
spec_root = os.path.dirname(os.path.abspath(SPEC))

# 数据文件和资源
datas = [
    # 包含图标文件
    (os.path.join(spec_root, 'logo.ico'), '.'),
    # 如果有其他资源文件，在这里添加
    # (os.path.join(spec_root, 'templates'), 'templates'),
]

# 隐藏的导入模块
hiddenimports = [
    'win32print',
    'win32api', 
    'win32gui',
    'win32con',
    'pystray',
    'PIL',
    'PIL.Image',
    'PIL.ImageDraw',
    'flask',
    'winreg',
    'json',
    'socket',
    'threading',
    'subprocess',
    'datetime',
]

# 排除的模块（可选，减少文件大小）
excludes = [
    'tkinter',
    'matplotlib',
    'numpy',
    'pandas',
    'scipy',
]

block_cipher = None

a = Analysis(
    ['print_server.py'],
    pathex=[spec_root],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='内网打印服务-静默版',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 完全隐藏控制台窗口
    icon=os.path.join(spec_root, 'logo.ico') if os.path.exists(os.path.join(spec_root, 'logo.ico')) else None,
    version_file=None,  # 可以添加版本信息文件
)