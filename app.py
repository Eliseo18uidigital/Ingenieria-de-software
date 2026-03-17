from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'clave_secreta_autos_colombia'

def get_db_connection():
    conn = sqlite3.connect('parqueadero.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    # Tablas Sprint 1 y 2
    conn.execute('''CREATE TABLE IF NOT EXISTS Usuarios (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, rol TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS Celdas (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT UNIQUE, tipo TEXT, estado TEXT DEFAULT 'Libre')''')
    conn.execute('''CREATE TABLE IF NOT EXISTS Vehiculos (placa TEXT PRIMARY KEY, tipo TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS Registros (id INTEGER PRIMARY KEY AUTOINCREMENT, placa_vehiculo TEXT, id_celda INTEGER, hora_entrada TIMESTAMP, hora_salida TIMESTAMP, estado TEXT, FOREIGN KEY (placa_vehiculo) REFERENCES Vehiculos(placa), FOREIGN KEY (id_celda) REFERENCES Celdas(id))''')
    
    # Crear administrador por defecto si no existe
    admin = conn.execute("SELECT * FROM Usuarios WHERE username = 'admin'").fetchone()
    if not admin:
        hashed_pw = generate_password_hash('admin123')
        conn.execute("INSERT INTO Usuarios (username, password, rol) VALUES (?, ?, ?)", ('admin', hashed_pw, 'Administrador'))
    
    # Crear celdas por defecto si no existen
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

# --- RUTAS PRINCIPALES (Requieren Login) ---
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    celdas_libres = conn.execute("SELECT * FROM Celdas WHERE estado = 'Libre'").fetchall()
    todas_celdas = conn.execute("SELECT * FROM Celdas").fetchall()
    
    vehiculos_activos = conn.execute('''
        SELECT r.placa_vehiculo, r.hora_entrada, c.nombre as celda 
        FROM Registros r JOIN Celdas c ON r.id_celda = c.id 
        WHERE r.estado='Activo'
    ''').fetchall()
    
    usuarios = conn.execute("SELECT * FROM Usuarios").fetchall() if session.get('rol') == 'Administrador' else []
    conn.close()
    
    return render_template('index.html', celdas_libres=celdas_libres, todas_celdas=todas_celdas, vehiculos=vehiculos_activos, usuarios=usuarios)

# --- RUTAS DE OPERACIÓN (Sprint 1 actualizado) ---
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

@app.route('/salida', methods=['POST'])
def salida():
    if 'user_id' not in session: return redirect(url_for('login'))
    placa = request.form['placa'].upper()
    hora_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    conn = get_db_connection()
    registro = conn.execute("SELECT id_celda FROM Registros WHERE placa_vehiculo=? AND estado='Activo'", (placa,)).fetchone()
    if registro:
        conn.execute("UPDATE Registros SET hora_salida=?, estado='Finalizado' WHERE placa_vehiculo=? AND estado='Activo'", (hora_actual, placa))
        conn.execute("UPDATE Celdas SET estado = 'Libre' WHERE id = ?", (registro['id_celda'],))
        conn.commit()
    conn.close()
    return redirect(url_for('index'))

# --- RUTAS DE ADMINISTRACIÓN (Sprint 2) ---
@app.route('/crear_usuario', methods=['POST'])
def crear_usuario():
    if session.get('rol') != 'Administrador': return redirect(url_for('index'))
    username = request.form['username']
    password = generate_password_hash(request.form['password'])
    rol = request.form['rol']
    
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO Usuarios (username, password, rol) VALUES (?, ?, ?)", (username, password, rol))
        conn.commit()
    except sqlite3.IntegrityError:
        flash('El usuario ya existe')
    conn.close()
    return redirect(url_for('index'))

@app.route('/crear_celda', methods=['POST'])
def crear_celda():
    if session.get('rol') != 'Administrador': return redirect(url_for('index'))
    nombre = request.form['nombre'].upper()
    tipo = request.form['tipo']
    
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO Celdas (nombre, tipo) VALUES (?, ?)", (nombre, tipo))
        conn.commit()
    except sqlite3.IntegrityError:
        flash('La celda ya existe')
    conn.close()
    return redirect(url_for('index'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)