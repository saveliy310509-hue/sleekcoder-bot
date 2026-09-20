@echo off
chcp 65001 > nul
title Telegram Bot - Download Plugins (Auto-Reload)
echo ========================================================
echo   Запуск Telegram-бота с автоматическим перезапуском
echo ========================================================
echo.
python run.py
pause
