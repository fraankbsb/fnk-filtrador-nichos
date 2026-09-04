# -*- mode: python ; coding: utf-8 -*-
# Empacota FNK_Separador.py com suas dependências pesadas (torch, open_clip,
# cv2, PIL, av, panns_inference/torchlibrosa/matplotlib — modelo de áudio).
# Todas precisam de collect_all porque carregam arquivos de dados/binários
# em tempo de execução (pesos, vocabulário BPE, DLLs do ffmpeg embutido no
# av, fontes/backends do matplotlib) que o PyInstaller não detecta sozinho
# a partir dos imports. O PESO do modelo de áudio (~300MB) NÃO entra aqui —
# ele é baixado sozinho na 1ª vez que a separação por música é usada (ver
# FNK_Musica.py), do mesmo jeito que o CLIP baixa os pesos dele.

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = ["cv2", "PIL", "PIL.Image", "numpy", "FNK_Template", "FNK_Musica"]

for pacote in ("torch", "open_clip", "av", "panns_inference", "torchlibrosa", "matplotlib"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pacote)
    # O matplotlib só entra aqui porque o panns_inference importa ele à
    # toa (uma função de gráfico que a gente nunca chama, ver
    # FNK_Musica.py). O programa força o backend "Agg" (sem janela) —
    # nunca precisa do PyQt5 que o matplotlib detecta como backend
    # opcional no PC de quem compila. Sem esse filtro, o PyQt5 inteiro
    # (~200MB) ia junto à toa.
    if pacote == "matplotlib":
        pkg_datas = [t for t in pkg_datas if "PyQt5" not in t[0]]
        pkg_binaries = [t for t in pkg_binaries if "PyQt5" not in t[0]]
        pkg_hidden = [h for h in pkg_hidden if "PyQt5" not in h]
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
    excludes=["PyQt5", "PyQt6", "PySide2", "PySide6"],
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
