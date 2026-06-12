# -*- mode: python ; coding: utf-8 -*-
"""墨盾 (Moshield) PyInstaller 打包配置

打包命令（在 PowerShell venv 里）:
    pip install pyinstaller
    pyinstaller build.spec --clean

输出: dist/Moshield.exe （单文件，约 60-90 MB）
"""
import sys
from pathlib import Path

# pathex 让 PyInstaller 找到 src/ 包
PATHEX = [str(Path('.').resolve())]

# 数据文件：项目自带的资源字典（运行时 import 用）
DATAS = [
    ('src/resources/*.py', 'src/resources'),
    ('assets/icon.ico', 'assets'),
]

# 排除不需要的库（减小体积）
EXCLUDES = [
    'tkinter',
    'matplotlib',
    'numpy.tests',
    'pandas.tests',
    'pytest',
    'setuptools',
    'pip',
    'unittest',
    'pydoc',
    'doctest',
    'argparse',
    'lib2to3',
    'pdb',
]

# PyQt6 隐式依赖（PyInstaller 有时漏掉）
HIDDENIMPORTS = [
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'PyQt6.QtPrintSupport',
    'sqlalchemy.dialects.sqlite',
    'docx.oxml',
    'docx.oxml.ns',
    'openpyxl.cell._writer',
    'pptx.oxml',
]


a = Analysis(
    ['src/gui/app.py'],
    pathex=PATHEX,
    binaries=[],
    datas=DATAS,
    hiddenimports=HIDDENIMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Moshield',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # UPX 压缩（如果装了 upx）
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI 应用，不显示控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',  # 墨盾应用图标（7 个分辨率：16-256）
)
