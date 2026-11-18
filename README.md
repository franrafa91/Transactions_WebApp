# Transactions WebApp

A Flask-based web application for managing personal or business financial transactions with multi-currency support (HNL, USD, EUR). Features include CRUD operations, search/filtering, balance reports, and interactive historical charts.

## Features

- **Transaction Management** – Create, edit, delete transactions, target-balance adjustments with category/payee/memo/description, and transfers between accounts
- **Three Operation Modes** – Enter an expense/income amount, set an account's balance at a date, or register a transfer between accounts
- **Search & Filter** – Filter by account, payee, category, date range, amount, memo, and description
- **Paginated Transaction List** – Browse transactions with configurable page size
- **Reports Dashboard** – Account balances with EUR conversion, category expense breakdowns
- **Interactive Charts** – Historical balance and category trend charts (Plotly.js)
- **Multi-Currency** – Automatic conversion between HNL, USD, EUR using live exchange rates
- **Exchange Rates** – Cached daily from ECB (EUR/USD) and BCH Honduras (HNL/USD)

## Technology Stack

| Layer | Technology |
|---|---|
| Web Framework | Flask 3.x |
| Database | PostgreSQL |
| Frontend | Bootstrap 5, Plotly.js |
| Data Processing | pandas, numpy |
| Exchange Rates | xmltodict (XML), requests, pandas (Excel) |
| Deployment | Gunicorn / WSGI |

## Prerequisites

- Python 3.13
- PostgreSQL database
- `.pgpass` file in home directory with database credentials (format: `host:port:dbname:user:password`)

## Database Setup

The application expects a PostgreSQL database named `trans_app` with the following tables:

- **`transacciones`** – Transaction records
- **`cuentas`** – Account definitions with currency and type
- **`Categories`** – Category definitions

### Stored procedures

All writes made by the application go through six `PROCEDURE`s in the `public` schema: the
five `web*` procedures below and `set_balance`. The application invokes them positionally
(`CALL webtransaction(%s, ...)` through psycopg2), so the parameter order, count, and types
below are a hard contract: changing them in the database requires updating `app.py` at the
same time.

Signatures as deployed in `trans_app` (from `information_schema.parameters`). PostgreSQL
discards type modifiers on procedure parameters, so `character` without a length is an
unbounded blank-padded string (`bpchar`), not a one-character value.

| Procedure | Parameters (in order) | Called by |
|---|---|---|
| `webtransaction` | `in_cuenta character, in_description character, in_categoria character, in_payee character, in_fecha timestamp without time zone, in_monto numeric, in_memo character, in_now timestamp without time zone` | “Transacción” submit on `/` |
| `webtransfer` | `in_cuenta character, in_transfer character, in_description character, in_payee character, in_fecha timestamp without time zone, in_monto numeric, in_recibido numeric, in_memo character, in_now timestamp without time zone` | “Transferencia” submit on `/` |
| `set_balance` | `in_cuenta character varying, in_fecha timestamp without time zone, in_balance double precision, in_categoria character varying, in_payee character varying DEFAULT NULL, in_memo character varying DEFAULT NULL, in_description character varying DEFAULT 'Balance adjustment'` | “Balance” submit on `/` |
| `webmodification` | `in_id integer, in_cuenta character, in_transfer character, in_payee character, in_categoria character, in_fecha timestamp without time zone, in_monto numeric, in_memo character, in_description character, in_now timestamp without time zone` | “Modificación” submit in the edit modal on `/` |
| `webduplication` | `in_id integer, in_now timestamp without time zone` | “Duplicar” submit in the edit modal on `/` |
| `webdeletion` | `in_id integer` | “Eliminar” submit in the edit modal on `/` |

#### Parameter sources

The three operation forms on `/` submit named fields, so `app.py` reads `Cuenta`, `Fecha`,
`Monto`, etc. by name. The edit modal and search offcanvas still use
`dict(request.form).values()`, so their field order remains significant.

##### `webtransaction` – 8 parameters

