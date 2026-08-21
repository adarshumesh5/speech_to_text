# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Grogu (onedir, no console).

Build:  python -m PyInstaller --noconfirm sotto.spec
"""

import glob
import os
import site

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

block_cipher = None

datas = []
binaries = []
hiddenimports = ["faster_whisper", "onnxruntime", "av", "sounddevice",
                 "huggingface_hub", "nvidia.cublas"]

# branding assets (app icon, tray PNGs, logo)
for f in glob.glob(os.path.join("sotto", "ui", "assets", "*")):
    if os.path.isfile(f):
        datas.append((f, "sotto/ui/assets"))

# NVIDIA cuBLAS — ctranslate2's CUDA backend (cublas64_12.dll etc.)
for sp in site.getsitepackages():
    for dll in glob.glob(os.path.join(sp, "nvidia", "cublas", "bin", "*.dll")):
        datas.append((dll, "nvidia/cublas/bin"))
        binaries.append((dll, "nvidia/cublas/bin"))

# ctranslate2 DLLs (cudnn64_9.dll, ctranslate2.dll, libiomp5md.dll)
binaries += collect_dynamic_libs("ctranslate2")

# PortAudio (sounddevice) + PyAV (audio decode for faster-whisper)
binaries += collect_dynamic_libs("sounddevice")
binaries += collect_dynamic_libs("av")
datas += collect_dynamic_libs("av")

# faster-whisper ships its Silero VAD model + tokenizer assets as package data
datas += collect_data_files("faster_whisper")

# jump-list helper (PowerShell/WPF) used by sotto.jumplist
datas.append(("scripts/jumplist.ps1", "."))

a = Analysis(
    ["sotto/__main__.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name="Grogu",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon="sotto/ui/assets/app.ico",
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Grogu",
)
