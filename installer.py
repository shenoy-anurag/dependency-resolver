import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Optional
from graphlib import TopologicalSorter

from packaging.tags import sys_tags, Tag
from packaging.utils import canonicalize_name, parse_wheel_filename


def get_install_order(adjacency_list: dict) -> list[str]:
    # Python's TopologicalSorter expects key -> set of dependencies
    # graph = { package: set(dependencies) }
    graph = {pkg: set(deps) for pkg, deps in adjacency_list.items()}

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
        if version and version != "unknown":
            if str(parsed_version) != version:
                if not is_wheel_compatible(wheel_tags=tags):
                    continue
                fallback_candidates.append(wheel_path)
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


def is_wheel_compatible(wheel_tags: frozenset[Tag]) -> bool:
    """Determines whether a wheel is compatible with the current interpreter.

    Args:
        wheel_tags (frozenset[Tag]): Wheel tags

    Returns:
        bool: Is Wheel Compatible with current interpreter.
        
    Rules:
    - Exact CP match allowed (cp312)
    - Upward compatible: abi3 wheels (e.g. cp37-abi3) work on >= their build version
    - py3 / py2.py3 compatible wheels allowed
    - none-any always compatible
    - If wheel specifies "none" tag for interpreter or abi, it is universal
    """
    current_tags = {str(t) for t in sys_tags()}
    
    if any(str(t) in current_tags for t in wheel_tags):
        return True
    
    wheel_tags_strs = [str(t) for t in wheel_tags]
    
    if any(t.endswith("none-any") for t in wheel_tags_strs):
        return True

    if any(t.startswith("py3-") or t.startswith("py2.py3-") for t in wheel_tags_strs):
        return True
    
    py_major, py_minor = sys.version_info[:2]
    for t in wheel_tags_strs:
        if t.startswith("cp") and "-abi3-" in t:
            try:
                wheel_cp = int(t[2:4])
                if py_major == 3 and py_minor >= wheel_cp:
                    return True
            except ValueError:
                pass
            
    for t in wheel_tags_strs:
        if t.startswith("cp") and t.endswith("+"):
            try:
                min_cp = int(t[2:-1])
                cur_cp = py_major * 100 + py_minor
                if cur_cp >= min_cp:
                    return True
            except ValueError:
                pass
    
    return False


def install_wheel(wheel_path: Path, pip_executable: Optional[str] = None) -> subprocess.CompletedProcess:
    """Install a wheel using pip."""
    executable = pip_executable or [sys.executable, "-m", "pip"]
    if isinstance(executable, str):
        cmd = [executable, "install", str(wheel_path), "--no-index"]
    else:
        cmd = [*executable, "install", str(wheel_path), "--no-index"]
    return subprocess.run(cmd, check=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Install Python wheels from a dependency tree in dependency-first order")
    parser.add_argument("dependency_tree", nargs="?",
                        help="Path to a dependency tree JSON file")
    parser.add_argument("--wheels", default="wheels",
                        help="Directory containing wheel files")
    parser.add_argument(
        "--python", "--python-tag",
        dest="python_tag",
        default=None,
        help="Python tag to select compatible wheels, e.g. cp313",
    )
    parser.add_argument("--abi-tag", default=None,
                        help="ABI tag to select compatible wheels")
    parser.add_argument("--platform-tag", default=None,
                        help="Platform tag to select compatible wheels")
    args = parser.parse_args()

    if not args.dependency_tree:
        parser.error("Please provide a dependency tree JSON file")

    tree_path = Path(args.dependency_tree)
    if not tree_path.exists():
        parser.error(f"Dependency tree file not found: {tree_path}")

    with tree_path.open("r", encoding="utf-8") as handle:
        tree = json.load(handle)

    wheel_dir = Path(args.wheels)

    adjacency_list = tree.get("adjacency_list", {})
    versions = tree.get("versions", {})

    install_order = get_install_order(adjacency_list)

    for pkg in install_order:
        version = versions.get(pkg)
        wheel = select_wheel_for_environment(
            package_name=pkg, version=version,
            wheel_dir=wheel_dir, python_tag=args.python_tag,
            platform_tag=args.platform_tag
        )
        
        if wheel is None:
            print(f"No compatible wheel found for {pkg} (version {version})")
            sys.exit(1)

        result = install_wheel(wheel_path=wheel)
        if result.returncode != 0:
            print(f"Failed to install wheel: {wheel}")
            sys.exit(result.returncode)


if __name__ == "__main__":
    main()
