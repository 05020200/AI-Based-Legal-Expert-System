# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
load_dotenv()

from backend.database.db import get_db_connection

def test_connection():
    print("Testing database connection...")
    conn = get_db_connection()
    if conn and conn.is_connected():
        print("Success! Connected to MySQL database.")
        conn.close()
    else:
        print("Failed! Could not connect to MySQL database.")

if __name__ == '__main__':
    test_connection()
