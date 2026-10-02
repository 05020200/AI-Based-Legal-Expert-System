import json
from pathlib import Path

import pytest

from backend.app import app
from backend.inference_engine.backward_chaining import BackwardChainingEngine
from backend.inference_engine.forward_chaining import ForwardChainingEngine
from backend.inference_engine.working_memory import WorkingMemory
from backend.services import defective_product
from backend.services.defective_product import DefectiveProductService


def load_rules():
    path = Path(__file__).resolve().parents[1] / "knowledge_base" / "defective_product_rules.json"
    return json.loads(path.read_text(encoding="utf-8"))


def complete_answers(**updates):
    answers = {
        "product_purchased": True,
        "product_has_problem": True,
        "seller_contacted": True,
        "seller_resolved": False,
        "desired_resolution": "Repair",
        "purchase_proof_available": True,
        "problem_evidence_available": False,
        "seller_communication_available": True,
    }
    answers.update(updates)
    return answers


class FakeDocumentRecommendationService:
    def recommend(self, issue, available_documents=None):
        assert issue == "Defective Product"
        return {
            "recommended_documents": [
                "purchase_invoice",
                "defect_photos",
                "seller_communication",
            ],
            "recommended_documents_display": [
                {"id": "purchase_invoice", "name": "Purchase Invoice / Receipt"},
                {"id": "defect_photos", "name": "Photographs / Videos of the Defect"},
                {"id": "seller_communication", "name": "Communication Records with Seller"},
            ],
        }


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(
        defective_product,
        "DocumentRecommendationService",
        FakeDocumentRecommendationService,
    )
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def test_questionnaire_contains_required_phase1_questions():
    questions = DefectiveProductService.get_questions()
    assert [question["key"] for question in questions] == [
        "product_purchased",
        "product_has_problem",
        "seller_contacted",
        "seller_resolved",
        "desired_resolution",
        "purchase_proof_available",
        "problem_evidence_available",
        "seller_communication_available",
    ]
    assert not any("reasoning_relevant" in question for question in questions)
    assert questions[4]["options"] == [
        {"label": "Repair", "value": "Repair"},
        {"label": "Replacement", "value": "Replacement"},
        {"label": "Refund", "value": "Refund"},
        {"label": "Not sure", "value": "Not sure"},
    ]


def test_question_navigation_skips_irrelevant_questions_and_supports_back():
    first = DefectiveProductService.get_next_question({})
    assert first["question"]["key"] == "product_purchased"
    assert (first["step"], first["total"]) == (1, 1)

    no_purchase = DefectiveProductService.get_visible_questions({
        "product_purchased": False,
    })
    assert [question["key"] for question in no_purchase] == ["product_purchased"]

    seller_not_contacted = DefectiveProductService.get_visible_questions({
        "product_purchased": True,
        "product_has_problem": True,
        "seller_contacted": False,
    })
    assert [question["key"] for question in seller_not_contacted] == [
        "product_purchased",
        "product_has_problem",
        "seller_contacted",
        "desired_resolution",
        "purchase_proof_available",
        "problem_evidence_available",
        "seller_communication_available",
    ]

    previous = DefectiveProductService.get_next_question(
        {"product_purchased": True}, "product_has_problem", "previous"
    )
    assert previous["question"]["key"] == "product_purchased"
    resumed = DefectiveProductService.get_next_question(
        {"product_purchased": True}, "product_has_problem", "current"
    )
    assert resumed["question"]["key"] == "product_has_problem"


def test_question_navigation_api_returns_one_question_only(client):
    response = client.post("/api/phase1/question", json={
        "answers": {"product_purchased": True},
        "current_key": "product_purchased",
    })
    assert response.status_code == 200
    assert response.get_json()["question"]["key"] == "product_has_problem"
    assert set(response.get_json()) == {"question", "step", "total"}


def test_answers_become_unique_working_memory_facts_and_forward_conclusions():
    result = DefectiveProductService.analyze(
        complete_answers(), {"product_name": "Phone"}
    )
    memory = WorkingMemory()
    for key, value in result["facts"].items():
        memory.add_fact(key, str(value).lower() if isinstance(value, bool) else value)
    assert len(memory.get_all_facts()) == len(result["facts"])
    assert memory.add_fact("product_purchased", "true") is False

    conclusions = ForwardChainingEngine(load_rules()).run(memory)["conclusions"]
    assert conclusions == [
        "possible_defective_product_issue",
        "unresolved_defective_product_issue",
        "consumer_guidance_required",
    ]
    assert len(result["internal"]["reasoning_trace"]) == 3


def test_backward_chaining_proves_goal_and_identifies_missing_relevant_questions():
    rules = load_rules()
    memory = WorkingMemory()
    query = BackwardChainingEngine(rules).query(
        "consumer_guidance_required", "true", memory
    )
    assert {item.split("=", 1)[0] for item in query["missing_facts"]} == {
        "product_purchased",
        "product_has_problem",
        "seller_contacted",
        "seller_resolved",
    }

    memory.add_fact("product_purchased", "true")
    memory.add_fact("product_has_problem", "true")
    memory.add_fact("seller_contacted", "true")
    memory.add_fact("seller_resolved", "false")
    assert BackwardChainingEngine(rules).query(
        "consumer_guidance_required", "true", memory
    )["goal_satisfied"] is True


