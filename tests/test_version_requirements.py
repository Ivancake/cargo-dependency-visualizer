"""Проверки требований версий Cargo и границ диапазонов."""

import unittest

from src.version_requirements import (
    matches_parsed_requirement,
    matches_requirement,
    parse_requirement,
)


class TestVersionRequirements(unittest.TestCase):
    """Проверки совместимости, сравнений и предварительных выпусков."""

    def assert_matches(self, requirement, accepted, rejected):
        """Проверить подходящие и неподходящие версии одного требования."""
        for expected, versions in ((True, accepted), (False, rejected)):
            for version in versions:
                with self.subTest(requirement=requirement, version=version):
                    self.assertEqual(
                        matches_requirement(version, requirement), expected
                    )

    def test_default_requirement(self):
        """Отсутствие оператора должно означать ^, а не точное равенство."""
        self.assert_matches("1.2.3", ("1.2.3", "1.9.0"), ("1.2.2", "2.0.0"))
        self.assert_matches("1.2", ("1.2.0", "1.9.0"), ("1.1.9", "2.0.0"))

    def test_caret(self):
        """Разрешить совместимые обновления в пределах major."""
        self.assert_matches("^1.2.3", ("1.2.3", "1.99.0"), ("1.2.2", "2.0.0"))

    def test_caret_with_zero(self):
        """Проверить правила ^ для нулевого major и сокращённых версий."""
        self.assert_matches("^0.2.3", ("0.2.3", "0.2.9"), ("0.2.2", "0.3.0"))
        self.assert_matches("^0.0.3", ("0.0.3",), ("0.0.2", "0.0.4"))
        self.assert_matches("^0.0", ("0.0.0", "0.0.9"), ("0.1.0",))
        self.assert_matches("^0", ("0.0.0", "0.9.0"), ("1.0.0",))

    def test_tilde(self):
        """Ограничить обновления оператором ~."""
        self.assert_matches("~1.2.3", ("1.2.3", "1.2.9"), ("1.2.2", "1.3.0"))
        self.assert_matches("~1.2", ("1.2.0", "1.2.9"), ("1.3.0",))
        self.assert_matches("~1", ("1.0.0", "1.9.9"), ("2.0.0",))

    def test_exact(self):
        """Проверить точное равенство и совпадение сокращённого префикса."""
        self.assert_matches("=1.2.3", ("1.2.3",), ("1.2.2", "1.2.4"))
        self.assert_matches("=1.2", ("1.2.0", "1.2.99"), ("1.3.0",))
        self.assert_matches("=1", ("1.0.0", "1.9.9"), ("2.0.0",))

    def test_comparison_operators(self):
        """Проверить включённые и исключённые границы сравнений."""
        self.assert_matches(">1.2.3", ("1.2.4",), ("1.2.3", "1.2.2"))
        self.assert_matches(">=1.2.3", ("1.2.3", "1.2.4"), ("1.2.2",))
        self.assert_matches("<1.2.3", ("1.2.2",), ("1.2.3", "1.2.4"))
        self.assert_matches("<=1.2.3", ("1.2.2", "1.2.3"), ("1.2.4",))

    def test_partial_comparisons(self):
        """Сравнивать только указанные числовые части сокращённой версии."""
        self.assert_matches(">1.2", ("1.3.0",), ("1.2.0", "1.2.99"))
        self.assert_matches(">1", ("2.0.0",), ("1.99.99",))
        self.assert_matches("<=1.2", ("1.2.99",), ("1.3.0",))
        self.assert_matches("<1.2", ("1.1.99",), ("1.2.0",))

    def test_wildcards(self):
        """Разрешить подстановки *, x и X в конце версии."""
        self.assert_matches("*", ("0.0.0", "9.9.9"), ("1.0.0-alpha",))
        self.assert_matches("1.*", ("1.0.0", "1.9.9"), ("2.0.0",))
        self.assert_matches("1.2.x", ("1.2.0", "1.2.99"), ("1.3.0",))
        self.assert_matches("1.X.X", ("1.9.9",), ("2.0.0",))

    def test_explicit_operator_with_wildcard(self):
        """Сохранить явный оператор перед числовой частью с подстановкой."""
        self.assert_matches(">=1.*", ("1.0.0", "2.0.0"), ("0.9.9",))
        self.assert_matches("^1.*", ("1.0.0", "1.9.9"), ("2.0.0",))

    def test_intersection(self):
        """Все условия через запятую должны выполняться одновременно."""
        self.assert_matches(
            " >= 1.2 , < 2 ", ("1.2.0", "1.9.9"), ("1.1.9", "2.0.0")
        )
        self.assert_matches("<1.2, ^1.2.2", (), ("1.1.9", "1.2.2"))

    def test_prereleases(self):
        """Не включать prerelease без явного допуска для его чисел."""
        self.assert_matches("^1.0", ("1.2.0",), ("1.0.0-alpha",))
        self.assert_matches(
            "^1.0.0-alpha",
            ("1.0.0-beta", "1.0.0", "1.5.0"),
            ("1.0.1-alpha", "2.0.0")
        )
        self.assert_matches("=1.0.0-alpha", ("1.0.0-alpha",), ("1.0.0-beta",))

    def test_prerelease_intersections(self):
        """Проверить prerelease при сочетании полных и неполных условий."""
        cases = (
            ("^1, =1.0.0-alpha", True),
            (">=1, =1.0.0-alpha", False),
            ("~1, =1.0.0-alpha", False),
            ("^1.2, =1.2.0-alpha", True),
            ("~1.2, =1.2.0-alpha", False),
            ("~1.2.3, =1.2.4-alpha", True),
        )
        for requirement, expected in cases:
            version = requirement.split("=")[-1]
            with self.subTest(requirement=requirement):
                self.assertEqual(
                    matches_requirement(version, requirement), expected
                )

    def test_build_metadata(self):
        """Не учитывать метаданные сборки при проверке требования."""
        self.assert_matches("=1.2.3+one", ("1.2.3", "1.2.3+two"), ("1.2.4",))

    def test_invalid_requirements(self):
        """Отклонить неправильные записи вместо приблизительного сравнения."""
        cases = (
            None, 123, "", " ", "=", "*.*", "*, >=1", "1.*.2",
            "^1.2.3,", "1 || 2", "1.2 - 2.0", ">=1 <2", "01.2",
            "1.2+build", "1.2.3-01", "1.2.3+", "1.2.3.4",
        )
        for requirement in cases:
            with self.subTest(requirement=requirement):
                with self.assertRaises(ValueError):
                    parse_requirement(requirement)

    def test_compiled_requirement(self):
        """Разобрать условие один раз для проверки нескольких кандидатов."""
        comparators = parse_requirement(">=1.2, <2")
        self.assertTrue(matches_parsed_requirement("1.5.0", comparators))
        self.assertFalse(matches_parsed_requirement("2.0.0", comparators))
        self.assertEqual(parse_requirement("*"), ())

    def test_invalid_candidate(self):
        """Сообщить об ошибочном формате проверяемой версии."""
        with self.assertRaises(ValueError):
            matches_requirement("1.2", "^1")


if __name__ == "__main__":
    unittest.main()