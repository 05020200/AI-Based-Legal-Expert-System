import json
import os
from typing import Any, Dict, List

from inference_engine.backward_chaining import BackwardChainingEngine
from inference_engine.forward_chaining import ForwardChainingEngine
from inference_engine.reasoning_trace import ReasoningTrace
from inference_engine.working_memory import WorkingMemory
from services.document_recommendation import DocumentRecommendationService
from services.legal_guidance import LegalGuidanceService


_RULES_PATH = os.path.join(
    os.path.dirname(__file__), "..", "knowledge_base", "defective_product_rules.json"
)
_BOOLEAN_QUESTIONS = [
    {
        "key": "product_purchased",
        "prompt": "Did you purchase the product from a seller or business?",
        "type": "boolean",
    },
    {
        "key": "product_has_problem",
        "prompt": "Does the product have a fault, damage, malfunction, or other problem?",
        "type": "boolean",
    },
    {
        "key": "seller_contacted",
        "prompt": "Have you contacted the seller or business about the problem?",
        "type": "boolean",
    },
    {
        "key": "seller_resolved",
        "prompt": "Did the seller resolve the problem?",
        "type": "boolean",
    },
    {
        "key": "purchase_proof_available",
        "prompt": "Do you have proof of purchase, such as an invoice, bill, or order receipt?",
        "type": "boolean",
    },
    {
        "key": "problem_evidence_available",
        "prompt": "Do you have evidence showing the product problem, such as photographs, videos, or a service report?",
        "type": "boolean",
    },
    {
        "key": "seller_communication_available",
        "prompt": "Do you have communication with the seller, such as emails, messages, or complaint/reference numbers?",
        "type": "boolean",
    },
]
_RESOLUTIONS = ["Repair", "Replacement", "Refund", "Not sure"]
_EVIDENCE_FACTS = {
    "purchase_invoice": "purchase_proof_available",
    "defect_photos": "problem_evidence_available",
    "seller_communication": "seller_communication_available",
}


