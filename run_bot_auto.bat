@echo off
chcp 65001 >nul
title Telegram Shop Bot — launcher

cd /d "%~dp0"

echo.
echo == Checking Python ==
where python >nul 2>&1
if errorlevel 1 (
  echo Python not found. Please install Python 3.10+ from https://python.org
  pause
  exit /b 1
)

echo.
echo == Creating virtual environment ==
if not exist ".venv" (
  python -m venv .venv
)

echo.
echo == Activating virtual environment ==
call .venv\Scripts\activate.bat

echo.
echo == Installing dependencies ==
if exist "requirements.txt" (
  pip install -r requirements.txt
) else (
  pip install "python-telegram-bot>=21.6" python-dotenv
)

echo.
echo == Starting bot ==
python shop_bot.py

echo.
echo Bot finished. Press any key to close...
pause
