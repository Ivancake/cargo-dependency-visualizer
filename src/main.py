"""Интерфейс командной строки визуализатора зависимостей Cargo."""

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit


# Поддерживаем и прямой запуск файла, и импорт из тестов.
if __package__:
    from .cargo_graph import build_cargo_dependency_graph
    from .dependency_graph import build_test_dependency_graph
    from .reverse_dependencies import find_reverse_dependencies
    from .test_repository import load_test_repository
    from .versions import version_key
    from .visualization import format_node, to_ascii_tree, to_graphviz
else:
    from cargo_graph import build_cargo_dependency_graph
    from dependency_graph import build_test_dependency_graph
    from reverse_dependencies import find_reverse_dependencies
    from test_repository import load_test_repository
    from versions import version_key
    from visualization import format_node, to_ascii_tree, to_graphviz


SUCCESS = 0
RUNTIME_ERROR = 1

# Части шаблона версии по правилам SemVer.
NUMBER_PATTERN = r"(?:0|[1-9][0-9]*)"
PRERELEASE_PART = r"(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
VERSION_PATTERN = (
    rf"{NUMBER_PATTERN}\.{NUMBER_PATTERN}\.{NUMBER_PATTERN}"
    rf"(?:-{PRERELEASE_PART}(?:\.{PRERELEASE_PART})*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)


def validate_package(value, test_mode):
    """Проверить имя пакета с учётом режима работы."""
    # Для тестового графа используем имена вроде A, B или ABC.
    pattern = r"[A-Z]+" if test_mode else r"[A-Za-z][A-Za-z0-9_-]*"
    if not re.fullmatch(pattern, value):
        if test_mode:
            raise ValueError("--package: нужны заглавные буквы A-Z.")
        raise ValueError(
            "--package: начните имя с латинской буквы; "
            "далее допустимы латинские буквы, цифры, '-' и '_'."
        )


def validate_version(value):
    """Проверить формат точной версии пакета по правилам SemVer."""
    if not re.fullmatch(VERSION_PATTERN, value):
        raise ValueError(
            "--version: нужна версия вида 1.2.3 или 1.2.3-beta.1; "
            "допускаются метаданные сборки после '+'."
        )


def validate_url(value):
    """Проверить схему, наличие узла и корректность порта URL."""
    # Пробелы и управляющие символы в адресе считаем ошибкой.
    if any(char.isspace() or not char.isprintable() for char in value):
        raise ValueError("--repository: URL содержит недопустимые символы.")
    try:
        address = urlsplit(value)
        # Чтение свойства port запускает проверку номера порта.
        _ = address.port
    except ValueError as error:
        raise ValueError("--repository: некорректный URL или порт.") from error
    if address.scheme not in ("http", "https") or not address.hostname:
        raise ValueError(
            "--repository: нужен URL вида https://index.crates.io."
        )


def validate_file(value):
    """Проверить существование и доступность тестового файла."""
    path = Path(value)
    try:
        if not path.is_file():
            raise ValueError("--repository: тестовый файл не найден.")
        # Проверяем доступ; структуру данных проверит загрузчик.
        with path.open("rb"):
            pass
    except OSError as error:
        raise ValueError("--repository: не удалось открыть файл.") from error


def validate_filter(value):
    """Разрешить пустой фильтр или печатную непустую подстроку."""
    if value and (not value.strip() or not value.isprintable()):
        raise ValueError(
            "--filter: укажите подстроку без управляющих символов; "
            "значение только из пробелов недопустимо."
        )


def parse_reverse_target(value, test_mode):
    """Проверить цель обратного поиска и получить строку или пару."""
    if test_mode:
        if not re.fullmatch(r"[A-Z]+", value):
            raise ValueError("--reverse: нужны заглавные буквы A-Z.")
        return value
    package, separator, version = value.partition("@")
    valid_name = re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", package)
    if not separator or not valid_name or not re.fullmatch(
        VERSION_PATTERN, version
    ):
        raise ValueError("--reverse: нужна цель вида serde@1.0.0.")
    return package.lower(), version


def validate_args(args):
    """Выполнить проверки значений всех настроек приложения."""
    validate_package(args.package, args.test_mode)
    validate_version(args.version)
    # Значение --repository проверяем по-разному в двух режимах.
    if args.test_mode:
        validate_file(args.repository)
    else:
        validate_url(args.repository)
    validate_filter(args.filter)
    if args.reverse is not None:
        parse_reverse_target(args.reverse, args.test_mode)
        if args.ascii:
            raise ValueError("--ascii: нельзя использовать вместе с --reverse.")


def create_parser():
    """Описать параметры приложения и встроенную справку."""
    # Создаём обработчик параметров и встроенную справку --help.
    parser = argparse.ArgumentParser(
        description="Визуализатор зависимостей пакетов Cargo.",
        allow_abbrev=False
    )
    # Обязательные параметры требуют значения после своего имени.
    parser.add_argument(
        "--package", required=True, help="Имя анализируемого пакета"
    )
    parser.add_argument(
        "--repository", required=True,
        help="URL репозитория или путь к тестовому файлу"
    )
    # Флаг включается самим присутствием в команде запуска.
    parser.add_argument(
        "--test-mode", action="store_true",
        help="Использовать тестовый репозиторий"
    )
    parser.add_argument(
        "--version", required=True, help="Версия пакета"
    )
    parser.add_argument(
        "--ascii", action="store_true",
        help="Дополнительно вывести ASCII-дерево"
    )
    # Пустая подстрока по умолчанию означает отсутствие фильтрации.
    parser.add_argument(
        "--filter", default="", help="Исключать пакеты с этой подстрокой"
    )
    parser.add_argument(
        "--reverse", metavar="PACKAGE",
        help="Обратный поиск: A для JSON или имя@версия для Cargo"
    )
    return parser


def parse_args(argv=None):
    """Прочитать настройки приложения из командной строки."""
    parser = create_parser()
    args = parser.parse_args(argv)
    try:
        validate_args(args)
    except ValueError as error:
        # Выводим справку по запуску и понятную причину ошибки.
        parser.error(str(error))
    return args


def print_graph(root, graph, ascii_mode=False):
    """Вывести описание Graphviz и при необходимости ASCII-дерево."""
    print(to_graphviz(graph))
    if ascii_mode:
        print()
        print("ASCII-дерево:")
        print(to_ascii_tree(graph, root))


def print_reverse_dependencies(
    target, graph, excluded_substring="", get_name=str, scope=""
):
    """Вывести обратные зависимости и указать область поиска Cargo."""
    filtered = bool(
        excluded_substring and excluded_substring in get_name(target)
    )
    packages = [] if filtered else find_reverse_dependencies(
        graph, target, excluded_substring, get_name
    )
    print(f"Обратные зависимости для {format_node(target)}:")
    if scope:
        print(f"Область поиска: граф зависимостей {scope}.")
    if filtered:
        print("Целевой пакет исключён фильтром.")
    elif not packages:
        print("Обратных зависимостей в области поиска нет.")
    else:
        for package in packages:
            print(f"- {format_node(package)}")


def run_test_mode(args):
    """Прочитать JSON, построить достижимый граф и вывести его связи."""
    repository = load_test_repository(args.repository)
    if args.reverse is not None:
        target = parse_reverse_target(args.reverse, True)
        print_reverse_dependencies(target, repository, args.filter)
        return
    graph = build_test_dependency_graph(repository, args.package, args.filter)
    print_graph(args.package, graph, args.ascii)


def run_cargo_mode(args):
    """Построить граф версий Cargo с кешированием и вывести результат."""
    graph = build_cargo_dependency_graph(
        args.repository, args.package, args.version, args.filter
    )
    # Первый ключ — корень с фактическим номером версии из индекса.
    root = next(iter(graph), (args.package.lower(), args.version))
    if args.reverse is not None:
        target = parse_reverse_target(args.reverse, False)
        # Метаданные сборки не меняют равенство версий SemVer.
        target = next((
            node for node in graph if node[0] == target[0]
            and version_key(node[1]) == version_key(target[1])
        ), target)
        print_reverse_dependencies(
            target, graph, args.filter, lambda node: node[0],
            scope=format_node(root)
        )
        return
    print_graph(root, graph, args.ascii)


def main(argv=None):
    """Запустить выбранный режим и вернуть код завершения приложения."""
    args = parse_args(argv)
    try:
        if args.test_mode:
            run_test_mode(args)
        else:
            run_cargo_mode(args)
    except ValueError as error:
        # Сообщения об ошибках отделяем от обычного вывода программы.
        print(f"Ошибка: {error}", file=sys.stderr)
        return RUNTIME_ERROR
    return SUCCESS


# Запускаем приложение только при непосредственном запуске файла.
if __name__ == "__main__":
    raise SystemExit(main())