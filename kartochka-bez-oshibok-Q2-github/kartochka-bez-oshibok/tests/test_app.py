from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from ocr_engine import OCRResult, OCRError

APP = Path(__file__).resolve().parents[1] / 'app.py'
TEXT = 'Количество: 4 шт\nРазмеры: 20 x 25 см\nМатериал: хлопок\nЦвет: белый\nВес: 250 г'


class InterfaceTests(unittest.TestCase):
    def app(self):
        return AppTest.from_file(str(APP), default_timeout=20).run()

    def demo(self, app):
        next(c for c in app.checkbox if c.label == 'Попробовать пример с ошибками').check().run()

    def submit(self, app):
        next(b for b in app.button if b.label == 'Распознать и проверить').click().run()

    def test_initial_screen(self):
        app = self.app()
        self.assertFalse(app.exception)
        self.assertIn('Q2', app.title[0].value)
        self.assertTrue(any('color-text-v2' in s.value for s in app.success))
        self.assertTrue(next(b for b in app.button if b.label == 'Распознать и проверить').disabled)

    def test_uncertain_color_and_manual_correction(self):
        app = self.app()
        self.demo(app)
        app.text_area(key='spec').set_value('Цвет: белый').run()
        with patch('ocr_engine.recognize', return_value=OCRResult('Цвет п 3g)', 90, [])):
            self.submit(app)
        self.assertFalse(app.exception)
        self.assertEqual([m.value for m in app.metric], ['0','0','0','1'])
        app.text_area(key='editable_text').set_value('Чёрный цвет').run()
        self.assertEqual([m.value for m in app.metric], ['0','1','0','0'])
        self.assertTrue(any('исправленному вами' in w.value for w in app.warning))

    def test_demo_report_edit_and_invalidation(self):
        app = self.app()
        self.demo(app)
        with patch('ocr_engine.recognize', return_value=OCRResult(TEXT, 90, [], color_value='белый', color_review=False)):
            self.submit(app)
        self.assertFalse(app.exception)
        self.assertEqual([m.value for m in app.metric], ['3', '2', '0', '0'])
        app.text_area(key='editable_text').set_value(TEXT.replace('4 шт', '6 шт')).run()
        self.assertEqual([m.value for m in app.metric], ['4', '1', '0', '0'])
        self.assertTrue(any('исправленному вами' in w.value for w in app.warning))
        # Changing specification recomputes comparison using current OCR.
        app.text_area(key='spec').set_value('Количество: 6 шт').run()
        self.assertEqual([m.value for m in app.metric], ['1', '0', '0', '0'])
        next(s for s in app.selectbox if s.label == 'Расположение текста').select('Автоматически').run()
        self.assertFalse(app.metric)
        self.assertNotIn('ocr', app.session_state)

    def test_ocr_error_does_not_leave_stale_report(self):
        app = self.app()
        self.demo(app)
        with patch('ocr_engine.recognize', return_value=OCRResult(TEXT, 90, [])):
            self.submit(app)
        with patch('ocr_engine.recognize', side_effect=OCRError('Тест: нет русского языка')):
            self.submit(app)
        self.assertFalse(app.exception)
        self.assertFalse(app.metric)
        self.assertTrue(any('нет русского языка' in e.value for e in app.error))

    def test_invalid_spec_disables_check(self):
        app = self.app()
        self.demo(app)
        app.text_area(key='spec').set_value('Количество: шесть').run()
        self.assertTrue(next(b for b in app.button if b.label == 'Распознать и проверить').disabled)

    def test_automatic_uncertainty_and_manual_quantity_edit(self):
        app = self.app()
        self.demo(app)
        app.text_area(key='spec').set_value('Количество: 6 штук').run()
        result = OCRResult('Товар', 90, [], True, [{'text': '22 штуки', 'confidence': 80}],
                           [{'name': 'test-pass', 'text': '22 штуки'}])
        with patch('ocr_engine.recognize', return_value=result):
            self.submit(app)
        self.assertFalse(app.exception)
        self.assertEqual([m.value for m in app.metric], ['0', '0', '0', '1'])
        app.text_area(key='editable_text').set_value('22 штуки').run()
        self.assertEqual([m.value for m in app.metric], ['0', '1', '0', '0'])
        self.assertTrue(any('исправленному вами' in w.value for w in app.warning))
        next(c for c in app.checkbox if c.label == 'Усиленный поиск количества и цвета').uncheck().run()
        self.assertFalse(app.metric)


if __name__ == '__main__':
    unittest.main()
