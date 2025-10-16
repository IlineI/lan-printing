# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller .spec for print_server2.2.1 (最全依赖版)

本 spec 文件已补全所有常用和可能用到的依赖，适配 Win7/Win10/Win11，确保打包后无缺失。
"""

import os
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

script = 'print_server2.2.1.py'
pathex = [os.path.abspath('.')]

hiddenimports = [
    'comtypes',
    'comtypes.client',
    'comtypes.stream',
    'win32com',
    'win32com.client',
    'win32api',
    'win32print',
    'win32con',
    'winreg',
    'wmi',
    'ctypes',
    'ctypes.wintypes',
    'pysnmp',
    'pysnmp.hlapi',
    'requests',
    'requests_toolbelt',
    'urllib3',
    'certifi',
    'chardet',
    'flask',
    'flask_cors',
    'flask.json',
    'flask.helpers',
    'werkzeug',
    'waitress',
    'pystray',
    'pystray._base',
    'pystray._win32',
    'PIL',
    'PIL.Image',
    'PIL.ImageDraw',
    'PIL.ImageFont',
    'PIL.ImageOps',
]
hiddenimports += collect_submodules('pystray') if os.path.isdir(os.path.join(pathex[0], 'pystray')) else []

datas = []
def add_if_exists(src, dest=None):
    if not dest:
        dest = os.path.basename(src)
    if os.path.exists(src):
        if os.path.isdir(src):
            for root, _, files in os.walk(src):
                for f in files:
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, src)
                    datas.append((full, os.path.join(dest, rel)))
        else:
            datas.append((src, dest))

add_if_exists(os.path.join('.', 'uploads'), 'uploads')
add_if_exists(os.path.join('.', 'scanned_files'), 'scanned_files')
add_if_exists(os.path.join('.', 'logo.ico'), '.')


a = Analysis([script],
             pathex=pathex,
             binaries=[],
             datas=datas,
             hiddenimports=hiddenimports,
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          name='print_server2.2.1',
          debug=False,
          strip=False,
          upx=True,
          console=True,
          icon='logo.ico' if os.path.exists('logo.ico') else None)

coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               name='print_server2.2.1')
