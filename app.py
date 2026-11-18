import datetime as dt
import io
import math
import os
import sys
import time

import numpy as np
import pandas as pd
import psycopg2
import requests
import xmltodict
from flask import Flask, render_template, request, session, redirect, url_for, send_from_directory
from sqlalchemy import create_engine

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

port_serve = 5000 if (len(sys.argv) == 1) else sys.argv[1]

# Secret key (for session signing and access control)
if port_serve == 5000:
    secret = os.environ.get("TRANSACTIONS_SECRET", "test")
else:
    secret_file = os.environ.get("TRANSACTIONS_SECRET_FILE", "./secret.txt")
    with open(secret_file, "r") as f:
        secret = f.readline().strip()

# Database credentials (from ~/.pgpass)
from os.path import expanduser
with open(expanduser("~/.pgpass"), "r") as f:
    host, port, _, user, password = f.read().split(":")
dbname = "trans_app"

# Application parameters
nb_records = 15

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

connection_string = "postgresql://{}:{}@{}:{}/{}".format(
    user, password, host, port, dbname
)
engine = create_engine(connection_string)
conn = engine.connect()


def _get_psycopg2_connection():
    """Return a new psycopg2 connection."""
    return psycopg2.connect(dbname=dbname, host=host, port=port, user=user, password=password)


# ---------------------------------------------------------------------------
# Exchange rate data loading
# ---------------------------------------------------------------------------

def load_bch_data():
    """Download BCH exchange rate Excel file, with fallback to cached copy."""
    bch_path = "static/Precio Promedio Diario del Dólar.parquet"
    bch_url = (
        "http://www.bch.hn/estadisticos/GIE/LIBTipo%20de%20cambio/"
        "Precio%20Promedio%20Diario%20del%20D%C3%B3lar.xlsx"
    )
    if os.path.exists(bch_path) and (time.time() - os.path.getmtime(bch_path)) < 86400:
        return pd.read_parquet(bch_path, engine="fastparquet")
    try:
        bch_response = requests.get(bch_url, timeout=30)
        bch_response.raise_for_status()
        bch_data = pd.read_excel(io.BytesIO(bch_response.content), header=6)[
            ["Fecha", "Compra 1/"]
        ].rename(columns={"Compra 1/": "Tasa"})
        # Drop footnote rows and coerce to clean dtypes so the parquet cache
        # holds homogeneous datetime64[ns] / float64 columns.
        bch_data = bch_data[
            bch_data["Fecha"].map(lambda x: isinstance(x, dt.datetime))
        ].copy()
        bch_data["Fecha"] = pd.to_datetime(
            bch_data["Fecha"], format="%Y-%m-%d 00:00:00"
        )
        bch_data["Tasa"] = pd.to_numeric(bch_data["Tasa"], errors="coerce")
        bch_data.to_parquet(bch_path, engine="fastparquet")
        return bch_data
    except Exception as e:
        print(f"Warning: BCH download failed ({e}), using cached file.")
        return pd.read_parquet(bch_path, engine="fastparquet")


def load_ecb_data():
    """Download ECB USD/EUR exchange rate XML, with fallback to cached copy."""
    ecb_path = "static/usd.parquet"
    ecb_url = (
        "https://www.ecb.europa.eu/stats/policy_and_exchange_rates/"
        "euro_reference_exchange_rates/html/usd.xml"
    )
    if os.path.exists(ecb_path) and (time.time() - os.path.getmtime(ecb_path)) < 86400:
        return pd.read_parquet(ecb_path, engine="fastparquet")
    try:
        ecb_response = requests.get(ecb_url, timeout=30)
        ecb_response.raise_for_status()
        eib_data = xmltodict.parse(ecb_response.content)
        usd_eur = pd.DataFrame(
            eib_data["CompactData"]["DataSet"]["Series"]["Obs"]
        ).rename(columns={"@TIME_PERIOD": "Fecha", "@OBS_VALUE": "Tasa"})[
            ["Fecha", "Tasa"]
        ]
        usd_eur["Fecha"] = pd.to_datetime(usd_eur["Fecha"], format="%Y-%m-%d")
        usd_eur.to_parquet(ecb_path, engine="fastparquet")
        return usd_eur
    except Exception as e:
        print(f"Warning: ECB download failed ({e}), using cached file.")
        usd_eur = pd.read_parquet(ecb_path, engine="fastparquet")
        return usd_eur


