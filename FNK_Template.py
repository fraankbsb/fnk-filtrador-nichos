#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FNK Template — análise do "template" (moldura/fundo) do vídeo
==============================================================
Complementa o FNK_Separador. Enquanto a separação por NICHO olha o
CONTEÚDO do vídeo (com IA/CLIP, pesado e lento), a separação por TEMPLATE
olha só a FORMA do vídeo: se ele tem faixas de fundo em volta da imagem
(o "template"), qual a cor dessas faixas, e se o vídeo é 9:16 preenchendo
a tela toda sozinho, sem moldura nenhuma.

Isso é feito com OpenCV puro (matemática simples sobre os pixels das
bordas) — não usa IA, não baixa modelo e roda muito mais rápido.

Regras de destino:
  - tem moldura e ela é escura   -> "Preto"
  - tem moldura e ela é clara    -> "Branco"
  - tem moldura em tom neutro    -> "Cinza"
  - tem moldura colorida         -> "Colorido"
  - sem moldura e o arquivo é 9:16 -> "9x16 Cheio"
  - sem moldura e outra proporção  -> "SemTemplate"
"""

import numpy as np

try:
    import cv2
except ImportError:  # tratado pelo FNK_Separador com messagebox
    cv2 = None


# ══════════════════════════════════════════════
#  CONFIGURAÇÃO (fundida no config.json principal)
# ══════════════════════════════════════════════

CONFIG_TEMPLATE_PADRAO = {
    # Quantos frames do vídeo são analisados para decidir o template.
    # Poucos frames bastam: a moldura é fixa o vídeo inteiro.
    "template_frames": 7,
    # Quanto a proporção pode fugir de 9:16 e ainda contar como 9:16.
    # 0.04 = 4% de folga (cobre 1080x1920, 720x1280, 1082x1920 etc).
    "template_tolerancia_916": 0.04,
    # Faixa menor que isso (2% do lado) é considerada "sem moldura" —
    # evita que 1 ou 2 linhas de pixel escuras da compressão de vídeo
    # sejam confundidas com um template de verdade.
    "template_margem_minima": 0.02,
    # Fração mínima dos pixels de uma linha que precisa bater com a cor
    # predominante dela pra essa linha contar como parte da moldura.
    # Alto de propósito (85%): usa a MEDIANA da própria linha (tolera uma
    # legenda ocupando uma fatia dela sem quebrar a detecção), mas exige
    # que seja a GRANDE maioria — um valor baixo aqui (testado com vídeo
    # real) também classificava roupa escura ou fundo desfocado comum de
    # vídeo como se fosse moldura, o que é errado.
    "template_fracao_minima_faixa": 0.85,
    # O quanto a cor de uma linha pode se afastar da cor do começo da
    # faixa sem quebrar a faixa (cobre fundos com leve degradê).
    "template_tolerancia_cor": 20.0,
    # Saturação abaixo disso = cor neutra (preto/branco/cinza).
    "template_saturacao_neutra": 45,
    # Brilho (0-255): abaixo disso é Preto, acima do outro é Branco.
    "template_preto_max": 60,
    "template_branco_min": 200,
}

# Nomes das pastas de destino. Ficam dentro de
# <fnkPerfis>\VIDEOS PROCESSADOS\Template\
NOME_PASTA_TEMPLATES = "Template"
TEMPLATE_PRETO       = "Preto"
TEMPLATE_BRANCO      = "Branco"
TEMPLATE_CINZA       = "Cinza"
TEMPLATE_COLORIDO    = "Colorido"
TEMPLATE_SEM         = "SemTemplate"
TEMPLATE_916         = "9x16 Cheio"

TODOS_TEMPLATES = [
    TEMPLATE_PRETO, TEMPLATE_BRANCO, TEMPLATE_CINZA,
    TEMPLATE_COLORIDO, TEMPLATE_SEM, TEMPLATE_916,
]

PROPORCAO_916 = 9 / 16


# Preenchidos por aplicar_config() a partir do config.json.
_CFG = dict(CONFIG_TEMPLATE_PADRAO)


def valor_config(chave):
    """Valor em uso de uma chave de template (já vinda do config.json)."""
    return _CFG.get(chave, CONFIG_TEMPLATE_PADRAO.get(chave))


def aplicar_config(cfg):
    """Recebe o dicionário completo do config.json e guarda só as chaves
    de template que existirem nele (as demais ficam no padrão)."""
    for chave, padrao in CONFIG_TEMPLATE_PADRAO.items():
        valor = cfg.get(chave, padrao)
        _CFG[chave] = type(padrao)(valor)


# ══════════════════════════════════════════════
#  LEITURA DOS FRAMES
# ══════════════════════════════════════════════

def _orientacao_meta(cap):
    """Ângulo de rotação gravado no arquivo (celular gravando deitado).
    O OpenCV normalmente NÃO aplica essa rotação sozinho, então um vídeo
    1920x1080 marcado como girado 90° é, na prática, 1080x1920 (vertical).
    Sem isso, a checagem de 9:16 erraria nesses arquivos."""
    try:
        prop = getattr(cv2, "CAP_PROP_ORIENTATION_META", None)
        if prop is None:
            return 0
        return int(cap.get(prop) or 0) % 360
    except Exception:
        return 0


def _ler_sequencial(cap, total, indices):
    """Leitura frame a frame desde o começo até o último índice pedido.
    Lenta, mas funciona em arquivo com índice quebrado."""
    frames = []
    alvo = 0
    pos = 0
    while alvo < len(indices):
        ok, frame = cap.read()
        if not ok:
            break
        if pos >= indices[alvo]:
            frames.append(frame)
            alvo += 1
        pos += 1
    return frames


def _frames_iguais(frames):
    """True se todos os frames forem praticamente a mesma imagem. É o
    sintoma de decoder travado depois de um seek em arquivo H.264
    malformado (devolve sempre o mesmo quadro congelado) — nesse caso a
    leitura precisa ser refeita do jeito lento."""
    if len(frames) < 2:
        return False
    base = frames[0].astype(np.int16)
    for f in frames[1:]:
        if f.shape != frames[0].shape:
            return False
        if float(np.abs(f.astype(np.int16) - base).mean()) > 0.5:
            return False
    return True


def extrair_frames_bgr(caminho_video, n=None, parar_quando=None):
    """Lê até n frames espalhados pelo vídeo, INTEIROS (sem recortar nada).

    Diferente do extrair_frames() do FNK_Separador — que corta o topo
    porque ali o objetivo é analisar o conteúdo — aqui a borda é
    justamente o que interessa, então o frame vem completo.

    Estratégia: pular direto pra cada ponto (seek) é ~2x mais rápido que
    ler o vídeo inteiro. Em arquivo H.264 malformado o seek pode devolver
    quadro congelado; por isso, se vierem poucos frames ou todos idênticos
    entre si, a leitura é refeita sequencialmente (lenta e confiável).
    Para MOLDURA isso é seguro: a faixa de fundo é a mesma o vídeo todo,
    então não faz diferença de qual instante o frame veio.

    parar_quando é uma função opcional que recebe a lista de frames lidos
    até agora e devolve True quando já dá pra decidir — assim um vídeo de
    moldura óbvia não paga o custo de ler todos os n frames.

    Retorna (lista_de_frames_BGR, rotacao_em_graus, usou_modo_lento).
    O último valor avisa que os frames NÃO são os que passaram pelo
    parar_quando — quem chamou precisa refazer a medição.
    """
    if n is None:
        n = int(_CFG["template_frames"])
    cap = cv2.VideoCapture(str(caminho_video))
    try:
        rot = _orientacao_meta(cap)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total <= 0:
            return [], rot, False
        indices = sorted(set(int(total * (i + 1) / (n + 1)) for i in range(n)))

        frames = []
        for idx in indices:
            try:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ok, frame = cap.read()
            except Exception:
                ok, frame = False, None
            if ok and frame is not None:
                frames.append(frame)
                # O callback é chamado a CADA frame (ele acompanha a
                # medição frame a frame); a checagem de frames congelados
                # só entra quando ele já quer parar, por ser a mais cara.
                if (parar_quando is not None and parar_quando(frames)
                        and len(frames) >= 3 and not _frames_iguais(frames)):
                    return frames, rot, False

        if len(frames) >= 2 and not _frames_iguais(frames):
            return frames, rot, False

        # Seek não foi confiável neste arquivo: refaz do jeito lento.
        cap.release()
        cap = cv2.VideoCapture(str(caminho_video))
        return _ler_sequencial(cap, total, indices), rot, True
    finally:
        cap.release()


# ══════════════════════════════════════════════
#  DETECÇÃO DAS FAIXAS DE FUNDO (a "moldura")
# ══════════════════════════════════════════════

def _contar_faixa(bloco, frac_min, tol_cor):
    """Recebe as linhas (ou colunas) já na ordem de varredura, de fora pra
    dentro — array (N, comprimento, 3) — e conta quantas delas seguidas
    fazem parte de uma faixa lisa de fundo.

    Uma linha entra na faixa se: (1) a GRANDE MAIORIA dos pixels dela bate
    com a cor predominante DELA MESMA — usa a mediana da própria linha,
    não a média, porque a mediana ignora uma legenda ocupando uma fatia
    da linha sem estragar a conta (a média seria puxada pra um tom
    intermediário) — e (2) essa cor predominante é parecida com a da
    primeira linha da faixa (tolera degradê leve, quebra em mudança de
    cor real, tipo quando a faixa acaba e começa o vídeo de verdade).

    Antes isso era feito com desvio padrão da linha inteira, mas uma
    legenda de 1-2 linhas de texto em cima da faixa fazia o desvio
    disparar e a moldura não era detectada (achava que a linha já não
    era mais fundo). Trocar pra "maioria dos pixels bate com a mediana"
    resolve isso mantendo a exigência alta (85% por padrão) — baixo
    demais e vira falso positivo com roupa escura ou fundo desfocado
    comum de vídeo.

    Feito de uma vez com numpy (e não num for linha a linha) porque a
    conta roda em milhares de linhas por frame — em Python puro isso
    sozinho custava alguns segundos por vídeo.

    Devolve (quantidade_de_linhas, medianas_dessas_linhas) — o segundo
    valor é usado depois pra estimar a cor da moldura sem contaminação de
    texto (ver _margens_frame): junta as medianas de CADA linha aceita
    (já limpas do texto daquela linha) em vez de misturar todos os
    pixels crus de uma vez, que reintroduziria o mesmo problema do texto
    puxando a cor pra um tom errado.
    """
    if bloco.shape[0] == 0:
        return 0, None
    mediana = np.median(bloco, axis=1)                          # (N, 3)
    dist_da_mediana = np.abs(bloco - mediana[:, None, :]).max(axis=2)  # (N, comprimento)
    frac_perto = (dist_da_mediana <= tol_cor).mean(axis=1)              # (N,)
    lisa = frac_perto >= frac_min
    if not bool(lisa[0]):
        return 0, None
    perto = np.abs(mediana - mediana[0]).max(axis=1) <= tol_cor
    ok = lisa & perto
    ok[0] = True                                     # a 1ª define a referência
    n = int(bloco.shape[0]) if bool(ok.all()) else int(np.argmax(~ok))
    return n, (mediana[:n] if n > 0 else None)


def _margens_frame(frame):
    """Mede a moldura de UM frame.

    Retorna (topo, base, esquerda, direita, cor_BGR_da_moldura) em pixels,
    ou None se o frame inteiro for liso (ex: transição em fade, tela preta)
    — frame assim não diz nada sobre a moldura e é descartado.
    """
    frac_min = float(_CFG["template_fracao_minima_faixa"])
    tol_cor = float(_CFG["template_tolerancia_cor"])

    f = frame.astype(np.float32)
    h, w = f.shape[:2]
    limite_v = h // 2
    limite_h = w // 2

    topo, med_topo = _contar_faixa(f[:limite_v], frac_min, tol_cor)
    base, med_base = _contar_faixa(f[h - limite_v:][::-1], frac_min, tol_cor)
    if topo >= limite_v and base >= limite_v:
        return None  # frame liso inteiro

    meio = f[topo:h - base]
    if meio.shape[0] <= 0:
        return None
    # transpose(1,0,2): vira "lista de colunas" pra usar a mesma contagem.
    colunas = meio.transpose(1, 0, 2)
    esq, med_esq = _contar_faixa(colunas[:limite_h], frac_min, tol_cor)
    dir_, med_dir = _contar_faixa(colunas[w - limite_h:][::-1], frac_min, tol_cor)
    if esq >= limite_h and dir_ >= limite_h:
        return None

    # Cor "central" da moldura: mediana das medianas de cada linha/coluna
    # aceita (não joga todos os pixels crus num saco só). Duas etapas de
    # mediana em vez de uma: a primeira (dentro de _contar_faixa) já
    # limpou o texto de CADA linha; juntar os pixels crus de novo aqui
    # reintroduziria o halo de compressão ao redor do texto e puxaria a
    # cor pra um tom errado (ex: branco virando "cinza").
    partes = [m for m in (med_topo, med_base, med_esq, med_dir) if m is not None]
    cor = np.median(np.concatenate(partes), axis=0) if partes else None

    return topo, base, esq, dir_, cor


def classificar_cor(cor_bgr):
    """Traduz uma cor BGR para o nome da pasta: Preto, Branco, Cinza ou
    Colorido."""
    pixel = np.uint8([[[int(round(cor_bgr[0])), int(round(cor_bgr[1])),
                        int(round(cor_bgr[2]))]]])
    h, s, v = cv2.cvtColor(pixel, cv2.COLOR_BGR2HSV)[0][0]
    if int(s) >= int(_CFG["template_saturacao_neutra"]):
        return TEMPLATE_COLORIDO
    if int(v) <= int(_CFG["template_preto_max"]):
        return TEMPLATE_PRETO
    if int(v) >= int(_CFG["template_branco_min"]):
        return TEMPLATE_BRANCO
    return TEMPLATE_CINZA


def e_916(largura, altura, tolerancia=None):
    """True se a proporção largura/altura for 9:16 dentro da folga."""
    if altura <= 0:
        return False
    if tolerancia is None:
        tolerancia = float(_CFG["template_tolerancia_916"])
    prop = largura / altura
    return abs(prop - PROPORCAO_916) <= PROPORCAO_916 * tolerancia


# ══════════════════════════════════════════════
#  ANÁLISE COMPLETA DE UM VÍDEO
# ══════════════════════════════════════════════

def analisar_template(caminho_video):
    """Analisa o vídeo e devolve um dicionário com o resultado:

        {
          "pasta":      nome da pasta de destino (ex: "Preto"),
          "tem_moldura": True/False,
          "cheio_916":  True/False,
          "largura", "altura", "proporcao",
          "margens":    (topo, base, esquerda, direita) em pixels,
          "cor_bgr":    cor média da moldura ou None,
          "resumo":     texto curto pro log,
        }

    Levanta exceção se o vídeo não puder ser lido (o chamador manda o
    arquivo pra pasta de revisão).
    """
    if cv2 is None:
        raise RuntimeError("OpenCV (cv2) não está instalado")

    # As margens de cada frame são medidas conforme os frames chegam. Se
    # 3 frames seguidos derem a mesma moldura (caso da imensa maioria dos
    # vídeos, cuja moldura é fixa), a leitura para por aí — decodificar
    # vídeo é a parte cara, e ler menos frames corta o tempo pela metade.
    parciais = []

    def _medir(frames_ate_agora):
        parciais.append(_margens_frame(frames_ate_agora[-1]))
        ultimas = [m for m in parciais[-3:] if m is not None]
        if len(ultimas) < 3:
            return False
        return all(
            all(abs(m[i] - ultimas[0][i]) <= 2 for i in range(4))
            for m in ultimas[1:]
        )

    frames, rotacao, modo_lento = extrair_frames_bgr(caminho_video,
                                                     parar_quando=_medir)
    if not frames:
        raise RuntimeError("não foi possível extrair frames do vídeo")

    h, w = frames[0].shape[:2]
    # Vídeo marcado como girado 90°/270°: as medidas reais são invertidas.
    largura, altura = (h, w) if rotacao in (90, 270) else (w, h)

    # Se o extrator caiu no modo lento, os frames não passaram pelo _medir
    # acima — as medidas guardadas são de outros frames e não valem.
    if modo_lento or len(parciais) != len(frames):
        parciais = [_margens_frame(f) for f in frames]
    medidas = [m for m in parciais if m is not None]
    if not medidas:
        # Todos os frames lisos: é um vídeo de cor sólida do começo ao fim.
        raise RuntimeError("vídeo sem imagem utilizável (todos os frames lisos)")

    # Mediana entre os frames: um frame com cena escura encostando na
    # borda não é suficiente pra inventar uma moldura que não existe.
    topo = int(np.median([m[0] for m in medidas]))
    base = int(np.median([m[1] for m in medidas]))
    esq  = int(np.median([m[2] for m in medidas]))
    dir_ = int(np.median([m[3] for m in medidas]))

    minimo = float(_CFG["template_margem_minima"])
    min_v = max(1, int(h * minimo))
    min_h = max(1, int(w * minimo))
    tem_moldura = (topo >= min_v or base >= min_v or esq >= min_h or dir_ >= min_h)

    cores = [m[4] for m in medidas if m[4] is not None]
    cor = np.median(np.array(cores), axis=0) if cores else None

    cheio_916 = (not tem_moldura) and e_916(largura, altura)

    if tem_moldura and cor is not None:
        pasta = classificar_cor(cor)
    elif cheio_916:
        pasta = TEMPLATE_916
    else:
        pasta = TEMPLATE_SEM

    proporcao = largura / altura if altura else 0.0
    if tem_moldura:
        resumo = (f"moldura {topo}/{base}/{esq}/{dir_}px · "
                  f"{largura}x{altura}")
    else:
        resumo = f"sem moldura · {largura}x{altura} ({proporcao:.3f})"

    return {
        "pasta": pasta,
        "tem_moldura": tem_moldura,
        "cheio_916": cheio_916,
        "largura": largura,
        "altura": altura,
        "proporcao": proporcao,
        "margens": (topo, base, esq, dir_),
        "cor_bgr": None if cor is None else tuple(float(c) for c in cor),
        "rotacao": rotacao,
        "resumo": resumo,
    }
