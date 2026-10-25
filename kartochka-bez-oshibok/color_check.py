"""Closed vocabulary and conservative text-only colour evidence. No photo classifier."""
from dataclasses import dataclass
import re
import unicodedata


def normalized(text):
    return unicodedata.normalize('NFKC', text).casefold().replace('ё', 'е')


# Explicit forms only: no fuzzy spelling, Latin lookalikes or substring matches.
FORMS = {}
for canonical, forms in {
    'чёрный': 'черный черная черное черные', 'белый': 'белый белая белое белые',
    'красный': 'красный красная красное красные', 'зелёный': 'зеленый зеленая зеленое зеленые',
    'синий': 'синий синяя синее синие', 'голубой': 'голубой голубая голубое голубые',
    'жёлтый': 'желтый желтая желтое желтые', 'розовый': 'розовый розовая розовое розовые',
    'серый': 'серый серая серое серые', 'бежевый': 'бежевый бежевая бежевое бежевые',
    'коричневый': 'коричневый коричневая коричневое коричневые',
    'фиолетовый': 'фиолетовый фиолетовая фиолетовое фиолетовые',
    'оранжевый': 'оранжевый оранжевая оранжевое оранжевые',
    'бордовый': 'бордовый бордовая бордовое бордовые',
    'бирюзовый': 'бирюзовый бирюзовая бирюзовое бирюзовые',
    'золотой': 'золотой золотая золотое золотые',
    'серебристый': 'серебристый серебристая серебристое серебристые',
    'прозрачный': 'прозрачный прозрачная прозрачное прозрачные',
}.items():
    for form in forms.split():
        FORMS[form] = canonical

WORDS = re.compile(r'\w+|[^\w\s]', re.UNICODE)
CAUTION = re.compile(r'\b(?:не|нет|или|либо|кроме|вместо|выбор|выборе|ассортименте|может|пример|фона|фон|упаковки|надписи)\b')


def color_value(text):
    return FORMS.get(normalized(text).strip(' \t\r\n.,'))


@dataclass
class ColorMention:
    value: str | None
    text: str
    start: int
    end: int
    caution: bool = False


def mentions(text):
    """Require a colour immediately before/after 'цвет'; keep ambiguous clauses."""
    result = []
    offset = 0
    for line in text.splitlines(keepends=True):
        norm = normalized(line)
        tokens = list(WORDS.finditer(norm))
        for i, token in enumerate(tokens):
            if token[0] != 'цвет':
                continue
            right = i + 1
            if right < len(tokens) and tokens[right][0] in {':', '='}:
                right += 1
            candidates = []
            for j in (i - 1, right):
                if 0 <= j < len(tokens) and tokens[j][0] in FORMS:
                    candidates.append(tokens[j])
            # Unsupported compounds/modifiers or multiple colour words are not
            # silently shortened to one supported base colour.
            all_colors = [t for t in tokens if t[0] in FORMS]
            caution = bool(CAUTION.search(norm)) or len(all_colors) != 1
            if candidates:
                for c in candidates:
                    lo, hi = min(c.start(), token.start()), max(c.end(), token.end())
                    before = norm[:lo].rstrip()
                    after = norm[hi:].lstrip()
                    if before.endswith(('-', '–')) or after.startswith(('-', '–', '/')):
                        caution = True
                    if re.search(r'\b(?:темно|светло|ярко)\s*$', before):
                        caution = True
                    result.append(ColorMention(FORMS[c[0]], line.strip(), offset + lo, offset + hi, caution))
            else:
                result.append(ColorMention(None, line.strip(), offset + token.start(), offset + token.end(), True))
        offset += len(line)
    return result


def text_mentions(text):
    # Manual transcription may contain a two-line isolated badge. Do not join
    # arbitrary paragraphs or colour words elsewhere in the description.
    lines = text.splitlines()
    joined = []
    i = 0
    while i < len(lines):
        a = normalized(lines[i]).strip(' .:')
        b = normalized(lines[i + 1]).strip(' .:') if i + 1 < len(lines) else ''
        if (a == 'цвет' and b in FORMS) or (a in FORMS and b == 'цвет'):
            joined.append(lines[i] + ' ' + lines[i + 1])
            i += 2
        else:
            joined.append(lines[i])
            i += 1
    return mentions('\n'.join(joined))


def color_evidence(lines, source, family):
    from ocr_pipeline import Line, union
    candidates = list(lines)
    for a in lines:
        av = normalized(a.text).strip(' .:')
        if av != 'цвет' and av not in FORMS:
            continue
        for b in lines:
            bv = normalized(b.text).strip(' .:')
            if not ((av == 'цвет' and bv in FORMS) or (av in FORMS and bv == 'цвет')):
                continue
            x, y = a.box, b.box
            height = max(x[3] - x[1], y[3] - y[1])
            shared = min(x[2], y[2]) - max(x[0], y[0])
            if 0 <= y[1] - x[3] <= 1.2 * height and shared >= .5 * min(x[2]-x[0], y[2]-y[0]):
                shift = len(a.text) + 1
                candidates.append(Line(a.text + ' ' + b.text, min(a.confidence,b.confidence), union([x,y]),
                    a.spans + [(s+shift,e+shift,c,box) for s,e,c,box in b.spans]))
    evidence = []
    for line in candidates:
        for m in mentions(line.text):
            if m.value is None:
                continue  # Noise is never a colour candidate.
            words = [s for s in line.spans if s[0] < m.end and s[1] > m.start]
            if words:
                evidence.append(dict(value=m.value, text=m.text, confidence=min(s[2] for s in words),
                    box=union([s[3] for s in words]), source=source, family=family, caution=m.caution))
    return evidence


def resolve(evidence, incomplete=False):
    from ocr_pipeline import overlapping
    viable = [e for e in evidence if e['confidence'] >= 55]
    accepted = []
    for item in viable:
        votes = [e for e in viable if e['value'] == item['value'] and not e['caution']
                 and overlapping(e['box'], item['box'])]
        if not item['caution'] and len({e['family'] for e in votes}) >= 2 and max(e['confidence'] for e in votes) >= 80:
            accepted.append(item)
    values = {e['value'] for e in viable}
    review = incomplete or not accepted or len(values) != 1 or any(e['caution'] for e in viable)
    return (accepted[0]['value'] if accepted and not review else None), review


def focused_color_variants(picture, lines):
    from ocr_pipeline import overlapping, prepared
    boxes = []
    for line in lines:
        for start, end, conf, box in line.spans:
            word = normalized(line.text[start:end]).strip(' .:')
            if conf < 40 or (word != 'цвет' and word not in FORMS):
                continue
            x1,y1,x2,y2 = box
            h = max(8, y2-y1)
            region = (max(0,int(x1-4*h)),max(0,int(y1-2*h)),
                      min(picture.width,int(x2+4*h)),min(picture.height,int(y2+2*h)))
            if not any(overlapping(region,b) for b in boxes):
                boxes.append(region)
    for i, box in enumerate(boxes[:4]):
        for kind in ('gray','invert'):
            img, transform = prepared(picture,box,kind,1600)
            family = f'color-{i}/{kind}'
            yield family+'/psm6', family, img, transform, 6