bch_data = load_bch_data()
hnl_usd = bch_data[
    bch_data["Fecha"].map(lambda x: isinstance(x, dt.datetime))
].copy()
hnl_usd["Fecha"] = pd.to_datetime(hnl_usd["Fecha"], format="%Y-%m-%d 00:00:00")
hnl_usd["Tasa"] = pd.to_numeric(hnl_usd["Tasa"], errors="coerce")

usd_eur = load_ecb_data().copy()
usd_eur["Fecha"] = pd.to_datetime(usd_eur["Fecha"], format="%Y-%m-%d")
usd_eur["Tasa"] = pd.to_numeric(usd_eur["Tasa"], errors="coerce")


# ---------------------------------------------------------------------------
# Currency conversion functions
# ---------------------------------------------------------------------------

def _latest_rate(data: pd.DataFrame, date: dt.datetime, column: str = "Tasa") -> float:
    """Return the most recent rate on or before ``date``."""
    rates = data.loc[data["Fecha"] <= date, column]
    if rates.empty:
        raise ValueError(f"No exchange rate available on or before {date:%Y-%m-%d}")
    return float(rates.tail(1).iloc[0])


def _convert(
    data: pd.DataFrame, rates: dict, fallback: float, multiply: bool = False
) -> pd.Series:
    """Convert ``data`` using its column 1 (amount) and column 2 (currency).

    ``rates`` maps a currency to its conversion factor. Unrecognised currencies
    use ``fallback``, matching the previous behaviour of treating them as HNL.
    """
    factors = data.iloc[:, 2].map(rates).fillna(fallback)
    amount = data.iloc[:, 1]
    return amount * factors if multiply else amount / factors


def to_eur(data: pd.DataFrame, date: dt.datetime) -> pd.Series:
    tasa_usd = _latest_rate(usd_eur, date)
    tasa_hnl = _latest_rate(hnl_usd, date) * tasa_usd
    return _convert(data, {"EUR": 1.0, "USD": tasa_usd}, tasa_hnl)


def to_hnl(data: pd.DataFrame, date: dt.datetime) -> pd.Series:
    tasa_usd = _latest_rate(hnl_usd, date)
    tasa_eur = _latest_rate(usd_eur, date) * tasa_usd
    return _convert(data, {"HNL": 1.0, "USD": tasa_usd}, tasa_eur, multiply=True)


def to_usd(data: pd.DataFrame, date: dt.datetime) -> pd.Series:
    tasa_eur = 1.0 / _latest_rate(usd_eur, date)
    tasa_hnl = _latest_rate(hnl_usd, date)
    return _convert(data, {"USD": 1.0, "EUR": tasa_eur}, tasa_hnl)


# ---------------------------------------------------------------------------
# Query helpers – parameterised WHERE clause builder
# ---------------------------------------------------------------------------

def _build_where_and_params(pars):
    """Return (where_clause, params_list) from a list of filter values.

    pars order:
      [0] Cuenta, [1] Transfer, [2] Payee, [3] Categoría,
      [4] Fecha_inicio, [5] Fecha_fin, [6] Monto, [7] Memo, [8] Descripcion
    """
    conditions = []
    params = []

    if pars[0] is not None:
        conditions.append("Cuenta = %s")
        params.append(pars[0])
    if pars[1] is not None:
        conditions.append("Transfer = %s")
        params.append(pars[1])
    if pars[2] is not None:
        conditions.append("Payee LIKE %s")
        params.append("%" + pars[2] + "%")
    if pars[3] is not None:
        conditions.append("Categoría = %s")
        params.append(pars[3])
    if pars[4] is not None:
        conditions.append("Fecha > %s")
        params.append(pars[4].replace("T", " "))
    if pars[5] is not None:
        conditions.append("Fecha < %s")
        params.append(pars[5].replace("T", " "))
    if pars[6] is not None:
        conditions.append("Monto = %s")
        params.append(str(pars[6]))
    if pars[7] is not None:
        conditions.append("Memo = %s")
        params.append(pars[7])
    if pars[8] is not None:
        conditions.append("Description LIKE %s")
        params.append("%" + pars[8] + "%")

    where_clause = " AND ".join(conditions) if conditions else ""
    return where_clause, params


