"""Build exactly 23 chronological, strategy-specific notebooks."""

from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
BOOKS = ROOT / "notebooks"
LABELS = {
    "raw_momentum": "Raw Momentum",
    "vol_adjusted": "Volatility-Adjusted Momentum",
    "jensen_alpha": "Jensen Alpha Momentum",
    "jt_academic": "Jegadeesh–Titman Momentum",
    "km_momentum": "KM Momentum",
}
SIGNALS = {
    "raw_momentum": "Score = adjusted close at the signal date / adjusted close at the formation start − 1. The start is the last common market close on or before the literal calendar-month offset. The latest month is included. Highest scores enter first.",
    "vol_adjusted": "Score = formation-period price return / annualized sample standard deviation of daily log returns. Annualization uses √252. The signal rewards stronger returns per unit of realized variability; it does not set inverse-volatility portfolio weights.",
    "jensen_alpha": "Daily stock excess return = alpha + beta × daily Nifty 50 excess return + residual. Both excess returns subtract the continuous liquid-fund daily return. OLS alpha is the ranking score over the fixed formation window; this is a trailing signal, not the strategy's subsequently realized alpha.",
    "jt_academic": "Raw price momentum ranks winners and losers. N denotes total names: N/2 winners long and N/2 losers short, normally ±1/N per name. The scheduled gross budgets are 50% each. This fixed-breadth, non-overlapping academic reference is not a replication of the paper's decile/cohort construction.",
    "km_momentum": "Quality/liquidity universe → Close ≥ 1.03 × EMA(100) and bullish Supertrend(10,3) → raw-momentum ranking → highest N. There is no secondary proximity or risk ranking. A daily close below EMA(100), or a bearish Supertrend, triggers a sale at the next actual observed open. The proceeds earn the cash-sleeve return until the next scheduled rebalance.",
}
SETUP = """from pathlib import Path
import sys
ROOT = Path.cwd().resolve().parent if Path.cwd().name == 'notebooks' else Path.cwd().resolve()
sys.path.insert(0, str(ROOT / 'src'))
from momentum_india.notebook_views import ResearchNotebook
"""


def md(text):
    return nbf.v4.new_markdown_cell(text)


def code(text):
    cell = nbf.v4.new_code_cell(text)
    if text.startswith("from pathlib"):
        cell.metadata = {"tags": ["hide-input"], "jupyter": {"source_hidden": True}}
    return cell


def save(filename, cells):
    book = nbf.v4.new_notebook(
        cells=cells,
        metadata={
            "kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
            "language_info": {"name": "python", "version": "3.12"},
        },
    )
    nbf.write(book, BOOKS / filename)


