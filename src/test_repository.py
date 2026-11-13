"""Чтение и проверка тестового графа зависимостей из JSON."""

import json
import re
from pathlib import Path


PACKAGE_NAME_PATTERN = re.compile(r"[A-Z]+")


def unique_object(pairs):
    """Собрать объект JSON, отклонив повторяющиеся имена пакетов."""
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError(f"Имя {name} повторяется в объекте JSON.")
        result[name] = value
    return result


def validate_node_name(name):
    """Проверить, что имя состоит из заглавных латинских букв."""
    if not isinstance(name, str) or not PACKAGE_NAME_PATTERN.fullmatch(name):
        raise ValueError("Имена пакетов должны состоять из букв A-Z.")


def validate_test_graph(graph):
    """Проверить структуру графа и убрать повторяющиеся рёбра."""
    if not isinstance(graph, dict):
        raise ValueError("Тестовый репозиторий должен быть объектом JSON.")
    for package, dependencies in graph.items():
        validate_node_name(package)
        if not isinstance(dependencies, list):
            raise ValueError(
                f"Зависимости пакета {package} должны быть списком."
            )
        for dependency in dependencies:
            validate_node_name(dependency)
            if dependency not in graph:
                raise ValueError(
                    f"Пакет {dependency} указан в зависимостях {package}, "
                    "но не описан отдельным ключом."
                )
    return {
        package: list(dict.fromkeys(dependencies))
        for package, dependencies in graph.items()
    }


def load_test_repository(path):
    """Прочитать файл UTF-8 и вернуть проверенный тестовый граф."""
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
        graph = json.loads(text, object_pairs_hook=unique_object)
    except OSError as error:
        raise ValueError(
            "Не удалось прочитать тестовый репозиторий."
        ) from error
    except UnicodeDecodeError as error:
        raise ValueError(
            "Тестовый файл должен быть в кодировке UTF-8."
        ) from error
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Ошибка JSON: строка {error.lineno}, столбец {error.colno}."
        ) from error
    return validate_test_graph(graph)