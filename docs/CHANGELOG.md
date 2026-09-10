# Research change history

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

