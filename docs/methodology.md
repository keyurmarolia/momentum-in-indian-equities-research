# Methodology

## Universe

Formation uses literal trailing 6M and 12M adjusted-price histories, including the latest month. The start is the last common market close on or before the calendar-month offset.

NSE main-board EQ securities need both endpoints, 96.8% price coverage, at least 120 volume observations over 126 sessions and no unresolved price jump above 50% in the quality window. These tests use information available at the signal close. Missing next-session opens affect fills, not eligibility or ranking.

Median daily traded value (MDTV) is the middle rupee turnover observation over 126 market sessions. Missing turnover enters as zero. It measures typical absolute activity, not whether today's volume exceeds the stock's own median.

Reference capacity MDTV = (INR 1 crore / N) / 5%.

Thresholds are INR 1.67 crore for 12 stocks, INR 83.33 lakh for 24 and INR 40 lakh for 50. These are diagnostics, not eligibility screens or daily order limits. There is no market-cap or top-200 cutoff; SME series are excluded.

Explicit split, bonus and consolidation factors adjust OHLC; dividends are excluded. A missing daily mark carries the last observed adjusted close. An order without an open waits for the next actual observed open. A confirmed delisting with no later exchange print is written down to zero; cash or merger consideration is not reconstructed.

## Signals

- Raw Momentum: adjusted-price return over formation.
- Volatility-Adjusted Momentum: raw return divided by annualized daily log-return standard deviation over formation. Weights are not inverse-volatility weights.
- Jensen Alpha Momentum: OLS daily intercept of stock excess return against Nifty 50 excess return over formation. The liquid fund is the common reference return.
- Jegadeesh–Titman momentum: raw-return winners long and losers short, N/2 names per leg and 50% scheduled gross budget each.
- KM Momentum: liquidity/quality → close at least 3% above EMA100 and bullish Supertrend(10,3) → raw-return ranking. Daily close below EMA100 or bearish Supertrend triggers sale at the next actual observed open. Proceeds remain in the liquid sleeve until scheduled rebalance.

KM's EMA starts at the mean of 100 observed closes. ATR10 starts at ten true ranges with prior closes, then uses Wilder smoothing. Supertrend uses HL2 ± 3 ATR, prior-band direction switching and non-retreating active bands; initial valid direction is bullish. Missing observations do not manufacture indicator bars. These rules do not claim exact equality to an unidentified charting-package version.

## Risk and return

Monthly portfolios begin on 3 May 2007; quarterly and semi-annual portfolios begin on 2 July 2007. All end on 28 August 2026. Strategy notebooks retain those complete histories. The final comparison measures every configuration over the shared 2 July 2007–28 August 2026 window, retaining its actual holdings history. Benchmark statistics and curves match each frequency's observation dates; the benchmark uses close-to-close price returns.

Raw excludes charges. After-cost includes specified delivery charges. Post-tax scales FIFO realizations by capital remaining after prior financial-year payments, applies fixed rupee thresholds and eight-year loss carry-forwards, and deducts the resulting liability from wealth. Holdings are not rerun after tax payments.

The academic reference reports zero, 3%, 6% and 12% annual short-notional borrowing assumptions and includes collateral/cash earnings. Delivery-equity tax, borrow availability, margins and recalls are excluded.

Sharpe uses daily excess mean divided by daily excess standard deviation, annualized with √252. Maximum drawdown includes initial capital as a peak. Time underwater counts sessions below prior peak, not negative daily returns. Longest underwater counts consecutive such sessions; unrecovered episodes remain open.

Historical monthly 95% VaR is the loss at the fifth percentile; expected shortfall averages losses in that tail. Partial first and last months are included. These are observed distributions, not forecasts.

## Market states

Prior-close Nifty 50 versus SMA200 defines up/down. Its 63-session volatility versus the expanding historical median defines high/low volatility. Labels are lagged one session and are descriptive only.
