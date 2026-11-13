"""Выбор самой новой подходящей версии из индекса Cargo."""

if __package__:
    from .cargo_repository import parse_index_record
    from .version_requirements import (
        matches_parsed_requirement, parse_requirement
    )
    from .versions import version_key
else:
    from cargo_repository import parse_index_record
    from version_requirements import (
        matches_parsed_requirement, parse_requirement
    )
    from versions import version_key


def record_is_yanked(record):
    """Проверить флаг отзыва версии, считая отсутствующий флаг ложным."""
    value = record.get("yanked", False)
    if not isinstance(value, bool):
        raise ValueError("Поле yanked должно содержать true или false.")
    return value


def read_package_versions(index_text, package):
    """Прочитать и проверить записи всех версий одного пакета."""
    records = []
    seen = set()
    for line_number, line in enumerate(index_text.splitlines(), start=1):
        if not line.strip():
            continue
        record = parse_index_record(line, line_number)
        if record["name"].lower() != package.lower():
            continue
        key = version_key(record["vers"])
        if key in seen:
            raise ValueError(
                f"Версия {record['vers']} пакета {package} повторяется."
            )
        seen.add(key)
        record_is_yanked(record)
        records.append(record)
    return records


def select_latest_version(records, package, requirement):
    """Выбрать новейшую неотозванную версию из проверенных записей пакета."""
    comparators = parse_requirement(requirement)
    candidates = [
        record for record in records
        if not record_is_yanked(record)
        and matches_parsed_requirement(record["vers"], comparators)
    ]
    if not candidates:
        raise ValueError(
            f"Для пакета {package} не найдена неотозванная версия "
            f"по требованию {requirement}."
        )
    return max(candidates, key=lambda record: version_key(record["vers"]))


def select_package_version(index_text, package, requirement):
    """Прочитать индекс и вернуть полную запись подходящей версии пакета."""
    records = read_package_versions(index_text, package)
    return select_latest_version(records, package, requirement)