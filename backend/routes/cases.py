from flask import Blueprint, request, jsonify, session
from database.db import get_db_connection
import uuid

cases_bp = Blueprint('cases', __name__)

@cases_bp.route('/api/cases', methods=['GET'])
def get_cases():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT case_id, session_token, created_at, status FROM cases WHERE user_id = %s ORDER BY created_at DESC", (session['user_id'],))
        cases = cursor.fetchall()
        return jsonify({"success": True, "cases": cases}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@cases_bp.route('/api/cases', methods=['POST'])
def create_case():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    session_token = str(uuid.uuid4())
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO cases (user_id, session_token) VALUES (%s, %s)", (session['user_id'], session_token))
        conn.commit()
        return jsonify({"success": True, "session_token": session_token}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@cases_bp.route('/api/cases/<session_token>/facts', methods=['GET'])
def get_case_facts(session_token):
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        # Verify ownership
        cursor.execute("SELECT case_id FROM cases WHERE session_token = %s AND user_id = %s", (session_token, session['user_id']))
        case = cursor.fetchone()
        if not case:
            return jsonify({"error": "Case not found or unauthorized"}), 404

        cursor.execute("SELECT fact_key, fact_value FROM case_facts WHERE case_id = %s", (case['case_id'],))
        facts_rows = cursor.fetchall()
        
        facts = {}
        for row in facts_rows:
            # Handle boolean conversion
            val = row['fact_value']
            if val.lower() == 'true': val = True
            elif val.lower() == 'false': val = False
            facts[row['fact_key']] = val
            
        return jsonify({"success": True, "facts": facts}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()
