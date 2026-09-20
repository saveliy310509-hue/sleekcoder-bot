@echo off
chcp 65001 > nul
echo Остановка процессов бота...
wmic process where "commandline like '%%main.py%%' or commandline like '%%run.py%%'" call terminate > nul 2>&1
echo Бот успешно остановлен!
timeout /t 2 > nul
