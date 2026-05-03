from flask import Flask, render_template, request, make_response
from flask import redirect, url_for
import psycopg2
import sys, secrets#, os
import datetime as dt
import pandas as pd
import numpy as np

## Connection Parameters
port_serve = 5000 if (len(sys.argv) == 1) else sys.argv[1]
if (port_serve == 5000):
    secret = "test"
else: #secrets.token_urlsafe(6)
    with open('./secret.txt','r') as file:
        secret = file.readline().strip('\n')

from os.path import expanduser
with open(expanduser('~/.pgpass'), 'r') as f:
    host, port, _, user, password = f.read().split(':')
dbname = 'trans_app'

## Application Parameters
#os.environ['PGPASSFILE'] = '/'+user+'/.pgpass'
nb_records = 50


## Create Connection
from sqlalchemy.engine import URL
from sqlalchemy import create_engine
connection_string = 'postgresql://{}:{}@{}:{}/{}'.format(user, password, host, port, dbname)
engine = create_engine(connection_string)
conn = engine.connect()

# TRANSACTIONAL PAGE
def gettop10(pars, limit=None, offset=0):
    if limit is None:
        limit = nb_records
    cnxn = psycopg2.connect(dbname=dbname, host=host, port=port)
    cursor = cnxn.cursor()
    if pars == None:
        cursor.execute("SELECT * FROM transacciones Order By Fecha Desc, Input Desc limit {} offset {}".format(limit, offset))
    else:
        query = "SELECT * FROM Transacciones WHERE "
        query = query + (("Cuenta = '"+ pars[0] + "' and ") if pars[0] != None else '')
        query = query + (("Transfer = '"+ pars[1] + "' and ") if pars[1] != None else '')
        query = query + (("Payee like '%"+ pars[2] + "%' and ") if pars[2] != None else '')
        query = query + (("Categoría = '"+ pars[3] + "' and ") if pars[3] != None else '')
        query = query + (("Fecha > '"+ pars[4].replace("T"," ") + "' and ") if pars[4] != None else '')
        query = query + (("Fecha < '"+ pars[5].replace("T"," ") + "' and ") if pars[5] != None else '')
        query = query + (("Monto = '"+ str(pars[6]) + "' and ") if pars[6] != None else '')
        query = query + (("Memo = '"+ pars[7] + "' and ") if pars[7] != None else '')
        query = query + (("Description like '%"+ pars[8] + "%' and ") if pars[8] != None else '')
        query = query[:-4] + ' Order By Fecha Desc, Input Desc '
        query = query + 'limit {} offset {}'.format(limit, offset)
        #print(query)
        cursor.execute(query)
    columns = [column[0] for column in cursor.description]
    results = []
    for row in cursor.fetchall():
        row = (v.strftime('%d-%m-%y %H:%M') if isinstance(v,dt.datetime) else v for v in row)
        row = (v.rstrip() if isinstance(v,str) else v for v in row)
        row = ('' if v is None else v for v in row)
        # print(v for v in row)
        results.append(dict(zip(columns, row)))
    # results = cursor.fetchall()
    cnxn.close()
    # print(results[0])
    return results

def getacts():
    cnxn = psycopg2.connect(dbname=dbname, host=host, port=port)
    cursor = cnxn.cursor()
    cursor.execute("""select "Nombre Cuenta" from
                    (select "Nombre Cuenta", count from
                        (select cuenta, count(id) as count from transacciones
                        where input>\'{:%Y-%m-%d}\' group by cuenta) a
                    full outer join cuentas c on a.cuenta = c."Nombre Cuenta" where c.activa != 0)
                    order by coalesce(count,0) desc;"""\
                   .format(dt.datetime.now()-dt.timedelta(180)))
    acts = cursor.fetchall()
    cnxn.close()
    return acts

def getpayees():
    cnxn = psycopg2.connect(dbname=dbname, host=host, port=port)
    cursor = cnxn.cursor()
    cursor.execute("select payee from \
                    (select payee, count(id) as count from transacciones where \
                    input>'{:%Y-%m-%d}' group by payee order by count desc limit 100);"\
                   .format(dt.datetime.now()-dt.timedelta(180)))
    acts = cursor.fetchall()
    cnxn.close()
    return acts