Called by `new_transaction()` (`app.py`), which reads
`[Cuenta, Payee, Categoria, Fecha, Monto, Memo, Descripcion]` by name, appends the server
time, and reorders them as `[0, 6, 2, 1, 3, 4, 5, 7]`.

| # | Parameter | Type | Supplied value |
|---|---|---|---|
| 1 | `in_cuenta` | `character` | `Cuenta` select |
| 2 | `in_description` | `character` | `Descripcion` input |
| 3 | `in_categoria` | `character` | `Categoria` input (must exist in `categories.categoría`) |
| 4 | `in_payee` | `character` | `Payee` input |
| 5 | `in_fecha` | `timestamp` | `Fecha` input, parsed with `%Y-%m-%dT%H:%M` |
| 6 | `in_monto` | `numeric` | `Monto` input (signed; negative = expense) |
| 7 | `in_memo` | `character` | `Memo` input |
| 8 | `in_now` | `timestamp` | Server-side `datetime.now()` at submission |

##### `webtransfer` – 9 parameters

Called by `new_transfer()` (`app.py`), which reads
`[Cuenta, Payee, Fecha, Monto, Memo, Descripcion, Transferencia, MontoRec]` by name, appends
the server time, and reorders them as `[0, 6, 5, 1, 2, 3, 7, 4, 8]`.

| # | Parameter | Type | Supplied value |
|---|---|---|---|
| 1 | `in_cuenta` | `character` | `Cuenta` select (source account) |
| 2 | `in_transfer` | `character` | `Transferencia` select (destination account) |
| 3 | `in_description` | `character` | `Descripcion` input |
| 4 | `in_payee` | `character` | `Payee` input |
| 5 | `in_fecha` | `timestamp` | `Fecha` input (`%Y-%m-%dT%H:%M`) |
| 6 | `in_monto` | `numeric` | `Monto` input (amount debited from the source) |
| 7 | `in_recibido` | `numeric` | `MontoRec` input (amount credited to the destination) |
| 8 | `in_memo` | `character` | `Memo` input |
| 9 | `in_now` | `timestamp` | Server-side `datetime.now()` at submission |

##### `set_balance` – 4 required + 3 optional parameters

Called by the **Balance** pane on `/`. `app.py` reads the fields by name, parses `Fecha`
with `%Y-%m-%dT%H:%M`, converts `Balance` to `float`, requires a non-empty `Categoria`,
and converts blank optional fields to `None`. It calls
`set_balance(cuenta, fecha, objetivo, categoria, payee, memo, descripcion)`. The procedure
stamps `Input` itself.

| # | Parameter | Type | Supplied value |
|---|---|---|---|
| 1 | `in_cuenta` | `character varying` | `Cuenta` select |
| 2 | `in_fecha` | `timestamp` | `Fecha` input (`%Y-%m-%dT%H:%M`) |
| 3 | `in_balance` | `double precision` | `Balance` input (target balance; may be zero or negative) |
| 4 | `in_categoria` | `character varying` | `Categoria` input (required; must exist in `categories`) |
| 5 | `in_payee` | `character varying` | `Payee` input (optional, default `NULL`) |
| 6 | `in_memo` | `character varying` | `Memo` input (optional, default `NULL`) |
| 7 | `in_description` | `character varying` | `Descripcion` input (optional, default `'Balance adjustment'`) |

`in_categoria` has no default, so the minimum call is four arguments. The old
three-argument overload is removed after deployment; `set_balance(cuenta, fecha, balance)`
no longer resolves.

Before calling `set_balance`, the route calls `get_balance(cuenta, fecha)` to report the
previous balance and the applied adjustment. The procedure inserts at most one row and
does nothing if the account is already at the target within `0.005`.

##### `webmodification` – 10 parameters

Called by `modify_transaction()` (`app.py`), which passes the submitted values through
unchanged and appends the server time. Submitting an empty transfer field sends `NULL`.

