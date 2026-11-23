import importlib.util
import sys
import types
import unittest
from unittest.mock import Mock, patch


def load(name):
    with patch.dict(sys.modules, {'model': types.SimpleNamespace(model_complete=Mock()),
                                 'harness': types.SimpleNamespace(run_benchmark=Mock())}):
        spec = importlib.util.spec_from_file_location(name, f"benchmarks/{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class HmmExtractionTests(unittest.TestCase):
    def setUp(self):
        self.extract = load('hmmt_2026')._extract

    def test_boxed_and_fallback_numbers(self):
        for text, want in [
            (r'Therefore \boxed{42}.', '42'),
            (r'\boxed{\frac{1}{\sqrt{2}}}', r'\frac{1}{\sqrt{2}}'),
            (r'First \boxed{12}; corrected \boxed{42}.', '42'),
            ('The final answer is 0.5.', '0.5'),
            ('The final answer is -3/7.', '-3/7'),
            ('The final answer is -.5.', '-.5'),
            ('The final answer is -0.125.', '-0.125'),
            ('The remaining candidates are 1,2.', '2'),
            ('The problem gives 2026. Simplifying gives 42.', '42'),
        ]:
            with self.subTest(text=text):
                self.assertEqual(self.extract(text), want)

    def test_degenerate_and_refusals(self):
        for text, want in [
            (r'\boxed{\frac{1}{2', '2'),
            ('I cannot solve this problem.', None),
            ('', None),
            (None, None),
        ]:
            with self.subTest(text=text):
                self.assertEqual(self.extract(text), want)


class MmmuExtractionTests(unittest.TestCase):
    def setUp(self):
        self.extract = load('mmmu_pro')._extract_letter

    def test_correct_formats(self):
        for text, want in [
            ('J', 'J'),
            (r'\boxed{J}', 'J'),
            ('The answer is J.', 'J'),
            ('After checking the diagram: (J)', 'J'),
            ('j', 'J'),
            ('A was initially plausible. The diagram rules it out.\nJ', 'J'),
            (r'A was initially plausible. Finally: \boxed{J}', 'J'),
            ('The answer is justified by the diagram.\nC', 'C'),
            ('Reject (A) after checking the diagram.\nJ', 'A'),
            ('I cannot answer this question.', 'I'),
            ('Unable to determine the option.', None),
            ('', None),
            (None, None),
        ]:
            with self.subTest(text=text):
                self.assertEqual(self.extract(text), want)

    def test_option_range(self):
        self.assertIsNone(self.extract('J', 4))
        self.assertEqual(self.extract('D', 4), 'D')


if __name__ == '__main__':
    unittest.main()