def getcategs():
    cnxn = psycopg2.connect(dbname=dbname, host=host, port=port)
    cursor = cnxn.cursor()
    cursor.execute("Select Categoría from Categories")
    cats = cursor.fetchall()
    cnxn.close()
    return cats

# FUNCTIONS TO POST TO DATABASE
def new_transaction(pars):
    try:
        cnxn = psycopg2.connect(dbname=dbname, host=host, port=port)
        cursor = cnxn.cursor()
        cursor.execute("CALL webtransaction(%s, %s, %s, %s, %s, %s, %s, %s);",
                       [pars[i] for i in [0,6,2,1,3,4,5,7]])
        cnxn.commit()
        cursor.close()
        del cursor
        cnxn.close()

    except Exception as e:
        print("Error: %s" % e)

    return ("nothing")

def new_transfer(pars):
    try:
        cnxn = psycopg2.connect(dbname=dbname, host=host, port=port)
        cursor = cnxn.cursor()
        cursor.execute("CALL webtransfer(%s, %s, %s, %s, %s, %s, %s, %s, %s);",
                       [pars[i] for i in [0,6,5,1,2,3,7,4,8]])
        cnxn.commit()
        cursor.close()
        del cursor
        cnxn.close()

    except Exception as e:
        print("Error: %s" % e)

    return ("nothing")

def modify_transaction(pars):
    try:
        cnxn = psycopg2.connect(dbname=dbname, host=host, port=port)
        cursor = cnxn.cursor()
        cursor.execute("CALL webmodification(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);",
                       pars) #no reorganizing necessary
        cnxn.commit()
        cursor.close()
        del cursor
        cnxn.close()

    except Exception as e:
        print("Error: %s" % e)

    return ("nothing")

def delete_transaction(pars):
    try:
        cnxn = psycopg2.connect(dbname=dbname, host=host, port=port)
        cursor = cnxn.cursor()
        cursor.execute("CALL webdeletion(%s);",
                       pars) #no reorganizing necessary
        cnxn.commit()
        cursor.close()
        del cursor
        cnxn.close()

    except Exception as e:
        print("Error: %s" % e)

    return ("nothing") 

app = Flask(__name__, template_folder='templates', static_folder='static')
search = None


@app.route("/", methods=["GET","POST"])
def index():
    if request.args.get('secret', None) != secret:
        return render_template('out.html')
    global search
    # search = None
    if request.method == "POST" and len(request.form)>0:
        if request.form['Operación'] == 'Transacción':
            trans_pars = dict(request.form)
            out = list(trans_pars.values())
            pars = [out[i] for i in [0,1,2,3,4,5,6]]
            pars.append(dt.datetime.now())
            pars[3] = dt.datetime.strptime(pars[3],'%Y-%m-%dT%H:%M')
            for i in range(0,len(pars)):
                if pars[i] == '': pars[i]=None
            new_transaction(pars)
        elif request.form['Operación'] == 'Transferencia':
            trans_pars = dict(request.form)
            out = list(trans_pars.values())
            pars = [out[i] for i in [0,1,3,4,5,6,7,8]]
            pars.append(dt.datetime.now())
            pars[2] = dt.datetime.strptime(pars[2],'%Y-%m-%dT%H:%M')
            for i in range(0,len(pars)):
                if pars[i] == '': pars[i]=None
            new_transfer(pars)
        elif request.form['Operación'] == 'Modificación':
            trans_pars = dict(request.form)
            out = list(trans_pars.values())
            if (len(out) == 9):
                pars = [out[0], out[1], '', out[2], out[3], out[4], out[5], out[6], out[7]]
            else:
                pars = [out[i] for i in [0,1,2,3,4,5,6,7,8]]
            for i in range(0,len(pars)):
                if pars[i] == '': pars[i]=None
            pars[5] = dt.datetime.strptime(pars[5],'%Y-%m-%dT%H:%M')
            pars.append(dt.datetime.now())
            # print(pars)
            modify_transaction(pars)
        elif request.form['Operación'] == 'Eliminar':
            trans_pars = dict(request.form)
            out = list(trans_pars.values())
            pars = [out[0]]
            delete_transaction(pars)
        elif request.form['Operación'] == 'Buscar':
            trans_pars = dict(request.form)
            out = list(trans_pars.values())
            out[6] = float(out[6])
            out = [el if el != '' else None for el in out]
            if (float(out[6])==-0 or float(out[6])==0):
                out[6] = None
            #print(out)
            search = out
        elif request.form['Operación'] == 'Clear Search':
            search = None
        #elif request.form['Operación'] == 'Go to Reports':
        #    return redirect(url_for('report'))
    # Handle pagination parameters
    try:
        page = int(request.args.get('page', 1))
        if page < 1:
            page = 1
    except (ValueError, TypeError):
        page = 1
    
    limit = nb_records  # 50 records per page
    offset = (page - 1) * limit
    
    return render_template('json.html', now=dt.datetime.now().strftime('%Y-%m-%dT%H:%M'), cuentas=getacts(), categs=getcategs(), payees=getpayees(), top=gettop10(search, limit=limit, offset=offset), secret=secret, page=page, limit=limit)

