import tempfile
import unittest
from pathlib import Path

import installer


class InstallerTests(unittest.TestCase):
    def test_build_install_order_installs_dependencies_before_dependents(self):
        tree = {
            "name": "root",
            "version": "1.0",
            "dependencies": {
                "alpha": {
                    "name": "alpha",
                    "version": "1.0",
                    "dependencies": {
                        "leaf": {
                            "name": "leaf",
                            "version": "1.0",
                            "dependencies": {},
                        }
                    },
                },
                "beta": {
                    "name": "beta",
                    "version": "1.0",
                    "dependencies": {},
                },
            },
        }

        order = installer.build_install_order(tree)

        self.assertEqual(order[0], "leaf")
        self.assertEqual(order[-1], "root")
        self.assertIn("beta", order)

    def test_select_wheel_for_environment_uses_matching_wheel_from_folder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wheel_path = Path(tmpdir) / "demo-1.0-py3-none-any.whl"
            wheel_path.write_bytes(b"dummy")

            matched = installer.select_wheel_for_environment(
                package_name="demo",
                version="1.0",
                wheel_dir=Path(tmpdir),
            )

            self.assertEqual(matched, wheel_path)

    def test_select_wheel_for_environment_prefers_requested_python_and_platform_tags(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            generic_wheel = Path(tmpdir) / "demo-1.0-py3-none-any.whl"
            generic_wheel.write_bytes(b"dummy")
            specific_wheel = Path(tmpdir) / "demo-1.0-cp311-cp311-macosx_11_0_arm64.whl"
            specific_wheel.write_bytes(b"dummy")

            matched = installer.select_wheel_for_environment(
                package_name="demo",
                version="1.0",
                wheel_dir=Path(tmpdir),
                python_tag="cp311",
                abi_tag="cp311",
                platform_tag="macosx_11_0_arm64",
            )

            self.assertEqual(matched, specific_wheel)


if __name__ == "__main__":
    unittest.main()
