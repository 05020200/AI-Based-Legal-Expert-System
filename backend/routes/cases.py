import json
import uuid
from datetime import datetime, timezone
from io import BytesIO

from flask import Blueprint, jsonify, request, send_file, session

from database.db import get_db_connection
from services.consumer_modules import ConsumerModuleService
from services.template_generation import TemplateGenerationService


cases_bp = Blueprint("cases", __name__)
_CASE_STATE_KEY = "__case_state__"
_MODULES = [
    {"id": "defective_product", "name": "Defective Product", "description": "Product is damaged, faulty, defective, or does not work properly.", "available": True},
    {"id": "refund_replacement", "name": "Refund / Replacement Issue", "description": "A seller has not provided a requested refund or replacement.", "available": True},
    {"id": "warranty", "name": "Warranty Issue", "description": "A product problem has arisen and requested warranty service may not have been provided.", "available": True},
    {"id": "ecommerce", "name": "E-Commerce Consumer Issue", "description": "A problem occurred with an order placed through an online platform, website, or app.", "available": True},
    {"id": "service_deficiency", "name": "Deficiency in Service", "description": "A service was not provided properly or as expected.", "available": False},
    {"id": "unfair_trade_practice", "name": "Misleading Advertisement / Unfair Trade Practice", "description": "An advertisement or business practice may be misleading or unfair.", "available": False},
]
_MODULE_BY_ID = {module["id"]: module for module in _MODULES}
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
_CASE_ANSWER_KEYS = set(_ANSWER_KEYS)
_BOOLEAN_ANSWER_KEYS = _ANSWER_KEYS - {"desired_resolution"}
for _module_id in ConsumerModuleService.available_module_ids():
    _CASE_ANSWER_KEYS.update(ConsumerModuleService.answer_keys(_module_id))
    _BOOLEAN_ANSWER_KEYS.update(
        question["key"]
        for question in ConsumerModuleService.get_module(_module_id)["questions"]
        if question["type"] == "boolean"
    )
_PUBLIC_ACTIVITY = {
    "Case created",
    "Questions completed",
    "Case details saved",
    "Guidance generated",
    "Document generated",
    "PDF exported",
    "Case completed",
}


@cases_bp.route("/api/modules", methods=["GET"])
def get_modules():
    return jsonify({"modules": _MODULES}), 200


def _guest_tokens():
    return session.get("guest_case_tokens", [])


def _timeline_event(event, details=None):
    return {
        "event": event,
        "at": datetime.now(timezone.utc).isoformat(),
        "details": details or {},
    }


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


def _case_title(state, case_label):
    module = next((item for item in _MODULES if item["id"] == state.get("module_id")), None)
    issue = module["name"] if module else "New case"
    module_id = state.get("module_id")
    detail_key = "product_name"
    if module_id in ConsumerModuleService.available_module_ids():
        detail_key = ConsumerModuleService.get_module(module_id).get("title_detail_key", detail_key)
    title_detail = state.get("case_details", {}).get(detail_key) or state.get("answers", {}).get(detail_key)
    if title_detail:
        return f"{title_detail} — {issue}"
    return f"{issue} — {case_label}"


def _public_activity(events):
    visible = []
    seen = set()
    for event in events:
        name = event.get("event")
        if name not in _PUBLIC_ACTIVITY:
            continue
        timestamp = event.get("at", "")
        day = timestamp[:10]
        key = (name, day)
        if key in seen:
            continue
        seen.add(key)
        visible.append(event)
    return visible


def _add_activity(state, event, details=None):
    state.setdefault("timeline", [])
    today = datetime.now(timezone.utc).date().isoformat()
    if any(
        item.get("event") == event and item.get("at", "")[:10] == today
        for item in state["timeline"]
    ):
        return
    state["timeline"].append(_timeline_event(event, details))


