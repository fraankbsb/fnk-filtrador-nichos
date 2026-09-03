#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FNK Separador de Vídeos
========================
Coloque este .exe dentro de:
  D:\\fnkSocialMidia\\fnkFiltradorNichos\\

Ao abrir, o programa lista as subpastas dessa pasta e deixa você escolher
quais processar (uma, várias ou todas). Depois pergunta COMO separar:

  1) NICHO    — pelo CONTEÚDO VISUAL do vídeo (não pelo nome do arquivo),
                usando IA. Vai para fnkPerfis\\<Nicho>\\ (Pets, Comedia).
                Um vídeo pode se encaixar em 2 nichos e ir para os 2.

  2) TEMPLATE — pela MOLDURA do vídeo: a cor das faixas de fundo (preto,
                branco, cinza, colorido) e se ele é 9:16 preenchendo a
                tela toda sozinho. Vai para fnkPerfis\\Templates\\<Cor>\\
                Não usa IA — é bem mais rápido (ver FNK_Template.py).

  3) AMBOS    — as duas separações; o vídeo ganha uma cópia em cada pasta.

O original só é apagado da pasta de origem depois que todas as cópias
necessárias forem concluídas com sucesso.

Vídeos que não puderem ser analisados (ex: arquivo corrompido) vão para a
pasta de revisão. No modo AMBOS, se só uma das duas análises falhar, o
vídeo ainda é separado pela que funcionou.

