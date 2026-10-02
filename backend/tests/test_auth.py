import pytest
from app import app
from database.db import get_db_connection
from werkzeug.security import check_password_hash

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.secret_key = 'test-secret'
    with app.test_client() as client:
        yield client

def test_registration_and_login(client):
    import uuid
    test_user = f"testuser_{uuid.uuid4().hex[:6]}"
    test_pass = "password123"

    # Register
    res = client.post('/api/register', json={"username": test_user, "password": test_pass})
    assert res.status_code == 201
    assert res.get_json()['success'] is True

    # Duplicate Register
    res = client.post('/api/register', json={"username": test_user, "password": test_pass})
    assert res.status_code == 400

    # Login
    res = client.post('/api/login', json={"username": test_user, "password": test_pass})
    assert res.status_code == 200
    assert res.get_json()['success'] is True

    # Me Endpoint
    res = client.get('/api/me')
    assert res.status_code == 200
    assert res.get_json()['logged_in'] is True

    # Logout
    res = client.post('/api/logout')
    assert res.status_code == 200

    res = client.get('/api/me')
    assert res.status_code == 401


def test_registration_with_name_email_and_hashed_password(client):
    import uuid

    email = f"phase1_{uuid.uuid4().hex[:12]}@example.test"
    password = "secure-test-password"
    connection = None
    cursor = None
    user_id = None
    try:
        response = client.post('/api/register', json={
            "name": "Phase One User",
            "email": email,
            "password": password,
        })
        assert response.status_code == 201
        assert response.get_json()["success"] is True

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT user_id, username, full_name, email, password_hash FROM users WHERE email = %s", (email,))
        stored = cursor.fetchone()
        user_id = stored["user_id"]
        assert stored["full_name"] == "Phase One User"
        assert stored["username"] == email
        assert stored["password_hash"] != password
        assert check_password_hash(stored["password_hash"], password)

        login = client.post('/api/login', json={"email": email, "password": password})
        assert login.status_code == 200
        assert login.get_json()["name"] == "Phase One User"
        assert client.get('/api/me').get_json()["logged_in"] is True
    finally:
        if user_id is not None:
            cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
            connection.commit()
        if cursor:
            cursor.close()
        if connection:
            connection.close()