# ---------------------------------------------------------------------------
# Data-fetch functions (transactional page)
# ---------------------------------------------------------------------------

def gettop10(pars, limit=None, offset=0):
    if limit is None:
        limit = nb_records
    cnxn = _get_psycopg2_connection()
    cursor = cnxn.cursor()
    if pars is None:
        cursor.execute(
            "SELECT * FROM transacciones ORDER BY Fecha DESC, Input DESC "
            "LIMIT %s OFFSET %s",
            (limit, offset),
        )
    else:
        where_clause, params = _build_where_and_params(pars)
        query = "SELECT * FROM transacciones"
        if where_clause:
            query += " WHERE " + where_clause
        query += " ORDER BY Fecha DESC, Input DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        cursor.execute(query, params)

    columns = [column[0] for column in cursor.description]
    results = []
    for row in cursor.fetchall():
        row = (v.strftime("%d-%m-%y %H:%M") if isinstance(v, dt.datetime) else v for v in row)
        row = (v.rstrip() if isinstance(v, str) else v for v in row)
        row = ("" if v is None else v for v in row)
        results.append(dict(zip(columns, row)))
    cnxn.close()
    return results


def getacts():
    cnxn = _get_psycopg2_connection()
    cursor = cnxn.cursor()
    cursor.execute(
        """SELECT "Nombre Cuenta" FROM
           (SELECT "Nombre Cuenta", count FROM
               (SELECT cuenta, count(id) AS count FROM transacciones
                WHERE input > %s GROUP BY cuenta) a
            FULL OUTER JOIN cuentas c ON a.cuenta = c."Nombre Cuenta"
            WHERE c.activa != 0)
           ORDER BY COALESCE(count, 0) DESC""",
        (dt.datetime.now() - dt.timedelta(180),),
    )
    acts = cursor.fetchall()
    cnxn.close()
    return acts


def getpayees():
    cnxn = _get_psycopg2_connection()
    cursor = cnxn.cursor()
    cursor.execute(
        """SELECT payee FROM
           (SELECT payee, count(id) AS count FROM transacciones
            WHERE input > %s GROUP BY payee ORDER BY count DESC LIMIT 100)""",
        (dt.datetime.now() - dt.timedelta(180),),
    )
    acts = cursor.fetchall()
    cnxn.close()
    return acts


def getcategs():
    cnxn = _get_psycopg2_connection()
    cursor = cnxn.cursor()
    cursor.execute("SELECT Categoría FROM Categories")
    cats = cursor.fetchall()
    cnxn.close()
    return cats


# ---------------------------------------------------------------------------
# Database write functions (stored procedures)
# ---------------------------------------------------------------------------

def new_transaction(pars):
    try:
        cnxn = _get_psycopg2_connection()
        cursor = cnxn.cursor()
        cursor.execute(
            "CALL webtransaction(%s, %s, %s, %s, %s, %s, %s, %s)",
            [pars[i] for i in [0, 6, 2, 1, 3, 4, 5, 7]],
        )
        cnxn.commit()
        cursor.close()
        cnxn.close()
    except Exception as e:
        print("Error: %s" % e)
    return "nothing"


def new_transfer(pars):
    try:
        cnxn = _get_psycopg2_connection()
        cursor = cnxn.cursor()
        cursor.execute(
            "CALL webtransfer(%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [pars[i] for i in [0, 6, 5, 1, 2, 3, 7, 4, 8]],
        )
        cnxn.commit()
        cursor.close()
        cnxn.close()
    except Exception as e:
        print("Error: %s" % e)
    return "nothing"


def modify_transaction(pars):
    try:
        cnxn = _get_psycopg2_connection()
        cursor = cnxn.cursor()
        cursor.execute(
            "CALL webmodification(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", pars
        )
        cnxn.commit()
        cursor.close()
        cnxn.close()
    except Exception as e:
        print("Error: %s" % e)
    return "nothing"


