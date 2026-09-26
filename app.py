import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_wtf.csrf import CSRFProtect
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from database import (
    init_db,
    create_team,
    find_team_by_email,
    find_team_by_id,
    get_team_member_count,
    mark_team_paid,
    update_project_details,
    get_all_teams,
)

load_dotenv('.env.local')

app = Flask(__name__)
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"]
)
csrf = CSRFProtect(app)
app.secret_key = os.getenv('SECRET_KEY')
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')
print("ADMIN_USERNAME set:", ADMIN_USERNAME is not None)
print("ADMIN_PASSWORD set:", ADMIN_PASSWORD is not None)
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024

if not os.path.exists('static/images'):
    os.makedirs('static/images')


@app.before_request
def prepare_database():
    init_db()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("10 per hour")
def register():
    if request.method == 'POST':
        team_name = request.form.get('team_name', '').strip()
        leader_name = request.form.get('leader_name', '').strip()
        leader_email = request.form.get('leader_email', '').strip().lower()
        leader_phone = request.form.get('leader_phone', '').strip()
        leader_status = request.form.get('leader_status', 'Not Specified')

        if len(team_name) > 100 or len(leader_name) > 100:
            return "Team or leader name is too long.", 400

        if len(leader_email) > 254 or len(leader_phone) > 20:
            return "Email or phone number is too long.", 400

        if not team_name or not leader_name or not leader_email or not leader_phone:
            return "Team and leader details are required!", 400

        member_names = request.form.getlist('member_name')
        member_emails = request.form.getlist('member_email')
        member_phones = request.form.getlist('member_phone')

        members = []

        for i in range(len(member_emails)):
            email = member_emails[i].strip().lower() if member_emails[i] else ""

            if email:
                status_key = f'member_status_{i+1}'
                status = request.form.get(status_key, 'Not Specified')
                name = member_names[i].strip() if i < len(member_names) else "Unknown"
                phone = member_phones[i].strip() if i < len(member_phones) else ""

                if len(name) > 100 or len(email) > 254 or len(phone) > 20:
                    return "Member details are too long.", 400

                members.append({
                    "name": name,
                    "email": email,
                    "phone": phone,
                    "status": status
                })

        # Enforce the 2-4 member rule on the server as well.
        if len(members) < 1:
            return "A team must have at least 2 members including the leader.", 400

        if len(members) > 3:
            return "A team can have a maximum of 4 members including the leader.", 400

        try:
            team_id = create_team(
                team_name,
                leader_name,
                leader_email,
                leader_phone,
                leader_status,
                members
            )

            session['user_email'] = leader_email
            session['team_id'] = team_id
            session['team_name'] = team_name

            return redirect(url_for('payment'))

        except ValueError as e:
            return str(e), 400
        except Exception as e:
            print(f"Registration failed: {e}")
            return "Registration failed. Please try again.", 500

    return render_template('register.html')


@app.route('/get_team_count')
def get_team_count():
    team_id = session.get('team_id')

    if not team_id:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        count = get_team_member_count(team_id)
        return jsonify({"count": count})
    except Exception as e:
        print(f"Team count error: {e}")
        return jsonify({"error": "Unable to calculate team count"}), 500


@app.route('/payment', methods=['GET', 'POST'])
def payment():
    if not session.get('team_id'):
        return redirect(url_for('register'))

    if request.method == 'POST':
        team_id = session['team_id']

        try:
            if mark_team_paid(team_id):
                return jsonify({"status": "success"})

            return jsonify({
                "status": "error",
                "message": "Team not found"
            }), 404

        except Exception as e:
            print(f"Payment update error: {e}")
            return jsonify({
                "status": "error",
                "message": "Payment update failed"
            }), 500

    return render_template('payment.html')


@app.route('/thankyou')
def thankyou():
    return render_template('thankyou.html')


@app.route('/login_page')
def login_page():
    return render_template('login.html')


