"""Local OCR only. Uploaded images are never sent to an external API."""
from dataclasses import dataclass, field
from io import BytesIO
import os
from pathlib import Path
import shutil
import subprocess
import threading
import warnings
import ctypes
import time
from itertools import chain

from PIL import Image, ImageOps, UnidentifiedImageError
import pytesseract
from ocr_pipeline import variants, focused_variants, lines_from_data, count_evidence, consolidate
from color_check import color_evidence, focused_color_variants, resolve

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 20_000_000
LOCK = threading.Lock()


class OCRError(Exception):
    """Actionable message suitable for the user."""


@dataclass
class OCRResult:
    text: str
    mean_confidence: float | None
    low_confidence_words: list[str]
    quantity_review: bool = False
    diagnostics: list = field(default_factory=list)
    passes: list = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    color_diagnostics: list = field(default_factory=list)
    color_value: str | None = None
    color_review: bool = True

    def quality_note(self) -> str:
        if self.mean_confidence is None:
            if self.text.strip():
                return "Основной проход не нашёл текст; подтверждённые надписи восстановлены дополнительными проходами."
            return "OCR не нашёл текст. Попробуйте другой режим или более чёткое изображение."
        return (f"Средняя уверенность основного прохода OCR: {self.mean_confidence:.0f}/100. "
                "Это внутренняя оценка Tesseract, а не вероятность правильности проверки.")


def windows_compatible_path(path: str) -> str:
    # Some Windows Tesseract builds fail to locate tessdata under Cyrillic paths.
    # Use the existing 8.3 alias where available; never rename the user's folders.
    if os.name == "nt":
        buffer = ctypes.create_unicode_buffer(32768)
        length = ctypes.windll.kernel32.GetShortPathNameW(str(path), buffer, len(buffer))
        if 0 < length < len(buffer):
            return buffer.value
    return path


