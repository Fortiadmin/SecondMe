@echo off
rem LauncherV - ingesta manual de las grabaciones de C:\V en los segundos cerebros.
rem 1) Transcribe y saca frames de los videos pendientes, de uno en uno y con
rem    prioridad baja (sin modelo). Ctrl+C lo corta: lo que queda a medias se
rem    repite en la siguiente ejecucion.
rem 0) Comprobacion de salud (salud\salud.py, sin modelo): avisa de lo que lleva
rem    dias parado en C:\V, la bandeja, Know, SecondB y Second Claude.
rem 2) Sugiere modelo y esfuerzo (reglas fijas, sin gastar tokens) y, si quieres,
rem    abre Claude con la skill ingesta-v: convocatoria, revision de frames,
rem    publicacion y consolidacion de lo que haya en la bandeja. Con S, Sonnet
rem    para lo que va a Know y luego Opus para lo que va a SecondB.
chcp 65001 >nul
title LauncherV
cd /d "%~dp0"
set "ONEDRIVE=%USERPROFILE%\OneDrive - FORTIA ENERGIA S.L"
set "DIRS=--add-dir "%ONEDRIVE%\Cajon\Know" --add-dir "%ONEDRIVE%\SecondB""

echo.
echo === Salud de la ingesta y de los cerebros ===
echo.
python salud\salud.py
echo.
echo === 1/2  Transcripcion y frames (un video cada vez) ===
echo.
python ingesta\ingesta_videos.py procesar
echo.
python ingesta\ingesta_videos.py inventario
echo.
python ingesta\ingesta_videos.py bandeja
echo.
python ingesta\ingesta_videos.py pendientes
echo.

echo === 2/2  Clasificar, revisar frames y consolidar con Claude ===
echo.
set "MODELO="
for /f "tokens=1,2" %%a in ('python ingesta\ingesta_videos.py sugerencia --corto') do (
    set "MODELO=%%a"
    set "ESFUERZO=%%b"
)
python ingesta\ingesta_videos.py sugerencia
echo.
if "%MODELO%"=="ninguno" goto fin
if "%MODELO%"=="" goto fin
echo   S = Sonnet para lo que va a Know y, despues, Opus para lo que va a SecondB (esfuerzo alto)
echo   P = abrir Claude con tu configuracion por defecto
echo   N = no abrir Claude
choice /C SPN /M "Opcion"
if errorlevel 3 goto fin
rem El texto va antes de --add-dir: esa opcion admite varias carpetas y se lo comeria.
if errorlevel 2 (
    call claude "Ejecuta la skill ingesta-v" %DIRS%
    goto fin
)
rem S: dos pasadas. Una grabacion sin titulo en el nombre solo sabe su destino al ver la
rem convocatoria: la pasada de Sonnet la deja en la bandeja si es un seguimiento, y la de
rem Opus se abre solo si queda algo.
echo.
echo === Pasada Know (Sonnet). Cierrala con /exit para seguir con SecondB ===
call claude "Ejecuta la skill ingesta-v solo con destino Know" --model sonnet --effort high %DIRS%
set "MODELO="
for /f "tokens=1" %%a in ('python ingesta\ingesta_videos.py sugerencia --corto') do set "MODELO=%%a"
if "%MODELO%"=="ninguno" goto fin
if "%MODELO%"=="" goto fin
echo.
echo === Pasada SecondB (Opus) ===
call claude "Ejecuta la skill ingesta-v solo con destino SecondB" --model opus --effort high %DIRS%

:fin
echo.
pause
