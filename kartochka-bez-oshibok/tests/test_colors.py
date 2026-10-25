import unittest
from checker import compare, compare_ocr, parse_spec, MATCH, DIFFERENT, REVIEW, MISSING
from color_check import color_evidence, resolve, color_value
from ocr_engine import OCRResult
from ocr_pipeline import Line


def line(text, confidence=95, box=(0,0,200,20)):
    return Line(text, confidence, box, [(0,len(text),confidence,box)])


class ColorTests(unittest.TestCase):
    def check(self, text, expected='белый'):
        return compare(text, parse_spec('Цвет: '+expected))[0]

    def test_explicit_color_contexts(self):
        for text in ('Чёрный цвет','Цвет: черный','ЧЁРНЫЙ\nцвет','Цвет:\nчёрный'):
            with self.subTest(text=text):
                f = self.check(text)
                self.assertEqual((f.status,f.found),(DIFFERENT,'чёрный'))

    def test_noise_is_never_a_color(self):
        for text in ('Цвет: п 3g)', 'цвет: черньй','цвет: black','цвет: бeлый','Цвет: черный123'):
            with self.subTest(text=text):
                f = self.check(text)
                self.assertEqual(f.status, REVIEW)
                self.assertEqual(f.found,'—')

    def test_normalization_and_explicit_forms(self):
        for value in ('чёрный','ЧЕРНЫЙ','черная','чёрное','чёрные'):
            self.assertEqual(color_value(value),'чёрный')
        self.assertEqual(self.check('Цвет: БЕЛЫЙ.').status,MATCH)

    def test_unsupported_expected_is_review(self):
        for value in ('молочный','белый/чёрный','светло-серый'):
            self.assertEqual(self.check('Белый цвет',value).status, REVIEW)

    def test_ambiguous_context_is_review(self):
        for text in ('не чёрный цвет','Цвет: не белый','Цвет: белый или чёрный',
                     'Чёрный цвет\nБелый цвет','Цвет: чёрно-белый',
                     'светло-серый цвет','цвет: серый-белый','Цвет фона: белый',
                     'Цвет: белый в ассортименте'):
            with self.subTest(text=text):
                self.assertEqual(self.check(text).status, REVIEW)

    def test_no_label_is_not_a_photo_color(self):
        self.assertEqual(self.check('Красивый белый товар').status,MISSING)
        result = OCRResult('Красивый белый товар',95,[])
        self.assertEqual(compare_ocr(result,result.text,parse_spec('Цвет: белый'))[0].status,REVIEW)

    def test_spatial_join_and_separation(self):
        for distance, count in ((24,1),(150,0)):
            lines = [line('Чёрный',box=(0,0,100,20)),line('цвет',box=(0,distance,90,distance+20))]
            self.assertEqual(len(color_evidence(lines,'one','gray')),count)

    def test_two_distinct_families_same_place_required(self):
        a = color_evidence([line('Чёрный цвет')],'one','gray')
        b = color_evidence([line('Чёрный цвет')],'two','invert')
        self.assertEqual(resolve(a),(None,True))
        self.assertEqual(resolve(a+a),(None,True))
        self.assertEqual(resolve(a+b),('чёрный',False))
        self.assertEqual(resolve(a+b,True),(None,True))
        far = color_evidence([line('Чёрный цвет',box=(500,500,700,520))],'far','invert')
        self.assertEqual(resolve(a+far),(None,True))

    def test_weak_words_and_conflicts(self):
        a = color_evidence([line('Чёрный цвет',60)],'one','gray')
        b = color_evidence([line('Чёрный цвет',60)],'two','invert')
        self.assertEqual(resolve(a+b),(None,True))
        strong = color_evidence([line('Чёрный цвет')],'three','otsu')
        other = color_evidence([line('Белый цвет',60)],'four','color')
        self.assertEqual(resolve(a+strong+other),(None,True))
        words = Line('Чёрный цвет',20,(0,0,100,20),[(0,6,20,(0,0,60,20)),(7,11,99,(65,0,100,20))])
        self.assertEqual(color_evidence([words],'x','x')[0]['confidence'],20)

    def test_manual_color_edit_and_unrelated_edit(self):
        result = OCRResult('Цвет: белый\nВес: 250 г',90,[])
        spec = parse_spec('Цвет: белый')
        self.assertEqual(compare_ocr(result,result.text.replace('250','200'),spec)[0].status,REVIEW)
        self.assertEqual(compare_ocr(result,'Цвет: чёрный\nВес: 250 г',spec)[0].status,DIFFERENT)
        self.assertEqual(compare_ocr(result,'Цвет: п 3g)',spec)[0].status,REVIEW)

    def test_confirmed_color_overrides_baseline_noise(self):
        result = OCRResult('Цвет п 3g)',90,[],color_value='чёрный',color_review=False)
        f = compare_ocr(result,result.text,parse_spec('Цвет: белый'))[0]
        self.assertEqual((f.status,f.found),(DIFFERENT,'чёрный'))


if __name__ == '__main__':
    unittest.main()
