# Financial totals

GC-019 centralizes operating costs in `app.services.expense_ledger`. Vehicle statistics,
fleet summary, yearly expense charts, report previews and private/shared PDFs use
`recorded_expenses_plus_scheduled_insurance`:

- Fuel, service, repair, tax, parking and consumables use their recorded dates.
  Fuel uses `total_price`, falling back to `amount` only when it is null.
- Insurance is a **scheduled estimate**, not verified payment. Installments start
  on the policy start date and repeat monthly, quarterly, semiannually or annually.
  One-time policies contribute once. Legacy blank/unknown frequencies use the
  existing annual fallback. Month-end dates stay anchored to the original day.
- Inclusive dates are capped at UTC today. Policy end dates, including stored
  cancellation dates, are inclusive. Expired/cancelled policies retain historical
  estimates inside their stored coverage interval. No implicit renewal is added.
  Status does not prove payment; historical cancellation timing cannot be recovered
  if the stored end date was not updated.
- Each amount is converted at the same current rate snapshot and rounded to cents
  before aggregation. These are display estimates, not historical FX accounts.
  Missing/invalid rates or unknown currencies exclude nonzero amounts from the
  numeric subtotal: `converted=false` and `unconverted` disclose this. Zero amounts
  need no FX rate. Per-distance costs and forecasts from incomplete totals are
  unavailable. Category/month subtotals reconcile exactly in cents.
- Recorded totals and scheduled insurance estimates are exposed separately.
  Purchase cost is separate from operating totals. Active annualized insurance
  and forecast estimates have their own declared bases and are not added again.

Fleet summary defaults to active vehicles. Explicit vehicle history includes
archived vehicles. Insurance statistics describe all owned vehicles, including
archived ones, and label that scope. The same vehicle/date selection is required
when comparing totals. Expense counts include scheduled insurance occurrences.

`purchase_currency` is nullable. New purchases store their explicit currency or
snapshot the owner's preference at creation. Existing/legacy prices remain unknown
until the owner reviews their original currency in Edit vehicle. Ownership totals
stay unavailable while currency or a required rate is missing. Changing display
preferences never relabels the stored price. Cost per distance uses the vehicle's
odometer span and unit; a missing or zero span produces no per-distance result.

Migration `gc019_purchase_currency` adds metadata only: no expense amounts or
historical purchase currencies are rewritten. Downgrading removes that metadata;
retain a version-4.3 personal backup before rollback. See USER_BACKUPS.md for
compatibility with older portable backups.
