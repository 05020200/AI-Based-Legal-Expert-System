import uuid
from io import BytesIO

import pytest
from pypdf import PdfReader
from werkzeug.security import generate_password_hash

from backend.app import app
from backend.database.db import get_db_connection
import routes.cases as case_routes


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def cleanup_cases(tokens):
    if not tokens:
        return
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.executemany(
        "DELETE FROM cases WHERE session_token = %s",
        [(token,) for token in tokens],
    )
    connection.commit()
    cursor.close()
    connection.close()


def test_guest_cases_save_reopen_and_isolate_facts(client):
    tokens = []
    try:
        first = client.post("/api/cases")
        second = client.post("/api/cases")
        assert first.status_code == 201
        assert second.status_code == 201
        first_case = first.get_json()["case"]
        second_case = second.get_json()["case"]
        tokens.extend([first_case["session_token"], second_case["session_token"]])

        detail_text = "problem details " * 30
        saved = client.put(f"/api/cases/{first_case['session_token']}", json={
            "module_id": "defective_product",
            "answers": {"product_purchased": True},
            "case_details": {"problem_description": detail_text},
            "current_question_key": "product_purchased",
        })
        assert saved.status_code == 200

        reopened = client.get(f"/api/cases/{first_case['session_token']}")
        assert reopened.status_code == 200
        reopened_case = reopened.get_json()["case"]
        assert reopened_case["answers"] == {"product_purchased": True}
        assert reopened_case["case_details"]["problem_description"] == detail_text
        assert reopened_case["current_question_key"] == "product_purchased"
        assert reopened_case["case_id"].startswith("CASE-2026-")
        assert reopened_case["case_title"] == f"Defective Product — {reopened_case['case_id']}"

        isolated = client.get(f"/api/cases/{second_case['session_token']}")
        assert isolated.get_json()["case"]["answers"] == {}
        assert app.test_client().get(
            f"/api/cases/{first_case['session_token']}"
        ).status_code == 404
    finally:
        cleanup_cases(tokens)


def test_authenticated_case_is_limited_to_its_owner():
    connection = get_db_connection()
    cursor = connection.cursor()
    usernames = [f"case_owner_{uuid.uuid4().hex[:12]}" for _ in range(2)]
    user_ids = []
    tokens = []
    try:
        for username in usernames:
            cursor.execute(
                "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
                (username, generate_password_hash("case-test-password")),
            )
            user_ids.append(cursor.lastrowid)
        connection.commit()

        owner_client = app.test_client()
        with owner_client.session_transaction() as user_session:
            user_session["user_id"] = user_ids[0]
        created = owner_client.post("/api/cases")
        assert created.status_code == 201
        token = created.get_json()["case"]["session_token"]
        tokens.append(token)

        other_client = app.test_client()
        with other_client.session_transaction() as user_session:
            user_session["user_id"] = user_ids[1]
        assert other_client.get(f"/api/cases/{token}").status_code == 404
        assert other_client.delete(f"/api/cases/{token}").status_code == 404
        assert owner_client.get(f"/api/cases/{token}").status_code == 200
        assert owner_client.delete(f"/api/cases/{token}").status_code == 200
        assert owner_client.get(f"/api/cases/{token}").status_code == 404
    finally:
        cleanup_cases(tokens)
        cursor.executemany(
            "DELETE FROM users WHERE user_id = %s",
            [(user_id,) for user_id in user_ids],
        )
        connection.commit()
        cursor.close()
        connection.close()


def test_guest_can_delete_only_their_case_and_cascade_case_data(client):
    created_cases = [client.post("/api/cases").get_json()["case"] for _ in range(2)]
    first, second = created_cases
    tokens = [first["session_token"], second["session_token"]]
    try:
        saved = client.put(f"/api/cases/{first['session_token']}", json={
            "module_id": "defective_product",
            "answers": {"product_purchased": True},
            "case_details": {"problem_description": "Delete cascade check"},
        })
        assert saved.status_code == 200

        deleted = client.delete(f"/api/cases/{first['session_token']}")
        assert deleted.status_code == 200
        assert client.get(f"/api/cases/{first['session_token']}").status_code == 404
        assert client.delete(f"/api/cases/{first['session_token']}").status_code == 404

        remaining = client.get("/api/cases").get_json()["cases"]
        assert [case["session_token"] for case in remaining] == [second["session_token"]]
        unchanged = client.get(f"/api/cases/{second['session_token']}").get_json()["case"]
        assert unchanged["status"] == "In Progress"
        assert unchanged["answers"] == {}
    finally:
        cleanup_cases(tokens)


