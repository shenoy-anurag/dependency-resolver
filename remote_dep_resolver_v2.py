import argparse
import json

import requests
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def fetch_pypi_metadata(package_name, version=None):
    """Fetch metadata for a package from the PyPI JSON API."""
    safe_name = canonicalize_name(package_name)
    url = f"https://pypi.org/pypi/{safe_name}/json"
    if version:
        url = f"https://pypi.org/pypi/{safe_name}/{version}/json"

    try:
        response = requests.get(url, timeout=10)
        if hasattr(response, "raise_for_status"):
            response.raise_for_status()
        if response.status_code != 200:
            return None, []
        data = response.json()
    except Exception:
        return None, []

    info = data.get("info", {})
    actual_version = version or info.get("version")
    releases = data.get("releases", {}) or {}
    release_info = releases.get(actual_version, {}) if isinstance(releases, dict) else {}

    if not isinstance(release_info, dict):
        release_info = {}

    requires_dist = (
        info.get("requires_dist")
        or info.get("requires_distribution")
        or release_info.get("requires_dist")
        or release_info.get("requires_distribution")
        or []
    )

    return actual_version, requires_dist


def build_dependency_tree(package_name, version=None, max_depth=None, path=None):
    """Recursively build a nested dependency tree for a Python package."""
    safe_name = canonicalize_name(package_name)
    if path is None:
        path = []

    actual_version, requires_dist = fetch_pypi_metadata(safe_name, version)
    if not actual_version:
        return {"name": safe_name, "version": "unknown", "dependencies": {}}

    if safe_name in path:
        return {"name": safe_name, "version": actual_version, "dependencies": "Circular Dependency Detected"}

    node = {"name": safe_name, "version": actual_version, "dependencies": {}}

    if max_depth is not None and len(path) >= max_depth:
        return node

    current_path = [*path, safe_name]
    for requirement_string in requires_dist:
        try:
            requirement = Requirement(requirement_string)
        except Exception:
            continue

        if requirement.marker and "extra ==" in str(requirement.marker):
            continue

        dependency_name = canonicalize_name(requirement.name)
        node["dependencies"][dependency_name] = build_dependency_tree(
            dependency_name,
            max_depth=max_depth,
            path=current_path,
        )

    return node


def collect_wheel_download_urls(package_name, version=None):
    """Collect wheel download URLs for a package version from PyPI."""
    safe_name = canonicalize_name(package_name)
    url = f"https://pypi.org/pypi/{safe_name}/{version}/json" if version else f"https://pypi.org/pypi/{safe_name}/json"

    try:
        response = requests.get(url, timeout=10)
        if hasattr(response, "raise_for_status"):
            response.raise_for_status()
        if response.status_code != 200:
            return set()
        data = response.json()
    except Exception:
        return set()

    urls = data.get("urls", []) or []
    return {
        item["url"]
        for item in urls
        if item.get("packagetype") == "bdist_wheel" and item.get("url")
    }


def build_adjacency_list(tree):
    """Convert a dependency tree into an adjacency list for topological sorting."""
    adjacency = {}

    def walk(node, parent_name=None):
        node_name = node.get("name")
        if node_name is None:
            return

        adjacency[node_name] = []
        if isinstance(node.get("dependencies"), dict):
            for dependency_name, dependency_node in node["dependencies"].items():
                adjacency[node_name].append(dependency_name)
                walk(dependency_node, node_name)

    walk(tree)
    return adjacency


def main():
    parser = argparse.ArgumentParser(description="Resolve a remote Python dependency tree from PyPI")
    parser.add_argument("package", nargs="?", default="paddlepaddle", help="Package name to resolve")
    parser.add_argument("version", nargs="?", default=None, help="Optional version to resolve")
    parser.add_argument("--max-depth", type=int, default=None, help="Limit recursion depth")
    args = parser.parse_args()

    print(f"Resolving dependency tree for {args.package}...\n")
    tree = build_dependency_tree(args.package, version=args.version, max_depth=args.max_depth)
    wheel_urls = collect_wheel_download_urls(args.package, args.version)
    adjacency_list = build_adjacency_list(tree)

    export = {
        "package": args.package,
        "version": args.version,
        "max_depth": args.max_depth,
        "tree": tree,
        "wheel_urls": sorted(wheel_urls),
        "adjacency_list": adjacency_list,
    }

    print(json.dumps(export, indent=2))
    with open("dependency_tree_{}.json".format(args.package + "==" + str(args.version)), "w", encoding="utf-8") as handle:
        json.dump(export, handle, indent=2)


if __name__ == "__main__":
    main()
