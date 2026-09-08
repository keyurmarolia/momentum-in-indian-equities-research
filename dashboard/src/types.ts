export type Metric = Record<string, number | string | boolean | null>;
export type Security = {
  symbol: string;
  ticker: string;
  name: string;
  start: string;
  end: string;
  multiple_isins: boolean;
};
export type Summary = {
  id: string;
  strategy: string;
  label: string;
  formation_period: string;
  frequency: string;
  holdings_n: number;
  maintenance: string;
  academic: boolean;
  start: string;
  end: string;
  events: number;
  securities: number;
  metrics: Record<string, Metric>;
};
export type Manifest = {
  schema: number;
  as_of: string;
  initial_capital: number;
  experiments: Summary[];
  securities: Record<string, Security>;
};
export type Holding = {
  id: string;
  weight: number;
  quantity: number;
  value: number;
  rank: number;
  signal: number;
  mdtv: number;
  leg: string;
  status: string;
  target_selected: boolean;
};
export type Snapshot = {
  date: string;
  signal_date: string;
  capital: number;
  cash: number;
  holdings: Holding[];
  departures: { id: string; date: string; reason: string }[];
  fees: number;
  eligible: number;
  threshold: number;
  turnover: number;
};
export type Trade = {
  date: string;
  price: number;
  quantity: number;
  value: number;
  fee: number;
  kind: string;
  reason: string;
  episode: number;
  after: number;
};
export type Episode = {
  id: number;
  entry: string;
  exit: string | null;
  direction: number;
  first_price: number;
  mark_price: number;
  mark_date: string;
  quantity: number;
  price_change: number;
  pnl: number;
  net_pnl: number;
  fees: number;
  borrow: number;
  realized: number;
  unrealized: number;
  realized_return: number | null;
  matched_cost: number;
  trade_count: number;
};
export type Position = { trades: Trade[]; episodes: Episode[] };
export type Experiment = Summary & {
  dates: string[];
  curves: Record<string, number[]>;
  snapshots: Snapshot[];
  positions: Record<string, Position>;
};
export type PriceRow = [
  string,
  number,
  number,
  number,
  number,
  number | null,
  number | null,
  boolean | null,
];
export type PriceData = { rows: PriceRow[]; columns: string[] };
