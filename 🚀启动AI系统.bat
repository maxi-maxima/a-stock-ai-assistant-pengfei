@echo off
chcp 65001
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
title 🧠 AI 交易分身 - 启动控制台
color 0A

echo.
echo ========================================================
echo       🚀 正在启动 AI 交易分身 (AI Trading Avatar)
echo ========================================================
echo.
echo  [1/3] 正在唤醒量化分析引擎...
echo  [2/3] 正在加载 Tushare/AkShare 数据接口...
echo  [3/3] 正在打开战术指挥室...
echo.
echo  请稍候，浏览器将自动弹出...
echo.
echo  (如需关闭系统，请直接关闭此窗口)
echo ========================================================
echo.

streamlit run dashboard.py

if %errorlevel% neq 0 (
    color 0C
    echo.
    echo ❌ 启动失败！请检查是否安装了依赖库或路径是否正确。
    echo 错误代码: %errorlevel%
    pause
)
