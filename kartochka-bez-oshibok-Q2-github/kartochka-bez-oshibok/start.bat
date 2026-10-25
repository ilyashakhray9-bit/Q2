@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto run
where py >nul 2>nul
if errorlevel 1 goto usepython
py -3 -m venv .venv
if errorlevel 1 goto failed
goto install
:usepython
python -m venv .venv
if errorlevel 1 goto failed
:install
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
:run
".venv\Scripts\python.exe" -c "import streamlit, PIL, pytesseract" >nul 2>nul
if errorlevel 1 goto install
echo.
title Карточка без ошибок Q2
echo Открываем «Карточка без ошибок Q2». Не закрывайте это окно во время работы.
echo Если браузер не открылся: http://127.0.0.1:8502
echo Вверху страницы должна быть крупная метка Q2. Старый Q1 на 8501 — другая версия.
echo Для остановки нажмите Ctrl+C.
".venv\Scripts\python.exe" -m streamlit run app.py --server.port 8502 --server.address 127.0.0.1 --browser.gatherUsageStats false
if errorlevel 1 goto failed
exit /b 0
:failed
echo.
echo Не удалось запустить приложение. Проверьте Python 3.12–3.14 и интернет при первой установке.
echo Подробная инструкция находится в README.md. Сообщение об ошибке — выше.
echo Если порт 8502 занят, остановите прежний запуск Q2 через Ctrl+C в его окне.
pause
exit /b 1