def _effective_status(case, state):
    status = case["status"]
    events = state.get("timeline", [])
    if status == "Completed" and not any(
        event.get("event") == "Case completed" for event in events
    ):
        if state.get("generated_documents") or any(
            event.get("event") == "Document generated" for event in events
        ):
            return "Document Ready"
        if state.get("report"):
            return "Guidance Ready"
        return "In Progress"
    return status


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
        "facts": {},
        "derived_facts": {},
        "reasoning_trace": [],
        "backward_result": None,
        "updated_at": None,
        "timeline": [],
    }
    for row in cursor.fetchall():
        if row["fact_key"] == _CASE_STATE_KEY:
            try:
                state.update(json.loads(row["fact_value"]))
            except (TypeError, json.JSONDecodeError):
                continue
        elif row["fact_key"] in _CASE_ANSWER_KEYS:
            value = row["fact_value"]
            if row["fact_key"] in _BOOLEAN_ANSWER_KEYS:
                if value == "true":
                    value = True
                elif value == "false":
                    value = False
            state["answers"][row["fact_key"]] = value
    return state


def _case_response(case, state):
    created = case["created_at"]
    case_label = _case_label(case)
    response_state = dict(state)
    response_state["timeline"] = _public_activity(state.get("timeline", []))
    return {
        "case_id": case_label,
        "case_title": _case_title(state, case_label),
        "session_token": case["session_token"],
        "created_at": created.isoformat() if hasattr(created, "isoformat") else str(created),
        "updated_at": state.get("updated_at") or (
            created.isoformat() if hasattr(created, "isoformat") else str(created)
        ),
        "status": _effective_status(case, state),
        **response_state,
    }


def _persist_case_state(cursor, case_id, state):
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    cursor.execute("DELETE FROM case_facts WHERE case_id = %s", (case_id,))
    fact_rows = [
        (case_id, key, str(value).lower() if isinstance(value, bool) else str(value))
        for key, value in state["answers"].items()
    ]
    fact_rows.append((case_id, _CASE_STATE_KEY, json.dumps(state)))
    cursor.executemany(
        "INSERT INTO case_facts (case_id, fact_key, fact_value) VALUES (%s, %s, %s)",
        fact_rows,
    )


def _answer_keys_for_module(module_id):
    if module_id == "defective_product":
        return _ANSWER_KEYS
    if module_id in ConsumerModuleService.available_module_ids():
        return ConsumerModuleService.answer_keys(module_id)
    return set()


def _document_types_for_module(module_id):
    if module_id == "defective_product":
        return {
            "seller_complaint", "replacement_request", "refund_request",
            "consumer_commission_complaint",
        }
    if module_id in ConsumerModuleService.available_module_ids():
        return {
            item["type"]
            for item in ConsumerModuleService.get_module(module_id)["documents"]
        }
    return set()


