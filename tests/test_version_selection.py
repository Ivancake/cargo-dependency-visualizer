"""Проверки выбора версии по индексу и требованию Cargo."""

import json
import unittest

from src.version_selection import (
    read_package_versions,
    select_latest_version,
    select_package_version,
)


class TestVersionSelection(unittest.TestCase):
    """Проверки выбора кандидатов и обработки повреждённых записей."""

    def make_record(self, version, name="demo", yanked=False):
        """Подготовить запись версии с пустым списком зависимостей."""
        return {
            "name": name, "vers": version, "deps": [], "yanked": yanked
        }

    def make_index(self, records):
        """Превратить записи в многострочный текст индекса Cargo."""
        return "\n".join(json.dumps(record) for record in records)

    def test_latest_matching_version(self):
        """Выбрать максимум по SemVer независимо от порядка строк."""
        records = [
            self.make_record(version)
            for version in ("1.9.0", "2.0.0", "1.10.0", "1.2.0")
        ]
        selected = select_package_version(
            self.make_index(records), "demo", "^1"
        )
        self.assertEqual(selected["vers"], "1.10.0")

    def test_wildcard_excludes_prerelease(self):
        """Не предпочитать предварительный выпуск обычному при требовании *."""
        records = [
            self.make_record("1.10.0"), self.make_record("2.0.0-alpha")
        ]
        selected = select_latest_version(records, "demo", "*")
        self.assertEqual(selected["vers"], "1.10.0")

    def test_skip_yanked(self):
        """Пропустить самую новую версию, если она отозвана."""
        records = [
            self.make_record("1.8.0"), self.make_record("1.9.0", yanked=True)
        ]
        selected = select_package_version(
            self.make_index(records), "demo", "^1"
        )
        self.assertEqual(selected["vers"], "1.8.0")

    def test_no_candidate(self):
        """Обработать пустой индекс, несовпадение требования и отзыв версий."""
        cases = (
            ([], "^1"),
            ([self.make_record("1.0.0")], "^2"),
            ([self.make_record("1.0.0", yanked=True)], "^1"),
        )
        for records, requirement in cases:
            with self.subTest(records=records, requirement=requirement):
                with self.assertRaises(ValueError) as error:
                    select_package_version(
                        self.make_index(records), "demo", requirement
                    )
                self.assertIn("demo", str(error.exception))
                self.assertIn(requirement, str(error.exception))

    def test_explicit_prerelease(self):
        """Выбрать предварительный выпуск только при подходящем условии."""
        records = [
            self.make_record(version)
            for version in ("1.0.0-alpha", "1.0.0-beta", "1.0.0", "1.1.0-alpha")
        ]
        selected = select_latest_version(records, "demo", "^1.0.0-alpha")
        self.assertEqual(selected["vers"], "1.0.0")
        selected = select_latest_version(records, "demo", "=1.0.0-beta")
        self.assertEqual(selected["vers"], "1.0.0-beta")

    def test_preserve_record(self):
        """Вернуть зависимости, их условия и прочие поля выбранной записи."""
        record = self.make_record("1.2.3+build.7")
        record["deps"] = [{"name": "helper", "req": "^2", "optional": True}]
        record["features"] = {"extra": ["helper"]}
        selected = select_package_version(
            self.make_index([record]), "demo", "=1.2.3"
        )
        self.assertEqual(selected, record)

    def test_invalid_yanked_flag(self):
        """Не принимать строку или число вместо логического флага отзыва."""
        for value in ("false", 0, None, []):
            with self.subTest(value=value):
                record = self.make_record("1.0.0", yanked=value)
                with self.assertRaisesRegex(ValueError, "yanked"):
                    read_package_versions(self.make_index([record]), "demo")

    def test_missing_yanked_flag(self):
        """Считать версию доступной при отсутствии флага yanked."""
        record = self.make_record("1.0.0")
        del record["yanked"]
        self.assertEqual(
            select_package_version(self.make_index([record]), "demo", "^1"),
            record
        )

    def test_broken_index(self):
        """Показать номер строки повреждённого JSON и ошибку версии."""
        with self.assertRaisesRegex(ValueError, "строке 2"):
            read_package_versions("\n{broken", "demo")
        record = self.make_record("1.2")
        with self.assertRaisesRegex(ValueError, "SemVer"):
            read_package_versions(self.make_index([record]), "demo")

    def test_duplicate_versions(self):
        """Отклонить повтор версии, даже если различаются метаданные сборки."""
        records = [self.make_record("1.0.0"), self.make_record("1.0.0+build")]
        with self.assertRaisesRegex(ValueError, "повторяется"):
            read_package_versions(self.make_index(records), "demo")

    def test_other_package(self):
        """Не выбрать более новую запись другого пакета."""
        records = [
            self.make_record("1.0.0"), self.make_record("9.0.0", name="other")
        ]
        selected = select_package_version(self.make_index(records), "DEMO", "*")
        self.assertEqual(selected["name"], "demo")
        self.assertEqual(selected["vers"], "1.0.0")

    def test_read_all_versions(self):
        """При чтении сохранить отозванные записи и пропустить пустые строки."""
        records = [
            self.make_record("1.0.0"), self.make_record("2.0.0", yanked=True)
        ]
        text = "\n\n" + self.make_index(records) + "\n"
        self.assertEqual(read_package_versions(text, "demo"), records)


if __name__ == "__main__":
    unittest.main()