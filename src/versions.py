"""Разбор и сравнение версий по правилам SemVer."""

import re


NUMBER_PATTERN = r"(?:0|[1-9][0-9]*)"
PRERELEASE_PART = r"(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
VERSION_PATTERN = re.compile(
    rf"({NUMBER_PATTERN})\.({NUMBER_PATTERN})\.({NUMBER_PATTERN})"
    rf"(?:-({PRERELEASE_PART}(?:\.{PRERELEASE_PART})*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)


def parse_version(value):
    """Разобрать версию на три числа и части предварительной версии."""
    if not isinstance(value, str):
        raise ValueError("Версия должна быть строкой.")
    match = VERSION_PATTERN.fullmatch(value)
    if not match:
        raise ValueError(f"Некорректная версия SemVer: {value}.")
    major, minor, patch, prerelease = match.groups()
    core = (int(major), int(minor), int(patch))
    identifiers = tuple(prerelease.split(".")) if prerelease else ()
    return core, identifiers


def identifier_key(identifier):
    """Подготовить часть предварительной версии для сравнения."""
    if identifier.isdigit():
        return False, int(identifier)
    return True, identifier


def prerelease_key(identifiers):
    """Поставить стабильный выпуск выше предварительных версий."""
    stable = not identifiers
    parts = tuple(identifier_key(part) for part in identifiers)
    return stable, parts


def version_key(value):
    """Получить ключ для сортировки версий и выбора максимальной."""
    core, identifiers = parse_version(value)
    return core, prerelease_key(identifiers)


def compare_versions(left, right):
    """Вернуть -1, 0 или 1 для меньшей, равной или большей версии."""
    left_key = version_key(left)
    right_key = version_key(right)
    return (left_key > right_key) - (left_key < right_key)