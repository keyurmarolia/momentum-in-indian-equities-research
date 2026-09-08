import { useMemo, useState } from 'react';
import { NativeSelect } from '@/components/ui/native-select';
import Plot from './Plot';
import { aggregatePrices, date, pct, rupee, number } from './utils';
import type { PriceData, Position } from './types';

export default function StockChart({
  prices,
  position,
  selectedDate,
  stockId,
  km,
}: {
  prices: PriceData;
  position: Position;
  selectedDate: string;
  stockId: string;
  km: boolean;
}) {
  const [granularity, setGranularity] = useState('Daily');
  const [mode, setMode] = useState('Line');
  const [log, setLog] = useState(true);
  const [visible, setVisible] = useState<Record<string, boolean>>({
    entry: true,
    exit: true,
    add: false,
    trim: false,
    stop: true,
    labels: false,
    ema: false,
    supertrend: false,
  });
  const ticks = useMemo(() => {
    const values = prices.rows
      .flatMap((r) => [r[3], r[2]])
      .filter((v) => v > 0);
    const lo = Math.min(...values),
      hi = Math.max(...values);
    let out: number[] = [];
    for (
      let e = Math.floor(Math.log10(lo));
      e <= Math.ceil(Math.log10(hi));
      e++
    )
      for (const m of [1, 2, 5]) {
        const v = m * 10 ** e;
        if (v >= lo * 0.8 && v <= hi * 1.2) out.push(v);
      }
    if (out.length > 14)
      out = out.filter(
        (v) => Math.abs(Math.log10(v) - Math.round(Math.log10(v))) < 1e-8,
      );
    return out;
  }, [prices]);
  const data = useMemo(() => {
    const rows = aggregatePrices(prices.rows, granularity),
      x = rows.map((r) => r[0]);
    const traces: Record<string, unknown>[] = [
      mode === 'Candles'
        ? {
            type: 'candlestick',
            x,
            open: rows.map((r) => r[1]),
            high: rows.map((r) => r[2]),
            low: rows.map((r) => r[3]),
            close: rows.map((r) => r[4]),
            name: 'Adjusted OHLC',
            increasing: { line: { color: '#147b70' } },
            decreasing: { line: { color: '#bf6a67' } },
          }
        : {
            type: 'scatter',
            mode: 'lines',
            x,
            y: rows.map((r) => r[4]),
            line: { color: '#315b70', width: 1.5 },
            name: 'Adjusted close',
            hovertemplate: '%{x}<br>Adjusted close ₹%{y:,.2f}<extra></extra>',
          },
    ];
    // Indicators retain their original daily observations, independent of candle aggregation.
    if (km && visible.ema)
      traces.push({
        x: prices.rows.map((r) => r[0]),
        y: prices.rows.map((r) => r[5]),
        mode: 'lines',
        line: { color: '#be974b', width: 1.2 },
        name: 'EMA 100',
        connectgaps: false,
      });
    if (km && visible.supertrend)
      for (const bull of [true, false])
        traces.push({
          x: prices.rows.map((r) => r[0]),
          y: prices.rows.map((r) => (r[7] === bull ? r[6] : null)),
          mode: 'lines',
          line: { color: bull ? '#169e6e' : '#cb5656', width: 1.2 },
          name: bull ? 'Supertrend bullish' : 'Supertrend bearish',
          connectgaps: false,
        });
    const specs: [string, string, string, string][] = [
      ['entry', '#148779', 'triangle-up', 'Entries'],
      ['exit', '#b75052', 'triangle-down', 'Full exits'],
      ['add', '#387cad', 'circle', 'Additions'],
      ['trim', '#b38135', 'diamond', 'Trims'],
      ['stop', '#b34749', 'x', 'Daily stop exits'],
    ];
    for (const [kind, color, symbol, name] of specs) {
      if (!visible[kind]) continue;
      const t = position.trades.filter((t) =>
        kind === 'stop'
          ? t.reason === 'km_daily_stop'
          : t.kind === kind && t.reason !== 'km_daily_stop',
      );
      traces.push({
        type: 'scatter',
        mode: 'markers',
        name,
        x: t.map((t) => t.date),
        y: t.map((t) => t.price),
        marker: {
          color,
          symbol,
          size: kind === 'entry' || kind === 'exit' ? 10 : 8,
          line: { color: '#fff', width: 0.7 },
        },
        text: t.map(
          (t) =>
            `${name} · ${date(t.date)}<br>Fill ${rupee(t.price)} · Qty ${number(t.quantity, 4)}<br>Trade ${rupee(Math.abs(t.value))} · Fees ${rupee(t.fee)}<br>${t.reason === 'km_daily_stop' ? 'Next-open stop execution' : 'Scheduled rebalance'} · Episode ${t.episode + 1}`,
        ),
        hovertemplate: '%{text}<extra></extra>',
      });
    }
    if (visible.labels) {
      const closed = position.episodes.filter((e) => e.exit);
      traces.push({
        mode: 'text',
        x: closed.map((e) => e.exit),
        y: closed.map((e) => e.mark_price),
        text: closed.map((e) => pct(e.price_change)),
        textposition: 'top center',
        textfont: { size: 10, color: '#7a5261' },
        name: 'Entry → exit price change',
        hoverinfo: 'skip',
      });
    }
    return traces;
  }, [prices, position, granularity, mode, visible, km]);
  const layout = useMemo(
    () => ({
      uirevision: stockId + '-' + log,
      xaxis: {
        type: 'date',
        gridcolor: '#edf1f2',
        rangeslider: {
          visible: true,
          thickness: 0.12,
          bgcolor: '#f3f7f7',
          bordercolor: '#dce3e5',
          borderwidth: 1,
        },
        rangeselector: {
          buttons: [
            { count: 1, label: '1Y', step: 'year', stepmode: 'backward' },
            { count: 5, label: '5Y', step: 'year', stepmode: 'backward' },
            { step: 'all', label: 'All history' },
          ],
          font: { size: 10 },
          bgcolor: '#edf3f3',
          activecolor: '#cee5df',
        },
      },
      yaxis: {
        type: log ? 'log' : 'linear',
        ...(log
          ? {
              tickmode: 'array',
              tickvals: ticks,
              ticktext: ticks.map((v) =>
                number(
                  v,
                  v < 1 ? Math.min(6, Math.ceil(-Math.log10(v)) + 1) : 0,
                ),
              ),
            }
          : {}),
        title: { text: 'Adjusted price · ₹', standoff: 8 },
        gridcolor: '#edf1f2',
        fixedrange: false,
      },
      margin: { l: 66, r: 24, t: 42, b: 40 },
      shapes: [
        {
          type: 'line',
          xref: 'x',
          x0: selectedDate,
          x1: selectedDate,
          yref: 'paper',
          y0: 0,
          y1: 1,
          line: { color: '#c65353', width: 1.4, dash: 'dot' },
        },
      ],
      annotations: [
        {
          x: selectedDate,
          xref: 'x',
          y: 1,
          yref: 'paper',
          text: 'Selected rebalance',
          showarrow: false,
          yshift: 10,
          font: { size: 10, color: '#b74848' },
          xanchor: 'center',
        },
      ],
    }),
    [stockId, selectedDate, log, ticks],
  );
  return (
    <>
      <div className="chart-toolbar">
        <label htmlFor="price-granularity">
          Price bars
          <NativeSelect
            id="price-granularity"
            aria-label="Price granularity"
            value={granularity}
            onChange={(e) => setGranularity(e.target.value)}
          >
            {['Daily', 'Weekly', 'Monthly'].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </NativeSelect>
        </label>
        <label htmlFor="chart-style">
          Chart
          <NativeSelect
            id="chart-style"
            aria-label="Chart style"
            value={mode}
            onChange={(e) => setMode(e.target.value)}
          >
            <option>Line</option>
            <option>Candles</option>
          </NativeSelect>
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={log}
            onChange={(e) => setLog(e.target.checked)}
          />
          Log price scale
        </label>
      </div>
      <div className="marker-controls" aria-label="Chart marker controls">
        {[
          ['entry', 'Entries'],
          ['exit', 'Full exits'],
          ['add', 'Additions'],
          ['trim', 'Trims'],
          ...(km
            ? [
                ['stop', 'Stop exits'],
                ['ema', 'EMA 100'],
                ['supertrend', 'Supertrend 10–3'],
              ]
            : []),
          ['labels', 'Episode price changes'],
        ].map(([k, label]) => (
          <label className="check" key={k}>
            <input
              type="checkbox"
              checked={visible[k]}
              onChange={(e) =>
                setVisible({ ...visible, [k]: e.target.checked })
              }
            />
            {label}
          </label>
        ))}
      </div>
      <Plot data={data} layout={layout} id={'stock-' + stockId} height={470} />
      <p className="caption">
        Full cached history; markers belong only to this experiment. The red
        line is the selected rebalance. Fills retain their exact daily dates
        even when price bars are grouped. Prices and quantities use the
        backtest’s adjusted basis.
      </p>
    </>
  );
}