## REPORTING PAGE

import xmltodict, requests
hnl_usd = None
usd_eur = None

bch_data = pd.read_excel("http://www.bch.hn/estadisticos/GIE/LIBTipo%20de%20cambio/Precio%20Promedio%20Diario%20del%20D%C3%B3lar.xlsx",header=6)[["Fecha","Compra 1/"]].rename(columns={"Compra 1/":"Tasa"})
hnl_usd = bch_data[bch_data["Fecha"].map(lambda x: isinstance(x,dt.datetime))]
hnl_usd["Fecha"] = pd.to_datetime(hnl_usd["Fecha"], format="%Y-%m-%d 00:00:00")

eib_data = xmltodict.parse(requests.get("https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/usd.xml").content)
usd_eur = pd.DataFrame(eib_data['CompactData']['DataSet']['Series']['Obs']).rename(columns={'@TIME_PERIOD':'Fecha','@OBS_VALUE':'Tasa'})[['Fecha','Tasa']]
usd_eur["Fecha"] = pd.to_datetime(usd_eur["Fecha"],format='%Y-%m-%d')

def to_eur(data:pd.DataFrame, date:dt.datetime) -> float:
    tasa_usd = float(usd_eur[usd_eur["Fecha"]-date <= dt.timedelta(0)].tail(1)["Tasa"])
    tasa_hnl = float(hnl_usd[hnl_usd["Fecha"]-date <= dt.timedelta(0)].tail(1)["Tasa"])*tasa_usd
    return data.apply(lambda x: x[1]/(1 if x[2]=="EUR" else (tasa_usd if x[2]=="USD" else tasa_hnl)), axis=1)

def to_hnl(data:pd.DataFrame, date:dt.datetime) -> float:
    tasa_usd = float(hnl_usd[hnl_usd["Fecha"]-date <= dt.timedelta(0)].tail(1)["Tasa"])
    tasa_eur = float(usd_eur[usd_eur["Fecha"]-date <= dt.timedelta(0)].tail(1)["Tasa"])*tasa_usd
    return data.apply(lambda x: x[1]*(1 if x[2]=="HNL" else (tasa_usd if x[2]=="USD" else tasa_eur)), axis=1)

def to_usd(data:pd.DataFrame, date:dt.datetime) -> float:
    tasa_eur = 1./float(usd_eur[usd_eur["Fecha"]-date <= dt.timedelta(0)].tail(1)["Tasa"])
    tasa_hnl = float(hnl_usd[hnl_usd["Fecha"]-date <= dt.timedelta(0)].tail(1)["Tasa"])
    return data.apply(lambda x: x[1]/(1 if x[2]=="USD" else (tasa_eur if x[2]=="EUR" else tasa_hnl)), axis=1)

