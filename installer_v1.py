import argparse
import json
import subprocess
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from packaging.tags import sys_tags
from packaging.utils import canonicalize_name, parse_wheel_filename


def collect_package_versions(tree: dict) -> Dict[str, str]:
    """Return a mapping of package name to resolved version from the dependency tree."""
    versions: Dict[str, str] = {}

    def walk(node: dict) -> None:
        if not isinstance(node, dict):
            return

        package_name = node.get("name")
        version = node.get("version")
        if isinstance(package_name, str) and package_name and isinstance(version, str):
            versions[package_name] = version

        dependencies = node.get("dependencies")
        if isinstance(dependencies, dict):
            for child in dependencies.values():
                walk(child)

    walk(tree)
    return versions


def build_install_order(tree: dict) -> List[str]:
    """Return package names in dependency-first order for installation."""
    indegree: Dict[str, int] = defaultdict(int)
    dependents: Dict[str, List[str]] = defaultdict(list)
    visited = set()

    def walk(node: dict) -> None:
        if not isinstance(node, dict):
            return

        package_name = node.get("name")
        if not isinstance(package_name, str) or not package_name:
            return

        if package_name in visited:
            return
        visited.add(package_name)

        dependencies = node.get("dependencies")
        if isinstance(dependencies, dict):
            for dependency_name in dependencies:
                dependents[dependency_name].append(package_name)
                indegree[package_name] += 1
                walk(dependencies[dependency_name])

    walk(tree)

    for package_name in visited:
        indegree.setdefault(package_name, 0)

    initial_queue: List[str] = []

    def gather_leaf_nodes(node: dict) -> None:
        if not isinstance(node, dict):
            return

        package_name = node.get("name")
        if not isinstance(package_name, str) or not package_name:
            return

        dependencies = node.get("dependencies")
        if isinstance(dependencies, dict):
            for dependency_name in dependencies:
                gather_leaf_nodes(dependencies[dependency_name])

        if not isinstance(dependencies, dict) or not dependencies:
            initial_queue.append(package_name)

    gather_leaf_nodes(tree)

    queue = deque(initial_queue)
    order: List[str] = []

    while queue:
        current = queue.popleft()
        if current in order:
            continue
        order.append(current)
        for dependent in sorted(dependents.get(current, [])):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                queue.append(dependent)

    return [name for name in order if name]


def select_wheel_for_environment(package_name: str, version: Optional[str], wheel_dir: Path, python_tag: Optional[str] = None, abi_tag: Optional[str] = None, platform_tag: Optional[str] = None) -> Optional[Path]:
    """Pick the best wheel file from a folder for the current platform and Python version."""
    safe_name = canonicalize_name(package_name)
    wheel_dir = Path(wheel_dir)
    if not wheel_dir.exists():
        return None

    version = version or ""
    supported_tags = set(sys_tags())

    candidates: List[Path] = []
    for wheel_path in sorted(wheel_dir.glob("*.whl")):
        try:
            parsed_name, parsed_version, _build_tag, tags = parse_wheel_filename(wheel_path.name)
        except Exception:
            continue

        if parsed_name != safe_name:
            continue
        if version and str(parsed_version) != version:
            continue

        if not tags:
            continue

        if supported_tags.intersection(tags):
            candidates.append(wheel_path)
            continue

        for tag in tags:
            if tag.interpreter.startswith("py") and tag.abi == "none" and tag.platform == "any":
                candidates.append(wheel_path)
                break

    if candidates:
        return candidates[0]

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
    install_order = build_install_order(tree)
    results: List[Tuple[str, Optional[Path]]] = []

    for package_name in install_order:
        node = None
        if package_name == tree.get("name"):
            node = tree
        else:
            stack = [tree]
            while stack:
                current = stack.pop()
                if current.get("name") == package_name:
                    node = current
                    break
                for child in current.get("dependencies", {}).values():
                    stack.append(child)

        if node is None:
            continue

        wheel_path = select_wheel_for_environment(package_name, node.get("version"), wheel_dir)
        results.append((package_name, wheel_path))
        if wheel_path is None:
            continue
        install_wheel(wheel_path, pip_executable=pip_executable)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Install Python wheels from a dependency tree in dependency-first order")
    parser.add_argument("dependency_tree", nargs="?", help="Path to a dependency tree JSON file")
    parser.add_argument("--wheel-dir", default="wheels", help="Directory containing wheel files")
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
    for package_name, wheel_path in install_dependency_tree(tree.get("tree", tree), wheel_dir):
        if wheel_path is None:
            print(f"{package_name}: no matching wheel found")
        else:
            print(f"{package_name}: {wheel_path}")


if __name__ == "__main__":
    main()
