from flask import Flask, request, session, redirect, render_template, render_template_string, send_from_directory
from flask_session import Session
from dotenv import load_dotenv
import os
load_dotenv()
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2, psycopg2.extras
import math, datetime
from functools import wraps
print(generate_password_hash('admin123'))

# Dapatkan path absolut untuk template dan static
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')
STATIC_DIR = os.path.join(os.path.dirname(BASE_DIR), 'public')

app = Flask(__name__,
            template_folder=TEMPLATE_DIR,
            static_folder=STATIC_DIR)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default-secret-key')
app.config['SESSION_TYPE'] = 'sqlalchemy'  # Menggunakan database untuk session
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SERVER_NAME'] = None  # Penting untuk Netlify Functions

# Konfigurasi DB dari environment
conn = psycopg2.connect(os.environ.get('DATABASE_URL'), sslmode='require')
conn.autocommit = True
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# Buat tabel session jika belum ada
cur.execute('''
    CREATE TABLE IF NOT EXISTS sessions (
        id VARCHAR(255) PRIMARY KEY,
        data BYTEA,
        expiry TIMESTAMP
    )
''')
conn.commit()

Session(app)

# Konfigurasi untuk Netlify
@app.route('/')
def index():
    return redirect('/login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nip = request.form['nip']
        password = request.form['password']
        
        # Tambahkan logging
        print(f"Login attempt for NIP: {nip}")
        
        # Query dengan is_admin untuk memastikan status admin
        cur.execute('''
            SELECT id, nama, nip, password_hash, is_admin 
            FROM pegawai 
            WHERE nip = %s
        ''', (nip,))
        user = cur.fetchone()
        
        if user:
            print("User found in database")
            if check_password_hash(user['password_hash'], password):
                print("Password match")
                print(f"User is admin: {user['is_admin']}")
                session['user'] = user
                if user['is_admin']:
                    return redirect('/admin')
                return redirect('/absen')
            else:
                print("Password mismatch")
        else:
            print("User not found")
            
        return render_template('login.html', error='NIP atau password salah')

    return render_template('login.html')

# Menambahkan static route
@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(STATIC_DIR, filename)

# Menambahkan template route
@app.route('/templates/<path:filename>')
def template_files(filename):
    return send_from_directory('templates', filename)

@app.route('/reset_db')
def reset_db():
    try:
        # Drop tabel absensi dan pegawai jika ada
        cur.execute('DROP TABLE IF EXISTS absensi')
        cur.execute('DROP TABLE IF EXISTS pegawai')
        
        # Buat tabel pegawai
        cur.execute('''
            CREATE TABLE pegawai (
                id SERIAL PRIMARY KEY,
                nip VARCHAR(20) UNIQUE NOT NULL,
                nama VARCHAR(100) NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin BOOLEAN DEFAULT FALSE
            )
        ''')
        
        # Buat tabel absensi
        cur.execute('''
            CREATE TABLE absensi (
                id SERIAL PRIMARY KEY,
                id_pegawai INTEGER REFERENCES pegawai(id),
                tanggal DATE NOT NULL,
                waktu TIME NOT NULL,
                jenis_absensi VARCHAR(10) NOT NULL,
                latitude DECIMAL(10,8),
                longitude DECIMAL(11,8),
                mock_location BOOLEAN DEFAULT FALSE,
                developer_mode BOOLEAN DEFAULT FALSE
            )
        ''')
        
        # Tambahkan admin default
        admin_password = generate_password_hash('admin123')
        cur.execute('''
            INSERT INTO pegawai (nip, nama, password_hash, is_admin)
            VALUES ('123456', 'Admin', %s, TRUE)
        ''', (admin_password,))
        
        conn.commit()
        return 'Database berhasil di-reset dan tabel berhasil dibuat'
    except Exception as e:
        conn.rollback()
        return f"Error: {str(e)}"

ABSEN_RADIUS = 100
KOORDINAT_KANTOR = [
    {'lat': -4.01329, 'lon': 119.62596},
    {'lat': -4.03630, 'lon': 119.63229},
]

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

def is_in_allowed_radius(lat, lon):
    return any(haversine(lat, lon, p['lat'], p['lon']) <= ABSEN_RADIUS for p in KOORDINAT_KANTOR)

@app.route('/absen', methods=['GET', 'POST'])
def absen():
    if 'user' not in session:
        return redirect('/login')

    if request.method == 'POST':
        user = session['user']
        lat = float(request.form['latitude'])
        lon = float(request.form['longitude'])
        mock = request.form['mock_location'] == 'true'
        dev = request.form['developer_mode'] == 'true'

        if not is_in_allowed_radius(lat, lon):
            return 'Lokasi di luar radius kantor'

        # Cek mock location
        if mock:
            return 'Absensi tidak diperbolehkan karena menggunakan lokasi palsu'

        now = datetime.datetime.now()
        
        # Definisikan waktu absensi
        waktu_masuk_mulai = datetime.time(7, 0)  # 07:00
        waktu_masuk_selesai = datetime.time(8, 30)  # 08:30
        waktu_pulang_mulai = datetime.time(15, 0)  # 15:00
        waktu_pulang_selesai = datetime.time(23, 59)  # 23:59
        
        # Periksa absensi terakhir hari ini
        cur.execute('''
            SELECT jenis_absensi, waktu 
            FROM absensi 
            WHERE id_pegawai = %s AND tanggal = CURRENT_DATE 
            ORDER BY waktu DESC 
            LIMIT 1
        ''', (user['id'],))
        last_absensi = cur.fetchone()
        
        # Jika belum ada absensi hari ini
        if not last_absensi:
            # Cek waktu absensi
            if waktu_masuk_mulai <= now.time() <= waktu_masuk_selesai:
                jenis = 'masuk'
            elif waktu_pulang_mulai <= now.time() <= waktu_pulang_selesai:
                jenis = 'pulang'
            else:
                return 'Waktu absensi tidak valid. Absen masuk: 07:00-08:30, Absen pulang: 15:00-23:59'
        else:
            # Jika absensi terakhir adalah masuk
            if last_absensi['jenis_absensi'] == 'masuk':
                # Cek waktu absensi pulang
                if waktu_pulang_mulai <= now.time() <= waktu_pulang_selesai:
                    jenis = 'pulang'
                else:
                    return 'Waktu absen pulang tidak valid. Harus antara 15:00-23:59'
            else:  # absensi terakhir adalah pulang
                # Cek waktu absensi masuk
                if waktu_masuk_mulai <= now.time() <= waktu_masuk_selesai:
                    jenis = 'masuk'
                else:
                    return 'Waktu absen masuk tidak valid. Harus antara 07:00-08:30'
        
        # Tambahkan log untuk debugging
        print(f"Absensi {jenis} pada {now.strftime('%Y-%m-%d %H:%M:%S')}")

        cur.execute('''
            INSERT INTO absensi (id_pegawai, tanggal, waktu, jenis_absensi, latitude, longitude, mock_location, developer_mode)
            VALUES (%s, CURRENT_DATE, CURRENT_TIME, %s, %s, %s, %s, %s)
        ''', (user['id'], jenis, lat, lon, mock, dev))
        conn.commit()

        return 'Absen berhasil'

    return render_template('absen.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/laporan')
def laporan():
    try:
        if 'user' not in session:
            return redirect('/login')

        # Ambil data absensi 7 hari terakhir
        cur.execute('''
            SELECT 
                tanggal,
                MIN(CASE WHEN jenis_absensi = 'masuk' THEN waktu END) as waktu_masuk,
                MAX(CASE WHEN jenis_absensi = 'pulang' THEN waktu END) as waktu_pulang
            FROM absensi
            WHERE id_pegawai = %s
            AND tanggal >= CURRENT_DATE - INTERVAL '7 days'
            GROUP BY tanggal
            ORDER BY tanggal DESC
        ''', (session['user']['id'],))
        
        absensi = cur.fetchall()
        
        return render_template('laporan.html', absensi=absensi)
    except Exception as e:
        return f"Error: {str(e)}"

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect('/login')
        if not session['user'].get('is_admin'):
            return 'Akses ditolak', 403
        return f(*args, **kwargs)
    return decorated_function

@app.route('/test_db')
def test_db():
    try:
        # Cek koneksi
        cur.execute('SELECT version()')
        version = cur.fetchone()
        
        # Cek tabel pegawai
        cur.execute('SELECT COUNT(*) FROM pegawai')
        count = cur.fetchone()
        
        # Tampilkan struktur tabel pegawai
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'pegawai'")
        columns = cur.fetchall()
        
        # Ambil beberapa data pegawai
        cur.execute('SELECT * FROM pegawai LIMIT 5')
        pegawai = cur.fetchall()
        
        # Update password hash untuk semua pegawai yang masih menggunakan password123
        for p in pegawai:
            if p['password_hash'] == 'password123':
                new_hash = generate_password_hash('password123')
                cur.execute('UPDATE pegawai SET password_hash = %s WHERE id = %s', 
                          (new_hash, p['id']))
        conn.commit()
        
        return render_template('test_db.html', 
            version=version['version'],
            count=count['count'],
            columns=columns,
            pegawai=pegawai)
    except Exception as e:
        conn.rollback()
        return f"Error: {str(e)}"

@app.route('/update_passwords')
def update_passwords():
    try:
        # Update password hash untuk semua pegawai yang masih menggunakan password123
        cur.execute('SELECT * FROM pegawai WHERE password_hash = %s', ('password123',))
        pegawai = cur.fetchall()
        
        for p in pegawai:
            new_hash = generate_password_hash('password123')
            cur.execute('UPDATE pegawai SET password_hash = %s WHERE id = %s', 
                      (new_hash, p['id']))
        conn.commit()
        
        return 'Password hash berhasil diupdate'
    except Exception as e:
        conn.rollback()
        return f"Error: {str(e)}"

@app.route('/admin', methods=['GET', 'POST'])
@admin_required
def admin():
    try:
        if request.method == 'POST':
            nama = request.form['nama']
            nip = request.form['nip']
            password = request.form['password']
            is_admin = request.form.get('is_admin', 'false') == 'true'
            
            # Hash password
            hashed_password = generate_password_hash(password)
            
            # Insert pegawai baru
            cur.execute('''
                INSERT INTO pegawai (nama, nip, password_hash, is_admin)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            ''', (nama, nip, hashed_password, is_admin))
            
            return redirect('/admin?success=true')
        
        # Get pegawai list
        cur.execute('''
            SELECT id, nama, nip, is_admin 
            FROM pegawai 
            ORDER BY nama
        ''')
        pegawai = cur.fetchall()
        
        return render_template('admin.html', pegawai=pegawai)
    except Exception as e:
        return f"Error: {str(e)}"

@app.route('/admin/edit', methods=['POST'])
@admin_required
def admin_edit():
    try:
        id = request.form['id']
        nama = request.form.get('nama')
        nip = request.form.get('nip')
        password = request.form.get('password')

        update_fields = []
        values = []

        if nama and nama.strip():
            update_fields.append('nama = %s')
            values.append(nama)
        if nip and nip.strip():
            update_fields.append('nip = %s')
            values.append(nip)
        if password and password.strip():
            update_fields.append('password_hash = %s')
            values.append(generate_password_hash(password))

        if update_fields:
            values.append(id)
            query = f"UPDATE pegawai SET {', '.join(update_fields)} WHERE id = %s"
            cur.execute(query, values)
            conn.commit()
            return redirect('/admin?success=true')
        else:
            return 'Tidak ada data yang diupdate', 400

    except Exception as e:
        conn.rollback()
        print(f"Error: {str(e)}")
        return 'Gagal update data pegawai', 500

@app.route('/admin/get_pegawai')
@admin_required
def get_pegawai():
    if 'user' not in session:
        return redirect('/login')
    cur.execute('SELECT id, nama, nip FROM pegawai ORDER BY nama')
    pegawai = cur.fetchall()
    return pegawai

@app.route('/admin/delete/<int:id>', methods=['POST'])
@admin_required
def delete_pegawai(id):
    if 'user' not in session:
        return redirect('/login')

    try:
        cur.execute('DELETE FROM absensi WHERE id_pegawai = %s', (id,))
        cur.execute('DELETE FROM pegawai WHERE id = %s', (id,))
        conn.commit()
        return redirect('/admin?success=true')
    except Exception as e:
        conn.rollback()
        print(f"Error: {str(e)}")
        return 'Gagal menghapus pegawai', 500