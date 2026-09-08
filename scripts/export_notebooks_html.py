"""Export existing executed notebooks without rerunning research."""

import nbformat
from execute_notebooks import OUT, ROOT, export


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for path in sorted((ROOT / "notebooks").glob("*.ipynb")):
        export(path, nbformat.read(path, as_version=4))
    print("Exported executed notebook HTML")


if __name__ == "__main__":
    main()