def balance(pars):
    if pars == None or pars[0:9] == [None]*9:
        query = 'SELECT * from (SELECT Cuenta, sum(Monto) as Balance, Moneda, "Tipo Cuenta" FROM transacciones t join cuentas c on t.Cuenta = c."Nombre Cuenta" Group by "Tipo Cuenta", Cuenta, Moneda) Where (Balance <-0.01 or Balance >0.01)'
        balance = pd.read_sql(query,conn)
    else:
        query = 'SELECT * from (Select Cuenta, sum(Monto) as Balance, Moneda, "Tipo Cuenta" FROM transacciones t join cuentas c on t.Cuenta = c."Nombre Cuenta" WHERE '
        query = query + (("Cuenta = '"+ pars[0] + "' and ") if pars[0] != None else '')
        query = query + (("Transfer = '"+ pars[1] + "' and ") if pars[1] != None else '')
        query = query + (("Payee like '%"+ pars[2] + "%' and ") if pars[2] != None else '')
        query = query + (("Categoría = '"+ pars[3] + "' and ") if pars[3] != None else '')
        query = query + (("Fecha > '"+ pars[4].replace("T"," ") + "' and ") if pars[4] != None else '')
        query = query + (("Fecha < '"+ pars[5].replace("T"," ") + "' and ") if pars[5] != None else '')
        query = query + (("Monto = '"+ pars[6] + "' and ") if pars[6] != None else '')
        query = query + (("Memo = '"+ pars[7] + "' and ") if pars[7] != None else '')
        query = query + (("Description like '%"+ pars[8] + "%' and ") if pars[8] != None else '')
        query = query[:-4] + 'Group by "Tipo Cuenta", Cuenta, Moneda) where (Balance <-0.01 or Balance >0.01)'
        balance = pd.read_sql(query,conn)
    now = dt.datetime.now()
    now = now if (pars == None or pars[0:9] == [None]*9) else (now if pars[5] == None else pd.to_datetime(pars[5].replace("T"," ")))
    balance = pd.merge(pd.DataFrame({'cuenta':[el[0] for el in getacts()]}),balance,on='cuenta')
    balance["balance_eur"] = to_eur(balance,now)
    return balance

def balance_plot(pars):
    import plotly.graph_objects as go
    import pandas as pd
    import datetime as dt
    import plotly.io as pio
    
    end = dt.datetime.today()
    end = end if (pars == None or pars[0:9] == [None]*9) else (end if pars[5] == None else pd.to_datetime(pars[5].replace("T"," ")))
    start = end - pd.offsets.DateOffset(years=5)
    start = start if (pars == None or pars[0:9] == [None]*9) else (start if pars[4] == None else pd.to_datetime(pars[4].replace("T"," ")))
    m_list = pd.period_range(start, end, freq='M').to_timestamp()
    
    par = pars.copy()
    par[4] = None
    par[5] = m_list[0].strftime("%Y-%m-%d %H:%M")
    
    bal_matrix = balance(par)[['Tipo Cuenta','balance_eur']].groupby('Tipo Cuenta', as_index=False).agg({'balance_eur':'sum'})
    bal_matrix = bal_matrix.rename(columns={'balance_eur':m_list[0]})
    
    for m in m_list[1:]:
        par[5] = m.strftime("%Y-%m-%d %H:%M")
        bal = balance(par)[['Tipo Cuenta','balance_eur']].groupby('Tipo Cuenta', as_index=False).agg({'balance_eur':'sum'})
        bal_matrix = pd.merge(bal_matrix, bal, how='outer', on='Tipo Cuenta')
        bal_matrix = bal_matrix.rename(columns={'balance_eur':m.strftime("%Y-%m")})
    
    bal_matrix = pd.concat([bal_matrix["Tipo Cuenta"], bal_matrix.drop("Tipo Cuenta", axis=1)], axis=1)
    
    # Create Plotly figure
    fig = go.Figure()
    
    # Add total line if there's more than one account type
    if bal_matrix.shape[0] > 1:
        fig.add_trace(go.Scatter(
            x=bal_matrix.columns[1:],
            y=bal_matrix.iloc[:, 1:].sum(axis=0)/1000,
            customdata=bal_matrix.iloc[:, 1:].sum(axis=0),
            mode='lines',
            name='Total',
            hovertemplate=f'<b>Bal. Total</b>' +
                        ': €%{customdata:,.2f}<extra></extra>'
        ))
    
    # Add individual account type lines
    for i in range(bal_matrix.shape[0]):
        fig.add_trace(go.Scatter(
            x=bal_matrix.columns[1:],
            y=bal_matrix.iloc[i, 1:]/1000,
            customdata=bal_matrix.iloc[i, 1:], 
            mode='lines',
            name=bal_matrix.iloc[i, 0],
            hovertemplate=f'<b>{bal_matrix.iloc[i, 0]}</b>' +
                ': €%{customdata:,.2f}<extra></extra>'
        ))
    
    # Update layout
    fig.update_layout(
        title="Balance Histórico",
        xaxis=dict(
            title="Mes",
            tickangle=45
        ),
        yaxis=dict(
            title="Balance € (000's)",
            tickformat="€,.0f",
            ticksuffix="k",
            gridcolor='lightgray'
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            x=1,
            xanchor="right",
            font=dict(size=14)
        )
    )
    
    # Convert to HTML for Flask
    plot_html = pio.to_html(fig, full_html=False, include_plotlyjs='cdn')
    
    return plot_html

