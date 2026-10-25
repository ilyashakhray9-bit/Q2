"""Bounded image passes and conservative, spatially corroborated quantity recovery.

No specification is passed here: OCR must never be steered towards the expected count.
"""
from dataclasses import dataclass, asdict
import re

from PIL import Image, ImageOps, ImageFilter, ImageChops
from quantity_context import CAUTION

COUNT = re.compile(r"(?<![\w.,+\-])([1-9]\d*)\s*(?:штук[аи]?|шт\.?|pcs)(?!\w)", re.I)
LABELED = re.compile(r"(?:количество|кол-во|в наборе)\s*[:=]?\s*([1-9]\d*)(?![\w.,])", re.I)


@dataclass
class Line:
    text: str
    confidence: float
    box: tuple[float, float, float, float]
    # Character spans retain per-word confidence; unrelated good words cannot
    # make an uncertain digit look certain.
    spans: list


@dataclass
class Evidence:
    value: int
    text: str
    confidence: float
    box: tuple
    source: str
    family: str
    caution: bool = False


def otsu(gray):
    hist = gray.histogram()
    total, weighted = sum(hist), sum(i * n for i, n in enumerate(hist))
    left_n = left_sum = 0
    best, threshold = -1, 127
    for i, n in enumerate(hist):
        left_n += n
        left_sum += i * n
        right_n = total - left_n
        if not left_n or not right_n:
            continue
        score = left_n * right_n * (left_sum / left_n - (weighted - left_sum) / right_n) ** 2
        if score > best:
            best, threshold = score, i
    return gray.point(lambda p: 255 if p > threshold else 0)


def prepared(picture, box, kind, target):
    crop = picture.crop(box)
    scale = min(3.0, target / max(crop.size))
    crop = crop.resize((max(1, round(crop.width * scale)), max(1, round(crop.height * scale))), Image.Resampling.LANCZOS)
    sx, sy = crop.width / (box[2] - box[0]), crop.height / (box[3] - box[1])
    if kind != "color":
        crop = ImageOps.autocontrast(ImageOps.grayscale(crop), cutoff=1)
        if kind == "otsu":
            crop = otsu(crop)
        elif kind == "local":
            mean = crop.filter(ImageFilter.GaussianBlur(15))
            crop = ImageChops.subtract(crop, mean, offset=128).point(lambda p: 255 if p > 120 else 0)
        elif kind == "invert":
            crop = ImageOps.invert(crop)
    return ImageOps.expand(crop, border=16, fill="white"), (box[0], box[1], sx, sy, 16)


def variants(picture, psm, enhance):
    w, h = picture.size
    full = (0, 0, w, h)
    # First pass remains a general transcription. Other passes recover counts
    # and colour inscriptions; each has a separate conservative evidence gate.
    baseline = picture.copy()
    baseline.thumbnail((3200, 3200), Image.Resampling.LANCZOS)
    if enhance:
        if max(baseline.size) < 1600:
            baseline = baseline.resize((baseline.width * 2, baseline.height * 2), Image.Resampling.LANCZOS)
        baseline = ImageOps.autocontrast(ImageOps.grayscale(baseline))
    yield f"baseline/psm{psm}", "full/gray" if enhance else "full/color", baseline, (0, 0, baseline.width / w, baseline.height / h, 0), psm
    plans = []
    if enhance:
        plans += [("full", full, "color", 11, 1800),
                  ("full", full, "gray", 3, 2400),
                  ("full", full, "otsu", 11, 2400),
                  ("full", full, "local", 11, 2400),
                  ("full", full, "invert", 11, 2400)]
        # Overlap protects badges crossing the center. No assumed badge position.
        for row in range(2):
            for col in range(2):
                box = (int(w * .38 * col), int(h * .38 * row),
                       int(w * (.62 + .38 * col)), int(h * (.62 + .38 * row)))
                plans += [(f"tile-{row}-{col}", box, "gray", 6, 1800),
                          (f"tile-{row}-{col}", box, "otsu", 11, 1800)]
    for region, box, kind, mode, target in plans:
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        img, transform = prepared(picture, box, kind, target)
        yield f"{region}/{kind}/psm{mode}", f"{region}/{kind}", img, transform, mode