| # | Parameter | Type | Supplied value |
|---|---|---|---|
| 1 | `in_id` | `integer` | Hidden `ID` field, filled by `selectrow()` |
| 2 | `in_cuenta` | `character` | `Cuenta` select |
| 3 | `in_transfer` | `character` | `Transfer` select (may be `NULL`) |
| 4 | `in_payee` | `character` | `Payee` input |
| 5 | `in_categoria` | `character` | `Categoria` input |
| 6 | `in_fecha` | `timestamp` | `Fecha` input (`%Y-%m-%dT%H:%M`) |
| 7 | `in_monto` | `numeric` | `Monto` input |
| 8 | `in_memo` | `character` | `Memo` input |
| 9 | `in_description` | `character` | `Descripcion` input |
| 10 | `in_now` | `timestamp` | Server-side `datetime.now()` at submission |

`webmodification` also accepts a 9-value form submission, in which case the route inserts
an empty `in_transfer` at position 3. The current modal always submits 10 values, so the
10-parameter path is the one in use.

##### `webduplication` – 2 parameters

Called by `duplicate_transaction()` (`app.py`) with the hidden `ID` value and the server
time. The copy receives `Fecha` and `Input` = `in_now` and `Tags = 'web_dup'`, so it
appears first in the list (`ORDER BY Fecha DESC, Input DESC`) and can then be adjusted
with “Modificación”.

| # | Parameter | Type | Supplied value |
|---|---|---|---|
| 1 | `in_id` | `integer` | Hidden `ID` field, filled by `selectrow()` |
| 2 | `in_now` | `timestamp` | Server-side `datetime.now()` at submission |

Only the selected row is copied: duplicating one leg of a transfer does not create the
mirror entry.

##### `webdeletion` – 1 parameter

Called by `delete_transaction()` (`app.py`) with the hidden `ID` value:

| # | Parameter | Type | Supplied value |
|---|---|---|---|
| 1 | `in_id` | `integer` | Hidden `ID` field, filled by `selectrow()` |

#### Recreating the procedures

The bodies are application-specific and already exist in `trans_app`; dump the live
definitions with psql (`\sf webtransaction`, `\sf webtransfer`, `\sf webmodification`,
`\sf webduplication`, `\sf webdeletion`). The `CREATE OR REPLACE` skeletons below use the
exact deployed signatures. These are signature placeholders: they compile, but their
bodies do nothing until you restore the real logic. Do not change the argument types
either, or PostgreSQL will create an overload instead of replacing the existing procedure.

```sql
CREATE OR REPLACE PROCEDURE public.webtransaction(
    IN in_cuenta      character,
    IN in_description character,
    IN in_categoria   character,
    IN in_payee       character,
    IN in_fecha       timestamp without time zone,
    IN in_monto       numeric,
    IN in_memo        character,
    IN in_now         timestamp without time zone
) LANGUAGE plpgsql AS $$ BEGIN END; $$;

CREATE OR REPLACE PROCEDURE public.webtransfer(
    IN in_cuenta      character,
    IN in_transfer    character,
    IN in_description character,
    IN in_payee       character,
    IN in_fecha       timestamp without time zone,
    IN in_monto       numeric,
    IN in_recibido    numeric,
    IN in_memo        character,
    IN in_now         timestamp without time zone
) LANGUAGE plpgsql AS $$ BEGIN END; $$;

CREATE OR REPLACE PROCEDURE public.webmodification(
    IN in_id          integer,
    IN in_cuenta      character,
    IN in_transfer    character,
    IN in_payee       character,
    IN in_categoria   character,
    IN in_fecha       timestamp without time zone,
    IN in_monto       numeric,
    IN in_memo        character,
    IN in_description character,
    IN in_now         timestamp without time zone
) LANGUAGE plpgsql AS $$ BEGIN END; $$;

CREATE OR REPLACE PROCEDURE public.webduplication(
    IN in_id  integer,
    IN in_now timestamp without time zone
) LANGUAGE plpgsql AS $$ BEGIN END; $$;

CREATE OR REPLACE PROCEDURE public.webdeletion(
    IN in_id integer
) LANGUAGE plpgsql AS $$ BEGIN END; $$;
```

#### Notes

- The edit modal form must keep its current field order, because the route maps values by
  position: `ID, Cuenta, Transfer, Payee, Categoria, Fecha, Monto, Memo, Descripcion, Operación`.
