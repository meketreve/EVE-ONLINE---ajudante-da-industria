@echo off
title EVE Industry Tool - Instalacao
setlocal EnableDelayedExpansion

echo ============================================
echo  EVE Industry Tool - Instalacao
echo ============================================
echo.

:: ── 1. Verifica Python ─────────────────────────────────────────────────────
echo [1/3] Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo [!] Python nao encontrado no PATH.
    echo.
    echo     Opcoes:
    echo       A^) Baixar e instalar Python automaticamente ^(requer internet^)
    echo       B^) Abrir python.org para download manual
    echo       C^) Cancelar
    echo.
    set /p OPCAO="Escolha [A/B/C]: "
    if /i "!OPCAO!"=="A" goto :instalar_python
    if /i "!OPCAO!"=="B" (
        start https://www.python.org/downloads/
        echo.
        echo Instale o Python e execute este script novamente.
        echo IMPORTANTE: marque "Add Python to PATH" durante a instalacao.
        pause
        exit /b 1
    )
    echo Instalacao cancelada.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] !PYVER! encontrado.
goto :instalar_deps

:: ── Instalacao automatica do Python via winget ─────────────────────────────
:instalar_python
echo.
echo [>] Tentando instalar Python via winget...
winget --version >nul 2>&1
if errorlevel 1 (
    echo [!] winget nao disponivel neste sistema.
    echo     Abra https://www.python.org/downloads/ e instale manualmente.
    echo     Marque "Add Python to PATH" durante a instalacao.
    pause
    exit /b 1
)

winget install --id Python.Python.3.12 --source winget --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo [!] Falha ao instalar Python via winget.
    echo     Tente instalar manualmente em https://www.python.org/downloads/
    pause
    exit /b 1
)

echo.
echo [OK] Python instalado. Reinicie o script para continuar.
echo      (O PATH precisa ser atualizado — feche e reabra o prompt.)
pause
exit /b 0

:: ── 2. Instala dependencias ────────────────────────────────────────────────
:instalar_deps
echo.
echo [2/3] Instalando dependencias do projeto...
echo       (pip install -r requirements.txt)
echo.

cd /d "%~dp0eve_industry_tool"
set PYTHONIOENCODING=utf-8

python -m pip install --upgrade pip --quiet
if errorlevel 1 (
    echo [!] Falha ao atualizar pip.
    pause
    exit /b 1
)

python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [!] Falha ao instalar dependencias.
    echo     Verifique sua conexao com a internet e tente novamente.
    pause
    exit /b 1
)

echo.
echo [OK] Dependencias instaladas com sucesso.

:: ── 3. Verifica .env ───────────────────────────────────────────────────────
echo.
echo [3/3] Verificando arquivo de configuracao (.env)...

if not exist ".env" (
    echo [!] Arquivo .env nao encontrado.
    echo.
    echo     Crie o arquivo eve_industry_tool\.env com o seguinte conteudo:
    echo.
    echo       EVE_CLIENT_ID=seu_client_id
    echo       EVE_CLIENT_SECRET=seu_client_secret
    echo       EVE_CALLBACK_URL=http://localhost:8765/auth/callback
    echo       SECRET_KEY=uma_chave_longa_e_aleatoria
    echo.
    echo     Obtenha suas credenciais em: https://developers.eveonline.com/
    echo.
) else (
    echo [OK] .env encontrado.
)

echo.
echo ============================================
echo  Instalacao concluida!
echo.
echo  Proximos passos:
echo    1. Configure o .env (se ainda nao fez)
echo    2. Execute 1_importar_sde.bat  (apenas na 1a vez)
echo    3. Execute 3_iniciar.bat       (para usar o app)
echo.
echo  Ou use EVE_Industry_Tool.bat para menu completo.
echo ============================================
echo.
pause
