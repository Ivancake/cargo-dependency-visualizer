"""Загрузка графа Cargo с кешированием индексов и выбора версий."""

import re

if __package__:
    from .cargo_repository import download_package_index, validate_dependency
    from .dependency_graph import build_dependency_graph
    from .version_selection import read_package_versions, select_latest_version
    from .versions import version_key
else:
    from cargo_repository import download_package_index, validate_dependency
    from dependency_graph import build_dependency_graph
    from version_selection import read_package_versions, select_latest_version
    from versions import version_key


PACKAGE_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")


def package_key(package):
    """Проверить имя пакета и привести его к ключу кеша и пути индекса."""
    if not isinstance(package, str) or not PACKAGE_PATTERN.fullmatch(package):
        raise ValueError("Некорректное имя пакета Cargo.")
    return package.lower()


class CargoRepository:
    """Хранить загруженные версии и выбранные записи в памяти обхода."""

    def __init__(self, repository, excluded_substring=""):
        """Сохранить адрес, фильтр и создать два пустых кеша."""
        self.repository = repository.rstrip("/")
        self.excluded_substring = excluded_substring
        self._versions = {}
        self._choices = {}

    def get_versions(self, package):
        """Загрузить и проверить индекс пакета только при первом запросе."""
        name = package_key(package)
        if name not in self._versions:
            text = download_package_index(self.repository, name)
            records = read_package_versions(text, name)
            self._versions[name] = records
        return self._versions[name]

    def get_exact(self, package, version):
        """Получить явно заданную версию, включая отозванный выпуск."""
        target = version_key(version)
        for record in self.get_versions(package):
            if version_key(record["vers"]) == target:
                return record
        raise ValueError(f"Пакет {package} версии {version} не найден.")

    def select(self, package, requirement):
        """Выбрать версию зависимости и сохранить результат по требованию."""
        name = package_key(package)
        key = (name, requirement)
        if key not in self._choices:
            self._choices[key] = select_latest_version(
                self.get_versions(name), name, requirement
            )
        return self._choices[key]

    def resolve_dependency(self, dependency):
        """Превратить описание зависимости в вершину или исключить её."""
        dependency = validate_dependency(dependency)
        name = package_key(dependency.get("package") or dependency["name"])
        if self.excluded_substring and self.excluded_substring in name:
            return None
        registry = dependency.get("registry")
        if registry is not None:
            if not isinstance(registry, str) or (
                registry.rstrip("/") != self.repository
            ):
                raise ValueError(
                    f"Зависимость {name} из другого репозитория "
                    "пока не поддерживается."
                )
        record = self.select(name, dependency["req"])
        return package_key(record["name"]), record["vers"]

    def get_dependencies(self, node):
        """Вернуть вершины прямых зависимостей пары (имя, версия)."""
        package, version = node
        record = self.get_exact(package, version)
        dependencies = []
        for description in record["deps"]:
            dependency = self.resolve_dependency(description)
            if dependency is not None:
                dependencies.append(dependency)
        return list(dict.fromkeys(dependencies))


def build_cargo_dependency_graph(
    repository, package, version, excluded_substring=""
):
    """Построить граф версий одного HTTP-индекса рекурсивным BFS."""
    name = package_key(package)
    version_key(version)
    if excluded_substring and excluded_substring in name:
        return {}
    source = CargoRepository(repository, excluded_substring)
    record = source.get_exact(name, version)
    root = (name, record["vers"])
    return build_dependency_graph(
        root, source.get_dependencies, excluded_substring,
        get_name=lambda node: node[0]
    )