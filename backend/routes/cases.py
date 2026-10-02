import json
import uuid

from flask import Blueprint, jsonify, request, session

from database.db import get_db_connection


cases_bp = Blueprint("cases", __name__)
_CASE_STATE_KEY = "__case_state__"
_MODULES = [
    {"id": "defective_product", "name": "Defective Product", "description": "Product is damaged, faulty, defective, or does not work properly.", "available": True},
    {"id": "refund_replacement", "name": "Refund / Replacement", "description": "A seller refuses or delays a refund or replacement.", "available": False},
    {"id": "warranty", "name": "Warranty Issue", "description": "A warranty claim is denied, delayed, or not honoured.", "available": False},
    {"id": "ecommerce", "name": "E-Commerce Consumer Issue", "description": "A problem involving an online purchase or delivery.", "available": False},
    {"id": "service_deficiency", "name": "Deficiency in Service", "description": "A service was not provided properly or as expected.", "available": False},
    {"id": "unfair_trade_practice", "name": "Misleading Advertisement / Unfair Trade Practice", "description": "An advertisement or business practice may be misleading or unfair.", "available": False},
]
_ANSWER_KEYS = {
    "product_purchased",
    "product_has_problem",
    "seller_contacted",
    "seller_resolved",
    "desired_resolution",
    "purchase_proof_available",
    "problem_evidence_available",
    "seller_communication_available",
}


@cases_bp.route("/api/modules", methods=["GET"])
def get_modules():
    return jsonify({"modules": _MODULES}), 200


def _guest_tokens():
    return session.get("guest_case_tokens", [])


def _case_access(cursor, session_token):
    user_id = session.get("user_id")
    if user_id is not None:
        cursor.execute(
            "SELECT case_id, user_id, session_token, created_at, status "
            "FROM cases WHERE session_token = %s AND user_id = %s",
            (session_token, user_id),
        )
    else:
        if session_token not in _guest_tokens():
            return None
        cursor.execute(
            "SELECT case_id, user_id, session_token, created_at, status "
            "FROM cases WHERE session_token = %s AND user_id IS NULL",
            (session_token,),
        )
    return cursor.fetchone()


def _case_label(case):
    created = case["created_at"]
    year = created.year if hasattr(created, "year") else int(str(created)[:4])
    return f"CASE-{year}-{case['case_id']:04d}"


def _read_case_state(cursor, case_id):
    cursor.execute(
        "SELECT fact_key, fact_value FROM case_facts WHERE case_id = %s",
        (case_id,),
    )
    state = {
        "module_id": None,
        "answers": {},
        "case_details": {},
        "current_question_key": None,
        "report": None,
    }
    for row in cursor.fetchall():
        if row["fact_key"] == _CASE_STATE_KEY:
            try:
                state.update(json.loads(row["fact_value"]))
            except (TypeError, json.JSONDecodeError):
                continue
        elif row["fact_key"] in _ANSWER_KEYS:
            value = row["fact_value"]
            if value == "true":
                value = True
            elif value == "false":
                value = False
            state["answers"][row["fact_key"]] = value
    return state


def _case_response(case, state):
    created = case["created_at"]
    return {
        "case_id": _case_label(case),
        "session_token": case["session_token"],
        "created_at": created.isoformat() if hasattr(created, "isoformat") else str(created),
        "status": case["status"],
        **state,
    }


@cases_bp.route("/api/cases", methods=["GET"])
def get_cases():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed."}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        user_id = session.get("user_id")
        if user_id is not None:
            cursor.execute(
                "SELECT case_id, user_id, session_token, created_at, status "
                "FROM cases WHERE user_id = %s ORDER BY created_at DESC",
                (user_id,),
            )
        else:
            tokens = _guest_tokens()
            if not tokens:
                return jsonify({"success": True, "cases": []}), 200
            placeholders = ",".join(["%s"] * len(tokens))
            cursor.execute(
                "SELECT case_id, user_id, session_token, created_at, status "
                f"FROM cases WHERE user_id IS NULL AND session_token IN ({placeholders}) "
                "ORDER BY created_at DESC",
                tuple(tokens),
            )
        cases = cursor.fetchall()
        result = []
        for case in cases:
            state = _read_case_state(cursor, case["case_id"])
            module = next((item for item in _MODULES if item["id"] == state["module_id"]), None)
            result.append({
                "case_id": _case_label(case),
                "session_token": case["session_token"],
                "issue": module["name"] if module else "Not selected",
                "status": case["status"],
                "created_at": case["created_at"].isoformat()
                if hasattr(case["created_at"], "isoformat") else str(case["created_at"]),
            })
        return jsonify({"success": True, "cases": result}), 200
    except Exception:
        conn.rollback()
        return jsonify({"error": "Unable to load cases."}), 500
    finally:
        cursor.close()
        conn.close()


