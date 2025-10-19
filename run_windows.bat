@echo off
cd /d %~dp0
python --version || (echo Требуется Python 3.10+ & pause & exit /b)
pip install -r requirements.txt
if "%TELEGRAM_BOT_TOKEN%"=="" set /p TELEGRAM_BOT_TOKEN=Введите TELEGRAM_BOT_TOKEN: 
setx TELEGRAM_BOT_TOKEN "%TELEGRAM_BOT_TOKEN%"
python main.py
pause
