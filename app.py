import os
import sqlite3
import smtplib
import urllib.parse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder='.')
DATABASE = 'bookings.db'

# ============================================
# EMAIL SETTINGS (optional — the site works fine without this)
# ============================================
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587

SENDER_EMAIL = 'threebrotherss100@gmail.com'
SENDER_PASSWORD = 'derc qyug pgye xzvx'  # Your Gmail App Password configured here

# 👇 CHANGE THIS to the email address YOU actually check every day.
RECEIVER_EMAIL = 'threebrotherss100@gmail.com'


def send_automated_email(name, whatsapp, property_details, date):
    if not SENDER_PASSWORD:
        print("\n=== NEW ENQUIRY (email alerts are OFF) ===")
        print(f"Name: {name} | WhatsApp: {whatsapp} | Property: {property_details} | Date: {date}")
        print("To enable email alerts, set SENDER_PASSWORD and RECEIVER_EMAIL at the top of app.py")
        print("===========================================")
        return False

    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = RECEIVER_EMAIL
        msg['Subject'] = f"New Property Scout Booking - {name}"

        body = f"""
        Hi Property Scouts,

        A new property scout booking has been submitted:

        - Client Name: {name}
        - WhatsApp Contact: {whatsapp}
        - Property Details/Address: {property_details}
        - Preferred Visit Date & Time: {date}

        This booking is also saved on your Admin Dashboard (/admin).
        """

        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        server.quit()
        print(f"Email sent to {RECEIVER_EMAIL}")
        return True
    except Exception as e:
        print(f"Email failed to send (booking is still saved): {e}")
        return False


# ============================================
# GENERIC DATABASE LAYER (PostgreSQL or SQLite)
# ============================================
def execute_query(query, params=(), fetchall=False, fetchone=False, commit=False):
    db_url = os.environ.get('DATABASE_URL')
    if db_url:
        import pg8000
        # Convert SQLite ? placeholders to PostgreSQL %s placeholders
        query = query.replace('?', '%s')
        
        # Parse PostgreSQL URL
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        url = urllib.parse.urlparse(db_url)
        
        conn = pg8000.connect(
            user=url.username,
            password=url.password,
            host=url.hostname,
            port=url.port or 5432,
            database=url.path[1:]
        )
        cursor = conn.cursor()
        cursor.execute(query, params)
        
        result = None
        if fetchall:
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            result = [dict(zip(columns, row)) for row in rows]
        elif fetchone:
            row = cursor.fetchone()
            if row:
                columns = [desc[0] for desc in cursor.description]
                result = dict(zip(columns, row))
                
        if commit:
            conn.commit()
            
        cursor.close()
        conn.close()
        return result
    else:
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query, params)
        
        result = None
        if fetchall:
            rows = cursor.fetchall()
            result = [dict(row) for row in rows]
        elif fetchone:
            row = cursor.fetchone()
            if row:
                result = dict(row)
                
        if commit:
            conn.commit()
            
        cursor.close()
        conn.close()
        return result


def init_db():
    db_url = os.environ.get('DATABASE_URL')
    if db_url:
        execute_query('''
            CREATE TABLE IF NOT EXISTS bookings (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                whatsapp TEXT NOT NULL,
                property_details TEXT NOT NULL,
                preferred_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''', commit=True)
        print("PostgreSQL Database initialized successfully!")
    else:
        # SQLite local database setup
        execute_query('''
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                whatsapp TEXT NOT NULL,
                property_details TEXT NOT NULL,
                preferred_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''', commit=True)
        print("SQLite Database initialized successfully!")


init_db()


@app.route('/')
def index():
    return send_from_directory('.', 'property-scouts-website.html')


@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('.', path)


@app.route('/admin')
def admin_page():
    return send_from_directory('.', 'admin.html')


# ============================================
# API Endpoints
# ============================================

@app.route('/api/bookings', methods=['POST'])
def create_booking():
    data = request.json
    if not data:
        return jsonify({"error": "Invalid request body"}), 400

    name = data.get('name')
    whatsapp = data.get('whatsapp')
    property_details = data.get('property')
    preferred_date = data.get('date')

    if not all([name, whatsapp, property_details, preferred_date]):
        return jsonify({"error": "All fields are required"}), 400

    # Insert booking and return generated row details
    # Postgres and SQLite (3.35.0+) both support the RETURNING clause!
    try:
        res = execute_query('''
            INSERT INTO bookings (name, whatsapp, property_details, preferred_date, status)
            VALUES (?, ?, ?, ?, 'Pending')
            RETURNING id
        ''', (name, whatsapp, property_details, preferred_date), fetchone=True, commit=True)
        booking_id = res['id'] if res else None
    except Exception as e:
        print(f"Insert with RETURNING failed: {e}. Trying standard insert...")
        # Fallback for old local SQLite versions without RETURNING clause
        execute_query('''
            INSERT INTO bookings (name, whatsapp, property_details, preferred_date, status)
            VALUES (?, ?, ?, ?, 'Pending')
        ''', (name, whatsapp, property_details, preferred_date), commit=True)
        
        # Get the max ID as fallback
        last_row = execute_query('SELECT MAX(id) as last_id FROM bookings', fetchone=True)
        booking_id = last_row['last_id'] if last_row else None

    # Best-effort email alert — booking is saved either way
    send_automated_email(name, whatsapp, property_details, preferred_date)

    return jsonify({
        "success": True,
        "message": "Booking stored successfully!",
        "booking_id": booking_id
    }), 201


@app.route('/api/bookings', methods=['GET'])
def get_bookings():
    bookings = execute_query('SELECT * FROM bookings ORDER BY created_at DESC', fetchall=True)
    return jsonify(bookings)


@app.route('/api/bookings/<int:booking_id>/status', methods=['POST'])
def update_status(booking_id):
    data = request.json
    status = data.get('status')
    if not status:
        return jsonify({"error": "Status is required"}), 400

    # Check database URL type for row count since cursor.rowcount behaves differently
    db_url = os.environ.get('DATABASE_URL')
    
    execute_query('UPDATE bookings SET status = ? WHERE id = ?', (status, booking_id), commit=True)
    return jsonify({"success": True, "message": "Booking status updated successfully!"})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