def strategy_cells(strategy, formation, maintenance):
    label = LABELS[strategy]
    maint = "Equal Weight" if maintenance == "equal_weight" else "Winner Drift"
    cells = [
        md(
            f"# {label} — {formation} — {maint}\n\nOne signal, one formation horizon and one maintenance method. The experiment contains nine cells: rebalance every 1, 3 or 6 months × target N=12, 24 or 50."
        ),
        code(
            SETUP + f"\nresearch = ResearchNotebook('{strategy}', '{formation}', '{maintenance}')"
        ),
        md("## 1. Signal and portfolio rule\n\n" + SIGNALS[strategy]),
    ]
    if strategy == "km_momentum":
        cells.append(
            md(
                "### Technical definition\n\nEMA(100) begins at the mean of the first 100 observed closes and thereafter uses α=2/101. ATR(10) begins at the mean of the first ten true ranges having a prior close, then uses Wilder's α=1/10 smoothing. Supertrend bands are HL2 ± 3×ATR; the prior bands govern direction changes and the active band cannot retreat while direction is unchanged. Direction starts bullish at the first valid ATR bar. Missing observations do not create synthetic indicator bars.\n\nThese initialization rules make the calculation reproducible. They do not claim exact equality with an unidentified historical charting-package version. All indicators use split/bonus-adjusted OHLC. The 3% buffer applies only to entry; the EMA exit has no 3% buffer."
            )
        )
    if strategy == "jt_academic":
        cells.append(
            md(
                "At scheduled rebalances, equal weight resets each leg's selected names. Winner drift retains relative position weights inside each leg, caps absolute weights at 2/N, and restores up to 50% gross per leg through scaling or equal residual allocation. Between scheduled dates both legs drift with prices. Borrowing is an academic 3%, 6% or 12% annual deduction on short notional; margin, recalls and stock-level borrow availability are not modeled."
            )
        )
    elif maintenance == "equal_weight":
        cells.append(
            md(
                "Each selected stock targets 1/N of pre-trade equity at a scheduled rebalance. If K<N qualify, target cash is (N−K)/N before charges; eligible stocks are not enlarged to 1/K. Sales precede purchases, which are reduced proportionally if charges or unfilled sales restrict available cash. Actual weights can therefore differ slightly from targets. Membership is rebuilt from current ranks without a retention buffer."
            )
        )
    else:
        cells.append(
            md(
                "Continuing holdings retain their naturally drifted weights, capped at 2/N at scheduled rebalances. Exits and entrants are paired in stable symbol order; an entrant receives min(exit weight, 1/N). Excess exit weight and cap trims are spread equally among continuing holdings with room below the cap. Unmatched entrants share existing cash up to 1/N each. Residual cash is retained. The cap is a scheduled target constraint, not a daily trim rule."
            )
        )
    cells += [
        md(
            "## 2. Universe → ranking → actual portfolio\n\nThe example uses the latest monthly N=24 signal and exposes the ranking inputs and actual target weights."
        ),
        code("research.snapshot()"),
        md(
            "## 3. Return layers across all nine cells\n\nRaw is before trading charges. After-cost gross/pre-tax deducts modeled trading charges. The long-only post-tax overlay additionally applies the annual equity-gains ledger. The academic reference instead compares raw and borrowing-adjusted layers."
        ),
        code("research.layers_bridge()"),
        md(
            "## 4. Risk-adjusted results\n\nSharpe uses daily excess returns relative to the liquid fund. VaR and expected shortfall are historical monthly 95% loss measures. Partial first/last months are included. Time below prior peak counts days awaiting a new all-time high—not losing days. The initial invested capital is included as the first peak."
        ),
        code("research.risk_grid()"),
    ]
    for metric, title in [
        ("cagr", "CAGR"),
        ("sharpe", "Sharpe ratio"),
        ("maximum_drawdown", "Maximum drawdown"),
        ("monthly_var_95", "Monthly 95% VaR"),
    ]:
        cells += [md("### " + title), code(f"research.heatmap('{metric}')")]
    cells += [
        md(
            "## 5. Equity paths and matched risks\n\nEach chart fixes breadth and compares rebalance frequencies. Final-layer curves and the price benchmark start visible; other return layers remain in the selectable legend. Logarithmic axes make early and late periods comparable; the bottom range slider preserves the full history. Curves display weekly observations for readability, while every statistic uses the complete daily series."
        )
    ]
    for n in [12, 24, 50]:
        cells += [md(f"### N={n}"), code(f"research.equity({n})")]
    cells += [
        md(
            "## 6. Recovery burden\n\nThe longest underwater episode is shown by its peak, trough and recovery dates. Unrecovered episodes remain explicitly open."
        ),
        code("research.recovery()"),
        md(
            "## 7. Portfolio behavior\n\nScheduled turnover is (buy value + sell value)/(2 × pre-trade equity). Retention compares successive scheduled target name sets. Cash and total charges include the intervening daily path."
        ),
        code("research.behavior()"),
        md(
            "## 8. Market-state attribution\n\nThis is an observation, not an extra strategy filter. Prior-close Nifty 50 versus SMA(200) defines up/down; 63-session volatility versus its expanding historical median defines high/low volatility. The representative monthly N=24 path is shown with shaded states."
        ),
        code("research.regimes()"),
        md(
            "## 9. Complete portfolio and trade evidence\n\nSeparate CSV files retain all scheduled portfolios, actual trades and risk layers for this exact signal/lookback/maintenance combination."
        ),
        code("research.portfolio_exports()"),
        md("## Findings"),
        code("research.conclusion()"),
    ]
    if strategy not in ["raw_momentum", "jt_academic"]:
        idx = 2 + (2 if formation == "12M" else 0) + (1 if maintenance == "winner_drift" else 0)
        cells.append(
            md(
                f"Matched reference: [Raw Momentum — {formation} — {maint}]({idx:02d}_raw_momentum_{formation.lower()}_{maintenance}.ipynb). The comparison holds formation, maintenance, frequency and N fixed."
            )
        )
    return cells


