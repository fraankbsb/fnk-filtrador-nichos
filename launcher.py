#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Launcher — atualiza e inicia o app via releases do GitHub.

Compilado uma única vez (PyInstaller --onefile --windowed). Depois disso
só o payload (código-fonte do app) muda a cada release — o launcher.exe
raramente precisa ser recompilado, só se houver bug nele mesmo.
"""

import os
import sys
import json
import shutil
import zipfile
import subprocess
import threading
import urllib.request
import urllib.error
from pathlib import Path

import tkinter as tk
from tkinter import messagebox

# Prefixo obrigatório do asset de código na release. NUNCA baixe "o primeiro
# .zip que achar" — uma release pode ter mais de um .zip (o payload de
# código E o launcher_setup.zip de instalação). Pegar o errado já causou um
# bug real: o launcher baixou o launcher_setup.zip e tentou sobrescrever o
# próprio .exe em execução — o Windows bloqueia isso (PermissionError 13).
PREFIXO_ASSET_PAYLOAD = "payload_"

# Segunda camada de proteção: mesmo que o zip certo seja escolhido, nunca
# extraia um arquivo chamado literalmente launcher.exe por cima do launcher
# que está rodando agora.
ARQUIVO_PROTEGIDO = "launcher.exe"


def pasta_app():
    """Pasta onde o launcher.exe (ou launcher.py em dev) está rodando.
    Nunca hardcode caminho — sempre calcule a partir de onde o processo
    atual está, pra funcionar em qualquer PC/disco."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def ler_json(caminho, padrao=None):
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return padrao


def salvar_json(caminho, dados):
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=2, ensure_ascii=False)


LIBS_NECESSARIAS = ("cv2", "torch", "open_clip", "PIL")


