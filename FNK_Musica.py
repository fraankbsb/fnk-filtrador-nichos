#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FNK Música — detecta se o vídeo tem alguma música tocando
=============================================================
Complementa o FNK_Separador e o FNK_Template. Analisa só o ÁUDIO do
vídeo (não a imagem) usando um modelo de IA treinado especificamente
pra reconhecer sons — do jeito que a separação por NICHO usa IA (CLIP)
pra reconhecer o que aparece na imagem.

Por quê IA e não só matemática simples: tentamos primeiro sem IA (só
olhando o volume e o "formato" do som), mas voz humana falando também
tem características parecidas com música em vários momentos — o
resultado errava demais (por exemplo, achava que vídeo só de narração
tinha música). Um modelo treinado com milhares de exemplos reais de
música e de fala acerta muito mais.

O modelo usado é o Cnn14 (rede "PANNs" — Pretrained Audio Neural
Networks), treinado no AudioSet do Google, que já sabe reconhecer 527
tipos de som, incluindo "Music". Só usamos a pontuação dessa categoria.

O peso do modelo (~300MB) é baixado sozinho na primeira vez que essa
separação é usada, e fica guardado no PC pra sempre (não baixa de novo).

Regras de destino:
  - o modelo dá confiança de música acima do limite -> "ComMusica"
  - abaixo do limite, ou vídeo mudo/sem áudio -> "SemMusica"