def test_first_four_consumer_modules_are_available(client):
    response = client.get("/api/modules")
    modules = response.get_json()["modules"]
    assert response.status_code == 200
    assert len(modules) == 6
    assert [module["id"] for module in modules if module["available"]] == [
        "defective_product",
        "refund_replacement",
        "warranty",
        "ecommerce",
    ]


def test_new_module_case_answers_save_reopen_and_remain_isolated(client):
    created = client.post("/api/cases")
    created_case = created.get_json()["case"]
    token = created_case["session_token"]
    try:
        assert created_case["created_at"]
        assert created_case["updated_at"]
        saved = client.put(f"/api/cases/{token}", json={
            "module_id": "refund_replacement",
            "answers": {"product_or_service_purchased": True},
            "case_details": {"product_name": "Mobile Phone"},
            "current_question_key": "refund_or_replacement_requested",
        })
        assert saved.status_code == 200
        assert saved.get_json()["case"]["case_title"] == "Mobile Phone — Refund / Replacement Issue"

        reopened = client.get(f"/api/cases/{token}").get_json()["case"]
        assert reopened["module_id"] == "refund_replacement"
        assert reopened["answers"] == {"product_or_service_purchased": True}
        assert reopened["case_details"]["product_name"] == "Mobile Phone"
        assert reopened["status"] == "In Progress"
        assert reopened["updated_at"] != created_case["updated_at"]

        unsupported = client.put(f"/api/cases/{token}", json={
            "answers": {"product_purchased": True},
        })
        assert unsupported.status_code == 400
    finally:
        cleanup_cases([token])


@pytest.mark.parametrize(("module_id", "document_type", "answers", "case_details"), [
    (
        "refund_replacement",
        "refund_request",
        {"product_or_service_purchased": True, "refund_or_replacement_requested": True},
        {"product_name": "Phone", "problem_description": "Wrong product received"},
    ),
    (
        "warranty",
        "warranty_complaint",
        {"product_purchased": True, "warranty_exists": True, "product_problem_exists": True},
        {"product_name": "Laptop", "seller_name": "Example Seller"},
    ),
    (
        "ecommerce",
        "consumer_commission_complaint",
        {"online_purchase": True, "platform_name": "Example Market", "order_placed": True},
        {"platform_name": "Example Market", "order_or_invoice_number": "ORD-52"},
    ),
])
def test_new_module_document_preview_and_pdf(client, module_id, document_type, answers, case_details):
    pytest.importorskip("reportlab")
    created = client.post("/api/cases")
    token = created.get_json()["case"]["session_token"]
    try:
        saved = client.put(f"/api/cases/{token}", json={
            "module_id": module_id,
            "answers": answers,
            "case_details": case_details,
            "report": {
                "title": "Module Guidance",
                "assessment": "Based on the information provided, this may indicate an issue.",
                "case_summary": {},
                "legal_provisions": [{
                    "act_name": "Consumer Protection Act, 2019",
                    "section_number": "Section 2(9)",
                    "title": "Consumer Rights",
                }],
                "evidence_checklist": [],
            },
        })
        assert saved.status_code == 200

        preview = client.post(f"/api/cases/{token}/documents", json={
            "document_type": document_type,
            "consumer_details": {"consumer_name": "Priya S"},
        })
        assert preview.status_code == 200
        assert preview.get_json()["title"]
        assert "Priya S" in preview.get_json()["preview"]
        if module_id == "ecommerce":
            assert "ORD-52" in preview.get_json()["preview"]

        pdf = client.post(f"/api/cases/{token}/documents/pdf", json={
            "document_type": document_type,
            "consumer_details": {"consumer_name": "Priya S"},
        })
        assert pdf.status_code == 200
        assert pdf.mimetype == "application/pdf"
        assert pdf.data.startswith(b"%PDF")
        text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf.data)).pages)
        assert "Priya S" in text
        ready = client.get(f"/api/cases/{token}").get_json()["case"]
        assert ready["status"] == "Document Ready"
        completed = client.put(f"/api/cases/{token}", json={"status": "Completed"})
        assert completed.status_code == 200
        assert completed.get_json()["case"]["status"] == "Completed"
    finally:
        cleanup_cases([token])


