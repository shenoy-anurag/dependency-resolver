import unittest
from unittest.mock import patch

import remote_dep_resolver


class DummyResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class RemoteDependencyResolverTests(unittest.TestCase):
    def test_fetch_pypi_metadata_uses_the_pypi_json_api(self):
        payload = {
            "info": {
                "version": "2.32.0",
                "requires_distribution": ["charset-normalizer<4,>=2", "idna<4,>=2.5"],
            },
            "releases": {},
        }

        with patch("remote_dep_resolver.requests.get") as mock_get:
            mock_get.return_value = DummyResponse(200, payload)
            version, requires_dist = remote_dep_resolver.fetch_pypi_metadata("Requests")

        self.assertEqual(version, "2.32.0")
        self.assertEqual(requires_dist, ["charset-normalizer<4,>=2", "idna<4,>=2.5"])
        self.assertEqual(mock_get.call_args.args[0], "https://pypi.org/pypi/requests/json")

    def test_build_dependency_tree_reports_circular_dependencies(self):
        def fake_fetch(package_name, version=None):
            if package_name == "requests":
                return "2.32.0", ["urllib3>=2"]
            if package_name == "urllib3":
                return "2.2.0", ["requests>=2"]
            return None, []

        with patch("remote_dep_resolver.fetch_pypi_metadata", side_effect=fake_fetch):
            tree = remote_dep_resolver.build_dependency_tree("requests")

        self.assertEqual(tree["version"], "2.32.0")
        self.assertIn("urllib3", tree["dependencies"])
        self.assertEqual(
            tree["dependencies"]["urllib3"]["dependencies"]["requests"]["dependencies"],
            "Circular Dependency Detected",
        )

    def test_collect_wheel_download_urls_returns_wheel_links(self):
        payload = {
            "urls": [
                {
                    "filename": "requests-2.34.2-py3-none-any.whl",
                    "packagetype": "bdist_wheel",
                    "url": "https://files.pythonhosted.org/packages/abc/requests-2.34.2-py3-none-any.whl",
                },
                {
                    "filename": "requests-2.34.2.tar.gz",
                    "packagetype": "sdist",
                    "url": "https://files.pythonhosted.org/packages/abc/requests-2.34.2.tar.gz",
                },
            ]
        }

        with patch("remote_dep_resolver.requests.get") as mock_get:
            mock_get.return_value = DummyResponse(200, payload)
            urls = remote_dep_resolver.collect_wheel_download_urls("requests", "2.34.2")

        self.assertEqual(
            urls,
            {"https://files.pythonhosted.org/packages/abc/requests-2.34.2-py3-none-any.whl"},
        )

    def test_build_adjacency_list_exports_dependencies(self):
        tree = {
            "name": "requests",
            "version": "2.34.2",
            "dependencies": {
                "urllib3": {"name": "urllib3", "version": "2.7.0", "dependencies": {}},
                "idna": {"name": "idna", "version": "3.18", "dependencies": {}},
            },
        }

        adjacency = remote_dep_resolver.build_adjacency_list(tree)

        self.assertEqual(adjacency["requests"], ["urllib3", "idna"])
        self.assertEqual(adjacency["urllib3"], [])

    def test_collect_dependency_artifacts_collects_all_package_names_and_wheels(self):
        tree = {
            "name": "requests",
            "version": "2.34.2",
            "dependencies": {
                "urllib3": {"name": "urllib3", "version": "2.7.0", "dependencies": {}},
                "idna": {"name": "idna", "version": "3.18", "dependencies": {}},
            },
        }

        with patch("remote_dep_resolver.collect_wheel_download_urls", side_effect=lambda name, version: {f"{name}-{version}-wheel"}):
            wheel_urls, package_names = remote_dep_resolver.collect_dependency_artifacts(tree)

        self.assertEqual(wheel_urls["requests"], ["requests-2.34.2-wheel"])
        self.assertEqual(wheel_urls["urllib3"], ["urllib3-2.7.0-wheel"])
        self.assertEqual(wheel_urls["idna"], ["idna-3.18-wheel"])
        self.assertEqual(package_names, ["idna", "requests", "urllib3"])


if __name__ == "__main__":
    unittest.main()
