import sys
import os
import pytest

# Add project root to Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


# Test home route
def test_home_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.data is not None


# Test invalid route
def test_invalid_route(client):
    response = client.get("/randompage")
    assert response.status_code == 404


# Test POST request handling (if form exists)
def test_post_request(client):
    response = client.post("/", data={})
    assert response.status_code in [200, 302, 405]


# Test headers exist
def test_headers(client):
    response = client.get("/")
    assert "Content-Type" in response.headers


# Test response content type
def test_content_type(client):
    response = client.get("/")
    assert response.content_type is not None


# Test multiple requests
def test_multiple_requests(client):
    for _ in range(3):
        response = client.get("/")
        assert response.status_code == 200


# Test redirect handling
def test_redirect(client):
    response = client.get("/", follow_redirects=True)
    assert response.status_code == 200


# Test application configuration
def test_app_config():
    assert app.config is not None


# Test Flask app instance
def test_app_instance():
    assert app is not None