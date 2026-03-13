@echo off
echo ============================================
echo  EVE Industry Tool - Atualizar Mercados
echo ============================================
echo.
echo Opcoes de execucao:
echo   (padrao)               atualiza lista de estruturas + cache de precos
echo   --so-estruturas        atualiza apenas a lista de estruturas
echo   --so-precos            atualiza apenas o cache de precos
echo.
echo Fonte de descoberta de estruturas (--so-estruturas ou padrao):
echo   --fonte ambos          usa Corp + Universo + Assets  [padrao]
echo   --fonte assets         usa apenas GET /characters/{id}/assets/
echo                          (estruturas onde voce tem ITEMS — melhor para null-sec)
echo   --fonte corp           usa apenas GET /corporations/{id}/structures/
echo                          (estruturas que a corp POSSUI com mercado ativo)
echo   --fonte universo       usa apenas GET /universe/structures/?filter=market
echo                          (estruturas onde ja usou o mercado no jogo)
echo.
echo Outros filtros:
echo   --character "Nome"     filtra por personagem especifico
echo   --structure ID         filtra por estrutura especifica (apenas precos)
echo   --limpar               remove estruturas antes de re-importar
echo.
echo Requisitos:
echo   - Servidor iniciado ao menos uma vez (personagem logado)
echo   - Scopes necessarios:
echo       esi-corporations.read_structures.v1  (fonte corp)
echo       esi-universe.read_structures.v1      (fonte universo)
echo       esi-markets.structure_markets.v1     (cache de precos)
echo.
pause

cd /d "%~dp0eve_industry_tool"

REM Detecta flags de controle de etapa
set RUN_ESTRUTURAS=1
set RUN_PRECOS=1

echo %* | findstr /i "\-\-so-estruturas" >nul && set RUN_PRECOS=0
echo %* | findstr /i "\-\-so-precos"     >nul && set RUN_ESTRUTURAS=0

REM --- Etapa 1: Lista de estruturas ---
if %RUN_ESTRUTURAS%==1 (
    echo.
    echo ============================================
    echo  Etapa 1/2 - Atualizando lista de estruturas
    echo ============================================
    python scripts/atualizar_estruturas.py %*
    if errorlevel 1 (
        echo.
        echo [!] Falha na etapa 1. Verifique os erros acima.
        pause
        exit /b 1
    )
)

REM --- Etapa 2: Cache de precos ---
if %RUN_PRECOS%==1 (
    echo.
    echo ============================================
    echo  Etapa 2/2 - Atualizando cache de precos
    echo ============================================
    python scripts/atualizar_precos_mercado.py %*
    if errorlevel 1 (
        echo.
        echo [!] Falha na etapa 2. Verifique os erros acima.
        pause
        exit /b 1
    )
)

echo.
echo ============================================
echo  Concluido!
echo ============================================
pause
