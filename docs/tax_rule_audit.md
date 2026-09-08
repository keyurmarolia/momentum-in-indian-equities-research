# Tax and trading-cost rules

## Listed-equity capital gains

- Before 1 October 2004: ordinary short-term treatment and Section 112 long-term alternatives.
- 1 October 2004 to 31 March 2008: 10% STCG; qualifying LTCG exempt.
- 1 April 2008 to 31 March 2018: 15% STCG; qualifying LTCG exempt.
- 1 April 2018 to 31 March 2024: 15% STCG; 10% LTCG above INR 1 lakh.
- 1 April 2024 to 22 July 2024: 15% STCG; 10% LTCG within the INR 1.25 lakh aggregate annual threshold.
- From 23 July 2024: 20% STCG; 12.5% LTCG above INR 1.25 lakh.

Cess is added at the historical rate. Surcharge is excluded under the stated investor profile. Equity lots are realized FIFO, grandfathering is applied where relevant, and gains and losses are netted within each financial year.

## Delivery STT

- 1 October 2004 to 31 May 2005: 0.075% on buy and sell value.
- 1 June 2005 to 31 May 2006: 0.10% per side.
- 1 June 2006 to 30 June 2012: 0.125% per side.
- From 1 July 2012: 0.10% per side.

For a INR 10 lakh purchase and INR 11 lakh sale at the current 0.10% rate, STT is INR 2,100: INR 1,000 on the buy and INR 1,100 on the sale. Brokerage is separate and capped per executed order.

## Other modeled delivery charges

- FYERS brokerage: INR 20 or 0.3% per executed order, whichever is lower.
- NSE transaction charge: 0.0030699% of turnover.
- SEBI turnover fee: INR 10 per crore.
- Stamp duty: 0.015% of buy value.
- DP debit: INR 12.50 plus GST per sold scrip.
- GST: 18% on taxable service charges.
- NSE IPFT: INR 0.01 per crore.

The backtest applies the current non-STT charge schedule consistently across history. STT and capital-gains tax use dated rules.

## Tax overlay

FIFO acquisition and disposal costs exclude STT from deductible expenses. Grandfathering applies only to qualifying long-term disposals from 1 April 2018 of shares acquired by 31 January 2018. The adjusted high on 31 January 2018 (or the last preceding traded date) supplies fair market value. Exempt Section 10(38) gains and losses neither consume taxable losses nor create carry-forwards. Taxable short-term and long-term losses are carried for up to eight financial years under their modeled offset rules. Fixed Section 112A thresholds remain fixed in rupees as capital declines after earlier tax payments. The final partial-year liability is accrued at sample end.

The holdings path is not rerun after tax payments. Each financial year's realizations are scaled by the capital fraction remaining after prior payments, then the annual liability is recomputed and deducted from wealth. Liquid-sleeve realization tax, surcharge and taxpayer-specific elections are excluded. Results are standardized research estimates rather than a personal tax return.

## Sources

A modeled zero-recovery delisting write-down is not treated as a deductible disposal: the archive does not establish a sale or legal extinguishment. This follows the distinction between valuation loss and [transfer of a capital asset](https://www.incometax.gov.in/iec/foportal/help/all-topics/e-filing-services/itr-2-faq). Adjusted-share FIFO is a research approximation; separate bonus allotment dates, zero-cost bonus lots and merger tax bases are not reconstructed.

- Income Tax Act Sections 111A, 112, 112A and 50AA.
- [CBDT grandfathering and loss-treatment FAQ](https://www.incometaxindia.gov.in/documents/20117/14614766/FAQ-on-LTCG.pdf/ee01c0b5-ce30-d9b6-2a63-4b3b48b86ae8?t=1767815955269).
- Finance Acts and Union Budget memoranda for dated rate changes.
- NSE published statutory levies.
- SEBI turnover-fee schedule.
- FYERS published delivery-equity charges.
