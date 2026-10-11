# Assessment Notes

**App name: CallMatch**, bank reconciliation for capital calls.

- Backend: Django 6.1 + Django REST Framework, PostgreSQL
- Frontend: React 19 + Vite (one page)

## Live demo

- App: https://callmatch.onrender.com
- API: https://callmatch-api.onrender.com/api/organizations/

Both run on Render's free plan, set up from `render.yaml`: Postgres, the Django API (gunicorn) and the React build as a static site. The API runs `migrate` and `seed_demo` every time it starts, and both are safe to repeat. The frontend calls the API through `VITE_API_URL`, and the API only allows that origin (`CORS_ALLOWED_ORIGINS`). The free API sleeps after about 15 minutes of no traffic, so the first request after that can take up to a minute.

## Setup from a fresh clone

You need Python 3.12+, Node 20.19+ and a running PostgreSQL.

```bash
git clone https://github.com/amartya1523/Digital_Alpha_platform_assignment.git
cd Digital_Alpha_platform_assignment

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then set DB_USER / DB_PASSWORD for your Postgres
createdb recon              # or: psql -c "create database recon;"

python manage.py migrate
python manage.py seed_demo  # safe to run more than once
python manage.py runserver  # http://localhost:8000
```

In a second terminal:

```bash
cd frontend
npm install
npm run dev                 # http://localhost:5173
```

Vite forwards `/api` to Django on port 8000, so there is no CORS setup.

### Run the tests

```bash
python manage.py test
```

The Postgres user needs permission to create a database, since Django creates a throwaway test database.

## Project layout

```
config/                  Django settings and root urls
recon/
  models.py              data model
  importer.py            CSV parsing, validation, duplicates, saving
  matching.py            normalisation + matching rules (section 6)
  actions.py             approve / reject / ignore
  airtable.py            optional Airtable sync (bonus)
  views.py, urls.py      thin API layer
  serializers.py
  management/commands/seed_demo.py
  tests/
frontend/src/            React page (App, UploadPanel, TransactionTable, LineItemPanel)
```

Views only read the org header, call a service function and return the result. All the rules live in `importer.py`, `matching.py` and `actions.py`.

## Data model

| Model | Main fields |
|---|---|
| `Organization` | `slug` (unique), `name` |
| `InvestorEntity` | `organization`, `name` (unique per org) |
| `CapitalCall` | `organization`, `number` (unique per org), `call_date`, `due_date` |
| `LineItem` | `capital_call`, `investor`, `expected_reference`, `amount_called`, `amount_funded`, `status`. `amount_remaining` is a property, not a column. |
| `BankTransaction` | `organization`, `date`, `description`, `amount`, `bank_reference`, `status`, `review_reason`, `airtable_record_id`, `airtable_sync_status` |
| `Match` | `transaction`, `line_item`, `status`, `reason` |

- All money uses `DecimalField(max_digits=14, decimal_places=2)` and Python `Decimal`. No floats.
- `(organization, bank_reference)` is unique in the database, so a duplicate can't be saved even if the code had a bug.
- A check constraint stops `amount_funded` from going above `amount_called`.
- Debits are stored with a negative amount, so `type` isn't saved as its own column.

## API

Every endpoint except the organization list needs the `X-Organization: <slug>` header. A missing header returns `400` and an unknown org returns `404`. Records from another organization return `404`.

| Method | Path | What it does |
|---|---|---|
| GET | `/api/organizations/` | List orgs for the switcher (`slug`, `name`) |
| GET | `/api/line-items/` | Line items with called, funded, remaining and status |
| GET | `/api/transactions/` | Transactions with their matches and reasons, newest first |
| POST | `/api/transactions/import/` | Upload a CSV (multipart, field `file`) and get the import summary |
| POST | `/api/transactions/{id}/ignore/` | Ignore a `suggested` / `needs_review` transaction. `409` otherwise. |
| POST | `/api/matches/{id}/approve/` | Approve a proposed match. `409` if it isn't proposed any more or the amount no longer fits. |
| POST | `/api/matches/{id}/reject/` | Reject a proposed match. `409` if it isn't proposed. |

Import response (`201`):

```json
{
  "imported": 11,
  "duplicates": 1,
  "duplicate_rows": [{ "line": 11, "reference": "FT20260403A" }],
  "errors": [
    { "line": 13, "message": "Invalid date \"2026-04-31\", not a real calendar date." },
    { "line": 14, "message": "Credit amount must be positive." }
  ]
}
```

