"""Conservative, deterministic comparison. No API, LLM or fuzzy number fixes."""
from dataclasses import asdict, dataclass
from decimal import Decimal
import re
import unicodedata
from quantity_context import CAUTION
from color_check import color_value, text_mentions
from version import VERSION

MATCH = "Совпало в тексте"
DIFFERENT = "Расхождение"
MISSING = "Не найдено"
REVIEW = "Нужна проверка"
DISCLAIMER = (
    "Проверен только текст. OCR может ошибаться или пропускать надписи. "
    "Сервис не считает предметы на фото, не измеряет их и не проверяет реальный цвет, "
    "материал, дизайн или соответствие товара изображению. Совпадения не гарантируют "
    "отсутствия ошибок: перед публикацией проверьте карточку вручную."
)

ALIASES = {
    "quantity": ("количество", "кол-во", "кол во", "количество в наборе", "в наборе", "комплектность"),
    "dimensions": ("размер", "размеры", "габариты"),
    "length": ("длина",), "width": ("ширина",), "height": ("высота",),
    "diameter": ("диаметр",), "thickness": ("толщина",),
    "weight": ("вес", "масса"), "volume": ("объем", "объём"),
    "color": ("цвет",), "material": ("материал", "состав"),
}
NUMERIC = {"quantity", "dimensions", "length", "width", "height", "diameter", "thickness", "weight", "volume"}
NUM = r"\d+(?:[.,]\d+)?"
UNITS = {
    "мм": ("length", Decimal("1")), "mm": ("length", Decimal("1")),
    "см": ("length", Decimal("10")), "cm": ("length", Decimal("10")),
    "м": ("length", Decimal("1000")), "m": ("length", Decimal("1000")),
    "г": ("weight", Decimal("1")), "g": ("weight", Decimal("1")),
    "кг": ("weight", Decimal("1000")), "kg": ("weight", Decimal("1000")),
    "мл": ("volume", Decimal("1")), "ml": ("volume", Decimal("1")),
    "л": ("volume", Decimal("1000")), "l": ("volume", Decimal("1000")),
}
UNIT_PATTERN = "|".join(sorted(UNITS, key=len, reverse=True))
DIM_PATTERN = rf"{NUM}(?:\s*(?:{UNIT_PATTERN}))?(?:\s*[xх×*]\s*{NUM}(?:\s*(?:{UNIT_PATTERN}))?){{1,2}}"


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold().replace("ё", "е")
    return re.sub(r"\s+", " ", text).strip()


def text_value(text: str) -> str:
    # Do not change O to 0 or other lookalikes: that could hide an OCR error.
    return normalize(text).strip(" .:;\t\n")


def kind_for(label: str) -> str:
    label = normalize(label)
    for kind, names in ALIASES.items():
        if label in {normalize(name) for name in names}:
            return kind
    return label


def number(text: str) -> Decimal:
    return Decimal(text.replace(",", "."))


def parse_numeric(value: str, kind: str):
    """Return canonical tuple or None. Missing/unsupported units are not guessed."""
    value = text_value(value)
    if kind == "quantity":
        match = re.fullmatch(rf"({NUM})\s*(?:шт\.?|штук[аи]?|pcs)?", value)
        if match:
            n = number(match[1])
            return (n,) if n > 0 and n == n.to_integral_value() else None
        return None
    if kind == "dimensions":
        if not re.fullmatch(DIM_PATTERN, value):
            return None
        pieces = re.split(r"\s*[xх×*]\s*", value)
        parsed = [re.fullmatch(rf"({NUM})\s*({UNIT_PATTERN})?", item) for item in pieces]
        # A final unit applies to preceding numbers: 20 x 30 см.
        last_unit = parsed[-1][2]
        if not last_unit:
            return None
        result = []
        for part in parsed:
            unit = part[2] or last_unit
            if UNITS[unit][0] != "length" or number(part[1]) <= 0:
                return None
            result.append(number(part[1]) * UNITS[unit][1])
        return tuple(result)
    match = re.fullmatch(rf"({NUM})\s*({UNIT_PATTERN})", value)
    if not match:
        return None
    dimension, factor = UNITS[match[2]]
    expected_dimension = kind if kind in {"weight", "volume"} else "length"
    n = number(match[1])
    return (n * factor,) if dimension == expected_dimension and n > 0 else None


@dataclass(frozen=True)
class Rule:
    label: str
    expected: str
    kind: str


@dataclass
class Finding:
    field: str
    expected: str
    found: str
    status: str
    explanation: str
    evidence: str = ""

    def row(self):
        return dict(zip(("Поле", "По ТЗ", "В тексте", "Результат", "Пояснение", "Фрагмент текста"), asdict(self).values()))


