"""Поиск прямых и транзитивных обратных зависимостей в заданном графе."""

if __package__:
    from .dependency_graph import build_dependency_graph
else:
    from dependency_graph import build_dependency_graph


def reverse_graph(graph):
    """Развернуть рёбра, сохранив все вершины и порядок соседей."""
    reversed_graph = {package: [] for package in graph}
    for package, dependencies in graph.items():
        # Повтор одной зависимости не должен создавать одинаковые рёбра.
        for dependency in dict.fromkeys(dependencies):
            reversed_graph.setdefault(dependency, []).append(package)
    return reversed_graph


def find_reverse_dependencies(
    graph, package, excluded_substring="", get_name=str
):
    """Найти зависящие от пакета вершины рекурсивным BFS по обратным рёбрам."""
    reversed_graph = reverse_graph(graph)
    if package not in reversed_graph:
        raise ValueError(f"Пакет {get_name(package)} отсутствует в графе.")
    reachable = build_dependency_graph(
        package, reversed_graph.__getitem__, excluded_substring, get_name
    )
    # Корень не включаем в ответ даже при цикле или ссылке на себя.
    return [node for node in reachable if node != package]