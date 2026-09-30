import pytest
from app import app
from database.db import get_db_connection

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
