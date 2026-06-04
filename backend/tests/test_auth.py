def test_register_and_login(client) -> None:
    register_response = client.post(
        "/auth/register",
        json={"email": "researcher@example.com", "password": "secret123", "role": "researcher"},
    )

    assert register_response.status_code == 201
    assert register_response.json()["token_type"] == "bearer"
    assert register_response.json()["access_token"]

    login_response = client.post(
        "/auth/login",
        json={"email": "researcher@example.com", "password": "secret123"},
    )

    assert login_response.status_code == 200
    assert login_response.json()["access_token"]

