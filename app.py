import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'nimbus_secret_key'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB limit for videos

# Database initialization
def init_db():
    conn = sqlite3.connect('nimbus.db')
    c = conn.cursor()
    # Teams table
    c.execute('''CREATE TABLE IF NOT EXISTS teams
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  team_name TEXT UNIQUE,
                  leader_email TEXT UNIQUE,
                  payment_status TEXT DEFAULT 'Unpaid',
                  problem_statement_id INTEGER)''')
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  email TEXT UNIQUE,
                  team_id INTEGER,
                  role TEXT,
                  FOREIGN KEY(team_id) REFERENCES teams(id))''')
    # Problem Statements table
    c.execute('''CREATE TABLE IF NOT EXISTS problems
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  track TEXT,
                  title TEXT,
                  description TEXT)''')

    # Seed problem statements if empty
    c.execute("SELECT COUNT(*) FROM problems")
    if c.fetchone()[0] == 0:
        problems = [
            ('AI/ML', 'Smart City Traffic', 'Optimize traffic flow using real-time AI.'),
            ('AI/ML', 'Healthcare Bot', 'AI diagnostic assistant for rural areas.'),
            ('Web3', 'Decentralized Voting', 'Secure voting system using blockchain.'),
            ('Web3', 'NFT Marketplace', 'Specialized marketplace for academic papers.'),
            ('FinTech', 'Micro-loan Platform', 'P2P lending for small businesses.'),
            ('FinTech', 'Budget Optimizer', 'AI-driven personal finance manager.')
        ]
        c.executemany("INSERT INTO problems (track, title, description) VALUES (?, ?, ?)", problems)

    conn.commit()
    conn.close()

init_db()

def get_db():
    conn = sqlite3.connect('nimbus.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    conn = get_db()
    problems = conn.execute("SELECT * FROM problems").fetchall()
    conn.close()
    return render_template('index.html', problems=problems)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        team_name = request.form['team_name']
        leader_email = request.form['leader_email']
        members = request.form.getlist('member_email')

        conn = get_db()
        try:
            c = conn.cursor()
            c.execute("INSERT INTO teams (team_name, leader_email) VALUES (?, ?)", (team_name, leader_email))
            team_id = c.lastrowid

            # Add leader
            c.execute("INSERT INTO users (email, team_id, role) VALUES (?, ?, ?)", (leader_email, team_id, 'leader'))
            # Add members
            for email in members:
                if email:
                    c.execute("INSERT INTO users (email, team_id, role) VALUES (?, ?, ?)", (email, team_id, 'member'))

            conn.commit()
            session['user_email'] = leader_email
            return redirect(url_for('payment'))
        except sqlite3.IntegrityError:
            return "Team name or leader email already exists!", 400
        finally:
            conn.close()

    return render_template('register.html')

@app.route('/payment', methods=['GET', 'POST'])
def payment():
    if 'user_email' not in session:
        return redirect(url_for('register'))

    if request.method == 'POST':
        email = session['user_email']
        conn = get_db()
        conn.execute("UPDATE teams SET payment_status = 'Paid' WHERE leader_email = ?", (email,))
        conn.commit()
        conn.close()
        return jsonify({"status": "success"})

    return render_template('payment.html')

@app.route('/login_page')
def login_page():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    email = request.form['email']
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()

    if user:
        session['user_email'] = email
        session['team_id'] = user['team_id']
        session['role'] = user['role']
        return redirect(url_for('dashboard'))
    return "Invalid email", 401

@app.route('/dashboard')
def dashboard():
    if 'user_email' not in session:
        return redirect(url_for('index'))

    conn = get_db()
    team = conn.execute("SELECT * FROM teams WHERE id = ?", (session['team_id'],)).fetchone()
    problems = conn.execute("SELECT * FROM problems").fetchall()
    conn.close()

    return render_template('dashboard.html', team=team, problems=problems)

@app.route('/select_problem', methods=['POST'])
def select_problem():
    if 'user_email' not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    problem_id = request.form['problem_id']
    team_id = session['team_id']

    conn = get_db()
    conn.execute("UPDATE teams SET problem_statement_id = ? WHERE id = ?", (problem_id, team_id))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

@app.route('/upload_video', methods=['POST'])
def upload_video():
    if 'user_email' not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    if 'video' not in request.files:
        return jsonify({"status": "error", "message": "No file uploaded"}), 400

    file = request.files['video']
    if file.filename == '':
        return jsonify({"status": "error", "message": "No selected file"}), 400

    filename = secure_filename(f"team_{session['team_id']}_{file.filename}")
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
