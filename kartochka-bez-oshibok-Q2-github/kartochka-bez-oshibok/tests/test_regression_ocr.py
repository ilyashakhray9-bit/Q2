from pathlib import Path
import unittest

from checker import compare_ocr, compare, parse_spec, DIFFERENT, MATCH, MISSING, REVIEW
from ocr_engine import recognize, find_tesseract, check_languages, OCRError

BASE = Path(__file__).resolve().parents[1] / "examples" / "regression"


class QuantityImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.executable = find_tesseract()
            check_languages(cls.executable)
        except OCRError as exc:
            raise unittest.SkipTest(str(exc))

    def check_image(self, filename, expected_status, actual=None):
        result = recognize((BASE / filename).read_bytes(), self.executable)
        finding = compare_ocr(result, result.text, parse_spec("Количество: 6 штук"))[0]
        self.assertEqual(finding.status, expected_status, (result.text, result.diagnostics))
        if actual:
            self.assertIn(actual, finding.found)
        return result

    def test_white_stacked_22(self):
        result = self.check_image("count_22_stacked.png", DIFFERENT, "22")
        # The old single-pass text misses the stacked number/unit connection.
        baseline = compare(result.passes[0]["text"], parse_spec("Количество: 6 штук"))[0]
        self.assertEqual(baseline.status, MISSING)

    def test_small_white_22(self):
        self.check_image("count_22_small.png", DIFFERENT, "22")

    def test_actual_six_not_replaced_by_22(self):
        # A single corroboration-free reading is intentionally REVIEW, not a
        # forced match. Both outcomes are safe; missing the badge is not.
        result = recognize((BASE / "count_6_stacked.png").read_bytes(), self.executable)
        finding = compare_ocr(result, result.text, parse_spec("Количество: 6 штук"))[0]
        self.assertIn(finding.status, (MATCH, REVIEW))
        self.assertIn("6 штук", finding.found)
        self.assertNotIn("22", finding.found)

    def test_122_not_truncated_to_22(self):
        self.check_image("count_122_stacked.png", DIFFERENT, "122")

    def test_decorations_and_dimension_are_not_counts(self):
        self.check_image("no_count.png", MISSING)

    def test_negation_not_removed(self):
        self.check_image("count_negated.png", REVIEW)

    def test_two_different_badges_need_review(self):
        self.check_image("count_conflict.png", REVIEW)
