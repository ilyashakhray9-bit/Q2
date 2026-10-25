from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch
from PIL import Image

from checker import compare_ocr, parse_spec, MATCH, DIFFERENT
from ocr_engine import load_image, recognize, find_tesseract, check_languages, OCRError, MAX_BYTES

BASE = Path(__file__).resolve().parents[1]


class ImageTests(unittest.TestCase):
    def test_invalid_image(self):
        for data in (b'', b'not a picture', b'x' * (MAX_BYTES+1)):
            with self.assertRaises(OCRError):
                load_image(data)

    def test_transparent_background_is_white(self):
        output = BytesIO()
        Image.new('RGBA', (20, 20), (0, 0, 0, 0)).save(output, format='PNG')
        self.assertEqual(load_image(output.getvalue()).getpixel((0, 0)), (255, 255, 255))

    def test_pixel_limit(self):
        output = BytesIO()
        Image.new('RGB', (4500, 4500), 'white').save(output, format='PNG')
        with self.assertRaises(OCRError):
            load_image(output.getvalue())

    def test_missing_executable(self):
        with self.assertRaises(OCRError):
            find_tesseract('missing-tesseract-12345.exe')

    def test_missing_language_message(self):
        class Result:
            stdout = b'List of available languages (1):\neng\n'
            returncode = 0
        with patch('ocr_engine.subprocess.run', return_value=Result()), self.assertRaisesRegex(OCRError, 'rus'):
            check_languages('tesseract')


class RealOCRTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.executable = find_tesseract()
            check_languages(cls.executable)
        except OCRError as exc:
            raise unittest.SkipTest(str(exc))

    def test_russian_card_end_to_end(self):
        result = recognize((BASE/'examples/card_with_errors.png').read_bytes(), self.executable)
        rules = parse_spec((BASE/'examples/spec.txt').read_text(encoding='utf-8'))
        findings = compare_ocr(result, result.text, rules)
        self.assertEqual([f.status for f in findings], [DIFFERENT, DIFFERENT, MATCH, MATCH, MATCH], result.text)

    def test_blank_image(self):
        result = recognize((BASE/'examples/blank.png').read_bytes(), self.executable)
        self.assertEqual(result.text.strip(), '')
        self.assertIsNone(result.mean_confidence)


class FailureHandlingTests(unittest.TestCase):
    def run_with_calls(self, calls):
        image = Image.new('RGB', (100, 100), 'white')
        passes = [(f'test-{i}', f'family-{i}', image, (0, 0, 1, 1, 0), 11) for i in range(2)]
        with patch('ocr_engine.find_tesseract', return_value='fake'), patch('ocr_engine.check_languages'), \
             patch('ocr_engine.variants', return_value=iter(passes)), patch('ocr_engine.focused_variants', return_value=iter(())), \
             patch('ocr_engine.pytesseract.image_to_data', side_effect=calls):
            return recognize((BASE/'examples/blank.png').read_bytes())

    def test_primary_timeout_is_actionable_error(self):
        with self.assertRaisesRegex(OCRError, '40 секунд'):
            self.run_with_calls([RuntimeError('timeout')])

    def test_secondary_timeout_retains_text_and_warns(self):
        raw = {key: [] for key in ('text', 'conf', 'left', 'top', 'width', 'height', 'page_num', 'block_num', 'par_num', 'line_num')}
        result = self.run_with_calls([raw, RuntimeError('timeout')])
        self.assertEqual(len(result.passes), 1)
        self.assertTrue(result.warnings)
        self.assertTrue(result.quantity_review)
