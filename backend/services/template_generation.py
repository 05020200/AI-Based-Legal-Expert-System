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
