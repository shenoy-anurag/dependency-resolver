import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import unquote, urlparse

import requests
from packaging.tags import sys_tags
from packaging.utils import canonicalize_name, parse_wheel_filename


def build_download_plan(tree: dict) -> List[Tuple[str, str, List[str]]]:
    """Build a package/version/wheel-url plan from a dependency tree export."""
    versions = tree.get("versions", {}) or {}
    wheel_urls = tree.get("wheel_urls", {}) or {}

    plan: List[Tuple[str, str, List[str]]] = []
    for package_name, version in versions.items():
        candidates = wheel_urls.get(package_name, []) or []
        if isinstance(candidates, str):
            candidates = [candidates]
        plan.append((str(package_name), str(version), [str(url) for url in candidates]))

    return plan


def select_best_wheel_url(
    package_name: str,
    version: Optional[str],
    candidates: List[str],
    python_tag: Optional[str] = None,
    abi_tag: Optional[str] = None,
    platform_tag: Optional[str] = None,
) -> Optional[str]:
    """Choose the best wheel URL for the current Python and platform tags."""
    if not candidates:
        return None

    safe_name = canonicalize_name(package_name)
    version = version or ""
    python_tag = python_tag or f"py{sys.version_info.major}{sys.version_info.minor}"
    abi_tag = abi_tag or "none"
    platform_tag = platform_tag or "any"
    supported_tags = set(sys_tags())

    exact_candidates: List[str] = []
    fallback_candidates: List[str] = []

    for candidate in candidates:
        wheel_name = Path(unquote(urlparse(candidate).path)).name
        try:
            parsed_name, parsed_version, _build_tag, tags = parse_wheel_filename(wheel_name)
        except Exception:
            continue

        if parsed_name != safe_name:
            continue
        if version and str(parsed_version) != version:
            continue
        if not tags:
            continue

        tag_matches = any(
            tag.interpreter == python_tag and tag.abi == abi_tag and tag.platform == platform_tag
            for tag in tags
        )
        if tag_matches:
            exact_candidates.append(candidate)
            continue

        if supported_tags.intersection(tags):
            fallback_candidates.append(candidate)
            continue

        if any(
            tag.interpreter.startswith("py") and tag.abi == "none" and tag.platform == "any"
            for tag in tags
        ):
            fallback_candidates.append(candidate)

    if exact_candidates:
        return exact_candidates[0]
    if fallback_candidates:
        return fallback_candidates[0]
    return candidates[0]


def download_wheel(url: str, wheel_dir: Path) -> Optional[Path]:
    """Download a single wheel URL into the target directory."""
    wheel_dir.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    wheel_name = Path(unquote(urlparse(url).path)).name
    if not wheel_name:
        return None

    destination = wheel_dir / wheel_name
    with destination.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                handle.write(chunk)
    return destination


def download_wheels_from_tree(tree: dict, wheel_dir: Path) -> List[Tuple[str, Optional[Path]]]:
    """Download wheels listed in a dependency-tree export into the target folder."""
    results: List[Tuple[str, Optional[Path]]] = []
    for package_name, version, urls in build_download_plan(tree):
        selected_url = select_best_wheel_url(package_name, version, urls)
        if not selected_url:
            results.append((package_name, None))
            continue

        wheel_path = download_wheel(selected_url, wheel_dir)
        results.append((package_name, wheel_path))

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Python wheels for a dependency-tree export")
    parser.add_argument("dependency_tree", nargs="?", help="Path to a dependency tree JSON file")
    parser.add_argument("--wheel-dir", default="wheels", help="Directory to store downloaded wheels")
    args = parser.parse_args()

    if not args.dependency_tree:
        parser.error("Please provide a dependency tree JSON file")

    tree_path = Path(args.dependency_tree)
    if not tree_path.exists():
        parser.error(f"Dependency tree file not found: {tree_path}")

    with tree_path.open("r", encoding="utf-8") as handle:
        tree = json.load(handle)

    wheel_dir = Path(args.wheel_dir)
    wheel_dir.mkdir(parents=True, exist_ok=True)

    for package_name, wheel_path in download_wheels_from_tree(tree, wheel_dir):
        if wheel_path is None:
            print(f"{package_name}: no matching wheel found")
        else:
            print(f"{package_name}: {wheel_path}")


if __name__ == "__main__":
    main()
