from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import math

app = Flask(__name__)
app.secret_key = 'clave_secreta_autos_colombia'

# Tarifas por minuto (Puedes ajustarlas)
TARIFA_CARRO = 100
TARIFA_MOTO = 50

def get_db_connection():
    conn = sqlite3.connect('parqueadero.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    # Tablas
    conn.execute('''CREATE TABLE IF NOT EXISTS Usuarios (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, rol TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS Celdas (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT UNIQUE, tipo TEXT, estado TEXT DEFAULT 'Libre')''')
    conn.execute('''CREATE TABLE IF NOT EXISTS Vehiculos (placa TEXT PRIMARY KEY, tipo TEXT)''')
    # Tabla Registros actualizada con columnas de pagos
    conn.execute('''CREATE TABLE IF NOT EXISTS Registros (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        placa_vehiculo TEXT, 
        id_celda INTEGER, 
        hora_entrada TIMESTAMP, 
        hora_salida TIMESTAMP, 
        estado TEXT, 
        metodo_pago TEXT,
        total_pagado REAL,
        FOREIGN KEY (placa_vehiculo) REFERENCES Vehiculos(placa), 
        FOREIGN KEY (id_celda) REFERENCES Celdas(id)
    )''')
    
    # Datos por defecto
    admin = conn.execute("SELECT * FROM Usuarios WHERE username = 'admin'").fetchone()
    if not admin:
        hashed_pw = generate_password_hash('admin123')
        conn.execute("INSERT INTO Usuarios (username, password, rol) VALUES (?, ?, ?)", ('admin', hashed_pw, 'Administrador'))
    
    if conn.execute("SELECT COUNT(*) FROM Celdas").fetchone()[0] == 0:
        celdas_iniciales = [('A1', 'Carro'), ('A2', 'Carro'), ('M1', 'Moto'), ('M2', 'Moto')]
        for nombre, tipo in celdas_iniciales:
            conn.execute("INSERT INTO Celdas (nombre, tipo) VALUES (?, ?)", (nombre, tipo))
            
    conn.commit()
    conn.close()

# --- RUTAS DE AUTENTICACIÓN ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM Usuarios WHERE username = ?", (username,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['rol'] = user['rol']
            return redirect(url_for('index'))
        else:
            flash('Credenciales incorrectas')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- RUTAS PRINCIPALES ---
@app.route('/')
def index():
    if 'user_id' not in session: return redirect(url_for('login'))
        
    conn = get_db_connection()
    celdas_libres = conn.execute("SELECT * FROM Celdas WHERE estado = 'Libre'").fetchall()
    todas_celdas = conn.execute("SELECT * FROM Celdas").fetchall()
    
    vehiculos_activos = conn.execute('''
        SELECT r.id as registro_id, r.placa_vehiculo, r.hora_entrada, c.nombre as celda 
        FROM Registros r JOIN Celdas c ON r.id_celda = c.id 
        WHERE r.estado='Activo'
    ''').fetchall()
    
    usuarios = conn.execute("SELECT * FROM Usuarios").fetchall() if session.get('rol') == 'Administrador' else []
    conn.close()
    
    return render_template('index.html', celdas_libres=celdas_libres, todas_celdas=todas_celdas, vehiculos=vehiculos_activos, usuarios=usuarios)

# --- OPERACIONES ---
@app.route('/entrada', methods=['POST'])
def entrada():
    if 'user_id' not in session: return redirect(url_for('login'))
    placa = request.form['placa'].upper()
    tipo = request.form['tipo']
    id_celda = request.form['id_celda']
    hora_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    conn = get_db_connection()
    conn.execute("INSERT OR IGNORE INTO Vehiculos (placa, tipo) VALUES (?, ?)", (placa, tipo))
    conn.execute("INSERT INTO Registros (placa_vehiculo, id_celda, hora_entrada, estado) VALUES (?, ?, ?, 'Activo')", (placa, id_celda, hora_actual))
    conn.execute("UPDATE Celdas SET estado = 'Ocupada' WHERE id = ?", (id_celda,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/liquidar/<int:id_registro>', methods=['GET', 'POST'])
def liquidar(id_registro):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    
    # Obtener datos del registro, vehículo y celda
    registro = conn.execute('''
        SELECT r.*, v.tipo, c.nombre as celda_nombre 
        FROM Registros r 
        JOIN Vehiculos v ON r.placa_vehiculo = v.placa 
        JOIN Celdas c ON r.id_celda = c.id
        WHERE r.id = ? AND r.estado = 'Activo'
    ''', (id_registro,)).fetchone()
    
    if not registro:
        conn.close()
        return redirect(url_for('index'))

    # Cálculos de tiempo
    fmt = "%Y-%m-%d %H:%M:%S"
    hora_entrada = datetime.strptime(registro['hora_entrada'], fmt)
    hora_salida_dt = datetime.now()
    hora_salida_str = hora_salida_dt.strftime(fmt)
    
    minutos = math.ceil((hora_salida_dt - hora_entrada).total_seconds() / 60)
    if minutos == 0: minutos = 1 # Cobro mínimo de 1 minuto
    
    tarifa_aplicada = TARIFA_CARRO if registro['tipo'] == 'Carro' else TARIFA_MOTO
    total_pagar = minutos * tarifa_aplicada

    if request.method == 'POST':
        metodo = request.form['metodo_pago']
        # Actualizar registro (Sprint 3)
        conn.execute('''
            UPDATE Registros 
            SET hora_salida = ?, estado = 'Pagado', metodo_pago = ?, total_pagado = ? 
            WHERE id = ?
        ''', (hora_salida_str, metodo, total_pagar, id_registro))
        # Liberar celda (Sprint 2)
        conn.execute("UPDATE Celdas SET estado = 'Libre' WHERE id = ?", (registro['id_celda'],))
        conn.commit()
        conn.close()
        return redirect(url_for('index'))
        
    conn.close()
    return render_template('liquidar.html', registro=registro, hora_salida=hora_salida_str, minutos=minutos, total=total_pagar)

# --- ADMINISTRACIÓN ---
@app.route('/crear_usuario', methods=['POST'])
def crear_usuario():
    if session.get('rol') != 'Administrador': return redirect(url_for('index'))
    try:
        conn = get_db_connection()
        conn.execute("INSERT INTO Usuarios (username, password, rol) VALUES (?, ?, ?)", 
                     (request.form['username'], generate_password_hash(request.form['password']), request.form['rol']))
        conn.commit()
    except sqlite3.IntegrityError:
        flash('El usuario ya existe')
    finally:
        conn.close()
    return redirect(url_for('index'))

@app.route('/crear_celda', methods=['POST'])
def crear_celda():
    if session.get('rol') != 'Administrador': return redirect(url_for('index'))
    try:
        conn = get_db_connection()
        conn.execute("INSERT INTO Celdas (nombre, tipo) VALUES (?, ?)", (request.form['nombre'].upper(), request.form['tipo']))
        conn.commit()
    except sqlite3.IntegrityError:
        flash('La celda ya existe')
    finally:
        conn.close()
    return redirect(url_for('index'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)