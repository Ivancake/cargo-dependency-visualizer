"""Проверки обратного поиска через командную строку."""

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.main import main, parse_args


class TestReverseCli(unittest.TestCase):
    """Проверить вывод, ошибки и область обратного поиска."""

    @property
    def args(self):
        """Вернуть независимый набор параметров загрузки Cargo."""
        return [
            "--package", "demo", "--version", "1.0.0",
            "--repository", "https://index.crates.io"
        ]

    def run_application(self, args, graph=None):
        """Перехватить вывод программы и заменить загрузку Cargo."""
        output, errors = io.StringIO(), io.StringIO()
        with patch(
            "src.main.build_cargo_dependency_graph", return_value=graph
        ) as build:
            with redirect_stdout(output), redirect_stderr(errors):
                code = main(args)
        return code, output.getvalue().splitlines(), errors.getvalue(), build

    def run_repository(self, repository, options):
        """Запустить обратный поиск по временному JSON без сети."""
        with TemporaryDirectory() as directory:
            path = Path(directory) / "repository.json"
            path.write_text(json.dumps(repository), encoding="utf-8")
            args = [
                "--package", "A", "--version", "1.0.0",
                "--repository", str(path), "--test-mode"
            ]
            return self.run_application(args + options)

    def test_full_json_repository(self):
        """Найти потребителей за пределами прямого обхода от A."""
        graph = {"A": ["B"], "B": [], "X": ["B"], "Y": ["X"]}
        code, output, errors, build = self.run_repository(
            graph, ["--reverse", "B"]
        )
        self.assertEqual(code, 0)
        self.assertEqual(output, [
            "Обратные зависимости для B:", "- A", "- X", "- Y"
        ])
        self.assertEqual(errors, "")
        build.assert_not_called()

    def test_cycle(self):
        """Обойти цикл без повторного вывода искомого пакета."""
        code, output, _, _ = self.run_repository(
            {"A": ["B"], "B": ["C"], "C": ["A"]}, ["--reverse", "A"]
        )
        self.assertEqual(code, 0)
        self.assertEqual(output, [
            "Обратные зависимости для A:", "- C", "- B"
        ])

    def test_no_dependents(self):
        """Вывести сообщение об отсутствии обратных зависимостей."""
        code, output, _, _ = self.run_repository({"A": []}, ["--reverse", "A"])
        self.assertEqual(code, 0)
        self.assertEqual(output, [
            "Обратные зависимости для A:",
            "Обратных зависимостей в области поиска нет."
        ])

    def test_filter(self):
        """Не проходить через исключённого потребителя."""
        graph = {"A": ["B"], "B": [], "X": ["B"], "Y": ["X"]}
        code, output, _, _ = self.run_repository(
            graph, ["--reverse", "B", "--filter", "X"]
        )
        self.assertEqual(code, 0)
        self.assertEqual(output, ["Обратные зависимости для B:", "- A"])

    def test_filtered_target(self):
        """Отдельно объяснить исключение целевого пакета."""
        code, output, _, _ = self.run_repository(
            {"A": []}, ["--reverse", "A", "--filter", "A"]
        )
        self.assertEqual(code, 0)
        self.assertEqual(output[-1], "Целевой пакет исключён фильтром.")

    def test_missing_target(self):
        """Сообщить об отсутствии цели без частичного вывода результата."""
        code, output, errors, _ = self.run_repository(
            {"A": []}, ["--reverse", "Z"]
        )
        self.assertEqual(code, 1)
        self.assertEqual(output, [])
        self.assertIn("Пакет Z отсутствует в графе", errors)
        self.assertNotIn("Traceback", errors)

    def test_invalid_json_target(self):
        """Отклонить имя цели, нарушающее правила тестового режима."""
        args = self.args.copy()
        args[args.index("--package") + 1] = "A"
        with patch("src.main.validate_file"):
            with redirect_stderr(io.StringIO()) as errors:
                with self.assertRaises(SystemExit) as result:
                    parse_args(args + ["--test-mode", "--reverse", "a"])
        self.assertEqual(result.exception.code, 2)
        self.assertIn("--reverse", errors.getvalue())

    def test_invalid_cargo_target(self):
        """Требовать имя и точную версию цели Cargo."""
        for target in ("", "helper", "helper@1.2", "helper@01.2.3"):
            with self.subTest(target=target):
                with redirect_stderr(io.StringIO()) as errors:
                    with self.assertRaises(SystemExit) as result:
                        parse_args(self.args + ["--reverse", target])
                self.assertEqual(result.exception.code, 2)
                self.assertIn("--reverse", errors.getvalue())

    def test_missing_target_argument(self):
        """Отклонить --reverse без следующего за ним значения."""
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as result:
                parse_args(self.args + ["--reverse"])
        self.assertEqual(result.exception.code, 2)

    def test_cargo_scope_and_versions(self):
        """Различать версии и явно назвать корень загруженного графа."""
        root = ("demo", "1.0.0")
        first, second = ("helper", "1.0.0"), ("helper", "2.0.0")
        other = ("extra", "1.0.0")
        graph = {root: [first, other], other: [second], first: [], second: []}
        code, output, errors, build = self.run_application(
            self.args + ["--reverse", "helper@2.0.0"], graph
        )
        self.assertEqual(code, 0)
        self.assertEqual(output, [
            "Обратные зависимости для helper@2.0.0:",
            "Область поиска: граф зависимостей demo@1.0.0.",
            "- extra@1.0.0", "- demo@1.0.0"
        ])
        self.assertEqual(errors, "")
        build.assert_called_once_with(
            "https://index.crates.io", "demo", "1.0.0", ""
        )

    def test_build_metadata(self):
        """Найти фактическую версию цели без учёта метаданных сборки."""
        root, target = ("demo", "1.0.0"), ("helper", "1.0.0+build.7")
        code, output, _, _ = self.run_application(
            self.args + ["--reverse", "HELPER@1.0.0"],
            {root: [target], target: []}
        )
        self.assertEqual(code, 0)
        self.assertEqual(
            output[0], "Обратные зависимости для helper@1.0.0+build.7:"
        )
        self.assertEqual(output[-1], "- demo@1.0.0")

    def test_cargo_missing_target(self):
        """Не выдавать отсутствие цели за отсутствие её потребителей."""
        code, output, errors, _ = self.run_application(
            self.args + ["--reverse", "unknown@1.0.0"],
            {("demo", "1.0.0"): []}
        )
        self.assertEqual(code, 1)
        self.assertEqual(output, [])
        self.assertIn("отсутствует в графе", errors)

    def test_help(self):
        """Упомянуть дополнительный параметр в справке."""
        with redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(SystemExit) as result:
                parse_args(["--help"])
        self.assertEqual(result.exception.code, 0)
        self.assertIn("--reverse", output.getvalue())


if __name__ == "__main__":
    unittest.main()