from flask import Blueprint, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from database.db import get_db_connection

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/api/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower() or None
    username = (data.get('username') or email or '').strip()
    full_name = (data.get('full_name') or data.get('name') or '').strip() or None
    password = data.get('password')

    if not username or not password:
        return jsonify({"error": "Email or username and password are required."}), 400

    hashed_pw = generate_password_hash(password)
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id FROM users WHERE username = %s OR email = %s",
            (username, email or username),
        )
        if cursor.fetchone():
            return jsonify({"error": "An account with this username or email already exists."}), 400

        cursor.execute(
            "INSERT INTO users (username, full_name, email, password_hash) "
            "VALUES (%s, %s, %s, %s)",
            (username, full_name, email, hashed_pw),
        )
        conn.commit()
        return jsonify({"success": True, "message": "Account created successfully."}), 201
    except Exception:
        conn.rollback()
        return jsonify({"error": "Unable to create the account."}), 500
    finally:
        cursor.close()
        conn.close()

@auth_bp.route('/api/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or data.get('email') or '').strip().lower()
    password = data.get('password')

    if not username or not password:
        return jsonify({"error": "Email or username and password are required."}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM users WHERE username = %s OR email = %s",
            (username, username),
        )
        user = cursor.fetchone()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['user_id']
            session['username'] = user['username']
            session['name'] = user.get('full_name') or user['username']
            session['email'] = user.get('email')
            return jsonify({
                "success": True,
                "username": user['username'],
                "name": session['name'],
            }), 200
        else:
            return jsonify({"error": "Invalid credentials"}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@auth_bp.route('/api/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('name', None)
    session.pop('email', None)
    return jsonify({"success": True, "message": "Logged out successfully"}), 200

@auth_bp.route('/api/me', methods=['GET'])
def me():
    if 'user_id' in session:
        return jsonify({
            "logged_in": True,
            "username": session['username'],
            "name": session.get('name', session['username']),
        }), 200
    return jsonify({"logged_in": False}), 401
