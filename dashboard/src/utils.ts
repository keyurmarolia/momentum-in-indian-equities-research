import type { PriceRow, Summary } from './types';
export const experimentLabel = (e: Summary) =>
  `${strategies[e.strategy]} · ${e.formation_period} lookback · ${e.holdings_n} total stocks · ${e.frequency} rebalance · ${e.maintenance === 'winner_drift' ? 'Winner drift' : 'Equal-weight reset'}`;
export const strategies: Record<string, string> = {
  raw_momentum: 'Raw momentum',
  vol_adjusted: 'Volatility-adjusted',
  jensen_alpha: 'Jensen alpha',
  km_momentum: 'KM momentum',
  jt_academic: 'Jegadeesh–Titman',
};
export const layerNames: Record<string, string> = {
  raw: 'Before costs',
  gross: 'After trading costs',
  post_tax: 'Post-tax overlay',
  academic_raw: 'Before borrowing',
  academic_borrow_3pct: '3% borrowing',
  academic_borrow_6pct: '6% borrowing',
  academic_borrow_12pct: '12% borrowing',
  benchmark: 'Nifty 50 price',
};
export const colors: Record<string, string> = {
  raw: '#829398',
  gross: '#3b82ab',
  post_tax: '#147b70',
  academic_raw: '#829398',
  academic_borrow_3pct: '#3b82ab',
  academic_borrow_6pct: '#147b70',
  academic_borrow_12pct: '#bc783e',
  benchmark: '#b68b57',
};
export const pct = (v: unknown, d = 1) =>
  v == null || !Number.isFinite(Number(v))
    ? '—'
    : `${(Math.abs(Number(v) * 100) < 0.5 * 10 ** -d ? 0 : Number(v) * 100).toFixed(d)}%`;
export const number = (v: unknown, d = 2) =>
  v == null || !Number.isFinite(Number(v))
    ? '—'
    : (Math.abs(Number(v)) < 0.5 * 10 ** -d ? 0 : Number(v)).toLocaleString(
        'en-IN',
        {
          maximumFractionDigits: d,
          minimumFractionDigits: d,
        },
      );
export const rupee = (v: unknown) => (v == null ? '—' : `₹${number(v)}`);
export function compact(v: number) {
  const a = Math.abs(v),
    s = v < -0.5 ? '−' : '';
  return a >= 1e7
    ? `${s}₹${(a / 1e7).toFixed(2)} cr`
    : a >= 1e5
      ? `${s}₹${(a / 1e5).toFixed(2)} lakh`
      : `${s}₹${number(a, 0)}`;
}
export const date = (s: string) =>
  new Date(s + 'T00:00:00Z').toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  });
export function toCSV(rows: Record<string, unknown>[]) {
  if (!rows.length) return '';
  const keys = Array.from(new Set(rows.flatMap(Object.keys)));
  const escape = (v: unknown) => {
    const serialized = JSON.stringify(v);
    let s = v == null ? '' : typeof v === 'string' ? v : (serialized ?? '');
    if (typeof v === 'string' && /^[=+\-@\t\r]/.test(s)) s = "'" + s;
    return '"' + s.replaceAll('"', '""') + '"';
  };
  return [
    keys.map(escape).join(','),
    ...rows.map((r) => keys.map((k) => escape(r[k])).join(',')),
  ].join('\r\n');
}
export function aggregatePrices(rows: PriceRow[], mode: string): PriceRow[] {
  if (mode === 'Daily') return rows;
  const groups = new Map<string, PriceRow>();
  for (const row of rows) {
    const day = new Date(row[0] + 'T00:00:00Z');
    if (mode === 'Weekly')
      day.setUTCDate(day.getUTCDate() - ((day.getUTCDay() + 6) % 7));
    const key =
      mode === 'Monthly' ? row[0].slice(0, 7) : day.toISOString().slice(0, 10);
    const prev = groups.get(key);
    if (!prev) groups.set(key, [...row]);
    else {
      prev[2] = Math.max(prev[2], row[2]);
      prev[3] = Math.min(prev[3], row[3]);
      prev[4] = row[4];
      prev[5] = row[5];
      prev[6] = row[6];
      prev[7] = row[7];
    }
  }
  return [...groups.values()];
}
