import json
from typing import Dict, Any, List, Optional

from database.db import get_db_connection


class TemplateGenerationService:
    """Service to generate a preliminary consumer complaint template.

    The service first tries to fetch a stored template from the ``templates``
    table that matches the provided ``issue`` (using the ``document_name`` field).
    If a stored template exists, placeholder values are substituted.  If not, a
    generic academic draft is produced.

    Placeholders follow the ``[PLACEHOLDER]`` convention and are left untouched
    when the corresponding data is missing.
    """

    # Mapping of issue (lower‑case) to a legal provision reference for metadata.
    _ISSUE_LEGAL_REFERENCE = {
        "defective product": "Consumer Protection Act, 2019 — Section 2(10)",
        "refund / replacement issue": "Consumer Protection Act, 2019 — Section 2(8)",
        "deficiency in service": "Consumer Protection Act, 2019 — Section 2(11)",
        "warranty‑related issue": "Consumer Protection Act, 2019 — Section 2(10)",
        "misleading advertisement / unfair trade practice": "Consumer Protection Act, 2019 — Section 2(47)",
        "e‑commerce consumer issue": "Consumer Protection Act, 2019 — Section 2(8)",
    }

    _DEFECTIVE_PRODUCT_DOCUMENTS = {
        "seller_complaint": (
            "Subject: Complaint about a product problem\n\n"
            "To: {seller_name}\n\n"
            "I purchased {product_name} on {purchase_date}. The amount paid was {amount_paid}. "
            "The order or invoice number is {order_number}.\n\n"
            "Problem reported: {problem}\n"
            "Previous seller contact and response: {seller_response}\n\n"
            "I request that you review this issue and consider the following resolution: {resolution}. "
            "Please respond through the appropriate customer-support channel.\n\n"
            "This draft reflects only the information entered and should be reviewed before sending.\n"
            "Consumer name: [Consumer Name Not Provided]\n"
            "Contact details: [Contact Details Not Provided]\n"
            "Date: [Date Not Provided]"
        ),
        "replacement_request": (
            "Subject: Request to consider replacement of a product\n\n"
            "To: {seller_name}\n\n"
            "I purchased {product_name} on {purchase_date}; amount paid: {amount_paid}; "
            "order or invoice number: {order_number}.\n\n"
            "The product problem reported is: {problem}.\n"
            "Previous seller contact and response: {seller_response}.\n\n"
            "I request that you consider a replacement, subject to the circumstances and applicable terms.\n\n"
            "Consumer name: [Consumer Name Not Provided]\n"
            "Date: [Date Not Provided]"
        ),
        "refund_request": (
            "Subject: Request to consider refund for a product problem\n\n"
            "To: {seller_name}\n\n"
            "I purchased {product_name} on {purchase_date}; amount paid: {amount_paid}; "
            "order or invoice number: {order_number}.\n\n"
            "The product problem reported is: {problem}.\n"
            "Previous seller contact and response: {seller_response}.\n\n"
            "I request that you review the issue and consider a refund, subject to the circumstances and applicable terms.\n\n"
            "Consumer name: [Consumer Name Not Provided]\n"
            "Date: [Date Not Provided]"
        ),
    }
    _DOCUMENT_TITLES = {
        "seller_complaint": "SELLER COMPLAINT",
        "replacement_request": "REPLACEMENT REQUEST",
        "refund_request": "REFUND REQUEST",
        "consumer_commission_complaint": "CONSUMER COMMISSION COMPLAINT",
    }

    def __init__(self) -> None:
        self._conn = get_db_connection()
        if not self._conn:
            raise RuntimeError("Unable to obtain a database connection for TemplateGenerationService")

    def _fetch_stored_template(self, issue: str) -> Optional[Dict[str, Any]]:
        """Return a stored template row for *issue* if present.

        The ``templates`` table stores a ``document_name`` that we align with the
        issue name (case‑insensitive).  The row contains ``content`` and a JSON
        list of ``placeholders``.
        """
        cursor = self._conn.cursor(dictionary=True)
        query = "SELECT content, placeholders FROM templates WHERE LOWER(document_name) = %s"
        cursor.execute(query, (issue.lower(),))
        row = cursor.fetchone()
        cursor.close()
        if row:
            # ``placeholders`` is stored as a JSON string.
            try:
                placeholders = json.loads(row["placeholders"]) if row["placeholders"] else []
            except Exception:
                placeholders = []
            return {"content": row["content"], "placeholders": placeholders}
        return None

    def _fill_placeholders(self, template: str, data: Dict[str, Any], placeholders: List[str]) -> str:
        """Replace known placeholders with supplied *data*.

        Unknown placeholders remain verbatim (e.g., ``[UNKNOWN]``).  Missing data
        results in the placeholder staying untouched, satisfying the "no
        fabrication" rule.
        """
        result = template
        for ph in placeholders:
            key = ph.strip("[]")  # e.g., "[CONSUMER NAME]" -> "CONSUMER NAME"
            value = data.get(key.lower())
            if value:
                result = result.replace(ph, str(value))
        return result

    def generate_template(self, issue: str, data: Dict[str, Any]) -> str:
        """Generate a deterministic complaint draft.

        Parameters
        ----------
        issue: str
            The consumer issue (e.g., "Defective Product").
        data: dict
            Keys correspond to lower‑cased placeholder names without brackets.
            Example: {"consumer name": "Alice", "seller name": "Bob Ltd"}
        """
        # Try to retrieve a stored template first.
        stored = self._fetch_stored_template(issue)
        if stored:
            # Apply Python format substitution for {issue} placeholder if present
            template_content = stored["content"].format(issue=issue)
            placeholders = stored.get("placeholders", [])
            return self._fill_placeholders(template_content, data, placeholders)

        # No stored template – build a generic academic draft.
        # Define the set of placeholders we will use.
        # Include a legal reference line based on the issue, if known.
        reference = self._ISSUE_LEGAL_REFERENCE.get(issue.lower())
        legal_ref_line = f"Legal Reference: {reference}\n\n" if reference else ""

        placeholders = [
            "[CONSUMER NAME]",
            "[SELLER / SERVICE PROVIDER NAME]",
            "[DATE OF PURCHASE]",
            "[AMOUNT PAID]",
            "[DESCRIPTION OF PRODUCT/SERVICE]",
            "[PROBLEM ENCOUNTERED]",
            "[RELIEF REQUESTED]",
            "[ANY ADDITIONAL FACTS]",
        ]
        # Generic template sections.
        template = (
            "Preliminary Complaint Draft / Academic Template\n"
            "---------------------------------------------------\n"
            "1. Consumer Details\n"
            "   Name: [CONSUMER NAME]\n"
            "   Address: [CONSUMER ADDRESS] (if known)\n\n"
            "2. Opposite Party Details\n"
            "   Name: [SELLER / SERVICE PROVIDER NAME]\n"
            "   Address: [OPPOSITE PARTY ADDRESS] (if known)\n\n"
            "3. Subject\n"
            f"   Complaint regarding: {issue}\n\n"
            "4. Facts of the Matter\n"
            "   Date of Purchase: [DATE OF PURCHASE]\n"
            "   Amount Paid: [AMOUNT PAID]\n"
            "   Description of Product/Service: [DESCRIPTION OF PRODUCT/SERVICE]\n"
            "   Problem Encountered: [PROBLEM ENCOUNTERED]\n"
            "   Additional Facts: [ANY ADDITIONAL FACTS]\n\n"
            "5. Nature of the Consumer Issue\n"
            f"   {issue}\n\n"
            "6. Previous Communication with Seller/Service Provider\n"
            "   (List any communications, if any)\n\n"
            "7. Documents / Evidence Available\n"
            "   (Enumerate documents the consumer can provide)\n\n"
            "8. Relief / Request Sought\n"
            "   [RELIEF REQUESTED]\n\n"
            "9. Declaration\n"
            "   I, [CONSUMER NAME], hereby declare that the above facts are true to the best of my knowledge.\n\n"
            "10. Date / Place / Signature\n"
            "   Date: [DATE OF PURCHASE]\n"
            "   Place: ______________________\n"
            "   Signature: ______________________\n"
        )
        # Fill placeholders with provided data where possible.
        return self._fill_placeholders(legal_ref_line + template, data, placeholders)

    def generate_defective_product_document(
        self,
        document_type: str,
        case_details: Dict[str, Any],
        consumer_details: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate an explicitly requested defective-product draft."""
        if document_type == "consumer_commission_complaint":
            return self._generate_commission_complaint(case_details, consumer_details or {})
        template = self._DEFECTIVE_PRODUCT_DOCUMENTS.get(document_type)
        if template is None:
            raise ValueError("Unsupported defective-product document type.")

        amount = case_details.get("amount_paid")
        amount_text = self._format_amount(amount)

        values = {
            "seller_name": case_details.get("seller_name") or "[Seller/Business Name Not Provided]",
            "product_name": case_details.get("product_name") or "[Product Name Not Provided]",
            "purchase_date": self._format_date(case_details.get("purchase_date"), "Purchase Date"),
            "amount_paid": amount_text,
            "order_number": case_details.get("order_or_invoice_number") or "[Order/Invoice Number Not Provided]",
            "problem": case_details.get("problem_description") or "[Product Problem Not Provided]",
            "seller_response": case_details.get("seller_response") or "[Seller Response Not Provided]",
            "resolution": case_details.get("desired_resolution") or "[Desired Resolution Not Provided]",
            "consumer_name": (consumer_details or {}).get("consumer_name") or "[Consumer Name Not Provided]",
            "consumer_address": (consumer_details or {}).get("consumer_address") or "[Consumer Address Not Provided]",
            "consumer_phone": (consumer_details or {}).get("consumer_phone") or "[Consumer Phone Not Provided]",
            "consumer_email": (consumer_details or {}).get("consumer_email") or "[Consumer Email Not Provided]",
            "document_date": self._format_date((consumer_details or {}).get("document_date"), "Document Date"),
            "seller_address": case_details.get("seller_address") or "[Seller Address Not Provided]",
        }
        title = self._DOCUMENT_TITLES[document_type]
        body = template.format(**values)
        body = body.replace(
            f"To: {values['seller_name']}",
            f"From:\n{values['consumer_name']}\n{values['consumer_address']}\n"
            f"{values['consumer_phone']}\n{values['consumer_email']}\n\n"
            f"To: {values['seller_name']}\n{values['seller_address']}",
        )
        body = body.replace(
            "Consumer name: [Consumer Name Not Provided]\nContact details: [Contact Details Not Provided]\nDate: [Date Not Provided]",
            f"Yours faithfully,\n\n{values['consumer_name']}\n\n"
            f"Signature: ____________________\nDate: {values['document_date']}",
        ).replace(
            "Consumer name: [Consumer Name Not Provided]\nDate: [Date Not Provided]",
            f"Yours faithfully,\n\n{values['consumer_name']}\n\n"
            f"Signature: ____________________\nDate: {values['document_date']}",
        )

        answers = case_details.get("answers") or {}
        evidence_labels = {
            "purchase_proof_available": "Purchase Invoice / Receipt",
            "problem_evidence_available": "Photographs / Videos of Defect",
            "seller_communication_available": "Communication Records with Seller",
        }
        evidence = [
            label for fact_key, label in evidence_labels.items()
            if answers.get(fact_key) is True
        ]
        evidence_text = "\n".join(f"- {item}" for item in evidence)
        if not evidence_text:
            evidence_text = "[No evidence reported as available]"
        case_id = case_details.get("case_id") or "[Case ID Not Provided]"
        document_date = values["document_date"]
        selected_resolution = case_details.get("selected_resolution") or "[Not provided]"
        return (
            f"{title}\nCase ID: {case_id}\nDate: {document_date}\n\n"
            f"Selected resolution in case: {selected_resolution}\n\n"
            f"{body}\n\nEvidence reported available:\n{evidence_text}"
        )

    def _generate_commission_complaint(
        self, case_details: Dict[str, Any], consumer_details: Dict[str, Any]
    ) -> str:
        report = case_details.get("report") or {}
        summary = report.get("case_summary") or {}
        answers = case_details.get("answers") or {}
        where = report.get("where_to_complain") or {}
        pecuniary = where.get("pecuniary_jurisdiction") or {}
        commission = (
            pecuniary.get("authority")
            if pecuniary.get("determined")
            else "Competent Consumer Disputes Redressal Commission (to be confirmed)"
        )
        consumer_name = consumer_details.get("consumer_name", "").strip()
        if not consumer_name:
            raise ValueError("Consumer name is required to prepare this document.")

        product = self._provided(case_details.get("product_name"), "Product Name")
        seller = self._provided(case_details.get("seller_name"), "Seller/Business Name")
        purchase_date = self._format_date(case_details.get("purchase_date"), "Purchase Date")
        amount = self._format_amount(case_details.get("amount_paid"))
        invoice = self._provided(case_details.get("order_or_invoice_number"), "Order/Invoice Number")
        problem = self._provided(case_details.get("problem_description"), "Product Problem")
        seller_response = self._provided(case_details.get("seller_response"), "Seller Response")

        facts = []
        if answers.get("product_purchased") is True:
            facts.append(
                f"The complainant reports purchasing a {product} from {seller} on {purchase_date} for {amount}. "
                f"The order or invoice number supplied is {invoice}."
            )
        if answers.get("product_has_problem") is True:
            facts.append(f"The product problem reported is: {problem}.")
        if answers.get("seller_contacted") is True:
            facts.append(
                f"The complainant reports contacting the seller. The reported response/details are: {seller_response}."
            )
            if answers.get("seller_resolved") is False:
                facts.append("The complainant reports that the issue was not resolved.")
        if not facts:
            facts.append("[Case facts not provided]")

        evidence_labels = {
            "purchase_proof_available": "Purchase Invoice / Receipt",
            "problem_evidence_available": "Photographs / Videos of Defect",
            "seller_communication_available": "Communication Records with Seller",
        }
        evidence = [
            label for fact_key, label in evidence_labels.items()
            if answers.get(fact_key) is True
        ]
        evidence_text = "\n".join(f"- {label}" for label in evidence) or "[No evidence reported as available]"

        desired = answers.get("desired_resolution")
        if desired == "Replacement":
            relief = (
                "The complainant requests that appropriate relief, including consideration of replacement "
                "of the problematic product, be granted as may be permissible under applicable law and circumstances."
            )
        elif desired == "Refund":
            relief = (
                "The complainant requests that appropriate relief, including consideration of refund of the "
                "amount paid, be granted as may be permissible under applicable law and circumstances."
            )
        elif desired == "Repair":
            relief = (
                "The complainant requests consideration of appropriate relief, which may include repair, "
                "as may be permissible under applicable law and circumstances."
            )
        else:
            relief = "The complainant requests appropriate relief as may be permissible under applicable law and circumstances."

        address = consumer_details.get("consumer_address") or "[Consumer Address Not Provided]"
        phone = consumer_details.get("consumer_phone") or "[Consumer Phone Not Provided]"
        email = consumer_details.get("consumer_email") or "[Consumer Email Not Provided]"
        document_date = consumer_details.get("document_date") or "[Document Date Not Provided]"
        seller_address = case_details.get("seller_address") or "[Seller Address Not Provided]"
        provisions = report.get("legal_provisions") or []
        law_lines = [
            f"{item.get('act_name')} — {item.get('section_number')}: {item.get('title')}"
            for item in provisions
            if item.get("section_number") in {"Section 2(10)", "Section 35", "Section 39"}
        ]
        law_text = "\n".join(f"- {line}" for line in law_lines) or (
            "Consumer Protection Act, 2019 — Section 2(10) (review the applicable facts and law)."
        )
        commission_powers_text = (
            " Section 39 describes orders the District Commission may make where statutory grounds are established."
            if any(item.get("section_number") == "Section 39" for item in provisions)
            else ""
        )

        return (
            f"BEFORE THE {commission.upper()}\n\n"
            "CONSUMER COMMISSION COMPLAINT — DRAFT FOR REVIEW\n\n"
            "COMPLAINANT:\n"
            f"{consumer_name}\n{address}\n{phone}\n{email}\n\n"
            "VERSUS\n\n"
            "OPPOSITE PARTY:\n"
            f"{seller}\n{seller_address}\n\n"
            "SUBJECT / NATURE OF COMPLAINT:\n"
            "Consumer complaint concerning defective goods and an unresolved consumer grievance.\n\n"
            "CASE DETAILS:\n"
            f"Product: {product}\nPurchase date: {purchase_date}\nAmount paid: {amount}\n"
            f"Order/invoice number: {invoice}\n\n"
            "FACTS OF THE CASE:\n"
            + "\n".join(f"{index}. {fact}" for index, fact in enumerate(facts, start=1))
            + "\n\nGROUNDS / POSSIBLE LEGAL BASIS:\n"
            "The reported facts may be relevant to a consumer dispute involving a defect under Section 2(10) "
            "of the Consumer Protection Act, 2019. Section 35 concerns the manner in which a consumer "
            f"complaint may be made.{commission_powers_text} This draft does not determine that a defect or claim has been proved.\n\n"
            f"Configured provisions:\n{law_text}\n\n"
            f"RELIEF / PRAYER:\n{relief}\n\n"
            f"EVIDENCE / DOCUMENTS REPORTED:\n{evidence_text}\n\n"
            "VERIFICATION / DECLARATION:\n"
            f"I, {consumer_name}, state that this draft is based on the information supplied by me and is to be reviewed for accuracy.\n\n"
            f"Place: [Place Not Provided]\nDate: {document_date}\n\n"
            f"Signature: ____________________\n{consumer_name}\n\n"
            "This is a draft for review and is not proof of filing or acceptance by a Consumer Commission. "
            "Verify current filing requirements and applicable procedure before submission."
        )

    @staticmethod
    def _provided(value, label):
        return str(value) if value not in (None, "") else f"[{label} Not Provided]"

    @staticmethod
    def _format_date(value, label):
        if value in (None, ""):
            return f"[{label} Not Provided]"
        try:
            from datetime import date
            parsed = date.fromisoformat(str(value))
            return f"{parsed.day} {parsed.strftime('%B %Y')}"
        except (ValueError, OSError):
            return str(value)

    @staticmethod
    def _format_amount(value):
        if value in (None, ""):
            return "[Amount Paid Not Provided]"
        try:
            digits = str(int(round(float(value))))
            if len(digits) <= 3:
                grouped = digits
            else:
                last_three = digits[-3:]
                prefix = digits[:-3]
                groups = []
                while prefix:
                    groups.insert(0, prefix[-2:])
                    prefix = prefix[:-2]
                grouped = f"{','.join(groups)},{last_three}"
            return f"₹{grouped}"
        except (TypeError, ValueError):
            return str(value)