class DefectiveProductService:
    """Coordinate the Phase 1 questionnaire and existing symbolic inference engines."""

    @staticmethod
    def _load_rules() -> List[Dict[str, Any]]:
        with open(_RULES_PATH, "r", encoding="utf-8") as rules_file:
            return json.load(rules_file)

    @classmethod
    def get_questions(cls) -> List[Dict[str, Any]]:
        rules = cls._load_rules()
        query = BackwardChainingEngine(rules).query(
            "consumer_guidance_required", "true", WorkingMemory()
        )
        relevant_keys = {
            missing.split("=", 1)[0] for missing in query["missing_facts"]
        }

        relevant_questions = [
            question
            for question in _BOOLEAN_QUESTIONS
            if question["key"] in relevant_keys
        ]
        supporting_questions = [
            question
            for question in _BOOLEAN_QUESTIONS
            if question["key"] not in relevant_keys
        ]

        questions = []
        for question in relevant_questions:
            questions.append({
                **question,
                "options": [
                    {"label": "Yes", "value": True},
                    {"label": "No", "value": False},
                ],
            })
        questions.append({
            "key": "desired_resolution",
            "prompt": "What would you like the seller to do?",
            "type": "choice",
            "options": [{"label": value, "value": value} for value in _RESOLUTIONS],
        })
        for question in supporting_questions:
            questions.append({
                **question,
                "options": [
                    {"label": "Yes", "value": True},
                    {"label": "No", "value": False},
                ],
            })
        return questions

    @classmethod
    def analyze(
        cls, answers: Dict[str, Any], case_details: Dict[str, Any]
    ) -> Dict[str, Any]:
        expected_boolean_keys = {question["key"] for question in _BOOLEAN_QUESTIONS}
        if any(type(answers.get(key)) is not bool for key in expected_boolean_keys):
            raise ValueError("Please answer all yes/no questions.")
        desired_resolution = answers.get("desired_resolution")
        if desired_resolution not in _RESOLUTIONS:
            raise ValueError("Choose a valid desired resolution.")

        facts = {key: answers[key] for key in expected_boolean_keys}
        facts["desired_resolution"] = desired_resolution
        memory = WorkingMemory()
        for key, value in facts.items():
            memory.add_fact(key, str(value).lower() if isinstance(value, bool) else value)

        rules = cls._load_rules()
        backward_result = BackwardChainingEngine(rules).query(
            "consumer_guidance_required", "true", memory
        )
        trace = ReasoningTrace()
        inference_result = ForwardChainingEngine(rules).run(memory, trace=trace)
        conclusions = set(inference_result["conclusions"])
        issue_identified = "possible_defective_product_issue" in conclusions

        guidance = LegalGuidanceService().get_guidance(
            ["defective_product_issue"] if issue_identified else []
        )
        provision = guidance[0]["applicable_law"][0] if guidance else None
        available_evidence = [
            identifier
            for identifier, fact_key in _EVIDENCE_FACTS.items()
            if facts[fact_key]
        ]
        documents = DocumentRecommendationService().recommend(
            "Defective Product", available_documents=available_evidence
        )
        evidence_checklist = [
            {
                "name": document["name"],
                "available": facts[_EVIDENCE_FACTS[document["id"]]],
            }
            for document in documents["recommended_documents_display"]
        ]

        details = cls._normalize_case_details(case_details)
        summary = {
            "selected_issue": "Defective Product",
            "product_purchased": facts["product_purchased"],
            "product_has_problem": facts["product_has_problem"],
            "product_name": details.get("product_name"),
            "seller_name": details.get("seller_name"),
            "purchase_date": details.get("purchase_date"),
            "amount_paid": details.get("amount_paid"),
            "order_or_invoice_number": details.get("order_or_invoice_number"),
            "problem_situation": details.get("problem_description"),
            "seller_contacted": facts["seller_contacted"],
            "seller_response_resolution": {
                "problem_resolved": facts["seller_resolved"],
                "response_details": details.get("seller_response"),
            },
            "desired_resolution": desired_resolution,
            "evidence_availability": {
                item["name"]: item["available"] for item in evidence_checklist
            },
        }

        if issue_identified:
            assessment = (
                "Based on the information provided, this may indicate a consumer issue involving a defective product."
            )
            why_relevant = (
                "You reported purchasing a product from a seller or business and that the product has a problem. "
                "Those facts may be relevant to whether the goods have a defect; this report does not decide that question."
            )
            possible_options = [
                "You may ask the seller about repair, replacement, or refund, depending on the circumstances and applicable law.",
                f"Your stated preference is: {desired_resolution}.",
            ]
        else:
            assessment = (
                "The answers provided do not currently establish the Phase 1 conditions for a possible defective-product issue. "
                "This is not a final legal determination."
            )
            why_relevant = (
                "The rule-based assessment looks for both a product purchase from a seller or business and a reported product problem."
            )
            possible_options = [
                f"Your stated preference is: {desired_resolution}.",
            ]

        next_steps = [
            "Keep the purchase receipt, clear photographs or videos of the problem, and copies of relevant seller communications.",
        ]
        if not facts["seller_contacted"]:
            next_steps.insert(
                0,
                "Consider contacting the seller in writing, describing the problem and the resolution you prefer; keep a copy of the message.",
            )
        elif not facts["seller_resolved"]:
            next_steps.insert(
                0,
                "Keep a dated record of your contact with the seller and any response.",
            )
        next_steps.extend([
            "For grievance assistance, contact the National Consumer Helpline at 1915 or use its official portal: https://consumerhelpline.gov.in/.",
            "Section 35 of the Consumer Protection Act, 2019 provides for making a complaint before the District Commission. Check current filing instructions and the applicable forum through official consumer-affairs sources before filing.",
        ])

        report = {
            "title": "Defective Product Legal Guidance Report",
            "assessment": assessment,
            "why_relevant": why_relevant,
            "legal_provision": {
                "act_name": provision.get("act_name"),
                "section_number": provision.get("section_number"),
                "title": provision.get("title"),
                "description": provision.get("plain_language_description"),
                "source_url": provision.get("source_url"),
            } if provision else None,
            "possible_options": possible_options,
            "evidence_checklist": evidence_checklist,
            "next_steps": next_steps,
            "case_summary": summary,
            "disclaimer": (
                "This is preliminary legal information for educational purposes, not legal advice. "
                "It is not a final determination of your rights or the merits of a complaint."
            ),
        }

        missing_question_keys = {
            missing.split("=", 1)[0]
            for missing in backward_result["missing_facts"]
            if not memory.has_fact(missing.split("=", 1)[0])
        }
        return {
            "facts": facts,
            "case_details": details,
            "report": report,
            "internal": {
                "conclusions": inference_result["conclusions"],
                "reasoning_trace": trace.get_steps(),
                "backward_result": backward_result,
                "missing_question_keys": sorted(missing_question_keys),
            },
        }

    @staticmethod
    def _normalize_case_details(case_details: Dict[str, Any]) -> Dict[str, Any]:
        allowed_text = {
            "product_name",
            "seller_name",
            "purchase_date",
            "order_or_invoice_number",
            "problem_description",
            "seller_response",
        }
        normalized = {
            key: str(case_details.get(key, "")).strip()
            for key in allowed_text
            if case_details.get(key) not in (None, "")
        }
        amount = case_details.get("amount_paid")
        if amount not in (None, ""):
            try:
                normalized_amount = float(amount)
            except (TypeError, ValueError) as error:
                raise ValueError("Amount paid must be a non-negative number.") from error
            if normalized_amount < 0:
                raise ValueError("Amount paid must be a non-negative number.")
            normalized["amount_paid"] = normalized_amount
        return normalized