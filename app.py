from flask import Flask, render_template, request, make_response
import pypyodbc as po 
import datetime as dt

# FUNCTIONS TO QUERY DATABASE FOR INFO TO SHOW IN PAGE
def gettop10(pars):
    cnxn = po.connect('driver={ODBC Driver 17 for SQL Server};\
            server=franrafa91.database.windows.net;\
            database=basic_sql;uid=reader;pwd=Test_Password; autocommit=True')
    cursor = cnxn.cursor()
    if pars == None:
        cursor.execute("SELECT TOP(10) * FROM dbo.Transacciones Order By Fecha Desc, Input Desc")
    else:
        query = "SELECT TOP(10) * FROM dbo.Transacciones WHERE "
        query = query + (("Cuenta = '"+ pars[0] + "' and ") if pars[0] != None else '')
        query = query + (("Transfer = '"+ pars[1] + "' and ") if pars[1] != None else '')
        query = query + (("Payee like '%"+ pars[2] + "%' and ") if pars[2] != None else '')
        query = query + (("Categoría = '"+ pars[3] + "' and ") if pars[3] != None else '')
        query = query + (("Fecha > '"+ pars[4].replace("T"," ") + "' and ") if pars[4] != None else '')
        query = query + (("Fecha < '"+ pars[5].replace("T"," ") + "' and ") if pars[5] != None else '')
        query = query + (("Monto = '"+ pars[6] + "' and ") if pars[6] != None else '')
        query = query + (("Memo = '"+ pars[7] + "' and ") if pars[7] != None else '')
        query = query + (("Description like '%"+ pars[8] + "%' and ") if pars[8] != None else '')
        # print(query)
        query = query[:-4] + ' Order By Fecha Desc, Input Desc'
        print(query)
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
    cnxn = po.connect('driver={ODBC Driver 17 for SQL Server};\
            server=franrafa91.database.windows.net;\
            database=basic_sql;uid=reader;pwd=Test_Password; autocommit=True')
    cursor = cnxn.cursor()
    cursor.execute("SELECT [Nombre Cuenta] from Cuentas Where Activa in (1,2,3) Order By Activa Asc")
    acts = cursor.fetchall()
    cnxn.close()
    return acts

def getcategs():
    cnxn = po.connect('driver={ODBC Driver 17 for SQL Server};\
            server=franrafa91.database.windows.net;\
            database=basic_sql;uid=reader;pwd=Test_Password; autocommit=True')
    cursor = cnxn.cursor()
    cursor.execute("Select Categoría from Categories")
    cats = cursor.fetchall()
    cnxn.close()
    return cats

# FUNCTIONS TO POST TO DATABASE
def new_transaction(pars):
    try:
        cnxn = po.connect('driver={ODBC Driver 17 for SQL Server};\
            server=franrafa91.database.windows.net;\
            database=basic_sql;uid=reader;pwd=Test_Password; autocommit=True')
                            
        cursor = cnxn.cursor()
        storedProc = "EXEC dbo.WebTransaction @Cuenta  = ?,\
            @Payee  = ?,\
            @Categoria  = ?,\
            @Fecha  = ?,\
            @Monto  = ?,\
            @Memo  = ?,\
            @Description = ?,\
            @Now  = ?"
        params = tuple(pars)
        
        cursor.execute(storedProc,params)
        cursor.close()
        del cursor
        
        cnxn.commit()
        cnxn.close()

    except Exception as e:
        print("Error: %s" % e)

    return ("nothing")

def new_transfer(pars):
    try:
        cnxn = po.connect('driver={ODBC Driver 17 for SQL Server};\
            server=franrafa91.database.windows.net;\
            database=basic_sql;uid=reader;pwd=Test_Password; autocommit=True')
                            
        cursor = cnxn.cursor()
        storedProc = "EXEC dbo.WebTransfer \
            @Cuenta  = ?,\
            @Payee  = ?,\
            @Fecha  = ?,\
            @Monto  = ?,\
            @Memo  = ?,\
            @Description = ?,\
            @Transfer = ?,\
            @Recibido = ?,\
            @Now  = ?"
        params = tuple(pars)
        
        # Execute Stored Procedure With Parameters
        cursor.execute(storedProc,params)
        # Iterate the cursor
        cursor.close()
        del cursor
        
        cnxn.commit()
        # Close the database connection
        cnxn.close()

    except Exception as e:
        print("Error: %s" % e)

    return ("nothing")

def modify_transaction(pars):
    try:
        cnxn = po.connect('driver={ODBC Driver 17 for SQL Server};\
            server=franrafa91.database.windows.net;\
            database=basic_sql;uid=reader;pwd=Test_Password; autocommit=True')
                            
        cursor = cnxn.cursor()
        storedProc = "EXEC dbo.WebModification @ID = ? ,\
            @Cuenta  = ?,\
            @Transfer = ?,\
            @Payee  = ?,\
            @Categoria  = ?,\
            @Fecha  = ?,\
            @Monto  = ?,\
            @Memo  = ?,\
            @Description = ?,\
            @Now  = ?"
        params = tuple(pars)
        
        cursor.execute(storedProc,params)
        cursor.close()
        del cursor
        
        cnxn.commit()
        cnxn.close()

    except Exception as e:
        print("Error: %s" % e)

    return ("nothing")

def delete_transaction(pars):
    try:
        cnxn = po.connect('driver={ODBC Driver 17 for SQL Server};\
            server=franrafa91.database.windows.net;\
            database=basic_sql;uid=reader;pwd=Test_Password; autocommit=True')

        cursor = cnxn.cursor()
        storedProc = "EXEC dbo.WebDeletion @ID = ?"
        params = tuple(pars)

        cursor.execute(storedProc,params)
        cursor.close()
        del cursor

        cnxn.commit()
        cnxn.close()

    except Exception as e:
        print("Error: %s" % e)

    return ("nothing") 

app = Flask(__name__, template_folder='templates', static_folder='static')
search = None

@app.route("/", methods=["GET","POST"])
def json():
    global search
    # search = None
    if request.method == "POST":
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
            print(out)
            search = out
        elif request.form['Operación'] == 'Clear Search':
            search = None
    return render_template('json.html',now=dt.datetime.now().strftime('%Y-%m-%dT%H:%M'),cuentas=getacts(),categs=getcategs(),top=gettop10(search))

if __name__ == '__main__':
    app.run()