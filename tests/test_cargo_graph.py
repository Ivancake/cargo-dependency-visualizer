"""Проверки кеша, выбора версий и полного обхода графа Cargo."""

import json
import unittest
from unittest.mock import Mock, patch

from src.cargo_graph import (
    CargoRepository,
    build_cargo_dependency_graph,
    package_key,
)
from src.version_selection import select_latest_version


REPOSITORY = "https://example.org/index"


class TestCargoGraph(unittest.TestCase):
    """Проверки графа Cargo с имитацией загрузки индексов."""

    def record(self, name, version="1.0.0", dependencies=None, yanked=False):
        """Подготовить запись одной версии пакета."""
        return {
            "name": name, "vers": version, "yanked": yanked,
            "deps": [] if dependencies is None else dependencies,
        }

    def dependency(
        self, name, requirement="^1", actual_name=None, registry=None
    ):
        """Подготовить описание зависимости, включая возможный псевдоним."""
        return {
            "name": name, "req": requirement,
            "package": actual_name, "registry": registry,
        }

    def downloader(self, indexes):
        """Создать подмену загрузчика с отдельными данными каждого пакета."""
        def download(repository, package):
            """Вернуть строки JSON из подготовленного индекса."""
            return "\n".join(json.dumps(item) for item in indexes[package])

        return Mock(side_effect=download)

    def test_index_cache(self):
        """Повторный запрос с другим регистром не должен загружать индекс."""
        records = [self.record("demo")]
        download = self.downloader({"demo": records})
        with patch("src.cargo_graph.download_package_index", download):
            source = CargoRepository(REPOSITORY)
            self.assertEqual(source.get_versions("Demo"), records)
            self.assertEqual(source.get_versions("demo"), records)
        download.assert_called_once_with(REPOSITORY, "demo")

    def test_two_versions_one_download(self):
        """Получить две версии из одного скачанного индекса."""
        records = [self.record("demo"), self.record("demo", "2.0.0")]
        download = self.downloader({"demo": records})
        with patch("src.cargo_graph.download_package_index", download):
            source = CargoRepository(REPOSITORY)
            self.assertEqual(source.get_exact("demo", "1.0.0")["vers"], "1.0.0")
            self.assertEqual(source.get_exact("demo", "2.0.0")["vers"], "2.0.0")
        download.assert_called_once()

    def test_selection_cache(self):
        """Не выбирать версию повторно для того же имени и требования."""
        download = self.downloader({"demo": [self.record("demo")]})
        with patch("src.cargo_graph.download_package_index", download):
            with patch(
                "src.cargo_graph.select_latest_version",
                wraps=select_latest_version
            ) as choose:
                source = CargoRepository(REPOSITORY)
                first = source.select("demo", "^1")
                self.assertEqual(source.select("Demo", "^1"), first)
        choose.assert_called_once()
        download.assert_called_once()

    def test_explicit_yanked_version(self):
        """Разрешить явный выпуск, запретив его автоматический выбор."""
        record = self.record("demo", "1.0.0+build", yanked=True)
        download = self.downloader({"demo": [record]})
        with patch("src.cargo_graph.download_package_index", download):
            source = CargoRepository(REPOSITORY)
            self.assertEqual(source.get_exact("demo", "1.0.0"), record)
            with self.assertRaises(ValueError):
                source.select("demo", "=1.0.0")
        download.assert_called_once()

    def test_missing_exact_version(self):
        """Не подменять явно заданную отсутствующую версию другой."""
        download = self.downloader({"demo": [self.record("demo")]})
        with patch("src.cargo_graph.download_package_index", download):
            source = CargoRepository(REPOSITORY)
            with self.assertRaisesRegex(ValueError, "2.0.0 не найден"):
                source.get_exact("demo", "2.0.0")

    def test_renamed_dependency(self):
        """Выбрать настоящее имя и сохранить optional-зависимость."""
        dependency = self.dependency("alias", actual_name="helper")
        dependency.update({"optional": True, "kind": "dev"})
        indexes = {
            "demo": [self.record("demo", dependencies=[dependency])],
            "helper": [self.record("helper", "1.2.0")],
        }
        download = self.downloader(indexes)
        with patch("src.cargo_graph.download_package_index", download):
            graph = build_cargo_dependency_graph(REPOSITORY, "demo", "1.0.0")
        self.assertEqual(graph, {
            ("demo", "1.0.0"): [("helper", "1.2.0")],
            ("helper", "1.2.0"): [],
        })

    def test_shared_dependency_and_cycle(self):
        """Сохранить общий пакет и цикл, скачав каждый индекс один раз."""
        indexes = {
            "demo": [self.record("demo", dependencies=[
                self.dependency("b"), self.dependency("c")
            ])],
            "b": [self.record("b", dependencies=[self.dependency("shared")])],
            "c": [self.record("c", dependencies=[self.dependency("shared")])],
            "shared": [self.record("shared", dependencies=[
                self.dependency("demo", "=1.0.0")
            ])],
        }
        download = self.downloader(indexes)
        with patch("src.cargo_graph.download_package_index", download):
            graph = build_cargo_dependency_graph(REPOSITORY, "demo", "1.0.0")
        self.assertEqual(list(graph), [
            ("demo", "1.0.0"), ("b", "1.0.0"),
            ("c", "1.0.0"), ("shared", "1.0.0")
        ])
        self.assertEqual(graph[("shared", "1.0.0")], [("demo", "1.0.0")])
        self.assertEqual(
            [call.args[1] for call in download.call_args_list],
            ["demo", "b", "c", "shared"]
        )

    def test_filter_before_download(self):
        """Не загружать исключённый пакет и не проверять его другой реестр."""
        indexes = {
            "demo": [self.record("demo", dependencies=[
                self.dependency("skipme", registry="https://other.org"),
                self.dependency("helper")
            ])],
            "helper": [self.record("helper")],
        }
        download = self.downloader(indexes)
        with patch("src.cargo_graph.download_package_index", download):
            graph = build_cargo_dependency_graph(
                REPOSITORY, "demo", "1.0.0", "skip"
            )
        self.assertEqual(graph[("demo", "1.0.0")], [("helper", "1.0.0")])
        self.assertEqual(
            [call.args[1] for call in download.call_args_list],
            ["demo", "helper"]
        )

    def test_filtered_root(self):
        """Не выполнять запросы при исключении начального пакета."""
        with patch("src.cargo_graph.download_package_index") as download:
            graph = build_cargo_dependency_graph(
                REPOSITORY, "Demo", "1.0.0", "demo"
            )
        self.assertEqual(graph, {})
        download.assert_not_called()

    def test_two_dependency_versions(self):
        """Различать две версии одной библиотеки, используя общий индекс."""
        indexes = {
            "demo": [self.record("demo", dependencies=[
                self.dependency("b"), self.dependency("c")
            ])],
            "b": [self.record("b", dependencies=[
                self.dependency("lib", "^1")
            ])],
            "c": [self.record("c", dependencies=[
                self.dependency("lib", "^2")
            ])],
            "lib": [self.record("lib", "1.5.0"), self.record("lib", "2.0.0")],
        }
        download = self.downloader(indexes)
        with patch("src.cargo_graph.download_package_index", download):
            graph = build_cargo_dependency_graph(REPOSITORY, "demo", "1.0.0")
        self.assertEqual(graph[("b", "1.0.0")], [("lib", "1.5.0")])
        self.assertEqual(graph[("c", "1.0.0")], [("lib", "2.0.0")])
        self.assertIn(("lib", "1.5.0"), graph)
        self.assertIn(("lib", "2.0.0"), graph)
        self.assertEqual(
            [call.args[1] for call in download.call_args_list].count("lib"), 1
        )

    def test_other_registry(self):
        """Отклонить другой реестр до запроса его пакета в текущем индексе."""
        indexes = {"demo": [self.record("demo", dependencies=[
            self.dependency("helper", registry="https://other.org")
        ])]}
        download = self.downloader(indexes)
        with patch("src.cargo_graph.download_package_index", download):
            with self.assertRaisesRegex(ValueError, "другого репозитория"):
                build_cargo_dependency_graph(REPOSITORY, "demo", "1.0.0")
        download.assert_called_once_with(REPOSITORY, "demo")

    def test_same_registry(self):
        """Разрешить явный адрес текущего реестра с завершающим слешем."""
        dependency = self.dependency("helper", registry=REPOSITORY + "/")
        indexes = {
            "demo": [self.record("demo", dependencies=[dependency])],
            "helper": [self.record("helper")],
        }
        download = self.downloader(indexes)
        with patch("src.cargo_graph.download_package_index", download):
            graph = build_cargo_dependency_graph(REPOSITORY, "demo", "1.0.0")
        self.assertIn(("helper", "1.0.0"), graph)

    def test_failed_download_not_cached(self):
        """После ошибки разрешить повторную попытку загрузки индекса."""
        text = json.dumps(self.record("demo"))
        download = Mock(side_effect=[ValueError("Нет соединения"), text])
        with patch("src.cargo_graph.download_package_index", download):
            source = CargoRepository(REPOSITORY)
            with self.assertRaisesRegex(ValueError, "Нет соединения"):
                source.get_versions("demo")
            self.assertEqual(source.get_versions("demo")[0]["vers"], "1.0.0")
        self.assertEqual(download.call_count, 2)

    def test_invalid_package_name(self):
        """Отклонить имя, которое нельзя использовать в пути индекса."""
        for name in ("", "../helper", "1demo", None):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, "имя пакета"):
                    package_key(name)


if __name__ == "__main__":
    unittest.main()