def delete_transaction(pars):
    try:
        cnxn = _get_psycopg2_connection()
        cursor = cnxn.cursor()
        cursor.execute("CALL webdeletion(%s)", pars)
        cnxn.commit()
        cursor.close()
        cnxn.close()
    except Exception as e:
        print("Error: %s" % e)
    return "nothing"


def duplicate_transaction(pars):
    try:
        cnxn = _get_psycopg2_connection()
        cursor = cnxn.cursor()
        cursor.execute("CALL webduplication(%s, %s)", pars)
        cnxn.commit()
        cursor.close()
        cnxn.close()
    except Exception as e:
        print("Error: %s" % e)
    return "nothing"


def set_account_balance(cuenta, fecha, objetivo):
    """Set an account balance at a date and report the applied adjustment."""
    cnxn = _get_psycopg2_connection()
    cursor = cnxn.cursor()
    try:
        cursor.execute("SELECT get_balance(%s, %s)", (cuenta, fecha))
        previous = cursor.fetchone()[0]
        cursor.execute(
            "CALL set_balance(%s, %s, %s)",
            (cuenta, fecha, objetivo),
        )
        cnxn.commit()
        delta = objetivo - previous
        return {
            "cuenta": cuenta,
            "fecha": fecha,
            "fecha_label": fecha.strftime("%Y-%m-%d %H:%M"),
            "previous": previous,
            "target": objetivo,
            "delta": delta,
            "changed": abs(delta) >= 0.005,
        }
    except Exception as e:
        cnxn.rollback()
        print("Error setting balance: %s" % e)
        return None
    finally:
        cursor.close()
        cnxn.close()


# ---------------------------------------------------------------------------
# Report functions
# ---------------------------------------------------------------------------

def balance(pars):
    if pars is None or pars[0:9] == [None] * 9:
        query = (
            'SELECT * FROM (SELECT Cuenta, SUM(Monto) AS Balance, '
            'Moneda, "Tipo Cuenta" FROM transacciones t '
            'JOIN cuentas c ON t.Cuenta = c."Nombre Cuenta" '
            'GROUP BY "Tipo Cuenta", Cuenta, Moneda) '
            'WHERE (Balance < -0.01 OR Balance > 0.01)'
        )
        balance_df = pd.read_sql(query, conn)
    else:
        where_clause, params = _build_where_and_params(pars)
        query = (
            'SELECT * FROM (SELECT Cuenta, SUM(Monto) AS Balance, '
            'Moneda, "Tipo Cuenta" FROM transacciones t '
            'JOIN cuentas c ON t.Cuenta = c."Nombre Cuenta"'
        )
        if where_clause:
            query += " WHERE " + where_clause
        query += (
            ' GROUP BY "Tipo Cuenta", Cuenta, Moneda) '
            'WHERE (Balance < -0.01 OR Balance > 0.01)'
        )
        balance_df = pd.read_sql(query, conn, params=tuple(params))
    now = dt.datetime.now()
    now = (
        now
        if (pars is None or pars[0:9] == [None] * 9)
        else (now if pars[5] is None else pd.to_datetime(pars[5].replace("T", " ")))
    )
    balance_df = pd.merge(
        pd.DataFrame({"cuenta": [el[0] for el in getacts()]}),
        balance_df,
        on="cuenta",
    )
    balance_df["balance_eur"] = to_eur(balance_df, now)
    return balance_df


