# Research validation

## Scope

The review covers signal timing, portfolio selection, execution accounting, tax calculations, data provenance, notebook interpretation and dashboard reconciliation. Passing these checks establishes consistency within the stated research model; it does not certify every historical exchange record or make the model an executable trading system.

## Corrected discrepancies

1. **Future opening availability affected selection.** The universe no longer excludes a stock because tomorrow's open is missing. The execution engine handles unavailable quotes. The corrected rankings contain 565 such security/date/lookback observations.
2. **Grandfathering affected short-term sales.** It now applies only to qualifying long-term disposals from 1 April 2018 of shares acquired by 31 January 2018.
3. **Grandfathering used the closing price.** Fair market value now uses the adjusted high on 31 January 2018, or the last preceding traded date.
4. **Exempt gains and losses entered taxable loss netting.** Section 10(38) disposals no longer consume taxable losses or create carry-forwards.
5. **Delisting marks created unsupported tax deductions.** A zero-recovery valuation mark does not automatically qualify as a realized tax loss. Inventory removal and tax eligibility are separated.
6. **Cash-reference calendars differed.** Notebook and dashboard reference returns now accumulate weekend/holiday NAV growth between market sessions, consistent with the backtest's convention.
7. **Cash initialization could use a future NAV.** Backfilling was removed; missing initial cash history raises an error.
8. **Frequency comparisons had different starting dates.** Notebook 22 measures every configuration over the common 2 July 2007–28 August 2026 window. Strategy notebooks preserve their full histories.
9. **Weekly chart points could be dated after the last observation.** Chart downsampling now retains actual observation dates instead of assigning artificial Friday dates.
10. **Target counts were labelled actual holdings.** Portfolio-count diagnostics now use actual positions, including holdings awaiting executable exits.
11. **Empty portfolios were skipped in churn calculations.** Scheduled empty snapshots now participate in membership transitions.
12. **Weight descriptions overstated exact post-cost equality.** Targets are based on pre-trade equity; sales precede cash-constrained purchases. Actual weights reflect fees and unfilled orders.
13. **Raw high/low provenance was overwritten.** Original values are preserved before the two analytical OHLC-envelope repairs. Analytical OHLC remained unchanged.
14. **Turnover fallback mixed adjusted prices with unadjusted volume.** It now uses raw close times volume. No current observations require that fallback, so current signal values are unaffected.
15. **Configuration implied unused rules.** Obsolete fixed-252-day alpha settings and history thresholds were removed; cash-sleeve tax exclusion and fixed-N academic selection are explicit. Unused alternative universe and tax-lot helpers were removed.
16. **Summary claims and output counts were stale.** Findings are calculated from refreshed results. Median and mean outcomes are distinguished; Jensen alpha is not described as improving average results when it does not.
17. **Final comparisons were fragmented.** Three figures expose all 180 configurations: return, risk and risk-adjusted return. Metric selectors cover CAGR, drawdowns, volatility, monthly VaR, underwater time, Sharpe and Calmar. A machine-readable table preserves exact values.
18. **A chart selector overlapped its title.** The comparison controls were moved clear of titles during visual inspection.
19. **A missing weekday NAV exposed inconsistent as-of alignment.** On 29 September 2025, a previous-market-session fill discarded a newer weekend NAV. One shared latest-known-NAV rule now governs cash accounting, references and validation; the independent signal check uses a separate as-of calculation.

## Remaining data uncertainties

- **Security identity:** the archive uses traded NSE EQ symbols, not a fully reconstructed permanent issuer identifier. Symbol changes, reuse and historical non-EQ series can split or obscure histories.
- **Corporate actions:** splits, bonuses and consolidations are adjusted; dividends, rights subscriptions, demerger entitlements and merger consideration are not fully reconstructed. This is a price-return study, not a total-shareholder-return study.
- **Four action exceptions:** DVL (5 August 2021), JINDALSTEL (21 January 2008), KWALITY (15 June 2010), and LAKSHVILAS (17 November 2006) fall outside the 25% price-ratio reconciliation tolerance. A price-ratio exception is a flag, not proof the action factor is wrong; genuine market moves can contribute. The supplied factors are retained, not guessed away.
- **Suspensions:** last observed prices mark unavailable holdings. This can suppress measured volatility and defer recognized losses.
- **Delistings:** zero recovery is a modeled outcome, not an observed exit price. It may understate long-position proceeds and overstate academic short profits. Fifty-six symbols have terminal marks somewhere in the tested paths; underlying legal consideration is not certified.
- **Historical investability:** EQ trading observations do not establish unrestricted market access, short availability, circuit-limit fills or absence of survivorship bias.

