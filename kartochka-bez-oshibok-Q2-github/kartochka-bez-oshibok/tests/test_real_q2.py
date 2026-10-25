"""Optional private fixtures, excluded from the public repository."""
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import unittest

from checker import compare_ocr, parse_spec, DIFFERENT, MATCH, REVIEW
from ocr_engine import recognize, find_tesseract, check_languages, OCRError
from version import VERSION

BASE = Path(__file__).resolve().parents[1]


class RealQ2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not all((BASE/"examples/real"/name).is_file() for name in ("calla.png", "original_22.png")):
            raise unittest.SkipTest("Private image fixtures are intentionally not distributed")
        try:
            cls.executable = find_tesseract()
            check_languages(cls.executable)
        except OCRError as exc:
            raise unittest.SkipTest(str(exc))

    def run_card(self, filename, spec):
        data = (BASE/'examples/real'/filename).read_bytes()
        result = recognize(data,self.executable)
        findings = compare_ocr(result,result.text,parse_spec(spec))
        payload = dict(version=VERSION,image=filename,image_sha256=sha256(data).hexdigest(),
                       manual_edit=False, findings=[asdict(f) for f in findings],ocr=asdict(result))
        (BASE/'validation').mkdir(parents=True, exist_ok=True)
        (BASE/'validation'/('q2-'+filename+'.json')).write_text(
            json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
        return result,findings

    def test_calla_black_inscription_against_white_and_black(self):
        result, findings = self.run_card('calla.png','Цвет: белый')
        self.assertEqual((findings[0].status,findings[0].found),(DIFFERENT,'чёрный'))
        self.assertEqual(compare_ocr(result,result.text,parse_spec('Цвет: черный'))[0].status,MATCH)
        self.assertEqual(compare_ocr(result,result.text,parse_spec('Цвет: молочный'))[0].status,REVIEW)

    def test_curlers_count_preserved_no_color_from_pixels(self):
        result, findings = self.run_card('original_22.png','Количество: 6 шт\nЦвет: розовый')
        self.assertEqual(findings[0].status,DIFFERENT)
        self.assertEqual(findings[0].found,'22 штуки')
        self.assertEqual((findings[1].status,findings[1].found),(REVIEW,'—'))
        self.assertEqual(compare_ocr(result,result.text,parse_spec('Количество: 22 шт'))[0].status,MATCH)


if __name__ == '__main__':
    unittest.main()
