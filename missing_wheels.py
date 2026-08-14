import argparse
import json
import subprocess
import sys
import platform
from pathlib import Path
from typing import List, Optional
from graphlib import TopologicalSorter

from packaging.tags import sys_tags, Tag
from packaging.utils import canonicalize_name, parse_wheel_filename


def select_wheel_for_environment(
    package_name: str,
    version: Optional[str],
    wheel_dir: Path,
    python_tag: Optional[str] = None,
    abi_tag: Optional[str] = None,
    platform_tag: Optional[str] = None,
    strict: bool = False
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
                if not strict and not is_wheel_compatible(wheel_tags=tags):
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


def find_missing_wheels(versions: dict, wheel_dir: Path, python_tag: str, abi_tag: str | None = None, platform_tag: str | None = None):
    missing_wheels = []
    for pkg, version in versions.items():
        wheel = select_wheel_for_environment(
            package_name=pkg,
            version=version,
            wheel_dir=wheel_dir,
            python_tag=python_tag,
            abi_tag=abi_tag,
            platform_tag=platform_tag,
            strict=True
        )
        if wheel is None:
            print(f"Error: No compatible wheel found for {pkg} ( {version} )")
            missing_wheels.append((pkg, version))
    return missing_wheels


def create_pypi_url(package_name: str, version: str | None = None):
    if not version:
        url_format = "https://pypi.org/project/{package_name}/#files"
        url = url_format.format(package_name=package_name)
    else:
        url_format = "https://pypi.org/project/{package_name}/{version}/#files"
        url = url_format.format(package_name=package_name, version=version)
    return url


def get_python_tag(python_tag: str | None):
    py_major, py_minor = sys.version_info[:2]
    if python_tag and '.' in python_tag:
        py_major, py_minor = python_tag.split('.')
    return f"cp{str(py_major)}{str(py_minor)}"


def get_platform_tag(platform_tag: str | None):
    arch = platform.machine()
    if platform_tag:
        if platform_tag == 'amd64' or platform_tag == 'x86_64':
            return 'x86_64', ['amd64', 'x86_64']
    platform_tags = [t.platform for t in sys_tags()]
    return arch, platform_tags


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

    versions = tree.get("versions", {})
    
    python_tag = get_python_tag(args.python_tag)
    # platform_tag = get_platform_tag(args.platform_tag)
    
    missing_wheels = find_missing_wheels(versions=versions, wheel_dir=wheel_dir, python_tag=python_tag, abi_tag=None, platform_tag=None)
    for pkg, version in missing_wheels:
        url = create_pypi_url(package_name=pkg, version=version)
        print(f"{pkg} {version} - {url}")


if __name__ == '__main__':
    main()