def parse_spec(text: str) -> list[Rule]:
    if len(text) > 10000:
        raise ValueError("ТЗ слишком длинное. Оставьте до 10 000 символов.")
    rules, seen = [], set()
    for line_no, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        if ":" not in raw:
            raise ValueError(f"Строка {line_no}: используйте формат «Характеристика: значение».")
        label, value = (part.strip() for part in raw.split(":", 1))
        if not label or not value:
            raise ValueError(f"Строка {line_no}: заполните и название, и значение.")
        if len(label) > 80 or len(value) > 500:
            raise ValueError(f"Строка {line_no}: сократите название до 80, значение до 500 символов.")
        kind = kind_for(label)
        if kind in seen:
            raise ValueError(f"Строка {line_no}: поле «{label}» повторяется. Оставьте одно эталонное значение.")
        if kind in NUMERIC and parse_numeric(value, kind) is None:
            raise ValueError(
                f"Строка {line_no}, «{label}»: не удалось понять значение. "
                "Примеры: 6 шт; 20 x 30 см; 0,5 кг; 250 мл. "
                "Диапазоны, допуски, нулевые/отрицательные значения и числа словами пока не поддерживаются."
            )
        rules.append(Rule(label, value, kind))
        seen.add(kind)
    if not rules:
        raise ValueError("Введите ТЗ: хотя бы одну строку «Характеристика: значение».")
    if len(rules) > 40:
        raise ValueError("В первой версии можно проверить до 40 характеристик за раз.")
    return rules


def segments(text: str, rules: list[Rule]):
    """Split by known labels; only attach a following line if label has no value."""
    labels = {normalize(name): kind for kind, names in ALIASES.items() for name in names}
    labels.update({normalize(rule.label): rule.kind for rule in rules})
    pattern = re.compile(r"(?<!\w)(" + "|".join(re.escape(x) for x in sorted(labels, key=len, reverse=True)) + r")(?!\w)\s*(?:[:=]\s*)?")
    labeled = {rule.kind: [] for rule in rules}
    unlabeled = []
    pending = None
    for line in re.split(r"[\n;]+", text):
        line = normalize(line)
        if not line:
            continue
        hits = list(pattern.finditer(line))
        if hits:
            pending = None
            for i, hit in enumerate(hits):
                kind = labels[hit[1]]
                end = hits[i+1].start() if i+1 < len(hits) else len(line)
                value = line[hit.end():end].strip(" ,|")
                # Do not discard a negation/offer before the quantity label.
                # Keep the whole clause so parse_numeric safely abstains.
                if kind == "quantity" and CAUTION.search(line[:end]):
                    value = line[:end]
                if kind in labeled:
                    if value:
                        labeled[kind].append((value, line[hit.start():end]))
                    else:
                        pending = (kind, hit[1])
        elif pending and ":" not in line:
            kind, name = pending
            labeled[kind].append((line, name + ": " + line))
            pending = None
        else:
            pending = None
            # Do not borrow values from another named attribute (e.g. weight gross).
            if ":" not in line:
                unlabeled.append(line)
    return labeled, unlabeled


def fallback_values(lines: list[str], rule: Rule):
    candidates = []
    for line in lines:
        if rule.kind == "quantity":
            pattern = rf"(?<![\w.,+-]){NUM}\s*(?:шт\.?|штук[аи]?|pcs)(?!\w)"
        elif rule.kind == "dimensions":
            pattern = rf"(?<![\w.,+-]){DIM_PATTERN}(?![\w.,])"
        else:
            # Named lengths, weights, color/material etc. need a label.
            continue
        for match in re.finditer(pattern, line):
            # Promotional/range/negated statements must not become matches.
            if CAUTION.search(line):
                candidates.append((line, line))
            else:
                candidates.append((match[0], line))
    return candidates


def compare(text: str, rules: list[Rule]) -> list[Finding]:
    labeled, unlabeled = segments(text, rules)
    findings = []
    for rule in rules:
        if rule.kind == "color":
            findings.append(compare_color_text(text, rule))
            continue
        candidates = labeled[rule.kind]
        # Include unlabelled counts/dimensions even if a labelled match exists:
        # contradictory badges on the same card need a human, not a green check.
        if rule.kind in {"quantity", "dimensions"}:
            candidates = candidates + fallback_values(unlabeled, rule)
        if not candidates:
            findings.append(Finding(rule.label, rule.expected, "—", MISSING,
                "Значение не найдено в распознанном тексте. Это не доказывает, что его нет на картинке."))
            continue
        evidence = " | ".join(dict.fromkeys(e for _, e in candidates))
        found = " / ".join(dict.fromkeys(v for v, _ in candidates))
        if rule.kind in NUMERIC:
            expected = parse_numeric(rule.expected, rule.kind)
            values = [parse_numeric(value, rule.kind) for value, _ in candidates]
        else:
            expected = text_value(rule.expected)
            values = [text_value(value) for value, _ in candidates]
        unique = set(values)
        if None in unique or len(unique) != 1:
            status, explanation = REVIEW, "Значение неоднозначно, формат не распознан или найдено несколько разных значений. Сверьте фрагменты с картинкой."
        elif unique == {expected}:
            status, explanation = MATCH, "Значение совпало в тексте. Единицы приведены к одному масштабу; порядок размеров сохранён." if rule.kind in NUMERIC else "Значение после названия поля совпало в тексте. Это не проверка самого товара."
        elif rule.kind == "dimensions" and sorted(next(iter(unique))) == sorted(expected):
            status, explanation = REVIEW, "Размеры перечислены в другом порядке. Проверьте, где длина, ширина и высота."
        else:
            status, explanation = DIFFERENT, "Распознанное значение отличается от ТЗ. Убедитесь, что это ошибка карточки, а не OCR."
        findings.append(Finding(rule.label, rule.expected, found, status, explanation, evidence))
    return findings