def balance_plot(pars):
    import plotly.graph_objects as go
    import plotly.io as pio

    end = dt.datetime.today()
    end = (
        end
        if (pars is None or pars[0:9] == [None] * 9)
        else (end if pars[5] is None else pd.to_datetime(pars[5].replace("T", " ")))
    )
    start = end - pd.offsets.DateOffset(years=5)
    start = (
        start
        if (pars is None or pars[0:9] == [None] * 9)
        else (
            start
            if pars[4] is None
            else pd.to_datetime(pars[4].replace("T", " "))
        )
    )
    m_list = pd.period_range(start, end, freq="M").to_timestamp()

    par = pars.copy() if pars is not None else [None] * 9
    par[4] = None
    par[5] = m_list[0].strftime("%Y-%m-%d %H:%M")

    bal_matrix = (
        balance(par)[["Tipo Cuenta", "balance_eur"]]
        .groupby("Tipo Cuenta", as_index=False)
        .agg({"balance_eur": "sum"})
    )
    bal_matrix = bal_matrix.rename(columns={"balance_eur": m_list[0]})

    for m in m_list[1:]:
        par[5] = m.strftime("%Y-%m-%d %H:%M")
        bal = (
            balance(par)[["Tipo Cuenta", "balance_eur"]]
            .groupby("Tipo Cuenta", as_index=False)
            .agg({"balance_eur": "sum"})
        )
        bal_matrix = pd.merge(bal_matrix, bal, how="outer", on="Tipo Cuenta")
        bal_matrix = bal_matrix.rename(
            columns={"balance_eur": m.strftime("%Y-%m")}
        )

    bal_matrix = pd.concat(
        [bal_matrix["Tipo Cuenta"], bal_matrix.drop("Tipo Cuenta", axis=1)],
        axis=1,
    )

    fig = go.Figure()

    if bal_matrix.shape[0] > 1:
        fig.add_trace(
            go.Scatter(
                x=bal_matrix.columns[1:],
                y=bal_matrix.iloc[:, 1:].sum(axis=0) / 1000,
                customdata=bal_matrix.iloc[:, 1:].sum(axis=0),
                mode="lines",
                name="Total",
                hovertemplate="<b>Bal. Total</b>"
                + ": €%{customdata:,.2f}<extra></extra>",
            )
        )

    for i in range(bal_matrix.shape[0]):
        fig.add_trace(
            go.Scatter(
                x=bal_matrix.columns[1:],
                y=bal_matrix.iloc[i, 1:] / 1000,
                customdata=bal_matrix.iloc[i, 1:],
                mode="lines",
                name=bal_matrix.iloc[i, 0],
                hovertemplate=f"<b>{bal_matrix.iloc[i, 0]}</b>"
                + ": €%{customdata:,.2f}<extra></extra>",
            )
        )

    fig.update_layout(
        title="Balance Histórico",
        xaxis=dict(title="Mes", tickangle=45),
        yaxis=dict(
            title="Balance € (000's)",
            tickformat="€,.0f",
            ticksuffix="k",
            gridcolor="lightgray",
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            x=1,
            xanchor="right",
            font=dict(size=14),
        ),
    )

    plot_html = pio.to_html(fig, full_html=False, include_plotlyjs="cdn")
    return plot_html


def rep_categ(pars, type: int = 0):
    if pars is None or pars[0:9] == [None] * 9:
        query = (
            'SELECT t.Categoría, Monto, Moneda, Fecha, '
            'cat."Tipo Categoría" FROM transacciones t '
            'JOIN cuentas c ON t.Cuenta = c."Nombre Cuenta" '
            'JOIN categories cat ON t.Categoría = cat.Categoría'
        )
        if type == 1:
            query += ' WHERE cat."Tipo de Transacción" = \'Ingreso\''
        elif type == -1:
            query += ' WHERE cat."Tipo de Transacción" = \'Gasto\''
        categoria = pd.read_sql(query, conn)
    else:
        where_clause, params = _build_where_and_params(pars)
        query = (
            'SELECT t.Categoría, Monto, Moneda, Fecha, '
            'cat."Tipo Categoría" FROM transacciones t '
            'JOIN cuentas c ON t.Cuenta = c."Nombre Cuenta" '
            'JOIN categories cat ON t.Categoría = cat.Categoría'
        )
        type_conds = []
        if type == 1:
            type_conds.append('cat."Tipo de Transacción" = \'Ingreso\'')
        elif type == -1:
            type_conds.append('cat."Tipo de Transacción" = \'Gasto\'')
        if where_clause:
            type_conds.append(where_clause)
        if type_conds:
            query += " WHERE " + " AND ".join(type_conds)
        categoria = pd.read_sql(query, conn, params=tuple(params))

    now = dt.datetime.now()
    now = (
        now
        if (pars is None or pars[0:9] == [None] * 9)
        else (now if pars[5] is None else pd.to_datetime(pars[5].replace("T", " ")))
    )
    categoria["monto_eur"] = to_eur(categoria, now)
    categoria = categoria.groupby(
        ["categoría", "Tipo Categoría"], as_index=False
    ).agg({"monto_eur": "sum"})
    return categoria


