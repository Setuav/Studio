import math
import unittest

from setuav_studio.plugins.core.expressions import (
    ExpressionEvaluationError,
    ExpressionEvaluator,
)


class ExpressionEvaluatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evaluator = ExpressionEvaluator()

    def test_is_expression(self) -> None:
        self.assertTrue(self.evaluator.is_expression("= 2 + 2"))
        self.assertTrue(self.evaluator.is_expression("=sqrt(16)"))
        self.assertFalse(self.evaluator.is_expression("2 + 2"))
        self.assertFalse(self.evaluator.is_expression(123))
        self.assertFalse(self.evaluator.is_expression(None))

    def test_strip_prefix(self) -> None:
        self.assertEqual(self.evaluator.strip_prefix("= 2 + 2"), "2 + 2")
        self.assertEqual(self.evaluator.strip_prefix("=sqrt(16)"), "sqrt(16)")
        self.assertEqual(self.evaluator.strip_prefix("100"), "100")

    def test_basic_arithmetic(self) -> None:
        self.assertEqual(self.evaluator.evaluate("= 2 + 3 * 4"), 14)
        self.assertAlmostEqual(self.evaluator.evaluate("= 10 / 4"), 2.5)
        self.assertEqual(self.evaluator.evaluate("= 2 ** 3"), 8)

    def test_built_in_math_functions_and_constants(self) -> None:
        self.assertAlmostEqual(self.evaluator.evaluate("= sqrt(16)"), 4.0)
        self.assertAlmostEqual(self.evaluator.evaluate("= sin(pi / 2)"), 1.0)
        self.assertAlmostEqual(self.evaluator.evaluate("= cos(0)"), 1.0)
        self.assertAlmostEqual(self.evaluator.evaluate("= g"), 9.80665)
        self.assertAlmostEqual(self.evaluator.evaluate("= radians(180)"), math.pi)

    def test_variables_substitution(self) -> None:
        vars_dict = {"aspect_ratio": 8.0, "wing_area": 2.0}
        res = self.evaluator.evaluate("= sqrt(aspect_ratio * wing_area)", vars_dict)
        self.assertAlmostEqual(res, 4.0)

    def test_extract_symbols(self) -> None:
        symbols = self.evaluator.extract_symbols(
            "= sqrt(aspect_ratio * wing_area) + pi + sin(alpha)"
        )
        self.assertEqual(symbols, {"aspect_ratio", "wing_area", "alpha"})

    def test_syntax_validation(self) -> None:
        self.assertEqual(self.evaluator.validate("= 2 + 2"), [])
        self.assertEqual(self.evaluator.validate(""), ["Expression cannot be empty."])
        errors = self.evaluator.validate("= 2 +")
        self.assertTrue(len(errors) > 0)

    def test_evaluation_error_on_unknown_variable(self) -> None:
        with self.assertRaises(ExpressionEvaluationError):
            self.evaluator.evaluate("= unknown_variable * 2")


if __name__ == "__main__":
    unittest.main()
