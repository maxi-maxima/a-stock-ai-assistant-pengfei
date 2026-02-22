@echo off
chcp 65001 >nul
title 小六壬 - 诸葛亮马前课
color 0A

:menu
cls
echo.
echo      ======================================
echo         小六壬 · 马前课
echo         诸葛亮掐指一算
echo      ======================================
echo.
echo      [1] 立即推算(当前时间)
echo      [2] 指定时间推算
echo      [3] 六宫详解
echo      [4] 使用说明
echo      [0] 退出
echo.
echo      ======================================
set /p choice=请选择[0-4]: 

if "%choice%"=="1" goto now
if "%choice%"=="2" goto custom
if "%choice%"=="3" goto detail
if "%choice%"=="4" goto help
if "%choice%"=="0" exit
goto menu

:now
cls
echo.
echo      正在推算当前时间...
python "%~dp0xiaoliuren.py"
echo.
pause
goto menu

:custom
cls
echo.
echo      ==============指定时间推算==============
echo.
set /p year=请输入年份(如2024): 
set /p month=请输入月份(1-12): 
set /p day=请输入日期(1-31): 
set /p hour=请输入小时(0-23): 
echo.
python "%~dp0xiaoliuren.py" %year% %month% %day% %hour%
echo.
pause
goto menu

:detail
cls
echo.
echo      ==============小六壬六宫详解=============
echo.
echo   [大安] 吉 - 事事昌，求财在坤方
echo   [留连]平 - 事难成，求谋日未明
echo   [速喜] 吉 - 喜来临，求财向南行
echo   [赤口]凶 - 主口舌，是非须慎防
echo   [小吉] 吉 - 最吉昌，路上好商量
echo   [空亡]凶 - 事不祥，阴人多乖张
echo.
pause
goto menu

:help
cls
echo.
echo      ==============使用方法================
echo.
echo   小六壬是诸葛亮创造的占卜术
echo.
echo   推算方法:
echo   1. 从大安(正月)开始，顺时针数至目标月
echo   2. 从月落宫开始，顺时针数至目标日
echo   3. 从日落宫开始，顺时针数至目标时辰
echo.
echo   六宫顺序: 大安-留连-速喜-赤口-小吉-空亡
echo.
pause
goto menu