def _generate_case_document(module_id, document_type, case, state, consumer_details):
    service = TemplateGenerationService()
    document_data = dict(state["case_details"])
    document_data.update({
        "case_id": _case_label(case),
        "answers": state["answers"],
        "report": state["report"],
        "desired_resolution": state["answers"].get("desired_resolution"),
        "selected_resolution": state["answers"].get("desired_resolution"),
    })
    if module_id == "defective_product":
        draft = service.generate_defective_product_document(
            document_type, document_data, consumer_details
        )
    else:
        draft = service.generate_consumer_module_document(
            module_id,
            document_type,
            _case_label(case),
            state["case_details"],
            state["answers"],
            state["report"],
            consumer_details,
        )
    return draft, TemplateGenerationService._DOCUMENT_TITLES[document_type]


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
            case_label = _case_label(case)
            result.append({
                "case_id": case_label,
                "case_title": _case_title(state, case_label),
                "session_token": case["session_token"],
                "issue": module["name"] if module else "Not selected",
                "status": _effective_status(case, state),
                "created_at": case["created_at"].isoformat()
                if hasattr(case["created_at"], "isoformat") else str(case["created_at"]),
                "updated_at": state.get("updated_at") or (
                    case["created_at"].isoformat()
                    if hasattr(case["created_at"], "isoformat") else str(case["created_at"])
                ),
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
        state = {
            "module_id": None,
            "answers": {},
            "case_details": {},
            "current_question_key": None,
            "report": None,
            "facts": {},
            "derived_facts": {},
            "reasoning_trace": [],
            "backward_result": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "timeline": [_timeline_event("Case created")],
        }
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
    if data.get("module_id") not in (
        None, "defective_product", *ConsumerModuleService.available_module_ids()
    ):
        return jsonify({"error": "This module is not available yet."}), 409
    if "answers" in data and not isinstance(data["answers"], dict):
        return jsonify({"error": "Answers must be an object."}), 400
    if "case_details" in data and not isinstance(data["case_details"], dict):
        return jsonify({"error": "Case details must be an object."}), 400
    if data.get("status") not in (None, "Completed"):
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
        previous_case_details = dict(state["case_details"])
        previous_question_key = state.get("current_question_key")
        previous_report = state.get("report")
        previous_status = _effective_status(case, state)
        if data.get("status") == "Completed" and not (
            state.get("generated_documents")
            or any(
                event.get("event") == "Document generated"
                for event in state.get("timeline", [])
            )
        ):
            return jsonify({
                "error": "Generate a case document before completing this case."
            }), 409
        for key in (
            "module_id", "answers", "case_details", "current_question_key", "report",
            "facts", "derived_facts", "reasoning_trace", "backward_result",
        ):
            if key in data:
                state[key] = data[key]
        if set(state["answers"]) - _answer_keys_for_module(state.get("module_id")):
            return jsonify({"error": "The case contains an unsupported answer."}), 400

        if data.get("current_question_key") == "analysis" and previous_question_key != "analysis":
            _add_activity(state, "Questions completed")
        if state["case_details"] != previous_case_details and data.get("current_question_key") == "analysis":
            _add_activity(state, "Case details saved")
        if not previous_report and state.get("report"):
            _add_activity(state, "Guidance generated")
        if data.get("status") == "Completed" and case["status"] != "Completed":
            _add_activity(state, "Case completed")

        _persist_case_state(cursor, case["case_id"], state)
        if data.get("status") == "Completed":
            case["status"] = "Completed"
        elif previous_status == "Completed":
            case["status"] = "Completed"
        elif state.get("generated_documents") or any(
            event.get("event") == "Document generated" for event in state.get("timeline", [])
        ):
            case["status"] = "Document Ready"
        elif state.get("report"):
            case["status"] = "Guidance Ready"
        else:
            case["status"] = "In Progress"
        cursor.execute(
            "UPDATE cases SET status = %s WHERE case_id = %s",
            (case["status"], case["case_id"]),
        )
        conn.commit()
        return jsonify({"success": True, "case": _case_response(case, state)}), 200
    except Exception:
        conn.rollback()
        return jsonify({"error": "Unable to save this case."}), 500
    finally:
        cursor.close()
        conn.close()


@cases_bp.route("/api/cases/<session_token>", methods=["DELETE"])
def delete_case(session_token):
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed."}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        case = _case_access(cursor, session_token)
        if not case:
            return jsonify({"error": "Case not found."}), 404
        cursor.execute("DELETE FROM cases WHERE case_id = %s", (case["case_id"],))
        conn.commit()
        if session.get("user_id") is None:
            session["guest_case_tokens"] = [
                token for token in _guest_tokens() if token != session_token
            ]
        return jsonify({"success": True}), 200
    except Exception:
        conn.rollback()
        return jsonify({"error": "Unable to delete this case."}), 500
    finally:
        cursor.close()
        conn.close()


@cases_bp.route("/api/cases/<session_token>/documents", methods=["POST"])
def preview_case_document(session_token):
    data = request.get_json(silent=True) or {}
    document_type = data.get("document_type")
    consumer_details = data.get("consumer_details")
    if document_type not in TemplateGenerationService._DOCUMENT_TITLES:
        return jsonify({"error": "Choose a supported document type."}), 400
    if not isinstance(consumer_details, dict):
        return jsonify({"error": "Enter consumer details to continue."}), 400
    consumer_details = {
        key: str(consumer_details.get(key, "")).strip()
        for key in ("consumer_name", "consumer_address", "consumer_phone", "consumer_email", "document_date")
    }
    if not consumer_details["consumer_name"]:
        return jsonify({"error": "Consumer name is required."}), 400
    if any(len(value) > 500 for value in consumer_details.values()):
        return jsonify({"error": "Consumer details must be 500 characters or fewer."}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed."}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        case = _case_access(cursor, session_token)
        if not case:
            return jsonify({"error": "Case not found."}), 404
        state = _read_case_state(cursor, case["case_id"])
        module_id = state.get("module_id")
        if module_id not in _MODULE_BY_ID or not state.get("report"):
            return jsonify({"error": "Complete the selected module analysis first."}), 409
        if document_type not in _document_types_for_module(module_id):
            return jsonify({"error": "Choose a document supported for this issue."}), 400

        draft, title = _generate_case_document(
            module_id, document_type, case, state, consumer_details
        )
        return jsonify({"success": True, "document_type": document_type, "title": title, "preview": draft}), 200
    except ValueError as error:
        conn.rollback()
        return jsonify({"error": str(error)}), 400
    except Exception:
        conn.rollback()
        return jsonify({"error": "Unable to generate this document."}), 500
    finally:
        cursor.close()
        conn.close()


@cases_bp.route("/api/cases/<session_token>/documents/pdf", methods=["POST"])
def generate_case_document_pdf(session_token):
    data = request.get_json(silent=True) or {}
    document_type = data.get("document_type")
    consumer_details = data.get("consumer_details")
    if document_type not in TemplateGenerationService._DOCUMENT_TITLES or not isinstance(consumer_details, dict):
        return jsonify({"error": "Choose a document type and provide consumer details."}), 400
    consumer_details = {
        key: str(consumer_details.get(key, "")).strip()
        for key in ("consumer_name", "consumer_address", "consumer_phone", "consumer_email", "document_date")
    }
    if not consumer_details["consumer_name"]:
        return jsonify({"error": "Consumer name is required."}), 400
    if any(len(value) > 500 for value in consumer_details.values()):
        return jsonify({"error": "Consumer details must be 500 characters or fewer."}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed."}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        from services.pdf_export import build_legal_document_pdf

        case = _case_access(cursor, session_token)
        if not case:
            return jsonify({"error": "Case not found."}), 404
        state = _read_case_state(cursor, case["case_id"])
        module_id = state.get("module_id")
        if module_id not in _MODULE_BY_ID or not state.get("report"):
            return jsonify({"error": "Complete the selected module analysis first."}), 409
        if document_type not in _document_types_for_module(module_id):
            return jsonify({"error": "Choose a document supported for this issue."}), 400
        draft, title = _generate_case_document(
            module_id, document_type, case, state, consumer_details
        )
        pdf_bytes = build_legal_document_pdf(title, draft, _case_label(case))
        state.setdefault("generated_documents", []).append({
            "document_type": document_type,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })
        _add_activity(state, "Document generated", {"document_type": document_type})
        if _effective_status(case, state) != "Completed":
            case["status"] = "Document Ready"
            cursor.execute(
                "UPDATE cases SET status = %s WHERE case_id = %s",
                (case["status"], case["case_id"]),
            )
        _persist_case_state(cursor, case["case_id"], state)
        conn.commit()
        return send_file(
            BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"{_case_label(case)}-{document_type}.pdf",
        )
    except ValueError as error:
        conn.rollback()
        return jsonify({"error": str(error)}), 400
    except Exception:
        conn.rollback()
        return jsonify({"error": "Unable to generate this document PDF."}), 500
    finally:
        cursor.close()
        conn.close()


@cases_bp.route("/api/cases/<session_token>/pdf", methods=["GET"])
def export_case_pdf(session_token):
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed."}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        from services.pdf_export import build_case_report_pdf

        case = _case_access(cursor, session_token)
        if not case:
            return jsonify({"error": "Case not found."}), 404
        state = _read_case_state(cursor, case["case_id"])
        if state.get("module_id") != "defective_product" or not state.get("report"):
            return jsonify({"error": "Complete the Defective Product analysis first."}), 409

        state["timeline"].append(_timeline_event("PDF exported"))
        pdf_bytes = build_case_report_pdf(
            state["report"],
            _case_label(case),
            case["created_at"].isoformat() if hasattr(case["created_at"], "isoformat") else str(case["created_at"]),
            state["answers"],
            _public_activity(state["timeline"]),
            _case_title(state, _case_label(case)),
        )
        _persist_case_state(cursor, case["case_id"], state)
        if _effective_status(case, state) != "Completed":
            case["status"] = _effective_status(case, state)
            cursor.execute(
                "UPDATE cases SET status = %s WHERE case_id = %s",
                (case["status"], case["case_id"]),
            )
        conn.commit()
        return send_file(
            BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"{_case_label(case)}-report.pdf",
        )
    except Exception:
        conn.rollback()
        return jsonify({"error": "Unable to export this case as PDF."}), 500
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
        return jsonify({"success": True, "facts": state.get("facts") or state["answers"]}), 200
    except Exception:
        return jsonify({"error": "Unable to load case facts."}), 500
    finally:
        cursor.close()
        conn.close()
