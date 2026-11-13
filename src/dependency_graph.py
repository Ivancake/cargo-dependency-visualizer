"""Построение графа зависимостей рекурсивным обходом в ширину."""


def build_dependency_graph(
    root, get_dependencies, excluded_substring="", get_name=str
):
    """Получить достижимый граф BFS с фильтрацией по подстроке имени.
    Рекурсия обрабатывает уровни, обнаруженные вершины не ставятся повторно.
    """
    if excluded_substring and excluded_substring in get_name(root):
        return {}
    graph = {}
    discovered = {root}

    def visit_level(level):
        """Обработать текущий уровень и рекурсивно перейти к следующему."""
        if not level:
            return
        next_level = []
        for package in level:
            dependencies = list(dict.fromkeys(
                dependency for dependency in get_dependencies(package)
                if not excluded_substring
                or excluded_substring not in get_name(dependency)
            ))
            graph[package] = dependencies
            for dependency in dependencies:
                if dependency not in discovered:
                    discovered.add(dependency)
                    next_level.append(dependency)
        visit_level(next_level)

    try:
        visit_level([root])
    except RecursionError as error:
        raise ValueError(
            "Граф слишком глубокий для рекурсивного BFS."
        ) from error
    return graph


def build_test_dependency_graph(repository, root, excluded_substring=""):
    """Построить граф из предварительно проверенного тестового словаря."""
    if root not in repository:
        raise ValueError(f"Пакет {root} отсутствует в тестовом репозитории.")
    return build_dependency_graph(
        root, lambda package: repository[package], excluded_substring
    )
