import json
from pathlib import Path

import pytest

from backend.app import app
from backend.services.consumer_modules import ConsumerModuleService


@pytest.fixture
def service(monkeypatch):
    class NoDatabaseDocumentRecommendations:
        def __init__(self):
            pass

    monkeypatch.setattr(
        "services.defective_product.DocumentRecommendationService",
        NoDatabaseDocumentRecommendations,
    )
    return ConsumerModuleService


def test_module_definitions_and_conditional_question_flow(service):
    assert service.available_module_ids() == {
        "refund_replacement", "warranty", "ecommerce",
        "service_deficiency", "unfair_trade_practice",
    }

    purchase_only = service.get_visible_questions(
        "refund_replacement", {"product_or_service_purchased": True}
    )
    assert [question["key"] for question in purchase_only] == [
        "product_or_service_purchased",
        "refund_or_replacement_requested",
        "purchase_proof_available",
    ]

    refund_requested = service.get_visible_questions(
        "refund_replacement",
        {"product_or_service_purchased": True, "refund_or_replacement_requested": True},
    )
    assert "reason_for_request" in [question["key"] for question in refund_requested]
    assert "seller_contacted" in [question["key"] for question in refund_requested]

    no_order = service.get_visible_questions("ecommerce", {"online_purchase": True})
    assert [question["key"] for question in no_order] == [
        "online_purchase", "platform_name", "order_placed"
    ]

    service_purchase = service.get_visible_questions(
        "service_deficiency", {"service_purchased": True}
    )
    assert "service_problem_exists" in [question["key"] for question in service_purchase]

    no_advertisement = service.get_visible_questions(
        "unfair_trade_practice", {"advertisement_seen": False}
    )
    assert [question["key"] for question in no_advertisement] == ["advertisement_seen"]


def test_module_facts_are_registered_in_the_shared_fact_catalog(service):
    knowledge_base = Path(__file__).resolve().parents[1] / "knowledge_base"
    catalog = json.loads((knowledge_base / "facts.json").read_text(encoding="utf-8"))
    definitions = json.loads(
        (knowledge_base / "consumer_issue_modules.json").read_text(encoding="utf-8")
    )
    catalog_keys = [item["fact_key"] for item in catalog]
    assert len(catalog_keys) == len(set(catalog_keys))

    used_keys = set()
    for module_id, definition in definitions.items():
        used_keys.update(service.answer_keys(module_id))
        used_keys.update(
            condition["fact_key"]
            for rule in definition["rules"]
            for condition in rule["conditions"]
        )
        used_keys.update(rule["conclusion"] for rule in definition["rules"])
        used_keys.update(
            derived_key
            for choices in definition.get("choice_derivations", {}).values()
            for derived in choices.values()
            for derived_key in derived
        )
    assert used_keys <= set(catalog_keys)


def test_refund_replacement_rules_guidance_and_resolution(service):
    answers = {
        "product_or_service_purchased": True,
        "refund_or_replacement_requested": True,
        "reason_for_request": "Wrong product received",
        "product_has_problem": True,
        "seller_contacted": True,
        "seller_agreed": False,
        "refund_or_replacement_provided": False,
        "seller_response": "Request declined",
        "purchase_proof_available": True,
        "problem_evidence_available": True,
        "seller_communication_available": True,
        "desired_resolution": "Refund",
    }
    result = service.analyze("refund_replacement", answers, {
        "product_name": "mattress",
        "seller_name": "Keerthi Mattress",
    })
    report = result["report"]
    assert result["facts"] == answers
    assert result["rules_fired"] == ["RR1", "RR2", "RR3", "RR4", "RR5"]
    assert result["backward_result"]["goal_satisfied"] is True
    assert report["case_summary"]["product_name"] == "mattress"
    assert report["case_summary"]["seller_name"] == "Keerthi Mattress"
    assert report["case_summary"]["reason_for_request"] == "Wrong product received"
    assert report["case_summary"]["seller_agreed"] is False
    assert "reported receiving the wrong product" in report["case_summary"]["situation_text"]
    assert "seller refused the refund" in report["case_summary"]["situation_text"]
    assert "refused refund request" in report["possible_issue"]
    assert report["evidence_checklist"] == [
        {"name": "Purchase Invoice / Receipt", "available": True},
        {"name": "Product Photos / Videos", "available": True},
        {"name": "Seller Communication", "available": True},
    ]
    assert len(report["recommended_evidence"]) == 6
    assert not set(report["recommended_evidence"]) & {
        item["name"] for item in report["evidence_checklist"] if item["available"] is True
    }
    assert report["possible_options"] == [
        "You may continue to seek the requested refund, subject to the facts and applicable terms."
    ]
    assert report["case_summary"]["situation_text"] == (
        "You purchased a mattress from Keerthi Mattress and reported receiving the wrong product. "
        "You contacted the seller and requested a refund, but the seller refused the refund."
    )
    assert any("Consumer Rights" in item["title"] for item in report["legal_provisions"])
    assert "Section 35" in {item["section_number"] for item in report["legal_provisions"]}
    assert any("restating your refund request" in step for step in report["next_steps"])
    assert any("National Consumer Helpline (1915)" in step for step in report["next_steps"])

    answers["seller_agreed"] = True
    answers["refund_or_replacement_provided"] = True
    resolved = service.analyze("refund_replacement", answers, {})
    assert "RR2" not in resolved["rules_fired"]
    assert resolved["report"]["where_to_complain"] is None
    assert resolved["report"]["next_steps"] == [
        "Keep your purchase proof, communication with the seller, and records showing how the request was resolved."
    ]


