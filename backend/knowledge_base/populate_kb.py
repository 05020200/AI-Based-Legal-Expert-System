import os
import json
import sys
from dotenv import load_dotenv

load_dotenv()

# Allow importing the database package
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from database.db import get_db_connection


def populate():
    conn = get_db_connection()

    if not conn:
        print("Failed to connect to database.")
        return

    cursor = conn.cursor(dictionary=True)

    try:
        print("Clearing existing knowledge base data...")

        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

        cursor.execute("TRUNCATE TABLE rule_conditions")
        cursor.execute("TRUNCATE TABLE legal_rules")
        cursor.execute("TRUNCATE TABLE legal_provisions")
        cursor.execute("TRUNCATE TABLE legal_acts")

        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")

        # --------------------------------------------------
        # 1. Load Legal Provisions
        # --------------------------------------------------

        provisions_file = os.path.join(
            os.path.dirname(__file__),
            "legal_provisions.json"
        )

        with open(provisions_file, "r", encoding="utf-8") as file:
            acts_data = json.load(file)

        provision_title_to_id = {}

        print("Populating legal acts and provisions...")

        for act in acts_data:

            cursor.execute(
                """
                INSERT INTO legal_acts
                (act_name, year, description)
                VALUES (%s, %s, %s)
                """,
                (
                    act["act_name"],
                    act["year"],
                    act.get("description", "")
                )
            )

            act_id = cursor.lastrowid

            for provision in act["provisions"]:

                cursor.execute(
                    """
                    INSERT INTO legal_provisions
                    (
                        act_id,
                        act_name,
                        section_number,
                        title,
                        plain_language_description,
                        applicability,
                        source_url,
                        verification_status,
                        last_verified_date
                    )
                    VALUES
                    (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                    """,
                    (
                        act_id,
                        act["act_name"],
                        provision["section_number"],
                        provision["title"],
                        provision["plain_language_description"],
                        provision["applicability"],
                        provision["source_url"],
                        provision["verification_status"],
                        provision.get("last_verified_date")
                    )
                )

                provision_id = cursor.lastrowid

                provision_title_to_id[
                    provision["title"]
                ] = provision_id

        # --------------------------------------------------
        # 2. Load AI Inference Rules
        # --------------------------------------------------

        rules_file = os.path.join(
            os.path.dirname(__file__),
            "inference_rules.json"
        )

        with open(rules_file, "r", encoding="utf-8") as file:
            rules_data = json.load(file)

        print("Populating AI inference rules...")

        for rule in rules_data:

            provision_title = rule.get(
                "legal_provision_title"
            )

            provision_id = provision_title_to_id.get(
                provision_title
            )

            cursor.execute(
                """
                INSERT INTO legal_rules
                (
                    rule_id,
                    rule_name,
                    conclusion,
                    explanation,
                    legal_provision_reference
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    rule["rule_id"],
                    rule["rule_name"],
                    rule["conclusion"],
                    rule["explanation"],
                    provision_id
                )
            )

            for condition in rule["conditions"]:

                cursor.execute(
                    """
                    INSERT INTO rule_conditions
                    (
                        rule_id,
                        fact_key,
                        operator,
                        expected_value
                    )
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        rule["rule_id"],
                        condition["fact_key"],
                        condition["operator"],
                        condition["expected_value"]
                    )
                )

        conn.commit()

        # --------------------------------------------------
        # 3. Populate Consumer Commission authorities and complaint procedures
        # --------------------------------------------------
        # Insert authorities only if the table is empty to avoid duplicate rows on repeated runs.
        cursor.execute("SELECT COUNT(*) AS cnt FROM authorities")
        # fetchone returns a tuple when the cursor is not dictionary-enabled; use index 0 for count
        count = cursor.fetchone()[0]
        if count == 0:
            # District Consumer Disputes Redressal Commission
            cursor.execute(
                """
                INSERT INTO authorities (name, jurisdiction_level, monetary_limit_min, monetary_limit_max, address)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    "District Consumer Disputes Redressal Commission",
                    "District",
                    0,
                    5000000,
                    "",
                ),
            )
            district_id = cursor.lastrowid
            # State Consumer Disputes Redressal Commission
            cursor.execute(
                """
                INSERT INTO authorities (name, jurisdiction_level, monetary_limit_min, monetary_limit_max, address)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    "State Consumer Disputes Redressal Commission",
                    "State",
                    5000000,
                    20000000,
                    "",
                ),
            )
            state_id = cursor.lastrowid
            # National Consumer Disputes Redressal Commission
            cursor.execute(
                """
                INSERT INTO authorities (name, jurisdiction_level, monetary_limit_min, monetary_limit_max, address)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    "National Consumer Disputes Redressal Commission",
                    "National",
                    20000000,
                    9999999999,
                    "",
                ),
            )
            national_id = cursor.lastrowid

            # Insert generic complaint procedure steps for each authority.
            steps = [
                (district_id, 1, "Identify the consumer issue and gather evidence"),
                (district_id, 2, "Prepare the complaint document"),
                (district_id, 3, "File the complaint with the District Commission (electronic or physical)"),
                (district_id, 4, "Track the complaint and follow up on proceedings"),
                (state_id, 1, "Identify the consumer issue and gather evidence"),
                (state_id, 2, "Prepare the complaint document"),
                (state_id, 3, "File the complaint with the State Commission (electronic or physical)"),
                (state_id, 4, "Track the complaint and follow up on proceedings"),
                (national_id, 1, "Identify the consumer issue and gather evidence"),
                (national_id, 2, "Prepare the complaint document"),
                (national_id, 3, "File the complaint with the National Commission (electronic or physical)"),
                (national_id, 4, "Track the complaint and follow up on proceedings"),
            ]
            cursor.executemany(
                "INSERT INTO complaint_procedures (authority_id, step_number, step_description) VALUES (%s, %s, %s)",
                steps,
            )
            conn.commit()
        

        print()
        print("======================================")
        print("Knowledge Base populated successfully!")
        print("======================================")

    except Exception as error:

        conn.rollback()

        print()
        print("Error populating knowledge base:")
        print(error)

    finally:

        cursor.close()
        conn.close()


if __name__ == "__main__":
    populate()