# Transactions WebApp

A Flask-based web application for managing personal or business financial transactions with multi-currency support (HNL, USD, EUR). Features include CRUD operations, search/filtering, balance reports, and interactive historical charts.

## Features

- **Transaction Management** – Create, edit, delete transactions and transfers between accounts
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

All writes go through four `PROCEDURE`s in the `public` schema. The application invokes
them positionally (`CALL webtransaction(%s, ...)` through psycopg2), so the parameter
order, count, and types below are a hard contract: changing them in the database requires
updating `app.py` at the same time.

Signatures as deployed in `trans_app` (from `information_schema.parameters`). PostgreSQL
discards type modifiers on procedure parameters, so `character` without a length is an
unbounded blank-padded string (`bpchar`), not a one-character value.

| Procedure | Parameters (in order) | Called by |
|---|---|---|
| `webtransaction` | `in_cuenta character, in_description character, in_categoria character, in_payee character, in_fecha timestamp without time zone, in_monto numeric, in_memo character, in_now timestamp without time zone` | “Transacción” submit on `/` |
| `webtransfer` | `in_cuenta character, in_transfer character, in_description character, in_payee character, in_fecha timestamp without time zone, in_monto numeric, in_recibido numeric, in_memo character, in_now timestamp without time zone` | “Transferencia” submit on `/` |
| `webmodification` | `in_id integer, in_cuenta character, in_transfer character, in_payee character, in_categoria character, in_fecha timestamp without time zone, in_monto numeric, in_memo character, in_description character, in_now timestamp without time zone` | “Modificación” submit in the edit modal on `/` |
| `webdeletion` | `in_id integer` | “Eliminar” submit in the edit modal on `/` |

#### Parameter sources

The routes read submitted fields with `dict(request.form).values()`, so the order of the
fields inside each `<form>` in `templates/json.html` is significant.

##### `webtransaction` – 8 parameters

Called by `new_transaction()` (`app.py`), which takes the form values
`[Cuenta, Payee, Categoria, Fecha, Monto, Memo, Descripcion]`, appends the server time,
and reorders them as `[0, 6, 2, 1, 3, 4, 5, 7]`.

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

Called by `new_transfer()` (`app.py`), which takes
`[Cuenta, Payee, Fecha, Monto, Memo, Descripcion, Transferencia, MontoRec]`, appends the
server time, and reorders them as `[0, 6, 5, 1, 2, 3, 7, 4, 8]`.

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

##### `webdeletion` – 1 parameter

Called by `delete_transaction()` (`app.py`) with the hidden `ID` value:

| # | Parameter | Type | Supplied value |
|---|---|---|---|
| 1 | `in_id` | `integer` | Hidden `ID` field, filled by `selectrow()` |

#### Recreating the procedures

The bodies are application-specific and already exist in `trans_app`; dump the live
definitions with psql (`\sf webtransaction`, `\sf webtransfer`, `\sf webmodification`,
`\sf webdeletion`). The `CREATE OR REPLACE` skeletons below use the exact deployed
signatures. These are signature placeholders: they compile, but their bodies do nothing
until you restore the real logic. Do not change the argument types either, or PostgreSQL
will create an overload instead of replacing the existing procedure.

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

CREATE OR REPLACE PROCEDURE public.webdeletion(
    IN in_id integer
) LANGUAGE plpgsql AS $$ BEGIN END; $$;
```

#### Notes

- Each form must keep its current field order, because the route maps values by position:
  - `/` transaction/transfer form: `Cuenta, Payee, Categoria, Fecha, Monto, Memo, Descripcion, Transferencia, MontoRec, Operación`.
  - Edit modal: `ID, Cuenta, Transfer, Payee, Categoria, Fecha, Monto, Memo, Descripcion, Operación`.
- Blank text inputs are converted to `NULL` before the call.
- `Monto` and `MontoRec` arrive as strings and are cast to `numeric` by PostgreSQL. The
  target column `transacciones.monto` is `double precision`, so the procedure body relies
  on the implicit `numeric` to `double precision` cast.
- `Fecha` must arrive as `YYYY-MM-DDTHH:MM` (HTML `datetime-local`); the route parses it
  with `datetime.strptime(..., "%Y-%m-%dT%H:%M")` and the DB columns are
  `timestamp without time zone`.
- `in_now` is always appended by the server; it is never a form field.
- The procedure parameters are unbounded, but the underlying `transacciones` columns are
  limited: `cuenta`, `transfer`, `categoría`, `memo` are `varchar(30)`, `payee` is
  `varchar(40)`, and `description` is `varchar(255)`.
- `Operación = Buscar` and `Operación = Clear Search` do not call any procedure; they only
  update the Flask session filter.

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