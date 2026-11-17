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

Stored procedures required:
- `webtransaction` – Create a new transaction
- `webtransfer` – Create a transfer between accounts
- `webmodification` – Modify an existing transaction
- `webdeletion` – Delete a transaction

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