def test_warranty_rules_preserve_coverage_uncertainty(service):
    answers = {
        "product_purchased": True,
        "warranty_exists": True,
        "warranty_document_available": False,
        "product_problem_exists": True,
        "warranty_service_requested": True,
        "seller_or_service_contacted": True,
        "warranty_service_provided": False,
        "warranty_service_refused": True,
        "warranty_refusal_reason": "Claim declined",
        "purchase_proof_available": True,
        "service_record_available": False,
        "communication_available": True,
        "desired_resolution": "Repair",
    }
    result = service.analyze("warranty", answers, {
        "product_name": "Phone",
        "seller_address": "1 Repair Lane",
        "purchase_date": "2026-01-12",
        "amount_paid": "50000",
        "problem_description": "Laptop will not power on",
    })
    report = result["report"]
    assert result["rules_fired"] == ["W1", "W2", "W3", "W4", "W5"]
    assert result["backward_result"]["goal_satisfied"] is True
    assert report["case_summary"]["warranty_exists"] is True
    assert report["case_summary"]["seller_address"] == "1 Repair Lane"
    assert report["case_summary"]["purchase_date"] == "2026-01-12"
    assert report["case_summary"]["amount_paid"] == "50000"
    assert report["case_summary"]["problem_description"] == "Laptop will not power on"
    assert report["case_summary"]["warranty_service_refused"] is True
    assert "Claim declined" in report["case_summary"]["situation_text"]
    assert "unresolved warranty-service request" in report["possible_issue"]
    assert "does not establish that the reported problem is covered" in " ".join(
        report["possible_options"]
    )
    assert {item["section_number"] for item in report["legal_provisions"]} == {
        "Section 2(9)", "Section 2(8)", "Section 35"
    }
    assert report["evidence_checklist"][0]["available"] is False
    assert len(report["recommended_evidence"]) == 5
    assert not set(report["recommended_evidence"]) & {
        item["name"] for item in report["evidence_checklist"] if item["available"] is True
    }

    resolved_answers = dict(answers)
    resolved_answers["warranty_service_provided"] = True
    resolved_answers.pop("warranty_service_refused")
    resolved_answers.pop("warranty_refusal_reason")
    resolved = service.analyze("warranty", resolved_answers, {"product_name": "Phone"})["report"]
    assert "was provided" in resolved["possible_issue"]
    assert resolved["where_to_complain"] is None
    assert not any("remains unresolved" in item for item in resolved["possible_options"])
    assert not any("Consumer Commission" in item for item in resolved["next_steps"])