def categ_plot(pars):
    import plotly.graph_objects as go
    import plotly.io as pio

    end = dt.datetime.today()
    end = (
        end
        if (pars is None or pars[0:9] == [None] * 9)
        else (end if pars[5] is None else pd.to_datetime(pars[5].replace("T", " ")))
    )
    start = end - pd.offsets.DateOffset(years=5)
    start = (
        start
        if (pars is None or pars[0:9] == [None] * 9)
        else (
            start
            if pars[4] is None
            else pd.to_datetime(pars[4].replace("T", " "))
        )
    )
    m_list = pd.period_range(start, end, freq="M").to_timestamp()

    # Process expense data
    par = pars.copy() if pars is not None else [None] * 9
    par[4] = m_list[0].strftime("%Y-%m-%d %H:%M")
    par[5] = m_list[1].strftime("%Y-%m-%d %H:%M")

    gasto_matrix = (
        rep_categ(par, -1)[["Tipo Categoría", "monto_eur"]]
        .groupby("Tipo Categoría", as_index=False)
        .agg({"monto_eur": "sum"})
    )
    gasto_matrix = gasto_matrix.rename(columns={"monto_eur": m_list[0]})

    for i in range(1, len(m_list) - 1):
        par[4] = m_list[i].strftime("%Y-%m-%d %H:%M")
        par[5] = m_list[i + 1].strftime("%Y-%m-%d %H:%M")
        gasto = (
            rep_categ(par, -1)[["Tipo Categoría", "monto_eur"]]
            .groupby("Tipo Categoría", as_index=False)
            .agg({"monto_eur": "sum"})
        )
        gasto_matrix = pd.merge(gasto_matrix, gasto, how="outer", on="Tipo Categoría")
        gasto_matrix = gasto_matrix.rename(
            columns={"monto_eur": m_list[i].strftime("%Y-%m")}
        )

    gasto_matrix = pd.concat(
        [gasto_matrix["Tipo Categoría"], gasto_matrix.drop("Tipo Categoría", axis=1)],
        axis=1,
    )

    # Process income data
    par = pars.copy() if pars is not None else [None] * 9
    par[4] = m_list[0].strftime("%Y-%m-%d %H:%M")
    par[5] = m_list[1].strftime("%Y-%m-%d %H:%M")

    ingreso_matrix = (
        rep_categ(par, 1)[["Tipo Categoría", "monto_eur"]]
        .groupby("Tipo Categoría", as_index=False)
        .agg({"monto_eur": "sum"})
    )
    ingreso_matrix = ingreso_matrix.rename(columns={"monto_eur": m_list[0]})

    for i in range(1, len(m_list) - 1):
        par[4] = m_list[i].strftime("%Y-%m-%d %H:%M")
        par[5] = m_list[i + 1].strftime("%Y-%m-%d %H:%M")
        ingreso = (
            rep_categ(par, 1)[["Tipo Categoría", "monto_eur"]]
            .groupby("Tipo Categoría", as_index=False)
            .agg({"monto_eur": "sum"})
        )
        ingreso_matrix = pd.merge(
            ingreso_matrix, ingreso, how="outer", on="Tipo Categoría"
        )
        ingreso_matrix = ingreso_matrix.rename(
            columns={"monto_eur": m_list[i].strftime("%Y-%m")}
        )

    ingreso_matrix = pd.concat(
        [
            ingreso_matrix["Tipo Categoría"],
            ingreso_matrix.drop("Tipo Categoría", axis=1),
        ],
        axis=1,
    )

    fig = go.Figure()

    # Add income bars
    if ingreso_matrix.shape[0] > 0:
        ingreso_total = ingreso_matrix.iloc[:, 1:].sum()
        fig.add_trace(
            go.Bar(
                x=gasto_matrix.columns[1:],
                y=ingreso_total / 1000,
                customdata=ingreso_total,
                name="Ingreso Total",
                marker_color="rgba(51, 102, 153, 0.8)",
                hoverinfo="skip",
            )
        )

    # Add expense bars (stacked)
    if gasto_matrix.shape[0] > 0:
        num_categories = gasto_matrix.shape[0]
        colors = [
            f"rgba({int(255*r)}, {int(255*0.3)}, {int(255*0.3)}, 0.8)"
            for r in np.linspace(0.5, 1.0, num_categories)
        ]
        for i in range(gasto_matrix.shape[0]):
            category = gasto_matrix.iloc[i, 0]
            values = gasto_matrix.iloc[i, 1:]
            fig.add_trace(
                go.Bar(
                    x=gasto_matrix.columns[1:],
                    y=values / 1000,
                    customdata=values,
                    name=category,
                    marker_color=colors[i],
                    width=1e9,
                    hovertemplate=f"<b>{category}</b>"
                    + ": €%{customdata:,.2f}<extra></extra>",
                )
            )

    # Add net income (invisible bar for hover)
    if ingreso_matrix.shape[0] > 0 and gasto_matrix.shape[0] > 0:
        ingreso_neto = (
            ingreso_matrix.iloc[:, 1:].sum() + gasto_matrix.iloc[:, 1:].sum()
        )
        fig.add_trace(
            go.Bar(
                x=gasto_matrix.columns[1:],
                y=ingreso_neto * 0,
                customdata=ingreso_neto,
                name="Ingreso Neto",
                marker_color="rgba(51, 153, 102, 0.8)",
                hovertemplate="<b>Ingreso Neto</b>"
                + ": €%{customdata:,.2f}<extra></extra>",
            )
        )

    # Add total income (invisible bar for hover)
    if ingreso_matrix.shape[0] > 0:
        ingreso_total = ingreso_matrix.iloc[:, 1:].sum()
        fig.add_trace(
            go.Bar(
                x=gasto_matrix.columns[1:],
                y=ingreso_total * 0,
                customdata=ingreso_total,
                name="Ingreso Total (hover)",
                marker_color="rgba(51, 102, 153, 0.8)",
                hovertemplate="<b>Ingreso Total</b>"
                + ": €%{customdata:,.2f}<extra></extra>",
            )
        )

    fig.update_layout(
        title="Monto Histórico",
        xaxis=dict(title="Mes", tickangle=45),
        yaxis=dict(
            title="Monto € (000's)",
            tickformat="€,.0f",
            ticksuffix="k",
            gridcolor="lightgray",
        ),
        barmode="stack",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            x=1,
            xanchor="right",
            font=dict(size=14),
        ),
        hovermode="x unified",
    )

    plot_html = pio.to_html(fig, full_html=False, include_plotlyjs="cdn")
    return plot_html


