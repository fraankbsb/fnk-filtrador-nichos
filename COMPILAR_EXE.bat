@echo off
title FNK Separador — Compilando .exe
color 0A
echo.
echo  ==========================================
echo   FNK Separador — Gerando .exe
echo  ==========================================
echo.

:: Verifica se Python está instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERRO] Python nao encontrado.
    echo  Baixe em: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Instala PyInstaller e dependencias (torch/open_clip/opencv sao pesadas,
:: a instalacao pode demorar alguns minutos na primeira vez)
echo  Instalando dependencias (isso pode demorar)...
pip install pyinstaller --quiet
pip install -r requirements.txt --quiet

:: Compila o .exe usando o .spec (ja configurado com as dependencias
:: pesadas: torch, open_clip, cv2, PIL)
echo.
echo  Compilando via FNK_Separador-2.spec...
echo.

pyinstaller --clean FNK_Separador-2.spec

if errorlevel 1 (
    echo.
    echo  [ERRO] Falha na compilacao. Veja a mensagem acima.
    pause
    exit /b 1
)

echo.
echo  ==========================================
echo   SUCESSO!
echo  ==========================================
echo.
echo  O arquivo FNK_Separador.exe esta em:
echo  dist\FNK_Separador.exe
echo.
echo  Copie esse .exe para qualquer pasta de nicho
echo  dentro de D:\fnkSocialMidia\fnkFiltradorNichos\
echo  e clique duas vezes para executar.
echo.
pause
