import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { date, pct, rupee, number, compact } from './utils';
import CsvLink from './CsvLink';
import type { Position } from './types';

export default function PositionDetails({
  position: p,
  academic,
  filename,
  context,
}: {
  position: Position;
  academic: boolean;
  filename: string;
  context: string;
}) {
  const [ledger, setLedger] = useState(false);
  const [page, setPage] = useState(0);
  const pageSize = 30;
  const total = (key: string) =>
    p.episodes.reduce((s, e) => s + Number(e[key as keyof typeof e] || 0), 0);
  return (
    <section className="surface">
      <div className="section-heading">
        <div>
          <div className="eyebrow">POSITION ACCOUNTING</div>
          <h2>Every visit to this stock.</h2>
          <p className="caption">{context}</p>
        </div>
        <div className="button-group">
          <Button
            variant={ledger ? 'outline' : 'default'}
            onClick={() => {
              setLedger(false);
              setPage(0);
            }}
          >
            Position episodes
          </Button>
          <Button
            variant={ledger ? 'default' : 'outline'}
            onClick={() => {
              setLedger(true);
              setPage(0);
            }}
          >
            Trade ledger
          </Button>
          <CsvLink
            filename={filename + (ledger ? '-trades.csv' : '-episodes.csv')}
            rows={
              ledger
                ? p.trades.map((t) => ({ ...t, episode: t.episode + 1 }))
                : p.episodes.map((e) => ({
                    ...e,
                    episode: e.id + 1,
                    before_cost_pnl: e.pnl + e.fees,
                    trading_charges: e.fees,
                    after_trading_cost_pnl: e.pnl,
                    after_borrowing_pnl: e.net_pnl,
                  }))
            }
          >
            Export CSV
          </CsvLink>
        </div>
      </div>
      <div className="position-totals">
        <div>
          <span>Before-cost profit · same fills</span>
          <strong>{compact(total('pnl') + total('fees'))}</strong>
        </div>
        <div>
          <span>
            Position result ·{' '}
            {academic ? 'after borrowing' : 'after trading costs'}
          </span>
          <strong className={total('net_pnl') >= 0 ? 'positive' : 'negative'}>
            {compact(total('net_pnl'))}
          </strong>
        </div>
        <div>
          <span>Realized · FIFO, after trading costs</span>
          <strong>{compact(total('realized'))}</strong>
        </div>
        <div>
          <span>Unrealized · after allocated entry fees</span>
          <strong>{compact(total('unrealized'))}</strong>
        </div>
        <div>
          <span>{academic ? 'Borrowing charged' : 'Trading charges'}</span>
          <strong>{compact(total(academic ? 'borrow' : 'fees'))}</strong>
        </div>
      </div>
      <p className="caption">
        One episode runs from opening a position until its quantity reaches
        zero. Additions and trims remain within it. Price change is first-entry
        to final-exit (or latest available mark); it is not the money-weighted
        position return.{' '}
        {academic
          ? 'Short-leg price changes describe the underlying stock; short-position profit moves in the opposite direction. Realized/unrealized figures precede borrowing; position result deducts it.'
          : ''}{' '}
        No stock-level tax is assigned.
      </p>
      {ledger ? (
        <>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Date / episode</th>
                  <th>Action</th>
                  <th>Adjusted fill</th>
                  <th>Quantity change</th>
                  <th>Trade value · signed</th>
                  <th>Fees</th>
                  <th>Quantity after</th>
                </tr>
              </thead>
              <tbody>
                {p.trades
                  .slice(page * pageSize, (page + 1) * pageSize)
                  .map((t, i) => (
                    <tr key={i}>
                      <td>
                        {date(t.date)}
                        <small>Episode {t.episode + 1}</small>
                      </td>
                      <td>
                        {t.reason === 'km_daily_stop'
                          ? 'Stop exit'
                          : t.reason === 'confirmed_delisting_zero_recovery'
                            ? 'Delisting write-down'
                            : t.kind}
                        <small>
                          {t.reason === 'km_daily_stop'
                            ? 'Next-open fill'
                            : t.reason === 'confirmed_delisting_zero_recovery'
                              ? 'Conservative zero recovery'
                              : 'Scheduled rebalance'}
                        </small>
                      </td>
                      <td>{rupee(t.price)}</td>
                      <td>{number(t.quantity, 4)}</td>
                      <td>{rupee(t.value)}</td>
                      <td>{rupee(t.fee)}</td>
                      <td>{number(t.after, 4)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
          <div className="pagination">
            <span>
              {page * pageSize + 1}–
              {Math.min((page + 1) * pageSize, p.trades.length)} of{' '}
              {p.trades.length} trade legs
            </span>
            <Button
              variant="outline"
              disabled={page === 0}
              onClick={() => setPage(page - 1)}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              disabled={(page + 1) * pageSize >= p.trades.length}
              onClick={() => setPage(page + 1)}
            >
              Next
            </Button>
          </div>
        </>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Episode / leg</th>
                <th>Entry → exit / mark</th>
                <th>Stock price change</th>
                <th>Position result</th>
                <th>Realized return · FIFO</th>
                <th>Unrealized result</th>
              </tr>
            </thead>
            <tbody>
              {p.episodes.map((e) => (
                <tr key={e.id}>
                  <td>
                    #{e.id + 1}
                    <small>
                      {e.direction > 0 ? 'Long' : 'Short'} · {e.trade_count}{' '}
                      trade legs
                    </small>
                  </td>
                  <td>
                    {date(e.entry)} → {date(e.mark_date)}
                    <small>
                      {e.exit ? 'Closed' : 'Open · latest available mark'} ·{' '}
                      {rupee(e.first_price)} → {rupee(e.mark_price)}
                    </small>
                  </td>
                  <td className={e.price_change >= 0 ? 'positive' : 'negative'}>
                    {pct(e.price_change, 2)}
                  </td>
                  <td className={e.net_pnl >= 0 ? 'positive' : 'negative'}>
                    <small>Before costs: {rupee(e.pnl + e.fees)}</small>
                    <small>Trading charges: {rupee(e.fees)}</small>
                    <strong>After trading costs: {rupee(e.pnl)}</strong>
                    {academic && (
                      <small>
                        Borrowing: {rupee(e.borrow)} · Net: {rupee(e.net_pnl)}
                      </small>
                    )}
                  </td>
                  <td>
                    {pct(e.realized_return, 2)}
                    <small>
                      {rupee(e.realized)} / {rupee(e.matched_cost)}
                    </small>
                  </td>
                  <td>{rupee(e.unrealized)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="caption">
        FIFO realized return = realized profit after matched entry/exit charges
        ÷ matched entry notional plus entry charges. The position result
        includes every addition and trim, but excludes the portfolio’s cash
        return and annual tax overlay. An open episode is marked at the last
        cached price; a stale mark is not evidence of an executable exit.
      </p>
    </section>
  );
}
