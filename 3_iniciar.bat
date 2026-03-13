@echo off
title EVE Industry Tool

echo ============================================
echo  EVE Industry Tool
echo ============================================
echo.

:: Verifica se a porta 8000 ja esta em uso e mata o processo
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    echo [!] Porta 8000 em uso pelo processo %%a. Encerrando...
    taskkill /PID %%a /F >nul 2>&1
    timeout /t 1 /nobreak >nul
)

cd /d "%~dp0eve_industry_tool"

:: Verifica se o .env existe
if not exist ".env" (
    echo [!] Arquivo .env nao encontrado.
    echo     Copie .env.example para .env e preencha com suas credenciais EVE.
    echo.
    pause
    exit /b 1
)

echo [✓] Iniciando servidor...
echo.
echo  Acesse no navegador:
echo  http://localhost:8000
echo.
echo  Pressione Ctrl+C para encerrar.
echo ============================================
echo.

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

pause