- The transaction, balance, and transfer forms on `/` are parsed by field name, so their
  order is not significant.
- Blank text inputs are converted to `NULL` before the call.
- `Monto` and `MontoRec` arrive as strings and are cast to `numeric` by PostgreSQL. The
  target column `transacciones.monto` is `double precision`, so the procedure body relies
  on the implicit `numeric` to `double precision` cast. The Balance target is converted to
  `float` in `app.py` and passed to a `double precision` parameter.
- `Fecha` must arrive as `YYYY-MM-DDTHH:MM` (HTML `datetime-local`); the route parses it
  with `datetime.strptime(..., "%Y-%m-%dT%H:%M")` and the DB columns are
  `timestamp without time zone`.
- `in_now` is always appended by the server for the `web*` procedures; it is never a form
  field. `set_balance` stamps `Input = LOCALTIMESTAMP` inside the procedure.
- `webduplication` copies the selected row and stamps `Fecha`, `Input`, and `Tags`
  (`web_dup`) from the server; the new `id` comes from the identity column.
- The procedure parameters are unbounded, but the underlying `transacciones` columns are
  limited: `cuenta`, `transfer`, `categoría`, `memo` are `varchar(30)`, `payee` is
  `varchar(40)`, and `description` is `varchar(255)`.
- `Operación = Buscar` and `Operación = Clear Search` do not call any procedure; they only
  update the Flask session filter.

### Balance helpers (psql)

The **Balance** pane on `/` calls both routines: `get_balance` to report the previous
balance and `set_balance` to apply the target. They can also be used directly from psql.
They work on one account at a time, in that account's own currency.

| Routine | Signature | Purpose |
|---|---|---|
| `get_balance` (function) | `in_cuenta character varying, in_fecha timestamp without time zone` → `double precision` | `SUM(monto)` for the account where `fecha < in_fecha` |
| `set_balance` (procedure) | `in_cuenta character varying, in_fecha timestamp without time zone, in_balance double precision, in_categoria character varying, in_payee character varying DEFAULT NULL, in_memo character varying DEFAULT NULL, in_description character varying DEFAULT 'Balance adjustment'` | Inserts one adjustment row so the balance at `in_fecha` equals `in_balance` |

`get_balance` returns `0` when the account has no earlier transactions and raises `22023`
(`invalid_parameter_value`) for a `NULL` argument or an account missing from `cuentas`.
The comparison is strict (`fecha < in_fecha`) and account matching is exact and
case-sensitive, consistent with the report filter in `app.py`.

`set_balance` computes `delta = in_balance - get_balance(in_cuenta, in_fecha)` and inserts
one row:

- `fecha = in_fecha - interval '1 millisecond'`
- `monto = delta`
- `categoría = in_categoria` (required; must exist in `categories`)
- `payee = in_payee` and `memo = in_memo` (optional)
- `description = in_description`, defaulting to `'Balance adjustment'`
- `tags = 'balance'`, `input = LOCALTIMESTAMP`

The one-millisecond offset is required because the balance uses `< in_fecha` and `fecha` is
`timestamp(3)`: a row stamped exactly at `in_fecha` would not be counted, and subtracting a
microsecond rounds back up to `in_fecha`. The adjustment therefore shows one minute earlier
in the web list (`%d-%m-%y %H:%M`), which is cosmetic.

`set_balance` inserts nothing when `abs(delta) < 0.005` (an already-correct balance or
floating-point noise) and reports the delta through `RAISE NOTICE`. Repeated calls are
numerically correct but add a row each time the target changes.

```sql
SELECT get_balance('KBC', '2026-01-01');
-- 10516.899999999921

CALL set_balance(
    'KBC', '2026-01-01', 11000, 'Financiero',
    'Payee opcional', 'Memo opcional', 'Custom adjustment'
);
-- NOTICE:  set_balance: KBC adjusted by 483.1000000000786 at 2025-12-31 23:59:59.999 (target 11000, category Financiero)

SELECT get_balance('KBC', '2026-01-01');
-- 11000

SELECT id, fecha, monto, categoría, payee, memo, description, tags
FROM transacciones WHERE tags = 'balance' ORDER BY id;
```

