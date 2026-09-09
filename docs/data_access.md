# Data and reproduction

## Pinned research snapshot

`config/research_bundle.json` records the release URL, archive size and SHA-256 checksum, plus each file's checksum. `python scripts/setup_research.py` downloads that exact snapshot without contacting a broker or exchange. Existing different files are preserved and reported, not overwritten.

The bundle contains the saved market panel, cash NAV, benchmark, rankings, targets, trading and tax ledgers, notebook CSV exports, source archives and the prebuilt stock-level dashboard. Research dates end on 28 August 2026. Credentials and the Python/Node environments are not included.

Complete portfolio and trade CSVs are under `reports/tables` after setup. Summary metrics are also available in the repository's `results` folder. The dataset retains the corporate-action, symbol-history and execution limitations described in [research validation](research_validation.md).

## Three reproducibility levels

- **Read the evidence:** GitHub displays saved tables and static chart previews. Exporting the notebooks to HTML restores interactive charts without accessing market inputs.
- **Recalculate notebook views:** install the bundle, then run `python scripts/execute_notebooks.py`. This recomputes the presentation and comparisons from the saved ledgers, not the trades themselves.
- **Recalculate signals and trades:** after setup, run the sequence below. This is a longer, memory-intensive calculation over the full historical universe, not a dashboard startup requirement. It replaces generated results in the working copy.

```sh
python scripts/build_signal_targets.py
python scripts/run_backtests.py
python scripts/build_post_tax_returns.py
python scripts/build_notebook_diagnostics.py
python scripts/execute_notebooks.py
python scripts/audit_signal_integrity.py
python scripts/validate_project.py
python scripts/build_dashboard_data.py
python scripts/validate_dashboard.py
```

The adjusted input panel is included, so this sequence makes no download requests. Source-acquisition scripts are separate and are not run by setup, tests or dashboard startup. Recomputed floating-point results may differ slightly with dependency/platform versions; the pinned saved results remain the reference snapshot.

## Dashboard development

The release includes a ready-to-serve build; Node is unnecessary for viewing it. To change the interface, use Node 22.13 or later and pnpm 10:

```sh
cd dashboard
pnpm install --frozen-lockfile
pnpm test
pnpm check
pnpm build
```

The setup command installs the public data and Plotly asset consumed by the build. Building the interface does not run a backtest or request broker data.

## Static preview maintenance

After changing and executing notebooks, `python scripts/prepare_public_notebooks.py` refreshes static previews and public download links. This step needs `pip install -e ".[dev,preview]"` and a local Chrome installation; neither is required just to read existing previews.
