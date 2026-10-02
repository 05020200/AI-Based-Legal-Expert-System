import json
import os
from copy import deepcopy
from typing import Any, Dict, List

from inference_engine.backward_chaining import BackwardChainingEngine
from inference_engine.forward_chaining import ForwardChainingEngine
from inference_engine.reasoning_trace import ReasoningTrace
from inference_engine.working_memory import WorkingMemory
from services.defective_product import DefectiveProductService
from services.legal_guidance import LegalGuidanceService


_MODULES_PATH = os.path.join(
    os.path.dirname(__file__), "..", "knowledge_base", "consumer_issue_modules.json"
)
_DISCLAIMER = (
    "This system provides preliminary legal information based on the facts and legal knowledge configured in the system. "
    "It is not a substitute for advice from a qualified legal professional. Legal outcomes depend on the specific facts, "
    "evidence, applicable law, and decisions of the competent authority."
)


class ConsumerModuleService:
    """Run the configured refund, warranty, and e-commerce modules."""

    @staticmethod
    def _definitions() -> Dict[str, Dict[str, Any]]:
        with open(_MODULES_PATH, "r", encoding="utf-8") as source:
            return json.load(source)

    @classmethod
    def get_module(cls, module_id: str) -> Dict[str, Any]:
        definition = cls._definitions().get(module_id)
        if definition is None:
            raise ValueError("This consumer module is not available yet.")
        return deepcopy(definition)

    @classmethod
    def available_module_ids(cls) -> set[str]:
        return set(cls._definitions())

    @classmethod
    def answer_keys(cls, module_id: str) -> set[str]:
        return {question["key"] for question in cls.get_module(module_id)["questions"]}

    @classmethod
    def get_questions(cls, module_id: str) -> List[Dict[str, Any]]:
        definition = cls.get_module(module_id)
        questions = []
        for original in definition["questions"]:
            question = deepcopy(original)
            if question["type"] == "boolean":
                question["options"] = [
                    {"label": "Yes", "value": True},
                    {"label": "No", "value": False},
                ]
            elif question["type"] == "choice":
                question["options"] = [
                    option if isinstance(option, dict) else {"label": option, "value": option}
                    for option in question.get("options", [])
                ]
            questions.append(question)
        return questions

    @staticmethod
    def _condition_matches(answers: Dict[str, Any], condition: Dict[str, Any]) -> bool:
        actual = answers.get(condition["fact_key"])
        expected = condition.get("equals")
        if expected == "true":
            return actual is True
        if expected == "false":
            return actual is False
        return actual == expected

    @classmethod
    def get_visible_questions(cls, module_id: str, answers: Dict[str, Any]) -> List[Dict[str, Any]]:
        visible = []
        visible_keys = set()
        for question in cls.get_questions(module_id):
            conditions = question.get("visible_when", [])
            if all(
                condition["fact_key"] in visible_keys
                and cls._condition_matches(answers, condition)
                for condition in conditions
            ):
                visible.append(question)
                visible_keys.add(question["key"])
        return visible

    @classmethod
    def get_next_question(
        cls,
        module_id: str,
        answers: Dict[str, Any],
        current_key: str = None,
        direction: str = "next",
    ) -> Dict[str, Any]:
        if direction not in {"current", "next", "previous"}:
            raise ValueError("Direction must be 'current', 'next', or 'previous'.")
        questions = cls.get_visible_questions(module_id, answers)
        keys = [question["key"] for question in questions]
        if current_key not in keys:
            index = 0
        else:
            index = keys.index(current_key)
            if direction == "previous":
                index = max(0, index - 1)
            elif direction == "next":
                index += 1
        question = questions[index] if index < len(questions) else None
        return {
            "question": question,
            "step": index + 1 if question else len(questions),
            "total": len(questions),
            "visible_keys": keys,
        }

    @classmethod
    def analyze(
        cls,
        module_id: str,
        answers: Dict[str, Any],
        case_details: Dict[str, Any],
    ) -> Dict[str, Any]:
        definition = cls.get_module(module_id)
        questions = cls.get_questions(module_id)
        questions_by_key = {question["key"]: question for question in questions}
        allowed_keys = set(questions_by_key)
        if set(answers) - allowed_keys:
            raise ValueError("An unsupported questionnaire answer was provided.")
        if not isinstance(case_details, dict):
            raise ValueError("Case details must be an object.")

        visible = cls.get_visible_questions(module_id, answers)
        visible_keys = {question["key"] for question in visible}
        for question in visible:
            key = question["key"]
            if question.get("required") and key not in answers:
                raise ValueError(f"Please answer: {question['prompt']}")
            if key not in answers:
                continue
            value = answers[key]
            if question["type"] == "boolean" and type(value) is not bool:
                raise ValueError(f"Please answer: {question['prompt']}")
            if question["type"] == "choice" and value not in {
                option["value"] for option in question["options"]
            }:
                raise ValueError(f"Choose a valid answer for: {question['prompt']}")
            if question["type"] == "text" and not isinstance(value, str):
                raise ValueError(f"Enter text for: {question['prompt']}")
        if set(answers) - visible_keys:
            raise ValueError("Remove answers to questions that are no longer relevant.")

        facts = dict(answers)
        for answer_key, choices in definition.get("choice_derivations", {}).items():
            selected_derivations = choices.get(answers.get(answer_key), {})
            facts.update(selected_derivations)

        memory = WorkingMemory()
        for key, value in facts.items():
            memory.add_fact(key, str(value).lower() if isinstance(value, bool) else value)

        rules = deepcopy(definition["rules"])
        for rule in rules:
            for condition in rule.get("conditions", []):
                condition.setdefault("operator", "==")
        trace = ReasoningTrace()
        forward_result = ForwardChainingEngine(rules).run(memory, trace=trace)
        backward_result = BackwardChainingEngine(rules).query(
            definition["unresolved_conclusion"], "true", memory
        )
        conclusions = set(forward_result["conclusions"])
        issue_identified = definition["issue_conclusion"] in conclusions
        unresolved = definition["unresolved_conclusion"] in conclusions
        resolved = facts.get(definition["resolved_fact"]) is True

        guidance_entries = LegalGuidanceService().get_guidance(forward_result["conclusions"])
        provisions = []
        seen_provisions = set()
        for entry in guidance_entries:
            for provision in entry.get("applicable_law", []):
                identity = (provision.get("act_name"), provision.get("section_number"))
                if identity not in seen_provisions:
                    seen_provisions.add(identity)
                    provisions.append(provision)
        complaint_provision = next(
            (item for item in provisions if item.get("section_number") == "Section 35"),
            None,
        )

        details = {
            key: str(case_details[key]).strip()
            for key in (
                "product_name", "seller_name", "seller_address", "purchase_date",
                "amount_paid", "order_or_invoice_number", "problem_description",
                "seller_response", "platform_name",
            )
            if case_details.get(key) not in (None, "")
        }
        summary = {
            "selected_issue": definition["name"],
            "product_name": details.get("product_name"),
            "platform_name": details.get("platform_name") or answers.get("platform_name"),
            "seller_name": details.get("seller_name"),
            "purchase_date": details.get("purchase_date"),
            "amount_paid": details.get("amount_paid"),
            "order_or_invoice_number": details.get("order_or_invoice_number"),
            "problem_situation": details.get("problem_description") or answers.get("reason_for_request") or answers.get("ecommerce_problem_type"),
            "seller_contacted": answers.get("seller_contacted", answers.get("seller_or_service_contacted")),
            "seller_response_resolution": {
                "problem_resolved": facts.get(definition["resolved_fact"]),
                "response_details": details.get("seller_response") or answers.get("seller_response") or answers.get("warranty_refusal_reason"),
            },
            "desired_resolution": answers.get("desired_resolution"),
            "evidence_availability": {
                evidence["name"]: facts.get(evidence["fact_key"])
                for evidence in definition["evidence"]
            },
            "issue_details": {
                question["prompt"].rstrip("?"): answers[question["key"]]
                for question in questions
                if question["key"] in answers and question["type"] != "text"
            },
        }

        if module_id == "refund_replacement":
            available_evidence = [
                evidence["name"]
                for evidence in definition["evidence"]
                if facts.get(evidence["fact_key"]) is True
            ]
            summary = {
                "selected_issue": definition["name"],
                "situation_text": cls._refund_replacement_situation(answers, details),
                "product_name": details.get("product_name"),
                "seller_name": details.get("seller_name"),
                "purchase_date": details.get("purchase_date"),
                "amount_paid": details.get("amount_paid"),
                "order_or_invoice_number": details.get("order_or_invoice_number"),
                "product_or_service_purchased": answers.get("product_or_service_purchased"),
                "refund_or_replacement_requested": answers.get("refund_or_replacement_requested"),
                "reason_for_request": answers.get("reason_for_request"),
                "product_has_problem": answers.get("product_has_problem"),
                "seller_contacted": answers.get("seller_contacted"),
                "seller_agreed": answers.get("seller_agreed"),
                "refund_or_replacement_provided": answers.get("refund_or_replacement_provided"),
                "seller_response": answers.get("seller_response") or details.get("seller_response"),
                "desired_resolution": answers.get("desired_resolution"),
                "evidence_availability": {
                    evidence["name"]: facts.get(evidence["fact_key"])
                    for evidence in definition["evidence"]
                },
            }
        elif module_id == "warranty":
            available_evidence_names = {
                evidence["name"]
                for evidence in definition["evidence"]
                if facts.get(evidence["fact_key"]) is True
            }
            summary = {
                "selected_issue": definition["name"],
                "situation_text": cls._warranty_situation(answers, details),
                "product_name": details.get("product_name"),
                "seller_name": details.get("seller_name"),
                "seller_address": details.get("seller_address"),
                "purchase_date": details.get("purchase_date"),
                "amount_paid": details.get("amount_paid"),
                "order_or_invoice_number": details.get("order_or_invoice_number"),
                "problem_description": details.get("problem_description"),
                "seller_response": None if answers.get("warranty_refusal_reason") else details.get("seller_response"),
                "product_purchased": answers.get("product_purchased"),
                "warranty_exists": answers.get("warranty_exists"),
                "product_problem_exists": answers.get("product_problem_exists"),
                "warranty_service_requested": answers.get("warranty_service_requested"),
                "seller_or_service_contacted": answers.get("seller_or_service_contacted"),
                "warranty_service_provided": answers.get("warranty_service_provided"),
                "warranty_service_refused": answers.get("warranty_service_refused"),
                "warranty_refusal_reason": answers.get("warranty_refusal_reason"),
                "desired_resolution": answers.get("desired_resolution"),
            }
        elif module_id == "ecommerce":
            available_evidence_names = {
                evidence["name"]
                for evidence in definition["evidence"]
                if facts.get(evidence["fact_key"]) is True
            }
            summary = {
                "selected_issue": definition["name"],
                "situation_text": cls._ecommerce_situation(answers, details),
                "platform_name": answers.get("platform_name") or details.get("platform_name"),
                "product_name": details.get("product_name"),
                "seller_name": details.get("seller_name"),
                "seller_address": details.get("seller_address"),
                "purchase_date": details.get("purchase_date"),
                "amount_paid": details.get("amount_paid"),
                "order_or_invoice_number": details.get("order_or_invoice_number"),
                "problem_description": details.get("problem_description"),
                "online_purchase": answers.get("online_purchase"),
                "order_placed": answers.get("order_placed"),
                "payment_made": answers.get("payment_made"),
                "delivery_received": answers.get("delivery_received"),
                "ecommerce_problem_type": answers.get("ecommerce_problem_type"),
                "seller_contacted": answers.get("seller_contacted"),
                "seller_response": answers.get("seller_response") or details.get("seller_response"),
                "issue_resolved": answers.get("issue_resolved"),
                "desired_resolution": answers.get("desired_resolution"),
            }
        elif module_id in {"service_deficiency", "unfair_trade_practice"}:
            available_evidence_names = {
                evidence["name"]
                for evidence in definition["evidence"]
                if facts.get(evidence["fact_key"]) is True
            }
            situation_builder = (
                cls._service_situation
                if module_id == "service_deficiency"
                else cls._advertisement_situation
            )
            summary = {
                "selected_issue": definition["name"],
                "situation_text": situation_builder(answers),
                "seller_address": details.get("seller_address"),
                "order_or_invoice_number": details.get("order_or_invoice_number"),
                "platform_name": details.get("platform_name"),
                "purchase_date": details.get("purchase_date"),
                "amount_paid": details.get("amount_paid"),
                "product_name": details.get("product_name"),
                **{
                    question["key"]: answers[question["key"]]
                    for question in questions
                    if question["key"] in answers
                },
            }

        if issue_identified and resolved:
            assessment = "You reported that the issue has been resolved. This report does not determine whether any further action is appropriate."
        elif issue_identified and unresolved:
            assessment = f"Based on the information provided, this may indicate an unresolved {definition['name'].lower()}."
        elif issue_identified:
            assessment = f"Based on the information provided, this may indicate a {definition['name'].lower()}. The answers do not establish that a request was refused or remains unresolved."
        else:
            assessment = f"The answers provided do not currently establish the configured conditions for a {definition['name'].lower()}. This is not a final legal determination."

        if module_id == "refund_replacement" and issue_identified and unresolved:
            requested_resolution = (answers.get("desired_resolution") or "refund or replacement").lower()
            if answers.get("seller_agreed") is False:
                assessment = (
                    "Based on the information provided, this may indicate an unresolved consumer dispute "
                    f"involving the product supplied and the refused {requested_resolution} request."
                )
            else:
                assessment = (
                    "Based on the information provided, this may indicate an unresolved consumer dispute "
                    f"involving the product supplied and the requested {requested_resolution}."
                )

        if module_id == "warranty" and issue_identified:
            if resolved:
                assessment = (
                    "You reported that the requested warranty service was provided. "
                    "This report does not determine warranty coverage or whether further action is appropriate."
                )
            elif unresolved:
                assessment = (
                    "Based on the information provided, this may indicate an unresolved warranty-service request."
                )
            else:
                assessment = (
                    "Based on the information provided, this may indicate a warranty-related product issue; "
                    "the answers do not establish that a service request remains unresolved."
                )

        if module_id == "ecommerce" and issue_identified:
            problem = cls._ecommerce_problem_label(answers.get("ecommerce_problem_type"))
            if resolved:
                assessment = (
                    f"You reported that the online-order issue ({problem}) was resolved. "
                    "This report does not determine liability or whether the resolution was adequate."
                )
            elif unresolved:
                assessment = (
                    "Based on the information provided, this may indicate an unresolved online-order issue "
                    f"involving {problem}."
                )
            else:
                assessment = (
                    "Based on the information provided, this may indicate an online-order issue involving "
                    f"{problem}; the answers do not establish that it remains unresolved."
                )

        if module_id == "service_deficiency":
            if issue_identified and resolved:
                assessment = (
                    "You reported that the service issue was resolved. This preliminary report does not determine "
                    "whether the service legally amounted to a deficiency."
                )
            elif issue_identified and unresolved:
                assessment = (
                    "Based on the information provided, this may indicate an unresolved consumer issue "
                    "concerning the reported service performance."
                )
            elif issue_identified:
                assessment = (
                    "Based on the information provided, this may indicate a possible deficiency in the purchased service."
                )
            else:
                assessment = (
                    "The answers do not establish both a purchased service and a reported service problem."
                )

        if module_id == "unfair_trade_practice":
            if issue_identified and resolved:
                assessment = (
                    "You reported that the advertisement issue was resolved. This does not determine whether the claim "
                    "legally amounted to an unfair trade practice."
                )
            elif issue_identified and unresolved:
                assessment = (
                    "Based on the information provided, this may raise a consumer issue concerning a potentially "
                    "misleading advertisement or unfair trade practice."
                )
            elif issue_identified:
                assessment = (
                    "Based on the information provided, this may raise a consumer issue concerning the reported advertisement claim."
                )
            else:
                assessment = (
                    "The answers do not establish a specific false or misleading claim or important omitted information."
                )

        if resolved:
            possible_options = definition["resolved_options"]
            next_steps = definition["resolved_next_steps"]
        elif unresolved:
            possible_options = definition["unresolved_options"]
            next_steps = definition["unresolved_next_steps"]
        else:
            possible_options = definition["general_options"]
            next_steps = definition["general_next_steps"]

        if module_id == "refund_replacement":
            if resolved:
                possible_options = definition["resolved_options"]
                next_steps = definition["resolved_next_steps"]
            elif unresolved:
                requested_resolution = (answers.get("desired_resolution") or "refund or replacement").lower()
                possible_options = [
                    f"You may continue to seek the requested {requested_resolution}, subject to the facts and applicable terms."
                ]
                next_steps = cls._refund_replacement_next_steps(answers)
            else:
                possible_options = definition["general_options"]
                next_steps = definition["general_next_steps"]

        if module_id == "warranty":
            if resolved:
                possible_options = [
                    "You reported that the requested warranty service was provided; keep its confirmation and service records."
                ]
                next_steps = [
                    "Keep the warranty terms, service records, and confirmation showing what service was provided."
                ]
            elif unresolved:
                resolution = (answers.get("desired_resolution") or "warranty service").lower()
                possible_options = [
                    f"You may ask the seller or service centre to provide the requested {resolution} under the warranty terms; this report does not establish that the reported problem is covered."
                ]
                next_steps = cls._warranty_next_steps(answers)

        if module_id == "ecommerce":
            if resolved:
                possible_options = [
                    "You reported that the online-order issue was resolved; keep the resolution confirmation."
                ]
                next_steps = [
                    "Keep the order, payment, delivery or return records, and confirmation of the resolution."
                ]
            elif answers.get("issue_resolved") is False:
                resolution = (answers.get("desired_resolution") or "a resolution").lower()
                problem = cls._ecommerce_problem_label(answers.get("ecommerce_problem_type"))
                possible_options = [
                    f"You may pursue the requested {resolution} for {problem} through the seller or platform's recorded process, subject to the order terms."
                ]
                next_steps = cls._ecommerce_next_steps(answers)
            elif issue_identified:
                resolution = (answers.get("desired_resolution") or "a resolution").lower()
                problem = cls._ecommerce_problem_label(answers.get("ecommerce_problem_type"))
                possible_options = [
                    f"Contact the seller or platform through its recorded process to seek the requested {resolution} for {problem}."
                ]
                next_steps = cls._ecommerce_next_steps(answers)

        if module_id == "service_deficiency" and issue_identified:
            if resolved:
                possible_options = [
                    "You reported that the service issue was resolved; retain the confirmation and related records."
                ]
                next_steps = cls._service_next_steps(answers, resolved=True)
            elif unresolved:
                resolution = (answers.get("desired_resolution") or "an appropriate resolution").lower()
                possible_options = [
                    f"You may pursue the requested {resolution}, subject to the service terms and circumstances."
                ]
                next_steps = cls._service_next_steps(answers)
            else:
                possible_options = [
                    "Consider contacting the provider in writing to request the stated outcome and keep a copy."
                ]
                next_steps = cls._service_next_steps(answers, contact_first=True)

        if module_id == "unfair_trade_practice" and issue_identified:
            if resolved:
                possible_options = [
                    "You reported that the business resolved the issue; retain the correction, refund, or other resolution confirmation."
                ]
                next_steps = cls._advertisement_next_steps(answers, resolved=True)
            elif unresolved:
                resolution = (answers.get("desired_resolution") or "an appropriate resolution").lower()
                possible_options = [
                    f"You may ask the business to consider the requested {resolution}, depending on the facts and applicable terms."
                ]
                next_steps = cls._advertisement_next_steps(answers)
            else:
                possible_options = [
                    "Consider asking the business to clarify or correct the claim; this report does not determine that it was legally misleading."
                ]
                next_steps = cls._advertisement_next_steps(answers, contact_first=True)

        details_for_explanation = details.get("problem_description") or summary.get("problem_situation")
        why_relevant = definition["why_relevant"]
        if details_for_explanation:
            why_relevant += f" Additional details supplied: {details_for_explanation}."
        platform = summary.get("platform_name")
        if platform:
            why_relevant += f" Platform named: {platform}."

        if module_id == "refund_replacement":
            reason = answers.get("reason_for_request", "product issue").lower()
            requested_resolution = (answers.get("desired_resolution") or "refund or replacement").lower()
            refusal = " and the seller's refusal" if answers.get("seller_agreed") is False else ""
            why_relevant = (
                f"The reported {reason}{refusal} of the requested {requested_resolution} "
                "may be relevant to consumer protections under the Consumer Protection Act, 2019."
            )

        if module_id == "warranty":
            refusal = answers.get("warranty_refusal_reason")
            if refusal:
                why_relevant = (
                    f"You reported that warranty service was refused ({refusal}). Sections 2(9) and 2(8) "
                    "may be relevant to consumer rights and the dispute; Section 35 describes a complaint route. "
                    "Coverage depends on the warranty terms."
                )
            elif unresolved:
                why_relevant = (
                    "You reported a product problem and requested warranty service that was not provided. "
                    "Section 2(9) may be relevant to consumer rights, and Section 35 describes a complaint route. "
                    "Coverage depends on the warranty terms."
                )
            else:
                why_relevant = (
                    "You reported that warranty service was provided. Section 2(9) may be relevant to consumer rights, "
                    "but this report does not determine warranty coverage."
                )
            if resolved:
                why_relevant = (
                    "You reported that warranty service was provided. Section 2(9) may be relevant to consumer rights, "
                    "but this report does not determine warranty coverage."
                )

        if module_id == "ecommerce":
            problem = cls._ecommerce_problem_label(answers.get("ecommerce_problem_type"))
            platform = answers.get("platform_name")
            platform_phrase = f" through {platform}" if platform else ""
            why_relevant = (
                f"You reported an online order{platform_phrase} and {problem}. Section 2(16) of the Consumer Protection Act, 2019 "
                "concerns e-commerce; the facts supplied do not determine responsibility."
            )
            if "potential_consumer_dispute" in conclusions or (
                answers.get("seller_contacted") is True
                and answers.get("issue_resolved") is False
            ):
                why_relevant += " Section 2(8) concerns consumer disputes."
            if unresolved:
                why_relevant += " Section 35 describes a consumer complaint route."

        if module_id == "service_deficiency" and issue_identified:
            reported_problems = [
                label for key, label in (
                    ("service_not_provided", "not provided"),
                    ("service_delayed", "delayed"),
                    ("service_inadequate", "inadequate or incomplete"),
                    ("service_not_as_agreed", "not as agreed"),
                ) if answers.get(key) is True
            ]
            problem_text = ", ".join(reported_problems) or answers.get("problem_description", "")
            why_relevant = (
                f"You reported that the service was {problem_text}. Section 2(11) addresses a fault, shortcoming, "
                "or inadequacy in service performance required by law, contract, or otherwise; applying it depends on the facts."
            )

        if module_id == "unfair_trade_practice" and issue_identified:
            why_relevant = (
                "You reported a specific advertisement claim and that it was false or misleading, or that important information was hidden. "
                "Section 2(47) addresses unfair or deceptive trade practices; this report does not determine whether the legal test is met."
            )
            if answers.get("claim_description"):
                why_relevant = (
                    f"You reported the claim '{answers['claim_description']}' and that it was false or misleading, "
                    "or that important information was hidden. Section 2(47) addresses unfair or deceptive trade practices; "
                    "this report does not determine whether the legal test is met."
                )

        if unresolved:
            amount_for_jurisdiction = details.get("amount_paid")
            if module_id == "service_deficiency":
                amount_for_jurisdiction = answers.get("amount_paid") or amount_for_jurisdiction
            complaint_information = DefectiveProductService._complaint_information(
                amount_for_jurisdiction, complaint_provision
            )
        else:
            complaint_information = None

        evidence_checklist = [
            {"name": evidence["name"], "available": facts.get(evidence["fact_key"])}
            for evidence in definition["evidence"]
        ]
        legal_provisions = provisions
        recommended_evidence = definition["recommended_evidence"]
        if module_id == "refund_replacement":
            relevant_sections = {"Section 2(9)"}
            if answers.get("seller_agreed") is False:
                relevant_sections.add("Section 2(8)")
            if unresolved:
                relevant_sections.add("Section 35")
            legal_provisions = [
                provision for provision in provisions
                if provision.get("section_number") in relevant_sections
            ]
            legal_provisions = [
                {
                    **provision,
                    "description": provision.get("description")
                    or provision.get("plain_language_description"),
                }
                for provision in legal_provisions
            ]
            recommended_evidence = [
                name for name in definition["recommended_evidence"]
                if name not in available_evidence
            ]
        elif module_id in {"warranty", "ecommerce"}:
            relevant_sections = (
                {"Section 2(9)"}
                if module_id == "warranty"
                else {"Section 2(16)"}
            )
            if "potential_consumer_dispute" in conclusions or (
                module_id == "ecommerce"
                and answers.get("seller_contacted") is True
                and answers.get("issue_resolved") is False
            ):
                relevant_sections.add("Section 2(8)")
            if unresolved:
                relevant_sections.add("Section 35")
            if "Section 2(8)" in relevant_sections and not any(
                provision.get("section_number") == "Section 2(8)"
                for provision in provisions
            ):
                section_28 = LegalGuidanceService().get_provision_by_section("Section 2(8)")
                if section_28:
                    provisions.append(section_28)
            legal_provisions = [
                {
                    **provision,
                    "description": provision.get("description")
                    or provision.get("plain_language_description"),
                }
                for provision in provisions
                if provision.get("section_number") in relevant_sections
            ]
            recommended_evidence = [
                name for name in definition["recommended_evidence"]
                if name not in available_evidence_names
            ]
        elif module_id in {"service_deficiency", "unfair_trade_practice"}:
            relevant_section = "Section 2(11)" if module_id == "service_deficiency" else "Section 2(47)"
            relevant_sections = {relevant_section}
            if unresolved:
                relevant_sections.add("Section 35")
            legal_provisions = [
                {
                    **provision,
                    "description": provision.get("description")
                    or provision.get("plain_language_description"),
                }
                for provision in provisions
                if provision.get("section_number") in relevant_sections
            ] if issue_identified else []
            if unresolved and not any(
                provision.get("section_number") == "Section 35"
                for provision in legal_provisions
            ):
                section_35 = LegalGuidanceService().get_provision_by_section("Section 35")
                if section_35:
                    legal_provisions.append({
                        **section_35,
                        "description": section_35.get("plain_language_description"),
                    })
            available_for_filter = set(available_evidence_names)
            if module_id == "unfair_trade_practice" and "Advertisement Screenshot / Video / Image" in available_for_filter:
                available_for_filter.update({"Advertisement Screenshot", "Advertisement Video / Image"})
            recommended_evidence = [
                name for name in definition["recommended_evidence"]
                if name not in available_for_filter
            ]
        report = {
            "title": f"{definition['name']} Legal Guidance Report",
            "your_situation": summary,
            "assessment": assessment,
            "possible_issue": assessment,
            "why_relevant": why_relevant,
            "legal_provisions": legal_provisions,
            "legal_provision": next(
                (item for item in legal_provisions if item.get("section_number") != "Section 35"),
                None,
            ),
            "possible_options": list(possible_options),
            "evidence_checklist": evidence_checklist,
            "recommended_evidence": recommended_evidence,
            "documents": definition["documents"],
            "next_steps": list(next_steps),
            "where_to_complain": complaint_information,
            "case_summary": summary,
            "disclaimer": _DISCLAIMER,
        }
        final_facts = memory.get_all_facts()
        return {
            "facts": facts,
            "derived_facts": forward_result["derived_facts"],
            "working_memory": final_facts,
            "reasoning_trace": trace.get_steps(),
            "rules_fired": forward_result["fired_rules"],
            "backward_result": backward_result,
            "report": report,
        }

    @staticmethod
    def _refund_replacement_situation(answers: Dict[str, Any], details: Dict[str, Any]) -> str:
        product_name = details.get("product_name")
        if product_name:
            article = "an" if product_name[0].lower() in "aeiou" else "a"
            purchase = f"You purchased {article} {product_name}"
        else:
            purchase = "You made a purchase"
        if details.get("seller_name"):
            purchase += f" from {details['seller_name']}"

        reason_phrases = {
            "Wrong product received": "receiving the wrong product",
            "Product defective": "receiving a defective product",
            "Product damaged": "receiving a damaged product",
            "Product not as described": "the product not matching its description",
            "Product incomplete": "receiving an incomplete product",
            "Product/service issue": "a product or service issue",
        }
        reason = answers.get("reason_for_request")
        if reason:
            purchase += f" and reported {reason_phrases.get(reason, reason.lower())}"
        situation = purchase + "."

        if answers.get("seller_contacted") is True:
            resolution = (answers.get("desired_resolution") or "refund or replacement").lower()
            if answers.get("seller_agreed") is False:
                situation += f" You contacted the seller and requested a {resolution}, but the seller refused the {resolution}."
            elif answers.get("seller_agreed") is True and answers.get("refund_or_replacement_provided") is False:
                situation += f" You contacted the seller, who agreed to the {resolution}, but it has not been provided."
            else:
                situation += f" You contacted the seller about your requested {resolution}."
        elif answers.get("refund_or_replacement_requested") is True:
            resolution = (answers.get("desired_resolution") or "refund or replacement").lower()
            situation += f" You requested a {resolution}."
        return situation

    @staticmethod
    def _refund_replacement_next_steps(answers: Dict[str, Any]) -> List[str]:
        steps = []
        if answers.get("purchase_proof_available") is True:
            steps.append("Keep your invoice or order proof.")
        else:
            steps.append("Locate any invoice, order confirmation, or other purchase proof.")
        if answers.get("problem_evidence_available") is True:
            steps.append("Keep photographs or other evidence showing the product received.")
        else:
            steps.append("Photograph the product and packaging, if still available.")
        if answers.get("seller_communication_available") is True:
            steps.append("Keep the seller's refusal and related communications.")
        elif answers.get("seller_contacted") is True:
            steps.append("Keep a record of your contact and ask the seller to confirm its response in writing.")
        requested_resolution = (answers.get("desired_resolution") or "refund or replacement").lower()
        steps.append(
            f"If appropriate, send a dated written request restating your {requested_resolution} request and keep a copy."
        )
        steps.append(
            "If unresolved, consider contacting the National Consumer Helpline (1915) or reviewing the applicable Consumer Commission procedure."
        )
        return steps

    @staticmethod
    def _warranty_situation(answers: Dict[str, Any], details: Dict[str, Any]) -> str:
        product = details.get("product_name") or "product"
        situation = f"You reported a purchase of {product}"
        if answers.get("warranty_exists") is True:
            situation += " with a warranty"
        if answers.get("product_problem_exists") is True:
            situation += " and reported a product problem"
        situation += "."

        if answers.get("warranty_service_requested") is True:
            resolution = (answers.get("desired_resolution") or "warranty service").lower()
            provider = details.get("seller_name") or "the seller or service centre"
            if answers.get("seller_or_service_contacted") is True:
                situation += f" You requested {resolution} service from {provider}."
            else:
                situation += f" You requested {resolution} service but did not report contacting {provider}."
            if answers.get("warranty_service_provided") is True:
                situation += " The service was provided."
            elif answers.get("warranty_service_refused") is True:
                situation += " The service was refused or left incomplete."
            else:
                situation += " The service has not been provided."
            if answers.get("warranty_refusal_reason"):
                situation += f" The stated reason was: {answers['warranty_refusal_reason']}."
        return situation

    @staticmethod
    def _ecommerce_problem_label(problem_type: str) -> str:
        return {
            "product_not_delivered": "non-delivery",
            "wrong_product": "wrong product received",
            "damaged_product": "damaged product",
            "defective_product": "defective product",
            "incomplete_order": "incomplete order",
            "product_not_as_described": "product not as described",
            "refund_not_received": "pending refund",
            "replacement_not_provided": "replacement not provided",
            "cancellation_issue": "cancellation issue",
            "other": "another order issue",
        }.get(problem_type, "order issue")

    @classmethod
    def _ecommerce_situation(cls, answers: Dict[str, Any], details: Dict[str, Any]) -> str:
        platform = answers.get("platform_name") or details.get("platform_name")
        situation = (
            "You placed an online order"
            if answers.get("order_placed") is True
            else "You reported an online purchase but no order was placed"
        )
        if platform:
            situation += f" through {platform}"
        situation += "."

        if answers.get("payment_made") is True:
            situation += " You paid for the order."
        elif answers.get("payment_made") is False:
            situation += " You reported that payment was not made."

        problem_type = answers.get("ecommerce_problem_type")
        problem = cls._ecommerce_problem_label(problem_type)
        situation += f" The reported issue was {problem}."
        if answers.get("delivery_received") is not None and problem_type != "product_not_delivered":
            delivery = "was delivered" if answers["delivery_received"] else "was not delivered"
            situation += f" The order {delivery}."

        if answers.get("seller_contacted") is True:
            if answers.get("issue_resolved") is True:
                situation += " You reported that the issue was resolved."
            elif answers.get("issue_resolved") is False:
                situation += " The issue remains unresolved after contacting the seller or platform."
        elif "seller_contacted" in answers:
            situation += " You have not reported contacting the seller or platform."

        resolution = answers.get("desired_resolution")
        if resolution and resolution != "Not sure":
            situation += f" Your preferred resolution is {resolution.lower()}."
        return situation

    @staticmethod
    def _warranty_next_steps(answers: Dict[str, Any]) -> List[str]:
        steps = [
            "Keep the warranty terms and purchase proof together."
            if answers.get("warranty_document_available") is True
            and answers.get("purchase_proof_available") is True
            else "Locate the warranty terms and purchase proof for the product."
        ]
        if answers.get("service_record_available") is True:
            steps.append("Keep the service records and job sheets.")
        else:
            steps.append("Ask for a service job sheet or reference number and keep it.")
        if answers.get("communication_available") is True:
            steps.append("Keep the seller or service-centre communications, including the refusal.")
        elif answers.get("seller_or_service_contacted") is True:
            steps.append("Ask the seller or service centre to explain its response in writing.")
        steps.append(
            "If the request remains unresolved, consider the National Consumer Helpline (1915) or the applicable Consumer Commission procedure."
        )
        return steps

    @classmethod
    def _ecommerce_next_steps(cls, answers: Dict[str, Any]) -> List[str]:
        steps = [
            "Keep the order confirmation or order details."
            if answers.get("order_proof_available") is True
            else "Save the order confirmation or order details."
        ]
        if answers.get("payment_made") is True:
            steps.append(
                "Keep the payment record."
                if answers.get("payment_proof_available") is True
                else "Locate the payment record."
            )
        if answers.get("delivery_proof_available") is True:
            steps.append("Keep the delivery or tracking record.")
        elif answers.get("delivery_received") is False:
            steps.append("Check the tracking status and keep any delivery updates.")
        if answers.get("communication_available") is True:
            steps.append("Keep the seller or platform communications and reference number.")
        elif answers.get("seller_contacted") is False:
            steps.append("Contact the seller or platform through its recorded support channel.")
        if answers.get("issue_resolved") is False:
            steps.append(
                "If the issue remains unresolved, consider the National Consumer Helpline (1915) or the applicable Consumer Commission procedure."
            )
        return steps

    @staticmethod
    def _service_situation(answers: Dict[str, Any]) -> str:
        service = answers.get("service_type") or "service"
        provider = answers.get("service_provider")
        if answers.get("service_purchased") is True:
            situation = f"You purchased {service}"
            if provider:
                situation += f" from {provider}"
            situation += "."
        else:
            return "You reported that you did not purchase the service from a provider or business."

        if answers.get("service_problem_exists") is True:
            categories = [
                label for key, label in (
                    ("service_not_provided", "not provided"),
                    ("service_delayed", "delayed"),
                    ("service_inadequate", "inadequate or incomplete"),
                    ("service_not_as_agreed", "not as agreed"),
                ) if answers.get(key) is True
            ]
            description = answers.get("problem_description")
            if description:
                situation += f" You reported: {description}."
            elif categories:
                situation += f" You reported that the service was {', '.join(categories)}."
            if answers.get("provider_contacted") is True:
                if answers.get("issue_resolved") is True:
                    situation += " You contacted the provider and reported that the issue was resolved."
                elif answers.get("issue_resolved") is False:
                    situation += " The issue remains unresolved after contacting the provider."
            elif answers.get("provider_contacted") is False:
                situation += " You have not yet contacted the provider."
            resolution = answers.get("desired_resolution")
            if resolution and resolution != "Not sure":
                situation += f" You are seeking {resolution.lower()}."
        return situation

    @staticmethod
    def _advertisement_situation(answers: Dict[str, Any]) -> str:
        if answers.get("advertisement_seen") is not True:
            return "You reported that you have not seen an advertisement or business claim."
        business = answers.get("advertiser_or_business")
        product = answers.get("product_or_service")
        situation = "You saw an advertisement"
        if answers.get("advertisement_source"):
            situation += f" at {answers['advertisement_source']}"
        if business:
            situation += f" from {business}"
        if product:
            situation += f" about {product}"
        situation += "."

        claim = answers.get("claim_description")
        if claim:
            situation += f" The claim was: {claim}."
        actual = answers.get("actual_experience")
        if actual:
            situation += f" Your reported experience: {actual}."
        if answers.get("claim_false_or_misleading") is True:
            situation += " You believe the claim was false or misleading."
        if answers.get("important_information_hidden") is True:
            situation += " You reported that important information was hidden."
        if answers.get("difference_from_advertisement"):
            situation += f" Difference reported: {answers['difference_from_advertisement']}."
        if answers.get("business_contacted") is True:
            if answers.get("issue_resolved") is True:
                situation += " You contacted the business and reported that the issue was resolved."
            elif answers.get("issue_resolved") is False:
                situation += " The issue remains unresolved after contacting the business."
        elif answers.get("business_contacted") is False:
            situation += " You have not yet contacted the business."
        resolution = answers.get("desired_resolution")
        if resolution and resolution != "Not sure":
            situation += f" You are seeking {resolution.lower()}."
        return situation

    @staticmethod
    def _service_next_steps(
        answers: Dict[str, Any], resolved: bool = False, contact_first: bool = False
    ) -> List[str]:
        steps = []
        steps.append(
            "Keep the invoice and payment proof."
            if answers.get("purchase_proof_available") is True
            else "Locate the invoice, payment proof, or booking confirmation."
        )
        if answers.get("service_evidence_available") is True:
            steps.append("Keep the service records and other evidence of the problem.")
        else:
            steps.append("Keep any service records, appointment details, or evidence of the problem.")
        if answers.get("communication_available") is True:
            steps.append("Keep communications with the provider and any service request number.")
        elif answers.get("provider_contacted") is True:
            steps.append("Ask the provider to confirm its response in writing and keep the reference number.")
        if contact_first:
            steps.append("Contact the provider in writing with the problem and requested outcome, and keep a copy.")
        if not resolved and answers.get("issue_resolved") is False:
            steps.append(
                "If unresolved, consider the National Consumer Helpline (1915) or the applicable Consumer Commission procedure."
            )
        return steps

    @staticmethod
    def _advertisement_next_steps(
        answers: Dict[str, Any], resolved: bool = False, contact_first: bool = False
    ) -> List[str]:
        steps = []
        if answers.get("advertisement_evidence_available") is True:
            steps.append("Keep the advertisement screenshot, image, or recording and its source/date.")
        else:
            steps.append("Save a copy or screenshot of the advertisement, including its source and date, if available.")
        if answers.get("product_or_service_received") is True:
            steps.append(
                "Keep the invoice and details of the product or service received."
                if answers.get("purchase_proof_available") is True
                else "Keep details of what you received and locate any purchase proof."
            )
        if answers.get("communication_available") is True:
            steps.append("Keep communications with the business and any complaint reference number.")
        elif answers.get("business_contacted") is True:
            steps.append("Ask the business to respond in writing and keep its response.")
        if contact_first:
            steps.append("Ask the business in writing to clarify or correct the claim and keep a copy.")
        if not resolved and answers.get("issue_resolved") is False:
            steps.append(
                "If unresolved, consider the National Consumer Helpline (1915) or the applicable Consumer Commission procedure."
            )
        return steps
