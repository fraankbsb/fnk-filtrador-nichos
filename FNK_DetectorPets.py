#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FNK Detector de Pets
=====================
Modo separado do FNK_Separador: em vez de classificar em todos os nichos
e mover os vídeos, este script só verifica se cada vídeo tem pet/animal
visível e, se tiver, CRIA UMA CÓPIA em D:\\fnkSocialMidia\\fnkPerfis\\Pets\\

Os demais vídeos (sem pet) são ignorados — não vão pra nenhuma pasta.

REGRA IMPORTANTE: nenhum vídeo é removido ou movido da pasta de origem,
em nenhuma hipótese. É sempre cópia, e a pasta raiz nunca perde arquivos.
"""

import os, sys, shutil, threading, time
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import FNK_Separador as fs

NOME_PET = "Pets"


def contem_pet(caminho_video):
    """Retorna (True/False, score_calibrado_de_pets).

    IMPORTANTE: Pets só é considerado presente se ele vencer (ou quase
    empatar com) a categoria mais forte do vídeo — usar só um limiar fixo
    isolado (score_pets >= confianca_minima) se mostrou falho na prática:
    como vários nichos têm um viés de similaridade alto com qualquer frame
    de vídeo (mesmo problema de calibração descrito em FNK_Separador), quase
    todo vídeo passava no limiar isolado, gerando muitos falsos positivos
    (ex: uma cena de árbitro de tênis marcada como 'pet'). Por isso
    reaproveitamos a mesma lógica de ranking do classificador principal."""
    resultado = fs.classificar_video(caminho_video)  # [(categoria, score), ...]
    categorias = {cat for cat, _ in resultado}
    pets_score = next((s for c, s in resultado if c == NOME_PET), None)
    if pets_score is None:
        # Pets não ficou entre as categorias vencedoras: calcula só p/ log.
        emb_medio = fs._embedding_medio_video(caminho_video)
        pets_score = float((emb_medio @ fs._texto_embeddings[NOME_PET]).item()) \
            - fs.FATOR_CALIBRACAO * fs._baseline[NOME_PET]
    return NOME_PET in categorias, pets_score


class AppDetectorPets(tk.Tk):
    def __init__(self, pasta_base, pasta_entrada_padrao=None, pasta_saida_padrao=None):
        super().__init__()
        self.pasta_base = pasta_base
        self.pasta_entrada = pasta_entrada_padrao
        self.pasta_saida = pasta_saida_padrao or os.path.join(fs.PASTA_PERFIS, NOME_PET)

        self.title("FNK Detector de Pets")
        self.geometry("660x480")
        self.configure(bg=fs.COR_BG)
        self.resizable(False, False)
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 660) // 2
        y = (self.winfo_screenheight() - 480) // 2
        self.geometry(f"+{x}+{y}")

        self._build_selector()

    def _limpar_janela(self):
        for w in self.winfo_children():
            w.destroy()

    # ─── Tela 1: escolha de pasta de entrada/saída ────────────

    def _build_selector(self):
        self._limpar_janela()
        hdr = tk.Frame(self, bg="#0d0d0d", pady=16)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🐾  FNK Detector de Pets",
                 bg="#0d0d0d", fg=fs.COR_VERDE_T,
                 font=("Segoe UI", 15, "bold")).pack()
        tk.Label(hdr, text="Copia vídeos com pet/animal da entrada para a saída",
                 bg="#0d0d0d", fg=fs.COR_CINZA,
                 font=("Segoe UI", 9)).pack()

        card = tk.Frame(self, bg=fs.COR_CARD, bd=0, padx=22, pady=18)
        card.pack(fill="both", expand=True, padx=18, pady=14)

        tk.Label(card, text="Pasta de entrada (onde estão os vídeos a analisar)",
                 bg=fs.COR_CARD, fg=fs.COR_BRANCO,
                 font=("Segoe UI", 10, "bold"), anchor="w").pack(fill="x", pady=(0, 4))
        f_in = tk.Frame(card, bg=fs.COR_CARD)
        f_in.pack(fill="x", pady=(0, 14))
        self._lbl_entrada = tk.Label(
            f_in, text=self.pasta_entrada or "(nenhuma selecionada)",
            bg="#0d1117", fg=fs.COR_VERDE_T if self.pasta_entrada else fs.COR_CINZA,
            font=("Consolas", 9), anchor="w", padx=8, pady=8,
        )
        self._lbl_entrada.pack(side="left", fill="x", expand=True)
        tk.Button(f_in, text="Procurar...", command=self._escolher_entrada,
                  font=("Segoe UI", 9), bg="#2c2c2a", fg=fs.COR_BRANCO, relief="flat",
                  padx=12, pady=8, cursor="hand2").pack(side="left", padx=(6, 0))

        tk.Label(card, text="Pasta de saída (onde as cópias com pet vão parar)",
                 bg=fs.COR_CARD, fg=fs.COR_BRANCO,
                 font=("Segoe UI", 10, "bold"), anchor="w").pack(fill="x", pady=(0, 4))
        f_out = tk.Frame(card, bg=fs.COR_CARD)
        f_out.pack(fill="x", pady=(0, 14))
        self._lbl_saida = tk.Label(
            f_out, text=self.pasta_saida,
            bg="#0d1117", fg=fs.COR_VERDE_T,
            font=("Consolas", 9), anchor="w", padx=8, pady=8,
        )
        self._lbl_saida.pack(side="left", fill="x", expand=True)
        tk.Button(f_out, text="Procurar...", command=self._escolher_saida,
                  font=("Segoe UI", 9), bg="#2c2c2a", fg=fs.COR_BRANCO, relief="flat",
                  padx=12, pady=8, cursor="hand2").pack(side="left", padx=(6, 0))

        tk.Label(card,
                 text="Vídeos com pet/animal são COPIADOS pra pasta de saída — "
                      "nada é removido/movido da pasta de entrada, em nenhuma hipótese.",
                 bg=fs.COR_CARD, fg=fs.COR_CINZA,
                 font=("Segoe UI", 9), anchor="w", wraplength=580,
                 justify="left").pack(fill="x", pady=(10, 0))

        self._info_entrada = tk.Label(card, text="", bg=fs.COR_CARD, fg=fs.COR_AMARELO,
                                       font=("Segoe UI", 9), anchor="w", justify="left")
        self._info_entrada.pack(fill="x", pady=(10, 0))
        self._atualizar_info_entrada()

        rod = tk.Frame(self, bg=fs.COR_BG, pady=12, padx=18)
        rod.pack(fill="x", side="bottom")
        self._btn_processar = tk.Button(
            rod, text="🐾  DETECTAR PETS",
            command=self._confirmar_selecao,
            font=("Segoe UI", 11, "bold"),
            bg=fs.COR_VERDE, fg="white", relief="flat",
            padx=20, pady=10, cursor="hand2",
            activebackground="#0f6e56", activeforeground="white",
        )
        self._btn_processar.pack(side="right")

    def _atualizar_info_entrada(self):
        if self.pasta_entrada and os.path.isdir(self.pasta_entrada):
            n = len(fs.listar_videos(self.pasta_entrada))
            self._info_entrada.configure(
                text=f"{n} vídeo(s) encontrado(s) na pasta de entrada.")
        else:
            self._info_entrada.configure(text="")

    def _escolher_entrada(self):
        pasta = filedialog.askdirectory(
            title="Escolha a pasta de entrada",
            initialdir=self.pasta_entrada or self.pasta_base,
        )
        if pasta:
            self.pasta_entrada = pasta
            self._lbl_entrada.configure(text=pasta, fg=fs.COR_VERDE_T)
            self._atualizar_info_entrada()

    def _escolher_saida(self):
        pasta = filedialog.askdirectory(
            title="Escolha a pasta de saída",
            initialdir=self.pasta_saida,
        )
        if pasta:
            self.pasta_saida = pasta
            self._lbl_saida.configure(text=pasta)

    def _confirmar_selecao(self):
        if not self.pasta_entrada or not os.path.isdir(self.pasta_entrada):
            messagebox.showinfo("FNK Detector de Pets", "Selecione uma pasta de entrada válida.")
            return
        if not self.pasta_saida:
            messagebox.showinfo("FNK Detector de Pets", "Selecione uma pasta de saída.")
            return
        pastas = [Path(self.pasta_entrada)]
        self._build_execucao(pastas)
        threading.Thread(target=self._executar_lote, args=(pastas,), daemon=True).start()

    # ─── Tela 2: execução ─────────────────────

    def _build_execucao(self, pastas):
        self._limpar_janela()
        hdr = tk.Frame(self, bg="#0d0d0d", pady=16)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🐾  FNK Detector de Pets",
                 bg="#0d0d0d", fg=fs.COR_VERDE_T,
                 font=("Segoe UI", 15, "bold")).pack()
        nomes = ", ".join(p.name for p in pastas)
        tk.Label(hdr, text=f"Analisando: {nomes}",
                 bg="#0d0d0d", fg=fs.COR_CINZA,
                 font=("Segoe UI", 9), wraplength=620).pack()

        card = tk.Frame(self, bg=fs.COR_CARD, bd=0, padx=22, pady=18)
        card.pack(fill="both", expand=True, padx=18, pady=14)

        cnt = tk.Frame(card, bg=fs.COR_CARD)
        cnt.pack(fill="x", pady=(0, 14))
        self._total_v, self._total_l = self._stat(cnt, "Vídeos analisados", "—")
        self._pets_v,  self._pets_l  = self._stat(cnt, "Com pet (copiados)", "0")
        self._erros_v, self._erros_l = self._stat(cnt, "Erros", "0")

        tk.Label(card, text="Progresso", bg=fs.COR_CARD, fg=fs.COR_CINZA,
                 font=("Segoe UI", 9), anchor="w").pack(fill="x")
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("fnk.Horizontal.TProgressbar",
                        troughcolor=fs.COR_BORDA, background=fs.COR_VERDE,
                        borderwidth=0, thickness=10)
        self._barra = ttk.Progressbar(card, style="fnk.Horizontal.TProgressbar",
                                       mode="determinate", maximum=100)
        self._barra.pack(fill="x", pady=(3, 12))
        self._pct_label = tk.Label(card, text="0%", bg=fs.COR_CARD, fg=fs.COR_CINZA,
                                    font=("Segoe UI", 9), anchor="e")
        self._pct_label.pack(fill="x")

        tk.Label(card, text="Log", bg=fs.COR_CARD, fg=fs.COR_CINZA,
                 font=("Segoe UI", 9), anchor="w").pack(fill="x", pady=(8, 3))
        log_frame = tk.Frame(card, bg=fs.COR_BORDA, padx=1, pady=1)
        log_frame.pack(fill="both", expand=True)
        self._log = tk.Text(log_frame, bg="#0d1117", fg=fs.COR_VERDE_T,
                             font=("Consolas", 9), relief="flat",
                             insertbackground="white", wrap="word", state="disabled")
        scroll = tk.Scrollbar(log_frame, command=self._log.yview,
                               bg=fs.COR_CARD, troughcolor=fs.COR_BG)
        self._log.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self._log.pack(fill="both", expand=True)
        self._log.tag_config("ok", foreground=fs.COR_VERDE_T)
        self._log.tag_config("skip", foreground=fs.COR_CINZA)
        self._log.tag_config("err", foreground=fs.COR_ERRO)
        self._log.tag_config("info", foreground=fs.COR_AZUL)
        self._log.tag_config("head", foreground=fs.COR_BRANCO, font=("Consolas", 9, "bold"))

        rod = tk.Frame(self, bg=fs.COR_BG, pady=12, padx=18)
        rod.pack(fill="x", side="bottom")
        self._btn = tk.Button(rod, text="⏳  Processando...", font=("Segoe UI", 11, "bold"),
                               bg="#2c2c2a", fg="white", relief="flat", padx=28, pady=10, state="disabled")
        self._btn.pack(side="left")
        self._status = tk.Label(rod, text="Preparando...", bg=fs.COR_BG, fg=fs.COR_CINZA,
                                 font=("Segoe UI", 9), anchor="w")
        self._status.pack(side="left", padx=16)

        self._log_add(f"  Destino (só cópia, origem intacta): {self.pasta_saida}\n", "info")

    def _stat(self, parent, titulo, valor):
        f = tk.Frame(parent, bg="#252525", padx=14, pady=10,
                     highlightthickness=1, highlightbackground=fs.COR_BORDA)
        f.pack(side="left", expand=True, fill="both", padx=4)
        tk.Label(f, text=titulo, bg="#252525", fg=fs.COR_CINZA, font=("Segoe UI", 8)).pack()
        lv = tk.Label(f, text=valor, bg="#252525", fg=fs.COR_BRANCO, font=("Segoe UI", 18, "bold"))
        lv.pack()
        return tk.StringVar(value=valor), lv

    def _log_add(self, msg, tag="ok"):
        self._log.configure(state="normal")
        self._log.insert("end", msg + "\n", tag)
        self._log.see("end")
        self._log.configure(state="disabled")

    def _atualizar_status(self, msg, cor=None):
        self._status.configure(text=msg, fg=cor or fs.COR_CINZA)

    # ─── Processamento ────────────────────────

    def _executar_lote(self, pastas):
        videos_por_pasta = {p: fs.listar_videos(p) for p in pastas}
        total = sum(len(v) for v in videos_por_pasta.values())
        self.after(0, lambda: self._total_l.configure(text=str(total)))
        if not total:
            self._atualizar_status("Nenhum vídeo encontrado.", fs.COR_AMARELO)
            self._finalizar()
            return

        pets = erros = processados = 0
        t0 = time.time()
        linhas_log = []

        self._atualizar_status("Carregando modelo de IA...", fs.COR_AMARELO)
        self._log_add("  Carregando modelo de análise de vídeo...", "info")
        try:
            fs.carregar_modelo()
        except Exception as e:
            self._log_add(f"  ✗ Falha ao carregar o modelo: {e}", "err")
            self._atualizar_status("Erro ao carregar modelo.", fs.COR_ERRO)
            self._finalizar()
            return

        for pasta in pastas:
            videos = videos_por_pasta[pasta]
            if not videos:
                continue
            self._log_add(f"\n▶ Pasta: {pasta.name} ({len(videos)} vídeo(s))", "head")
            self._atualizar_status(f"Calibrando para '{pasta.name}'...", fs.COR_AMARELO)
            try:
                fs.calibrar_baseline(pasta, self.pasta_base)
            except Exception as e:
                self._log_add(f"  ✗ Falha ao calibrar '{pasta.name}': {e}", "err")
                continue

            for video in videos:
                processados += 1
                pct = int(processados / total * 100)
                self.after(0, lambda p=pct: self._barra.configure(value=p))
                self.after(0, lambda p=pct: self._pct_label.configure(text=f"{p}%"))
                self.after(0, lambda t=f"[{pasta.name}] Analisando {processados}/{total}...":
                           self._status.configure(text=t))

                try:
                    tem_pet, score = contem_pet(str(video))
                except Exception as e:
                    erros += 1
                    self._log_add(f"  ✗ ERRO: {video.name[:40]} — {e}", "err")
                    linhas_log.append(f"ERRO|{pasta.name}|{video.name}|{e}")
                    self.after(0, lambda e=erros: self._erros_l.configure(text=str(e)))
                    continue

                if tem_pet:
                    try:
                        pasta_dest = self.pasta_saida
                        os.makedirs(pasta_dest, exist_ok=True)
                        dest = fs.destino_unico(video, pasta_dest)
                        shutil.copy2(str(video), str(dest))  # cópia — original nunca é tocado
                        pets += 1
                        self._log_add(f"  🐾 [PET {score:.3f}] {video.name[:44]}", "ok")
                        linhas_log.append(f"PET|{pasta.name}|{video.name}|{dest}|{score:.4f}")
                    except Exception as e:
                        erros += 1
                        self._log_add(f"  ✗ ERRO ao copiar: {video.name[:34]} — {e}", "err")
                        linhas_log.append(f"ERRO|{pasta.name}|{video.name}|{e}")
                else:
                    self._log_add(f"     [sem pet {score:.3f}] {video.name[:44]}", "skip")
                    linhas_log.append(f"SEM_PET|{pasta.name}|{video.name}||{score:.4f}")

                self.after(0, lambda p=pets: self._pets_l.configure(text=str(p)))
                self.after(0, lambda e=erros: self._erros_l.configure(text=str(e)))

        tempo = time.time() - t0
        self._salvar_log(linhas_log, total, pets, erros, tempo)

        self._log_add(f"\n{'═'*54}", "head")
        self._log_add("  DETECÇÃO CONCLUÍDA!", "head")
        self._log_add(f"  Total analisado : {total}", "head")
        self._log_add(f"  Com pet (copiados) : {pets}", "ok")
        self._log_add(f"  Sem pet (ignorados): {total - pets - erros}", "skip")
        if erros:
            self._log_add(f"  Erros           : {erros}", "err")
        self._log_add(f"  Tempo total     : {tempo:.1f}s", "head")
        self._log_add("  Nenhum arquivo foi removido das pastas de origem.", "info")
        self._log_add(f"{'═'*54}", "head")

        self.after(0, lambda: self._atualizar_status(
            f"✓ Concluído em {tempo:.1f}s — {pets} com pet, copiados", fs.COR_VERDE_T
        ))
        self._finalizar()

    def _salvar_log(self, linhas, total, pets, erros, tempo):
        pasta_log = os.path.join(os.path.dirname(fs.PASTA_REVISAO), "_logs")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            os.makedirs(pasta_log, exist_ok=True)
            caminho = os.path.join(pasta_log, f"deteccao_pets_{ts}.txt")
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(f"FNK Detector de Pets — {datetime.now():%d/%m/%Y %H:%M:%S}\n")
                f.write(f"Total: {total} | Com pet: {pets} | Erros: {erros} | Tempo: {tempo:.1f}s\n")
                f.write("Nenhum arquivo foi removido das pastas de origem.\n")
                f.write("─" * 60 + "\n")
                for l in linhas:
                    f.write(l + "\n")
            self._log_add(f"\n  Log salvo em: {pasta_log}", "info")
            try:
                os.startfile(caminho)
            except Exception:
                pass
        except Exception as e:
            self._log_add(f"  ⚠  Não foi possível salvar o log: {e}", "skip")

    def _finalizar(self):
        self.after(0, lambda: self._btn.configure(
            state="normal", text="✓  Concluído — Fechar",
            bg="#2c2c2a", command=self.destroy
        ))


def main():
    if getattr(sys, "frozen", False):
        pasta_exe = os.path.dirname(sys.executable)
    else:
        pasta_exe = os.path.dirname(os.path.abspath(__file__))

    cfg = fs.carregar_config(pasta_exe)
    fs.aplicar_config(cfg)

    if not os.path.isdir(fs.PASTA_PERFIS):
        root = tk.Tk(); root.withdraw()
        messagebox.showwarning(
            "FNK Detector de Pets",
            f"A pasta de perfis não foi encontrada:\n{fs.PASTA_PERFIS}\n\n"
            "Verifique o caminho em config.json."
        )
        root.destroy()
        sys.exit(1)

    # Sugestão padrão: Comédia -> Pets (edite/troque na tela se quiser outra).
    entrada_padrao = os.path.join(fs.PASTA_PERFIS, "Comedia")
    saida_padrao = os.path.join(fs.PASTA_PERFIS, NOME_PET)
    if not os.path.isdir(entrada_padrao):
        entrada_padrao = None

    app = AppDetectorPets(pasta_exe, entrada_padrao, saida_padrao)
    app.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        try:
            root = tk.Tk(); root.withdraw()
            messagebox.showerror("FNK Detector de Pets — erro inesperado", str(e))
            root.destroy()
        except Exception:
            pass
        raise