# ---------------------------------------------------------------------------
# Flask application
# ---------------------------------------------------------------------------

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secret)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/favicon.ico")
def favicon():
    """Serve the site favicon for browsers that request /favicon.ico directly."""
    return send_from_directory(app.static_folder, "favicon.ico", mimetype="image/vnd.microsoft.icon")


@app.route("/", methods=["GET", "POST"])
def index():
    if request.args.get("secret", None) != secret:
        return render_template("out.html")

    # Initialize session search if not present
    if "search" not in session:
        session["search"] = None

    active_tab = request.args.get("tab", "transaccion")
    if active_tab not in ("transaccion", "balance", "transferencia"):
        active_tab = "transaccion"
    balance_result = None
    balance_error = None

    if request.method == "POST" and len(request.form) > 0:
        operacion = request.form.get("Operación")

        if operacion == "Transacción":
            active_tab = "transaccion"
            pars = [
                request.form.get("Cuenta"),
                request.form.get("Payee"),
                request.form.get("Categoria"),
                request.form.get("Fecha"),
                request.form.get("Monto"),
                request.form.get("Memo"),
                request.form.get("Descripcion"),
                dt.datetime.now(),
            ]
            pars[3] = dt.datetime.strptime(pars[3], "%Y-%m-%dT%H:%M")
            for i in range(0, len(pars)):
                if pars[i] == "":
                    pars[i] = None
            new_transaction(pars)
        elif operacion == "Balance":
            active_tab = "balance"
            try:
                cuenta = request.form["Cuenta"]
                fecha = dt.datetime.strptime(
                    request.form["Fecha"], "%Y-%m-%dT%H:%M"
                )
                objetivo = float(request.form["Balance"])
                if not math.isfinite(objetivo):
                    raise ValueError("balance must be finite")
                balance_result = set_account_balance(cuenta, fecha, objetivo)
                if balance_result is None:
                    balance_error = (
                        "No se pudo fijar el balance. Revisa la cuenta y la fecha."
                    )
            except (KeyError, ValueError) as e:
                print("Invalid balance form: %s" % e)
                balance_error = "El balance objetivo o la fecha no son válidos."
        elif operacion == "Transferencia":
            active_tab = "transferencia"
            pars = [
                request.form.get("Cuenta"),
                request.form.get("Payee"),
                request.form.get("Fecha"),
                request.form.get("Monto"),
                request.form.get("Memo"),
                request.form.get("Descripcion"),
                request.form.get("Transferencia"),
                request.form.get("MontoRec"),
                dt.datetime.now(),
            ]
            pars[2] = dt.datetime.strptime(pars[2], "%Y-%m-%dT%H:%M")
            for i in range(0, len(pars)):
                if pars[i] == "":
                    pars[i] = None
            new_transfer(pars)
        elif operacion == "Modificación":
            trans_pars = dict(request.form)
            out = list(trans_pars.values())
            if len(out) == 9:
                pars = [out[0], out[1], "", out[2], out[3], out[4], out[5], out[6], out[7]]
            else:
                pars = [out[i] for i in [0, 1, 2, 3, 4, 5, 6, 7, 8]]
            for i in range(0, len(pars)):
                if pars[i] == "":
                    pars[i] = None
            pars[5] = dt.datetime.strptime(pars[5], "%Y-%m-%dT%H:%M")
            pars.append(dt.datetime.now())
            modify_transaction(pars)
        elif operacion == "Eliminar":
            trans_pars = dict(request.form)
            out = list(trans_pars.values())
            pars = [out[0]]
            delete_transaction(pars)
        elif operacion == "Duplicar":
            trans_pars = dict(request.form)
            out = list(trans_pars.values())
            pars = [out[0], dt.datetime.now()]
            duplicate_transaction(pars)
        elif operacion == "Buscar":
            trans_pars = dict(request.form)
            out = list(trans_pars.values())
            out[6] = float(out[6])
            out = [el if el != "" else None for el in out]
            if float(out[6]) == -0 or float(out[6]) == 0:
                out[6] = None
            session["search"] = out
        elif operacion == "Clear Search":
            session["search"] = None

    # Handle pagination parameters
    try:
        page = int(request.args.get("page", 1))
        if page < 1:
            page = 1
    except (ValueError, TypeError):
        page = 1

    limit = nb_records
    offset = (page - 1) * limit
    search = session.get("search")

    return render_template(
        "json.html",
        now=dt.datetime.now().strftime("%Y-%m-%dT%H:%M"),
        cuentas=getacts(),
        categs=getcategs(),
        payees=getpayees(),
        top=gettop10(search, limit=limit, offset=offset),
        secret=secret,
        page=page,
        limit=limit,
        active_tab=active_tab,
        balance_result=balance_result,
        balance_error=balance_error,
    )


