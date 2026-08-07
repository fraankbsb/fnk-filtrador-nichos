#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vigia — monitora os arquivos do payload e publica sozinho quando param de
mudar. Espera 8s de silêncio após a última alteração antes de publicar,
pra não disparar uma release no meio de uma edição em andamento.
"""

import subprocess
import sys
import time
from pathlib import Path

from publish import PAYLOAD_FILES

PASTA = Path(__file__).resolve().parent
SEGUNDOS_SILENCIO = 8
INTERVALO_CHECAGEM = 1


def snapshot_mtimes():
    mtimes = {}
    for nome in PAYLOAD_FILES:
        caminho = PASTA / nome
        if caminho.is_file():
            mtimes[nome] = caminho.stat().st_mtime
    return mtimes


def main():
    print("Vigia rodando — monitorando payload em", PASTA)
    print(f"Publica sozinho {SEGUNDOS_SILENCIO}s depois da última mudança.\n")

    anterior = snapshot_mtimes()
    ultima_mudanca = None

    while True:
        time.sleep(INTERVALO_CHECAGEM)
        atual = snapshot_mtimes()

        if atual != anterior:
            anterior = atual
            ultima_mudanca = time.time()
            print(f"[{time.strftime('%H:%M:%S')}] mudança detectada, aguardando silêncio...")
            continue

        if ultima_mudanca is not None and (time.time() - ultima_mudanca) >= SEGUNDOS_SILENCIO:
            print(f"[{time.strftime('%H:%M:%S')}] publicando...")
            r = subprocess.run([sys.executable, str(PASTA / "publish.py"), "auto"], cwd=str(PASTA))
            if r.returncode != 0:
                print("  ⚠ publish.py terminou com erro, veja a saída acima.")
            ultima_mudanca = None
            anterior = snapshot_mtimes()


if __name__ == "__main__":
    main()