"""

import os
import threading
import urllib.request
from pathlib import Path

import numpy as np

try:
    import av
except ImportError:  # tratado pelo FNK_Separador com messagebox
    av = None


# ══════════════════════════════════════════════
#  CONFIGURAÇÃO (fundida no config.json principal)
# ══════════════════════════════════════════════

CONFIG_MUSICA_PADRAO = {
    # Quantos segundos de áudio analisar (a partir do começo). O modelo
    # olha o áudio inteiro que for dado a ele; não precisa do vídeo
    # inteiro pra perceber se tem música — isso mantém a análise rápida.
    "musica_duracao_analise": 20.0,
    # Abaixo desse volume (bem baixo), o programa considera "vídeo mudo"
    # e nem chama o modelo de IA.
    "musica_limiar_silencio": 0.002,
    # Confiança mínima (0 a 1) que o modelo precisa dar pra categoria
    # "Music" do AudioSet pra considerar que tem música tocando.
    "musica_limiar_confianca": 0.15,
}

# Nomes das pastas de destino. Ficam dentro de
# <fnkPerfis>\VIDEOS PROCESSADOS\Musica\
NOME_PASTA_MUSICA = "Musica"
MUSICA_COM = "ComMusica"
MUSICA_SEM = "SemMusica"
TODAS_MUSICA = [MUSICA_COM, MUSICA_SEM]

# Preenchidos por aplicar_config() a partir do config.json.
_CFG = dict(CONFIG_MUSICA_PADRAO)


def valor_config(chave):
    """Valor em uso de uma chave de música (já vindo do config.json)."""
    return _CFG.get(chave, CONFIG_MUSICA_PADRAO.get(chave))


def aplicar_config(cfg):
    """Recebe o dicionário completo do config.json e guarda só as chaves
    de música que existirem nele (as demais ficam no padrão)."""
    for chave, padrao in CONFIG_MUSICA_PADRAO.items():
        valor = cfg.get(chave, padrao)
        _CFG[chave] = type(padrao)(valor)


# ══════════════════════════════════════════════
#  MODELO DE IA (Cnn14 / PANNs, treinado no AudioSet)
# ══════════════════════════════════════════════

TAXA_AMOSTRAGEM = 32000  # Hz — a taxa que o modelo Cnn14 espera
INDICE_CLASSE_MUSICA = 137  # "Music" na lista de 527 classes do AudioSet

_PASTA_MODELOS = Path.home() / "panns_data"
_ARQUIVO_MODELO = _PASTA_MODELOS / "Cnn14_mAP=0.431.pth"
_ARQUIVO_LABELS = _PASTA_MODELOS / "class_labels_indices.csv"
_TAMANHO_MINIMO_MODELO = 300_000_000  # bytes — abaixo disso, download incompleto

_URL_MODELO = "https://zenodo.org/record/3987831/files/Cnn14_mAP%3D0.431.pth?download=1"
_URL_LABELS = ("http://storage.googleapis.com/us_audioset/youtube_corpus/"
               "v1/csv/class_labels_indices.csv")

_MODELO_LOCK = threading.Lock()
_tagger = None


def modelo_ja_baixado():
    """True se o peso do modelo de música já está no PC (não precisa
    baixar de novo). Usado pra avisar o usuário antes de começar."""
    return (_ARQUIVO_MODELO.is_file()
            and _ARQUIVO_MODELO.stat().st_size >= _TAMANHO_MINIMO_MODELO)


def _baixar(url, destino, callback_progresso=None):
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(destino.suffix + ".baixando")

    def relatorio(bloco_num, tam_bloco, tam_total):
        if callback_progresso and tam_total > 0:
            pct = min(100, int(bloco_num * tam_bloco * 100 / tam_total))
            callback_progresso(pct)

    urllib.request.urlretrieve(str(url), str(tmp), reporthook=relatorio)
    tmp.replace(destino)


def carregar_modelo(callback_status=None):
    """Baixa (se preciso) e carrega o modelo de IA de áudio. Chamado uma
    única vez (pode demorar bastante na 1ª vez, por causa do download de
    ~300MB — depois disso é rápido)."""
    global _tagger
    with _MODELO_LOCK:
        if _tagger is not None:
            return

        def avisar(msg):
            if callback_status:
                callback_status(msg)

        if not _ARQUIVO_LABELS.is_file():
            avisar("Baixando lista de categorias de som (~15 KB)...")
            _baixar(_URL_LABELS, _ARQUIVO_LABELS)

        if not modelo_ja_baixado():
            avisar("Baixando modelo de IA de áudio (~300 MB, só na 1ª vez)...")
            _baixar(_URL_MODELO, _ARQUIVO_MODELO,
                    lambda pct: avisar(f"Baixando modelo de IA de áudio... {pct}%"))

        avisar("Carregando modelo de IA de áudio...")
        # Import tardio: assim o download acima roda ANTES do panns_inference
        # tentar ler os arquivos (ele tentaria baixar sozinho via "wget",
        # que não existe no Windows, e travaria com erro confuso).
        #
        # O panns_inference importa matplotlib só por causa de uma função
        # de plotar gráfico que a gente nunca usa — força o backend "Agg"
        # (sem janela nenhuma) antes desse import, senão ele tenta abrir
        # uma janela gráfica à toa (e complica empacotar o .exe).
        import matplotlib
        matplotlib.use("Agg")
        import torch
        from panns_inference import AudioTagging
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _tagger = AudioTagging(checkpoint_path=str(_ARQUIVO_MODELO), device=device)


# ══════════════════════════════════════════════
#  LEITURA DO ÁUDIO
# ══════════════════════════════════════════════

def _extrair_audio_mono(caminho_video, duracao_max):
    """Decodifica a trilha de áudio (se existir) pra mono, na taxa de
    amostragem que o modelo espera, até duracao_max segundos. Devolve
    None se o vídeo não tiver nenhuma trilha de áudio."""
    container = av.open(str(caminho_video))
    try:
        if not container.streams.audio:
            return None
        stream = container.streams.audio[0]
        resampler = av.AudioResampler(format="s16", layout="mono", rate=TAXA_AMOSTRAGEM)
        partes = []
        total = 0
        limite = int(TAXA_AMOSTRAGEM * duracao_max)
        for frame in container.decode(stream):
            for rframe in resampler.resample(frame):
                arr = rframe.to_ndarray().astype(np.float32) / 32768.0
                partes.append(arr.reshape(-1))
                total += arr.size
            if total >= limite:
                break
        if not partes:
            return None
        return np.concatenate(partes)[:limite]
    finally:
        container.close()


# ══════════════════════════════════════════════
#  ANÁLISE DE UM VÍDEO
# ══════════════════════════════════════════════

def analisar_musica(caminho_video):
    """Analisa o áudio do vídeo e devolve um dicionário com o resultado:

        {
          "pasta":       nome da pasta de destino ("ComMusica"/"SemMusica"),
          "tem_musica":  True/False,
          "tem_audio":   True/False (False = vídeo mudo, sem trilha),
          "confianca":   confiança do modelo (0 a 1) pra categoria "Music",
          "resumo":      texto curto pro log,
        }

    Levanta exceção se o vídeo não puder ser lido (o chamador manda o
    arquivo pra pasta de revisão).
    """
    if av is None:
        raise RuntimeError("biblioteca de áudio (av) não está instalada")

    duracao_max = float(_CFG["musica_duracao_analise"])
    limiar_silencio = float(_CFG["musica_limiar_silencio"])
    limiar_confianca = float(_CFG["musica_limiar_confianca"])

    audio = _extrair_audio_mono(caminho_video, duracao_max)
    if audio is None or len(audio) < TAXA_AMOSTRAGEM // 2:
        return {
            "pasta": MUSICA_SEM, "tem_musica": False, "tem_audio": False,
            "confianca": None,
            "resumo": "sem trilha de áudio",
        }

    pico = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    if pico < limiar_silencio:
        return {
            "pasta": MUSICA_SEM, "tem_musica": False, "tem_audio": True,
            "confianca": None,
            "resumo": "áudio praticamente mudo",
        }

    if _tagger is None:
        carregar_modelo()

    entrada = audio[None, :].astype(np.float32)  # (1, amostras) — 1 "clipe"
    saida, _embedding = _tagger.inference(entrada)
    confianca = float(saida[0, INDICE_CLASSE_MUSICA])

    tem_musica = confianca >= limiar_confianca
    pasta = MUSICA_COM if tem_musica else MUSICA_SEM

    return {
        "pasta": pasta,
        "tem_musica": tem_musica,
        "tem_audio": True,
        "confianca": confianca,
        "resumo": f"confiança de música: {confianca:.3f} (limite: {limiar_confianca:.2f})",
    }