def test_rules_do_not_identify_unresolved_issue_without_required_facts():
    memory = WorkingMemory()
    memory.add_fact("product_purchased", "true")
    memory.add_fact("product_has_problem", "true")
    memory.add_fact("seller_contacted", "false")
    memory.add_fact("seller_resolved", "false")
    result = ForwardChainingEngine(load_rules()).run(memory)
    assert result["conclusions"] == ["possible_defective_product_issue"]


def test_report_uses_section_210_limited_evidence_and_preserves_case_details():
    result = DefectiveProductService.analyze(
        complete_answers(),
        {
            "product_name": "Phone X",
            "seller_name": "Local Shop",
            "purchase_date": "2026-09-10",
            "amount_paid": "15000",
            "order_or_invoice_number": "INV-7",
            "problem_description": "Screen flickers",
            "seller_response": "Asked me to wait",
        },
    )
    report = result["report"]
    assert report["assessment"].startswith("Based on the information provided")
    assert report["legal_provision"]["section_number"] == "Section 2(10)"
    assert {item["section_number"] for item in report["legal_provisions"]} == {
        "Section 2(10)",
        "Section 35",
        "Section 39",
    }
    assert report["where_to_complain"]["pecuniary_jurisdiction"]["determined"] is True
    assert report["where_to_complain"]["pecuniary_jurisdiction"]["jurisdiction_level"] == "District"
    assert [item["name"] for item in report["evidence_checklist"]] == [
        "Purchase Invoice / Receipt",
        "Photographs / Videos of the Defect",
        "Communication Records with Seller",
    ]
    assert report["case_summary"]["product_name"] == "Phone X"
    assert report["case_summary"]["product_purchased"] is True
    assert report["case_summary"]["product_has_problem"] is True
    assert report["case_summary"]["seller_name"] == "Local Shop"
    assert report["case_summary"]["purchase_date"] == "2026-09-10"
    assert report["case_summary"]["amount_paid"] == 15000
    assert report["case_summary"]["order_or_invoice_number"] == "INV-7"
    assert report["case_summary"]["problem_situation"] == "Screen flickers"
    assert report["case_summary"]["seller_response_resolution"]["response_details"] == "Asked me to wait"
    assert report["case_summary"]["desired_resolution"] == "Repair"
    assert result["internal"]["initial_facts"]["product_purchased"] == "true"
    assert len(result["internal"]["derived_facts"]) == 3
    assert len(result["internal"]["rules_fired"]) == 3
    assert len(result["internal"]["reasoning_trace"]) == 3


def test_api_questions_and_report_keep_guest_flow_without_internal_reasoning(client):
    questions_response = client.get("/api/phase1/questions")
    assert questions_response.status_code == 200
    assert len(questions_response.get_json()["questions"]) == 8

    response = client.post("/api/phase1/analyze", json={
        "answers": complete_answers(),
        "case_details": {"product_name": "Phone X", "amount_paid": 15000},
    })
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["session_token"]
    assert payload["report"]["case_summary"]["selected_issue"] == "Defective Product"
    assert "inference" not in payload
    assert "reasoning" not in payload
    assert "rule_id" not in json.dumps(payload)


def test_api_rejects_incomplete_questionnaire(client):
    response = client.post("/api/phase1/analyze", json={"answers": {}})
    assert response.status_code == 400
    assert "product was purchased" in response.get_json()["error"]


def test_conditional_analysis_preserves_unanswered_fields_as_unprovided(monkeypatch):
    monkeypatch.setattr(
        defective_product,
        "DocumentRecommendationService",
        FakeDocumentRecommendationService,
    )
    result = DefectiveProductService.analyze(
        {"product_purchased": False}, {}
    )
    summary = result["report"]["case_summary"]
    assert summary["product_purchased"] is False
    assert summary["product_has_problem"] is None
    assert summary["seller_contacted"] is None
    assert summary["desired_resolution"] is None
    assert all(item["available"] is None for item in result["report"]["evidence_checklist"])


def test_missing_amount_does_not_guess_complaint_commission(monkeypatch):
    class NoLookupAuthorityService:
        _JURISDICTION_SOURCE = {"source": "Configured 2021 jurisdiction rules"}

        def get_territorial_jurisdiction_info(self):
            return {"territorial_jurisdiction": ["territorial factor"]}

        def get_authority_information(self, amount):
            raise AssertionError("No authority lookup should run without an amount.")

    monkeypatch.setattr(
        defective_product,
        "AuthorityInfoService",
        NoLookupAuthorityService,
    )
    monkeypatch.setattr(
        defective_product,
        "DocumentRecommendationService",
        FakeDocumentRecommendationService,
    )
    report = DefectiveProductService.analyze(complete_answers(), {})["report"]
    jurisdiction = report["where_to_complain"]["pecuniary_jurisdiction"]
    assert jurisdiction["determined"] is False
    assert "Amount paid was not provided" in jurisdiction["message"]