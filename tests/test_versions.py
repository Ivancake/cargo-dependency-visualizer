"""Тесты разбора и порядка версий SemVer."""

import unittest

from src.versions import compare_versions, parse_version, version_key


class TestVersions(unittest.TestCase):
    """Проверки числовых частей, суффиксов и метаданных сборки."""

    def test_parse_core(self):
        """Превратить основные части версии в числа."""
        self.assertEqual(parse_version("1.20.300"), ((1, 20, 300), ()))

    def test_parse_suffix(self):
        """Разделить предварительную версию и пропустить метаданные."""
        self.assertEqual(
            parse_version("1.2.3-beta.2+build.7"),
            ((1, 2, 3), ("beta", "2"))
        )

    def test_invalid_versions(self):
        """Отклонить неправильные типы и нарушение синтаксиса SemVer."""
        cases = (
            None, 123, [], "", "v1.2.3", "1", "1.2",
            "01.2.3", "1.02.3", "1.2.03", "1.2.3-01",
            "1.2.3-", "1.2.3+", "1.2.3-a..b", "1.2.3\n", "١.2.3",
        )
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_version(value)

    def test_numeric_order(self):
        """Сравнивать числа версии, а не строки символов."""
        cases = (
            ("1.10.0", "1.9.0"),
            ("2.0.0", "1.100.100"),
            ("1.0.10", "1.0.9"),
        )
        for newer, older in cases:
            with self.subTest(newer=newer, older=older):
                self.assertEqual(compare_versions(newer, older), 1)
                self.assertEqual(compare_versions(older, newer), -1)

    def test_prerelease_order(self):
        """Проверить последовательность предварительных выпусков."""
        expected = [
            "1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta",
            "1.0.0-beta", "1.0.0-beta.2", "1.0.0-beta.11",
            "1.0.0-rc.1", "1.0.0",
        ]
        self.assertEqual(sorted(reversed(expected), key=version_key), expected)

    def test_numeric_identifier(self):
        """Числовой идентификатор меньше текстового, числа сравнимы численно."""
        self.assertEqual(compare_versions("1.0.0-999", "1.0.0-a"), -1)
        self.assertEqual(
            compare_versions("1.0.0-alpha.2", "1.0.0-alpha.10"), -1
        )

    def test_prerelease_prefix(self):
        """При общем начале более короткий предварительный суффикс меньше."""
        self.assertEqual(compare_versions("1.0.0-alpha", "1.0.0-alpha.0"), -1)
        self.assertEqual(
            compare_versions("1.0.0-alpha.0", "1.0.0-alpha.0.a"), -1
        )

    def test_stable_release(self):
        """Учитывать предварительный суффикс после сравнения трёх чисел."""
        self.assertEqual(compare_versions("1.2.3-alpha", "1.2.3"), -1)
        self.assertEqual(compare_versions("1.2.4-alpha", "1.2.3"), 1)

    def test_build_metadata(self):
        """Метаданные сборки не должны менять порядок версий."""
        self.assertEqual(compare_versions("1.2.3+build.7", "1.2.3+other"), 0)
        self.assertEqual(
            compare_versions("1.2.3-beta.1+build", "1.2.3-beta.1"), 0
        )

    def test_equal_versions(self):
        """Вернуть ноль при сравнении версии с самой собой."""
        self.assertEqual(compare_versions("1.0.0", "1.0.0"), 0)

    def test_valid_suffixes(self):
        """Разрешить корректные числовые, текстовые и сборочные суффиксы."""
        cases = ("0.0.0", "1.2.3-0", "1.2.3-01a", "1.2.3--", "1.2.3+001")
        for version in cases:
            with self.subTest(version=version):
                core, _ = parse_version(version)
                self.assertIsInstance(core, tuple)


if __name__ == "__main__":
    unittest.main()