def rep_categ(pars,type:int=0):
    if pars == None or pars[0:9] == [None]*9:
        query = 'SELECT t.Categoría, Monto, Moneda, Fecha, cat."Tipo Categoría" FROM transacciones t join cuentas c on t.Cuenta = c."Nombre Cuenta" join categories cat on t.categoría = cat.categoría'
        query = query + (' Where cat."Tipo de Transacción"=\'Ingreso\'' if type==1 else "")
        query = query + (' Where cat."Tipo de Transacción"=\'Gasto\'' if type==-1 else "")
        categoria = pd.read_sql(query,conn)
    else:
        query = 'SELECT t.Categoría, Monto, Moneda, Fecha, cat."Tipo Categoría" FROM transacciones t join cuentas c on t.Cuenta = c."Nombre Cuenta" join categories cat on t.categoría = cat.categoría WHERE '
        query = query + ('cat."Tipo de Transacción"=\'Ingreso\' and ' if type==1 else "")
        query = query + ('cat."Tipo de Transacción"=\'Gasto\' and ' if type==-1 else "")
        query = query + (("Cuenta = '"+ pars[0] + "' and ") if pars[0] != None else '')
        query = query + (("Transfer = '"+ pars[1] + "' and ") if pars[1] != None else '')
        query = query + (("Payee like '%"+ pars[2] + "%' and ") if pars[2] != None else '')
        query = query + (("t.Categoría = '"+ pars[3] + "' and ") if pars[3] != None else '')
        query = query + (("Fecha > '"+ pars[4].replace("T"," ") + "' and ") if pars[4] != None else '')
        query = query + (("Fecha < '"+ pars[5].replace("T"," ") + "' and ") if pars[5] != None else '')
        query = query + (("Monto = '"+ pars[6] + "' and ") if pars[6] != None else '')
        query = query + (("Memo = '"+ pars[7] + "' and ") if pars[7] != None else '')
        query = query + (("Description like '%"+ pars[8] + "%' and ") if pars[8] != None else '')
        query = query[:-4]
        categoria = pd.read_sql(query,conn)
    now = dt.datetime.now()
    now = now if (pars == None or pars[0:9] == [None]*9) else (now if pars[5] == None else pd.to_datetime(pars[5].replace("T"," ")))
    categoria["monto_eur"] = to_eur(categoria,now)
    categoria = categoria.groupby(['categoría','Tipo Categoría'],as_index=False).agg({"monto_eur":'sum'})
    return categoria

