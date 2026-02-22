@echo off
chcp 65001 >nul
title XiaoLiuRen - Divination Tool
color 0A

:menu
cls
echo.
echo      ======================================
echo          XiaoLiuRen - Ma Qian Ke
necho      ======================================
echo.
echo      [1] Divination Now (Current Time)
echo      [2] Custom Time Divination
echo      [3] Six Palaces Details
echo      [4] Help
echo      [0] Exit
echo.
echo      ======================================
set /p choice=Select [0-4]: 

if "%choice%"=="1" goto now
if "%choice%"=="2" goto custom
if "%choice%"=="3" goto detail
if "%choice%"=="4" goto help
if "%choice%"=="0" exit
goto menu

:now
cls
echo.
echo      Calculating current time...
python "%~dp0xiaoliuren.py"
echo.
pause
goto menu

:custom
cls
echo.
echo      ============ Custom Time ============
echo.
set /p year=Year (e.g. 2024): 
set /p month=Month (1-12): 
set /p day=Day (1-31): 
set /p hour=Hour (0-23): 
echo.
python "%~dp0xiaoliuren.py" %year% %month% %day% %hour%
echo.
pause
goto menu

:detail
cls
echo.
echo      ========= Six Palaces Details =========
echo.
echo   [Da An]     Good - Everything goes well
echo   [Liu Lian]  Fair - Delays, need patience
echo   [Su Xi]     Good - Joy comes quickly
echo   [Chi Kou]   Bad  - Quarrels, be careful
echo   [Xiao Ji]   Good - Small success, smooth
echo   [Kong Wang] Bad  - Empty, nothing gained
echo.
pause
goto menu

:help
cls
echo.
echo      ============ How to Use ============
echo.
echo   XiaoLiuRen is a traditional Chinese
echo   divination method created by Zhuge Liang.
echo.
echo   Method:
echo   1. Start from Da An (1st month), count to target month
echo   2. From month palace, count to target day
echo   3. From day palace, count to target hour
echo.
echo   Palace Order: Da An - Liu Lian - Su Xi
echo                Chi Kou - Xiao Ji - Kong Wang
echo.
pause
goto menu