Out-of-order updates: setting a later date first and an earlier date afterwards changes the
later balance by the earlier delta. For example, after setting October to 30,000 and then
September to 20,000, October reads `30,000 + (20,000 - September's old balance)`; calling
`set_balance` for October again with 30,000 inserts the corrective delta and restores it.
Automating that would require storing each date's target balance, which the schema does
not do.

Notes:

- Balances are derived (`SUM(monto)`), not stored, so later transactions never need to be
  edited; an adjustment is automatically included in every later balance.
- The category is required and must exist in `categories`. Choosing a real category makes
  the adjustment part of that category's report; `Sin Categoría` remains excluded from the
  income/expense breakdowns.
- Existing balance rows are not backfilled; only new adjustments use the category, payee,
  memo, and description fields.
- This is a single-entry ledger: a balance adjustment changes that account and total net
  worth with no counterpart entry.
- `idx_transacciones_cuenta_fecha` on `(cuenta, fecha)` supports these lookups.
- `\sf get_balance` and `\sf set_balance` show the deployed definitions.

#### Deployed definitions

```sql
CREATE INDEX IF NOT EXISTS idx_transacciones_cuenta_fecha
    ON public.transacciones (cuenta, fecha);

CREATE OR REPLACE FUNCTION public.get_balance(
    in_cuenta character varying,
    in_fecha  timestamp without time zone
) RETURNS double precision
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_balance double precision;
BEGIN
    IF in_cuenta IS NULL OR in_fecha IS NULL THEN
        RAISE EXCEPTION 'get_balance: cuenta and fecha are required'
            USING ERRCODE = '22023';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM public.cuentas WHERE "Nombre Cuenta" = in_cuenta
    ) THEN
        RAISE EXCEPTION 'get_balance: unknown account "%"', in_cuenta
            USING ERRCODE = '22023';
    END IF;

    SELECT COALESCE(SUM(monto), 0)::double precision
      INTO v_balance
      FROM public.transacciones
     WHERE cuenta = in_cuenta
       AND fecha < in_fecha;

    RETURN v_balance;
END;
$$;

-- If replacing the old 3-argument version:
-- DROP PROCEDURE IF EXISTS public.set_balance(
--     character varying, timestamp without time zone, double precision
-- );

CREATE OR REPLACE PROCEDURE public.set_balance(
    IN in_cuenta      character varying,
    IN in_fecha       timestamp without time zone,
    IN in_balance     double precision,
    IN in_categoria   character varying,
    IN in_payee       character varying DEFAULT NULL,
    IN in_memo        character varying DEFAULT NULL,
    IN in_description character varying DEFAULT 'Balance adjustment'
)
LANGUAGE plpgsql AS $$
DECLARE
    v_current double precision;
    v_delta   double precision;
    v_stamp   timestamp without time zone;
BEGIN
    IF in_cuenta IS NULL OR in_fecha IS NULL OR in_balance IS NULL
       OR in_categoria IS NULL OR btrim(in_categoria) = '' THEN
        RAISE EXCEPTION 'set_balance: cuenta, fecha, balance and categoria are required'
            USING ERRCODE = '22023';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM public.categories WHERE categoría = in_categoria
    ) THEN
        RAISE EXCEPTION 'set_balance: unknown category "%"', in_categoria
            USING ERRCODE = '22023';
    END IF;

    v_current := public.get_balance(in_cuenta, in_fecha);
    v_delta := in_balance - v_current;

    IF abs(v_delta) < 0.005 THEN
        RAISE NOTICE 'set_balance: % already at % on %; nothing inserted',
            in_cuenta, in_balance, in_fecha;
        RETURN;
    END IF;

    v_stamp := in_fecha - interval '1 millisecond';

    INSERT INTO public.transacciones
        (cuenta, transfer, description, payee, categoría,
         fecha, monto, memo, tags, input)
    VALUES
        (in_cuenta, NULL, NULLIF(in_description, ''), NULLIF(in_payee, ''),
         in_categoria, v_stamp, v_delta, NULLIF(in_memo, ''), 'balance',
         LOCALTIMESTAMP);

    RAISE NOTICE 'set_balance: % adjusted by % at % (target %, category %)',
        in_cuenta, v_delta, v_stamp, in_balance, in_categoria;
END;
$$;
```