def categ_plot(pars):
    import plotly.graph_objects as go
    import pandas as pd
    import datetime as dt
    import numpy as np
    import plotly.io as pio
    
    end = dt.datetime.today()
    end = end if (pars == None or pars[0:9] == [None]*9) else (end if pars[5] == None else pd.to_datetime(pars[5].replace("T"," ")))
    start = end - pd.offsets.DateOffset(years=5)
    start = start if (pars == None or pars[0:9] == [None]*9) else (start if pars[4] == None else pd.to_datetime(pars[4].replace("T"," ")))
    m_list = pd.period_range(start, end, freq='M').to_timestamp()
    
    # Process expense data
    par = pars.copy()
    par[4] = m_list[0].strftime("%Y-%m-%d %H:%M")
    par[5] = m_list[1].strftime("%Y-%m-%d %H:%M")
    
    gasto_matrix = rep_categ(par, -1)[['Tipo Categoría', 'monto_eur']].groupby('Tipo Categoría', as_index=False).agg({'monto_eur': 'sum'})
    gasto_matrix = gasto_matrix.rename(columns={'monto_eur': m_list[0]})
    
    for i in range(1, len(m_list)-1):
        par[4] = m_list[i].strftime("%Y-%m-%d %H:%M")
        par[5] = m_list[i+1].strftime("%Y-%m-%d %H:%M")
        gasto = rep_categ(par, -1)[['Tipo Categoría', 'monto_eur']].groupby('Tipo Categoría', as_index=False).agg({'monto_eur': 'sum'})
        gasto_matrix = pd.merge(gasto_matrix, gasto, how='outer', on='Tipo Categoría')
        gasto_matrix = gasto_matrix.rename(columns={'monto_eur': m_list[i].strftime("%Y-%m")})
    
    gasto_matrix = pd.concat([gasto_matrix["Tipo Categoría"], gasto_matrix.drop("Tipo Categoría", axis=1)], axis=1)
    
    # Process income data
    par = pars.copy()
    par[4] = m_list[0].strftime("%Y-%m-%d %H:%M")
    par[5] = m_list[1].strftime("%Y-%m-%d %H:%M")
    
    ingreso_matrix = rep_categ(par, 1)[['Tipo Categoría', 'monto_eur']].groupby('Tipo Categoría', as_index=False).agg({'monto_eur': 'sum'})
    ingreso_matrix = ingreso_matrix.rename(columns={'monto_eur': m_list[0]})
    
    for i in range(1, len(m_list)-1):
        par[4] = m_list[i].strftime("%Y-%m-%d %H:%M")
        par[5] = m_list[i+1].strftime("%Y-%m-%d %H:%M")
        ingreso = rep_categ(par, 1)[['Tipo Categoría', 'monto_eur']].groupby('Tipo Categoría', as_index=False).agg({'monto_eur': 'sum'})
        ingreso_matrix = pd.merge(ingreso_matrix, ingreso, how='outer', on='Tipo Categoría')
        ingreso_matrix = ingreso_matrix.rename(columns={'monto_eur': m_list[i].strftime("%Y-%m")})
    
    ingreso_matrix = pd.concat([ingreso_matrix["Tipo Categoría"], ingreso_matrix.drop("Tipo Categoría", axis=1)], axis=1)
    
    # Create Plotly figure
    fig = go.Figure()
    
    # Add income bars if available
    if ingreso_matrix.shape[0] > 0:
        ingreso_total = ingreso_matrix.iloc[:, 1:].sum()
        fig.add_trace(go.Bar(
            x=gasto_matrix.columns[1:],
            y=ingreso_total/1000,
            customdata=ingreso_total,
            name="Ingreso Total",
            marker_color='rgba(51, 102, 153, 0.8)',
            #width=0.7,  # Adjust bar width
            hoverinfo='skip'
        ))
    
    # Add expense bars if available
    if gasto_matrix.shape[0] > 0:
       
        # Generate colors for expense categories
        num_categories = gasto_matrix.shape[0]
        colors = [f'rgba({int(255*r)}, {int(255*0.3)}, {int(255*0.3)}, 0.8)' 
                 for r in np.linspace(0.5, 1.0, num_categories)]
        
        # Add each expense category as a stacked bar
        for i in range(gasto_matrix.shape[0]):
            category = gasto_matrix.iloc[i, 0]
            values = gasto_matrix.iloc[i, 1:]
            
            fig.add_trace(go.Bar(
                x=gasto_matrix.columns[1:],
                y=values/1000,
                customdata = values,
                name=category,
                marker_color=colors[i],
                width=1e9,  # Slightly narrower than income bars
                #base=base,  # Stack on top of previous bars
                hovertemplate=f'<b>{category}</b>' +
                              ': €%{customdata:,.2f}<extra></extra>'
            ))

    # Add Net Income Result
    if ingreso_matrix.shape[0] > 0 and gasto_matrix.shape[0] > 0:
        ingreso_neto = ingreso_matrix.iloc[:, 1:].sum() + gasto_matrix.iloc[:, 1:].sum()
        fig.add_trace(go.Bar(
            x=gasto_matrix.columns[1:],
            y=ingreso_neto*0,
            customdata = ingreso_neto,
            name="Ingreso Total",
            marker_color='rgba(51, 153, 102, 0.8)',
            #width=0.7,  # Adjust bar width
            hovertemplate='<b>Ingreso Neto</b>' +
                          ': €%{customdata:,.2f}<extra></extra>'    # Add income bars if available
        ))

    # Add Total Income
    if ingreso_matrix.shape[0] > 0:
        ingreso_total = ingreso_matrix.iloc[:, 1:].sum()
        fig.add_trace(go.Bar(
            x=gasto_matrix.columns[1:],
            y=ingreso_total*0,
            customdata = ingreso_total,
            name="Ingreso Total",
            marker_color='rgba(51, 102, 153, 0.8)',
            #width=0.7,  # Adjust bar width
            hovertemplate='<b>Ingreso Total</b>' +
                          ': €%{customdata:,.2f}<extra></extra>'    # Add income bars if available
        ))

    # Update layout
    fig.update_layout(
        title="Monto Histórico",
        xaxis=dict(
            title="Mes",
            tickangle=45
        ),
        yaxis=dict(
            title="Monto € (000's)",
            tickformat="€,.0f",
            ticksuffix="k",
            gridcolor='lightgray'
        ),
        barmode='stack',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            x=1,
            xanchor="right",
            font=dict(size=14)
        ),
        hovermode="x unified"
    )
    
    # Convert to HTML
    plot_html = pio.to_html(fig, full_html=False, include_plotlyjs='cdn')
    
    return plot_html

@app.route("/report", methods=["GET","POST"])
def report():
    if request.args.get('secret', None) != secret:
        return render_template('out.html')
    global search
    if request.method == "POST" and len(request.form)>0:
        if request.form['Operación'] == 'Return':
            return redirect(url_for('index')+'?secret='+secret)
        elif request.form['Operación'] == 'Buscar':
            trans_pars = dict(request.form)
            out = list(trans_pars.values())
            out = [el if el != '' and el!= 'None' else None for el in out]
            search = out
            #print(search)
            out[6] = float(out[6])
            if (out[6]==-0 or out[6]==0):
                out[6] = None
            #print(out)
            #print(search)
        elif request.form['Operación'] == 'Clear Search':
            search = None
    if search == None:
        search = [None]*9
    return render_template('report.html',now=dt.datetime.now().strftime('%Y-%m-%dT%H:%M'),balance=balance(search).to_dict(orient='records'), rep_categs=rep_categ(search,-1).to_dict(orient='records'), secret=secret, cuentas=getacts(), categs=getcategs(), search = search, bal_img=balance_plot(search), cat_img=categ_plot(search))


if __name__ == '__main__':
    print("Secret Key for Session: "+secret)
    app.run(host="0.0.0.0", port=port_serve)