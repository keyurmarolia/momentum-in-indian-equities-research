"""Readable research views for the chronological notebook series."""

import html

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from IPython.display import HTML, display
from plotly.subplots import make_subplots

from .comparison import comparison_metrics
from .config import PROJECT_ROOT
from .risk import align_cash_nav, drawdown_episode_table, performance_summary

KEYS = ["strategy", "formation_period", "frequency", "holdings_n", "maintenance"]
LABELS = {
    "raw_momentum": "Raw Momentum",
    "vol_adjusted": "Volatility-Adjusted Momentum",
    "jensen_alpha": "Jensen Alpha Momentum",
    "jt_academic": "Jegadeesh–Titman Momentum",
    "km_momentum": "KM Momentum",
}
LAYERS = {
    "raw": "Raw",
    "gross": "After costs",
    "post_tax": "Post-tax overlay",
    "academic_raw": "Academic raw",
    "academic_borrow_3pct": "Borrow 3%",
    "academic_borrow_6pct": "Borrow 6%",
    "academic_borrow_12pct": "Borrow 12%",
}
NAMES = {
    "frequency": "Rebalance",
    "holdings_n": "N",
    "return_type": "Return layer",
    "strategy": "Strategy",
    "cagr": "CAGR",
    "sharpe": "Sharpe",
    "maximum_drawdown": "Max drawdown",
    "average_drawdown": "Mean daily drawdown",
    "annualized_volatility": "Annualized volatility",
    "calmar": "Calmar",
    "monthly_var_95": "Monthly VaR 95%",
    "monthly_es_95": "Monthly ES 95%",
    "time_below_prior_peak": "Time below prior peak",
    "longest_underwater_trading_days": "Longest underwater (sessions)",
    "maintenance": "Maintenance",
    "formation_period": "Lookback",
    "average_names_held": "Mean names at rebalance",
    "average_cash_weight": "Mean cash weight",
    "average_one_way_turnover": "Mean scheduled turnover",
    "average_name_retention_rate": "Scheduled name retention",
    "total_transaction_cost_inr": "All trading charges (INR)",
    "signal_value": "Ranking score",
    "mdtv_inr": "MDTV (INR)",
    "symbol": "Symbol",
    "company_name": "Company",
    "weight": "Actual weight",
    "target_selected": "Current selection",
    "execution_status": "Execution status",
    "leg": "Leg",
    "signal_date": "Signal date",
    "execution_date": "Execution date",
}
NAMES.update(
    {
        "raw_momentum": "Formation price return",
        "vol_adjusted": "Return / volatility",
        "jensen_alpha": "Daily alpha",
        "stop_exit_days": "Days with stop sales",
        "regime": "Market state",
        "sessions": "Sessions",
        "mean_daily": "Mean daily return",
        "volatility": "Daily volatility",
        "positive_days": "Positive days",
        "mean_long": "Mean long exposure",
        "mean_short": "Mean short exposure",
        "borrow_INR": "Borrow fees (INR)",
        "first_rebalance": "First rebalance",
        "last_rebalance": "Last rebalance",
        "rebalance_dates": "Rebalance dates",
        "holding_rows": "Holding rows",
        "price_history_eligible": "Price-history eligible",
        "excluded_unresolved_price_jump": "Price-jump exclusions",
        "eligible_before_liquidity_cut": "Quality-eligible universe",
        "selected_liquidity_universe": "Meets reference capacity",
        "minimum_names": "Minimum names",
        "median_names": "Median names",
        "maximum_names": "Maximum names",
        "MDTV_INR": "Minimum MDTV (INR)",
    }
)
PERCENT = {
    "cagr",
    "maximum_drawdown",
    "average_drawdown",
    "annualized_volatility",
    "monthly_var_95",
    "monthly_es_95",
    "time_below_prior_peak",
    "average_cash_weight",
    "average_one_way_turnover",
    "average_name_retention_rate",
    "weight",
    "raw_momentum",
}
PERCENT.update({"mean_long", "mean_short"})
FREQS = ["1M", "3M", "6M"]
COLORS = {"1M": "#2266a5", "3M": "#a15b16", "6M": "#297c50", "Benchmark": "#616b78"}
REGIMES = {
    "Up / Low volatility": "#d5ebd5",
    "Up / High volatility": "#f4dfb3",
    "Down / Low volatility": "#d6e1f1",
    "Down / High volatility": "#efc3c3",
}


def display_series(series):
    """Keep weekly chart points while preserving exact first and last observations."""
    series = series.dropna().sort_index()
    if len(series) < 3:
        return series
    weekly = series.groupby(series.index.to_period("W-FRI")).tail(1)
    return (
        pd.concat([series.iloc[:1], weekly, series.iloc[-1:]])
        .sort_index()
        .loc[lambda x: ~x.index.duplicated(keep="last")]
    )


def note(text, tone="neutral"):
    palette = {
        "neutral": ("#f2f4f7", "#59636e"),
        "positive": ("#e8f4eb", "#287745"),
        "negative": ("#fceced", "#ab3438"),
    }
    bg, edge = palette[tone]
    display(
        HTML(
            f"<div style='background:{bg};border-left:4px solid {edge};padding:10px 14px;margin:12px 0;color:#202a32'><b>Observation.</b> {html.escape(text)}</div>"
        )
    )


def table(frame, caption):
    frame = frame.copy()
    for column in frame:
        if column in PERCENT:
            frame[column] = frame[column].map(lambda x: "—" if pd.isna(x) else f"{x:.1%}")
        elif column in ("sharpe", "signal_value", "vol_adjusted", "jensen_alpha"):
            decimals = 4 if column == "jensen_alpha" else 3
            frame[column] = frame[column].map(
                lambda x, digits=decimals: "—" if pd.isna(x) else f"{x:.{digits}f}"
            )
        elif pd.api.types.is_datetime64_any_dtype(frame[column]):
            frame[column] = frame[column].dt.strftime("%Y-%m-%d").fillna("Not recovered")
        elif pd.api.types.is_float_dtype(frame[column]):
            frame[column] = frame[column].map(lambda x: "—" if pd.isna(x) else f"{x:,.2f}")
    frame = frame.rename(
        columns={c: NAMES.get(c, str(c).replace("_", " ").capitalize()) for c in frame}
    )
    frame.columns.name = None
    rendered = frame.to_html(
        index=False, escape=True, classes="research-table", border=0, na_rep="—"
    )
    display(
        HTML(f"<p><b>{html.escape(caption)}</b></p><div style='overflow-x:auto'>{rendered}</div>")
    )


