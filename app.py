from flask import Flask, render_template, request, make_response
import pypyodbc as po 
import datetime as dt

# FUNCTIONS TO QUERY DATABASE FOR INFO TO SHOW IN PAGE
def gettop10():
  cnxn = po.connect(#driver='{SQL Server Native Client 11.0}',\
                    server='franrafa91.database.windows.net',\
                    database='basic_sql',\
                    uid='reader',\
                    pwd='Test_Password', autocommit=True)
  cursor = cnxn.cursor()
  cursor.execute("SELECT TOP(10) * FROM dbo.Transacciones Order By Input Desc")
  results = cursor.fetchall()
  cnxn.close()
  return results

def getacts():
    cnxn = po.connect(#driver='{SQL Server Native Client 11.0}',\
                    server='franrafa91.database.windows.net',\
                    database='basic_sql',\
                    uid='reader',pwd='Test_Password',autocommit=True)
    cursor = cnxn.cursor()
    cursor.execute("SELECT [Nombre Cuenta] from Cuentas Where Activa in (1,2,3) Order By Activa Asc")
    acts = cursor.fetchall()
    cnxn.close()
    return acts

def getcategs():
    cnxn = po.connect(#driver='{SQL Server Native Client 11.0}',\
                    server='franrafa91.database.windows.net',\
                    database='basic_sql',\
                    uid='reader',pwd='Test_Password',autocommit=True)
    cursor = cnxn.cursor()
    cursor.execute("Select Categoría from Categories")
    cats = cursor.fetchall()
    cnxn.close()
    return cats

# FUNCTIONS TO POST TO DATABASE
def new_transaction(pars):
    try:
        cnxn = po.connect(#driver='{SQL Server Native Client 11.0}',\
                        server='franrafa91.database.windows.net',\
                        database='basic_sql',\
                        uid='reader',pwd='Test_Password',autocommit=True)
                            
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
        cnxn = po.connect(#driver='{SQL Server Native Client 11.0}',\
                        server='franrafa91.database.windows.net',\
                        database='basic_sql',\
                        uid='reader',pwd='Test_Password',autocommit=True)
                            
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

app = Flask(__name__, template_folder='templates', static_folder='static')
@app.route("/", methods=["GET","POST"])
def json():
    if request.method == "POST":
        if request.form['Operación'] == 'Transacción':
            trans_pars = dict(request.form)
            out = list(trans_pars.values())
            pars = [out[i] for i in [0,1,2,3,4,5,6]]
            pars.append(dt.datetime.now())
            pars[3] = dt.to_datetime(pars[3])
            for i in range(0,len(pars)):
                if pars[i] == '': pars[i]=None
            new_transaction(pars)
        elif request.form['Operación'] == 'Transferencia':
            trans_pars = dict(request.form)
            out = list(trans_pars.values())
            pars = [out[i] for i in [0,1,3,4,5,6,7,8]]
            pars.append(dt.datetime.now())
            pars[2] = dt.to_datetime(pars[2])
            for i in range(0,len(pars)):
                if pars[i] == '': pars[i]=None
            new_transfer(pars)
    return render_template('json.html',now=dt.datetime.now().strftime('%Y-%m-%dT%H:%M'),cuentas=getacts(),categs=getcategs(),top=gettop10())

if __name__ == '__main__':
    app.run()