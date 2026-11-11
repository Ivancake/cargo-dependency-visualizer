"""Проверки текста Graphviz и ASCII-дерева зависимостей."""

import sys
import unittest
from copy import deepcopy

from src.visualization import (
    collect_nodes, format_node, quote_label, to_ascii_tree, to_graphviz
)


class TestVisualization(unittest.TestCase):
    """Проверить сохранение вершин, связей и обработку повторных посещений."""

    def test_node_labels(self):
        """Подписать тестовый пакет и пакет Cargo с точной версией."""
        self.assertEqual(format_node("A"), "A")
        self.assertEqual(format_node(("demo", "1.2.3")), "demo@1.2.3")

    def test_collect_nodes(self):
        """Сохранить порядок ключей и добавить неявную вершину один раз."""
        self.assertEqual(
            collect_nodes({"A": ["B", "B"], "X": []}), ["A", "X", "B"]
        )

    def test_graphviz_edges_and_isolated_node(self):
        """Сохранить каждое ребро и объявить изолированную вершину."""
        graph = {"A": ["B", "B"], "B": [], "X": []}
        self.assertEqual(to_graphviz(graph).splitlines(), [
            "digraph dependencies {", "    rankdir=LR;",
            '    n0 [label="A"];', '    n1 [label="B"];',
            '    n2 [label="X"];', "    n0 -> n1;", "}"
        ])

    def test_graphviz_cycle(self):
        """Сохранить цикл и ссылку на себя в описании Graphviz."""
        text = to_graphviz({"A": ["A", "B"], "B": ["A"]})
        for edge in ("n0 -> n0;", "n0 -> n1;", "n1 -> n0;"):
            self.assertIn(edge, text)

    def test_graphviz_distinct_versions(self):
        """Назначить отдельные идентификаторы разным версиям библиотеки."""
        first, second = ("demo", "1.0.0"), ("demo", "2.0.0")
        text = to_graphviz({first: [second], second: []})
        self.assertIn('n0 [label="demo@1.0.0"]', text)
        self.assertIn('n1 [label="demo@2.0.0"]', text)
        self.assertIn("n0 -> n1;", text)

    def test_same_labels_keep_distinct_nodes(self):
        """Сохранить разные вершины при одинаковой пользовательской подписи."""
        text = to_graphviz({"A": ["B"], "B": []}, lambda node: "пакет")
        self.assertEqual(text.count('[label="пакет"]'), 2)
        self.assertIn("n0 -> n1;", text)

    def test_label_escaping(self):
        """Защитить кавычки и обратную косую черту внутри подписи DOT."""
        self.assertEqual(quote_label('A"B\\N'), '"A\\"B\\\\N"')
        self.assertEqual(quote_label("A\r\nB\rC"), '"A\\nB\\nC"')
        text = to_graphviz({'A"B': []})
        self.assertIn('label="A\\"B"', text)

    def test_empty_graph(self):
        """Вернуть корректное пустое описание и сообщение для дерева."""
        self.assertEqual(
            to_graphviz({}), "digraph dependencies {\n    rankdir=LR;\n}"
        )
        self.assertEqual(to_ascii_tree({}, "A"), "(пустой граф)")

    def test_ascii_branches(self):
        """Сохранить вертикальную линию и отступы соседних веток."""
        graph = {
            "A": ["B", "C"], "B": ["D", "E"], "C": [], "D": [], "E": []
        }
        self.assertEqual(to_ascii_tree(graph, "A").splitlines(), [
            "A", "|-- B", "|   |-- D", "|   `-- E", "`-- C"
        ])

    def test_ascii_cycle(self):
        """Отметить ребро к предку, остановив дальнейшее раскрытие цикла."""
        graph = {"A": ["B"], "B": ["C"], "C": ["A"]}
        self.assertEqual(to_ascii_tree(graph, "A").splitlines(), [
            "A", "`-- B", "    `-- C", "        `-- A [цикл]"
        ])

    def test_ascii_self_reference(self):
        """Показать ссылку на себя как цикл."""
        self.assertEqual(
            to_ascii_tree({"A": ["A"]}, "A"), "A\n`-- A [цикл]"
        )

    def test_ascii_shared_dependency(self):
        """Показать общую зависимость повторно без раскрытия её потомков."""
        graph = {
            "A": ["B", "C"], "B": ["D"], "C": ["D"],
            "D": ["E"], "E": []
        }
        self.assertEqual(to_ascii_tree(graph, "A").splitlines(), [
            "A", "|-- B", "|   `-- D", "|       `-- E",
            "`-- C", "    `-- D [повтор]"
        ])

    def test_ascii_distinct_versions(self):
        """Раскрыть разные версии отдельно и отметить повтор одной версии."""
        root = ("root", "1.0.0")
        first, second = ("demo", "1.0.0"), ("demo", "2.0.0")
        graph = {root: [first, second], first: [second], second: []}
        self.assertEqual(to_ascii_tree(graph, root).splitlines(), [
            "root@1.0.0", "|-- demo@1.0.0", "|   `-- demo@2.0.0",
            "`-- demo@2.0.0 [повтор]"
        ])

    def test_missing_root(self):
        """Сообщить об отсутствии корня в непустом графе."""
        with self.assertRaisesRegex(ValueError, "отсутствует"):
            to_ascii_tree({"A": []}, "B")

    def test_referenced_leaf(self):
        """Поддержать вершину без отдельного ключа и её выбор корнем."""
        graph = {"A": ["B"]}
        self.assertIn('n1 [label="B"]', to_graphviz(graph))
        self.assertEqual(to_ascii_tree(graph, "A"), "A\n`-- B")
        self.assertEqual(to_ascii_tree(graph, "B"), "B")

    def test_unreachable_nodes(self):
        """Показать весь граф в DOT и только выбранную компоненту в дереве."""
        graph = {"A": [], "X": ["Y"], "Y": []}
        self.assertIn('label="X"', to_graphviz(graph))
        self.assertEqual(to_ascii_tree(graph, "A"), "A")

    def test_deep_tree_without_recursion(self):
        """Построить глубокое дерево без рекурсивных вызовов визуализатора."""
        depth = sys.getrecursionlimit() + 10
        graph = {index: [index + 1] for index in range(depth)}
        graph[depth] = []
        self.assertEqual(len(to_ascii_tree(graph, 0).splitlines()), depth + 1)

    def test_source_unchanged(self):
        """Не менять исходные списки при удалении повторов для вывода."""
        graph = {"A": ["B", "B"], "B": []}
        original = deepcopy(graph)
        to_graphviz(graph)
        self.assertEqual(to_ascii_tree(graph, "A"), "A\n`-- B")
        self.assertEqual(graph, original)


if __name__ == "__main__":
    unittest.main()