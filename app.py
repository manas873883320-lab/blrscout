import os
import sqlite3
import smtplib
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
SENDER_PASSWORD = ''  # Leave blank if you don't want email alerts. See note below.

# 👇 CHANGE THIS to the email address YOU actually check every day.
RECEIVER_EMAIL = 'threebrotherss100@gmail.com'

# To enable email alerts:
# 1. Go to Google Account -> Security -> 2-Step Verification -> App Passwords
# 2. Generate a new App Password, paste it into SENDER_PASSWORD above
# 3. Change RECEIVER_EMAIL to the inbox you want enquiries sent to
# If you skip this, every booking still gets saved to bookings.db and
# shows up on your /admin dashboard — you just won't get an email alert.


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


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    if not os.path.exists(DATABASE):
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                whatsapp TEXT NOT NULL,
                property_details TEXT NOT NULL,
                preferred_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
        print("Database initialized successfully!")


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

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO bookings (name, whatsapp, property_details, preferred_date, status)
        VALUES (?, ?, ?, ?, 'Pending')
    ''', (name, whatsapp, property_details, preferred_date))
    conn.commit()
    booking_id = cursor.lastrowid
    conn.close()

    # Best-effort email alert — booking is saved either way
    send_automated_email(name, whatsapp, property_details, preferred_date)

    return jsonify({
        "success": True,
        "message": "Booking stored successfully!",
        "booking_id": booking_id
    }), 201


@app.route('/api/bookings', methods=['GET'])
def get_bookings():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM bookings ORDER BY created_at DESC')
    rows = cursor.fetchall()
    conn.close()

    bookings = []
    for row in rows:
        bookings.append({
            "id": row['id'],
            "name": row['name'],
            "whatsapp": row['whatsapp'],
            "property_details": row['property_details'],
            "preferred_date": row['preferred_date'],
            "status": row['status'],
            "created_at": row['created_at']
        })
    return jsonify(bookings)


@app.route('/api/bookings/<int:booking_id>/status', methods=['POST'])
def update_status(booking_id):
    data = request.json
    status = data.get('status')
    if not status:
        return jsonify({"error": "Status is required"}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE bookings SET status = ? WHERE id = ?', (status, booking_id))
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()

    if rows_affected == 0:
        return jsonify({"error": "Booking not found"}), 404

    return jsonify({"success": True, "message": "Booking status updated successfully!"})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
