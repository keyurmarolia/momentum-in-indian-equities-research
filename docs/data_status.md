# Data coverage

## Inputs

The official NSE EQ archive contains 6,402 trading-day files from 17 October 2000 through 28 August 2026. The market table has 8,138,535 security-day rows and 4,308 symbols; 3,526 symbols have at least 252 observations.

These are traded symbols, not certified unique issuer counts. Disappearance from a monthly file is not proof of delisting.

The corporate-action audit checks 1,130 events; four fall outside its 25% reconciliation tolerance. Explicit factors adjust splits, bonuses and consolidations, not dividends.

## References

The benchmark is the Nifty 50 price index. Continuous Aditya Birla Sun Life Liquid Fund Growth history begins on 2 April 2006. A documented unit-value rescaling on 7 October 2011 is removed before calculating returns. Direct Growth is linked from 1 January 2013 with a level-neutral adjustment.

The strategy sample begins after formation and reference history are available; the archive start is not the backtest start.

## Outputs

- 522,101 monthly ranking rows.
- 596,122 target rows and 893,426 actual portfolio-snapshot rows.
- 2,103,485 executed trade legs.
- 20,880 scheduled-rebalance diagnostics.
- 180 portfolio combinations.
- 576 performance rows: 144 long-only combinations × three layers, plus 36 academic combinations × four layers.
- 23 notebooks, numbered 00–22.
- Portfolio, trade and risk exports for all 20 strategy/lookback/maintenance notebooks.

## Limits

EQ history does not reconstruct every historical non-EQ series, symbol change or terminal recovery. Suspended positions remain marked at the last observed close and orders wait for an actual open. Confirmed delistings without a later exchange print use zero recovery.

Downloaded records are not equivalent to fully validated historical investability. Notebook 00 shows point-in-time screening losses and corporate-action exceptions.