def test_ecommerce_derivations_rules_guidance_and_evidence(service):
    answers = {
        "online_purchase": True,
        "platform_name": "Example Market",
        "order_placed": True,
        "payment_made": True,
        "delivery_received": False,
        "ecommerce_problem_type": "product_not_delivered",
        "seller_contacted": True,
        "seller_response": "Shipment under review",
        "issue_resolved": False,
        "order_proof_available": True,
        "payment_proof_available": True,
        "delivery_proof_available": False,
        "communication_available": True,
        "desired_resolution": "Refund",
    }
    result = service.analyze("ecommerce", answers, {
        "product_name": "Wireless mouse",
        "seller_name": "Gadget House",
        "seller_address": "8 Market Road",
        "purchase_date": "2026-09-22",
        "amount_paid": "2500",
        "order_or_invoice_number": "OR-19",
    })
    report = result["report"]
    assert result["facts"]["product_not_received"] is True
    assert result["rules_fired"] == ["EC1", "EC2", "EC4", "EC6", "EC7"]
    assert result["backward_result"]["goal_satisfied"] is True
    assert report["case_summary"]["platform_name"] == "Example Market"
    assert report["case_summary"]["product_name"] == "Wireless mouse"
    assert report["case_summary"]["seller_name"] == "Gadget House"
    assert report["case_summary"]["order_or_invoice_number"] == "OR-19"
    assert report["case_summary"]["ecommerce_problem_type"] == "product_not_delivered"
    assert "non-delivery" in report["case_summary"]["situation_text"]
    assert "unresolved online-order issue" in report["possible_issue"]
    assert "requested refund" in report["possible_options"][0]
    assert "Section 2(16)" in {item["section_number"] for item in report["legal_provisions"]}
    assert "Section 2(8)" in {item["section_number"] for item in report["legal_provisions"]}
    assert "Section 35" in {item["section_number"] for item in report["legal_provisions"]}
    assert [item["available"] for item in report["evidence_checklist"]] == [
        True, True, False, True
    ]
    assert len(report["recommended_evidence"]) == 7
    assert not set(report["recommended_evidence"]) & {
        item["name"] for item in report["evidence_checklist"] if item["available"] is True
    }
    assert len(result["reasoning_trace"]) == len(result["rules_fired"])

    resolved_answers = dict(answers)
    resolved_answers["issue_resolved"] = True
    resolved = service.analyze("ecommerce", resolved_answers, {})["report"]
    assert "was resolved" in resolved["possible_issue"]
    assert resolved["where_to_complain"] is None
    assert not any("remains unresolved" in item for item in resolved["possible_options"])
    assert not any("Consumer Commission" in item for item in resolved["next_steps"])


@pytest.mark.parametrize(("problem_type", "expected_fact", "expected_rule", "delivery_received"), [
    ("product_not_delivered", "product_not_received", "EC2", False),
    ("wrong_product", "wrong_product", "EC3", True),
    ("damaged_product", "damaged_product", "EC8", True),
    ("defective_product", "product_defective", "EC9", True),
    ("incomplete_order", "incomplete_order", "EC10", True),
    ("product_not_as_described", "product_not_as_described", "EC11", True),
    ("refund_not_received", "refund_pending", "EC12", True),
    ("replacement_not_provided", "replacement_pending", "EC13", True),
    ("cancellation_issue", "cancellation_issue", "EC14", True),
])
def test_ecommerce_problem_categories_derive_distinct_facts_and_rules(
    service, problem_type, expected_fact, expected_rule, delivery_received
):
    answers = {
        "online_purchase": True,
        "platform_name": "Shop",
        "order_placed": True,
        "payment_made": True,
        "delivery_received": delivery_received,
        "ecommerce_problem_type": problem_type,
        "seller_contacted": False,
        "order_proof_available": True,
        "payment_proof_available": True,
        "delivery_proof_available": False,
        "desired_resolution": "Refund",
    }
    result = service.analyze("ecommerce", answers, {})
    assert result["facts"][expected_fact] is True
    assert expected_rule in result["rules_fired"]
    assert result["report"]["case_summary"]["ecommerce_problem_type"] == problem_type
    assert ConsumerModuleService._ecommerce_problem_label(problem_type) in result["report"]["case_summary"]["situation_text"]