@cases_bp.route("/api/cases", methods=["POST"])
def create_case():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed."}), 500
    cursor = conn.cursor(dictionary=True)
    token = uuid.uuid4().hex
    try:
        cursor.execute(
            "INSERT INTO cases (user_id, session_token, status) VALUES (%s, %s, %s)",
            (session.get("user_id"), token, "In Progress"),
        )
        case_pk = cursor.lastrowid
        state = {"module_id": None, "answers": {}, "case_details": {}, "current_question_key": None, "report": None}
        cursor.execute(
            "INSERT INTO case_facts (case_id, fact_key, fact_value) VALUES (%s, %s, %s)",
            (case_pk, _CASE_STATE_KEY, json.dumps(state)),
        )
        conn.commit()
        if session.get("user_id") is None:
            session["guest_case_tokens"] = (_guest_tokens() + [token])[-25:]
        cursor.execute(
            "SELECT case_id, user_id, session_token, created_at, status FROM cases WHERE case_id = %s",
            (case_pk,),
        )
        return jsonify({"success": True, "case": _case_response(cursor.fetchone(), state)}), 201
    except Exception:
        conn.rollback()
        return jsonify({"error": "Unable to create a case."}), 500
    finally:
        cursor.close()
        conn.close()


@cases_bp.route("/api/cases/<session_token>", methods=["GET"])
def get_case(session_token):
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed."}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        case = _case_access(cursor, session_token)
        if not case:
            return jsonify({"error": "Case not found."}), 404
        state = _read_case_state(cursor, case["case_id"])
        return jsonify({"success": True, "case": _case_response(case, state)}), 200
    except Exception:
        return jsonify({"error": "Unable to load this case."}), 500
    finally:
        cursor.close()
        conn.close()


@cases_bp.route("/api/cases/<session_token>", methods=["PUT"])
def update_case(session_token):
    data = request.get_json(silent=True) or {}
    if data.get("module_id") not in (None, "defective_product"):
        return jsonify({"error": "This module is not available yet."}), 409
    if "answers" in data and not isinstance(data["answers"], dict):
        return jsonify({"error": "Answers must be an object."}), 400
    if "case_details" in data and not isinstance(data["case_details"], dict):
        return jsonify({"error": "Case details must be an object."}), 400
    if data.get("status") not in (None, "In Progress", "Completed"):
        return jsonify({"error": "Invalid case status."}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed."}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        case = _case_access(cursor, session_token)
        if not case:
            return jsonify({"error": "Case not found."}), 404
        state = _read_case_state(cursor, case["case_id"])
        for key in ("module_id", "answers", "case_details", "current_question_key", "report"):
            if key in data:
                state[key] = data[key]
        if set(state["answers"]) - _ANSWER_KEYS:
            return jsonify({"error": "The case contains an unsupported answer."}), 400

        cursor.execute("DELETE FROM case_facts WHERE case_id = %s", (case["case_id"],))
        fact_rows = []
        for key, value in state["answers"].items():
            value = str(value).lower() if isinstance(value, bool) else str(value)
            fact_rows.append((case["case_id"], key, value))
        fact_rows.append((case["case_id"], _CASE_STATE_KEY, json.dumps(state)))
        cursor.executemany(
            "INSERT INTO case_facts (case_id, fact_key, fact_value) VALUES (%s, %s, %s)",
            fact_rows,
        )
        if data.get("status"):
            cursor.execute(
                "UPDATE cases SET status = %s WHERE case_id = %s",
                (data["status"], case["case_id"]),
            )
            case["status"] = data["status"]
        conn.commit()
        return jsonify({"success": True, "case": _case_response(case, state)}), 200
    except Exception:
        conn.rollback()
        return jsonify({"error": "Unable to save this case."}), 500
    finally:
        cursor.close()
        conn.close()


@cases_bp.route("/api/cases/<session_token>/facts", methods=["GET"])
def get_case_facts(session_token):
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed."}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        case = _case_access(cursor, session_token)
        if not case:
            return jsonify({"error": "Case not found."}), 404
        state = _read_case_state(cursor, case["case_id"])
        return jsonify({"success": True, "facts": state["answers"]}), 200
    except Exception:
        return jsonify({"error": "Unable to load case facts."}), 500
    finally:
        cursor.close()
        conn.close()
