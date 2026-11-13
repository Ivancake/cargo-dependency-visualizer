"""Тесты настроек, вывода графов и обработки ошибок приложения."""

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.main import RUNTIME_ERROR, SUCCESS, main, parse_args, validate_file


CLI_ERROR = 2


class TestCommandLine(unittest.TestCase):
    """Проверки интерфейса командной строки без доступа к сети."""

    @property
    def args(self):
        """Вернуть независимый набор допустимых параметров теста."""
        return [
            "--package", "serde",
            "--repository", "https://index.crates.io",
            "--version", "1.0.0"
        ]

    def replace_option(self, option, value):
        """Вернуть копию параметров с заменённой или добавленной опцией."""
        args = self.args.copy()
        if option not in args:
            return args + [option, value]
        position = args.index(option)
        args[position + 1] = value
        return args

    def assert_cli_error(self, args, option):
        """Проверить код завершения и указание ошибочного параметра."""
        stream = io.StringIO()
        with redirect_stderr(stream):
            with self.assertRaises(SystemExit) as error:
                parse_args(args)
        self.assertEqual(error.exception.code, CLI_ERROR)
        self.assertIn(option, stream.getvalue())
        self.assertNotIn("Traceback", stream.getvalue())

    def run_application(self, args=None, graph=None, error=None):
        """Запустить приложение с подменой графа Cargo и перехватом вывода."""
        output = io.StringIO()
        errors = io.StringIO()
        result = {("serde", "1.0.0"): []} if graph is None else graph
        with patch(
            "src.main.build_cargo_dependency_graph",
            return_value=result, side_effect=error
        ) as download:
            with redirect_stdout(output), redirect_stderr(errors):
                code = main(self.args if args is None else args)
        return code, output.getvalue(), errors.getvalue(), download

    def run_test_application(self, graph, extra_args=None, raw_text=None):
        """Запустить тестовый режим с настоящим временным JSON-файлом."""
        text = json.dumps(graph) if raw_text is None else raw_text
        with TemporaryDirectory() as directory:
            path = Path(directory) / "graph.json"
            path.write_text(text, encoding="utf-8")
            args = [
                "--package", "A", "--version", "1.0.0",
                "--repository", str(path), "--test-mode"
            ]
            args.extend([] if extra_args is None else extra_args)
            return self.run_application(args)

    def test_default_settings(self):
        """Проверить обязательные настройки и значения по умолчанию."""
        args = parse_args(self.args)
        self.assertEqual(args.package, "serde")
        self.assertEqual(args.repository, "https://index.crates.io")
        self.assertEqual(args.version, "1.0.0")
        self.assertFalse(args.test_mode)
        self.assertFalse(args.ascii)
        self.assertEqual(args.filter, "")

    def test_ascii_and_filter(self):
        """Проверить включение ASCII-режима и передачу фильтра."""
        args = parse_args(self.args + ["--ascii", "--filter", "serde-"])
        self.assertTrue(args.ascii)
        self.assertEqual(args.filter, "serde-")

    def test_invalid_values(self):
        """Проверить ошибки значений имени, версии, URL и фильтра."""
        cases = {
            "--package": ("", " ", "1serde", "serde.json", "пакет"),
            "--version": (
                "", "1.2", "v1.2.3", "01.2.3", "1.02.3", "1.2.03",
                "1.2.3-01", "1.2.3-", "1.2.3+", "1.2.3-a..b"
            ),
            "--repository": (
                "", "index.crates.io", "ftp://example.com", "https://",
                "https://example.com:wrong", "https://example.com:99999",
                "https://[bad", "https://exam ple.com"
            ),
            "--filter": (" ", "  ", "a\nb", "\t")
        }
        for option, values in cases.items():
            for value in values:
                with self.subTest(option=option, value=value):
                    args = self.replace_option(option, value)
                    self.assert_cli_error(args, option)

    def test_valid_versions(self):
        """Проверить обычные версии, предварительные и со сборкой."""
        versions = (
            "0.0.0", "1.2.3", "1.2.3-beta.1", "1.2.3+001",
            "1.2.3-alpha.1+build.007", "1.2.3-01a"
        )
        for version in versions:
            with self.subTest(version=version):
                args = parse_args(self.replace_option("--version", version))
                self.assertEqual(args.version, version)

    def test_missing_required_options(self):
        """Проверить отсутствие каждого обязательного параметра."""
        for option in ("--package", "--repository", "--version"):
            with self.subTest(option=option):
                args = self.args.copy()
                position = args.index(option)
                del args[position:position + 2]
                self.assert_cli_error(args, option)

    def test_invalid_flags(self):
        """Проверить, что переключатели не принимают значения."""
        for option in ("--ascii", "--test-mode"):
            with self.subTest(option=option):
                self.assert_cli_error(self.args + [option + "=false"], option)

    def test_unknown_and_abbreviated_options(self):
        """Отклонить неизвестный параметр и сокращённое имя."""
        self.assert_cli_error(self.args + ["--unknown"], "--unknown")
        self.assert_cli_error(self.args + ["--pack", "other"], "--pack")

    def test_local_repository(self):
        """Проверить тестовый режим и путь к файлу с пробелами."""
        with TemporaryDirectory() as directory:
            path = Path(directory) / "test graph.json"
            path.write_text('{"A": ["B"], "B": []}', encoding="utf-8")
            args = self.replace_option("--package", "A")
            position = args.index("--repository")
            args[position + 1] = str(path)
            args.append("--test-mode")
            settings = parse_args(args)
            self.assertTrue(settings.test_mode)
            self.assertEqual(settings.repository, str(path))
            self.assertEqual(settings.package, "A")
            args[args.index("--package") + 1] = "a"
            self.assert_cli_error(args, "--package")
            args[args.index("--package") + 1] = "A"
            for invalid in (path.with_name("missing.json"), Path(directory)):
                with self.subTest(path=invalid):
                    args[position + 1] = str(invalid)
                    self.assert_cli_error(args, "--repository")

    def test_unreadable_repository(self):
        """Проверить сообщение об отказе в доступе к файлу."""
        with patch("src.main.Path.is_file", return_value=True):
            with patch("src.main.Path.open", side_effect=PermissionError):
                with self.assertRaisesRegex(ValueError, "не удалось открыть"):
                    validate_file("private.json")

    def test_main_output(self):
        """Вывести цикл и две версии библиотеки как разные вершины."""
        root = ("serde", "1.0.0")
        first = ("helper", "1.0.0")
        second = ("helper", "2.0.0")
        graph = {root: [first, second], first: [root], second: []}
        code, output, errors, download = self.run_application(graph=graph)
        expected = [
            "digraph dependencies {", "    rankdir=LR;",
            '    n0 [label="serde@1.0.0"];',
            '    n1 [label="helper@1.0.0"];',
            '    n2 [label="helper@2.0.0"];',
            "    n0 -> n1;", "    n0 -> n2;", "    n1 -> n0;", "}"
        ]
        self.assertEqual(code, SUCCESS)
        self.assertEqual(output.splitlines(), expected)
        self.assertEqual(errors, "")
        download.assert_called_once_with(
            "https://index.crates.io", "serde", "1.0.0", ""
        )

    def test_no_dependencies_output(self):
        """Вывести понятное сообщение для пакета без зависимостей."""
        code, output, errors, _ = self.run_application()
        self.assertEqual(code, SUCCESS)
        self.assertEqual(
            output.splitlines(),
            [
                "digraph dependencies {", "    rankdir=LR;",
                '    n0 [label="serde@1.0.0"];', "}"
            ]
        )
        self.assertEqual(errors, "")

    def test_download_failure(self):
        """Вывести ошибку загрузки в stderr и вернуть код ошибки."""
        code, output, errors, _ = self.run_application(
            error=ValueError("Сервер недоступен")
        )
        self.assertEqual(code, RUNTIME_ERROR)
        self.assertEqual(output, "")
        self.assertIn("Ошибка: Сервер недоступен", errors)
        self.assertNotIn("Traceback", errors)

    def test_cargo_filter_parameter(self):
        """Передать фильтр построителю графа реальных пакетов."""
        code, _, errors, build = self.run_application(
            self.args + ["--filter", "derive"]
        )
        self.assertEqual(code, SUCCESS)
        self.assertEqual(errors, "")
        build.assert_called_once_with(
            "https://index.crates.io", "serde", "1.0.0", "derive"
        )

    def test_filtered_cargo_root(self):
        """Вывести пустой граф при исключении начального пакета Cargo."""
        code, output, errors, _ = self.run_application(
            self.args + ["--filter", "serde"], graph={}
        )
        self.assertEqual(code, SUCCESS)
        self.assertEqual(output.splitlines(), [
            "digraph dependencies {", "    rankdir=LR;", "}"
        ])
        self.assertEqual(errors, "")

    def test_actual_root_version(self):
        """Показать фактическую версию корня с метаданными из индекса."""
        graph = {("serde", "1.0.0+build.7"): []}
        code, output, errors, _ = self.run_application(graph=graph)
        self.assertEqual(code, SUCCESS)
        self.assertEqual(output.splitlines(), [
            "digraph dependencies {", "    rankdir=LR;",
            '    n0 [label="serde@1.0.0+build.7"];', "}"
        ])
        self.assertEqual(errors, "")

    def test_test_mode_output(self):
        """Прочитать файл и вывести достижимый граф без сетевого запроса."""
        graph = {"A": ["B", "C"], "B": ["C"], "C": []}
        code, output, errors, download = self.run_test_application(graph)
        self.assertEqual(code, SUCCESS)
        self.assertEqual(output.splitlines(), [
            "digraph dependencies {", "    rankdir=LR;",
            '    n0 [label="A"];', '    n1 [label="B"];',
            '    n2 [label="C"];', "    n0 -> n1;", "    n0 -> n2;",
            "    n1 -> n2;", "}"
        ])
        self.assertEqual(errors, "")
        download.assert_not_called()

    def test_test_mode_cycle(self):
        """Вывести цикл и ссылку на себя, завершив работу успешно."""
        graph = {"A": ["A", "B"], "B": ["A"]}
        code, output, errors, _ = self.run_test_application(graph)
        self.assertEqual(code, SUCCESS)
        self.assertEqual(output.splitlines(), [
            "digraph dependencies {", "    rankdir=LR;",
            '    n0 [label="A"];', '    n1 [label="B"];',
            "    n0 -> n0;", "    n0 -> n1;", "    n1 -> n0;", "}"
        ])
        self.assertEqual(errors, "")

    def test_test_mode_filter(self):
        """Применить фильтр к тестовому графу и остановить обход ветки."""
        graph = {"A": ["B", "C"], "B": ["D"], "C": [], "D": []}
        code, output, errors, _ = self.run_test_application(
            graph, ["--filter", "B"]
        )
        self.assertEqual(code, SUCCESS)
        self.assertEqual(output.splitlines(), [
            "digraph dependencies {", "    rankdir=LR;",
            '    n0 [label="A"];', '    n1 [label="C"];',
            "    n0 -> n1;", "}"
        ])
        self.assertEqual(errors, "")

    def test_filtered_test_root(self):
        """Сообщить о пустом графе при исключении начального пакета."""
        code, output, errors, _ = self.run_test_application(
            {"A": []}, ["--filter", "A"]
        )
        self.assertEqual(code, SUCCESS)
        self.assertEqual(output.splitlines(), [
            "digraph dependencies {", "    rankdir=LR;", "}"
        ])
        self.assertEqual(errors, "")

    def test_missing_test_package(self):
        """Показать ошибку, если начального пакета нет в файле."""
        code, output, errors, _ = self.run_test_application({"B": []})
        self.assertEqual(code, RUNTIME_ERROR)
        self.assertEqual(output, "")
        self.assertIn("Пакет A отсутствует", errors)
        self.assertNotIn("Traceback", errors)

    def test_broken_test_json(self):
        """Вывести понятную ошибку повреждённого JSON в stderr."""
        code, output, errors, _ = self.run_test_application(
            {}, raw_text='{"A": ['
        )
        self.assertEqual(code, RUNTIME_ERROR)
        self.assertEqual(output, "")
        self.assertIn("Ошибка JSON", errors)
        self.assertNotIn("Traceback", errors)

    def test_invalid_test_graph(self):
        """Обработать ссылку на пакет, не описанный в тестовом файле."""
        code, output, errors, _ = self.run_test_application({"A": ["B"]})
        self.assertEqual(code, RUNTIME_ERROR)
        self.assertEqual(output, "")
        self.assertIn("не описан отдельным ключом", errors)
        self.assertNotIn("Traceback", errors)

    def test_cargo_ascii_cycle(self):
        """Вывести Graphviz и дерево версий Cargo с отметкой цикла."""
        root, child = ("serde", "1.0.0"), ("helper", "2.0.0")
        code, output, errors, _ = self.run_application(
            self.args + ["--ascii"], {root: [child], child: [root]}
        )
        self.assertEqual(code, SUCCESS)
        self.assertEqual(errors, "")
        self.assertTrue(output.startswith("digraph dependencies {\n"))
        self.assertIn("    n1 -> n0;\n", output)
        self.assertTrue(output.endswith(
            "\nASCII-дерево:\nserde@1.0.0\n`-- helper@2.0.0\n"
            "    `-- serde@1.0.0 [цикл]\n"
        ))

    def test_json_ascii_shared_dependency(self):
        """Показать общую зависимость в дереве и сохранить все рёбра DOT."""
        code, output, errors, download = self.run_test_application(
            {"A": ["B", "C"], "B": ["C"], "C": []}, ["--ascii"]
        )
        self.assertEqual(code, SUCCESS)
        self.assertEqual(errors, "")
        self.assertIn("    n0 -> n2;\n", output)
        self.assertIn("    n1 -> n2;\n", output)
        self.assertTrue(output.endswith(
            "\nASCII-дерево:\nA\n|-- B\n|   `-- C\n`-- C [повтор]\n"
        ))
        download.assert_not_called()

    def test_filtered_ascii_root(self):
        """Вывести пустой DOT и пояснение для дерева исключённого корня."""
        code, output, errors, _ = self.run_test_application(
            {"A": []}, ["--ascii", "--filter", "A"]
        )
        self.assertEqual(code, SUCCESS)
        self.assertEqual(errors, "")
        self.assertEqual(
            output, "digraph dependencies {\n    rankdir=LR;\n}\n"
            "\nASCII-дерево:\n(пустой граф)\n"
        )

    def test_cargo_ascii_actual_root_version(self):
        """Использовать в дереве фактическую версию корня из индекса."""
        code, output, errors, _ = self.run_application(
            self.args + ["--ascii"], {("serde", "1.0.0+build.7"): []}
        )
        self.assertEqual(code, SUCCESS)
        self.assertEqual(errors, "")
        self.assertTrue(output.endswith(
            "\nASCII-дерево:\nserde@1.0.0+build.7\n"
        ))

    def test_reverse_ascii_conflict(self):
        """Отклонить сочетание обратного поиска и прямого ASCII-дерева."""
        self.assert_cli_error(
            self.args + ["--reverse", "serde@1.0.0", "--ascii"], "--ascii"
        )

    def test_help(self):
        """Проверить справку и успешное завершение при --help."""
        stream = io.StringIO()
        with redirect_stdout(stream):
            with self.assertRaises(SystemExit) as result:
                parse_args(["--help"])
        self.assertEqual(result.exception.code, 0)
        for option in (
            "--package", "--repository", "--test-mode",
            "--version", "--ascii", "--filter"
        ):
            self.assertIn(option, stream.getvalue())


if __name__ == "__main__":
    unittest.main()