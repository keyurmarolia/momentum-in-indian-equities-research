"""Export existing executed notebooks without rerunning research."""

import nbformat

if __package__:
    from .execute_notebooks import OUT, ROOT, export, export_index
else:
    from execute_notebooks import OUT, ROOT, export, export_index


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for path in sorted((ROOT / "notebooks").glob("*.ipynb")):
        export(path, nbformat.read(path, as_version=4))
    export_index()
    print("Exported executed notebook HTML")


if __name__ == "__main__":
    main()
