"""Тесты выбора версии и извлечения зависимостей из индекса Cargo."""

import json
import unittest
from unittest.mock import patch

from src.cargo_repository import (
    find_package_version,
    get_direct_dependencies,
    parse_index_record,
    validate_dependency,
)


class TestDependencyData(unittest.TestCase):
    """Проверки чтения индекса без обращения к сети."""

    def make_record(self, version="1.0.0", dependencies=None, name="demo"):
        """Подготовить запись версии пакета для проверки."""
        return {
            "name": name,
            "vers": version,
            "deps": [] if dependencies is None else dependencies,
        }

    def test_select_version(self):
        """Выбрать нужную версию и пропустить другой пакет и пустые строки."""
        records = [
            self.make_record(name="other"),
            self.make_record(version="1.0.1"),
            self.make_record(version="1.0.0"),
        ]
        text = "\n\n".join(json.dumps(record) for record in records)
        result = find_package_version(text, "Demo", "1.0.0")
        self.assertEqual(result, records[-1])

    def test_build_metadata(self):
        """Игнорировать метаданные сборки при выборе версии."""
        record = self.make_record(version="1.0.0+build.7")
        for version in ("1.0.0", "1.0.0+other"):
            with self.subTest(version=version):
                self.assertEqual(
                    find_package_version(json.dumps(record), "demo", version),
                    record,
                )

    def test_missing_version(self):
        """Не подменять отсутствующую версию другой версией пакета."""
        records = [self.make_record(version="1.0.0-beta.1")]
        text = "\n".join(json.dumps(record) for record in records)
        for index_text in ("", text):
            with self.subTest(index_text=index_text):
                with self.assertRaisesRegex(ValueError, "не найден"):
                    find_package_version(index_text, "demo", "1.0.0")

    def test_invalid_index_records(self):
        """Отклонить повреждённый JSON и неправильную структуру записи."""
        cases = (
            "{broken", "[]", "null", "{}",
            '{"name":"demo","vers":"1.0.0","deps":null}',
        )
        for line in cases:
            with self.subTest(line=line):
                with self.assertRaisesRegex(ValueError, "строке 7"):
                    parse_index_record(line, 7)

    def test_invalid_dependencies(self):
        """Обработать неправильные поля описания зависимости."""
        cases = (
            None, [], {}, {"name": "a", "req": ""},
            {"name": "a", "req": 1},
            {"name": "a", "req": "^1", "package": []},
        )
        for dependency in cases:
            with self.subTest(dependency=dependency):
                with self.assertRaises(ValueError):
                    validate_dependency(dependency)

    def test_dependency_conditions(self):
        """Сохранить переименование, диапазон версии, тип и платформу."""
        dependencies = [
            {
                "name": "alias", "package": "real-crate", "req": "^2",
                "kind": "build", "optional": True,
                "target": "cfg(windows)", "features": ["extra"],
            },
            {"name": "helper", "req": "~1.0", "kind": "dev"},
        ]
        text = json.dumps(self.make_record(dependencies=dependencies))
        with patch(
            "src.cargo_repository.download_package_index", return_value=text
        ) as download:
            result = get_direct_dependencies(
                "https://example.org", "demo", "1.0.0"
            )
        self.assertEqual(result, dependencies)
        download.assert_called_once_with("https://example.org", "demo")

    def test_no_dependencies(self):
        """Вернуть пустой список для пакета без зависимостей."""
        text = json.dumps(self.make_record())
        with patch(
            "src.cargo_repository.download_package_index", return_value=text
        ):
            result = get_direct_dependencies(
                "https://example.org", "demo", "1.0.0"
            )
        self.assertEqual(result, [])

    def test_download_error(self):
        """Передать ошибку загрузки вызывающему коду."""
        with patch(
            "src.cargo_repository.download_package_index",
            side_effect=ValueError("Сервер недоступен"),
        ):
            with self.assertRaisesRegex(ValueError, "Сервер недоступен"):
                get_direct_dependencies("https://example.org", "demo", "1.0.0")


if __name__ == "__main__":
    unittest.main()