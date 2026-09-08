import test from 'node:test';
import assert from 'node:assert/strict';
import { aggregatePrices, pct, compact, toCSV, rupee } from '../src/utils.ts';

const rows = [
  ['2026-01-29', 100, 110, 95, 105, 99, 96, true],
  ['2026-01-30', 105, 115, 102, 112, 101, 98, true],
  ['2026-02-02', 113, 118, 109, 116, 103, 100, true],
];
test('daily bars preserve every source observation', () =>
  assert.deepEqual(aggregatePrices(rows, 'Daily'), rows));
test('weekly OHLC uses first open, extreme high/low, and last close', () => {
  const out = aggregatePrices(rows, 'Weekly');
  assert.equal(out.length, 2);
  assert.deepEqual(out[0], ['2026-01-29', 100, 115, 95, 112, 101, 98, true]);
  assert.deepEqual(rows[0], ['2026-01-29', 100, 110, 95, 105, 99, 96, true]);
});
test('monthly bars do not combine adjacent months', () =>
  assert.equal(aggregatePrices(rows, 'Monthly').length, 2));
test('display rounding does not show negative zero cash or weights', () => {
  assert.equal(pct(-1e-12), '0.0%');
  assert.equal(compact(-1e-6), '₹0');
  assert.equal(rupee(-1e-6), '₹0.00');
  assert.equal(pct(-0.13), '-13.0%');
  assert.equal(pct(null), '—');
});
test('CSV preserves numbers, quotes names, and neutralizes string formulas', () => {
  const csv = toCSV([
    { name: 'A, "B"', quantity: -5 },
    { name: '=cmd', quantity: 2 },
  ]);
  assert.ok(csv.includes('"A, ""B"""'));
  assert.ok(csv.includes('"-5"'));
  assert.ok(csv.includes('"\'=cmd"'));
});