@app.route("/report", methods=["GET", "POST"])
def report():
    if request.args.get("secret", None) != secret:
        return render_template("out.html")

    if "search" not in session:
        session["search"] = None

    if request.method == "POST" and len(request.form) > 0:
        if request.form["Operación"] == "Return":
            return redirect(url_for("index") + "?secret=" + secret)
        elif request.form["Operación"] == "Buscar":
            trans_pars = dict(request.form)
            out = list(trans_pars.values())
            out = [el if el != "" and el != "None" else None for el in out]
            out[6] = float(out[6])
            if out[6] == -0 or out[6] == 0:
                out[6] = None
            session["search"] = out
        elif request.form["Operación"] == "Clear Search":
            session["search"] = None

    search = session.get("search")
    if search is None:
        search = [None] * 9

    return render_template(
        "report.html",
        now=dt.datetime.now().strftime("%Y-%m-%dT%H:%M"),
        balance=balance(search).to_dict(orient="records"),
        rep_categs=rep_categ(search, -1).to_dict(orient="records"),
        secret=secret,
        cuentas=getacts(),
        categs=getcategs(),
        search=search,
        bal_img=balance_plot(search),
        cat_img=categ_plot(search),
    )


if __name__ == "__main__":
    print("Secret Key for Session: " + secret)
    app.run(host="0.0.0.0", port=port_serve)