def compare_color_text(text, rule):
    expected = color_value(rule.expected)
    candidates = text_mentions(text)
    values = {m.value for m in candidates if m.value is not None}
    found = " / ".join(sorted(values)) or "—"
    evidence = " | ".join(dict.fromkeys(m.text for m in candidates))
    if expected is None or any(m.caution for m in candidates) or len(values) > 1:
        status, explanation = REVIEW, "Цвет вне словаря, неясный контекст или несколько чтений. Сверьте надпись с изображением."
    elif not values:
        status, explanation = MISSING, "Надпись о цвете не найдена. Цвет предмета на фото не определяется."
    else:
        status = MATCH if values == {expected} else DIFFERENT
        explanation = "Сопоставлена надпись о цвете с ТЗ; фактический цвет предмета на фото не проверялся."
    return Finding(rule.label, rule.expected, found, status, explanation, evidence)


def make_report(findings: list[Finding], source_name: str, raw_text: str, checked_text: str, quality_note: str = "") -> str:
    lines = [f"КАРТОЧКА БЕЗ ОШИБОК — {VERSION}", f"Изображение: {source_name}", "", DISCLAIMER, "", quality_note]
    if raw_text != checked_text:
        lines += ["ВНИМАНИЕ: сверка выполнена по тексту, исправленному пользователем."]
    lines += [""]
    for item in findings:
        lines += [f"[{item.status}] {item.field}", f"  По ТЗ: {item.expected}", f"  В тексте: {item.found}",
                  f"  {item.explanation}", f"  Фрагмент: {item.evidence or '—'}", ""]
    lines += ["ИСХОДНЫЙ ТЕКСТ OCR", raw_text or "(пусто)", "", "ТЕКСТ, ИСПОЛЬЗОВАННЫЙ ДЛЯ СВЕРКИ", checked_text or "(пусто)"]
    return "\n".join(lines)


def compare_ocr(result, checked_text: str, rules: list[Rule]) -> list[Finding]:
    """Uncertain automatic quantities need review; explicit manual edits win."""
    findings = compare(checked_text, rules)
    # Editing an unrelated field must not turn an uncertain colour into a fact.
    def signature(text):
        return [(m.value, m.text, m.caution) for m in text_mentions(text)]
    color_edited = checked_text != result.text and signature(checked_text) != signature(result.text)
    for rule, finding in zip(rules, findings):
        if rule.kind != "color" or color_edited:
            continue
        expected = color_value(rule.expected)
        valid = result.color_value if not result.color_review else None
        finding.found = valid or "—"
        supporting = [e for e in result.color_diagnostics if e['confidence'] >= 55]
        finding.evidence = " | ".join(dict.fromkeys(e['text'] for e in supporting))
        if valid is None or expected is None:
            finding.status = REVIEW
            finding.explanation = ("OCR не подтвердил однозначную надпись о цвете либо цвет в ТЗ вне словаря. "
                                   "Сверьте изображение и исправьте строку о цвете вручную. Мусор OCR не считается цветом.")
        else:
            finding.status = MATCH if valid == expected else DIFFERENT
            finding.explanation = ("Надпись о цвете подтверждена несколькими вариантами OCR в одной области. "
                                   "Проверяется текст, а не фактический цвет предмета на фото.")
    if checked_text == result.text and result.quantity_review:
        for rule, finding in zip(rules, findings):
            if rule.kind == "quantity":
                finding.status = REVIEW
                finding.explanation = ("OCR не смог надёжно подтвердить количество: есть одиночное, "
                                       "слабое или противоречивое чтение либо выполнены не все проходы. "
                                       "Сверьте надпись с изображением и при необходимости исправьте текст.")
                evidence = list(dict.fromkeys(e["text"] for e in result.diagnostics if e["confidence"] >= 55))
                if evidence:
                    finding.evidence = " | ".join(evidence)
                    if finding.found == "—":
                        finding.found = "Возможные чтения: " + " / ".join(evidence)
    return findings
