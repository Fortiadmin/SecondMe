@echo off
rem IngestaV - abre Claude con la skill ingesta-v sobre lo que ya hay en la bandeja
rem (el paso 2 de LauncherV, sin volver a transcribir). Sugiere modelo y esfuerzo
rem con las mismas reglas fijas que LauncherV.
chcp 65001 >nul
title IngestaV
cd /d "%~dp0"
set "ONEDRIVE=%USERPROFILE%\OneDrive - FORTIA ENERGIA S.L"
set "DIRS=--add-dir "%ONEDRIVE%\Cajon\Know" --add-dir "%ONEDRIVE%\SecondB""

set "MODELO="
for /f "tokens=1,2" %%a in ('python ingesta\ingesta_videos.py sugerencia --corto') do (
    set "MODELO=%%a"
    set "ESFUERZO=%%b"
)
python ingesta\ingesta_videos.py sugerencia
echo.
if "%MODELO%"=="ninguno" goto vacia
if "%MODELO%"=="" goto vacia
rem El texto va antes de --add-dir: esa opcion admite varias carpetas y se lo comeria.
call claude "Ejecuta la skill ingesta-v" --model %MODELO% --effort %ESFUERZO% %DIRS%
goto fin

:vacia
echo   La bandeja esta vacia: lanza antes LauncherV para transcribir las grabaciones.

:fin
echo.
pause
