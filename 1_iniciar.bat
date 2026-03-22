@echo off
title EVE Industry Tool

echo ============================================
echo  EVE Industry Tool
echo ============================================
echo.

cd /d "%~dp0eve_industry_tool"

:: Verifica se o .env existe
if not exist ".env" (
    echo [!] Arquivo .env nao encontrado.
    echo     Crie o arquivo .env com suas credenciais EVE SSO.
    echo.
    echo     Exemplo:
    echo       EVE_CLIENT_ID=seu_client_id
    echo       EVE_CLIENT_SECRET=seu_client_secret
    echo       EVE_CALLBACK_URL=http://localhost:8765/auth/callback
    echo       SECRET_KEY=uma_chave_longa_e_aleatoria
    echo.
    pause
    exit /b 1
)

echo [✓] Iniciando EVE Industry Tool...
echo     A janela do aplicativo abrira automaticamente.
echo.
echo  Pressione Ctrl+C para encerrar.
echo ============================================
echo.

python -m app.main

pause
