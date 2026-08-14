import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Optional
from graphlib import TopologicalSorter

from packaging.tags import sys_tags, Tag
from packaging.utils import canonicalize_name, parse_wheel_filename


def create_pypi_url(package_name: str, version: str | None = None):
    if not version:
        url_format = "https://pypi.org/project/{package_name}/#files"
        url = url_format.format(package_name=package_name)
    else:
        url_format = "https://pypi.org/project/{package_name}/{version}/#files"
        url = url_format.format(package_name=package_name, version=version)
    return url



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
    
    