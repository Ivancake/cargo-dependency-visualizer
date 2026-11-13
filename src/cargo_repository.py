"""Загрузка индекса Cargo и получение прямых зависимостей пакета."""

import json

from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


SHORT_NAME_LENGTHS = (1, 2)
THREE_CHARACTER_NAME_LENGTH = 3
REQUEST_TIMEOUT_SECONDS = 15
USER_AGENT = "cargo-dependency-visualizer"


def package_index_path(package):
    """Построить путь в индексе для предварительно проверенного имени."""
    name = package.lower()
    length = len(name)
    if not name:
        raise ValueError("Имя пакета не должно быть пустым.")
    if length in SHORT_NAME_LENGTHS:
        return f"{length}/{name}"
    if length == THREE_CHARACTER_NAME_LENGTH:
        return f"3/{name[0]}/{name}"
    return f"{name[:2]}/{name[2:4]}/{name}"


def package_index_url(repository, package):
    """Объединить адрес корня HTTP-индекса и путь файла пакета."""
    base_url = repository.rstrip("/") + "/"
    return urljoin(base_url, package_index_path(package))


def download_package_index(repository, package):
    """Загрузить текст со сведениями обо всех версиях одного пакета."""
    url = package_index_url(repository, package)
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return response.read().decode("utf-8")
    except HTTPError as error:
        raise ValueError(
            f"Сервер вернул HTTP {error.code} для пакета {package}."
        ) from error
    except OSError as error:
        raise ValueError(
            "Не удалось загрузить индекс: проверьте адрес и соединение."
        ) from error
    except UnicodeDecodeError as error:
        raise ValueError(
            "Индекс пакета должен быть текстом в кодировке UTF-8."
        ) from error


def parse_index_record(line, line_number):
    """Прочитать одну строку JSON и проверить основные поля записи."""
    try:
        record = json.loads(line)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Некорректный JSON в строке {line_number} индекса."
        ) from error
    if not isinstance(record, dict):
        raise ValueError(f"В строке {line_number} ожидается объект JSON.")
    if (
        not isinstance(record.get("name"), str)
        or not isinstance(record.get("vers"), str)
        or not isinstance(record.get("deps"), list)
    ):
        raise ValueError(
            f"Некорректные поля name, vers или deps в строке {line_number}."
        )
    return record


def find_package_version(index_text, package, version):
    """Найти запись заданного пакета и версии в многострочном индексе."""
    target_version = version.partition("+")[0]
    target_package = package.lower()
    for line_number, line in enumerate(index_text.splitlines(), start=1):
        if not line.strip():
            continue
        record = parse_index_record(line, line_number)
        if record["name"].lower() != target_package:
            continue
        if record["vers"].partition("+")[0] == target_version:
            return record
    raise ValueError(
        f"Пакет {package} версии {version} не найден в индексе."
    )


def validate_dependency(dependency):
    """Проверить обязательные поля зависимости, сохранив её условия."""
    if not isinstance(dependency, dict):
        raise ValueError("Описание зависимости должно быть объектом JSON.")
    fields = (dependency.get("name"), dependency.get("req"))
    if not all(isinstance(value, str) and value for value in fields):
        raise ValueError("В зависимости нужны непустые строки name и req.")
    actual_name = dependency.get("package")
    if actual_name is not None and (
        not isinstance(actual_name, str) or not actual_name
    ):
        raise ValueError("Поле package должно содержать имя или null.")
    return dependency


def get_direct_dependencies(repository, package, version):
    """Получить все объявленные прямые зависимости заданной версии."""
    index_text = download_package_index(repository, package)
    record = find_package_version(index_text, package, version)
    return [validate_dependency(item) for item in record["deps"]]