# Portfolio construction

## Shared sequence

At scheduled month-end, the study forms the point-in-time quality universe, calculates the fixed 6M or 12M signal, ranks stocks, constructs targets and fills at the next session's actual observed open. MDTV is retained as capacity evidence but does not remove a stock from the strategy universe. KM applies its technical entry filter before ranking.

N is 12, 24 or 50. A slot is 1/N: 8.333%, 4.167% or 2.000%. There is no rank buffer; a stock outside the selected membership exits at scheduled rebalance.

## Equal-weight reset

Every selected long targets 1/N of pre-trade equity. With 48 eligible stocks for N=50, target investment is 96% and target cash is 4%, before charges. Positions are not enlarged to 1/48. Sales execute first; affordable purchases share any cost-related reduction proportionally. Actual post-charge weights can differ slightly from targets.

Retained stocks reset at scheduled dates and drift between dates.

## Winner drift

Continuing stocks retain their current weights, capped at 2/N at scheduled dates. The cap does not trigger daily trimming.

Exits and entrants pair in stable symbol order. Each entrant receives min(paired exit weight, 1/N). Excess exit weight and cap trims are distributed equally among continuing holdings with room below 2/N. Distribution repeats until the residual is used or capacity exhausted.

Unmatched entrants share existing cash up to 1/N each. Unpaired exits and unallocated residual become cash. With insufficient breadth, retained winners can remain above 1/N, so the cash fraction need not equal that under equal-weight reset. Signal strength does not determine weights.

## KM exits

Between scheduled rebalances, close below EMA100 or bearish Supertrend(10,3) triggers next-observed-open sale. Other holdings are not resized; there is no immediate replacement. Proceeds earn the liquid-sleeve return until scheduled rebalance.

At scheduled dates, current qualifying membership governs targets. The entry buffer is 3% above EMA100; the exit is below EMA100 itself. There is no risk-distance ranking.

## Academic reference

N counts both legs: 6/6, 12/12 or 25/25 long/short. Equal-weight absolute slots are 1/N.

Winner drift operates separately inside each leg, with an absolute 2/N cap and up to 50% scheduled gross per leg through scaling or equal residual allocation. This leg-budget convention differs from long-only exit/entrant pairing and is stated in the academic notebooks. Exposures drift between dates.

Fixed annual borrowing deductions apply to short notional. Cash includes short-sale proceeds; this is not a pure uncollateralized winner-minus-loser spread. Borrow availability, margins and recalls are not modeled.

## Accounting

Costs apply to actual additions, removals, resizing and KM stop sales. Target rupee values use pre-trade, pre-tax equity; buy quantities respect available cash after charges. Portfolio exports show actual holdings before the separate tax overlay.

An order without an observed open remains pending while the position is marked at the last observed close. A confirmed delisting with no later exchange print is written down to zero. Merger consideration and other terminal recoveries are not reconstructed.
