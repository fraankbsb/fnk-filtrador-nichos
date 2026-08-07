# -*- mode: python ; coding: utf-8 -*-
# Empacota FNK_Separador.py com suas dependências pesadas (torch, open_clip,
# cv2, PIL). torch e open_clip precisam de collect_all porque carregam
# arquivos de dados/binários em tempo de execução (pesos, vocabulário BPE)
# que o PyInstaller não detecta sozinho a partir dos imports.

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = ["cv2", "PIL", "PIL.Image"]

for pacote in ("torch", "open_clip"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pacote)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

a = Analysis(
    ['FNK_Separador.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# Modo "onedir" (pasta) em vez de "onefile": o onefile precisa descompactar
# ~300MB pra uma pasta temporária TODA VEZ que o programa abre, o que deixa
# a inicialização muito lenta. Onedir só descompacta uma vez, na instalação/
# compilação — abrir depois é quase instantâneo. A troca é o conteúdo dos
# arquivos ir direto pro EXE() ou pro COLLECT() (pasta) no final.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FNK_Separador',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='NONE',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='FNK_Separador',
)
