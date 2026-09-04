#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Publish — empacota o payload do app e publica uma release no GitHub.

Uso:
    python publish.py <versao> [mensagem]
    python publish.py auto              # incrementa patch + timestamp

Toda publicação sobe DOIS assets na release:
  - payload_vX.Y.Z.zip   → só o código do app (o launcher baixa isso)
  - launcher_setup.zip   → launcher.exe + update_config.json, nome FIXO,
                            pra instalar em PC novo via link permanente:
                            github.com/OWNER/REPO/releases/latest/download/launcher_setup.zip
"""

import sys
import json
import shutil
import zipfile
import subprocess
from pathlib import Path
from datetime import datetime

PASTA = Path(__file__).resolve().parent

# Whitelist explícita do que é "código do app". NUNCA usar glob "tudo da
# pasta" aqui — esta pasta também recebe vídeos do usuário (às vezes
# milhares de arquivos), e isso não pode ir pro git nem pra release.
PAYLOAD_FILES = [
    "FNK_Separador.py",
    "FNK_DetectorPets.py",
    "FNK_Template.py",
    "FNK_Musica.py",
    "FNK_Separador-2.spec",
    "FNK_Separador.spec",
    "COMPILAR_EXE.bat",
    "requirements.txt",
    "update_config.json",
    "version.json",
    ".gitignore",
    "launcher.py",
    "publish.py",
    "watch_and_publish.py",
    "iniciar_vigia.bat",
]

# Binários grandes de terceiros (modelos de IA, etc.) que não devem ir pro
# git mas precisam entrar no zip da release, lidos direto do disco. Este
# projeto não tem nenhum hoje (o CLIP baixa os pesos via HuggingFace em
# tempo de execução, não fica salvo aqui) — mantido vazio de propósito.
BINARIOS_EXTRA = []

NOME_LAUNCHER_EXE = "launcher.exe"
NOME_LAUNCHER_SETUP = "launcher_setup.zip"


def resolver_gh():
    """Localiza o executável do gh CLI. shutil.which() sozinho falha se o
    script rodar fora de um terminal com PATH atualizado (ex: agendador de
    tarefas, atalho); por isso o fallback pro caminho padrão do Windows."""
    caminho = shutil.which("gh")
    if caminho:
        return caminho
    padrao = Path(r"C:\Program Files\GitHub CLI\gh.exe")
    if padrao.is_file():
        return str(padrao)
    raise RuntimeError(
        "gh CLI não encontrado. Instale em https://cli.github.com/ "
        "e rode 'gh auth login' antes de publicar."
    )


def ler_config():
    with open(PASTA / "update_config.json", "r", encoding="utf-8") as f:
        return json.load(f)


def ler_versao_atual():
    caminho = PASTA / "version.json"
    if caminho.is_file():
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f).get("version", "0.0.0")
    return "0.0.0"


def proxima_versao_auto(atual):
    partes = atual.split(".")
    while len(partes) < 3:
        partes.append("0")
    try:
        partes[2] = str(int(partes[2]) + 1)
    except ValueError:
        partes[2] = "1"
    return ".".join(partes[:3])


def salvar_versao(versao):
    with open(PASTA / "version.json", "w", encoding="utf-8") as f:
        json.dump({"version": versao}, f, indent=2, ensure_ascii=False)


def rodar(cmd, **kwargs):
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=str(PASTA), text=True, **kwargs)


def git_commit_push(versao, mensagem):
    arquivos_existentes = [f for f in PAYLOAD_FILES if (PASTA / f).is_file()]
    rodar(["git", "add", "--"] + arquivos_existentes)

    status = rodar(["git", "status", "--porcelain"], capture_output=True)
    if not status.stdout.strip():
        print("  Nada novo pra commitar — pulando commit, seguindo pro push/release.")
        return

    r = rodar(["git", "commit", "-m", f"{mensagem} (v{versao})"])
    if r.returncode != 0:
        print("  Commit não gerou mudanças — seguindo mesmo assim.")
        return

    push = rodar(["git", "push"])
    if push.returncode != 0:
        raise RuntimeError("git push falhou — veja a saída acima.")


def montar_zip_payload(versao):
    destino = PASTA / f"payload_v{versao}.zip"
    if destino.exists():
        destino.unlink()

    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for nome in PAYLOAD_FILES:
            caminho = PASTA / nome
            if caminho.is_file():
                z.write(caminho, arcname=nome)
        for caminho_str in BINARIOS_EXTRA:
            caminho = Path(caminho_str)
            if caminho.is_file():
                z.write(caminho, arcname=caminho.name)
    return destino


def montar_launcher_setup():
    exe = PASTA / NOME_LAUNCHER_EXE
    if not exe.is_file():
        print(f"  ⚠ {NOME_LAUNCHER_EXE} não encontrado — pulando launcher_setup.zip "
              "(compile o launcher primeiro).")
        return None

    destino = PASTA / NOME_LAUNCHER_SETUP
    if destino.exists():
        destino.unlink()

    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(exe, arcname=NOME_LAUNCHER_EXE)
        z.write(PASTA / "update_config.json", arcname="update_config.json")
    return destino


def publicar_release(repo, versao, mensagem, zip_payload, zip_launcher_setup):
    gh = resolver_gh()
    tag = f"v{versao}"

    # Se a tag já existir (ex: reupload depois de corrigir algo), apaga e
    # recria em vez de falhar.
    existe = rodar([gh, "release", "view", tag, "--repo", repo], capture_output=True)
    if existe.returncode == 0:
        rodar([gh, "release", "delete", tag, "--repo", repo, "--yes"])

    assets = [str(zip_payload)]
    if zip_launcher_setup:
        assets.append(str(zip_launcher_setup))

    cmd = [
        gh, "release", "create", tag, *assets,
        "--repo", repo,
        "--title", tag,
        "--notes", mensagem,
    ]
    r = rodar(cmd)
    if r.returncode != 0:
        raise RuntimeError("gh release create falhou — veja a saída acima.")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    arg_versao = sys.argv[1]
    mensagem = sys.argv[2] if len(sys.argv) > 2 else None

    versao_atual = ler_versao_atual()
    if arg_versao == "auto":
        versao = proxima_versao_auto(versao_atual)
        if mensagem is None:
            mensagem = f"Publicação automática {datetime.now():%d/%m/%Y %H:%M:%S}"
    else:
        versao = arg_versao.lstrip("v")
        if mensagem is None:
            mensagem = f"Release v{versao}"

    cfg = ler_config()
    repo = cfg["repo"]

    print(f"Publicando {repo} v{versao} — \"{mensagem}\"")
    salvar_versao(versao)

    print("\n[1/4] git commit + push")
    git_commit_push(versao, mensagem)

    print("\n[2/4] Empacotando payload")
    zip_payload = montar_zip_payload(versao)
    print(f"  {zip_payload.name}")

    print("\n[3/4] Empacotando launcher_setup.zip")
    zip_launcher_setup = montar_launcher_setup()
    if zip_launcher_setup:
        print(f"  {zip_launcher_setup.name}")

    print("\n[4/4] Publicando release no GitHub")
    publicar_release(repo, versao, mensagem, zip_payload, zip_launcher_setup)

    print(f"\n✓ Publicado: v{versao}")


if __name__ == "__main__":
    main()
