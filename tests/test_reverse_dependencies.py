"""Проверки обратных зависимостей, циклов, фильтра и порядка BFS."""

from copy import deepcopy
import unittest

from src.reverse_dependencies import find_reverse_dependencies, reverse_graph


class TestReverseDependencies(unittest.TestCase):
    """Проверить поиск на полном переданном графе репозитория."""

    def test_reverse_edges(self):
        """Развернуть связи и сохранить вершину без обратных зависимостей."""
        graph = {"A": ["B", "C"], "B": ["C"], "C": [], "X": []}
        self.assertEqual(reverse_graph(graph), {
            "A": [], "B": ["A"], "C": ["A", "B"], "X": []
        })

    def test_direct_and_transitive(self):
        """Найти сначала прямую, затем транзитивную обратную зависимость."""
        graph = {"A": ["B"], "B": ["C"], "C": []}
        self.assertEqual(find_reverse_dependencies(graph, "C"), ["B", "A"])

    def test_breadth_first_order(self):
        """Выдать всех соседей текущего уровня раньше следующего уровня."""
        graph = {
            "A": ["B", "C"], "B": ["D"], "C": ["D"], "D": []
        }
        self.assertEqual(
            find_reverse_dependencies(graph, "D"), ["B", "C", "A"]
        )

    def test_outside_forward_graph(self):
        """Найти пакеты, которые не видны при прямом обходе от цели."""
        graph = {"A": ["B"], "B": [], "X": ["B"], "Y": ["X"]}
        self.assertEqual(
            find_reverse_dependencies(graph, "B"), ["A", "X", "Y"]
        )

    def test_cycle(self):
        """Завершить обход цикла и исключить сам искомый пакет из ответа."""
        graph = {"A": ["B"], "B": ["C"], "C": ["A"]}
        self.assertEqual(find_reverse_dependencies(graph, "A"), ["C", "B"])

    def test_self_reference(self):
        """Сохранить обратное ребро к себе, но не считать корень ответом."""
        graph = {"A": ["A"], "B": ["A"]}
        self.assertEqual(reverse_graph(graph), {"A": ["A", "B"], "B": []})
        self.assertEqual(find_reverse_dependencies(graph, "A"), ["B"])

    def test_no_dependents(self):
        """Вернуть пустой список для пакета без обратных зависимостей."""
        graph = {"A": ["B"], "B": [], "X": []}
        self.assertEqual(find_reverse_dependencies(graph, "A"), [])
        self.assertEqual(find_reverse_dependencies(graph, "X"), [])

    def test_missing_package(self):
        """Сообщить об отсутствии пакета, в том числе в пустом графе."""
        for graph in ({}, {"B": []}):
            with self.subTest(graph=graph):
                with self.assertRaisesRegex(ValueError, "A отсутствует"):
                    find_reverse_dependencies(graph, "A")

    def test_filter_stops_branch(self):
        """Остановить обратный обход на исключённом пакете."""
        graph = {"A": ["B"], "B": ["C"], "C": []}
        self.assertEqual(find_reverse_dependencies(graph, "C", "B"), [])

    def test_filter_keeps_alternative_path(self):
        """Найти пакет через другую ветку после исключения одной ветки."""
        graph = {
            "A": ["B", "C"], "B": ["D"], "C": ["D"], "D": []
        }
        self.assertEqual(
            find_reverse_dependencies(graph, "D", "B"), ["C", "A"]
        )

    def test_filtered_target(self):
        """Не выполнять обратный поиск от исключённой цели."""
        self.assertEqual(
            find_reverse_dependencies({"A": ["B"], "B": []}, "B", "B"), []
        )

    def test_case_sensitive_filter(self):
        """Учитывать регистр при фильтрации и разрешать пустой фильтр."""
        graph = {"A": ["B"], "B": []}
        self.assertEqual(find_reverse_dependencies(graph, "B", ""), ["A"])
        self.assertEqual(find_reverse_dependencies(graph, "B", "a"), ["A"])
        self.assertEqual(find_reverse_dependencies(graph, "B", "A"), [])

    def test_duplicate_edges(self):
        """Не повторять пакет из-за нескольких одинаковых связей."""
        graph = {"A": ["B", "B"], "B": []}
        self.assertEqual(reverse_graph(graph), {"A": [], "B": ["A"]})
        self.assertEqual(find_reverse_dependencies(graph, "B"), ["A"])

    def test_referenced_leaf(self):
        """Сохранить цель, указанную только в списке зависимостей."""
        self.assertEqual(reverse_graph({"A": ["B"]}), {"A": [], "B": ["A"]})
        self.assertEqual(find_reverse_dependencies({"A": ["B"]}, "B"), ["A"])

    def test_different_versions(self):
        """Различать версии и применять фильтр только к имени пакета."""
        first = ("helper", "1.0.0")
        second = ("helper", "2.0.0")
        root = ("demo", "1.0.0")
        other = ("extra", "1.0.0")
        graph = {root: [first], other: [second], first: [], second: []}
        get_name = lambda node: node[0]
        self.assertEqual(
            find_reverse_dependencies(graph, first, get_name=get_name), [root]
        )
        self.assertEqual(
            find_reverse_dependencies(graph, second, get_name=get_name),
            [other]
        )
        self.assertEqual(
            find_reverse_dependencies(graph, first, "demo", get_name), []
        )
        self.assertEqual(
            find_reverse_dependencies(graph, first, "1.0", get_name), [root]
        )

    def test_source_unchanged(self):
        """Не менять списки и ключи исходного графа при обратном поиске."""
        graph = {"A": ["B", "B"], "B": []}
        original = deepcopy(graph)
        find_reverse_dependencies(graph, "B")
        self.assertEqual(graph, original)


if __name__ == "__main__":
    unittest.main()