def encontrar_python():
    """Localiza um interpretador Python que realmente tenha as bibliotecas
    do app instaladas. Não basta pegar "o primeiro python do PATH": em PCs
    com mais de uma instalação (comum aqui — Python 3.11 e 3.14 lado a
    lado), o primeiro do PATH pode ser justamente o que NÃO tem torch/
    open_clip instalados, e o app abriria só pra fechar com erro.
    Não usar sys.executable aqui: quando o launcher está compilado
    (frozen), sys.executable aponta pro próprio launcher.exe, não pra um
    Python."""
    candidatos = []
    for nome in ("python", "py", "python3"):
        caminho = shutil.which(nome)
        if caminho and caminho not in candidatos:
            candidatos.append(caminho)

    # O Python Launcher (py.exe) sabe listar TODAS as versões instaladas,
    # mesmo as que não são a primeira no PATH — usa isso pra não depender
    # só da ordem do PATH.
    py_launcher = shutil.which("py")
    if py_launcher:
        try:
            saida = subprocess.run(
                [py_launcher, "-0p"], capture_output=True, text=True, timeout=5
            )
            for linha in saida.stdout.splitlines():
                for pedaco in linha.split():
                    if pedaco.lower().endswith(("python.exe", "python")) and pedaco not in candidatos:
                        candidatos.append(pedaco)
        except Exception:
            pass

    if not candidatos:
        return None

    # Testa cada candidato de verdade: só serve o que consegue importar
    # as bibliotecas pesadas que o app precisa.
    codigo_teste = "import " + ", ".join(LIBS_NECESSARIAS)
    for cand in candidatos:
        try:
            r = subprocess.run(
                [cand, "-c", codigo_teste],
                capture_output=True, timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if r.returncode == 0:
                return cand
        except Exception:
            continue

    # Nenhum tem as libs — devolve o primeiro mesmo assim, pra pelo menos
    # cair na mensagem de erro clara do próprio FNK_Separador.py.
    return candidatos[0]


class Launcher(tk.Tk):
    COR_BG = "#141414"
    COR_CARD = "#1e1e1e"
    COR_VERDE = "#1d9e75"
    COR_BRANCO = "#f0ede8"
    COR_CINZA = "#888780"
    COR_ERRO = "#F09595"

    def __init__(self):
        super().__init__()
        self.pasta = pasta_app()
        self.cfg = ler_json(self.pasta / "update_config.json", {})
        self.repo = self.cfg.get("repo", "")
        self.entry_point = self.cfg.get("entry_point", "")
        self.titulo_app = self.cfg.get("app_title", "App")

        self.title(f"Launcher — {self.titulo_app}")
        self.geometry("480x320")
        self.configure(bg=self.COR_BG)
        self.resizable(False, False)
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 480) // 2
        y = (self.winfo_screenheight() - 320) // 2
        self.geometry(f"+{x}+{y}")

        self._build()

    def _build(self):
        hdr = tk.Frame(self, bg="#0d0d0d", pady=18)
        hdr.pack(fill="x")
        tk.Label(hdr, text=self.titulo_app, bg="#0d0d0d", fg=self.COR_BRANCO,
                 font=("Segoe UI", 14, "bold")).pack()

        versao = ler_json(self.pasta / "version.json", {}).get("version", "?")
        self._lbl_versao = tk.Label(hdr, text=f"Versão instalada: {versao}",
                                     bg="#0d0d0d", fg=self.COR_CINZA, font=("Segoe UI", 9))
        self._lbl_versao.pack()

        card = tk.Frame(self, bg=self.COR_CARD, padx=20, pady=20)
        card.pack(fill="both", expand=True, padx=16, pady=14)

        self._btn_update = tk.Button(
            card, text="🔄  Atualizar App", command=self._atualizar_thread,
            font=("Segoe UI", 11, "bold"), bg="#2c2c2a", fg=self.COR_BRANCO,
            relief="flat", pady=12, cursor="hand2",
        )
        self._btn_update.pack(fill="x", pady=(0, 10))

        self._btn_iniciar = tk.Button(
            card, text="▶  Iniciar App", command=self._iniciar,
            font=("Segoe UI", 11, "bold"), bg=self.COR_VERDE, fg="white",
            relief="flat", pady=12, cursor="hand2",
        )
        self._btn_iniciar.pack(fill="x")

        self._status = tk.Label(card, text="Pronto.", bg=self.COR_CARD, fg=self.COR_CINZA,
                                 font=("Segoe UI", 9), wraplength=420, justify="left")
        self._status.pack(fill="x", pady=(16, 0))

    def _set_status(self, msg, cor=None):
        self.after(0, lambda: self._status.configure(text=msg, fg=cor or self.COR_CINZA))

    # ─── Atualizar ─────────────────────────────

    def _atualizar_thread(self):
        self._btn_update.configure(state="disabled")
        self._btn_iniciar.configure(state="disabled")
        threading.Thread(target=self._atualizar, daemon=True).start()

    def _atualizar(self):
        if not self.repo:
            self._set_status("update_config.json sem 'repo' configurado.", self.COR_ERRO)
            self._reabilitar_botoes()
            return

        self._set_status("Consultando última versão no GitHub...")
        try:
            url = f"https://api.github.com/repos/{self.repo}/releases/latest"
            req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                release = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            self._set_status(f"Erro ao consultar releases: HTTP {e.code}", self.COR_ERRO)
            self._reabilitar_botoes()
            return
        except Exception as e:
            self._set_status(f"Erro ao consultar releases: {e}", self.COR_ERRO)
            self._reabilitar_botoes()
            return

        tag_remota = release.get("tag_name", "").lstrip("v")
        dados_versao = ler_json(self.pasta / "version.json", {"version": "0.0.0"})
        versao_local = dados_versao.get("version", "0.0.0")

        if tag_remota == versao_local:
            self._set_status(f"Já está na versão mais recente ({versao_local}).", self.COR_VERDE)
            self._reabilitar_botoes()
            return

        # Seleção específica do asset — NUNCA "o primeiro .zip que achar".
        assets = release.get("assets", [])
        asset_payload = next(
            (a for a in assets if a.get("name", "").startswith(PREFIXO_ASSET_PAYLOAD)
             and a.get("name", "").endswith(".zip")),
            None
        )
        if not asset_payload:
            self._set_status(
                f"Release {tag_remota} não tem asset '{PREFIXO_ASSET_PAYLOAD}*.zip'.",
                self.COR_ERRO
            )
            self._reabilitar_botoes()
            return

        self._set_status(f"Baixando {asset_payload['name']} ({tag_remota})...")
        destino_zip = self.pasta / asset_payload["name"]
        try:
            urllib.request.urlretrieve(asset_payload["browser_download_url"], destino_zip)
        except Exception as e:
            self._set_status(f"Erro ao baixar: {e}", self.COR_ERRO)
            self._reabilitar_botoes()
            return

        self._set_status("Extraindo atualização...")
        try:
            pulados = []
            with zipfile.ZipFile(destino_zip, "r") as z:
                for membro in z.infolist():
                    nome_arquivo = os.path.basename(membro.filename)
                    # Segunda camada de proteção: nunca sobrescreve o launcher
                    # que está rodando, não importa o que vier no zip.
                    if nome_arquivo == ARQUIVO_PROTEGIDO:
                        pulados.append(membro.filename)
                        continue
                    z.extract(membro, self.pasta)
        except Exception as e:
            self._set_status(f"Erro ao extrair: {e}", self.COR_ERRO)
            self._reabilitar_botoes()
            return
        finally:
            try:
                destino_zip.unlink(missing_ok=True)
            except Exception:
                pass

        salvar_json(self.pasta / "version.json", {"version": tag_remota})
        msg = f"Atualizado para {tag_remota}."
        if pulados:
            msg += f" ({len(pulados)} arquivo(s) protegido(s) ignorado(s))"
        self._set_status(msg, self.COR_VERDE)
        self.after(0, lambda: self._lbl_versao.configure(text=f"Versão instalada: {tag_remota}"))
        self._reabilitar_botoes()

    def _reabilitar_botoes(self):
        self.after(0, lambda: self._btn_update.configure(state="normal"))
        self.after(0, lambda: self._btn_iniciar.configure(state="normal"))

    # ─── Iniciar ───────────────────────────────

    def _iniciar(self):
        if not self.entry_point:
            messagebox.showerror("Erro", "update_config.json sem 'entry_point' configurado.")
            return

        # Se existir um .exe já compilado do app do lado do launcher (modo
        # "onedir" do PyInstaller: pasta com o mesmo nome, ou onefile solto
        # na mesma pasta), roda ele direto — não depende de Python nem das
        # bibliotecas estarem instaladas nessa máquina.
        nome_base = Path(self.entry_point).stem
        for candidato in (self.pasta / f"{nome_base}.exe", self.pasta / nome_base / f"{nome_base}.exe"):
            if candidato.is_file():
                try:
                    subprocess.Popen([str(candidato)], cwd=str(candidato.parent))
                except Exception as e:
                    messagebox.showerror("Erro ao iniciar", str(e))
                return

        caminho_entry = self.pasta / self.entry_point
        if not caminho_entry.is_file():
            messagebox.showerror("Erro", f"Arquivo não encontrado:\n{caminho_entry}")
            return

        python = encontrar_python()
        if not python:
            messagebox.showerror(
                "Python não encontrado",
                "Não achei nenhum interpretador Python no sistema (python/py).\n"
                "Instale o Python e as dependências (requirements.txt) antes de iniciar o app."
            )
            return

        try:
            subprocess.Popen(
                [python, str(caminho_entry)],
                cwd=str(self.pasta),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        except Exception as e:
            messagebox.showerror("Erro ao iniciar", str(e))


if __name__ == "__main__":
    Launcher().mainloop()
