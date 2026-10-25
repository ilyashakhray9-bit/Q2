# Искусственные примеры

В этой папке нет фотографий клиентов и настоящих карточек товаров.

- `card_with_errors.png` и `blank.png` создаются `tests/generate_demo.py`.
- `regression/*.png` создаются `tests/generate_fixtures.py`.
- `quality/*.png` и `quality/manifest.json` создаются `tests/generate_quality_fixtures.py`.
- `spec.txt` — искусственное ТЗ для демонстрации.

Генераторы рисуют простые формы и тестовые надписи с Pillow. На Windows используют установленный Arial; файлы шрифтов не распространяются. Для генератора regression можно передать `--font` с путём к своему подходящему шрифту. Изменение шрифта может изменить результат OCR.

После установки зависимостей:

```powershell
.\.venv\Scripts\python.exe tests/generate_demo.py
.\.venv\Scripts\python.exe tests/generate_fixtures.py
.\.venv\Scripts\python.exe tests/generate_quality_fixtures.py
```

Папка `examples/real/` исключена из поставки и игнорируется Git. Не добавляйте в публичный репозиторий чужие изображения без разрешения.
