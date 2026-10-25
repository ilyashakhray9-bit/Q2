from hashlib import sha256
from pathlib import Path
import json
import streamlit as st

from checker import DISCLAIMER, MATCH, DIFFERENT, MISSING, REVIEW, compare_ocr, make_report, parse_spec
from ocr_engine import OCRError, check_languages, find_tesseract, load_image, recognize
from version import VERSION

BASE = Path(__file__).resolve().parent
DEFAULT_SPEC = "Количество: 6 шт\nРазмеры: 20 x 30 см\nМатериал: хлопок\nЦвет: белый\nВес: 250 г"

st.set_page_config(page_title="Q2 — Карточка без ошибок", page_icon="🔎", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>
@media (max-width: 1100px) {
  section[data-testid="stMain"] .block-container {padding-left: 1.5rem; padding-right: 1.5rem;}
  div[data-testid="stHorizontalBlock"] {flex-wrap: wrap;}
  div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
    min-width: min(100%, 300px); flex: 1 1 300px;
  }
}
</style>""", unsafe_allow_html=True)
st.title("Карточка без ошибок · Q2")
st.success(f"Версия {VERSION} · Проверка надписей о цвете")
st.caption("Бесплатная сверка текста карточки с вашим ТЗ · без API-ключей · на вашем компьютере")
st.info("Проверяем надписи. Количество предметов на фото, реальный цвет, размеры и дизайн нужно проверить вручную.")

with st.sidebar:
    st.subheader("Настройки OCR")
    tesseract_path = st.text_input("Путь к tesseract.exe (если не найден)", placeholder=r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    mode = st.selectbox("Расположение текста", ["Надписи в разных местах", "Один текстовый блок", "Автоматически"])
    psm = {"Надписи в разных местах": 11, "Один текстовый блок": 6, "Автоматически": 3}[mode]
    enhance = st.checkbox("Усиленный поиск количества и цвета", value=True)
    st.caption("До 30 проходов: увеличение, контраст, пороги и области. Может занять до 3 минут. Без усиления — один проход; количество и цвет требуют ручной проверки.")
    with st.expander("Какая версия запущена"):
        st.text(f"{VERSION}\nПапка: {BASE}\nАдрес запуска Q2: http://127.0.0.1:8502")
    if st.button("Проверить установку OCR"):
        try:
            executable = find_tesseract(tesseract_path)
            check_languages(executable)
            st.success("Tesseract и языки rus + eng готовы.")
        except OCRError as exc:
            st.error(str(exc))
    st.divider()
    st.caption("Изображения обрабатываются локально. Для установки нужен интернет; для дальнейшей работы — нет. Временные файлы OCR удаляются библиотекой после обработки.")

left, right = st.columns([1, 1], gap="large")
with left:
    st.subheader("1. Изображение карточки")
    demo = st.checkbox("Попробовать пример с ошибками")
    uploaded = st.file_uploader("Выберите PNG, JPG или WEBP — до 10 МБ", type=["png", "jpg", "jpeg", "webp"], disabled=demo)
    data = (BASE / "examples" / "card_with_errors.png").read_bytes() if demo else (uploaded.getvalue() if uploaded else None)
    source_name = "card_with_errors.png" if demo else (uploaded.name if uploaded else "")
    if data:
        try:
            preview = load_image(data)
            st.image(preview, width="stretch")
        except OCRError as exc:
            st.error(str(exc))
            data = None
    else:
        st.caption("Лучше всего работает чёткий горизонтальный текст на контрастном фоне.")

with right:
    st.subheader("2. Эталонное ТЗ")
    spec = st.text_area("Одна характеристика на строку: название: значение", value=DEFAULT_SPEC, height=220, key="spec")
    with st.expander("Как заполнить ТЗ"):
        st.markdown("**Числа:** количество, размеры, длина, ширина, высота, диаметр, толщина, вес, объём.\n\n"
                    "**Единицы:** мм / см / м, г / кг, мл / л. Например, 200 мм = 20 см. Размеры: `20 x 30 см`.\n\n"
                    "**Цвет:** ограниченный словарь; например, «Чёрный цвет» или «Цвет: белый», в том числе на двух строках. «е/ё» равнозначны. Неизвестные оттенки и неуверенный OCR требуют проверки.\n\n"
                    "**Другие поля:** материал, мощность, артикул и т. п. — точное текстовое сравнение после названия поля. "
                    "Например, для `Материал: хлопок` нужна надпись «Материал: хлопок». Слова без названия поля могут остаться непроверенными.\n\n"
                    "Количество с «шт» и размеры через × можно найти без названия поля. Числа словами, диапазоны, допуски, "
                    "синонимы и смысл рекламных фраз первая версия не понимает.")
    try:
        rules = parse_spec(spec)
        spec_error = None
    except ValueError as exc:
        rules, spec_error = [], str(exc)
        st.warning(spec_error)
    run = st.button("Распознать и проверить", type="primary", disabled=not data or bool(spec_error), width="stretch")

# Changing the image/settings invalidates previous OCR before a report can be shown.
fingerprint = sha256(data + repr((VERSION, tesseract_path, psm, enhance)).encode()).hexdigest() if data else None
if st.session_state.get("fingerprint") != fingerprint:
    for key in ("ocr", "editable_text"):
        st.session_state.pop(key, None)
    st.session_state["fingerprint"] = fingerprint

if run:
    # Remove a previous successful run if retrying now fails.
    st.session_state.pop("ocr", None)
    st.session_state.pop("editable_text", None)
    with st.spinner("Распознаём текст и проверяем надписи с количеством и цветом…"):
        try:
            result = recognize(data, tesseract_path, psm, enhance)
            st.session_state.ocr = result
            st.session_state.editable_text = result.text
        except OCRError as exc:
            st.error(str(exc))

if "ocr" in st.session_state:
    result = st.session_state.ocr
    st.subheader("3. Распознанный текст")
    st.caption(result.quality_note())
    for note in result.warnings:
        st.warning(note)
    if not result.text.strip():
        st.warning("Текст не распознан. Отсутствие текста — не отсутствие ошибок. Попробуйте другой режим OCR.")
    if result.low_confidence_words:
        st.warning("OCR сомневается в отдельных словах. Проверьте их на картинке: " + ", ".join(result.low_confidence_words[:30]))
    checked_text = st.text_area("Можно исправить ошибки распознавания. Сверка обновится после выхода из поля.", key="editable_text", height=200, max_chars=30000)
    if checked_text != result.text:
        st.warning("Сверка ниже выполнена по исправленному вами тексту. Исходный OCR сохранён в отчёте.")
    with st.expander("Исходный текст OCR"):
        st.text(result.text or "(пусто)")
    if result.passes:
        with st.expander("Подробности автоматического поиска"):
            st.caption("Здесь сохранены чтения отдельных проходов. Они могут содержать ошибки; количество и цвет подтверждаются несколькими вариантами OCR. Цвет предмета на фото не определяется.")
            st.write(f"Выполнено проходов: {len(result.passes)}")
            for item in result.passes:
                st.text(item["name"] + "\n" + (item["text"] or "(пусто)"))
            st.download_button("Скачать диагностику OCR", json.dumps({"passes": result.passes, "quantity_evidence": result.diagnostics,
                               "quantity_review": result.quantity_review, "warnings": result.warnings,
                               "version": VERSION, "color_evidence": result.color_diagnostics,
                               "color_value": result.color_value, "color_review": result.color_review}, ensure_ascii=False, indent=2),
                               file_name="ocr-diagnostics.json", mime="application/json")
    st.subheader("4. Результат сверки")
    if spec_error:
        st.warning("Исправьте ТЗ, чтобы обновить отчёт: " + spec_error)
    else:
        findings = compare_ocr(result, checked_text, rules)
        metrics = st.columns(4)
        for column, status in zip(metrics, (MATCH, DIFFERENT, MISSING, REVIEW)):
            column.metric(status, sum(f.status == status for f in findings))
        for item in findings:
            with st.container(border=True):
                st.write(f"{item.status} · {item.field}")
                st.text(f"По ТЗ: {item.expected}\nВ тексте: {item.found}")
                st.caption(item.explanation)
                if item.evidence:
                    with st.expander("Показать фрагмент текста"):
                        st.text(item.evidence)
        with st.expander("Сводная таблица"):
            st.dataframe([item.row() for item in findings], hide_index=True, width="stretch")
        st.warning(DISCLAIMER)
        if demo:
            st.caption("В примере намеренно указано 4 шт вместо 6 шт и 20 × 25 см вместо 20 × 30 см. Материал, цвет и вес совпадают с исходным ТЗ.")
        report = make_report(findings, source_name, result.text, checked_text, result.quality_note())
        report += "\n\nДИАГНОСТИКА OCR\n" + json.dumps({"passes": result.passes, "quantity_evidence": result.diagnostics,
                                  "quantity_review": result.quantity_review, "warnings": result.warnings,
                                  "version": VERSION, "color_evidence": result.color_diagnostics,
                                  "color_value": result.color_value, "color_review": result.color_review}, ensure_ascii=False, indent=2)
        st.download_button("Скачать понятный отчёт (.txt)", report.encode("utf-8-sig"), file_name="otchet-kartochki.txt", mime="text/plain")
else:
    st.caption("Загрузите карточку или включите пример, заполните ТЗ и нажмите «Распознать и проверить».")