def test_service_deficiency_report_evidence_and_resolution(service):
    answers = {
        "service_purchased": True,
        "service_type": "Home cleaning",
        "service_provider": "CleanCo",
        "service_date": "2026-09-20",
        "amount_paid": "1500",
        "service_problem_exists": True,
        "problem_description": "Cleaner did not arrive",
        "service_not_provided": True,
        "service_delayed": False,
        "service_inadequate": False,
        "service_not_as_agreed": False,
        "provider_contacted": True,
        "provider_response": "No response",
        "issue_resolved": False,
        "desired_resolution": "Refund",
        "purchase_proof_available": True,
        "service_evidence_available": True,
        "communication_available": True,
    }
    result = service.analyze("service_deficiency", answers, {
        "seller_address": "12 Main Street",
        "order_or_invoice_number": "SV-100",
    })
    report = result["report"]
    assert result["rules_fired"] == ["SV1", "SV2", "SV3", "SV4"]
    assert result["backward_result"]["goal_satisfied"] is True
    assert "Cleaner did not arrive" in report["case_summary"]["situation_text"]
    assert report["case_summary"]["seller_address"] == "12 Main Street"
    assert report["case_summary"]["order_or_invoice_number"] == "SV-100"
    assert "unresolved consumer issue" in report["possible_issue"]
    assert "Section 2(11)" in {item["section_number"] for item in report["legal_provisions"]}
    assert "Section 35" in {item["section_number"] for item in report["legal_provisions"]}
    assert [item["available"] for item in report["evidence_checklist"]] == [True, True, True]
    assert len(report["recommended_evidence"]) == 5
    assert not set(report["recommended_evidence"]) & {
        item["name"] for item in report["evidence_checklist"] if item["available"] is True
    }
    assert "requested refund" in report["possible_options"][0]
    assert any("National Consumer Helpline" in item for item in report["next_steps"])

    resolved_answers = dict(answers)
    resolved_answers["issue_resolved"] = True
    resolved = service.analyze("service_deficiency", resolved_answers, {})["report"]
    assert "was resolved" in resolved["possible_issue"]
    assert resolved["where_to_complain"] is None
    assert not any("Consumer Commission" in item for item in resolved["next_steps"])

    no_problem = dict(answers)
    no_problem["service_problem_exists"] = False
    for key in (
        "problem_description", "service_not_provided", "service_delayed",
        "service_inadequate", "service_not_as_agreed", "provider_contacted",
        "provider_response", "issue_resolved", "desired_resolution",
        "service_evidence_available", "communication_available",
    ):
        no_problem.pop(key)
    no_problem_result = service.analyze("service_deficiency", no_problem, {})
    assert "deficient_service_issue" not in no_problem_result["facts"]
    assert no_problem_result["report"]["legal_provisions"] == []


def test_unfair_trade_practice_report_requires_supported_claim_facts(service):
    answers = {
        "advertisement_seen": True,
        "advertisement_source": "Website",
        "advertiser_or_business": "BrightHome",
        "product_or_service": "Cleaning service",
        "claim_made": True,
        "claim_description": "Same-day service guaranteed",
        "actual_experience": "No appointment was provided",
        "claim_false_or_misleading": True,
        "important_information_hidden": False,
        "price_or_discount_claim": False,
        "product_or_service_received": True,
        "difference_from_advertisement": "No service was provided",
        "business_contacted": True,
        "business_response": "We are reviewing this",
        "issue_resolved": False,
        "desired_resolution": "Refund",
        "advertisement_evidence_available": True,
        "purchase_proof_available": True,
        "communication_available": True,
    }
    result = service.analyze("unfair_trade_practice", answers, {
        "seller_address": "4 Claim Road",
        "purchase_date": "2026-09-22",
        "amount_paid": "2500",
        "order_or_invoice_number": "AD-50",
    })
    report = result["report"]
    assert result["rules_fired"] == ["UT1", "UT3", "UT4", "UT5"]
    assert result["backward_result"]["goal_satisfied"] is True
    assert "Same-day service guaranteed" in report["case_summary"]["situation_text"]
    assert report["case_summary"]["seller_address"] == "4 Claim Road"
    assert report["case_summary"]["purchase_date"] == "2026-09-22"
    assert report["case_summary"]["amount_paid"] == "2500"
    assert report["case_summary"]["order_or_invoice_number"] == "AD-50"
    assert "may raise a consumer issue" in report["possible_issue"]
    assert "Section 2(47)" in {item["section_number"] for item in report["legal_provisions"]}
    assert "Section 35" in {item["section_number"] for item in report["legal_provisions"]}
    assert [item["available"] for item in report["evidence_checklist"]] == [True, True, True]
    assert len(report["recommended_evidence"]) == 5
    assert not set(report["recommended_evidence"]) & {
        item["name"] for item in report["evidence_checklist"] if item["available"] is True
    }
    assert "requested refund" in report["possible_options"][0]

    resolved_answers = dict(answers)
    resolved_answers["issue_resolved"] = True
    resolved = service.analyze("unfair_trade_practice", resolved_answers, {})["report"]
    assert "issue was resolved" in resolved["possible_issue"]
    assert resolved["where_to_complain"] is None
    assert not any("Consumer Commission" in item for item in resolved["next_steps"])

    disagreement_only = dict(answers)
    disagreement_only["claim_false_or_misleading"] = False
    cautious = service.analyze("unfair_trade_practice", disagreement_only, {})
    assert "potential_unfair_trade_practice" not in cautious["facts"]
    hidden_information = dict(disagreement_only)
    hidden_information["important_information_hidden"] = True
    hidden = service.analyze("unfair_trade_practice", hidden_information, {})
    assert "UT2" in hidden["rules_fired"]


