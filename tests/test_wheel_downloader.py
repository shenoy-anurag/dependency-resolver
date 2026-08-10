import unittest

import wheel_downloader


class WheelDownloaderTests(unittest.TestCase):
    def test_build_download_plan_uses_versions_mapping(self):
        tree = {
            "versions": {
                "requests": "2.34.2",
                "urllib3": "2.2.0",
            },
            "wheel_urls": {
                "requests": ["https://example.com/requests-2.34.2-py3-none-any.whl"],
                "urllib3": ["https://example.com/urllib3-2.2.0-py3-none-any.whl"],
            },
        }

        plan = wheel_downloader.build_download_plan(tree)

        self.assertEqual(
            plan,
            [
                ("requests", "2.34.2", ["https://example.com/requests-2.34.2-py3-none-any.whl"]),
                ("urllib3", "2.2.0", ["https://example.com/urllib3-2.2.0-py3-none-any.whl"]),
            ],
        )

    def test_select_best_wheel_url_prefers_matching_environment_tags(self):
        candidates = [
            "https://example.com/demo-1.0-py3-none-any.whl",
            "https://example.com/demo-1.0-cp313-cp313-macosx_11_0_arm64.whl",
        ]

        selected = wheel_downloader.select_best_wheel_url(
            "demo",
            "1.0",
            candidates,
            python_tag="cp313",
            abi_tag="cp313",
            platform_tag="macosx_11_0_arm64",
        )

        self.assertEqual(selected, candidates[1])


if __name__ == "__main__":
    unittest.main()
