# pyrefly: ignore [missing-import]
import mysql.connector

try:
    from ..config import Config
except ImportError:
    from config import Config


def get_db_connection():
    """
    Creates and returns a connection to the MySQL database 
    using the credentials from the environment variables.
    """
    try:
        connection = mysql.connector.connect(
            host=Config.DB_HOST,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            database=Config.DB_NAME
        )
        return connection
    except mysql.connector.Error as err:
        print(f"Error connecting to MySQL: {err}")
        return None
