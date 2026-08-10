import json
from graphlib import TopologicalSorter

raw_data = """{
"versions": {
    "fastapi": "0.124.0",
    "starlette": "5.23.3",
    "anyio": "1.3.4",
    "exceptiongroup": "19.2.3",
    "typing-extensions": "44.24.2",
    "idna": "0.8.1",
    "pydantic": "4.23.3",
    "annotated-types": "2.41.2",
    "pydantic-core": "0.4.2",
    "typing-inspection": "0.3.1"
},
 "adjacency_list": {
    "fastapi": [
      "starlette",
      "pydantic",
      "typing-extensions",
      "annotated-doc"
    ],
    "starlette": [
      "anyio",
      "typing-extensions"
    ],
    "anyio": [
      "exceptiongroup",
      "idna",
      "typing-extensions"
    ],
    "exceptiongroup": [
      "typing-extensions"
    ],
    "typing-extensions": [],
    "idna": [],
    "pydantic": [
      "annotated-types",
      "pydantic-core",
      "typing-extensions",
      "typing-inspection"
    ],
    "annotated-types": [],
    "pydantic-core": [
      "typing-extensions"
    ],
    "typing-inspection": [
      "typing-extensions"
    ],
    "annotated-doc": []
  }
}"""


def get_install_order(data: dict) -> list[str]:
    adj_list = data.get("adjacency_list", {})

    # Python's TopologicalSorter expects key -> set of dependencies
    # graph = { package: set(dependencies) }
    graph = {pkg: set(deps) for pkg, deps in adj_list.items()}

    ts = TopologicalSorter(graph)
    # prepare() + static_order() returns nodes where dependencies come before dependents
    return list(ts.static_order())


data = json.loads(raw_data)
install_order = get_install_order(data)

print(install_order)