def lines_from_data(data, transform):
    x, y, sx, sy, border = transform
    groups = {}
    for i, raw in enumerate(data["text"]):
        word = raw.strip()
        if not word:
            continue
        key = tuple(data[name][i] for name in ("page_num", "block_num", "par_num", "line_num"))
        left, top = data["left"][i], data["top"][i]
        box = (x + (left - border) / sx, y + (top - border) / sy,
               x + (left + data["width"][i] - border) / sx,
               y + (top + data["height"][i] - border) / sy)
        groups.setdefault(key, []).append((word, float(data["conf"][i]), box))
    lines = []
    for words in groups.values():
        text, spans = "", []
        for word, conf, box in words:
            start = len(text)
            text += word
            spans.append((start, len(text), conf, box))
            text += " "
        box = union([item[2] for item in words])
        lines.append(Line(text.strip(), min(item[1] for item in words), box, spans))
    return lines


def focused_variants(picture, lines):
    """Verify at most four unit-word regions, including the space above a badge.

    Proposals come from the image's OCR coordinates, never from a known count.
    """
    boxes = []
    for line in lines:
        for start, end, conf, box in line.spans:
            if conf < 50 or not re.fullmatch(r"(?:штук[аи]?|шт\.?|pcs)", line.text[start:end], re.I):
                continue
            x1, y1, x2, y2 = box
            height = max(8, y2 - y1)
            margin = max(height * 2, (x2 - x1) * .55)
            region = (max(0, int(x1 - margin)), max(0, int(y1 - height * 8)),
                      min(picture.width, int(x2 + margin)), min(picture.height, int(y2 + height)))
            if not any(overlapping(region, existing) for existing in boxes):
                boxes.append(region)
    for index, box in enumerate(boxes[:4]):
        for kind in ("gray", "invert"):
            img, transform = prepared(picture, box, kind, 1600)
            name = f"unit-{index}/{kind}"
            yield name + "/psm6", name, img, transform, 6


def union(boxes):
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def overlapping(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    area = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return area > 0 and intersection / area >= .45


def count_evidence(lines, source, family):
    cleaned = []
    for line in lines:
        text, spans = "", []
        for start, end, conf, box in line.spans:
            word = line.text[start:end]
            # A detached vertical rule is often read as a pipe. Do not change
            # characters inside words/numbers or remove signs and negations.
            if word in {"|", "¦"}:
                continue
            offset = len(text)
            text += word + " "
            spans.append((offset, len(text) - 1, conf, box))
        if spans:
            cleaned.append(Line(text.strip(), min(s[2] for s in spans), union([s[3] for s in spans]), spans))
    lines = cleaned
    candidates = list(lines)
    # A stacked badge may be split into two OCR blocks. Join only isolated,
    # nearby, horizontally aligned number/unit lines, never arbitrary text.
    for number in lines:
        if not re.fullmatch(r"[1-9]\d*", number.text):
            continue
        for unit in lines:
            if not re.fullmatch(r"(?:штук[аи]?|шт\.?|pcs)", unit.text, re.I):
                continue
            a, b = number.box, unit.box
            height = max(a[3] - a[1], b[3] - b[1])
            shared_x = min(a[2], b[2]) - max(a[0], b[0])
            if (-.2 * height <= b[1] - a[3] <= 1.2 * height
                    and shared_x >= .5 * min(a[2] - a[0], b[2] - b[0])):
                shift = len(number.text) + 1
                spans = number.spans + [(s + shift, e + shift, c, box) for s, e, c, box in unit.spans]
                candidates.append(Line(number.text + " " + unit.text, min(number.confidence, unit.confidence), union([a, b]), spans))
    evidence = []
    for line in candidates:
        matches = list(COUNT.finditer(line.text)) or list(LABELED.finditer(line.text))
        for match in matches:
            words = [s for s in line.spans if s[0] < match.end() and s[1] > match.start()]
            if words:
                evidence.append(Evidence(int(match[1]), line.text, min(s[2] for s in words),
                                         union([s[3] for s in words]), source, family,
                                         bool(CAUTION.search(line.text))))
    return evidence


def consolidate(evidence):
    # Independent preprocessing/region evidence at the SAME location is required.
    # Different PSM on identical pixels alone is not a second confirming vote.
    viable = [e for e in evidence if e.confidence >= 55]
    accepted = []
    for item in viable:
        votes = [e for e in viable if e.value == item.value and overlapping(e.box, item.box) and not e.caution]
        if not item.caution and len({e.family for e in votes}) >= 2 and max(e.confidence for e in votes) >= 75:
            accepted.append(item)
    values = {e.value for e in accepted}
    review = bool(viable) and (not values or len({e.value for e in viable}) != 1 or any(e.caution for e in viable))
    # Preserve entire supporting lines, including semantic context; don't append
    # a naked value extracted from e.g. "до 22 штуки".
    added = []
    for value in sorted(values):
        best = max((e for e in accepted if e.value == value), key=lambda e: e.confidence)
        added.append(best.text)
    return added, review, [asdict(e) for e in evidence]
