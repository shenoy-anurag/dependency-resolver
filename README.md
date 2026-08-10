# Dependency Resolver

This repository helps collect Python package dependencies from PyPI, download wheel files, and install them in the correct dependency-first order for air-gapped or offline environments.

## Scripts

### `remote_dep_resolver.py`

Use this script to resolve a package dependency tree from PyPI and export a JSON package manifest.

Example:

```bash
python remote_dep_resolver.py fastapi 0.124.0 --max-depth 3
```

This prints a dependency tree and creates an export file like:

```text
output/dependency_tree_fastapi==0.124.0.json
```

The export contains:

- `tree`: nested dependency tree nodes
- `adjacency_list`: package -> dependency list
- `versions`: package -> selected version
- `wheel_urls`: package -> candidate wheel download URLs

### `wheel_downloader.py`

Use this script to download wheels from the exported dependency tree JSON.

Example:

```bash
python wheel_downloader.py output/dependency_tree_fastapi==0.124.0.json --wheel-dir wheels
```

This writes wheel files into `wheels/` for each package listed in `versions`.

### `installer_final.py`

Use this script to install wheels from a dependency tree in dependency-first order.

Example:

```bash
python installer_final.py output/dependency_tree_fastapi==0.124.0.json --wheels wheels --python-tag cp313
```

The script reads the tree export, computes a topological install order, selects compatible wheels from the wheel directory, and installs them with `pip --no-index`.

### `sorter.py`

This helper demonstrates the core ordering algorithm:

- the dependency graph is represented as an adjacency list
- `graphlib.TopologicalSorter` produces an order where dependencies appear before dependents

It is useful for understanding and validating the install order calculation.

## Dependency tree format

The dependency export uses two important structures:

- `adjacency_list`: a map from package name to a list of its direct dependencies
- `versions`: a map from package name to the resolved version string

Example adjacency list:

```json
{
  "fastapi": ["starlette", "pydantic", "typing-extensions", "annotated-doc"],
  "starlette": ["anyio", "typing-extensions"],
  "anyio": ["exceptiongroup", "idna", "typing-extensions"],
  "typing-extensions": [],
  "idna": []
}
```

Example versions:

```json
{
  "fastapi": "0.124.0",
  "starlette": "5.23.3",
  "anyio": "1.3.4",
  "typing-extensions": "44.24.2",
  "idna": "0.8.1"
}
```

## Basic idea

1. Resolve the package tree from PyPI and note every dependency relationship.
2. Represent the dependency tree as an adjacency list plus package version numbers.
3. Topologically sort the adjacency list so that every dependency is installed before packages that require it.
4. Download the wheel files for each package version.
5. In an air-gapped environment, copy the wheel files to the offline machine and install them in the sorted order with `pip --no-index`.

This approach ensures wheel installation succeeds even when network access is unavailable, because dependencies are installed first and version requirements are tracked explicitly.
