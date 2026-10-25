@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Сначала запустите start.bat для установки библиотек.
  pause
  exit /b 2
)
set "PYTHONUTF8=1"
".venv\Scripts\python.exe" -c "from ocr_engine import find_tesseract,check_languages; check_languages(find_tesseract())"
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 goto failed
".venv\Scripts\python.exe" quality_check.py
if errorlevel 1 goto failed
echo.
echo Проверки публичной Q2 завершены. Частные изображения не входят в поставку.
echo Два сложных искусственных примера могут остаться непрочитанными.
echo Подробности: validation\quality-results.json и VERIFIED.md.
pause
exit /b 0
:failed
echo.
echo Есть ошибка запуска или несовпадение с ожидаемым результатом. Сообщение выше.
pause
exit /b 1