def test_document_generation_requires_explicit_supported_action(monkeypatch, client):
    class FakeTemplateGenerationService:
        _DOCUMENT_TITLES = {
            "seller_complaint": "SELLER COMPLAINT",
            "replacement_request": "REPLACEMENT REQUEST",
            "refund_request": "REFUND REQUEST",
            "consumer_commission_complaint": "CONSUMER COMMISSION COMPLAINT",
        }

        def generate_defective_product_document(self, document_type, case_details, consumer_details):
            assert case_details["product_name"] == "Test product"
            assert consumer_details["consumer_name"] == "Priya S"
            return f"{self._DOCUMENT_TITLES[document_type]} draft for {consumer_details['consumer_name']}."

    monkeypatch.setattr(
        case_routes, "TemplateGenerationService", FakeTemplateGenerationService
    )
    created = client.post("/api/cases")
    token = created.get_json()["case"]["session_token"]
    try:
        saved = client.put(f"/api/cases/{token}", json={
            "module_id": "defective_product",
            "answers": {"product_purchased": True, "product_has_problem": True},
            "case_details": {"product_name": "Test product"},
            "report": {"assessment": "Possible issue"},
        })
        assert saved.status_code == 200
        unsupported = client.post(f"/api/cases/{token}/documents", json={
            "document_type": "arbitrary_document",
            "consumer_details": {"consumer_name": "Priya S"},
        })
        assert unsupported.status_code == 400
        missing_name = client.post(f"/api/cases/{token}/documents", json={
            "document_type": "seller_complaint",
            "consumer_details": {},
        })
        assert missing_name.status_code == 400

        document_types = [
            "seller_complaint",
            "replacement_request",
            "refund_request",
            "consumer_commission_complaint",
        ]
        for document_type in document_types:
            preview = client.post(f"/api/cases/{token}/documents", json={
                "document_type": document_type,
                "consumer_details": {"consumer_name": "Priya S"},
            })
            assert preview.status_code == 200
            assert preview.get_json()["title"] == FakeTemplateGenerationService._DOCUMENT_TITLES[document_type]
            assert document_type.upper().replace("_", " ") in preview.get_json()["preview"]

            pdf_response = client.post(f"/api/cases/{token}/documents/pdf", json={
                "document_type": document_type,
                "consumer_details": {"consumer_name": "Priya S"},
            })
            assert pdf_response.status_code == 200
            assert pdf_response.mimetype == "application/pdf"
            assert pdf_response.data.startswith(b"%PDF")
            pdf_text = "\n".join(
                page.extract_text() or ""
                for page in PdfReader(BytesIO(pdf_response.data)).pages
            )
            assert FakeTemplateGenerationService._DOCUMENT_TITLES[document_type] in pdf_text
            assert "Priya S" in pdf_text

        reopened = client.get(f"/api/cases/{token}").get_json()["case"]
        assert reopened["timeline"][-1]["event"] == "Document generated"
        assert reopened["status"] == "Document Ready"
    finally:
        cleanup_cases([token])


def test_case_status_advances_only_at_workflow_milestones(client, monkeypatch):
    class FakeTemplateGenerationService:
        _DOCUMENT_TITLES = {"seller_complaint": "SELLER COMPLAINT"}

        def generate_defective_product_document(self, document_type, case_details, consumer_details):
            return "Seller complaint draft."

    monkeypatch.setattr(
        case_routes, "TemplateGenerationService", FakeTemplateGenerationService
    )
    created = client.post("/api/cases")
    token = created.get_json()["case"]["session_token"]
    try:
        assert created.get_json()["case"]["status"] == "In Progress"
        guidance = client.put(f"/api/cases/{token}", json={
            "module_id": "defective_product",
            "answers": {"product_purchased": True, "product_has_problem": True},
            "case_details": {"product_name": "Laptop"},
            "report": {"assessment": "Possible issue"},
        })
        assert guidance.get_json()["case"]["status"] == "Guidance Ready"
        assert guidance.get_json()["case"]["case_title"] == "Laptop — Defective Product"

        reopened = client.get(f"/api/cases/{token}").get_json()["case"]
        assert reopened["status"] == "Guidance Ready"

        skipped = client.put(f"/api/cases/{token}", json={"status": "Completed"})
        assert skipped.status_code == 409
        assert client.get(f"/api/cases/{token}").get_json()["case"]["status"] == "Guidance Ready"

        generated = client.post(f"/api/cases/{token}/documents/pdf", json={
            "document_type": "seller_complaint",
            "consumer_details": {"consumer_name": "Priya S"},
        })
        assert generated.status_code == 200
        assert generated.mimetype == "application/pdf"
        assert client.get(f"/api/cases/{token}").get_json()["case"]["status"] == "Document Ready"

        complete = client.put(f"/api/cases/{token}", json={"status": "Completed"})
        assert complete.get_json()["case"]["status"] == "Completed"
        activity_names = [event["event"] for event in complete.get_json()["case"]["timeline"]]
        assert "Case completed" in activity_names
        assert "Case saved" not in activity_names
        assert "Question answered" not in activity_names
    finally:
        cleanup_cases([token])


