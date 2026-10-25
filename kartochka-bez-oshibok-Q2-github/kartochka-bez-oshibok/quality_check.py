"""Run real local OCR; record abstentions separately from correct decisions."""
import argparse
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import platform
import re
import time
import pytesseract
from checker import compare_ocr, parse_spec, parse_numeric, MATCH, DIFFERENT, MISSING, REVIEW
from ocr_engine import recognize, find_tesseract, check_languages

BASE = Path(__file__).resolve().parent
STATUS = {MATCH:'match', DIFFERENT:'different', MISSING:'missing', REVIEW:'review'}


def assess(case, finding):
    predicted = STATUS[finding.status]
    exact = predicted == case['truth']
    wrong_quantity = False
    if predicted in ('match', 'different') and case['truth'] in ('match', 'different'):
        truth_value = int(re.search(r'\d+', case['inscription'])[0])
        readings = [parse_numeric(v.strip(), 'quantity') for v in finding.found.split('/')]
        wrong_quantity = not readings or any(v != (truth_value,) for v in readings)
        exact = exact and not wrong_quantity
    return dict(predicted=predicted, exact=exact, wrong_quantity=wrong_quantity,
                false_alarm=predicted == 'different' and case['truth'] != 'different',
                false_clear=predicted == 'match' and case['truth'] != 'match',
                missed_discrepancy=case['truth'] == 'different' and predicted != 'different')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path, default=BASE/'validation/quality-results.json')
    parser.add_argument('--real', type=Path, help='Unedited real card showing 22 pieces')
    parser.add_argument('--only', nargs='*', help='Optional fixture ids')
    args = parser.parse_args()
    exe = find_tesseract()
    check_languages(exe)  # Missing OCR is an error, never a passing benchmark.
    cases = json.loads((BASE/'examples/quality/manifest.json').read_text(encoding='utf-8'))
    if args.only:
        cases = [c for c in cases if c['id'] in args.only]
        if not cases:
            raise ValueError('No cases selected')
    if args.real:
        cases.append(dict(id='real_original_22', file=str(args.real.resolve()), origin='real',
                          inscription='22 ШТУКИ', truth='different', expected=6, challenge=False))
    rows = []
    for case in cases:
        data = (BASE/'examples/quality'/case['file']).read_bytes()
        started = time.monotonic()
        result = recognize(data, exe)
        finding = compare_ocr(result, result.text, parse_spec(f"Количество: {case['expected']} шт"))[0]
        # Positive = a definite quantity discrepancy. Review/missing are not successes.
        row = dict(case, image_sha256=sha256(data).hexdigest(), **assess(case, finding), manual_edit=False,
                   seconds=round(time.monotonic()-started, 2), finding=asdict(finding), ocr=asdict(result))
        rows.append(row)
        print(f"{case['id']}: {case['truth']} -> {row['predicted']}", flush=True)
        payload = dict(python=platform.python_version(), tesseract=str(pytesseract.get_tesseract_version()),
                       finished=len(rows)==len(cases), total=len(cases), completed=len(rows),
                       matrix=dict(Counter(r['truth']+' -> '+r['predicted'] for r in rows)),
                       cases=rows)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    # Hard challenge misses are reported but don't hide failures of routine cases.
    print('Unresolved discrepancy cases:', sum(r['missed_discrepancy'] for r in rows))
    print('See JSON for all results, including hard challenge misses.')
    return int(any((not r['exact'] and not r['challenge']) or r['false_clear'] or r['false_alarm'] or r['wrong_quantity'] for r in rows))


if __name__ == '__main__':
    raise SystemExit(main())