Configuração em config.json (criado automaticamente na 1ª execução, ao
lado do .exe/script).
"""

import os, sys, shutil, time, threading, random, json, csv
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox

# As libs abaixo são pesadas e às vezes ausentes quando o .py é aberto com
# um Python diferente do usado para instalar as dependências (ex: duplo
# clique usando outro interpretador do PATH). Sem este try/except, a falta
# de qualquer uma delas derruba o programa na hora do import, sem mensagem
# nenhuma — a janela "abre e fecha" instantaneamente.
try:
    import cv2
    import torch
    import open_clip
    from PIL import Image
    import FNK_Template as tpl
except ImportError as e:
    _root = tk.Tk()
    _root.withdraw()
    messagebox.showerror(
        "FNK Separador — dependência ausente",
        f"Não foi possível carregar uma biblioteca necessária:\n\n{e}\n\n"
        "Instale as dependências antes de rodar o programa:\n"
        "  pip install -r requirements.txt\n\n"
        "Se você tem mais de um Python instalado, confirme que está "
        "rodando com o mesmo interpretador onde rodou esse comando."
    )
    _root.destroy()
    sys.exit(1)

# ══════════════════════════════════════════════
#  CONFIGURAÇÃO EXTERNA (config.json)
# ══════════════════════════════════════════════

CONFIG_PADRAO = {
    # Onde ficam as pastas de vídeo A PROCESSAR (a lista que aparece na
    # tela inicial do programa). Vazio = usa a própria pasta onde o .exe/
    # script está rodando (comportamento antigo). Preencha isso quando o
    # programa estiver instalado num lugar diferente (ex: Área de
    # Trabalho) mas os vídeos continuarem numa pasta fixa, tipo a pasta
    # do projeto.
    "pasta_origem":        "",
    "pasta_perfis":        r"D:\fnkSocialMidia\fnkPerfis",
    "pasta_revisao":       r"D:\fnkSocialMidia\COMPLETOS\fnkFiltradorNichos\Revisão de Videos",
    "frames_por_video":    10,
    "amostra_calibracao":  30,
    "confianca_minima":    0.05,
    "gap_secundaria":      0.003,
    "fator_calibracao":    0.5,
    "usar_duas_categorias": True,
    "recorte_topo":        0.30,
    # Ajustes da separação por TEMPLATE (cor do fundo e 9:16). Ficam no
    # mesmo config.json, com prefixo "template_", e quem lê/valida é o
    # próprio módulo FNK_Template.
    **tpl.CONFIG_TEMPLATE_PADRAO,
}

# Preenchidos por aplicar_config() a partir do config.json na inicialização.
PASTA_ORIGEM  = CONFIG_PADRAO["pasta_origem"]
PASTA_PERFIS  = CONFIG_PADRAO["pasta_perfis"]
PASTA_REVISAO = CONFIG_PADRAO["pasta_revisao"]
FRAMES_POR_VIDEO      = CONFIG_PADRAO["frames_por_video"]
AMOSTRA_CALIBRACAO    = CONFIG_PADRAO["amostra_calibracao"]
CONFIANCA_MINIMA      = CONFIG_PADRAO["confianca_minima"]
GAP_SECUNDARIA        = CONFIG_PADRAO["gap_secundaria"]
FATOR_CALIBRACAO      = CONFIG_PADRAO["fator_calibracao"]
USAR_DUAS_CATEGORIAS  = CONFIG_PADRAO["usar_duas_categorias"]
RECORTE_TOPO          = CONFIG_PADRAO["recorte_topo"]


def caminho_config(pasta_base):
    return os.path.join(pasta_base, "config.json")


def carregar_config(pasta_base):
    """Lê config.json ao lado do .exe/script. Se não existir, cria com os
    valores padrão. Chaves ausentes ou desconhecidas são toleradas."""
    caminho = caminho_config(pasta_base)
    if not os.path.isfile(caminho):
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(CONFIG_PADRAO, f, indent=2, ensure_ascii=False)
        return dict(CONFIG_PADRAO)

    try:
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
    except Exception:
        dados = {}

    cfg = dict(CONFIG_PADRAO)
    cfg.update({k: v for k, v in dados.items() if k in CONFIG_PADRAO})
    return cfg


def aplicar_config(cfg):
    global PASTA_ORIGEM, PASTA_PERFIS, PASTA_REVISAO, FRAMES_POR_VIDEO, AMOSTRA_CALIBRACAO
    global CONFIANCA_MINIMA, GAP_SECUNDARIA, FATOR_CALIBRACAO
    global USAR_DUAS_CATEGORIAS, RECORTE_TOPO
    PASTA_ORIGEM         = cfg.get("pasta_origem", "")
    PASTA_PERFIS         = cfg["pasta_perfis"]
    PASTA_REVISAO        = cfg["pasta_revisao"]
    FRAMES_POR_VIDEO     = int(cfg["frames_por_video"])
    AMOSTRA_CALIBRACAO   = int(cfg["amostra_calibracao"])
    CONFIANCA_MINIMA     = float(cfg["confianca_minima"])
    GAP_SECUNDARIA       = float(cfg["gap_secundaria"])
    FATOR_CALIBRACAO     = float(cfg["fator_calibracao"])
    USAR_DUAS_CATEGORIAS = bool(cfg["usar_duas_categorias"])
    RECORTE_TOPO         = float(cfg["recorte_topo"])
    tpl.aplicar_config(cfg)


# ══════════════════════════════════════════════
#  NICHOS — PROMPTS VISUAIS (p/ CLIP)
# ══════════════════════════════════════════════

# Frases objetivas (em inglês, o CLIP entende melhor assim) descrevendo
# visualmente cada nicho. "Gerais" NÃO entra aqui de propósito: é o balde
# padrão para vídeo sem confiança suficiente em nenhum nicho específico,
# então nunca compete como categoria visual no CLIP.
#
# Projeto reduzido a 2 nichos apenas: Pets (animais) e Comedia (engraçado).
# Um vídeo pode ser as duas coisas ao mesmo tempo (ex: animal fazendo algo
# engraçado) — nesse caso ele é copiado pras duas pastas.
NICHO_PROMPTS = {
    "Comedia": [
        "a comedy video, a joke or a ridiculous situation making people laugh",
        "people laughing out loud at something funny",
    ],
    "Pets": [
        "a video with a visible animal, such as a dog, cat or other pet",
        "an animal behaving in a funny, cute or interesting way",
    ],
}

GERAIS_FALLBACK = "Gerais"

# Regra simples de compatibilidade: pares que não fazem sentido combinados
# nunca formam a 2ª categoria, mesmo que o score dê empate técnico.
# Edite este conjunto para adicionar/remover restrições. Com só 2 nichos
# (Pets e Comedia), não há par incompatível — os dois podem coexistir.
PARES_INCOMPATIVEIS = set()

EXTENSOES_VIDEO = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".m4v", ".3gp", ".ts", ".mts", ".m2ts", ".vob", ".ogv",
    ".mpg", ".mpeg", ".rm", ".rmvb", ".divx", ".xvid",
}

# ══════════════════════════════════════════════
#  LÓGICA DE CLASSIFICAÇÃO POR CONTEÚDO (CLIP)
# ══════════════════════════════════════════════

_MODELO_LOCK = threading.Lock()
_modelo = None
_preprocess = None
_tokenizer = None
_device = "cuda" if torch.cuda.is_available() else "cpu"
_texto_embeddings = None   # {categoria: tensor normalizado}
_baseline = None           # {categoria: score médio "neutro"} — calibrado por pasta


def carregar_modelo():
    """Carrega o CLIP e pré-calcula os embeddings de texto dos nichos.
    Chamado uma única vez (pode demorar alguns segundos na 1ª vez)."""
    global _modelo, _preprocess, _tokenizer, _texto_embeddings
    with _MODELO_LOCK:
        if _modelo is not None:
            return
        modelo, _, preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32-quickgelu", pretrained="openai"
        )
        modelo.eval().to(_device)
        tokenizer = open_clip.get_tokenizer("ViT-B-32-quickgelu")

        embeddings = {}
        with torch.no_grad():
            for cat, frases in NICHO_PROMPTS.items():
                tokens = tokenizer(frases).to(_device)
                emb = modelo.encode_text(tokens)
                emb = emb / emb.norm(dim=-1, keepdim=True)
                embeddings[cat] = emb.mean(dim=0)
                embeddings[cat] = embeddings[cat] / embeddings[cat].norm()

        _modelo, _preprocess, _tokenizer = modelo, preprocess, tokenizer
        _texto_embeddings = embeddings


def extrair_frames(caminho_video, n=None):
    """Extrai n frames distribuídos ao longo do vídeo como imagens PIL,
    recortando a faixa superior (logo/legenda fixos de conta, comuns em
    vídeo repostado — sem o corte, essa faixa idêntica em todo vídeo
    confunde o CLIP e mascara o conteúdo real abaixo dela).

    A leitura é SEQUENCIAL (não usa cap.set/seek). Muitos vídeos baixados/
    reeditados têm H.264 malformado ("mmco: unref short failure"), e pular
    direto pro frame X com cap.set() nesses arquivos costuma devolver um
    frame corrompido ou congelado (ex: um ícone de "play" parado), fazendo
    o CLIP classificar lixo visual em vez do conteúdo real. Ler frame a
    frame em ordem é mais lento mas muito mais confiável nesses casos."""
    if n is None:
        n = FRAMES_POR_VIDEO
    cap = cv2.VideoCapture(str(caminho_video))
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total <= 0:
            return []
        indices = sorted(set(int(total * (i + 1) / (n + 1)) for i in range(n)))
        frames = []
        alvo = 0
        pos = 0
        while alvo < len(indices):
            ok, frame = cap.read()
            if not ok:
                break
            if pos == indices[alvo]:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame_rgb)
                corte = int(img.height * RECORTE_TOPO)
                img = img.crop((0, corte, img.width, img.height))
                frames.append(img)
                alvo += 1
            pos += 1
        return frames
    finally:
        cap.release()


def _embedding_medio_video(caminho_video):
    """Extrai frames do vídeo e retorna o embedding de imagem médio
    normalizado. Levanta exceção se não der pra ler frames."""
    frames = extrair_frames(caminho_video)
    if not frames:
        raise RuntimeError("não foi possível extrair frames do vídeo")
    with torch.no_grad():
        imagens = torch.stack([_preprocess(f) for f in frames]).to(_device)
        emb_img = _modelo.encode_image(imagens)
        emb_img = emb_img / emb_img.norm(dim=-1, keepdim=True)
        emb_medio = emb_img.mean(dim=0)
        return emb_medio / emb_medio.norm()


NOME_BASELINE_ACUMULADO = "baseline_acumulado.json"


def _caminho_baseline_acumulado(pasta_base):
    return os.path.join(pasta_base, NOME_BASELINE_ACUMULADO)


def _carregar_baseline_acumulado(pasta_base):
    caminho = _caminho_baseline_acumulado(pasta_base)
    if not os.path.isfile(caminho):
        return {"soma": {cat: 0.0 for cat in NICHO_PROMPTS}, "n": 0}
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
        if "soma" not in dados or "n" not in dados:
            raise ValueError("formato inválido")
        for cat in NICHO_PROMPTS:
            dados["soma"].setdefault(cat, 0.0)
        return dados
    except Exception:
        return {"soma": {cat: 0.0 for cat in NICHO_PROMPTS}, "n": 0}


def _salvar_baseline_acumulado(pasta_base, dados):
    try:
        with open(_caminho_baseline_acumulado(pasta_base), "w", encoding="utf-8") as f:
            json.dump(dados, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def calibrar_baseline(pasta, pasta_base=None, amostra=None):
    """Mede o viés 'de base' de cada nicho analisando uma amostra de vídeos
    da pasta a processar, e guarda em _baseline. Sem isso, o CLIP tende a
    favorecer sempre os mesmos nichos, independente do conteúdo real
    (alguns prompts têm similaridade mais alta com qualquer imagem).

    Se pasta_base for informado, a amostra desta execução é ACUMULADA num
    arquivo (baseline_acumulado.json) na raiz de fnkFiltradorNichos, em vez
    de recalcular do zero toda vez — com mais execuções, a média fica mais
    estável e a calibração tende a ficar mais precisa ao longo do tempo.

    A correção aplicada usa só uma fração (FATOR_CALIBRACAO) desse viés
    medido: se um nicho for realmente predominante na pasta (ex: conta de
    humor, maioria dos vídeos são comédia de verdade), corrigir 100%
    cancelaria esse sinal real de prevalência junto com o viés do CLIP."""
    global _baseline
    if amostra is None:
        amostra = AMOSTRA_CALIBRACAO
    carregar_modelo()

    videos = listar_videos(pasta)
    if len(videos) > amostra:
        videos = random.sample(videos, amostra)

    soma_nova = {cat: 0.0 for cat in _texto_embeddings}
    n_novo = 0
    for v in videos:
        try:
            emb = _embedding_medio_video(str(v))
        except Exception:
            continue
        for cat, emb_txt in _texto_embeddings.items():
            soma_nova[cat] += float((emb @ emb_txt).item())
        n_novo += 1

    if pasta_base is None:
        # Sem pasta_base: comportamento isolado (sem acumular no arquivo raiz).
        if n_novo == 0:
            _baseline = {cat: 0.0 for cat in _texto_embeddings}
        else:
            _baseline = {cat: soma_nova[cat] / n_novo for cat in soma_nova}
        return

    acumulado = _carregar_baseline_acumulado(pasta_base)
    for cat in soma_nova:
        acumulado["soma"][cat] = acumulado["soma"].get(cat, 0.0) + soma_nova[cat]
    acumulado["n"] += n_novo
    _salvar_baseline_acumulado(pasta_base, acumulado)

    if acumulado["n"] == 0:
        _baseline = {cat: 0.0 for cat in _texto_embeddings}
    else:
        _baseline = {cat: acumulado["soma"][cat] / acumulado["n"] for cat in _texto_embeddings}


def _par_compativel(cat1, cat2):
    return frozenset({cat1, cat2}) not in PARES_INCOMPATIVEIS


def classificar_video(caminho_video):
    """Regra atual do projeto (só 2 nichos, separação ADITIVA, não
    exclusiva): TODO vídeo vai pra Comedia, sempre — é o destino garantido
    de 100% dos vídeos da pasta. Além disso, se o vídeo também tiver
    pet/animal com confiança suficiente (e essa confiança bater mais forte
    que o sinal de "só comédia"), ele GANHA UMA CÓPIA EXTRA em Pets — sem
    sair de Comedia. Ou seja: de 100 vídeos, os 100 ficam em Comedia, e só
    o subconjunto com pet (ex: 15) também vai parar em Pets.

    Levanta exceção se o vídeo não puder ser analisado (ex: arquivo
    corrompido) — nesse caso o chamador deve mandar p/ revisão."""
    carregar_modelo()
    if _baseline is None:
        raise RuntimeError("calibrar_baseline() precisa ser chamado antes de classificar")

    emb_medio = _embedding_medio_video(caminho_video)
    scores = {
        cat: float((emb_medio @ emb_txt).item()) - FATOR_CALIBRACAO * _baseline[cat]
        for cat, emb_txt in _texto_embeddings.items()
    }

    pets_score = scores.get("Pets", float("-inf"))
    comedia_score = scores.get("Comedia", 0.0)

    resultado = [("Comedia", comedia_score)]
    if pets_score >= CONFIANCA_MINIMA and pets_score > comedia_score:
        resultado.append(("Pets", pets_score))
    return resultado


def listar_videos(pasta):
    return [
        f for f in Path(pasta).iterdir()
        if f.is_file() and f.suffix.lower() in EXTENSOES_VIDEO
    ]


# Pastas dentro de fnkFiltradorNichos que não são pastas de origem de vídeo.
PASTAS_RESERVADAS = {"_logs", "build", "dist", "__pycache__", ".git", ".claude"}


def listar_pastas_origem(pasta_base):
    """Lista as subpastas de fnkFiltradorNichos que podem ser processadas
    (exclui a pasta de revisão, logs e pastas técnicas do projeto)."""
    nome_revisao = Path(PASTA_REVISAO).name
    reservadas = PASTAS_RESERVADAS | {nome_revisao}
    return sorted(
        (d for d in Path(pasta_base).iterdir()
         if d.is_dir() and d.name not in reservadas and not d.name.startswith(".")),
        key=lambda d: d.name.lower()
    )


# ══════════════════════════════════════════════
#  MODOS DE SEPARAÇÃO
# ══════════════════════════════════════════════
# NICHO    → analisa o CONTEÚDO com IA (Pets / Comedia). Lento.
# TEMPLATE → analisa a MOLDURA do vídeo (cor do fundo, 9:16). Rápido.
# AMBOS    → faz as duas coisas; o vídeo ganha uma cópia em cada pasta.

MODO_NICHO    = "nicho"
MODO_TEMPLATE = "template"
MODO_AMBOS    = "ambos"

ROTULO_MODO = {
    MODO_NICHO:    "Somente NICHO",
    MODO_TEMPLATE: "Somente TEMPLATE",
    MODO_AMBOS:    "NICHO + TEMPLATE",
}


def usa_nicho(modo):
    return modo in (MODO_NICHO, MODO_AMBOS)


def usa_template(modo):
    return modo in (MODO_TEMPLATE, MODO_AMBOS)


# Tudo que este programa separa cai dentro dessa pasta, pra não se
# misturar com as outras pastas de fnkPerfis (perfis, planilhas etc.) e
# ficar fácil de achar visualmente.
NOME_PASTA_PROCESSADOS = "VIDEOS PROCESSADOS"
NOME_PASTA_NICHOS      = "Nichos"


def pasta_destino_nicho(nicho):
    """<fnkPerfis>\\VIDEOS PROCESSADOS\\Nichos\\<Pets|Comedia>"""
    return os.path.join(PASTA_PERFIS, NOME_PASTA_PROCESSADOS, NOME_PASTA_NICHOS, nicho)


def pasta_destino_template(nome):
    """<fnkPerfis>\\VIDEOS PROCESSADOS\\Template\\<Preto|Branco|Cinza|Colorido|...>"""
    return os.path.join(PASTA_PERFIS, NOME_PASTA_PROCESSADOS, tpl.NOME_PASTA_TEMPLATES, nome)


def destino_unico(arquivo, pasta_destino):
    dest = Path(pasta_destino) / arquivo.name
    if dest.exists():
        i = 1
        while dest.exists():
            dest = Path(pasta_destino) / f"{arquivo.stem}_{i}{arquivo.suffix}"
            i += 1
    return dest

# ══════════════════════════════════════════════
#  INTERFACE GRÁFICA
# ══════════════════════════════════════════════

COR_BG      = "#141414"
COR_CARD    = "#1e1e1e"
COR_BORDA   = "#2a2a2a"
COR_VERDE   = "#1d9e75"
COR_VERDE_T = "#c0dd97"
COR_AMARELO = "#FAC775"
COR_CINZA   = "#888780"
COR_BRANCO  = "#f0ede8"
COR_ERRO    = "#F09595"
COR_AZUL    = "#85B7EB"


class App(tk.Tk):
    def __init__(self, pasta_base):
        super().__init__()
        self.pasta_base = pasta_base
        self._rodando   = False
        self._vars_pastas = {}   # {Path: tk.IntVar}

        self.title("FNK Separador de Vídeos")
        self.geometry("660x640")
        self.configure(bg=COR_BG)
        self.resizable(False, False)

        # Centralizar na tela
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - 660) // 2
        y = (self.winfo_screenheight() - 640) // 2
        self.geometry(f"+{x}+{y}")

        self._build_selector()

    def _limpar_janela(self):
        for w in self.winfo_children():
            w.destroy()

    # ─── Tela 1: seleção de pastas ────────────

    def _build_selector(self):
        self._limpar_janela()

        hdr = tk.Frame(self, bg="#0d0d0d", pady=16)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🎬  FNK Separador de Vídeos",
                 bg="#0d0d0d", fg=COR_VERDE_T,
                 font=("Segoe UI", 15, "bold")).pack()
        tk.Label(hdr, text=f"Origem: {self.pasta_base}",
                 bg="#0d0d0d", fg=COR_CINZA,
                 font=("Segoe UI", 9)).pack()

        card = tk.Frame(self, bg=COR_CARD, bd=0, padx=22, pady=18)
        card.pack(fill="both", expand=True, padx=18, pady=14)

        tk.Label(card, text="Selecione as pastas que deseja processar",
                 bg=COR_CARD, fg=COR_BRANCO,
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(fill="x")
        tk.Label(card, text="Marque 1, 2, 3 ou quantas quiser — ou use "
                            "\"Selecionar todas\"",
                 bg=COR_CARD, fg=COR_CINZA,
                 font=("Segoe UI", 9), anchor="w").pack(fill="x", pady=(0, 10))

        pastas = listar_pastas_origem(self.pasta_base)
        self.pastas_disponiveis = pastas

        lista_wrap = tk.Frame(card, bg=COR_BORDA, padx=1, pady=1)
        lista_wrap.pack(fill="both", expand=True)

        canvas = tk.Canvas(lista_wrap, bg="#0d1117", highlightthickness=0)
        scroll = tk.Scrollbar(lista_wrap, orient="vertical", command=canvas.yview,
                               bg=COR_CARD, troughcolor=COR_BG)
        lista_frame = tk.Frame(canvas, bg="#0d1117")
        lista_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=lista_frame, anchor="nw", width=580)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self._vars_pastas = {}
        if not pastas:
            tk.Label(lista_frame, text="Nenhuma pasta de origem encontrada.",
                     bg="#0d1117", fg=COR_AMARELO,
                     font=("Segoe UI", 10)).pack(anchor="w", padx=10, pady=10)
        else:
            for pasta in pastas:
                n_videos = len(listar_videos(pasta))
                var = tk.IntVar(value=0)
                sufixo = "vídeo" if n_videos == 1 else "vídeos"
                texto = f"  {pasta.name}   —   {n_videos} {sufixo}"
                cb = tk.Checkbutton(
                    lista_frame, text=texto, variable=var,
                    bg="#0d1117", fg=COR_BRANCO, selectcolor=COR_BORDA,
                    activebackground="#0d1117", activeforeground=COR_VERDE_T,
                    disabledforeground=COR_CINZA,
                    font=("Segoe UI", 10), anchor="w", padx=6, pady=4,
                    state=("normal" if n_videos > 0 else "disabled"),
                )
                cb.pack(fill="x")
                self._vars_pastas[pasta] = var

        # Rodapé
        rod = tk.Frame(self, bg=COR_BG, pady=12, padx=18)
        rod.pack(fill="x", side="bottom")

        tk.Button(
            rod, text="Selecionar todas", command=self._selecionar_todas,
            font=("Segoe UI", 9), bg="#2c2c2a", fg=COR_BRANCO, relief="flat",
            padx=12, pady=6, cursor="hand2",
        ).pack(side="left")

        tk.Button(
            rod, text="Limpar", command=self._limpar_selecao,
            font=("Segoe UI", 9), bg="#2c2c2a", fg=COR_BRANCO, relief="flat",
            padx=12, pady=6, cursor="hand2",
        ).pack(side="left", padx=(8, 0))

        self._btn_processar = tk.Button(
            rod, text="▶  PROCESSAR SELECIONADAS",
            command=self._confirmar_selecao,
            font=("Segoe UI", 11, "bold"),
            bg=COR_VERDE, fg="white", relief="flat",
            padx=20, pady=10, cursor="hand2",
            activebackground="#0f6e56", activeforeground="white",
            state=("normal" if pastas else "disabled"),
        )
        self._btn_processar.pack(side="right")

    def _selecionar_todas(self):
        for pasta, var in self._vars_pastas.items():
            if len(listar_videos(pasta)) > 0:
                var.set(1)

    def _limpar_selecao(self):
        for var in self._vars_pastas.values():
            var.set(0)

    def _confirmar_selecao(self):
        selecionadas = [p for p, v in self._vars_pastas.items() if v.get() == 1]
        if not selecionadas:
            messagebox.showinfo("FNK Separador", "Selecione ao menos uma pasta.")
            return
        self._build_modo(selecionadas)

    # ─── Tela 2: escolha do modo ──────────────

    def _build_modo(self, pastas):
        """Pergunta o que fazer com as pastas escolhidas: separar por
        nicho (conteúdo), por template (moldura) ou pelos dois."""
        self._limpar_janela()

        hdr = tk.Frame(self, bg="#0d0d0d", pady=16)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🎬  FNK Separador de Vídeos",
                 bg="#0d0d0d", fg=COR_VERDE_T,
                 font=("Segoe UI", 15, "bold")).pack()
        n_videos = sum(len(listar_videos(p)) for p in pastas)
        nomes = ", ".join(p.name for p in pastas)
        tk.Label(hdr, text=f"{len(pastas)} pasta(s), {n_videos} vídeo(s): {nomes}",
                 bg="#0d0d0d", fg=COR_CINZA,
                 font=("Segoe UI", 9), wraplength=620).pack()

        card = tk.Frame(self, bg=COR_CARD, bd=0, padx=22, pady=18)
        card.pack(fill="both", expand=True, padx=18, pady=14)

        tk.Label(card, text="Como você quer separar esses vídeos?",
                 bg=COR_CARD, fg=COR_BRANCO,
                 font=("Segoe UI", 12, "bold"), anchor="w").pack(fill="x")
        tk.Label(card, text="Escolha uma das três opções abaixo:",
                 bg=COR_CARD, fg=COR_CINZA,
                 font=("Segoe UI", 9), anchor="w").pack(fill="x", pady=(0, 14))

        opcoes = [
            (MODO_NICHO, "🎯  Somente NICHO",
             "Analisa o que aparece no vídeo (Pets / Comedia) usando IA.\n"
             "Vai para: fnkPerfis\\Pets  e  fnkPerfis\\Comedia\n"
             "Mais demorado — precisa carregar o modelo de IA."),
            (MODO_TEMPLATE, "🎨  Somente TEMPLATE",
             "Analisa a moldura/fundo do vídeo (preto, branco, cinza, colorido)\n"
             "e separa os que são 9:16 preenchendo a tela toda.\n"
             "Vai para: fnkPerfis\\Templates\\...  —  bem mais rápido, sem IA."),
            (MODO_AMBOS, "⚡  NICHO + TEMPLATE",
             "Faz as duas separações de uma vez. Cada vídeo ganha uma cópia\n"
             "na pasta do nicho E outra na pasta da cor do template.\n"
             "É o mais demorado: soma o tempo das duas análises."),
        ]

        for modo, titulo, desc in opcoes:
            bloco = tk.Frame(card, bg="#252525", padx=16, pady=12,
                             highlightthickness=1, highlightbackground=COR_BORDA,
                             cursor="hand2")
            bloco.pack(fill="x", pady=5)

            lbl_t = tk.Label(bloco, text=titulo, bg="#252525", fg=COR_VERDE_T,
                             font=("Segoe UI", 12, "bold"), anchor="w")
            lbl_t.pack(fill="x")
            lbl_d = tk.Label(bloco, text=desc, bg="#252525", fg=COR_CINZA,
                             font=("Segoe UI", 9), anchor="w", justify="left")
            lbl_d.pack(fill="x")

            def escolher(_evento=None, m=modo):
                self._iniciar(pastas, m)

            # O clique vale no bloco inteiro, não só no texto do título.
            for w in (bloco, lbl_t, lbl_d):
                w.bind("<Button-1>", escolher)

            def realce(cor, alvo=bloco, textos=(lbl_t, lbl_d)):
                alvo.configure(bg=cor)
                for w in textos:
                    w.configure(bg=cor)

            for w in (bloco, lbl_t, lbl_d):
                w.bind("<Enter>", lambda e, f=realce: f("#2f3b36"))
                w.bind("<Leave>", lambda e, f=realce: f("#252525"))

        rod = tk.Frame(self, bg=COR_BG, pady=12, padx=18)
        rod.pack(fill="x", side="bottom")
        tk.Button(
            rod, text="←  Voltar", command=self._build_selector,
            font=("Segoe UI", 9), bg="#2c2c2a", fg=COR_BRANCO, relief="flat",
            padx=12, pady=6, cursor="hand2",
        ).pack(side="left")

    def _iniciar(self, pastas, modo):
        self._build_execucao(pastas, modo)
        threading.Thread(target=self._executar_lote, args=(pastas, modo),
                         daemon=True).start()

    # ─── Tela 3: execução ─────────────────────

    def _build_execucao(self, pastas, modo):
        self._limpar_janela()

        hdr = tk.Frame(self, bg="#0d0d0d", pady=16)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🎬  FNK Separador de Vídeos",
                 bg="#0d0d0d", fg=COR_VERDE_T,
                 font=("Segoe UI", 15, "bold")).pack()
        nomes = ", ".join(p.name for p in pastas)
        tk.Label(hdr, text=f"Processando: {nomes}",
                 bg="#0d0d0d", fg=COR_CINZA,
                 font=("Segoe UI", 9), wraplength=620).pack()
        tk.Label(hdr, text=f"Modo: {ROTULO_MODO[modo]}",
                 bg="#0d0d0d", fg=COR_AMARELO,
                 font=("Segoe UI", 9, "bold")).pack()

        card = tk.Frame(self, bg=COR_CARD, bd=0, padx=22, pady=18)
        card.pack(fill="both", expand=True, padx=18, pady=14)

        cnt = tk.Frame(card, bg=COR_CARD)
        cnt.pack(fill="x", pady=(0, 14))

        self._total_v,   self._total_l   = self._stat(cnt, "Vídeos no total", "—")
        self._movidos_v, self._movidos_l = self._stat(cnt, "Movidos",         "0")
        self._revisao_v, self._revisao_l = self._stat(cnt, "Para revisão",    "0")
        self._erros_v,   self._erros_l   = self._stat(cnt, "Erros",           "0")

        tk.Label(card, text="Progresso", bg=COR_CARD, fg=COR_CINZA,
                 font=("Segoe UI", 9), anchor="w").pack(fill="x")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("fnk.Horizontal.TProgressbar",
                        troughcolor=COR_BORDA, background=COR_VERDE,
                        borderwidth=0, thickness=10)
        self._barra = ttk.Progressbar(card, style="fnk.Horizontal.TProgressbar",
                                       mode="determinate", maximum=100)
        self._barra.pack(fill="x", pady=(3, 12))

        self._pct_label = tk.Label(card, text="0%", bg=COR_CARD, fg=COR_CINZA,
                                    font=("Segoe UI", 9), anchor="e")
        self._pct_label.pack(fill="x")

        tk.Label(card, text="Log", bg=COR_CARD, fg=COR_CINZA,
                 font=("Segoe UI", 9), anchor="w").pack(fill="x", pady=(8,3))

        log_frame = tk.Frame(card, bg=COR_BORDA, padx=1, pady=1)
        log_frame.pack(fill="both", expand=True)

        self._log = tk.Text(log_frame, bg="#0d1117", fg=COR_VERDE_T,
                             font=("Consolas", 9), relief="flat",
                             insertbackground="white", wrap="word",
                             state="disabled")
        scroll = tk.Scrollbar(log_frame, command=self._log.yview,
                               bg=COR_CARD, troughcolor=COR_BG)
        self._log.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self._log.pack(fill="both", expand=True)

        self._log.tag_config("ok",   foreground=COR_VERDE_T)
        self._log.tag_config("rev",  foreground=COR_AMARELO)
        self._log.tag_config("err",  foreground=COR_ERRO)
        self._log.tag_config("info", foreground=COR_AZUL)
        self._log.tag_config("head", foreground=COR_BRANCO,
                              font=("Consolas", 9, "bold"))

        rod = tk.Frame(self, bg=COR_BG, pady=12, padx=18)
        rod.pack(fill="x", side="bottom")

        self._btn = tk.Button(
            rod, text="⏳  Processando...",
            font=("Segoe UI", 11, "bold"),
            bg="#2c2c2a", fg="white", relief="flat",
            padx=28, pady=10, state="disabled",
        )
        self._btn.pack(side="left")

        self._status = tk.Label(rod, text="Preparando...",
                                 bg=COR_BG, fg=COR_CINZA,
                                 font=("Segoe UI", 9), anchor="w")
        self._status.pack(side="left", padx=16)

        esperadas = []
        if usa_nicho(modo):
            esperadas += [pasta_destino_nicho(c) for c in NICHO_PROMPTS]
        if usa_template(modo):
            esperadas += [pasta_destino_template(c) for c in tpl.TODOS_TEMPLATES]
        ausentes = [p for p in esperadas if not os.path.isdir(p)]
        if ausentes:
            self._log_add(
                f"⚠  {len(ausentes)} pasta(s) de destino não encontrada(s) — "
                "serão criadas automaticamente.", "rev"
            )
        self._log_add(f"  Modo: {ROTULO_MODO[modo]}", "info")
        self._log_add(
            f"  Destino: {os.path.join(PASTA_PERFIS, NOME_PASTA_PROCESSADOS)}",
            "info"
        )
        self._log_add(f"  Revisão: {PASTA_REVISAO}", "info")
        if usa_nicho(modo):
            self._log_add(
                f"  Nicho: {FRAMES_POR_VIDEO} frames/vídeo | "
                f"confiança mín. {CONFIANCA_MINIMA} | "
                f"fator calibração {FATOR_CALIBRACAO} | "
                f"2 categorias: {'sim' if USAR_DUAS_CATEGORIAS else 'não'}",
                "info"
            )
        if usa_template(modo):
            self._log_add(
                f"  Template: pastas em {NOME_PASTA_PROCESSADOS}\\{tpl.NOME_PASTA_TEMPLATES}\\ | "
                f"{tpl.valor_config('template_frames')} frames/vídeo | "
                f"9:16 com folga de "
                f"{tpl.valor_config('template_tolerancia_916')*100:.0f}%",
                "info"
            )
        self._log_add("", "info")

    def _stat(self, parent, titulo, valor):
        f = tk.Frame(parent, bg="#252525", padx=14, pady=10,
                     highlightthickness=1, highlightbackground=COR_BORDA)
        f.pack(side="left", expand=True, fill="both", padx=4)
        tk.Label(f, text=titulo, bg="#252525", fg=COR_CINZA,
                 font=("Segoe UI", 8)).pack()
        lv = tk.Label(f, text=valor, bg="#252525", fg=COR_BRANCO,
                      font=("Segoe UI", 18, "bold"))
        lv.pack()
        return tk.StringVar(value=valor), lv

    # ─── Helpers ──────────────────────────────

    def _log_add(self, msg, tag="ok"):
        self._log.configure(state="normal")
        self._log.insert("end", msg + "\n", tag)
        self._log.see("end")
        self._log.configure(state="disabled")

    def _atualizar_status(self, msg, cor=COR_CINZA):
        self._status.configure(text=msg, fg=cor)

    # ─── Processamento em lote ────────────────

    def _executar_lote(self, pastas, modo):
        videos_por_pasta = {p: listar_videos(p) for p in pastas}
        total = sum(len(v) for v in videos_por_pasta.values())
        self.after(0, lambda: self._total_l.configure(text=str(total)))

        if not total:
            self._atualizar_status("Nenhum vídeo encontrado nas pastas selecionadas.", COR_AMARELO)
            self._finalizar()
            return

        movidos  = 0
        revisao  = 0
        erros    = 0
        processados = 0
        t0 = time.time()
        log_linhas = []
        csv_linhas = []

        # O modelo de IA só é necessário para a separação por nicho. No
        # modo Somente TEMPLATE ele nem é carregado — é o que faz esse
        # modo começar na hora, em vez de esperar o CLIP subir.
        if usa_nicho(modo):
            self._atualizar_status("Carregando modelo de IA (pode demorar na 1ª vez)...", COR_AMARELO)
            self._log_add("  Carregando modelo de análise de vídeo...", "info")
            try:
                carregar_modelo()
            except Exception as e:
                self._log_add(f"  ✗ Falha ao carregar o modelo de IA: {e}", "err")
                self._atualizar_status("Erro ao preparar modelo de IA.", COR_ERRO)
                self._finalizar()
                return
        else:
            self._log_add("  Modo template: análise direta dos pixels, "
                          "sem modelo de IA (bem mais rápido).", "info")

        self._log_add("─" * 54, "head")
        self._log_add(f"  Início: {datetime.now():%d/%m/%Y %H:%M:%S}", "head")
        self._log_add("─" * 54, "head")

        for pasta in pastas:
            videos = videos_por_pasta[pasta]
            if not videos:
                continue

            self._log_add(f"\n▶ Pasta: {pasta.name} ({len(videos)} vídeo(s))", "head")
            if usa_nicho(modo):
                self._atualizar_status(f"Calibrando modelo para '{pasta.name}'...", COR_AMARELO)
                try:
                    calibrar_baseline(pasta, self.pasta_base)
                    total_acumulado = _carregar_baseline_acumulado(self.pasta_base)["n"]
                    self._log_add(
                        f"  Calibração acumulada: {total_acumulado} vídeo(s) analisados "
                        "no total (desde sempre, guardado na raiz).", "info"
                    )
                except Exception as e:
                    self._log_add(f"  ✗ Falha ao calibrar '{pasta.name}': {e}", "err")
                    continue

            for video in videos:
                processados += 1
                pct = int(processados / total * 100)
                self.after(0, lambda p=pct: self._barra.configure(value=p))
                self.after(0, lambda p=pct: self._pct_label.configure(text=f"{p}%"))
                self.after(0, lambda txt=f"[{pasta.name}] Analisando {processados}/{total}...":
                           self._status.configure(text=txt))

                agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

                # ─── Análise: nicho (IA) e/ou template (pixels) ───
                # Cada análise falha por conta própria. No modo AMBOS, se
                # uma falhar mas a outra funcionar, o vídeo ainda é
                # separado pelo que deu certo — só vai pra revisão quando
                # não sobrar nenhum destino.
                cat_score = []
                info_tpl = None
                falhas = []

                if usa_nicho(modo):
                    try:
                        cat_score = classificar_video(str(video))
                    except Exception as e:
                        falhas.append(f"nicho: {e}")

                if usa_template(modo):
                    try:
                        info_tpl = tpl.analisar_template(str(video))
                    except Exception as e:
                        falhas.append(f"template: {e}")

                # ─── Monta a lista de destinos ───
                alvos = []   # [(rótulo_p/_log, pasta_de_destino)]
                for cat, _score in cat_score:
                    alvos.append((cat, pasta_destino_nicho(cat)))
                if info_tpl is not None:
                    alvos.append((info_tpl["pasta"],
                                  pasta_destino_template(info_tpl["pasta"])))

                cat1, score1 = (cat_score[0] if len(cat_score) > 0 else ("", ""))
                cat2, score2 = (cat_score[1] if len(cat_score) > 1 else ("", ""))
                nome_tpl = info_tpl["pasta"] if info_tpl else ""
                resumo_tpl = info_tpl["resumo"] if info_tpl else ""

                if falhas and alvos:
                    self._log_add(f"  ⚠ Análise parcial de {video.name[:30]} — "
                                  f"{'; '.join(falhas)}", "rev")
                elif falhas:
                    self._log_add(f"  ⚠ Não foi possível analisar {video.name[:30]} — "
                                  f"{'; '.join(falhas)}", "rev")

                try:
                    if alvos:
                        # Copia para todos os destinos ANTES de apagar o
                        # original — se qualquer cópia falhar, o arquivo
                        # de origem continua onde está.
                        destinos = []
                        for rotulo, pasta_dest in alvos:
                            os.makedirs(pasta_dest, exist_ok=True)
                            dest = destino_unico(video, pasta_dest)
                            shutil.copy2(str(video), str(dest))
                            destinos.append((rotulo, dest))

                        os.remove(str(video))

                        movidos += 1
                        rotulos = " + ".join(r for r, _ in destinos)
                        self._log_add(f"  ✓ [{rotulos:<22}] {video.name[:42]}", "ok")
                        for rotulo, dest in destinos:
                            log_linhas.append(f"OK|{pasta.name}|{rotulo}|{video.name}|{dest}")
                        csv_linhas.append([
                            pasta.name, video.name, modo,
                            cat1, f"{score1:.4f}" if score1 != "" else "",
                            cat2, f"{score2:.4f}" if score2 != "" else "",
                            nome_tpl, resumo_tpl,
                            " | ".join(str(d) for _, d in destinos),
                            "OK", "; ".join(falhas), agora,
                        ])
                    else:
                        os.makedirs(PASTA_REVISAO, exist_ok=True)
                        dest = destino_unico(video, PASTA_REVISAO)
                        shutil.move(str(video), str(dest))

                        revisao += 1
                        motivo = "; ".join(falhas) or "confiança insuficiente"
                        self._log_add(f"  ⚠ [REVISÃO               ] {video.name[:42]}", "rev")
                        log_linhas.append(f"REVISAO|{pasta.name}||{video.name}|{dest}")
                        csv_linhas.append([
                            pasta.name, video.name, modo, "", "", "", "",
                            "", "", str(dest), "REVISAO", motivo, agora,
                        ])

                except Exception as e:
                    erros += 1
                    self._log_add(f"  ✗ ERRO: {video.name[:40]} — {e}", "err")
                    log_linhas.append(f"ERRO|{pasta.name}||{video.name}|{e}")
                    csv_linhas.append([
                        pasta.name, video.name, modo, cat1, "", cat2, "",
                        nome_tpl, resumo_tpl, "", "ERRO", str(e), agora,
                    ])

                self.after(0, lambda m=movidos: self._movidos_l.configure(text=str(m)))
                self.after(0, lambda r=revisao: self._revisao_l.configure(text=str(r)))
                self.after(0, lambda e=erros:   self._erros_l.configure(text=str(e)))

        tempo = time.time() - t0
        self._salvar_log(log_linhas, csv_linhas, total, movidos, revisao, erros, tempo)

        self._log_add(f"\n{'═'*54}", "head")
        self._log_add("  SEPARAÇÃO CONCLUÍDA!", "head")
        self._log_add(f"  Total processado : {total}", "head")
        self._log_add(f"  Vídeos separados : {movidos}", "ok")
        self._log_add(f"  Para revisão     : {revisao}", "rev")
        if erros:
            self._log_add(f"  Erros            : {erros}", "err")
        self._log_add(f"  Tempo total      : {tempo:.1f}s", "head")

        # Quantos arquivos caíram em cada pasta de destino.
        por_pasta = {}
        for l in log_linhas:
            if l.startswith("OK|"):
                rotulo = l.split("|")[2]
                por_pasta[rotulo] = por_pasta.get(rotulo, 0) + 1
        if por_pasta:
            self._log_add("  ─ Cópias por pasta ─", "head")
            for rotulo, qtd in sorted(por_pasta.items(), key=lambda x: -x[1]):
                self._log_add(f"    {rotulo:<16} {qtd}", "ok")
        self._log_add(f"{'═'*54}", "head")

        self.after(0, lambda: self._atualizar_status(
            f"✓ Concluído em {tempo:.1f}s — {movidos} movidos, {revisao} para revisão",
            COR_VERDE_T
        ))
        self._finalizar()

    def _salvar_log(self, linhas, csv_linhas, total, movidos, revisao, erros, tempo):
        pasta_log = os.path.join(os.path.dirname(PASTA_REVISAO), "_logs")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            os.makedirs(pasta_log, exist_ok=True)
            nome_txt = f"separacao_lote_{ts}.txt"
            with open(os.path.join(pasta_log, nome_txt), "w", encoding="utf-8") as f:
                f.write(f"FNK Separador — {datetime.now():%d/%m/%Y %H:%M:%S}\n")
                f.write(f"Total: {total} | Movidos: {movidos} | "
                        f"Revisão: {revisao} | Erros: {erros} | "
                        f"Tempo: {tempo:.1f}s\n")
                f.write("─" * 60 + "\n")
                for l in linhas:
                    f.write(l + "\n")

            nome_csv = f"separacao_lote_{ts}.csv"
            with open(os.path.join(pasta_log, nome_csv), "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow([
                    "pasta", "arquivo", "modo",
                    "categoria_1", "score_1", "categoria_2", "score_2",
                    "template", "detalhe_template",
                    "destinos", "status", "motivo", "data_hora",
                ])
                w.writerows(csv_linhas)

            self._log_add(f"\n  Log salvo em: {pasta_log}", "info")

            # Lista só dos vídeos efetivamente movidos, aberta na tela ao final
            # do processamento (o que o usuário pediu pra acompanhar).
            movidos_linhas = [l for l in linhas if l.startswith("OK|")]
            caminho_movidos = os.path.join(pasta_log, f"movidos_{ts}.txt")
            with open(caminho_movidos, "w", encoding="utf-8") as f:
                f.write(f"Vídeos movidos para as pastas de nicho — {datetime.now():%d/%m/%Y %H:%M:%S}\n")
                f.write(f"Total movidos: {movidos}\n")
                f.write("─" * 60 + "\n")
                for l in movidos_linhas:
                    _, pasta_origem, cat, arquivo, dest = l.split("|", 4)
                    f.write(f"[{pasta_origem}] {arquivo}  ->  {cat}\n     {dest}\n")
            self._abrir_arquivo(caminho_movidos)
        except Exception as e:
            self._log_add(f"  ⚠  Não foi possível salvar o log: {e}", "rev")

    def _abrir_arquivo(self, caminho):
        """Abre o arquivo no aplicativo padrão do Windows (ex: Bloco de Notas)."""
        try:
            os.startfile(caminho)
        except Exception as e:
            self._log_add(f"  ⚠  Não foi possível abrir o log na tela: {e}", "rev")

    def _finalizar(self):
        self._rodando = False
        self.after(0, lambda: self._btn.configure(
            state="normal", text="✓  Concluído — Fechar",
            bg="#2c2c2a", command=self.destroy
        ))


# ══════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════

def main():
    # Detecta a pasta onde o executável está rodando — deve ser
    # D:\fnkSocialMidia\fnkFiltradorNichos (ou onde o .py estiver, em dev)
    if getattr(sys, "frozen", False):
        # Modo .exe (PyInstaller)
        pasta_exe = os.path.dirname(sys.executable)
    else:
        # Modo script .py
        pasta_exe = os.path.dirname(os.path.abspath(__file__))

    cfg = carregar_config(pasta_exe)
    aplicar_config(cfg)

    # A pasta com os vídeos a processar pode ser diferente de onde o
    # programa está instalado (ex: .exe na Área de Trabalho, vídeos numa
    # pasta fixa do projeto) — ver "pasta_origem" no config.json.
    pasta_origem_videos = PASTA_ORIGEM.strip() if PASTA_ORIGEM else ""
    pasta_base = Path(pasta_origem_videos) if pasta_origem_videos else Path(pasta_exe)

    # Validações rápidas
    if not pasta_base.is_dir():
        root = tk.Tk(); root.withdraw()
        messagebox.showwarning(
            "FNK Separador",
            f"A pasta de origem dos vídeos não foi encontrada:\n{pasta_base}\n\n"
            "Verifique 'pasta_origem' em config.json."
        )
        root.destroy()
        sys.exit(1)

    if not os.path.isdir(PASTA_PERFIS):
        root = tk.Tk(); root.withdraw()
        messagebox.showwarning(
            "FNK Separador",
            f"A pasta de perfis não foi encontrada:\n{PASTA_PERFIS}\n\n"
            "Verifique o caminho em config.json."
        )
        root.destroy()
        sys.exit(1)

    app = App(pasta_base)
    app.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Última rede de segurança: qualquer erro não previsto aparece numa
        # messagebox em vez de fechar o programa sem explicação nenhuma.
        try:
            root = tk.Tk(); root.withdraw()
            messagebox.showerror("FNK Separador — erro inesperado", str(e))
            root.destroy()
        except Exception:
            pass
        raise
