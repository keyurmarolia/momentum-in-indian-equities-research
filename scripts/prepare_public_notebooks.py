"""Add static GitHub previews and resolve public notebook download links.

Only presentation outputs are changed; no research calculations are executed.
PNG generation requires the preview extra and a local Chrome installation.
"""

import base64
import hashlib
import json
import re
import shutil
from pathlib import Path

import nbformat
import plotly.io as pio

ROOT = Path(__file__).resolve().parents[1]
MIME = "application/vnd.plotly.v1+json"


def public_links(body):
    def replace(match):
        filename, label = match.groups()
        if filename.endswith("_all_return_layer_metrics.csv") or filename == "matched_strategy_comparison.csv":
            return f'<a href="../results/{filename}">{label}</a>'
        return f'<a href="../docs/data_access.md">{label} — included in the research data bundle</a>'

    return re.sub(r'<a href="\.\./reports/tables/([^"/]+)">(.*?)</a>', replace, body)


def main():
    results = ROOT / "results"
    results.mkdir(exist_ok=True)
    previews = 0
    for path in sorted((ROOT / "notebooks").glob("*.ipynb")):
        book = nbformat.read(path, as_version=4)
        for cell in book.cells:
            if cell.cell_type == "markdown":
                cell.source = cell.source.replace(
                    "Separate CSV files retain all scheduled portfolios, actual trades and risk layers for this exact signal/lookback/maintenance combination.",
                    "Risk metrics are included in the repository. Complete portfolio and trade CSVs belong to the local full-data research run.",
                )
            for output in cell.get("outputs", []):
                data = output.get("data", {})
                if "text/html" in data:
                    data["text/html"] = public_links(data["text/html"])
                    data["text/html"] = re.sub(
                        r"([^<>]+) \(available only with the local research datasets\)",
                        r'<a href="../docs/data_access.md">\1 — included in the research data bundle</a>',
                        data["text/html"],
                    )
                if MIME not in data:
                    continue
                figure = data[MIME]
                digest = hashlib.sha256(json.dumps(figure, sort_keys=True).encode()).hexdigest()
                if output.metadata.get("preview_sha256") != digest or "image/png" not in data:
                    png = pio.to_image(figure, format="png", scale=1.5)
                    data["image/png"] = base64.b64encode(png).decode()
                    output.metadata["preview_sha256"] = digest
                previews += 1
        nbformat.write(book, path)
        print(f"Prepared {path.name}", flush=True)
    for path in (ROOT / "reports/tables").glob("*_all_return_layer_metrics.csv"):
        shutil.copy2(path, results / path.name)
    matched = ROOT / "reports/tables/matched_strategy_comparison.csv"
    if matched.exists():
        shutil.copy2(matched, results / matched.name)
    print(f"Static previews: {previews}")


if __name__ == "__main__":
    main()