## Installation

Run the app inside a Python virtual environment (the Debian system Python is "externally managed" and refuses plain `pip install` calls).

```bash
# Create and activate a virtual environment (first time only)
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

Leave the environment later with `deactivate`. All commands below assume the venv is activated.

## Configuration

### Environment Variables

| Variable | Description | Default |
|---|---|---|
| `TRANSACTIONS_SECRET` | Shared secret for access control (dev mode) | `test` |
| `TRANSACTIONS_SECRET_FILE` | Path to file containing the secret (production) | `./secret.txt` |
| `FLASK_SECRET_KEY` | Flask session signing key | Value of `TRANSACTIONS_SECRET` |

### Development Mode

When running on port 5000 (default), the app uses `TRANSACTIONS_SECRET` env var:

```bash
export TRANSACTIONS_SECRET="your-secret-key"
python app.py
```

### Production Mode

In production the app runs as the systemd service `trans_app` (gunicorn from the
project virtual environment), fronted by nginx on `https://frafa.de:2248`.
See [Deployment (systemd + nginx)](#deployment-systemd--nginx) below.

The secret is read from `secret.txt`. Running `app.py` directly on a non-5000
port works for local testing (also reads `secret.txt`):

```bash
echo "your-secret-key" > secret.txt
.venv/bin/python app.py 8080
```

## Accessing the Application

Append `?secret=your-secret-key` to the URL:

```
http://localhost:5000/?secret=your-secret-key
```

## Deployment (systemd + nginx)

Unit file `/etc/systemd/system/trans_app.service` — gunicorn from the venv,
serving the unix socket that nginx proxies to:

```ini
[Unit]
Description=Gunicorn instance to serve trans_app Flask App
After=network.target

[Service]
User=frafa
Group=www-data
WorkingDirectory=/home/frafa/Projects/Transactions_WebApp
Environment="PATH=/home/frafa/Projects/Transactions_WebApp/.venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/home/frafa/Projects/Transactions_WebApp/.venv/bin/gunicorn --bind unix:trans_app.sock -m 007 wsgi

[Install]
WantedBy=multi-user.target
```

After changing the app or its dependencies:

```bash
.venv/bin/pip install -r requirements.txt   # refresh dependencies into the venv
sudo systemctl daemon-reload                # only needed if the unit file changed
sudo systemctl restart trans_app
sudo systemctl status trans_app
```

nginx (`/etc/nginx/sites-available/trans_app.conf`) serves
`https://frafa.de:2248` and proxies to
`unix:/home/frafa/Projects/Transactions_WebApp/trans_app.sock`.

## Project Structure

```
├── .venv/                    # Python 3.13 virtual environment
├── app.py                    # Main application
├── wsgi.py                   # WSGI entry point
├── requirements.txt          # Python dependencies
├── templates/
│   ├── json.html             # Main transactions page
│   ├── _operation_card.html  # New-operation tabs and forms
│   ├── report.html           # Reports/analytics page
│   └── out.html              # Access denied page
└── static/
    ├── main.css              # Custom CSS
    ├── favicon.ico           # Site favicons / touch icon
    ├── favicon.svg
    ├── apple-touch-icon.png
    ├── Precio Promedio Diario del Dólar.parquet  # Cached BCH rates
    └── usd.parquet           # Cached ECB rates
```

## Exchange Rates

- **EUR/USD**: Downloaded from [ECB](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/usd.xml) and cached for 24 hours
- **HNL/USD**: Downloaded from [BCH Honduras](http://www.bch.hn/estadisticos/GIE/LIBTipo%20de%20cambio/Precio%20Promedio%20Diario%20del%20D%C3%B3lar.xlsx) and cached for 24 hours
- If downloads fail, the app falls back to cached local copies

## License

This project is licensed under the terms in the LICENSE file.