"""Проверки рекурсивного BFS, циклов и фильтрации пакетов."""

import sys
import unittest
from unittest.mock import Mock

from src.dependency_graph import (
    build_dependency_graph,
    build_test_dependency_graph,
)


class TestDependencyGraph(unittest.TestCase):
    """Проверки структуры результата и порядка получения зависимостей."""

    def test_breadth_first_order(self):
        """Получать зависимости по уровням, а не уходить в глубину."""
        repository = {
            "A": ["B", "C"], "B": ["D"], "C": ["E"], "D": [], "E": []
        }
        loader = Mock(side_effect=repository.__getitem__)
        graph = build_dependency_graph("A", loader)
        expected_order = ["A", "B", "C", "D", "E"]
        self.assertEqual(list(graph), expected_order)
        self.assertEqual(
            [call.args[0] for call in loader.call_args_list], expected_order
        )
        self.assertEqual(graph, repository)

    def test_shared_dependency(self):
        """Сохранить общую зависимость, получая её список только один раз."""
        repository = {"A": ["B", "C"], "B": ["D"], "C": ["D"], "D": []}
        loader = Mock(side_effect=repository.__getitem__)
        graph = build_dependency_graph("A", loader)
        self.assertEqual(graph, repository)
        self.assertEqual(
            [call.args[0] for call in loader.call_args_list],
            ["A", "B", "C", "D"]
        )

    def test_cycle_and_self_reference(self):
        """Завершить обход цикла и сохранить рёбра, включая ссылку на себя."""
        repository = {"A": ["A", "B"], "B": ["A"]}
        loader = Mock(side_effect=repository.__getitem__)
        self.assertEqual(build_dependency_graph("A", loader), repository)
        self.assertEqual(
            [call.args[0] for call in loader.call_args_list], ["A", "B"]
        )

    def test_unreachable_packages(self):
        """Не включать пакеты, недостижимые из выбранного корня."""
        repository = {"A": ["B"], "B": [], "X": ["Y"], "Y": []}
        self.assertEqual(
            build_test_dependency_graph(repository, "A"),
            {"A": ["B"], "B": []}
        )

    def test_package_without_dependencies(self):
        """Сохранить корень даже при отсутствии зависимостей."""
        self.assertEqual(
            build_test_dependency_graph({"A": []}, "A"), {"A": []}
        )

    def test_filter_stops_branch(self):
        """Не получать исключённый пакет и не обходить его ветку."""
        repository = {"A": ["B", "C"], "B": ["D"], "C": [], "D": []}
        loader = Mock(side_effect=repository.__getitem__)
        graph = build_dependency_graph("A", loader, "B")
        self.assertEqual(graph, {"A": ["C"], "C": []})
        self.assertEqual(
            [call.args[0] for call in loader.call_args_list], ["A", "C"]
        )

    def test_alternative_path(self):
        """Сохранить потомка, достижимого через другую разрешённую ветку."""
        repository = {"A": ["B", "C"], "B": ["D"], "C": ["D"], "D": []}
        self.assertEqual(
            build_test_dependency_graph(repository, "A", "B"),
            {"A": ["C"], "C": ["D"], "D": []}
        )

    def test_filtered_root(self):
        """Вернуть пустой граф без загрузки исключённого корня."""
        loader = Mock()
        self.assertEqual(build_dependency_graph("ABC", loader, "B"), {})
        loader.assert_not_called()

    def test_empty_filter(self):
        """Пустая подстрока не должна исключать все пакеты."""
        repository = {"A": ["B"], "B": []}
        self.assertEqual(
            build_test_dependency_graph(repository, "A", ""), repository
        )

    def test_case_sensitive_filter(self):
        """Учитывать регистр символов при поиске подстроки."""
        repository = {"A": ["B"], "B": []}
        self.assertEqual(
            build_test_dependency_graph(repository, "A", "b"), repository
        )

    def test_duplicate_edges(self):
        """Убирать повтор рёбер, не меняя исходный список зависимостей."""
        repository = {"A": ["B", "B"], "B": []}
        self.assertEqual(
            build_test_dependency_graph(repository, "A"),
            {"A": ["B"], "B": []}
        )
        self.assertEqual(repository["A"], ["B", "B"])

    def test_missing_root(self):
        """Обработать пустой репозиторий и отсутствие выбранного пакета."""
        for repository in ({}, {"B": []}):
            with self.subTest(repository=repository):
                with self.assertRaisesRegex(ValueError, "отсутствует"):
                    build_test_dependency_graph(repository, "A")

    def test_different_versions(self):
        """Различать версии пакета и фильтровать только по его имени."""
        root = ("demo", "1.0.0")
        first = ("serde", "1.0.0")
        second = ("serde", "2.0.0")
        repository = {root: [first, second], first: [], second: []}
        loader = repository.__getitem__

        def get_name(package):
            """Выбрать имя из пары, не включая версию в фильтрацию."""
            return package[0]

        self.assertEqual(
            build_dependency_graph(root, loader, get_name=get_name), repository
        )
        self.assertEqual(
            build_dependency_graph(root, loader, "serde", get_name), {root: []}
        )
        self.assertEqual(
            build_dependency_graph(root, loader, "2.0", get_name), repository
        )

    def test_loader_error(self):
        """Передать ошибку получения зависимостей вызывающему коду."""
        loader = Mock(side_effect=ValueError("Ошибка репозитория"))
        with self.assertRaisesRegex(ValueError, "Ошибка репозитория"):
            build_dependency_graph("A", loader)

    def test_wide_graph(self):
        """Обработать широкий граф без рекурсии для каждой вершины."""
        children = [f"N{index}" for index in range(1500)]
        repository = {"ROOT": children}
        repository.update({child: [] for child in children})
        graph = build_dependency_graph("ROOT", repository.__getitem__)
        self.assertEqual(graph, repository)

    def test_deep_graph(self):
        """Сообщить о превышении глубины рекурсии понятной ошибкой."""
        depth = sys.getrecursionlimit() + 1

        def get_dependencies(package):
            """Построить длинную цепочку без подготовки большого словаря."""
            return [package + 1] if package < depth else []

        with self.assertRaisesRegex(ValueError, "слишком глубокий"):
            build_dependency_graph(0, get_dependencies)


if __name__ == "__main__":
    unittest.main()