def find_tesseract(custom_path: str = "") -> str:
    configured = custom_path.strip().strip('"') or os.environ.get("TESSERACT_CMD", "").strip().strip('"')
    if configured:
        if Path(configured).is_file():
            return windows_compatible_path(str(Path(configured).resolve()))
        raise OCRError("По указанному пути нет tesseract.exe. Выберите сам файл программы, а не папку.")
    candidates = [shutil.which("tesseract")]
    for base in (os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
        if base:
            candidates += [str(Path(base) / "Tesseract-OCR" / "tesseract.exe"),
                           str(Path(base) / "Programs" / "Tesseract-OCR" / "tesseract.exe")]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return windows_compatible_path(candidate)
    raise OCRError("Tesseract не найден. Установите Tesseract OCR с языком Russian, затем укажите путь к tesseract.exe в настройках слева. Инструкция — README.md.")


def check_languages(executable: str) -> list[str]:
    try:
        result = subprocess.run([executable, "--list-langs"], capture_output=True, timeout=10,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OCRError("Не удалось запустить Tesseract. Проверьте путь и установку программы.") from exc
    langs = [line.strip() for line in result.stdout.decode("utf-8", errors="replace").splitlines()[1:]]
    if result.returncode:
        raise OCRError("Tesseract не смог прочитать языковые модели. Проверьте папку tessdata и переменную TESSDATA_PREFIX.")
    missing = {"rus", "eng"} - set(langs)
    if missing:
        raise OCRError("Не установлены языки: " + ", ".join(sorted(missing)) + ". Добавьте rus.traineddata и eng.traineddata в папку tessdata рядом с tesseract.exe (см. README.md).")
    return langs


def load_image(data: bytes) -> Image.Image:
    if not data:
        raise OCRError("Файл пустой. Выберите изображение PNG, JPG или WEBP.")
    if len(data) > MAX_BYTES:
        raise OCRError("Файл больше 10 МБ. Сохраните изображение меньшего размера.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                if source.format not in {"PNG", "JPEG", "WEBP"}:
                    raise OCRError("Поддерживаются только PNG, JPG и WEBP.")
                if source.width * source.height > MAX_PIXELS:
                    raise OCRError("Изображение больше 20 мегапикселей. Уменьшите его размер.")
                if getattr(source, "n_frames", 1) != 1:
                    raise OCRError("Выберите обычное изображение, а не анимацию.")
                source.load()
                rgba = ImageOps.exif_transpose(source).convert("RGBA")
                canvas = Image.new("RGBA", rgba.size, "white")
                return Image.alpha_composite(canvas, rgba).convert("RGB")
    except OCRError:
        raise
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise OCRError("Не удалось прочитать изображение. Попробуйте пересохранить его как PNG или JPG.") from exc


def recognize(data: bytes, custom_path: str = "", psm: int = 11, enhance: bool = True) -> OCRResult:
    executable = find_tesseract(custom_path)
    check_languages(executable)
    picture = load_image(data)
    if psm not in {3, 6, 11}:
        raise OCRError("Выберите один из доступных режимов распознавания.")
    evidence, passes, notes, base_lines, all_lines = [], [], [], [], []
    colors = []
    confidences, weak = [], []
    try:
        with LOCK:
            pytesseract.pytesseract.tesseract_cmd = executable
            deadline = time.monotonic() + 180
            # Generators are lazy: focused proposals see the lines of all initial passes.
            scan = chain(variants(picture, psm, enhance), focused_variants(picture, all_lines) if enhance else (),
                         focused_color_variants(picture, all_lines) if enhance else ())
            for index, (name, family, image, transform, mode) in enumerate(scan):
                remaining = deadline - time.monotonic()
                if remaining < 1:
                    notes.append("Достигнут лимит 180 секунд: выполнены не все дополнительные проходы.")
                    break
                try:
                    raw = pytesseract.image_to_data(image, lang="rus+eng", config=f"--oem 1 --psm {mode}",
                                                   output_type=pytesseract.Output.DICT, timeout=min(40, remaining))
                except (RuntimeError, pytesseract.TesseractError) as exc:
                    if index == 0:
                        raise
                    notes.append(f"Дополнительный проход {name} не выполнен: {type(exc).__name__}.")
                    continue
                lines = lines_from_data(raw, transform)
                if not name.startswith(("unit-", "color-")):
                    all_lines.extend(lines)
                passes.append({"name": name, "text": "\n".join(line.text for line in lines)})
                if not name.startswith("color-"):
                    evidence.extend(count_evidence(lines, name, family))
                colors.extend(color_evidence(lines, name, family))
                if index == 0:
                    base_lines = lines
                    for word, confidence in zip(raw["text"], raw["conf"]):
                        confidence = float(confidence)
                        if word.strip() and confidence >= 0:
                            confidences.append(confidence)
                            if confidence < 60:
                                weak.append(word)
    except pytesseract.TesseractNotFoundError as exc:
        raise OCRError("Tesseract не найден. Проверьте путь к программе.") from exc
    except pytesseract.TesseractError as exc:
        raise OCRError("Ошибка Tesseract. Проверьте модели rus и eng, затем попробуйте другое изображение или режим.") from exc
    except RuntimeError as exc:
        raise OCRError("Основной проход OCR не завершился за 40 секунд. Уменьшите изображение и попробуйте снова.") from exc
    except OSError as exc:
        raise OCRError("Не удалось обработать изображение. Проверьте доступ к временной папке Windows.") from exc
    additions, review, diagnostics = consolidate(evidence)
    confirmed_color, color_review = resolve(colors, incomplete=bool(notes))
    original = [line.text for line in base_lines]
    color_additions = [f"Цвет: {confirmed_color}"] if confirmed_color else []
    text = "\n".join(dict.fromkeys(original + additions + color_additions))
    # The primary pass may contain a low-confidence quantity that no additional
    # pass supports. Never silently treat that as a confirmed match/difference.
    base_counts = count_evidence(base_lines, "base", "base")
    from checker import compare, parse_spec, MISSING, REVIEW
    baseline = compare("\n".join(original), parse_spec("Количество: 1 шт"))[0]
    if baseline.status != MISSING and (not additions or baseline.status == REVIEW):
        review = True
    confirmed_values = {e.value for e in evidence if e.text in additions}
    if any(e.value not in confirmed_values for e in base_counts):
        review = True
    if notes:
        review = True  # incomplete search must not silently become a clean check
    return OCRResult(text, sum(confidences) / len(confidences) if confidences else None,
                     list(dict.fromkeys(weak)), review, diagnostics, passes, notes,
                     colors, confirmed_color, color_review)