def chart(fig, title, log=False, slider=False, heatmap=False):
    fig.update_layout(
        template="plotly_white",
        width=870 if heatmap else 1040,
        height=450 if heatmap else 610,
        title=dict(text=title, x=0.02, y=0.97, font=dict(size=18)),
        margin=dict(l=110 if heatmap else 75, r=155 if heatmap else 235, t=95, b=80),
        legend=dict(
            x=1.025, y=1, font=dict(size=12), itemclick="toggle", itemdoubleclick="toggleothers"
        ),
        hovermode="closest" if heatmap else "x unified",
    )
    if slider:
        fig.update_xaxes(rangeslider=dict(visible=True, thickness=0.13), title="Date")
    if log:
        ticks = [v * 10.0**power for power in range(-3, 9) for v in (1, 2, 5)]
        fig.update_yaxes(
            type="log", tickmode="array", tickvals=ticks, ticktext=[f"{v:g}" for v in ticks]
        )
    fig.show(
        renderer="plotly_mimetype",
        config={"responsive": False, "displaylogo": False, "scrollZoom": True},
    )


class ResearchNotebook:
    def __init__(self, strategy=None, formation=None, maintenance=None):
        self.root = PROJECT_ROOT
        self.p = self.root / "data/processed"
        self.tables = self.root / "reports/tables"
        self.strategy, self.formation, self.maintenance = strategy, formation, maintenance
        self.metrics = pd.read_csv(self.p / "backtest_metrics.csv")
        self.impl = pd.read_csv(self.p / "implementation_diagnostics.csv")
        self.path = pd.read_csv(self.p / "path_risk_diagnostics.csv")
        self.benchmark = (
            pd.read_csv(self.p / "nifty50_price_index.csv", parse_dates=["date"])
            .set_index("date")
            .close.pct_change(fill_method=None)
        )
        cash_nav = (
            pd.read_csv(self.p / "absl_liquid_fund_continuous.csv", parse_dates=["date"])
            .set_index("date")
            .continuous_nav
        )
        self.cash = align_cash_nav(cash_nav, self.benchmark.index).pct_change(fill_method=None)
        self.academic = strategy == "jt_academic"
        self.layer = "academic_borrow_6pct" if self.academic else "post_tax"
        self.layers = (
            [
                "academic_raw",
                "academic_borrow_3pct",
                "academic_borrow_6pct",
                "academic_borrow_12pct",
            ]
            if self.academic
            else ["raw", "gross", "post_tax"]
        )
        self.filters = (
            [
                ("strategy", "=", strategy),
                ("formation_period", "=", formation),
                ("maintenance", "=", maintenance),
            ]
            if strategy
            else None
        )
        if strategy:
            self.daily = pd.read_parquet(self.p / "backtest_daily.parquet", filters=self.filters)
            self.holdings = pd.read_parquet(
                self.p / "portfolio_holdings_at_rebalance.parquet", filters=self.filters
            )
            self.rankings = pd.read_parquet(
                self.p / "signal_rankings_monthly.parquet",
                filters=[("formation_period", "=", formation)],
            )
            self.m = self.slice(self.metrics)
            self.i = self.slice(self.impl)
            self.r = self.slice(self.path)
        display(
            HTML(
                "<style>.research-table{border-collapse:collapse;font-size:13px;width:100%;max-width:1040px}.research-table th,.research-table td{padding:8px 10px;text-align:left;border-bottom:1px solid #dfe4e8;white-space:normal;max-width:220px}.research-table th{background:#edf1f4;color:#22313f}.jp-OutputArea-output{overflow-x:auto}</style>"
            )
        )

    def slice(self, frame):
        q = frame
        for key, value in [
            ("strategy", self.strategy),
            ("formation_period", self.formation),
            ("maintenance", self.maintenance),
        ]:
            q = q[q[key].eq(value)]
        return q.copy()

    def series(self, n, f, layer=None):
        q = self.daily[
            (self.daily.holdings_n == n)
            & (self.daily.frequency == f)
            & (self.daily.return_type == (layer or self.layer))
        ]
        return q.sort_values("date").set_index("date")["return"]

    def snapshot(self):
        q = self.holdings[(self.holdings.holdings_n == 24) & (self.holdings.frequency == "1M")]
        self.sample = q[q.signal_date == q.signal_date.max()].copy()
        self.selected_sample = self.sample[self.sample.target_selected].copy()
        day = self.sample.signal_date.iloc[0]
        self.cross = self.rankings[self.rankings.signal_date == day].copy()
        before = len(self.cross)
        if self.strategy == "km_momentum":
            self.cross = self.cross[self.cross.km_entry_eligible]
        col = {"vol_adjusted": "vol_adjusted", "jensen_alpha": "jensen_alpha"}.get(
            self.strategy, "raw_momentum"
        )
        top = self.cross.sort_values([col, "symbol"], ascending=[False, True]).head(10)
        table(
            top[["symbol", col, "mdtv_inr"]],
            "First 10 ranks — full quality universe retained in the signal database",
        )
        table(
            self.sample[
                ["symbol", "leg", "weight", "target_selected", "execution_status", col, "mdtv_inr"]
            ],
            "Complete actual monthly N=24 portfolio at the latest signal date",
        )
        selected = int(self.sample.target_selected.sum())
        note(
            f"{day.date()}: {before:,} securities passed the common data-quality gates; {len(self.cross):,} passed this signal's gates. The actual portfolio contains {len(self.sample)} names, including {selected} current selections and {len(self.sample) - selected} positions awaiting an executable exit. MDTV is reported as capacity evidence and does not change the ranking."
        )
        candidates = self.selected_sample[self.selected_sample[col].notna()]
        example = candidates.sort_values(col, ascending=False).iloc[0]
        prices = pd.read_parquet(
            self.p / "equity_market_panel.parquet",
            columns=["date", "close"],
            filters=[
                ("symbol", "=", example.symbol),
                ("date", ">=", example.formation_start_date),
                ("date", "<=", day),
            ],
        ).sort_values("date")
        first, last = prices.iloc[0], prices.iloc[-1]
        table(
            pd.DataFrame(
                {
                    "Symbol": [example.symbol],
                    "Formation start": [first.date],
                    "Start adjusted close": [first.close],
                    "Signal close date": [last.date],
                    "End adjusted close": [last.close],
                    "raw_momentum": [last.close / first.close - 1],
                }
            ),
            "Price inputs behind one selected stock",
        )
        note(
            f"{example.symbol}: {last.close:.2f} / {first.close:.2f} − 1 = {last.close / first.close - 1:.2%}. This is the raw formation return; the signal rule above explains whether it is used directly, volatility-scaled, or replaced by regression alpha."
        )
        self.signal_evidence(col)

    def signal_evidence(self, col):
        fig = go.Figure()
        if self.strategy == "raw_momentum":
            fig.add_trace(
                go.Histogram(x=self.cross.raw_momentum, nbinsx=45, name="Eligible universe")
            )
            selected = self.selected_sample.raw_momentum.median()
            fig.add_vline(x=selected, line_color="#267746", line_width=3)
            fig.update_xaxes(title=f"{self.formation} price return", tickformat=".0%")
            fig.update_yaxes(title="Securities")
            chart(fig, "Price-momentum distribution")
            note(
                f"The selected median formation return is {selected:.1%}, versus {self.cross.raw_momentum.median():.1%} across eligible stocks. The green line marks the selected median: rank selection concentrates the high-return tail."
            )
        elif self.strategy in ("vol_adjusted", "jensen_alpha"):
            fig.add_trace(
                go.Scatter(
                    x=self.cross.raw_momentum,
                    y=self.cross[col],
                    mode="markers",
                    name="Eligible universe",
                    marker=dict(opacity=0.35, size=5),
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=self.selected_sample.raw_momentum,
                    y=self.selected_sample[col],
                    mode="markers",
                    name="Selected",
                    marker=dict(color="#267746", size=9),
                )
            )
            fig.update_xaxes(title=f"{self.formation} price return", tickformat=".0%")
            fig.update_yaxes(
                title="Return / annualized<br>log-return volatility"
                if col == "vol_adjusted"
                else "Daily regression intercept"
            )
            chart(fig, "How the adjusted signal changes the ranking")
            pair = self.cross[["raw_momentum", col]].dropna().rank(method="average")
            corr = pair.raw_momentum.corr(pair[col])
            note(
                f"Rank correlation with raw momentum is {corr:.3f} on this date. {'Volatility scaling rewards smoother trends' if col == 'vol_adjusted' else 'The regression removes fitted market exposure'}; the highlighted selections show the resulting change in the top tail."
            )
        elif self.academic:
            x = (
                self.selected_sample.groupby("leg")
                .agg(
                    momentum=("raw_momentum", "mean"),
                    names=("symbol", "size"),
                    weight=("weight", lambda v: v.abs().sum()),
                )
                .reset_index()
            )
            fig.add_trace(go.Bar(x=x.leg, y=x.momentum, marker_color=["#297c50", "#ac4545"]))
            fig.update_yaxes(title="Mean formation price return", tickformat=".0%")
            chart(fig, "Winner and loser signal separation")
            note(
                f"The winner leg averages {x.loc[x.leg == 'long', 'momentum'].iloc[0]:.1%} past return and the loser leg {x.loc[x.leg == 'short', 'momentum'].iloc[0]:.1%}. Their subsequent difference, not the long leg alone, measures the momentum spread."
            )
        else:
            symbol = self.selected_sample.sort_values("weight", ascending=False).symbol.iloc[0]
            state = (
                pd.read_parquet(
                    self.p / "km_technical_state.parquet", filters=[("symbol", "=", symbol)]
                )
                .dropna(subset=["close"])
                .sort_values("date")
                .tail(252)
            )
            for column, name, color in [
                ("close", "Adjusted close", "#2266a5"),
                ("ema100", "EMA(100)", "#a56b14"),
            ]:
                fig.add_trace(
                    go.Scatter(x=state.date, y=state[column], name=name, line=dict(color=color))
                )
            for bull, name, color in [
                (True, "Bullish Supertrend", "#297c50"),
                (False, "Bearish Supertrend", "#b44444"),
            ]:
                fig.add_trace(
                    go.Scatter(
                        x=state.date,
                        y=state.supertrend.where(state.supertrend_bullish.eq(bull)),
                        name=name,
                        line=dict(color=color, width=2),
                        connectgaps=False,
                    )
                )
            fig.update_yaxes(title="Adjusted price (INR)")
            chart(fig, f"KM technical evidence: {symbol}", log=True, slider=True)
            last = state.iloc[-1]
            note(
                f"The plotted example uses EMA(100), not SMA. Its final close is {(last.close / last.ema100 - 1):.1%} above EMA, and Supertrend is {'bullish' if last.supertrend_bullish else 'bearish'}. Entry needs the 3% buffer; exit needs only close below EMA or a bearish Supertrend."
            )

    def layers_bridge(self):
        dates = (
            self.daily[self.daily.return_type == self.layer]
            .groupby("frequency")
            .agg(
                first_date=("date", "min"), last_date=("date", "max"), sessions=("date", "nunique")
            )
            .reindex(FREQS)
            .reset_index()
        )
        table(
            dates,
            "Observation windows — each frequency begins at its first eligible scheduled rebalance",
        )
        note(
            "Monthly portfolios start on 3 May 2007; quarterly and semi-annual portfolios start on 2 July 2007. All end on 28 August 2026. Frequency comparisons therefore include this initial timing difference; each benchmark uses its portfolio's actual window."
        )
        x = self.m.pivot(index=["frequency", "holdings_n"], columns="return_type", values="cagr")[
            self.layers
        ].reset_index()
        for col in self.layers:
            x[col] = x[col].map(lambda v: f"{v:.1%}")
        table(x.rename(columns=LAYERS), "CAGR bridge — every rebalance/breadth cell")
        if self.academic:
            note(
                "All borrowing scenarios share the same sample and membership. The 6% baseline is a notional stock-borrow deduction, not an executable delivery-equity post-tax return."
            )
        else:
            z = self.m.pivot(
                index=["frequency", "holdings_n"], columns="return_type", values="cagr"
            )
            note(
                f"Across this notebook's nine cells, costs change CAGR by {(z.gross - z.raw).mean():+.2%} on average; the modeled tax overlay changes it by {(z.post_tax - z.gross).mean():+.2%}. Annual taxes are paid from modeled capital, and later gains are scaled to the capital remaining."
            )
        joined = self.m.merge(self.r, on=KEYS + ["return_type"], validate="one_to_one")
        joined.to_csv(self.tables / f"{self.stem}_all_return_layer_metrics.csv", index=False)

    @property
    def stem(self):
        return f"{self.strategy}_{self.formation.lower()}_{self.maintenance}"

    def risk_grid(self):
        q = (
            self.m[self.m.return_type == self.layer]
            .merge(self.r, on=KEYS + ["return_type"], validate="one_to_one")
            .sort_values(["frequency", "holdings_n"])
        )
        table(
            q[["frequency", "holdings_n", "cagr", "sharpe", "maximum_drawdown", "monthly_var_95"]],
            "Growth and downside risk — all nine cells",
        )
        table(
            q[
                [
                    "frequency",
                    "holdings_n",
                    "monthly_es_95",
                    "time_below_prior_peak",
                    "longest_underwater_trading_days",
                ]
            ],
            "Tail severity and recovery burden — all nine cells",
        )
        best = q.loc[q.sharpe.idxmax()]
        worst = q.loc[q.maximum_drawdown.idxmin()]
        note(
            f"The strongest Sharpe is {best.sharpe:.2f} at {best.frequency}, N={int(best.holdings_n)}. The deepest drawdown is {worst.maximum_drawdown:.1%} at {worst.frequency}, N={int(worst.holdings_n)}. The two criteria need not select the same portfolio."
        )

    def heatmap(self, metric):
        q = self.m[self.m.return_type == self.layer]
        z = (
            q.pivot(index="frequency", columns="holdings_n", values=metric)
            .reindex(FREQS)
            .reindex(columns=[12, 24, 50])
        )
        fmt = ".2f" if metric == "sharpe" else ".1%"
        text = np.array([[format(v, fmt) for v in row] for row in z.values])
        global_values = self.metrics[
            (self.metrics.return_type == self.layer)
            & (
                self.metrics.strategy.eq("jt_academic")
                if self.academic
                else self.metrics.strategy.ne("jt_academic")
            )
        ][metric]
        if metric in ("cagr", "sharpe"):
            bound = float(global_values.abs().max())
            zmin, zmax, zmid = -bound, bound, 0.0
        elif metric == "maximum_drawdown":
            zmin, zmax, zmid = float(global_values.min()), 0.0, None
        else:
            zmin, zmax, zmid = 0.0, float(global_values.max()), None
        fig = go.Figure(
            go.Heatmap(
                z=z.values,
                x=["12", "24", "50"],
                y=["Monthly", "Quarterly", "Semi-annual"],
                text=text,
                texttemplate="%{text}",
                textfont=dict(size=15),
                colorscale="YlOrRd" if metric == "monthly_var_95" else "RdYlGn",
                zmin=zmin,
                zmax=zmax,
                zmid=zmid,
                colorbar=dict(
                    title=dict(text="Sharpe" if metric == "sharpe" else "Rate"), tickformat=fmt
                ),
                xgap=3,
                ygap=3,
            )
        )
        fig.update_xaxes(title="Target holdings")
        fig.update_yaxes(autorange="reversed")
        chart(fig, NAMES[metric], heatmap=True)
        best = q.loc[q[metric].idxmin() if metric == "monthly_var_95" else q[metric].idxmax()]
        note(
            f"The preferred {NAMES[metric]} cell is {best.frequency}, N={int(best.holdings_n)} ({format(best[metric], fmt)}). Colour limits are shared across the {'academic' if self.academic else 'long-only'} notebooks, so equal colours mean equal values; lower VaR and less-negative drawdown are preferable."
        )

    def equity(self, n):
        fig = go.Figure()
        for f in FREQS:
            for layer in self.layers:
                s = self.series(n, f, layer)
                w = display_series((1 + s).cumprod())
                fig.add_trace(
                    go.Scatter(
                        x=w.index,
                        y=w,
                        name=f"{f} · {LAYERS[layer]}",
                        visible=True if layer == self.layer else "legendonly",
                        line=dict(
                            color=COLORS[f],
                            width=2,
                            dash="solid"
                            if layer == self.layer
                            else "dash"
                            if layer in ("gross", "academic_raw")
                            else "dot",
                        ),
                    )
                )
        benchmarks = {f: self.benchmark.reindex(self.series(n, f).index).fillna(0) for f in FREQS}
        benchmark_risks = {f: performance_summary(b, self.cash) for f, b in benchmarks.items()}
        for f in FREQS:
            w = display_series((1 + benchmarks[f]).cumprod())
            fig.add_trace(
                go.Scatter(
                    x=w.index,
                    y=w,
                    name=f"Nifty · {f} window",
                    visible=True if f == "1M" else "legendonly",
                    line=dict(color="#656b72", dash="dash"),
                )
            )
        fig.update_yaxes(title="Growth of INR 1 (log scale)")
        chart(fig, f"N={n} · formation {self.formation}", log=True, slider=True)
        q = self.m[(self.m.holdings_n == n) & (self.m.return_type == self.layer)]
        best = q.loc[q.cagr.idxmax()]
        bm = benchmark_risks[best.frequency]
        note(
            f"N={n}: {best.frequency} has the highest CAGR ({best.cagr:.1%}), against {bm['cagr']:.1%} for the matched price benchmark. Its drawdown is {best.maximum_drawdown:.1%}. Only final-layer curves start visible; the legend exposes the raw and cost layers for each frequency."
        )
        rows = []
        for f in FREQS:
            for layer in self.layers:
                r = self.m[
                    (self.m.holdings_n == n)
                    & (self.m.frequency == f)
                    & (self.m.return_type == layer)
                ].iloc[0]
                rows.append(
                    {
                        "frequency": f,
                        "return_type": LAYERS[layer],
                        **r[["cagr", "sharpe", "maximum_drawdown", "monthly_var_95"]].to_dict(),
                    }
                )
            rows.append(
                {
                    "frequency": f,
                    "return_type": "Nifty 50 price",
                    **{
                        k: benchmark_risks[f][k]
                        for k in ["cagr", "sharpe", "maximum_drawdown", "monthly_var_95"]
                    },
                }
            )
        table(pd.DataFrame(rows), f"N={n}: risk statistics for every selectable curve")
        recovery = self.m[self.m.holdings_n == n].merge(
            self.r, on=KEYS + ["return_type"], validate="one_to_one"
        )
        recovery = recovery[
            [
                "frequency",
                "return_type",
                "monthly_es_95",
                "time_below_prior_peak",
                "longest_underwater_trading_days",
            ]
        ].copy()
        recovery.return_type = recovery.return_type.map(LAYERS)
        extra = []
        for f, benchmark in benchmarks.items():
            bwealth = (1 + benchmark).cumprod()
            below = bwealth.div(bwealth.cummax().clip(lower=1)).sub(1) < -1e-12
            episodes = drawdown_episode_table(benchmark)
            extra.append(
                {
                    "frequency": f,
                    "return_type": "Nifty 50 price",
                    "monthly_es_95": benchmark_risks[f]["monthly_es_95"],
                    "time_below_prior_peak": below.mean(),
                    "longest_underwater_trading_days": episodes.trading_days.max()
                    if len(episodes)
                    else 0,
                }
            )
        table(
            pd.concat([recovery, pd.DataFrame(extra)], ignore_index=True),
            f"N={n}: tail losses and recovery for every selectable curve",
        )
        note(
            "Each frequency has a benchmark measured on its own dates. The monthly benchmark starts visible; the other matching windows are selectable. All benchmarks are close-to-close price returns, not dividend-inclusive total returns."
        )

    def recovery(self):
        rows = []
        paths = {f: self.series(24, f) for f in FREQS}
        paths.update(
            {
                f"Nifty · {f}": self.benchmark.reindex(self.series(24, f).index).fillna(0)
                for f in FREQS
            }
        )
        for f, s in paths.items():
            ep = drawdown_episode_table(s)
            if ep.empty:
                continue
            longest = ep.loc[ep.trading_days.idxmax()]
            rows.append(
                {
                    "Series": f,
                    "Peak": str(longest.peak_date.date())
                    if pd.notna(longest.peak_date)
                    else "Initial capital",
                    "Trough": str(longest.trough_date.date()),
                    "Recovery": str(longest.recovery_date.date())
                    if pd.notna(longest.recovery_date)
                    else "Not recovered",
                    "Sessions": int(longest.trading_days),
                    "Calendar days": int(longest.calendar_days),
                    "Episode loss": f"{longest.maximum_loss:.1%}",
                }
            )
        table(pd.DataFrame(rows), "Longest underwater episode — N=24 and matched benchmark")
        under = self.r[self.r.return_type == self.layer].time_below_prior_peak.mean()
        note(
            f"Across the nine cells, the average share below a prior peak is {under:.1%}. This counts days waiting for a new all-time high, not negative-return days. An unrecovered episode remains open at sample end."
        )

    def behavior(self):
        if self.academic:
            q = (
                self.daily[self.daily.return_type == self.layer]
                .groupby(["frequency", "holdings_n"])
                .agg(
                    mean_long=("long_exposure", "mean"),
                    mean_short=("short_exposure", "mean"),
                    borrow_INR=("borrow_cost", "sum"),
                )
                .reset_index()
            )
            table(q, "Academic gross exposures and cumulative borrow deduction")
            note(
                "50% long and 50% short are scheduled gross budgets, not constant daily exposures. Prices can change both legs between rebalances. Short-sale proceeds remain in the collateral/cash account; this is not net-zero risk."
            )
        else:
            table(
                self.i[
                    [
                        "frequency",
                        "holdings_n",
                        "average_names_held",
                        "average_cash_weight",
                        "average_name_retention_rate",
                    ]
                ],
                "Membership and cash",
            )
            table(
                self.i[
                    [
                        "frequency",
                        "holdings_n",
                        "average_one_way_turnover",
                        "total_transaction_cost_inr",
                        "stop_exit_days",
                    ]
                ],
                "Trading intensity and all-date charges",
            )
            note(
                f"Mean daily cash weight averages {self.i.average_cash_weight.mean():.1%} across the grid. Scheduled retention compares successive target name sets, not uninterrupted ownership; all-date charges include daily stop sales."
            )
            if self.strategy == "km_momentum":
                fig = go.Figure()
                for f in FREQS:
                    q = self.daily[
                        (self.daily.frequency == f)
                        & (self.daily.holdings_n == 24)
                        & (self.daily.return_type == "gross")
                    ].sort_values("date")
                    cash_weight = display_series(
                        q.set_index("date").cash_value / q.set_index("date").equity
                    )
                    fig.add_trace(
                        go.Scatter(
                            x=cash_weight.index,
                            y=cash_weight,
                            name=f,
                            line=dict(color=COLORS[f]),
                        )
                    )
                fig.update_yaxes(title="Cash / portfolio value", tickformat=".0%")
                chart(fig, "KM cash between scheduled rebalances", slider=True)
                note(
                    f"{int(self.i.stop_exit_days.sum()):,} portfolio-days contain a KM stop sale across the nine cells. Stop proceeds do not trigger a replacement selection. An already-pending scheduled order can still fill when a missing quote becomes available."
                )

    def regimes(self):
        b = (
            pd.read_csv(self.p / "nifty50_price_index.csv", parse_dates=["date"])
            .set_index("date")
            .close
        )
        r = b.pct_change(fill_method=None)
        ma = b.rolling(200).mean()
        vol = r.rolling(63).std() * np.sqrt(252)
        threshold = vol.expanding(min_periods=252).median()
        labels = (
            pd.Series(np.where(b >= ma, "Up", "Down"), index=b.index)
            + " / "
            + pd.Series(
                np.where(vol <= threshold, "Low volatility", "High volatility"), index=b.index
            )
        )
        labels = labels.where(ma.notna() & threshold.notna()).shift(1)
        s = self.series(24, "1M")
        q = pd.DataFrame({"return": s, "regime": labels.reindex(s.index)}).dropna()
        fig = go.Figure()
        segments = (q.regime != q.regime.shift()).cumsum()
        for _, g in q.groupby(segments):
            fig.add_vrect(
                x0=g.index[0],
                x1=g.index[-1] + pd.Timedelta(days=1),
                fillcolor=REGIMES[g.regime.iloc[0]],
                opacity=0.45,
                line_width=0,
                layer="below",
            )
        strategy_wealth = display_series((1 + s).cumprod())
        fig.add_trace(
            go.Scatter(
                x=strategy_wealth.index,
                y=strategy_wealth,
                name=LAYERS[self.layer],
                line=dict(color="#2266a5"),
            )
        )
        bm = self.benchmark.reindex(s.index).fillna(0)
        benchmark_wealth = display_series((1 + bm).cumprod())
        fig.add_trace(
            go.Scatter(
                x=benchmark_wealth.index,
                y=benchmark_wealth,
                name="Nifty 50 price",
                line=dict(color="#646b74"),
            )
        )
        for label, color in REGIMES.items():
            fig.add_trace(
                go.Scatter(
                    x=[None],
                    y=[None],
                    name=label,
                    mode="markers",
                    marker=dict(color=color, size=12),
                )
            )
        fig.update_yaxes(title="Growth of INR 1")
        chart(fig, "Market-state attribution · monthly N=24", log=True, slider=True)
        summary = (
            q.groupby("regime")
            .agg(
                sessions=("return", "size"),
                mean_daily=("return", "mean"),
                volatility=("return", "std"),
                positive_days=("return", lambda x: (x > 0).mean()),
            )
            .reset_index()
        )
        for c in ("mean_daily", "positive_days", "volatility"):
            summary[c] = summary[c].map(lambda x: f"{x:.2%}")
        table(summary, "Daily outcomes by prior-close market state")
        means = q.groupby("regime")["return"].mean()
        note(
            f"The highest mean daily return occurs in {means.idxmax()} ({means.max():.3%}); the lowest in {means.idxmin()} ({means.min():.3%}). States use the prior close versus SMA(200), and 63-session volatility versus its expanding median. They describe outcomes and never alter positions."
        )

    def portfolio_exports(self):
        stem = self.stem
        files = [
            (f"{stem}_portfolios.csv", "Complete scheduled portfolio history"),
            (f"{stem}_all_return_layer_metrics.csv", "All grid and return-layer risk metrics"),
        ]
        trades = pd.read_parquet(
            self.p / "trade_ledger.parquet",
            filters=self.filters
            + [("return_type", "=", "academic_borrow_6pct" if self.academic else "gross")],
        )
        trades.to_csv(self.tables / f"{stem}_trades.csv", index=False)
        files.append((f"{stem}_trades.csv", "Complete trade history, including stop exits"))
        for filename, label in files:
            display(HTML(f'<p><a href="../reports/tables/{filename}">{label}</a></p>'))
        summaries = (
            self.holdings.groupby(["frequency", "holdings_n"])
            .agg(
                first_rebalance=("execution_date", "min"),
                last_rebalance=("execution_date", "max"),
                rebalance_dates=("execution_date", "nunique"),
                holding_rows=("symbol", "size"),
            )
            .reset_index()
        )
        table(summaries, "Portfolio-history coverage")
        note(
            "The exports contain every actual holding and trade row; no widget state is required. Portfolio rows distinguish current selections from positions awaiting an executable exit. Weights are after execution charges and before the tax overlay. Cash-only rebalance dates appear in the diagnostics rather than as invented stock rows."
        )

    def conclusion(self):
        q = self.m[self.m.return_type == self.layer]
        best = q.loc[q.sharpe.idxmax()]
        same = self.metrics[
            (self.metrics.formation_period == self.formation)
            & (self.metrics.maintenance == self.maintenance)
            & (self.metrics.return_type == "post_tax")
        ]
        if self.strategy == "raw_momentum":
            text = f"{int(q.cagr.gt(0).sum())}/9 raw-momentum cells have positive post-tax CAGR. This is the benchmark signal for assessing whether risk adjustment or technical exits add value."
        elif self.academic:
            raw = self.m[self.m.return_type == "academic_raw"].set_index(
                ["frequency", "holdings_n"]
            )
            borrow = q.set_index(["frequency", "holdings_n"])
            text = f"Baseline borrowing reduces mean CAGR by {(raw.cagr - borrow.cagr).mean():.2%}; {int(q.cagr.gt(0).sum())}/9 cells remain positive. This is an academic spread-plus-collateral result, not a post-tax executable portfolio."
        else:
            raw = same[same.strategy == "raw_momentum"].set_index(["frequency", "holdings_n"])
            own = q.set_index(["frequency", "holdings_n"])
            text = f"Against matched Raw Momentum cells, mean CAGR changes by {(own.cagr - raw.cagr).mean():+.2%} and mean maximum drawdown by {(own.maximum_drawdown - raw.maximum_drawdown).mean():+.2%}; {int((own.sharpe > raw.sharpe).sum())}/9 cells have higher Sharpe."
        if self.strategy not in ("raw_momentum", "jt_academic"):
            growth = (own.cagr - raw.cagr).mean()
            safety = (own.maximum_drawdown - raw.maximum_drawdown).mean()
            tone = (
                "positive"
                if growth > 0 and safety >= 0
                else "negative"
                if growth < 0 and safety <= 0
                else "neutral"
            )
        else:
            tone = "positive" if q.cagr.mean() > 0 else "negative"
        note(text, tone)
        note(
            f"The strongest Sharpe specification is {best.frequency}, N={int(best.holdings_n)}: CAGR {best.cagr:.1%}, Sharpe {best.sharpe:.2f}, maximum drawdown {best.maximum_drawdown:.1%}. This is an in-sample result across a tested grid, not an independent forecast."
        )

    def universe(self):
        coverage = pd.read_csv(
            self.p / "equity_market_coverage.csv", parse_dates=["first_date", "last_date"]
        )
        a = pd.read_csv(self.p / "universe_rebalance_audit.csv", parse_dates=["signal_date"])
        table(
            pd.DataFrame(
                {
                    "Measure": [
                        "Observed EQ symbols",
                        "Observed security-days",
                        "First archive date",
                        "Last archive date",
                        "First strategy signal",
                    ],
                    "Value": [
                        len(coverage),
                        int(coverage.observations.sum()),
                        coverage.first_date.min().date(),
                        coverage.last_date.max().date(),
                        a.signal_date.min().date(),
                    ],
                }
            ),
            "Archive versus effective research sample",
        )
        note(
            "A traded symbol is not necessarily a distinct issuer. The strategy sample starts later than the archive because the liquid-fund reference and formation history are both required. Disappearance from one monthly file does not prove delisting."
        )
        q = a[a.formation_period == "12M"]
        fig = go.Figure()
        for c, label in [
            ("price_history_eligible", "Price-history eligible"),
            ("eligible_before_liquidity_cut", "Strategy quality universe"),
            ("selected_liquidity_universe", "5% MDTV capacity diagnostic, N=24"),
        ]:
            fig.add_trace(go.Scatter(x=q.signal_date, y=q[c], name=label))
        fig.update_yaxes(title="Eligible securities")
        chart(fig, "Point-in-time eligibility funnel", slider=True)
        lows = q.nsmallest(3, "selected_liquidity_universe")
        table(
            lows[
                [
                    "signal_date",
                    "price_history_eligible",
                    "excluded_unresolved_price_jump",
                    "eligible_before_liquidity_cut",
                    "selected_liquidity_universe",
                ]
            ],
            "Three smallest capacity-diagnostic observations",
        )
        note(
            "These rows locate the exact lows and show which quality gates operated there. The chart does not label the full-history union of symbols as the number actually listed on each date."
        )
        c = pd.read_csv(self.p / "universe_capacity_by_n_rebalance.csv")
        table(
            c.groupby("holdings_n")
            .agg(
                MDTV_INR=("required_mdtv_inr", "first"),
                minimum_names=("capacity_eligible_symbols", "min"),
                median_names=("capacity_eligible_symbols", "median"),
                maximum_names=("capacity_eligible_symbols", "max"),
            )
            .reset_index(),
            "Absolute capacity thresholds",
        )
        note(
            "The INR 1 crore and 5% of trailing 126-session MDTV calculation is a capacity diagnostic, not a strategy-selection rule. Its reference thresholds are INR 1.67 crore, INR 83.33 lakh and INR 40 lakh for N=12, 24 and 50. The principal backtest is a one-shot research fill and therefore should not be interpreted as executable at that capital for names below these levels."
        )
        actions = pd.read_csv(self.p / "corporate_action_price_reconciliation.csv")
        table(
            pd.DataFrame(
                {
                    "Result": ["Events checked", "Within tolerance", "Flagged"],
                    "Count": [
                        len(actions),
                        int(actions.within_25_percent_of_expected.sum()),
                        int((~actions.within_25_percent_of_expected).sum()),
                    ],
                }
            ),
            "Corporate-action price reconciliation",
        )
        note(
            "Split, bonus and consolidation factors are applied to OHLC. The 25% event tolerance is a quality check, not proof of exact adjustment; flagged events and symbol/ISIN ambiguity remain limitations. Dividends are excluded."
        )

    def costs(self):
        from .costs import delivery_trade_cost

        bridge = delivery_trade_cost(1e6, 1.1e6, buy_orders=1, sell_orders=1, sold_isins=1)
        table(
            pd.DataFrame({"Charge": list(bridge), "INR": list(bridge.values())}),
            "INR 10 lakh buy and INR 11 lakh sale — one order each",
        )
        note(
            f"STT is INR {bridge['stt']:,.2f}. The full modeled charge is INR {bridge['total']:,.2f}, including DP debit and its GST. The screenshot calculator excluded DP; its INR 2,375.75 becomes INR 2,390.50 including INR 14.75 DP plus GST."
        )
        h = pd.read_csv(
            self.root / "data/reference/trading_cost_history.csv", parse_dates=["effective_from"]
        ).sort_values("effective_from")
        for kind, mask in [
            ("Delivery STT", h.component.eq("STT")),
            ("Service tax / GST history", h.segment.eq("broker_services")),
        ]:
            q = h[mask]
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=q.effective_from,
                    y=q.buy_rate / 100,
                    mode="lines+markers",
                    line_shape="hv",
                    name=kind,
                )
            )
            fig.update_yaxes(title="Rate", tickformat=".1%")
            chart(fig, kind)
            note(
                "The STT line is used as a dated input in every delivery trade. Other fee and GST histories are context: non-STT charges use the single stated current-cost backcast."
                if kind == "Delivery STT"
                else "Service tax and GST changed historically. This study does not present the current 18% GST backcast as the rate actually charged before July 2017."
            )
        q = pd.read_csv(
            self.root / "data/tax_rules/equity_capital_gains.csv", parse_dates=["effective_from"]
        )
        q = q[pd.to_numeric(q.tax_rate, errors="coerce").notna()]
        fig = go.Figure()
        for name, g in q.groupby("holding_class"):
            fig.add_trace(
                go.Scatter(
                    x=g.effective_from, y=pd.to_numeric(g.tax_rate), name=name, line_shape="hv"
                )
            )
        fig.update_yaxes(title="Headline rate", tickformat=".0%")
        chart(fig, "Listed-equity capital-gains rates")
        note(
            "Headline rates do not equal the tax paid on every sale: FIFO holding age, annual net gains, exemptions, grandfathering and cess also enter the simplified ledger."
        )
        m = self.metrics[self.metrics.strategy != "jt_academic"].pivot(
            index=KEYS, columns="return_type", values="cagr"
        )
        table(
            pd.DataFrame(
                {
                    "Layer": [
                        "Average raw-minus-after-cost CAGR",
                        "Average after-cost-minus-post-tax CAGR",
                    ],
                    "Percentage points": [
                        100 * (m.raw - m.gross).mean(),
                        100 * (m.gross - m.post_tax).mean(),
                    ],
                }
            ),
            "Matched return drag",
        )
        note(
            "Tax is an annual portfolio overlay built from FIFO gross-path realizations. It includes eight-year equity-loss carryforwards and keeps fixed rupee exemptions unscaled; it excludes liquid-fund realization tax, surcharge and investor-specific adjustments. The incomplete final financial year is accrued at sample end."
        )

    def findings(self):
        matched = self.comparison_figures()
        q = matched[matched.strategy.ne("jt_academic")]
        avg = (
            q.groupby("strategy")[
                ["cagr", "sharpe", "maximum_drawdown", "monthly_var_95", "monthly_es_95"]
            ]
            .mean()
            .reset_index()
        )
        avg.strategy = avg.strategy.map(LABELS)
        table(avg, "Mean post-tax statistics across matched long-only cells")
        recovery = (
            q.groupby("strategy")[["time_below_prior_peak", "longest_underwater_trading_days"]]
            .mean()
            .reset_index()
        )
        recovery.strategy = recovery.strategy.map(LABELS)
        table(recovery, "Average recovery burden across the same cells")
        note(
            "The mean longest episode is an average across portfolios, not one continuous combined episode. Time underwater measures waiting for a previous peak to be recovered; it does not count negative days."
        )
        for strategy in ["vol_adjusted", "jensen_alpha", "km_momentum"]:
            raw = q[q.strategy == "raw_momentum"].set_index(KEYS[1:])
            own = q[q.strategy == strategy].set_index(KEYS[1:])
            delta = (own.cagr - raw.cagr).mean()
            hit = (own.sharpe > raw.sharpe).mean()
            note(
                f"{LABELS[strategy]} versus Raw Momentum: mean CAGR difference {delta:+.2%}; higher Sharpe in {hit:.0%} of matched cells; mean drawdown difference {(own.maximum_drawdown - raw.maximum_drawdown).mean():+.2%}.",
                "positive" if delta > 0 else "negative",
            )
        for dim, order in [
            ("formation_period", ["6M", "12M"]),
            ("frequency", FREQS),
            ("holdings_n", [12, 24, 50]),
            ("maintenance", ["equal_weight", "winner_drift"]),
        ]:
            s = (
                q.groupby(dim)[["cagr", "sharpe", "maximum_drawdown", "monthly_var_95"]]
                .mean()
                .reindex(order)
            )
            table(s.reset_index(), f"Matched grid summary: {NAMES[dim]}")
            note(
                f"{s.sharpe.idxmax()} has the highest average Sharpe ({s.sharpe.max():.2f}) in this dimension. These balanced averages cover the same other settings and shared measurement dates; individual portfolios can show the opposite ordering."
            )
        j = matched[matched.strategy.eq("jt_academic")]
        table(
            j.groupby(["formation_period", "maintenance"])[["cagr", "sharpe", "maximum_drawdown"]]
            .mean()
            .reset_index(),
            "Academic factor at the 6% borrowing assumption",
        )
        note(
            f"{int(j.cagr.gt(0).sum())}/{len(j)} academic cells have positive compound returns. They include collateral/cash earnings and therefore do not by themselves prove a pure winner-minus-loser alpha."
        )
        note(
            f"{int(q.cagr.gt(0).sum())}/{len(q)} long-only cells remain positive after the modeled tax overlay. This is evidence about the observed sample and stated assumptions, not proof of a behavioral cause. No holdout test or multiple-testing correction is claimed."
        )

    def comparison_figures(self):
        daily = pd.read_parquet(self.p / "backtest_daily.parquet")
        nav = (
            pd.read_csv(self.p / "absl_liquid_fund_continuous.csv", parse_dates=["date"])
            .set_index("date")
            .continuous_nav
        )
        dates = pd.DatetimeIndex(sorted(pd.to_datetime(daily.date).unique()))
        # Include the preceding market session so the first comparison return
        # has the same reference convention as the backtest.
        reference = (
            nav.reindex(nav.index.union(self.benchmark.index))
            .sort_index()
            .ffill()
            .reindex(self.benchmark.index)
            .pct_change(fill_method=None)
        )
        if not dates.isin(reference.index).all():
            raise ValueError("Benchmark calendar is missing valuation sessions")
        q = comparison_metrics(daily, reference)
        if len(q) != 180 or q.duplicated(KEYS).any():
            raise ValueError("Expected 180 unique strategy configurations")
        q.to_csv(self.tables / "matched_strategy_comparison.csv", index=False)
        note(
            f"All 180 portfolios are measured from {q.start_date.min():%d %b %Y} to {q.end_date.max():%d %b %Y}, rebased at the start of this shared measurement window. Holdings retain their actual earlier history. Long-only results include the tax overlay. JT* is an academic long-short reference with 6% annual borrowing, not a taxable executable alternative."
        )
        strategies = ["raw_momentum", "vol_adjusted", "jensen_alpha", "km_momentum", "jt_academic"]
        names = ["Raw", "Vol-adjusted", "Jensen alpha", "KM", "JT* academic"]
        settings = [(f, m) for f in FREQS for m in ["equal_weight", "winner_drift"]]
        x = [f"{f} {'EW' if m == 'equal_weight' else 'WD'}" for f, m in settings]
        specs = [(lookback, n) for lookback in ["6M", "12M"] for n in [12, 24, 50]]
        families = [
            ("Return", ["cagr"]),
            (
                "Risk",
                [
                    "maximum_drawdown",
                    "average_drawdown",
                    "annualized_volatility",
                    "monthly_var_95",
                    "time_below_prior_peak",
                    "longest_underwater_trading_days",
                ],
            ),
            ("Risk-adjusted return", ["sharpe", "calmar"]),
        ]
        for family, metrics in families:
            fig = make_subplots(
                rows=2,
                cols=3,
                subplot_titles=[f"{f} lookback · {n} stocks" for f, n in specs],
                horizontal_spacing=0.10,
                vertical_spacing=0.20,
            )
            buttons = []
            for k, metric in enumerate(metrics):
                is_pct = metric in PERCENT
                lo, hi = q[metric].min(), q[metric].max()
                low_better = family == "Risk" and metric not in [
                    "maximum_drawdown",
                    "average_drawdown",
                ]
                for i, (formation, n) in enumerate(specs):
                    part = q.loc[q.formation_period.eq(formation) & q.holdings_n.eq(n)].set_index(
                        ["strategy", "frequency", "maintenance"]
                    )
                    z = [
                        [float(part.loc[(s, f, m), metric]) for f, m in settings]
                        for s in strategies
                    ]
                    text = [
                        [
                            f"{v:.1%}"
                            if is_pct
                            else f"{v:.2f}"
                            if metric != "longest_underwater_trading_days"
                            else f"{v:.0f}"
                            for v in row
                        ]
                        for row in z
                    ]
                    fig.add_trace(
                        go.Heatmap(
                            x=x,
                            y=names,
                            z=z,
                            text=text,
                            texttemplate="%{text}",
                            textfont=dict(size=10),
                            zmin=lo,
                            zmax=hi,
                            colorscale="RdYlGn_r" if low_better else "RdYlGn",
                            showscale=i == 5,
                            colorbar=dict(
                                title=NAMES[metric],
                                tickformat=".0%" if is_pct else ".1f",
                                len=0.75,
                                thickness=12,
                            ),
                            visible=k == 0,
                            hovertemplate=f"{formation} · N={n}<br>%{{y}} · %{{x}}<br>{NAMES[metric]}: %{{text}}<extra></extra>",
                        ),
                        row=i // 3 + 1,
                        col=i % 3 + 1,
                    )
                buttons.append(
                    dict(
                        label=NAMES[metric],
                        method="update",
                        args=[{"visible": [j // 6 == k for j in range(6 * len(metrics))]}],
                    )
                )
            fig.update_yaxes(autorange="reversed", tickfont=dict(size=10))
            fig.update_xaxes(tickangle=-35, tickfont=dict(size=10))
            fig.update_layout(
                width=1180,
                height=760,
                template="plotly_white",
                title=dict(text=f"{family} across every configuration", x=0.04),
                margin=dict(l=100, r=180, t=140, b=65),
                updatemenus=[dict(buttons=buttons, x=0.60, y=1.16, xanchor="left", yanchor="top")]
                if len(metrics) > 1
                else [],
            )
            fig.show(config={"responsive": False, "displaylogo": False})
            note(
                "Each tile is one portfolio, not an average. Columns pair rebalance frequency with EW (equal-weight reset) or WD (winner drift); rows identify the strategy. The same color scale applies to all six panels for the selected metric. Green denotes the favorable direction, not statistical significance."
            )
            leaders = q.loc[q.strategy.ne("jt_academic")].groupby("strategy")[metrics[0]].mean()
            best = (
                leaders.idxmin()
                if family == "Risk" and metrics[0] not in ["maximum_drawdown", "average_drawdown"]
                else leaders.idxmax()
            )
            value = f"{leaders[best]:.1%}" if metrics[0] in PERCENT else f"{leaders[best]:.2f}"
            note(
                f"{LABELS[best]} has the best mean {NAMES[metrics[0]]} across its 36 matched long-only configurations ({value}). This summarizes separate portfolios; it is not the performance of a combined fund."
            )
        note(
            "Mean daily drawdown averages the distance below the running peak over all sessions, including peaks at zero. Time underwater is the fraction below that peak, not the fraction of loss-making days. VaR is the historical 95% monthly loss quantile; partial boundary months are included. Calmar is CAGR divided by maximum drawdown magnitude. Sharpe uses daily excess returns over the liquid-fund proxy. No arbitrary risk/reward score is used."
        )
        display(
            HTML(
                "<p><a href='../reports/tables/matched_strategy_comparison.csv'>All 180 matched configurations and metrics (CSV)</a></p>"
            )
        )
        return q
