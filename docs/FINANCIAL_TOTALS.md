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

`purchase_currency` is nullable. A purchase price saved through the app is
stamped with the owner's currency at that moment, both when the vehicle is created
and when a price is added later; a currency sent explicitly to the API is kept. An
older price stored without a currency is treated as being in the owner's current
currency. Ownership totals stay unavailable while a required rate is missing.
Changing display preferences never relabels a stored currency. Cost per distance
uses the vehicle's odometer span and unit; a missing or zero span produces no
per-distance result.

Migration `gc019_purchase_currency` adds metadata only: no expense amounts or
historical purchase currencies are rewritten. Downgrading removes that metadata;
retain a version-4.3 personal backup before rollback. See USER_BACKUPS.md for
compatibility with older portable backups.

## The currency of a record

The currency chosen in Profile → Preferences is the account's currency. Amounts
default to it on every screen; neither the browser's location nor the interface
language changes it. A record keeps the currency it was saved with, and a new
record without an explicit currency takes the account's.

No form asks for a currency. A new record is saved in the account's currency. A
record that already has another one — an older or imported record, or an expense
drafted from a bank statement row — keeps it, and its form shows that currency's
symbol next to the amount. The vehicle forms show the purchase price the same way.

On the server:

- every create route and the CSV and LubeLogger importers use the account
  currency when the request or file names none; a recurring occurrence or a
  renewed policy copies the record it repeats;
- the `Entry.currency` and `InsurancePolicy.currency` column defaults resolve the
  owner's currency (`owner_currency` in `app/models/user.py`), so a code path that
  forgets to pass one cannot label a record with a built-in currency;
- legacy personal backups without a currency still store *unknown* (`NULL`).
  Every total leaves such an amount out and says so: the ledger totals and
  `GET /api/fuel/stats` with `converted=false`, the weekly and monthly report
  e-mails with a line under the summary. None of them counts it as euros.

Until late July 2026 the forms sent no currency and every expense was saved as
EUR, every policy as USD. Those labels made totals convert amounts that were
never foreign. `GET /api/vehicles/currency-review` lists, per account, the
records that still carry such a label while the account currency differs:
expenses in EUR and policies in USD, with their count and date range. Expenses
matched to a statement line are left out, because a match is only possible in
the statement's own currency. `POST /api/vehicles/currency-review` with
`{currency, action}` resolves a group:

- `relabel` sets the group's records to the account currency. Amounts are not
  converted, and each record's revision moves so a form opened earlier cannot
  restore the old label;
- `keep` records in the account preferences that the label is right, and the
  group is not offered again.

The Expenses page shows the review as a prompt and asks for confirmation before
relabelling. A person who really paid some of those records in the listed
currency can keep the group and edit single records instead.
