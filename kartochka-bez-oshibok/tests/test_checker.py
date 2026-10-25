import unittest
from checker import compare, parse_spec, parse_numeric, make_report, MATCH, DIFFERENT, MISSING, REVIEW


class ComparisonTests(unittest.TestCase):
    def check(self, spec, text):
        return compare(text, parse_spec(spec))[0]

    def test_count_difference(self):
        self.assertEqual(self.check('Количество: 6 шт', 'Количество: 4 шт').status, DIFFERENT)

    def test_count_no_label(self):
        self.assertEqual(self.check('Количество: 6 шт', 'Выгодный набор 6 шт').status, MATCH)

    def test_count_not_substring(self):
        self.assertEqual(self.check('Количество: 6 шт', '16 шт').status, DIFFERENT)

    def test_equivalent_units(self):
        for spec, text in [('Длина: 20 см', 'Длина: 200 мм'), ('Вес: 0,25 кг', 'Масса: 250 г'),
                           ('Объем: 1 л', 'Объём: 1000 мл'), ('Размеры: 20 x 30 см', 'Размеры: 200 mm × 0,3 m')]:
            with self.subTest(spec=spec):
                self.assertEqual(self.check(spec, text).status, MATCH)

    def test_dimensions_difference(self):
        self.assertEqual(self.check('Размеры: 20 x 30 см', '20 x 25 см').status, DIFFERENT)

    def test_dimensions_order_needs_review(self):
        self.assertEqual(self.check('Размеры: 20 x 30 см', 'Размеры: 30 x 20 см').status, REVIEW)

    def test_three_dimensions(self):
        self.assertEqual(self.check('Размеры: 20 x 30 x 5 см', 'Размеры: 200 x 300 x 50 мм').status, MATCH)

    def test_no_units_no_match(self):
        self.assertEqual(self.check('Длина: 20 см', 'Длина: 20').status, REVIEW)

    def test_missing_and_empty(self):
        self.assertEqual(self.check('Цвет: белый', '').status, MISSING)
        self.assertEqual(self.check('Цвет: белый', 'красивый белый товар').status, MISSING)

    def test_unknown_fields_and_regex_characters(self):
        self.assertEqual(self.check('Модель (код): А-123', 'Модель (код): А-123').status, MATCH)
        self.assertEqual(self.check('Артикул: AB-12', 'Артикул: AB-123').status, DIFFERENT)

    def test_text_negative_or_other_composition(self):
        self.assertEqual(self.check('Материал: хлопок', 'Материал: не хлопок').status, DIFFERENT)
        self.assertEqual(self.check('Материал: хлопок', 'Материал: 80% хлопок, 20% полиэстер').status, DIFFERENT)

    def test_case_yo_and_spaces(self):
        self.assertEqual(self.check('Цвет: чёрный', 'ЦВЕТ:  черный.').status, MATCH)

    def test_conflicting_values(self):
        for text in ['Количество: 6 шт\nКоличество: 4 шт', 'Количество: 6 шт\n4 шт']:
            self.assertEqual(self.check('Количество: 6 шт', text).status, REVIEW)

    def test_repeated_identical_values(self):
        self.assertEqual(self.check('Вес: 250 г', 'Вес: 250 г\nМасса: 0,25 кг').status, MATCH)

    def test_do_not_borrow_other_property(self):
        self.assertEqual(self.check('Ширина: 20 см', 'Длина: 20 см').status, MISSING)
        self.assertNotEqual(self.check('Вес: 250 г', 'Вес брутто: 250 г').status, MATCH)

    def test_no_silent_digit_correction(self):
        self.assertEqual(self.check('Количество: 6 шт', 'Количество: б шт').status, REVIEW)

    def test_split_lines_and_multiple_fields(self):
        self.assertEqual(self.check('Количество: 6 шт', 'Количество:\n6 шт').status, MATCH)
        results = compare('Количество: 6 шт Цвет: белый', parse_spec('Количество: 6 шт\nЦвет: белый'))
        self.assertEqual([r.status for r in results], [MATCH, MATCH])

    def test_approximate_or_range_never_matches(self):
        for text in ['до 6 шт', 'от 6 шт', 'не 6 шт', '4-6 шт', 'около 6 шт', 'Количество: 4-6 шт']:
            with self.subTest(text=text):
                self.assertNotEqual(self.check('Количество: 6 шт', text).status, MATCH)

    def test_bad_specs_rejected(self):
        for spec in ['', '6 шт', 'Цвет:', ': белый', 'Количество: 2,5 шт', 'Вес: 20',
                     'Количество: 0', 'Количество: -6', 'Размеры: 20 x 30', 'Вес: 1 кг\nМасса: 2 кг']:
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                parse_spec(spec)

    def test_report_preserves_original_and_manual_text(self):
        results = compare('Количество: 6 шт', parse_spec('Количество: 6 шт'))
        report = make_report(results, 'example.png', 'Количество: б шт', 'Количество: 6 шт')
        self.assertIn('исправленному пользователем', report)
        self.assertIn('Количество: б шт', report)
        self.assertIn('не считает предметы', report)


if __name__ == '__main__':
    unittest.main()
