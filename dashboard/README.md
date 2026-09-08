# Momentum research explorer

A local, read-only dashboard for the completed Indian-equity momentum study.

## Coverage

180 experiment combinations: five strategy labels, two momentum lookbacks, two allocation methods, three portfolio concentrations, and three rebalance frequencies. The four long-only strategies are separate from the academic Jegadeesh–Titman reference.

The portfolio browser uses scheduled rebalance events, including cash-only events. Stock charts show the complete cached price history and all trades belonging to the selected experiment. Only the selected rebalance is marked with a red vertical line.

## Accounting

Long-only holdings follow the after-trading-cost simulation. Academic holdings follow the 6% annual borrowing scenario. Portfolio-level tax overlays are not allocated to individual stocks.

Position episodes close only at zero quantity. Additions and partial exits stay within the episode. Reversals close one directional episode and open another. FIFO realized return uses matched acquisition notional plus entry charges as its denominator. Position profit includes trading charges and, for the academic reference, allocated borrowing. Liquid-cash income remains outside stock-level profit.

Price charts, fills, and quantities use the same corporate-action-adjusted basis. Open positions are marked at the latest cached price. Orders wait for an actual observed open; confirmed delistings without later exchange prints use zero recovery. Symbol continuity and unreconstructed terminal consideration remain research limitations.

## Data and application

The interface is a static React application. Its production build is `dist`; all asset links are relative. There is no account login, trading endpoint, broker connection, server-side calculation, or external chart CDN.

The manifest identifies the experiments and securities. Compressed experiment files and stock-price files load only when selected. The browser retains a bounded cache. Original source files and credentials stay outside the application; its exported price and portfolio data are derived from the research cache.

The exporter reads the existing processed market, holdings, trade, return, and risk files. It rejects mismatched portfolio membership, trading charges, stock profit, and academic borrowing before writing the manifest. The validation report is stored in the project’s reports directory.

The project-root `Open Research Dashboard.command` launches the built dashboard on the local computer.
