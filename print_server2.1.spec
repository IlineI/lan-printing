# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller .spec for print_server2.1

This spec was generated to include all explicit and common optional
dependencies referenced in print_server2.1.py (comtypes, win32com, pysnmp,
pystray, Pillow, requests, chardet, etc.) and to bundle common data folders
used at runtime (uploads, scanned_files, logo.ico, README.md, 测试).

If you add/remove resource files or 3rd-party libs, update hiddenimports
or datas accordingly.
"""

import os
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# Put the script name here (relative to this spec file)
script = 'print_server2.1.py'

# Base search path for imports
pathex = [os.path.abspath('.')]

# Hidden imports: include dynamic / optional modules observed in the source.
# This list is intentionally conservative to reduce runtime "missing module" issues.
hiddenimports = [
    # COM / Windows
    'comtypes',
    'comtypes.client',
    'win32com',
    'win32com.client',
    # pywin32 pieces
    'win32api',
    'win32print',
    'win32con',

    # Networking / SNMP and HTTP
    'pysnmp',
    'pysnmp.hlapi',
    'requests',
    'urllib3',

    # Tray / GUI / imaging
    'pystray',
    'PIL',
    'PIL.Image',
    'PIL.ImageDraw',

    # Encoding / detection / misc
    'chardet',
    'certifi',

    # Werkzeug / waitress (WSGI server)
    'werkzeug',
    'waitress',

    # Commonly used stdlib modules that sometimes need explicit inclusion
    'ctypes',
    'threading',
    'tkinter',
]

# Collect optional submodules automatically for some packages that are often
# imported dynamically.
# When PyInstaller executes this spec `__file__` may not be defined, so use
# the explicit `pathex[0]` (project root) to check for a local `pystray` folder.
hiddenimports += collect_submodules('pystray') if os.path.isdir(os.path.join(pathex[0], 'pystray')) else []

# Data files / folders to bundle into the executable. Each tuple is (src, dest)
# If a path doesn't exist it will simply be ignored by PyInstaller at build time.
datas = []

def add_if_exists(src, dest=None):
    """Helper: add src to datas if it exists on disk."""
    if not dest:
        dest = os.path.basename(src)
    if os.path.exists(src):
        # When a directory is provided, PyInstaller expects (path, dest) for each file.
        if os.path.isdir(src):
            for root, _, files in os.walk(src):
                for f in files:
                    full = os.path.join(root, f)
                    # preserve relative layout under dest
                    rel = os.path.relpath(full, src)
                    datas.append((full, os.path.join(dest, rel)))
        else:
            datas.append((src, dest))

# common runtime folders used by the app
add_if_exists(os.path.join('.', 'uploads'), 'uploads')
add_if_exists(os.path.join('.', 'scanned_files'), 'scanned_files')
add_if_exists(os.path.join('.', 'logo.ico'), '.')
add_if_exists(os.path.join('.', 'README.md'), '.')
add_if_exists(os.path.join('.', '测试'), '测试')
add_if_exists(os.path.join('.', 'exe'), 'exe')

# If you have a separate resources folder used by path_manager, try to include it
add_if_exists(os.path.join('.', 'resources'), 'resources')


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
          name='print_server2.1',
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
               name='print_server2.1')