def main():
    BOOKS.mkdir(exist_ok=True)
    save(
        "00_research_universe_and_data_quality.ipynb",
        [
            md(
                "# Research universe and data quality\n\nThe study asks whether relative past winners retain a return advantage across a fixed portfolio grid after modeled trading costs and an annual tax overlay."
            ),
            code(SETUP + "\nresearch = ResearchNotebook()"),
            md(
                "## Data and eligible securities\n\nThe source is observed main-board NSE EQ history, not a current-symbol-only watchlist. SME series are excluded; there is no independent market-cap or top-200 rule. Formation endpoints, 96.8% price coverage, at least 120 of 126 volume observations and a price-jump quality gate are required. Eligibility uses only information known at the signal close; missing next-session opens affect execution, not ranking."
            ),
            code("research.universe()"),
            md(
                "## Scope of evidence\n\nThere are 180 portfolio cells: five signals × two lookbacks × two maintenance methods × three frequencies × three breadths. Four signals are long-only, while Jegadeesh–Titman is an academic long-short reference. Each strategy gets four notebooks in chronological order.\n\nTrades require an actual observed opening price. A suspended position remains marked at its last observed close until it trades again; a confirmed delisting with no later exchange print is written down to zero. This conservative delisting rule is not a reconstruction of cash or merger consideration. Symbol reuse, unmodeled non-split corporate actions and historical non-EQ series remain limitations. The archive is broad but not certified free of every survivorship issue."
            ),
            md(
                "## Research sequence\n\nNotebook 01 defines costs and tax. Notebooks 02–21 fix each strategy's lookback and maintenance rule. Notebook 22 compares matched results and answers the research questions."
            ),
        ],
    )
    save(
        "01_trading_costs_and_tax_framework.ipynb",
        [
            md(
                "# Trading costs and tax framework\n\nThe cost bridge separates statutory turnover levies from brokerage and tax on realized gains."
            ),
            code(SETUP + "\nresearch = ResearchNotebook()"),
            md(
                "## Charges and dated tax inputs\n\nDelivery STT uses its historical effective-date schedule. Other charges use the stated 29 August 2026 FYERS schedule across the sample, with zero additional slippage. Historical service-tax/GST charts provide context and are not presented as historical fee replication."
            ),
            code("research.costs()"),
            md(
                "## Tax interpretation\n\nFIFO gains, deductible trade expenses excluding STT, dated listed-equity rates, annual gain/loss netting, eight-year loss carryforwards, exemptions, grandfathering and cess produce a research estimate. Each annual payment reduces the modeled capital; later realized gains are scaled to the capital remaining while fixed rupee exemptions remain fixed. Cash-sleeve realization tax, surcharge and investor-specific adjustments are excluded. Results are a portfolio-level tax overlay, not an investor tax return.\n\nRaw → after costs → post-tax comparisons in the strategy notebooks use these same assumptions."
            ),
        ],
    )
    number = 2
    for strategy in LABELS:
        for formation in ["6M", "12M"]:
            for maintenance in ["equal_weight", "winner_drift"]:
                save(
                    f"{number:02d}_{strategy}_{formation.lower()}_{maintenance}.ipynb",
                    strategy_cells(strategy, formation, maintenance),
                )
                number += 1
    save(
        "22_cross_strategy_findings.ipynb",
        [
            md(
                "# Cross-strategy findings\n\nThe comparisons hold the other design dimensions fixed and keep the academic long-short result separate from taxable long-only portfolios."
            ),
            code(SETUP + "\nresearch = ResearchNotebook()"),
            md(
                "## Questions answered\n\n- Does raw momentum remain positive after the modeled frictions?\n- Do volatility scaling and Jensen alpha improve matched raw-momentum outcomes?\n- Does KM's technical filter and exit-to-cash rule improve risk-adjusted returns?\n- How do six/twelve-month formation, rebalance speed and breadth change performance?\n- Does winner drift improve the equal-weight trade-off?\n- Does the academic winner-minus-loser portfolio remain positive after fixed borrowing deductions?"
            ),
            code("research.findings()"),
            md(
                "## Meaning of the evidence\n\nThe study compares signal behavior, portfolio construction and realized risk—not only terminal wealth. It does not identify a causal behavioral explanation, establish statistical significance across a searched grid or demonstrate out-of-sample persistence. Corporate-action coverage, suspended-position valuation, delisting recovery and tax-overlay assumptions remain part of every result."
            ),
        ],
    )
    print("Built 23 notebooks, numbered 00–22", flush=True)


if __name__ == "__main__":
    main()
