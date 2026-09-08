import { useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { NativeSelect } from '@/components/ui/native-select';
import {
  ArrowLeft,
  ArrowRight,
  Download,
  Search,
  ArrowUpRight,
  BarChart3,
  Layers3,
} from 'lucide-react';
import StockChart from './StockChart';
import Performance from './Performance';
import PositionDetails from './PositionDetails';
import CsvLink from './CsvLink';
import {
  strategies,
  pct,
  number,
  compact,
  date,
  layerNames,
  rupee,
  experimentLabel,
} from './utils';
import type { Experiment, Manifest, PriceData } from './types';

const cache = new Map<string, unknown>();
function useData<T>(path: string | null) {
  const [state, setState] = useState<{
    path: string | null;
    data: T | null;
    error: string;
  }>({ path: null, data: null, error: '' });
  useEffect(() => {
    if (!path) return;
    let active = true;
    const controller = new AbortController();
    if (cache.has(path)) {
      setState({ path, data: cache.get(path) as T, error: '' });
      return;
    }
    setState({ path, data: null, error: '' });
    fetch(path, { signal: controller.signal })
      .then(async (r) => {
        if (!r.ok) throw Error(`Saved data unavailable (${r.status}).`);
        if (path.endsWith('.gz')) {
          const bytes = new Uint8Array(await r.arrayBuffer());
          if (bytes[0] === 31 && bytes[1] === 139) {
            if (typeof DecompressionStream === 'undefined')
              throw Error(
                'This browser cannot read the compressed research files. A current browser is required.',
              );
            return new Response(
              new Blob([bytes])
                .stream()
                .pipeThrough(new DecompressionStream('gzip')),
            ).json();
          }
          return JSON.parse(new TextDecoder().decode(bytes));
        }
        return r.json();
      })
      .then((data) => {
        if (!active) return;
        cache.set(path, data);
        if (cache.size > 18) cache.delete(cache.keys().next().value!);
        setState({ path, data: data as T, error: '' });
      })
      .catch((e) => {
        if (active && e.name !== 'AbortError')
          setState({ path, data: null, error: e.message });
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [path]);
  return {
    data: state.path === path ? state.data : null,
    error: state.path === path ? state.error : '',
  };
}
function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: [string, string][];
}) {
  return (
    <label className="filter-label">
      {label}
      <NativeSelect
        aria-label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map(([v, name]) => (
          <option key={v} value={v}>
            {name}
          </option>
        ))}
      </NativeSelect>
    </label>
  );
}
function Metric({
  label,
  value,
  help,
}: {
  label: string;
  value: string;
  help: string;
}) {
  return (
    <div title={help}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{help}</small>
    </div>
  );
}

export default function App() {
  const { data: manifest, error: manifestError } = useData<Manifest>(
    './data/manifest.json',
  );
  const [selection, setSelection] = useState({
    strategy: 'raw_momentum',
    formation_period: '12M',
    frequency: '1M',
    holdings_n: '24',
    maintenance: 'equal_weight',
  });
  const [view, setView] = useState('portfolio');
  const [rebalance, setRebalance] = useState(0);
  const [stock, setStock] = useState('');
  const [search, setSearch] = useState('');
  const [showAll, setShowAll] = useState(false);
  const [sort, setSort] = useState('rank');
  const summary = manifest?.experiments.find(
    (e) =>
      e.strategy === selection.strategy &&
      e.formation_period === selection.formation_period &&
      e.frequency === selection.frequency &&
      String(e.holdings_n) === selection.holdings_n &&
      e.maintenance === selection.maintenance,
  );
  const { data: experiment, error: experimentError } = useData<Experiment>(
    summary ? './data/experiments/' + summary.id + '.json.gz' : null,
  );
  const { data: prices, error: priceError } = useData<PriceData>(
    stock ? './data/stocks/' + stock + '.json.gz' : null,
  );
  const snapshot =
    experiment?.snapshots[Math.min(rebalance, experiment.snapshots.length - 1)];
  const security = manifest?.securities[stock];
  const selectedHolding = snapshot?.holdings.find((h) => h.id === stock);
  const position = experiment?.positions[stock];
  const finalLayer = summary?.academic ? 'academic_borrow_6pct' : 'post_tax';
  const metric = summary?.metrics[finalLayer];
  useEffect(() => {
    if (!snapshot) return;
    if (!stock || (!showAll && !snapshot.holdings.some((h) => h.id === stock)))
      setStock(snapshot.holdings[0]?.id ?? '');
  }, [snapshot, stock, showAll]);
  function change(key: string, value: string) {
    setSelection((s) => ({ ...s, [key]: value }));
    setStock('');
    setRebalance(0);
    setSearch('');
    setShowAll(false);
  }
  const holdings = useMemo(() => {
    if (!snapshot || !manifest) return [];
    return snapshot.holdings
      .filter((h) => {
        const s = manifest.securities[h.id];
        return `${s.ticker} ${s.name}`
          .toLowerCase()
          .includes(search.toLowerCase());
      })
      .sort((a, b) =>
        sort === 'weight'
          ? Math.abs(b.weight) - Math.abs(a.weight)
          : sort === 'name'
            ? manifest.securities[a.id].ticker.localeCompare(
                manifest.securities[b.id].ticker,
              )
            : a.leg.localeCompare(b.leg) || a.rank - b.rank,
      );
  }, [snapshot, manifest, search, sort]);
  const scope = summary?.academic
    ? 'Academic long–short'
    : 'Long-only strategies';
  return (
    <main>
      <header>
        <div className="brand">
          M<span>↗</span>
        </div>
        <div>
          <h1>
            Momentum <span>/ Research explorer</span>
          </h1>
          <p>
            Indian equities · ₹1 crore initial capital · Through 28 Aug 2026
          </p>
        </div>
        <span className="badge">
          <span className="status-dot" /> CACHED RESEARCH
        </span>
      </header>
      <nav className="main-nav" aria-label="Dashboard views">
        {[
          ['portfolio', 'Portfolio explorer'],
          ['performance', 'Performance'],
          ['notes', 'Study notes'],
        ].map(([v, label]) => (
          <Button
            key={v}
            variant="ghost"
            className={view === v ? 'active' : ''}
            onClick={() => setView(v)}
          >
            {v === 'portfolio' ? (
              <Layers3 size={16} />
            ) : v === 'performance' ? (
              <BarChart3 size={16} />
            ) : null}
            {label}
          </Button>
        ))}
        <span>
          {manifest?.experiments.length ?? '…'} saved experiments · No live
          orders
        </span>
      </nav>
      <section className="surface filter-surface">
        <div className="scope-row">
          <div className="scope-tabs">
            <button
              className={selection.strategy !== 'jt_academic' ? 'chosen' : ''}
              onClick={() => {
                if (selection.strategy === 'jt_academic')
                  change('strategy', 'raw_momentum');
              }}
            >
              Long-only
            </button>
            <button
              className={selection.strategy === 'jt_academic' ? 'chosen' : ''}
              onClick={() => change('strategy', 'jt_academic')}
            >
              Academic long–short
            </button>
          </div>
          <span className="tiny muted">
            {summary
              ? `${date(summary.start)} — ${date(summary.end)}`
              : 'Loading saved research…'}
          </span>
        </div>
        <div className="filters">
          <Select
            label="Strategy"
            value={selection.strategy}
            onChange={(v) => change('strategy', v)}
            options={Object.entries(strategies).filter(([k]) =>
              selection.strategy === 'jt_academic'
                ? k === 'jt_academic'
                : k !== 'jt_academic',
            )}
          />
          <Select
            label="Momentum lookback"
            value={selection.formation_period}
            onChange={(v) => change('formation_period', v)}
            options={['6M', '12M'].map((v) => [
              v,
              v === '6M' ? '6 months' : '12 months',
            ])}
          />
          <Select
            label="Portfolio size"
            value={selection.holdings_n}
            onChange={(v) => change('holdings_n', v)}
            options={['12', '24', '50'].map((v) => [
              v,
              `${v} ${selection.strategy === 'jt_academic' ? 'total stocks' : 'stocks'}`,
            ])}
          />
          <Select
            label="Rebalance every"
            value={selection.frequency}
            onChange={(v) => change('frequency', v)}
            options={['1M', '3M', '6M'].map((v) => [
              v,
              v === '1M' ? '1 month' : v === '3M' ? '3 months' : '6 months',
            ])}
          />
          <Select
            label="Allocation"
            value={selection.maintenance}
            onChange={(v) => change('maintenance', v)}
            options={['equal_weight', 'winner_drift'].map((v) => [
              v,
              v === 'equal_weight' ? 'Equal weight' : 'Winner drift · 2/N cap',
            ])}
          />
        </div>
      </section>
      {manifestError && (
        <div role="alert" className="error surface">
          {manifestError}
        </div>
      )}
      {manifest && !summary && (
        <output className="surface muted">
          This experiment’s export is not available yet.
        </output>
      )}
      {experimentError && (
        <div role="alert" className="error surface">
          {experimentError}
        </div>
      )}
      {metric && (
        <div className="metrics summary-metrics">
          <Metric
            label="CAGR"
            value={pct(metric.cagr)}
            help={layerNames[finalLayer]}
          />
          <Metric
            label="Sharpe ratio"
            value={number(metric.sharpe)}
            help="Daily liquid-fund excess return"
          />
          <Metric
            label="Maximum drawdown"
            value={pct(metric.maximum_drawdown)}
            help="Worst decline from a prior peak"
          />
          <Metric
            label="Monthly 95% VaR"
            value={pct(metric.monthly_var_95)}
            help="Historical monthly loss threshold"
          />
          <Metric
            label="Time underwater"
            value={pct(metric.time_below_prior_peak)}
            help="Sessions below a prior wealth peak"
          />
          <Metric
            label="Longest underwater"
            value={number(metric.longest_underwater_trading_days, 0)}
            help="Consecutive trading sessions"
          />
        </div>
      )}
      {summary && !experiment && !experimentError && (
        <output className="surface loading">
          Loading this experiment’s saved portfolios and trades…
        </output>
      )}
      {view === 'portfolio' && experiment && snapshot && manifest && (
        <>
          <section className="surface rebalance-strip">
            <div>
              <div className="eyebrow">POINT-IN-TIME PORTFOLIO</div>
              <h2>
                Rebalance {rebalance + 1}{' '}
                <span>of {experiment.snapshots.length}</span>
              </h2>
              <p className="muted">
                Signals: {date(snapshot.signal_date)} · Holdings after the
                opening trades
              </p>
            </div>
            <div className="rebalance-controls">
              <Button
                variant="outline"
                aria-label="Previous rebalance"
                disabled={rebalance === 0}
                onClick={() => {
                  setRebalance(rebalance - 1);
                  setShowAll(false);
                }}
              >
                <ArrowLeft />
              </Button>
              <NativeSelect
                aria-label="Rebalance date"
                value={rebalance}
                onChange={(e) => {
                  setRebalance(+e.target.value);
                  setShowAll(false);
                  setSearch('');
                }}
              >
                {experiment.snapshots.map((s, i) => (
                  <option key={s.date} value={i}>
                    {String(i + 1).padStart(3, '0')} · {date(s.date)}
                  </option>
                ))}
              </NativeSelect>
              <Button
                variant="outline"
                aria-label="Next rebalance"
                disabled={rebalance === experiment.snapshots.length - 1}
                onClick={() => {
                  setRebalance(rebalance + 1);
                  setShowAll(false);
                }}
              >
                <ArrowRight />
              </Button>
              <CsvLink
                label="Export selected portfolio"
                filename={
                  experiment.id + '-' + snapshot.date + '-portfolio.csv'
                }
                rows={[
                  ...snapshot.holdings.map((h) => ({
                    execution_date: snapshot.date,
                    signal_date: snapshot.signal_date,
                    symbol: manifest.securities[h.id].symbol,
                    company: manifest.securities[h.id].name,
                    ...h,
                  })),
                  {
                    execution_date: snapshot.date,
                    signal_date: snapshot.signal_date,
                    symbol: 'CASH',
                    value: snapshot.cash,
                    weight: snapshot.cash / snapshot.capital,
                  },
                ]}
              >
                <Download />
              </CsvLink>
            </div>
          </section>
          <div className="explorer-grid">
            <section className="surface portfolio-panel">
              <div className="section-heading">
                <div>
                  <div className="eyebrow">HOLDINGS AT THIS REBALANCE</div>
                  <h2>{snapshot.holdings.length} positions</h2>
                </div>
                <span className="pill">{scope}</span>
              </div>
              <div className="portfolio-summary">
                <div>
                  <span>Portfolio value</span>
                  <b>{compact(snapshot.capital)}</b>
                </div>
                <div>
                  <span>Cash · {pct(snapshot.cash / snapshot.capital)}</span>
                  <b>{compact(snapshot.cash)}</b>
                </div>
              </div>
              <div className="search-row">
                <label className="search-box">
                  <Search size={15} />
                  <input
                    aria-label="Search portfolio stocks"
                    placeholder="Find a stock…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                </label>
                <NativeSelect
                  aria-label="Sort portfolio"
                  value={sort}
                  onChange={(e) => setSort(e.target.value)}
                >
                  <option value="rank">Rank</option>
                  <option value="weight">Weight</option>
                  <option value="name">Name</option>
                </NativeSelect>
              </div>
              <div className="portfolio-list">
                <div className="holding-head">
                  <span>Stock / signal rank</span>
                  <span>Weight / change</span>
                </div>
                {holdings.map((h) => (
                  <button
                    key={h.id}
                    aria-label={`Open ${manifest.securities[h.id].ticker} history`}
                    className={'holding ' + (stock === h.id ? 'selected' : '')}
                    onClick={() => {
                      setStock(h.id);
                      setShowAll(false);
                    }}
                  >
                    <span>
                      <b>{manifest.securities[h.id].ticker}</b>
                      <small>
                        #{h.rank} {h.leg === 'short' ? '· Short' : ''} ·{' '}
                        {manifest.securities[h.id].name}
                      </small>
                    </span>
                    <span>
                      <b>{pct(h.weight, 2)}</b>
                      <small className={h.status === 'new' ? 'positive' : ''}>
                        {h.status}
                      </small>
                    </span>
                  </button>
                ))}
                {!holdings.length && (
                  <p className="empty">
                    {snapshot.holdings.length
                      ? 'No stock matches this search.'
                      : 'No qualifying holdings. The portfolio is in cash.'}
                  </p>
                )}
              </div>
              <p className="caption">
                Actual after-cost weights, not nominal targets. Rank is within
                the selected leg.{' '}
                {selection.maintenance === 'winner_drift'
                  ? 'Continuing winners drift; the concentration cap is checked at scheduled rebalances.'
                  : 'Positions are equal-weighted at the scheduled rebalance.'}
              </p>
              <details>
                <summary>Selection & turnover</summary>
                <p className="caption">
                  {snapshot.eligible} capacity-eligible stocks. Minimum trailing
                  median daily traded value: {compact(snapshot.threshold)}.
                  Two-way turnover: {pct(snapshot.turnover)}. Trading charges at
                  this rebalance: {rupee(snapshot.fees)}.
                </p>
              </details>
              <details>
                <summary>
                  Closed since the previous rebalance (
                  {snapshot.departures.length})
                </summary>
                {snapshot.departures.length ? (
                  snapshot.departures.map((d, i) => (
                    <button
                      key={i}
                      className="departure"
                      onClick={() => {
                        setStock(d.id);
                        setShowAll(true);
                      }}
                    >
                      <b>{manifest.securities[d.id].ticker}</b>
                      <span>
                        {date(d.date)} ·{' '}
                        {d.reason === 'km_daily_stop'
                          ? 'Daily stop'
                          : 'Rebalance exit'}
                      </span>
                      <ArrowUpRight size={14} />
                    </button>
                  ))
                ) : (
                  <p className="caption">
                    No position closed during this interval.
                  </p>
                )}
              </details>
            </section>
            <section className="surface stock-panel">
              <div className="section-heading">
                <div>
                  <div className="eyebrow">
                    STOCK HISTORY · THIS EXACT EXPERIMENT
                  </div>
                  <h2>
                    {security?.ticker ?? 'Stock explorer'}{' '}
                    <span>
                      {security?.name !== security?.symbol
                        ? security?.name
                        : ''}
                    </span>
                  </h2>
                  <p className="caption">{experimentLabel(experiment)}</p>
                </div>
                <span className="pill">FULL HISTORY</span>
              </div>
              <div className="history-selector">
                <label>
                  Any stock traded in this experiment
                  <NativeSelect
                    aria-label="Stock history selector"
                    value={stock}
                    onChange={(e) => {
                      setStock(e.target.value);
                      setShowAll(true);
                    }}
                  >
                    <option value="">Select a stock</option>
                    {Object.keys(experiment.positions)
                      .sort((a, b) =>
                        manifest.securities[a].ticker.localeCompare(
                          manifest.securities[b].ticker,
                        ),
                      )
                      .map((id) => (
                        <option key={id} value={id}>
                          {manifest.securities[id].ticker} ·{' '}
                          {manifest.securities[id].name}
                        </option>
                      ))}
                  </NativeSelect>
                </label>
              </div>
              {selectedHolding && (
                <div className="holding-detail">
                  <span>At selected rebalance</span>
                  <b>{pct(selectedHolding.weight, 2)} weight</b>
                  <b>{compact(selectedHolding.value)}</b>
                  <span>
                    {number(selectedHolding.quantity, 4)} adjusted shares
                  </span>
                  <span>Signal {number(selectedHolding.signal, 4)}</span>
                </div>
              )}
              {stock && !snapshot.holdings.some((h) => h.id === stock) && (
                <p className="notice">
                  This stock is not held at the selected rebalance. Its trades
                  elsewhere in this experiment remain visible.
                </p>
              )}
              {security?.multiple_isins && (
                <p className="notice">
                  This symbol has multiple recorded ISINs. Corporate actions or
                  identity changes may affect continuity; the chart preserves
                  the research dataset’s symbol mapping.
                </p>
              )}
              {priceError && (
                <p role="alert" className="error">
                  {priceError}
                </p>
              )}
              {stock && !prices && !priceError && (
                <output className="loading">
                  Loading full cached stock history…
                </output>
              )}
              {prices && position ? (
                <StockChart
                  key={experiment.id + '-' + stock}
                  prices={prices}
                  position={position}
                  selectedDate={snapshot.date}
                  stockId={stock}
                  km={experiment.strategy === 'km_momentum'}
                />
              ) : !stock ? (
                <div className="empty chart-empty">
                  Select a holding or a stock from the experiment’s history.
                </div>
              ) : null}
            </section>
          </div>
          <section className="surface">
            <details>
              <summary>
                Complete portfolio · {snapshot.holdings.length} stocks ·{' '}
                {date(snapshot.date)}
              </summary>
              <p className="caption">
                {experimentLabel(experiment)}. Holdings immediately after
                scheduled execution, before the annual tax overlay. Quantities
                and values use the adjusted-price basis; cash includes the
                liquid-cash sleeve.
              </p>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Stock / leg</th>
                      <th>Rank / score</th>
                      <th>Adjusted quantity</th>
                      <th>Allocation</th>
                      <th>Actual weight</th>
                      <th>Change</th>
                    </tr>
                  </thead>
                  <tbody>
                    {snapshot.holdings.map((h) => (
                      <tr key={h.id}>
                        <td>
                          <button
                            className="text-button"
                            onClick={() => {
                              setStock(h.id);
                              setShowAll(true);
                            }}
                          >
                            {manifest.securities[h.id].ticker}
                          </button>
                          <small>{h.leg}</small>
                        </td>
                        <td>
                          {h.rank}
                          <small>{number(h.signal, 4)}</small>
                        </td>
                        <td>{number(h.quantity, 4)}</td>
                        <td>{rupee(h.value)}</td>
                        <td>{pct(h.weight, 2)}</td>
                        <td>{h.status}</td>
                      </tr>
                    ))}
                    <tr>
                      <td>Cash</td>
                      <td>—</td>
                      <td>—</td>
                      <td>{rupee(snapshot.cash)}</td>
                      <td>{pct(snapshot.cash / snapshot.capital, 2)}</td>
                      <td>Residual balance</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </details>
          </section>
          {position && security && (
            <PositionDetails
              key={experiment.id + '-' + stock}
              position={position}
              academic={experiment.academic}
              filename={experiment.id + '-' + security.ticker}
              context={experimentLabel(experiment) + ' · ' + security.ticker}
            />
          )}
        </>
      )}
      {view === 'performance' && experiment && (
        <Performance key={experiment.id} experiment={experiment} />
      )}
      {view === 'notes' && (
        <section className="surface study-notes">
          <div className="eyebrow">SCOPE & DEFINITIONS</div>
          <h2>A viewing layer over the completed study.</h2>
          <div className="explanation-grid">
            <article>
              <h3>Universe and portfolios</h3>
              <p>
                The point-in-time NSE equity universe uses observed main-board
                trading and data-quality gates. MDTV capacity is reported as a
                diagnostic rather than used to alter strategy ranks. Six- and
                twelve-month lookbacks, 12/24/50-stock concentrations,
                monthly/quarterly/semi-annual rebalances, and
                equal-weight/winner-drift allocations remain separate
                experiments. The selected stock’s entire recorded history is
                shown, not just prices known at the selected rebalance.
              </p>
              <h3>KM momentum</h3>
              <p>
                Quality-eligible stocks must be at least 3% above EMA 100 and
                have bullish Supertrend 10–3 before momentum selection. A daily
                close below EMA 100 or a bearish Supertrend triggers a next-open
                exit. Proceeds remain in the liquid-cash sleeve until the next
                scheduled rebalance.
              </p>
              <h3>Academic reference</h3>
              <p>
                Jegadeesh–Titman is displayed separately as a long–short
                reference. Its position histories use the 6% annual borrowing
                scenario. Portfolio size counts both legs together: 12 means six
                long and six short stocks. Borrowing is charged to each short
                position using the same daily notional and calendar-day
                convention as the saved simulation. It is not an execution
                model.
              </p>
            </article>
            <article>
              <h3>Return layers</h3>
              <p>
                Before costs, after trading costs, and the post-tax overlay
                describe different wealth paths. Long-only holdings and stock
                trades follow the after-trading-cost simulation. Tax is
                estimated at portfolio level and is not assigned to individual
                stock episodes.
              </p>
              <h3>Price and profit</h3>
              <p>
                Charts, fill prices and quantities share the backtest’s
                corporate-action-adjusted basis. Entry-to-exit price change
                ignores position size; position profit includes every fill and
                allocated trading charge. Cash-sleeve income is outside stock
                profit. Open positions use their latest cached mark.
              </p>
              <h3>Data boundaries</h3>
              <p>
                The study retains unresolved symbol/ISIN continuity risks.
                Trades require an observed opening price; suspended holdings
                remain at the last observed close until another print. A
                confirmed delisting without a later print is written down to
                zero rather than assigned an invented recovery. Monthly
                experiments begin in May 2007; quarterly and semi-annual
                experiments begin in July 2007. Comparisons use each
                experiment’s own benchmark window.
              </p>
            </article>
          </div>
        </section>
      )}
      <footer>
        <span>Momentum in Indian Equities · Keyur Marolia</span>
        <span>Saved results through 28 Aug 2026 · No broker connection</span>
      </footer>
    </main>
  );
}