def test_module_analysis_rejects_hidden_or_missing_required_answers(service):
    with pytest.raises(ValueError, match="Please answer"):
        service.analyze("warranty", {"product_purchased": True}, {})

    with pytest.raises(ValueError, match="no longer relevant"):
        service.analyze("ecommerce", {
            "online_purchase": False,
            "order_placed": True,
        }, {})


def test_module_question_and_analysis_api_uses_shared_reasoning():
    client = app.test_client()
    service_questions = client.get("/api/modules/service_deficiency/questions")
    assert service_questions.status_code == 200
    assert len(service_questions.get_json()["questions"]) == 18
    advertisement_questions = client.get("/api/modules/unfair_trade_practice/questions")
    assert advertisement_questions.status_code == 200
    assert len(advertisement_questions.get_json()["questions"]) == 19

    questions = client.get("/api/modules/warranty/questions")
    assert questions.status_code == 200
    assert len(questions.get_json()["questions"]) == 13

    next_question = client.post("/api/modules/warranty/question", json={
        "answers": {"product_purchased": True},
        "current_key": "product_purchased",
        "direction": "next",
    })
    assert next_question.status_code == 200
    assert next_question.get_json()["question"]["key"] == "warranty_exists"

    answers = {
        "online_purchase": True,
        "platform_name": "Example Market",
        "order_placed": True,
        "payment_made": True,
        "delivery_received": False,
        "ecommerce_problem_type": "product_not_delivered",
        "seller_contacted": True,
        "seller_response": "No delivery update",
        "issue_resolved": False,
        "order_proof_available": True,
        "payment_proof_available": True,
        "delivery_proof_available": False,
        "communication_available": True,
        "desired_resolution": "Refund",
    }
    analysis = client.post("/api/modules/ecommerce/analyze", json={
        "answers": answers,
        "case_details": {"platform_name": "Example Market"},
    })
    assert analysis.status_code == 200
    payload = analysis.get_json()
    assert payload["facts"]["product_not_received"] is True
    assert payload["rules_fired"] == ["EC1", "EC2", "EC4", "EC6", "EC7"]
    assert payload["reasoning_trace"]
    assert payload["backward_result"]["goal_satisfied"] is True

    service_analysis = client.post("/api/modules/service_deficiency/analyze", json={
        "answers": {
            "service_purchased": True,
            "service_type": "Home cleaning",
            "service_problem_exists": True,
            "problem_description": "Cleaner did not arrive",
            "service_not_provided": True,
            "service_delayed": False,
            "service_inadequate": False,
            "service_not_as_agreed": False,
            "provider_contacted": True,
            "issue_resolved": False,
            "desired_resolution": "Refund",
            "purchase_proof_available": True,
            "service_evidence_available": False,
            "communication_available": True,
        },
    })
    assert service_analysis.status_code == 200
    assert service_analysis.get_json()["rules_fired"] == ["SV1", "SV2", "SV3", "SV4"]
    assert service_analysis.get_json()["reasoning_trace"]

    advertisement_analysis = client.post("/api/modules/unfair_trade_practice/analyze", json={
        "answers": {
            "advertisement_seen": True,
            "claim_made": True,
            "claim_description": "Same-day service guaranteed",
            "actual_experience": "No appointment was provided",
            "claim_false_or_misleading": True,
            "important_information_hidden": False,
            "price_or_discount_claim": False,
            "product_or_service_received": True,
            "business_contacted": True,
            "issue_resolved": False,
            "desired_resolution": "Refund",
            "advertisement_evidence_available": True,
            "purchase_proof_available": True,
            "communication_available": False,
        },
    })
    assert advertisement_analysis.status_code == 200
    assert advertisement_analysis.get_json()["rules_fired"] == ["UT1", "UT3", "UT4", "UT5"]
    assert advertisement_analysis.get_json()["reasoning_trace"]
