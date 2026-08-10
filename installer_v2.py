import argparse
import json
import subprocess
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from graphlib import TopologicalSorter

from packaging.tags import sys_tags
from packaging.utils import canonicalize_name, parse_wheel_filename


def get_install_order(data: dict) -> list[str]:
    adj_list = data.get("adjacency_list", {})

    # Python's TopologicalSorter expects key -> set of dependencies
    # graph = { package: set(dependencies) }
    graph = {pkg: set(deps) for pkg, deps in adj_list.items()}

    ts = TopologicalSorter(graph)
    # prepare() + static_order() returns nodes where dependencies come before dependents
    return list(ts.static_order())


def select_wheel_for_environment(
    package_name: str,
    version: Optional[str],
    wheel_dir: Path,
    python_tag: Optional[str] = None,
    abi_tag: Optional[str] = None,
    platform_tag: Optional[str] = None,
) -> Optional[Path]:
    """Pick the best wheel file from a folder for the requested Python, ABI, and platform tags."""
    safe_name = canonicalize_name(package_name)
    wheel_dir = Path(wheel_dir)
    if not wheel_dir.exists():
        return None

    version = version or ""
    python_tag = python_tag or f"py{sys.version_info.major}{sys.version_info.minor}"
    abi_tag = abi_tag or "none"
    platform_tag = platform_tag or "any"
    supported_tags = set(sys_tags())

    exact_candidates: List[Path] = []
    fallback_candidates: List[Path] = []

    for wheel_path in sorted(wheel_dir.glob("*.whl")):
        try:
            parsed_name, parsed_version, _build_tag, tags = parse_wheel_filename(
                wheel_path.name)
        except Exception:
            continue

        if parsed_name != safe_name:
            continue
        if version and str(parsed_version) != version:
            continue

        if not tags:
            continue

        tag_matches = False
        for tag in tags:
            if (
                tag.interpreter == python_tag
                and tag.abi == abi_tag
                and tag.platform == platform_tag
            ):
                tag_matches = True
                break

        if tag_matches:
            exact_candidates.append(wheel_path)
            continue

        if supported_tags.intersection(tags):
            fallback_candidates.append(wheel_path)
            continue

        for tag in tags:
            if tag.interpreter.startswith("py") and tag.abi == "none" and tag.platform == "any":
                fallback_candidates.append(wheel_path)
                break

    if exact_candidates:
        return exact_candidates[0]
    if fallback_candidates:
        return fallback_candidates[0]
    return None


def install_wheel(wheel_path: Path, pip_executable: Optional[str] = None) -> subprocess.CompletedProcess:
    """Install a wheel using pip."""
    executable = pip_executable or [sys.executable, "-m", "pip"]
    if isinstance(executable, str):
        cmd = [executable, "install", str(wheel_path)]
    else:
        cmd = [*executable, "install", str(wheel_path)]
    return subprocess.run(cmd, check=False)


def install_dependency_tree(tree: dict, wheel_dir: Path, pip_executable: Optional[str] = None) -> List[Tuple[str, Optional[Path]]]:
    """Install all packages from a dependency tree in dependency-first order."""
    install_order = get_install_order(tree)
    results: List[Tuple[str, Optional[Path]]] = []

    for package_name in install_order:
        version = tree["versions"][package_name]
        wheel_path = select_wheel_for_environment(
            package_name, version, wheel_dir)
        results.append((package_name, wheel_path))
        if wheel_path is None:
            continue
        print(package_name, version)
        # install_wheel(wheel_path, pip_executable=pip_executable)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Install Python wheels from a dependency tree in dependency-first order")
    parser.add_argument("dependency_tree", nargs="?",
                        help="Path to a dependency tree JSON file")
    parser.add_argument("--wheel-dir", default="wheels",
                        help="Directory containing wheel files")
    parser.add_argument("--python-tag", default=None)
    parser.add_argument("--abi-tag", default=None)
    parser.add_argument("--platform-tag", default=None)
    args = parser.parse_args()

    if not args.dependency_tree:
        parser.error("Please provide a dependency tree JSON file")

    tree_path = Path(args.dependency_tree)
    if not tree_path.exists():
        parser.error(f"Dependency tree file not found: {tree_path}")

    with tree_path.open("r", encoding="utf-8") as handle:
        tree = json.load(handle)

    wheel_dir = Path(args.wheel_dir)
    for package_name, wheel_path in install_dependency_tree(tree, wheel_dir):
        if wheel_path is None:
            print(f"{package_name}: no matching wheel found")
        else:
            print(f"{package_name}: {wheel_path}")


if __name__ == "__main__":
    main()