A missing column returns `400` with `{"detail": "Missing column(s): reference. Nothing was imported."}`.

Transaction (list item, and the response of the three actions):

```json
{
  "id": 7, "date": "2026-04-11", "description": "WIRE INCOMING OAKRIDGE HOLDINGS LLC",
  "amount": "15000.00", "bank_reference": "FT20260411G", "status": "needs_review",
  "review_reason": "Name and amount match more than one line item (CC-1005, CC-1006).",
  "airtable_sync_status": "not_synced",
  "matches": [
    { "id": 5, "line_item": 5, "investor": "Oakridge Holdings LLC", "expected_reference": "CC-1005",
      "status": "proposed", "reason": "Investor \"Oakridge Holdings LLC\" found in description; amount equals remaining 15,000.00." }
  ]
}
```

## How the important parts work

**Import.** The whole file is read first. If a column is missing, nothing is saved. Each row is trimmed and validated, and bad rows are reported with their file line number (the header is line 1, and blank lines still count). Valid rows are checked for duplicates against the database and against earlier rows in the same file. Everything is then saved in one DB transaction. The org row is locked (`select_for_update`) during the import, so two uploads for the same org can't both pass the duplicate check.

**Matching.** `matching.find_matches()` follows section 6 step by step: eligible line items, then the reference check, then name + exact amount. It returns the status, a review reason and a list of `(line_item, reason)`. Line items are loaded once per import, so a few thousand rows stay fast.

**Approve.** This runs in one DB transaction. It locks the transaction row, then the match, then the line item. It re-checks that the match is still `proposed` and that the amount fits the *current* remaining amount, and returns `409` otherwise. So if the same approval arrives twice at the same moment, the second one waits for the lock, sees the match is already `approved` and gets a `409`. There's a test that does exactly this with two threads (`ConcurrentApproveTests`). Reject and ignore lock in the same order, so they can't deadlock with approve.

**Airtable (bonus).** If `AIRTABLE_TOKEN` and `AIRTABLE_BASE_ID` are set, new `needs_review` transactions are created as Airtable records after the import has committed (in batches of 10). Any error is caught and saved as `sync_failed`, so it can never break the import. The client is a small class with one method, and the tests swap it for a fake. The Airtable table needs these text columns: `Bank Reference`, `Organization`, `Date`, `Description`, `Amount`, `Reason`.

## Assumptions

- Header names are trimmed and case-insensitive. Extra columns are ignored. The file must be UTF-8 (a BOM is fine).
- An amount can have a sign, commas as thousands separators and up to 2 decimals. Currency symbols, `(25.00)` and scientific notation are rejected.
- Each invalid row reports the first problem found.
- An invalid row isn't checked for duplicates. Only valid rows count as imported or duplicate.
- Bank references are compared exactly after trimming (case-sensitive), since they're bank IDs.
- The reference check is a plain "appears in" check, as the spec says. So a reference like `CC-100` would also be found inside `CC-1001`. That's fine for the seed data.
- When more than one reference is found, all of them are proposed whatever the amount. Approve re-checks the amount anyway.
- Approve is allowed on any proposed match, including on `needs_review` transactions. That's how the GP picks one of several candidates.
- Ignore only works on `suggested` / `needs_review`. Ignoring a `reconciled` or already `ignored` transaction returns `409`.
- Suggestions are made once at import, using the remaining amounts at that time.
- Amounts are shown in USD in the UI.

## Trade-offs

- I used function-based DRF views and plain service modules instead of ViewSets/routers. There's less magic and the code is easier to follow for a small API.
- Services raise DRF exceptions (`ParseError`, `NotFound`, a `Conflict` 409) directly. That ties them a little to DRF, but it keeps the views tiny.
- No pagination on the transaction list. It's fine for a few thousand rows.
- The Airtable sync runs inside the upload request. For big files with many `needs_review` rows this makes the upload slower (Airtable allows 5 requests a second). A background worker would fix that, but it was out of scope.
- No login, as the brief says. The org header is trusted.

## Next steps

- Pagination and status filters on the transaction list.
- Let the GP manually pick a line item for a `needs_review` transaction that has no matches, and undo a reject.
- A retry button for `sync_failed` Airtable records.
- Docker Compose for Postgres + backend + frontend, and CI running the tests.


