"""Execute research notebooks and export self-contained, widget-free HTML."""

import html
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

import nbformat
import plotly.io as pio
from jupyter_client import KernelManager
from nbclient import NotebookClient
from nbconvert import HTMLExporter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "html"


def export(path, book):
    book = deepcopy(book)
    first = True
    for cell in book.cells:
        if "hide-input" in cell.get("metadata", {}).get("tags", []):
            cell.source = ""
        for output in cell.get("outputs", []):
            figure = output.get("data", {}).get("application/vnd.plotly.v1+json")
            if figure:
                output.data = {
                    "text/html": pio.to_html(
                        figure,
                        full_html=False,
                        include_plotlyjs=first,
                        config={"responsive": False, "scrollZoom": True, "displaylogo": False},
                    )
                }
                first = False
    exporter = HTMLExporter()
    exporter.exclude_input = True
    exporter.mathjax_url = ""
    body, _ = exporter.from_notebook_node(book)
    body = body.replace("../reports/tables/", "../tables/")
    body = body.replace('href="../results/', 'href="../../results/')
    body = body.replace('href="../docs/', 'href="../../docs/')
    body = re.sub(r'(href="[^"]+)\.ipynb(")', r"\1.html\2", body)
    (OUT / (path.stem + ".html")).write_text(body)


def export_index():
    books = sorted((ROOT / "notebooks").glob("*.ipynb"))
    links = "".join(
        f'<li><a href="{p.stem}.html">{html.escape(nbformat.read(p, as_version=4).cells[0].source.splitlines()[0].lstrip("# "))}</a></li>'
        for p in books
    )
    (OUT / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Momentum in Indian Equities</title>'
        '<style>body{font:18px system-ui;max-width:950px;margin:50px auto;padding:20px}li{margin:12px}</style>'
        '<h1>Momentum in Indian Equities</h1><p>Saved research results. Interactive charts are restored from executed notebook outputs; this view does not rerun the backtests.</p>'
        '<ol start="0">' + links + '</ol>'
    )


def run(path):
    book = nbformat.read(path, as_version=4)
    manager = KernelManager(kernel_name="python3")
    manager.kernel_spec.argv[0] = sys.executable
    client = NotebookClient(
        book, timeout=900, km=manager, resources={"metadata": {"path": str(ROOT / "notebooks")}}
    )
    try:
        client.execute()
        nbformat.write(book, path)
        export(path, book)
        print("Executed and exported: " + path.name, flush=True)
    finally:
        if manager.has_kernel:
            manager.shutdown_kernel(now=True)
    return path


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    books = sorted((ROOT / "notebooks").glob(sys.argv[1] if len(sys.argv) > 1 else "*.ipynb"))
    if len(sys.argv) > 2:
        books = [p for p in books if int(p.name[:2]) >= int(sys.argv[2])]
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, books))
    export_index()


if __name__ == "__main__":
    main()
