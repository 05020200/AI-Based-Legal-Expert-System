import json
from typing import Any, Dict, List, Optional, Union

from database.db import get_db_connection


class AuthorityInfoService:
    """Service to determine the appropriate authority based on
    the domain and monetary consideration of a dispute.

    For consumer disputes, the monetary limits are stored in the ``authorities``
    table. For other domains, static authority information is provided.
    """

    # Static metadata describing the legal source of the jurisdiction thresholds
    _JURISDICTION_SOURCE = {
        "source": "Consumer Protection (Jurisdiction of the District Commission, the State Commission and the National Commission) Rules, 2021",
        "organization": "Department of Consumer Affairs, Government of India",
        "verification_date": "2026-09-28",
    }

    # Fixed territorial‑jurisdiction factors from Section 34(2) CPA 2019
    _TERRITORIAL_JURISDICTION_FACTORS = [
        "place where the opposite party resides or carries on business",
        "place where the cause of action wholly or partly arises",
        "place where the complainant resides or personally works for gain",
    ]

    # Domain-specific authority info for non-consumer domains
    _DOMAIN_AUTHORITIES = {
        "contract": {
            "authority": {
                "name": "Civil Court",
                "jurisdiction_level": "District / High Court (depending on the value of the claim)",
                "description": "Contract disputes are generally adjudicated by civil courts. The jurisdictional court depends on the value of the subject matter and the place where the contract was made or was to be performed.",
            },
            "legal_basis": [
                "Indian Contract Act, 1872",
                "Code of Civil Procedure, 1908",
            ],
            "complaint_procedure": [
                {"step_number": 1, "step_description": "Send a legal notice to the breaching party"},
                {"step_number": 2, "step_description": "If no satisfactory response, prepare the plaint (complaint document)"},
                {"step_number": 3, "step_description": "File the civil suit in the appropriate court"},
                {"step_number": 4, "step_description": "Attend hearings and present evidence"},
            ],
            "disclaimer": "This information is provided for educational purposes only and does not constitute legal advice.",
        },
        "rental": {
            "authority": {
                "name": "Rent Controller / Civil Court",
                "jurisdiction_level": "District (varies by state)",
                "description": "Rental disputes are governed by state-specific rent control laws. The Rent Controller or civil court in the district where the property is located typically has jurisdiction.",
            },
            "legal_basis": [
                "State-specific Rent Control Act",
                "Transfer of Property Act, 1882 — Section 108",
            ],
            "complaint_procedure": [
                {"step_number": 1, "step_description": "Identify the applicable state rent control law"},
                {"step_number": 2, "step_description": "Send a written notice to the other party"},
                {"step_number": 3, "step_description": "File an application with the Rent Controller or appropriate authority"},
                {"step_number": 4, "step_description": "Attend hearings and present evidence"},
            ],
            "jurisdictional_note": "Rent control laws vary by state. The applicable state/UT must be identified to determine the exact authority and procedure.",
            "disclaimer": "This information is provided for educational purposes only and does not constitute legal advice.",
        },
        "cyber": {
            "authority": {
                "name": "Cyber Crime Cell / Local Police Station",
                "jurisdiction_level": "Local / National",
                "description": "Cyber complaints can be filed online through the National Cyber Crime Reporting Portal (cybercrime.gov.in) or at the nearest police station / cyber crime cell.",
            },
            "additional_authorities": [
                {
                    "name": "National Cyber Crime Reporting Portal",
                    "url": "https://cybercrime.gov.in",
                    "helpline": "1930",
                    "description": "Online portal for reporting cyber crimes. Available 24x7.",
                },
            ],
            "legal_basis": [
                "Information Technology Act, 2000",
                "Bharatiya Nyaya Sanhita, 2023 (for fraud-related offences)",
            ],
            "complaint_procedure": [
                {"step_number": 1, "step_description": "Preserve all evidence (screenshots, transaction records, messages)"},
                {"step_number": 2, "step_description": "For financial fraud: immediately contact your bank to block the account/card"},
                {"step_number": 3, "step_description": "File a complaint on cybercrime.gov.in or call helpline 1930"},
                {"step_number": 4, "step_description": "File an FIR at the nearest police station or cyber crime cell"},
            ],
            "disclaimer": "This information is provided for educational purposes only and does not constitute legal advice.",
        },
    }

    def __init__(self) -> None:
        self._conn = get_db_connection()
        # Allow graceful initialization even without DB for non-consumer domains
        if not self._conn:
            self._conn = None

    # ---------------------------------------------------------------------
    # Helper utilities
    # ---------------------------------------------------------------------
    @staticmethod
    def _coerce_amount(amount: Any) -> Optional[float]:
        """Convert *amount* to a float if possible.

        Returns ``None`` for invalid input (e.g., ``None``, empty string,
        non‑numeric string, negative values).  Zero is considered a valid
        amount but will be treated as *invalid* for authority lookup because it
        does not satisfy any monetary range.
        """
        if amount is None:
            return None
        try:
            # ``float`` also accepts integer strings.
            value = float(amount)
        except (TypeError, ValueError):
            return None
        # Negative values are not meaningful in this context.
        if value < 0:
            return None
        return value

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def get_authority_for_amount(self, amount: Any) -> Union[Dict[str, Any], str]:
        """Return the authority row that matches *amount*.

        If *amount* is invalid, a descriptive validation string is returned.
        The returned dictionary contains the fields from the ``authorities``
        table plus the static ``source`` metadata.
        """
        if not self._conn:
            return "Database connection unavailable"

        value = self._coerce_amount(amount)
        if value is None or value == 0:
            return "Invalid amount – cannot determine authority"

        cursor = self._conn.cursor(dictionary=True)
        query = (
            "SELECT * FROM authorities "
            "WHERE monetary_limit_min <= %s AND monetary_limit_max >= %s "
            "ORDER BY monetary_limit_min ASC LIMIT 1"
        )
        cursor.execute(query, (value, value))
        authority = cursor.fetchone()
        cursor.close()
        if not authority:
            return "No matching authority found for the given amount"
        # Attach source metadata
        authority["source"] = self._JURISDICTION_SOURCE
        return authority

    def get_territorial_jurisdiction_info(self) -> Dict[str, List[str]]:
        """Return the statutory territorial‑jurisdiction factors.
        """
        return {"territorial_jurisdiction": self._TERRITORIAL_JURISDICTION_FACTORS}

    def get_complaint_procedure(self, authority_id: int) -> List[Dict[str, Any]]:
        """Retrieve the ordered complaint‑procedure steps for *authority_id*.
        The result is a list of dictionaries with ``step_number`` and
        ``step_description``.
        """
        if not self._conn:
            return []
        cursor = self._conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT step_number, step_description FROM complaint_procedures "
            "WHERE authority_id = %s ORDER BY step_number",
            (authority_id,),
        )
        steps = cursor.fetchall()
        cursor.close()
        return steps

    def get_authority_information(self, amount: Any, domain: str = "consumer") -> Dict[str, Any]:
        """High‑level helper that bundles all relevant information.

        For consumer domain, uses DB-based authority lookup.
        For other domains, uses static authority information.
        """
        # Non-consumer domains use static authority info
        if domain and domain != "consumer":
            domain_info = self._DOMAIN_AUTHORITIES.get(domain)
            if domain_info:
                return domain_info
            return {"error": f"No authority information available for domain: {domain}"}

        # Consumer domain — use DB
        if not self._conn:
            return {"error": "Database connection unavailable for authority lookup"}

        authority = self.get_authority_for_amount(amount)
        if isinstance(authority, str):
            # Validation error – return a minimal deterministic structure.
            return {"error": authority}

        territorial = self.get_territorial_jurisdiction_info()
        complaint_steps = self.get_complaint_procedure(authority["authority_id"])

        result: Dict[str, Any] = {
            "authority": {
                "name": authority["name"],
                "jurisdiction_level": authority["jurisdiction_level"],
                "monetary_basis": {
                    "min": float(authority["monetary_limit_min"]),
                    "max": float(authority["monetary_limit_max"]),
                },
                "source": self._JURISDICTION_SOURCE,
            },
            "territorial_jurisdiction": territorial["territorial_jurisdiction"],
            "complaint_procedure": complaint_steps,
            "legal_basis": [
                "Section 34(2) of the Consumer Protection Act, 2019",
                "Section 35 of the Consumer Protection Act, 2019",
                "Consumer Protection (Jurisdiction of the District Commission, the State Commission and the National Commission) Rules, 2021",
            ],
            "disclaimer": "This information is provided for educational purposes only and does not constitute legal advice.",
        }
        return result
