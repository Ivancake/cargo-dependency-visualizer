"""Тесты чтения и проверки локального графа зависимостей."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.test_repository import load_test_repository, validate_test_graph


class TestGraphInput(unittest.TestCase):
    """Проверки корректных графов и ошибок тестового файла."""

    def load_bytes(self, data):
        """Создать временный файл и прочитать его загрузчиком."""
        with TemporaryDirectory() as directory:
            path = Path(directory) / "test graph.json"
            path.write_bytes(data)
            return load_test_repository(path)

    def test_valid_graph(self):
        """Прочитать граф с общими зависимостями и конечным пакетом."""
        graph = {"A": ["B", "C"], "B": ["C"], "C": []}
        result = self.load_bytes(json.dumps(graph).encode("utf-8"))
        self.assertEqual(result, graph)

    def test_cycle_allowed(self):
        """Разрешить цикл и зависимость пакета от самого себя."""
        graph = {"A": ["A", "B"], "B": ["A"]}
        result = self.load_bytes(json.dumps(graph).encode("utf-8"))
        self.assertEqual(result, graph)

    def test_duplicate_edges(self):
        """Удалить повтор рёбер без изменения порядка и исходных данных."""
        graph = {"A": ["B", "B", "C"], "B": [], "C": []}
        result = validate_test_graph(graph)
        self.assertEqual(result["A"], ["B", "C"])
        self.assertEqual(graph["A"], ["B", "B", "C"])

    def test_invalid_structure(self):
        """Отклонить неверные типы, имена и отсутствующие описания пакетов."""
        cases = (
            [], None, 42, {"A": "B"}, {"a": []},
            {"A": ["b"]}, {"A": [123]}, {"A": ["B"]},
        )
        for graph in cases:
            with self.subTest(graph=graph):
                with self.assertRaises(ValueError):
                    self.load_bytes(json.dumps(graph).encode("utf-8"))

    def test_duplicate_keys(self):
        """Не допустить потери зависимостей при повторе имени пакета."""
        with self.assertRaisesRegex(ValueError, "повторяется"):
            self.load_bytes(b'{"A":["B"],"A":[],"B":[]}')

    def test_invalid_json(self):
        """Показать строку и столбец ошибки JSON."""
        with self.assertRaisesRegex(ValueError, "строка.*столбец"):
            self.load_bytes(b'{"A": [')

    def test_invalid_encoding(self):
        """Отклонить данные, которые нельзя прочитать как UTF-8."""
        with self.assertRaisesRegex(ValueError, "UTF-8"):
            self.load_bytes(b"\xff")

    def test_bom(self):
        """Разрешить файл UTF-8 с начальной меткой BOM."""
        result = self.load_bytes('{"A": []}'.encode("utf-8-sig"))
        self.assertEqual(result, {"A": []})

    def test_empty_graph(self):
        """Прочитать пустой репозиторий без добавления выдуманных пакетов."""
        self.assertEqual(self.load_bytes(b"{}"), {})

    def test_missing_file(self):
        """Обработать отсутствие файла на диске."""
        with TemporaryDirectory() as directory:
            path = Path(directory) / "missing.json"
            with self.assertRaisesRegex(ValueError, "прочитать"):
                load_test_repository(path)

    def test_unreadable_file(self):
        """Обработать отказ операционной системы в доступе к файлу."""
        with patch(
            "src.test_repository.Path.read_text", side_effect=PermissionError
        ):
            with self.assertRaisesRegex(ValueError, "прочитать"):
                load_test_repository("private.json")


if __name__ == "__main__":
    unittest.main()