import unittest
from ocr_pipeline import Evidence, Line, consolidate, count_evidence
from ocr_engine import OCRResult
from checker import compare_ocr, parse_spec, REVIEW, DIFFERENT, MATCH, MISSING


def vote(value=22, confidence=90, source="full/gray/psm11", family="full/gray", box=(10, 10, 100, 35), text=None):
    return Evidence(value, text or f"{value} штуки", confidence, box, source, family)


class ConsensusTests(unittest.TestCase):
    def test_two_views_confirm_at_same_location(self):
        extra, review, _ = consolidate([vote(), vote(source="full/otsu/psm11", family="full/otsu")])
        self.assertEqual(extra, ["22 штуки"])
        self.assertFalse(review)

    def test_one_high_confidence_reading_is_not_enough(self):
        extra, review, _ = consolidate([vote(confidence=99)])
        self.assertFalse(extra)
        self.assertTrue(review)

    def test_same_pixels_different_psm_do_not_confirm(self):
        extra, review, _ = consolidate([vote(), vote(source="full/gray/psm3")])
        self.assertFalse(extra)
        self.assertTrue(review)

    def test_distant_identical_numbers_do_not_confirm(self):
        extra, review, _ = consolidate([vote(), vote(family="tile/gray", box=(300, 10, 390, 35))])
        self.assertFalse(extra)
        self.assertTrue(review)

    def test_conflicting_numbers_need_review(self):
        extra, review, _ = consolidate([vote(), vote(family="full/otsu"), vote(2, confidence=65, family="tile/gray")])
        self.assertEqual(extra, ["22 штуки"])
        self.assertTrue(review)

    def test_weak_digits_do_not_become_confirmed(self):
        extra, review, _ = consolidate([vote(confidence=50), vote(confidence=60, family="full/otsu")])
        self.assertFalse(extra)
        self.assertTrue(review)

    def test_no_evidence_means_missing_not_review(self):
        self.assertEqual(consolidate([]), ([], False, []))

    def test_quantity_guard_and_manual_override(self):
        result = OCRResult("22 штуки", 90, [], quantity_review=True)
        rules = parse_spec("Количество: 6 штук")
        self.assertEqual(compare_ocr(result, result.text, rules)[0].status, REVIEW)
        self.assertEqual(compare_ocr(result, "22 штуки\nПроверено вручную", rules)[0].status, DIFFERENT)
        self.assertEqual(compare_ocr(result, "6 штук", rules)[0].status, MATCH)

    def test_missing_primary_but_uncertain_secondary_is_visible(self):
        result = OCRResult("Товар", 90, [], True, [{"text": "22 штуки", "confidence": 80}])
        finding = compare_ocr(result, result.text, parse_spec("Количество: 6 штук"))[0]
        self.assertEqual(finding.status, REVIEW)
        self.assertIn("22 штуки", finding.found)

    def test_guard_only_affects_quantity(self):
        result = OCRResult("Вес: 250 г", 90, [], True)
        findings = compare_ocr(result, result.text, parse_spec("Вес: 250 г\nМатериал: хлопок"))
        self.assertEqual([f.status for f in findings], [MATCH, MISSING])


def line(text, box=(0, 0, 100, 20), confidence=90):
    return Line(text, confidence, box, [(0, len(text), confidence, box)])


class ExtractionTests(unittest.TestCase):
    def test_stacked_badge(self):
        evidence = count_evidence([line("22", (10, 0, 60, 30)), line("штуки", (0, 35, 70, 55))], "pass", "family")
        self.assertEqual([e.value for e in evidence], [22])

    def test_distant_numbers_not_joined_to_units(self):
        for box in [(200, 35, 270, 55), (0, 100, 70, 120)]:
            self.assertFalse(count_evidence([line("22", (10, 0, 60, 30)), line("штуки", box)], "pass", "family"))

    def test_no_lookalike_digit_corrections(self):
        for text in ["2Z штуки", "б штук", "22 см", "122A штуки", "2,22 штуки", "0 штук"]:
            self.assertFalse(count_evidence([line(text)], "pass", "family"), text)

    def test_preserve_negation_and_range(self):
        for text in ["до 22 штуки", "не 22 штуки", "от 22 штуки", "22 штуки + подарок"]:
            evidence = count_evidence([line(text)], "one", "gray")
            evidence += count_evidence([line(text)], "two", "otsu")
            extra, review, _ = consolidate(evidence)
            self.assertFalse(extra)
            self.assertTrue(review)

    def test_low_digit_confidence_not_hidden_by_good_words(self):
        sample = Line("22 штуки", 10, (0, 0, 100, 20), [(0, 2, 10, (0, 0, 20, 20)), (3, 8, 99, (25, 0, 100, 20))])
        self.assertEqual(count_evidence([sample], "pass", "family")[0].confidence, 10)

    def test_other_counts_not_hardcoded(self):
        for value in (6, 12, 24, 122):
            evidence = count_evidence([line(f"{value} шт")], "one", "gray") + count_evidence([line(f"{value} шт")], "two", "otsu")
            extra, review, _ = consolidate(evidence)
            self.assertEqual(extra, [f"{value} шт"])
            self.assertFalse(review)