def test_legacy_completed_status_is_projected_from_actual_activity():
    case = {"status": "Completed"}
    state = {
        "report": {"assessment": "Guidance ready"},
        "timeline": [
            {"event": "Guidance generated"},
            {"event": "Document generated"},
            {"event": "PDF exported"},
        ],
    }
    assert case_routes._effective_status(case, state) == "Document Ready"
    state["timeline"].append({"event": "Case completed"})
    assert case_routes._effective_status(case, state) == "Completed"


def test_pdf_export_returns_pdf_and_records_event(client):
    pytest.importorskip("reportlab")
    created = client.post("/api/cases")
    token = created.get_json()["case"]["session_token"]
    try:
        saved = client.put(f"/api/cases/{token}", json={
            "module_id": "defective_product",
            "answers": {"product_purchased": True, "product_has_problem": True},
            "case_details": {"product_name": "Product A"},
            "report": {
                "title": "Defective Product Legal Guidance Report",
                "possible_issue": "This may be a consumer issue.",
                "assessment": "This may be a consumer issue.",
                "why_relevant": "A product problem was reported.",
                "case_summary": {
                    "selected_issue": "Defective Product",
                    "product_purchased": True,
                    "product_has_problem": True,
                    "product_name": "Product A",
                    "seller_response_resolution": {},
                    "evidence_availability": {},
                },
                "legal_provisions": [],
                "legal_provision": None,
                "evidence_checklist": [],
                "possible_options": ["Consider asking the seller about repair."],
                "next_steps": ["Keep relevant records."],
                "where_to_complain": {},
                "disclaimer": "Preliminary legal information only.",
            },
        })
        assert saved.status_code == 200

        response = client.get(f"/api/cases/{token}/pdf")
        assert response.status_code == 200
        assert response.mimetype == "application/pdf"
        assert response.data.startswith(b"%PDF")
        assert "CASE-2026-" in response.headers["Content-Disposition"]
        pdf_text = "\n".join(
            page.extract_text() or ""
            for page in PdfReader(BytesIO(response.data)).pages
        )
        for section in ["LegalAssist", "Your Situation / Case Summary", "Possible Legal Issue", "Evidence", "What To Do Next", "Where To Complain", "Disclaimer"]:
            assert section in pdf_text
        assert "Product A" in pdf_text
        assert not pdf_text.lstrip().startswith("{")

        reopened = client.get(f"/api/cases/{token}").get_json()["case"]
        assert reopened["timeline"][-1]["event"] == "PDF exported"
    finally:
        cleanup_cases([token])


def test_resolved_case_pdf_keeps_law_but_omits_complaint_guidance(client):
    pytest.importorskip("reportlab")
    created = client.post("/api/cases")
    token = created.get_json()["case"]["session_token"]
    try:
        saved = client.put(f"/api/cases/{token}", json={
            "module_id": "defective_product",
            "answers": {
                "product_purchased": True,
                "product_has_problem": True,
                "seller_contacted": True,
                "seller_resolved": True,
            },
            "case_details": {"product_name": "Resolved Product"},
            "report": {
                "title": "Defective Product Legal Guidance Report",
                "possible_issue": "The seller resolved the reported issue.",
                "why_relevant": "The reported issue has been resolved.",
                "case_summary": {
                    "product_purchased": True,
                    "product_has_problem": True,
                    "seller_response_resolution": {"problem_resolved": True},
                },
                "legal_provisions": [{
                    "act_name": "Consumer Protection Act, 2019",
                    "section_number": "Section 2(10)",
                    "title": "Defect",
                    "description": "Relevant law remains available.",
                }],
                "evidence_checklist": [],
                "possible_options": ["You reported that the seller resolved the issue."],
                "next_steps": ["Keep purchase and resolution records."],
                "where_to_complain": {
                    "grievance_support": {"name": "National Consumer Helpline", "phone": "1915"},
                    "formal_complaint": {"message": "File a complaint before the Consumer Commission."},
                },
                "disclaimer": "Preliminary legal information only.",
            },
        })
        assert saved.status_code == 200

        response = client.get(f"/api/cases/{token}/pdf")
        assert response.status_code == 200
        pdf_text = "\n".join(
            page.extract_text() or ""
            for page in PdfReader(BytesIO(response.data)).pages
        )
        assert "Relevant Law" in pdf_text
        assert "Section 2(10)" in pdf_text
        assert "Where To Complain" not in pdf_text
        assert "National Consumer Helpline" not in pdf_text
        assert "File a complaint before the Consumer Commission" not in pdf_text
    finally:
        cleanup_cases([token])