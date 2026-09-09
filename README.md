# Momentum in Indian Equities

An NSE price-momentum study of portfolio construction, trading charges and risk.

## Run locally

Python 3.12 is the tested environment. From the cloned repository:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python scripts/setup_research.py
python scripts/serve_dashboard.py
```

On Windows, activation is `.venv\Scripts\activate` in Command Prompt. The setup command downloads a pinned, checksum-verified GitHub release containing the research datasets, saved results and prebuilt dashboard. No FYERS account or API key is required. Allow 8 GB of free disk space during extraction.

To read the interactive research notebooks without recalculating the study:

```sh
python scripts/export_notebooks_html.py
```

Open `reports/html/index.html` in a browser. GitHub notebook previews show static charts; local HTML retains the sliders, legends and metric selectors. Saved results are distinct from rerunning calculations.

```sh
python -m pytest -q
python scripts/setup_research.py --verify
python scripts/execute_notebooks.py
```

The last command recalculates all notebook views from the installed research datasets. [Data and reproduction](docs/data_access.md) describes the bundle and the full signal/backtest sequence.

## Experiment

Five strategies: Raw Momentum, Volatility-Adjusted Momentum, Jensen Alpha Momentum, Jegadeesh–Titman academic momentum and KM Momentum.

Each has six- and twelve-month formation periods, with equal-weight reset and winner drift. Each experiment contains nine cells: 12, 24 or 50 stocks × one-, three- or six-month rebalancing. There are 180 portfolio combinations.

The reference capital is INR 1 crore. Strategies rank the complete point-in-time quality universe; trailing median daily traded value is reported as a capacity diagnostic and does not remove securities. There is no top-200 or independent market-cap cutoff. One-shot research fills exclude staged execution, slippage and market impact.

## Notebook sequence

The executed Jupyter notebooks are the primary research record.

- 00: universe and data quality.
- 01: trading costs and tax.
- 02–05: Raw Momentum.
- 06–09: Volatility-Adjusted Momentum.
- 10–13: Jensen Alpha Momentum.
- 14–17: Jegadeesh–Titman academic momentum.
- 18–21: KM Momentum.
- 22: matched cross-strategy findings.

Every strategy notebook fixes its lookback and maintenance rule. Its nine-cell grid includes equity paths, comparable risks, heatmaps, complete portfolio exports and observations.

## Selected findings

Over the shared 2 July 2007–28 August 2026 window, KM Momentum produced the strongest median post-tax result across 36 cells: 13.2% CAGR and 0.46 Sharpe. Its highest-Sharpe cell used a six-month lookback, quarterly equal-weight reset and 24 stocks, with 19.7% CAGR, 0.84 Sharpe and a 30.1% maximum drawdown.

Volatility adjustment beat raw momentum's Sharpe in 94% of matched cells; KM did so in 75%. Jensen alpha did not improve average CAGR or Sharpe over raw momentum, despite slightly higher medians. The academic winner-minus-loser reference remained stronger under the fixed 6% borrowing assumption, but it is not treated as an executable delivery-equity strategy.

These are in-sample price-return results across a searched grid. They describe the evidence in this dataset rather than establish a causal behavioral mechanism or future performance.

## Interpretation

Long-only results separate raw returns, trading charges and a post-tax overlay. The academic reference instead compares borrowing assumptions and includes collateral/cash earnings.

Historical STT and equity-gains rules are dated. Other charges use a FYERS schedule dated 29 August 2026. The tax layer uses FIFO realizations and financial-year payments while leaving the underlying holdings path unchanged.

Historical traded symbols are retained, but the archive is not certified survivorship-bias-free. A suspended holding is marked at its last observed close and an order waits for its next actual observed open. A confirmed delisting with no later exchange print is written down to zero. Merger consideration and other terminal recoveries are not reconstructed. These limitations constrain claims of investability.

Regimes describe outcomes and never alter positions. In-sample comparisons do not establish a behavioral cause or out-of-sample persistence.

## Research dashboard

The local [dashboard](dashboard/README.md) browses all 180 experiments, scheduled portfolios, stock histories, holding episodes and risk statistics from saved results. [Open Research Dashboard.command](Open%20Research%20Dashboard.command) launches the local browser view. Dashboard use makes no broker requests.

Market histories and portfolio datasets are distributed as a versioned release asset, not Git source files. The executed notebooks retain the research narrative, static previews and interactive figure data.

## Research components

[Methodology](docs/methodology.md), [portfolio construction](docs/portfolio_construction.md), [data coverage](docs/data_status.md), [cost and tax rules](docs/tax_rule_audit.md), and [relationship to the 1993 paper](docs/jegadeesh_titman_1993_bridge.md).

[Validation and limitations](docs/research_validation.md) separates verified accounting identities from unresolved source-data and execution assumptions.

## Related projects

[Credit scorecard](https://github.com/keyurmarolia/credit-scorecard-pd-model) · [IFRS 9 ECL](https://github.com/keyurmarolia/ifrs9-mortgage-ecl) · [Basel capital](https://github.com/keyurmarolia/basel-credit-capital-engine) · [FRTB](https://github.com/keyurmarolia/frtb-market-risk-engine) · [IndiGo research](https://github.com/keyurmarolia/indigo-equity-research)
