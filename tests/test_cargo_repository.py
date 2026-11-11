"""Тесты построения адресов и загрузки индекса Cargo."""

import io
import unittest
from urllib.error import HTTPError, URLError
from unittest.mock import patch

from src.cargo_repository import (
    REQUEST_TIMEOUT_SECONDS,
    USER_AGENT,
    download_package_index,
    package_index_path,
    package_index_url,
)


class TestCargoRepository(unittest.TestCase):
    """Проверки загрузчика без обращения к внешнему серверу."""

    def test_package_paths(self):
        """Проверить все правила длины имени и перевод в нижний регистр."""
        cases = {
            "a": "1/a",
            "ab": "2/ab",
            "abc": "3/a/abc",
            "abcd": "ab/cd/abcd",
            "serde": "se/rd/serde",
            "Serde_JSON": "se/rd/serde_json",
        }
        for package, expected in cases.items():
            with self.subTest(package=package):
                self.assertEqual(package_index_path(package), expected)

    def test_empty_package(self):
        """Отклонить пустое имя до попытки сетевого запроса."""
        with self.assertRaisesRegex(ValueError, "Имя пакета"):
            package_index_path("")

    def test_repository_path(self):
        """Сохранить папку репозитория независимо от завершающего слеша."""
        repositories = (
            "https://example.org/index", "https://example.org/index/"
        )
        for repository in repositories:
            with self.subTest(repository=repository):
                self.assertEqual(
                    package_index_url(repository, "serde"),
                    "https://example.org/index/se/rd/serde",
                )

    def test_download(self):
        """Проверить чтение текста, адрес запроса, заголовок и тайм-аут."""
        text = '{"name":"serde","vers":"1.0.0","deps":[]}\n'
        response = io.BytesIO(text.encode("utf-8"))
        with patch(
            "src.cargo_repository.urlopen", return_value=response
        ) as open_url:
            result = download_package_index("https://example.org", "serde")
        self.assertEqual(result, text)
        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url, "https://example.org/se/rd/serde")
        self.assertEqual(request.get_header("User-agent"), USER_AGENT)
        self.assertEqual(
            open_url.call_args.kwargs["timeout"], REQUEST_TIMEOUT_SECONDS
        )
        self.assertTrue(response.closed)

    def test_http_error(self):
        """Преобразовать ответ HTTP 404 в понятное сообщение."""
        error = HTTPError("https://example.org", 404, "Not Found", {}, None)
        with patch("src.cargo_repository.urlopen", side_effect=error):
            with self.assertRaisesRegex(ValueError, "HTTP 404"):
                download_package_index("https://example.org", "missing")

    def test_network_errors(self):
        """Обработать сбой подключения, тайм-аут и разрыв соединения."""
        errors = (URLError("offline"), TimeoutError(), ConnectionResetError())
        for error in errors:
            with self.subTest(error=type(error).__name__):
                with patch("src.cargo_repository.urlopen", side_effect=error):
                    with self.assertRaisesRegex(ValueError, "соединение"):
                        download_package_index("https://example.org", "serde")

    def test_invalid_encoding(self):
        """Отклонить ответ, который нельзя прочитать как UTF-8."""
        response = io.BytesIO(b"\xff")
        with patch("src.cargo_repository.urlopen", return_value=response):
            with self.assertRaisesRegex(ValueError, "UTF-8"):
                download_package_index("https://example.org", "serde")
        self.assertTrue(response.closed)


if __name__ == "__main__":
    unittest.main()