## Research assumptions, not execution claims

- All available quality-eligible stocks can enter ranks. INR 1 crore and 5% MDTV participation are capacity diagnostics, not enforced liquidity limits. A portfolio can select a security that fails the capacity reference.
- Fractional adjusted shares, opening-price fills and immediate reinvestment are used. Bid/ask spreads, market impact, auction access, settlement delays and whole-share rounding are excluded.
- An unavailable quote delays execution until an actual open is observed. This is not proof that a real order would fill there. Stops are daily-close rules, not guaranteed loss limits; overnight gaps remain possible.
- The corrected after-cost ledger contains 14 delayed scheduled buy fills, including eight KM fills. These are pending rebalance orders, not fresh stop replacements. There are 48 selected-position snapshots above their fee-adjusted target caps; every one lacks an executable opening quote. The model does not pretend that an unavailable holding can be trimmed.
- Winner drift's 2/N cap applies to scheduled target weights. Price movements, fees and locked positions can move actual weights beyond it. Stable-symbol entrant/exit pairing is a design convention, not an optimized allocation.
- Non-STT fees use the 29 August 2026 FYERS schedule throughout history. Historical brokerage and service-tax regimes are not reconstructed in execution costs.
- The tax layer rescales financial-year realizations after prior payments without rerunning holdings or fixed order costs. Separate bonus-share allotment dates and tax bases, merger tax bases, surcharge, taxpayer-specific exemptions and cash-sleeve realization tax are excluded. It is not an investor tax return.
- The liquid-fund NAV is a cash/reference proxy with credit and liquidity risk, not a truly risk-free yield. Regular and direct plans are linked without modeling investor-specific switching taxes.
- The academic portfolio has 50% scheduled gross per leg and includes earnings on cash/short proceeds. Borrow fees use a fixed annual rate on closing short notional over elapsed calendar days, an approximation around entry and exit dates. Margins, recalls, borrow availability, tax and delivery fees are excluded. Its absolute return is not pure winner-minus-loser alpha.
- The 1993 comparison is conceptual: this project uses fixed-N portfolios and non-overlapping scheduled rebalances rather than reproducing the paper's complete decile/overlapping-holding design.
- CAGR uses elapsed calendar years; Sharpe uses daily excess returns with 252-session annualization. Monthly VaR/ES include partial boundary months. Underwater time measures sessions below a previous wealth peak, not negative-return days. An average Sharpe across configurations is not a combined portfolio's Sharpe.
- The parameter grid is in-sample. No holdout, multiple-testing correction, causal behavioral proof or guaranteed ranking persistence is claimed.

## Validation evidence

- All 522,101 saved raw-momentum scores reconcile to their formation endpoints.
- All 20,880 scheduled memberships reconcile to their ranking, technical-filter and concentration rules.
- Sixty deterministic samples independently reconcile volatility scores and OLS alpha using a separate least-squares calculation.
- Unit tests cover EMA/ATR/Supertrend causality, missing bars, stops, fees, FIFO, tax transitions, drawdown definitions and comparison alignment.
- All 67 Python tests pass, including archive-checksum, extraction-safety and notebook-preview checks. A fresh Python environment installs successfully with no dependency conflicts. Five frontend tests, TypeScript checks and the production build also pass.
- The pinned bundle installs into a clean clone and all 11,828 files pass checksum verification. All 23 notebooks execute there, and the installed dashboard serves the full 180-experiment manifest and chart assets. This verifies notebook and dashboard reproduction from the saved input snapshot; it is not an independent certification of exchange records.
- All 23 consecutively numbered notebooks execute and pass validation: 191 interactive figures, 471 chart/table observations, no unsupported widgets, valid links, complete grids and 576 reconciled return paths.
- Dashboard validation covers 180 experiments, 2,616 securities, 20,880 scheduled snapshots, 329,601 holding episodes and 872,721 trade legs. The largest profit reconciliation residual is below INR 0.000007; the largest fee residual is below INR 0.00000005. Holdings, trade markers, borrowing and cash income also reconcile against saved ledgers.

The notebooks are the research record. The versioned data release supplies the inputs, ledgers, exports and prebuilt dashboard needed by a clean clone. Setup verifies archive and per-file checksums. Git source files exclude credentials and large research inputs; static previews and summary metrics are included. Recalculating notebook views is distinct from rerunning the signal and trading engines.