@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per hour")
def login():
    email = request.form.get('email', '').strip().lower()

    if not email:
        return "Email is required", 400

    try:
        team = find_team_by_email(email)

        if team:
            session['user_email'] = email
            session['team_id'] = team['id']
            session['team_name'] = team['team_name']
            return redirect(url_for('dashboard'))

        return "Invalid email", 401

    except Exception as e:
        print(f"Login error: {e}")
        return "Login failed. Please try again.", 500

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['is_admin'] = True
            return redirect(url_for('admin_dashboard'))

        return "Invalid admin credentials", 401

    return render_template('admin_login.html')

@app.route('/admin')
def admin_dashboard():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))

    teams = get_all_teams()

    return render_template(
        'admin_dashboard.html',
        teams=teams
    )

@app.route('/dashboard')
def dashboard():
    team_id = session.get('team_id')

    if not team_id:
        return redirect(url_for('index'))

    try:
        team = find_team_by_id(team_id)

        if not team:
            session.clear()
            return redirect(url_for('index'))

        team_data = {
            'team_name': team['team_name'],
            'payment_status': team['payment_status'],
            'problem_statement_id': team['problem_statement'],
            'proposed_solution': team['proposed_solution']
        }

        problems = [
            {'id': '1', 'track': 'AI/ML', 'title': 'Smart City Traffic'},
            {'id': '2', 'track': 'AI/ML', 'title': 'Healthcare Bot'},
            {'id': '3', 'track': 'Web3', 'title': 'Decentralized Voting'},
            {'id': '4', 'track': 'Web3', 'title': 'NFT Marketplace'},
            {'id': '5', 'track': 'FinTech', 'title': 'Micro-loan Platform'},
            {'id': '6', 'track': 'FinTech', 'title': 'Budget Optimizer'},
        ]

        return render_template(
            'dashboard.html',
            team=team_data,
            problems=problems
        )

    except Exception as e:
        print(f"Dashboard error: {e}")
        return "Unable to load dashboard", 500


@app.route('/submit_details', methods=['POST'])
def submit_details():
    if not session.get('team_id'):
        return jsonify({
            "status": "error",
            "message": "Unauthorized"
        }), 401

    problem_id = request.form.get('problem_id')
    solution = request.form.get('proposed_solution')

    if not problem_id or not solution:
        return jsonify({
            "status": "error",
            "message": "Problem statement and proposed solution are required."
        }), 400

    try:
        if update_project_details(session['team_id'], problem_id, solution):
            return jsonify({"status": "success"})

        return jsonify({
            "status": "error",
            "message": "Team not found"
        }), 404

    except Exception as e:
        print(f"Project update error: {e}")
        return jsonify({
            "status": "error",
            "message": "Unable to save project details"
        }), 500


@app.route('/submission_page')
def submission_page():
    team_id = session.get('team_id')

    if not team_id:
        return redirect(url_for('index'))

    try:
        team = find_team_by_id(team_id)

        if not team:
            session.clear()
            return redirect(url_for('index'))

        return render_template(
            'submission.html',
            team={'team_name': team['team_name']}
        )

    except Exception as e:
        print(f"Submission page error: {e}")
        return "Unable to load submission page", 500


@app.route('/upload_file', methods=['POST'])
def upload_file():
    if not session.get('team_id'):
        return jsonify({
            "status": "error",
            "message": "Unauthorized"
        }), 401

    file_type = request.form.get('file_type')

    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file"}), 400

    file = request.files['file']
    filename = secure_filename(
        f"team_{session.get('team_name')}_{file_type}_{file.filename}"
    )
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    return jsonify({"status": "success"})


@app.route('/upload_video', methods=['POST'])
def upload_video():
    if not session.get('team_id'):
        return jsonify({
            "status": "error",
            "message": "Unauthorized"
        }), 401

    if 'video' not in request.files:
        return jsonify({"status": "error", "message": "No file"}), 400

    file = request.files['video']
    filename = secure_filename(
        f"team_{session.get('team_name')}_video_{file.filename}"
    )
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    return jsonify({"status": "success"})


if __name__ == '__main__':
    app.run(debug=False, port=5000)
