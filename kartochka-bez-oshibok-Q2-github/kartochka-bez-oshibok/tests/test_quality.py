"""Semantic regression tests independent of OCR randomness."""
import unittest
from checker import compare, compare_ocr, parse_spec, MATCH, DIFFERENT, MISSING, REVIEW
from ocr_pipeline import Line, count_evidence, consolidate
from ocr_engine import OCRResult
from checker import Finding
from quality_check import assess


class QualityTests(unittest.TestCase):
    def check(self, text):
        return compare(text, parse_spec('Количество: 6 шт'))[0]

    def test_clear_matches(self):
        for text in ('6 шт', '6 штук', '6 pcs', 'КОЛИЧЕСТВО: 6', 'В наборе: 6 шт'):
            with self.subTest(text=text):
                self.assertEqual(self.check(text).status, MATCH)

    def test_different_not_truncated(self):
        for text in ('16 шт', '22 штуки', '122 штуки', 'Количество: 66 шт'):
            with self.subTest(text=text):
                self.assertEqual(self.check(text).status, DIFFERENT)

    def test_numbers_without_quantity(self):
        for text in ('Цена: 6 руб', 'Длина 22 см', 'Артикул: 6', '', 'Набор для волос'):
            with self.subTest(text=text):
                self.assertEqual(self.check(text).status, MISSING)

    def test_offer_and_price_are_not_package_counts(self):
        for text in ('6 шт в подарок', 'Цена за 6 шт', 'Закажите 6 шт', 'Скидка при покупке 6 шт',
                     'Бонус 6 шт', 'Стоимость за 6 шт', 'Не количество: 6 шт',
                     'Примерно количество: 6 шт', 'Подарочное количество: 6 шт'):
            with self.subTest(text=text):
                self.assertEqual(self.check(text).status, REVIEW)

    def test_offer_cannot_be_confirmed_by_two_ocr_passes(self):
        for text in ('6 шт в подарок', 'Цена за 6 шт', 'Не количество: 6 шт'):
            with self.subTest(text=text):
                line = Line(text, 95, (0,0,300,30), [(0,len(text),95,(0,0,300,30))])
                evidence = count_evidence([line], 'one', 'gray') + count_evidence([line], 'two', 'otsu')
                additions, review, diagnostics = consolidate(evidence)
                self.assertEqual(additions, [])
                self.assertTrue(review)
                result = OCRResult(text, 95, [], review, diagnostics)
                self.assertEqual(compare_ocr(result, result.text, parse_spec('Количество: 6 шт'))[0].status, REVIEW)

    def test_missing_does_not_mean_match(self):
        result = OCRResult('', None, [])
        self.assertEqual(compare_ocr(result, '', parse_spec('Количество: 6 шт'))[0].status, MISSING)

    def test_quantity_guard_does_not_change_unrelated_weight(self):
        finding = compare('Вес: 250 г\nЦена за 6 шт', parse_spec('Вес: 250 г'))[0]
        self.assertEqual(finding.status, MATCH)

    def test_benchmark_rejects_wrong_digit_even_when_discrepancy_detected(self):
        case = {'truth': 'different', 'inscription': '22 штуки'}
        finding = Finding('Количество', '6 шт', '23 штуки', DIFFERENT, '')
        result = assess(case, finding)
        self.assertFalse(result['exact'])
        self.assertTrue(result['wrong_quantity'])

    def test_benchmark_counts_abstention_as_missed_discrepancy(self):
        case = {'truth': 'different', 'inscription': '22 штуки'}
        for status in (MISSING, REVIEW):
            with self.subTest(status=status):
                result = assess(case, Finding('Количество', '6 шт', '—', status, ''))
                self.assertTrue(result['missed_discrepancy'])
                self.assertFalse(result['exact'])
