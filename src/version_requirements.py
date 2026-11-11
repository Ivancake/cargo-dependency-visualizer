"""Проверка требований к версиям Cargo средствами стандартной библиотеки."""

import operator
import re
from dataclasses import dataclass

if __package__:
    from .versions import (
        NUMBER_PATTERN, PRERELEASE_PART, parse_version, prerelease_key
    )
else:
    from versions import (
        NUMBER_PATTERN, PRERELEASE_PART, parse_version, prerelease_key
    )


FULL_COMPONENTS = 3
MAJOR_COMPONENTS = 1
MINOR_COMPONENTS = 2
EQUAL = 0
WILDCARDS = ("*", "x", "X")
COMPARISONS = {
    "=": operator.eq, ">": operator.gt, ">=": operator.ge,
    "<": operator.lt, "<=": operator.le,
}
COMPARATOR_PATTERN = re.compile(r"(>=|<=|>|<|=|\^|~)? *(.+)")
PARTIAL_PATTERN = re.compile(
    rf"(?P<core>{NUMBER_PATTERN}"
    rf"(?:\.(?:{NUMBER_PATTERN}|[*xX])){{0,2}})"
    rf"(?:-(?P<pre>{PRERELEASE_PART}(?:\.{PRERELEASE_PART})*))?"
    r"(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
)


@dataclass(frozen=True)
class Comparator:
    """Одно условие: оператор, указанные числа версии и её суффикс."""

    operator: str
    numbers: tuple
    prerelease: tuple = ()


def read_components(core):
    """Прочитать числовую часть, разрешив подстановки только в конце."""
    numbers = []
    wildcard = False
    for part in core.split("."):
        if part in WILDCARDS:
            wildcard = True
        else:
            if wildcard:
                raise ValueError("После подстановки нельзя указывать число.")
            numbers.append(int(part))
    return tuple(numbers), wildcard


def parse_partial(value):
    """Разобрать полную или сокращённую версию из условия Cargo."""
    match = PARTIAL_PATTERN.fullmatch(value)
    if not match:
        raise ValueError(f"Некорректная версия в требовании: {value}.")
    numbers, wildcard = read_components(match.group("core"))
    prerelease = match.group("pre")
    suffix = prerelease or match.group("build")
    if suffix and (wildcard or len(numbers) != FULL_COMPONENTS):
        raise ValueError("Суффикс требует трёх чисел версии без подстановок.")
    identifiers = tuple(prerelease.split(".")) if prerelease else ()
    return numbers, identifiers, wildcard


def parse_comparator(text):
    """Разобрать одно условие; отсутствие оператора означает совместимость."""
    match = COMPARATOR_PATTERN.fullmatch(text.strip(" "))
    if not match:
        raise ValueError(f"Некорректное условие версии: {text}.")
    explicit_operator, value = match.groups()
    numbers, prerelease, wildcard = parse_partial(value)
    # Подстановка без оператора означает совпадение указанного префикса.
    operation = explicit_operator or ("=" if wildcard else "^")
    return Comparator(operation, numbers, prerelease)


def parse_requirement(text):
    """Разобрать условия через запятую; каждое из них обязательно."""
    if not isinstance(text, str) or not text.strip(" "):
        raise ValueError("Требование версии должно быть непустой строкой.")
    if text.strip(" ") in WILDCARDS:
        return ()
    return tuple(parse_comparator(part) for part in text.split(","))


def compare_partial(version, comparator):
    """Сравнить указанные части; предварительная версия требует полноты."""
    core, prerelease = version
    prefix = core[:len(comparator.numbers)]
    if prefix != comparator.numbers:
        return (prefix > comparator.numbers) - (prefix < comparator.numbers)
    if len(comparator.numbers) < FULL_COMPONENTS:
        return None if prerelease else EQUAL
    left = prerelease_key(prerelease)
    right = prerelease_key(comparator.prerelease)
    return (left > right) - (left < right)


def matches_tilde(version, comparator):
    """Проверить ~: сохраняем major и, если задан, minor."""
    core, prerelease = version
    size = min(len(comparator.numbers), MINOR_COMPONENTS)
    if core[:size] != comparator.numbers[:size]:
        return False
    if len(comparator.numbers) == FULL_COMPONENTS:
        if core[2] != comparator.numbers[2]:
            return core[2] > comparator.numbers[2]
    return prerelease_key(prerelease) >= prerelease_key(comparator.prerelease)


def matches_caret(version, comparator):
    """Проверить ^ с учётом особых правил для начального нуля."""
    core, prerelease = version
    numbers = comparator.numbers
    if core[0] != numbers[0]:
        return False
    if len(numbers) == MAJOR_COMPONENTS:
        return True
    if len(numbers) == MINOR_COMPONENTS:
        return core[1] >= numbers[1] if numbers[0] else core[1] == numbers[1]
    left = prerelease_key(prerelease)
    right = prerelease_key(comparator.prerelease)
    if numbers[0]:
        return (core[1:], left) >= (numbers[1:], right)
    if numbers[1]:
        return core[1] == numbers[1] and (core[2], left) >= (numbers[2], right)
    return core[1:] == numbers[1:] and left >= right


def matches_comparator(version, comparator):
    """Проверить одно условие без общего ограничения prerelease."""
    if comparator.operator == "^":
        return matches_caret(version, comparator)
    if comparator.operator == "~":
        return matches_tilde(version, comparator)
    relation = compare_partial(version, comparator)
    if relation is None:
        return False
    return COMPARISONS[comparator.operator](relation, EQUAL)


def matches_parsed_requirement(version, comparators):
    """Проверить версию по заранее разобранным условиям Cargo."""
    parsed = parse_version(version)
    if not all(matches_comparator(parsed, item) for item in comparators):
        return False
    core, prerelease = parsed
    # Предварительный выпуск требует явного суффикса для тех же трёх чисел.
    return not prerelease or any(
        item.prerelease and item.numbers == core for item in comparators
    )


def matches_requirement(version, requirement):
    """Проверить, подходит ли точная версия под строку требования Cargo."""
    return matches_parsed_requirement(version, parse_requirement(requirement))