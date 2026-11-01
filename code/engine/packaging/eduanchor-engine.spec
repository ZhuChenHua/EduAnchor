# -*- mode: python ; coding: utf-8 -*-

import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis(
    [os.path.abspath(os.path.join(SPECPATH, "entrypoint.py"))],
    pathex=[os.path.join(ROOT, "src")],
    binaries=[],
    datas=[(os.path.join(ROOT, "src", "eduanchor", "data"), "eduanchor/data")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "IPython",
        "pytest",
        "torch",
        "onnxruntime",
        "transformers",
        "sentence_transformers",
        "FlagEmbedding",
        "scipy",
        "sklearn",
        "pandas",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="eduanchor-engine",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="eduanchor-engine",
)
