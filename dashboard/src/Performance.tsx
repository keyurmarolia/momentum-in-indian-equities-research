import { useMemo, useState } from 'react';
import Plot from './Plot';
import {
  colors,
  layerNames,
  pct,
  number,
  date,
  experimentLabel,
} from './utils';
import CsvLink from './CsvLink';
import type { Experiment } from './types';

export default function Performance({
  experiment: e,
}: {
  experiment: Experiment;
}) {
  const primary = e.academic ? 'academic_borrow_6pct' : 'post_tax';
  const [visible, setVisible] = useState<Record<string, boolean>>({
    [primary]: true,
    benchmark: true,
  });
  const [log, setLog] = useState(true);
  const keys = useMemo(
    () =>
      (e.academic
        ? [
            'academic_raw',
            'academic_borrow_3pct',
            'academic_borrow_6pct',
            'academic_borrow_12pct',
            'benchmark',
          ]
        : ['raw', 'gross', 'post_tax', 'benchmark']
      ).filter((k) => k in e.curves),
    [e],
  );
  const data = useMemo(
    () =>
      keys
        .filter((k) => visible[k])
        .map((k) => ({
          type: 'scatter',
          mode: 'lines',
          name: layerNames[k],
          x: e.dates,
          y: e.curves[k],
          line: { color: colors[k], width: k === primary ? 2.3 : 1.5 },
          hovertemplate: `${layerNames[k]}<br>%{x}<br>Wealth %{y:.2f}×<extra></extra>`,
        })),
    [e, visible, keys, primary],
  );
  const layout = useMemo(
    () => ({
      uirevision: e.id + '-' + log,
      hovermode: 'x unified',
      xaxis: {
        type: 'date',
        rangeslider: { visible: true, thickness: 0.11 },
        gridcolor: '#edf1f2',
      },
      yaxis: {
        type: log ? 'log' : 'linear',
        ...(log
          ? {
              tickmode: 'array',
              tickvals: Array.from({ length: 12 }, (_, i) => i - 4).flatMap(
                (p) => [1, 2, 5].map((v) => v * 10 ** p),
              ),
              tickformat: ',.4~g',
            }
          : {}),
        title: { text: 'Wealth · initial capital = 1', standoff: 10 },
        gridcolor: '#edf1f2',
      },
    }),
    [e.id, log],
  );
  const stats: [string, string, boolean][] = [
    ['cagr', 'CAGR', true],
    ['sharpe', 'Sharpe', false],
    ['calmar', 'Calmar · CAGR / maximum loss', false],
    ['maximum_drawdown', 'Max drawdown', true],
    ['average_drawdown', 'Mean daily drawdown', true],
    ['time_below_prior_peak', 'Time underwater', true],
    ['longest_underwater_trading_days', 'Longest underwater · sessions', false],
    ['monthly_var_95', 'Monthly 95% VaR', true],
    ['monthly_es_95', 'Monthly 95% ES', true],
  ];
  return (
    <section className="surface">
      <div className="section-heading">
        <div>
          <div className="eyebrow">RETURN & RISK</div>
          <h2>Growth, with the drawdowns in view.</h2>
          <p className="caption">{experimentLabel(e)}</p>
        </div>
        <CsvLink
          filename={e.id + '-metrics.csv'}
          rows={keys.map((k) => ({ layer: layerNames[k], ...e.metrics[k] }))}
        >
          Export metrics
        </CsvLink>
      </div>
      <div className="marker-controls">
        {keys.map((k) => (
          <label key={k} className="check">
            <input
              type="checkbox"
              checked={!!visible[k]}
              onChange={(ev) =>
                setVisible({ ...visible, [k]: ev.target.checked })
              }
            />
            <i style={{ background: colors[k] }} />
            {layerNames[k]}
          </label>
        ))}
        <label className="check">
          <input
            type="checkbox"
            checked={log}
            onChange={(ev) => setLog(ev.target.checked)}
          />
          Log wealth scale
        </label>
      </div>
      <Plot data={data} layout={layout} id="experiment-equity" height={420} />
      <p className="caption">
        {date(e.start)}–{date(e.end)}. Each line uses the same dates. Nifty 50
        is a price index, not a dividend-inclusive total-return index.{' '}
        {e.academic
          ? 'The long–short reference uses assumed borrowing costs; it is not an executable short-selling account.'
          : 'Post-tax wealth is the research tax overlay; underlying holdings are the after-trading-cost portfolio.'}
      </p>
      <div className="table-scroll">
        <table className="risk-table">
          <thead>
            <tr>
              <th>Measure</th>
              {keys.map((k) => (
                <th key={k}>{layerNames[k]}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {stats.map(([key, label, percentage]) => (
              <tr key={key}>
                <th>{label}</th>
                {keys.map((k) => (
                  <td key={k}>
                    {percentage
                      ? pct(e.metrics[k][key])
                      : number(e.metrics[k][key], key.includes('days') ? 0 : 2)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="explanation-grid">
        <p>
          <strong>Underwater</strong> means below the highest wealth reached so
          far, with initial capital treated as the first peak. A profitable
          strategy can spend most sessions recovering prior peaks. Longest
          underwater counts consecutive trading sessions.
        </p>
        <p>
          <strong>Sharpe</strong> compares daily returns with the liquid-fund
          reference. <strong>VaR</strong> is the historical 5th-percentile
          monthly loss threshold; <strong>ES</strong> averages the returns
          beyond that threshold. Neither is a maximum possible loss.
        </p>
      </div>
    </section>
  );
}
