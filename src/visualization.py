"""Текстовое представление графа в формате Graphviz и ASCII-дерева."""


def format_node(node):
    """Подготовить подпись пакета или пары (имя, версия)."""
    if isinstance(node, tuple):
        package, version = node
        return f"{package}@{version}"
    return str(node)


def collect_nodes(graph):
    """Собрать все вершины, включая указанные только в списках соседей."""
    nodes = dict.fromkeys(graph)
    for dependencies in graph.values():
        nodes.update(dict.fromkeys(dependencies))
    return list(nodes)


def quote_label(value):
    """Экранировать подпись для строки в двойных кавычках языка DOT."""
    text = value.replace("\\", "\\\\").replace('"', '\\"')
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return '"' + text.replace("\n", "\\n") + '"'


def to_graphviz(graph, get_label=format_node):
    """Сформировать описание ориентированного графа на языке DOT."""
    identifiers = {
        node: f"n{index}" for index, node in enumerate(collect_nodes(graph))
    }
    lines = ["digraph dependencies {", "    rankdir=LR;"]
    for node, identifier in identifiers.items():
        label = quote_label(get_label(node))
        lines.append(f"    {identifier} [label={label}];")
    for package, dependencies in graph.items():
        for dependency in dict.fromkeys(dependencies):
            source = identifiers[package]
            target = identifiers[dependency]
            lines.append(f"    {source} -> {target};")
    lines.append("}")
    return "\n".join(lines)


def tree_children(graph, node):
    """Получить итератор соседей с признаком последней ветки."""
    dependencies = list(dict.fromkeys(graph.get(node, [])))
    return iter(
        (dependency, index == len(dependencies) - 1)
        for index, dependency in enumerate(dependencies)
    )


def to_ascii_tree(graph, root, get_label=format_node):
    """Показать достижимую часть графа деревом, отмечая циклы и повторы."""
    if not graph:
        return "(пустой граф)"
    if root not in collect_nodes(graph):
        raise ValueError("Начальный пакет отсутствует в графе.")
    lines = [get_label(root)]
    expanded = {root}
    path = {root}
    stack = [(root, tree_children(graph, root), "")]
    while stack:
        parent, children, prefix = stack[-1]
        item = next(children, None)
        if item is None:
            path.remove(parent)
            stack.pop()
            continue
        child, last = item
        marker = ""
        if child in path:
            marker = " [цикл]"
        elif child in expanded:
            marker = " [повтор]"
        branch = "`-- " if last else "|-- "
        lines.append(prefix + branch + get_label(child) + marker)
        if marker:
            continue
        expanded.add(child)
        path.add(child)
        child_prefix = prefix + ("    " if last else "|   ")
        stack.append((child, tree_children(graph, child), child_prefix))
    return "\n".join(lines)