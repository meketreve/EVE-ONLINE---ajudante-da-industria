@echo off
echo ============================================
echo  EVE Industry Tool - Importar dados estaticos
echo ============================================
echo.
echo Fontes (tentadas em ordem):
echo   1. EVERef reference-data  (~13 MB)  - preferida
echo   2. Fuzzwork SQLite SDE    (~130 MB) - fallback
echo.
echo Opcoes:
echo   --force-download    Rebaixa mesmo com cache existente
echo   --source fuzzwork   Pula EVERef e usa Fuzzwork direto
echo   --skip-download     Usa apenas cache local
echo.
pause

cd /d "%~dp0eve_industry_tool"
python scripts/import_sde.py %*

echo.
pause
