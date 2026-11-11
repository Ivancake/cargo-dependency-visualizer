"""Тесты настроек и обработки ошибок первого этапа."""

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.main import main, parse_args, validate_file


CLI_ERROR = 2


class TestCommandLine(unittest.TestCase):
    """Проверки интерфейса командной строки без доступа к сети."""

    def setUp(self):
        """Подготовить корректный набор параметров для каждого теста."""
        self.args = [
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
        # Ошибки argparse направляются в отдельный поток stderr.
        with redirect_stderr(stream):
            with self.assertRaises(SystemExit) as error:
                parse_args(args)
        self.assertEqual(error.exception.code, CLI_ERROR)
        self.assertIn(option, stream.getvalue())
        self.assertNotIn("Traceback", stream.getvalue())

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
        # Каждый случай получает собственную отметку при падении теста.
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
                # Удаляем имя параметра и следующее за ним значение.
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
        # Временная папка удаляется автоматически после проверки.
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
            # Строчные буквы в тестовом имени недопустимы.
            args[args.index("--package") + 1] = "a"
            self.assert_cli_error(args, "--package")
            args[args.index("--package") + 1] = "A"
            # Проверяем отсутствующий файл и папку вместо файла.
            for invalid in (path.with_name("missing.json"), Path(directory)):
                with self.subTest(path=invalid):
                    args[position + 1] = str(invalid)
                    self.assert_cli_error(args, "--repository")

    def test_unreadable_repository(self):
        """Проверить сообщение об отказе в доступе к файлу."""
        # Имитируем отказ ОС независимо от прав текущего пользователя.
        with patch("src.main.Path.is_file", return_value=True):
            with patch("src.main.Path.open", side_effect=PermissionError):
                with self.assertRaisesRegex(ValueError, "не удалось открыть"):
                    validate_file("private.json")

    def test_main_output(self):
        """Проверить вывод всех шести настроек в формате ключ=значение."""
        stream = io.StringIO()
        with patch("sys.argv", ["main.py"] + self.args + ["--ascii"]):
            with redirect_stdout(stream):
                main()
        expected = [
            "package=serde",
            "repository=https://index.crates.io",
            "test_mode=False",
            "version=1.0.0",
            "ascii=True",
            "filter="
        ]
        self.assertEqual(stream.getvalue().splitlines(), expected)

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