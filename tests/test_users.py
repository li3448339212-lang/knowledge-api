from fastapi.testclient import TestClient

from models import User


def test_register_user_success(
    client: TestClient,
    test_db,
):
    response = client.post(
        "/users",
        json={
            "username": "test_user",
            "password": "test_password123",
        },
    )

    assert response.status_code == 200

    body = response.json()
    assert body["code"] == 200
    assert body["message"] == "User created successfully"
    assert body["data"]["username"] == "test_user"
    assert "password" not in body["data"]

    db = test_db()
    try:
        user = db.query(User).filter(
            User.username == "test_user"
        ).first()

        assert user is not None
        assert user.password != "test_password123"
    finally:
        db.close()


def test_register_duplicate_username(
    client: TestClient,
):
    first_response = client.post(
        "/users",
        json={
            "username": "duplicate_user",
            "password": "test_password123",
        },
    )

    assert first_response.status_code == 200

    second_response = client.post(
        "/users",
        json={
            "username": "duplicate_user",
            "password": "another_password123",
        },
    )

    assert second_response.status_code == 400
    assert second_response.json()["message"] == (
        "Username already exists"
    )


def test_register_missing_username(
    client: TestClient,
):
    response = client.post(
        "/users",
        json={
            "password": "test_password123",
        },
    )

    assert response.status_code == 422


def test_register_missing_password(
    client: TestClient,
):
    response = client.post(
        "/users",
        json={
            "username": "missing_password_user",
        },
    )

    assert response.status_code == 422

def test_get_user_detail(
    client: TestClient,
):
    # 先注册一个用户
    register_response = client.post(
        "/users",
        json={
            "username": "detail_user",
            "password": "test_password123",
        },
    )

    assert register_response.status_code == 200

    user_id = register_response.json()["data"]["id"]

    # 登录，获取 Token
    login_response = client.post(
        "/login",
        json={
            "username": "detail_user",
            "password": "test_password123",
        },
    )

    assert login_response.status_code == 200

    token = login_response.json()["access_token"]

    # 携带 Token 查询用户详情
    response = client.get(
        f"/users/{user_id}",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 200

    body = response.json()
    assert body["code"] == 200
    assert body["data"]["id"] == user_id
    assert body["data"]["username"] == "detail_user"
    assert "password" not in body["data"]

def test_update_user_profile(
    client: TestClient,
):
    # 1. 注册用户
    register_response = client.post(
        "/users",
        json={
            "username": "update_user",
            "password": "test_password123",
        },
    )

    assert register_response.status_code == 200
    user_id = register_response.json()["data"]["id"]

    # 2. 登录获取 Token
    login_response = client.post(
        "/login",
        json={
            "username": "update_user",
            "password": "test_password123",
        },
    )

    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # 3. 更新用户资料
    response = client.put(
        f"/users/{user_id}",
        headers={
            "Authorization": f"Bearer {token}",
        },
        json={
            "username": "updated_user",
        },
    )

    assert response.status_code == 200

    body = response.json()
    assert body["data"]["username"] == "updated_user"
    assert "password" not in body["data"]

def test_update_password(
    client: TestClient,
):
    # 1. 注册用户
    register_response = client.post(
        "/users",
        json={
            "username": "password_user",
            "password": "old_password123",
        },
    )

    assert register_response.status_code == 200

    # 2. 登录获取 Token
    login_response = client.post(
        "/login",
        json={
            "username": "password_user",
            "password": "old_password123",
        },
    )

    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # 3. 修改密码
    response = client.put(
        f"/users/{register_response.json()['data']['id']}/password",
        headers={
            "Authorization": f"Bearer {token}",
        },
        json={
            "old_password": "old_password123",
            "new_password": "new_password123",
        },
    )

    print("状态码：", response.status_code)
    print("错误详情：", response.text)

    assert response.status_code == 200

    # 4. 验证新密码可以登录
    new_login_response = client.post(
        "/login",
        json={
            "username": "password_user",
            "password": "new_password123",
        },
    )

    assert new_login_response.status_code == 200
    assert new_login_response.json()["access_token"]

def test_update_password_wrong_old_password(
    client: TestClient,
):
    # 1. 注册用户
    register_response = client.post(
        "/users",
        json={
            "username": "wrong_old_password_user",
            "password": "old_password123",
        },
    )

    assert register_response.status_code == 200

    user_id = register_response.json()["data"]["id"]

    # 2. 登录获取 Token
    login_response = client.post(
        "/login",
        json={
            "username": "wrong_old_password_user",
            "password": "old_password123",
        },
    )

    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # 3. 使用错误的旧密码尝试修改密码
    response = client.put(
        f"/users/{user_id}/password",
        headers={
            "Authorization": f"Bearer {token}",
        },
        json={
            "old_password": "wrong_password123",
            "new_password": "new_password123",
        },
    )

    assert response.status_code == 400

    # 4. 确认原密码仍然可以登录
    old_login_response = client.post(
        "/login",
        json={
            "username": "wrong_old_password_user",
            "password": "old_password123",
        },
    )

    assert old_login_response.status_code == 200

    # 5. 确认新密码不能登录
    new_login_response = client.post(
        "/login",
        json={
            "username": "wrong_old_password_user",
            "password": "new_password123",
        },
    )

    assert new_login_response.status_code == 401

def test_user_cannot_delete_another_user(
    client: TestClient,
):
    # 1. 注册用户 A
    user_a_response = client.post(
        "/users",
        json={
            "username": "delete_user_a",
            "password": "password123456",
        },
    )

    assert user_a_response.status_code == 200

    # 2. 注册用户 B
    user_b_response = client.post(
        "/users",
        json={
            "username": "delete_user_b",
            "password": "password123456",
        },
    )

    assert user_b_response.status_code == 200
    user_b_id = user_b_response.json()["data"]["id"]

    # 3. 用户 A 登录
    login_response = client.post(
        "/login",
        json={
            "username": "delete_user_a",
            "password": "password123456",
        },
    )

    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # 4. 用户 A 尝试删除用户 B
    response = client.delete(
        f"/users/{user_b_id}",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 403

def test_user_cannot_update_another_user(
    client: TestClient,
):
    # 1. 注册用户 A
    user_a_response = client.post(
        "/users",
        json={
            "username": "update_user_a",
            "password": "password123456",
        },
    )

    assert user_a_response.status_code == 200

    # 2. 注册用户 B
    user_b_response = client.post(
        "/users",
        json={
            "username": "update_user_b",
            "password": "password123456",
        },
    )

    assert user_b_response.status_code == 200
    user_b_id = user_b_response.json()["data"]["id"]

    # 3. 用户 A 登录
    login_response = client.post(
        "/login",
        json={
            "username": "update_user_a",
            "password": "password123456",
        },
    )

    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # 4. 用户 A 尝试修改用户 B 的资料
    response = client.put(
        f"/users/{user_b_id}",
        headers={
            "Authorization": f"Bearer {token}",
        },
        json={
            "username": "hacked_username",
        },
    )

    assert response.status_code == 403

def test_get_nonexistent_user(
    client: TestClient,
):
    # 1. 注册并登录一个用户
    register_response = client.post(
        "/users",
        json={
            "username": "query_user",
            "password": "password123456",
        },
    )

    assert register_response.status_code == 200

    login_response = client.post(
        "/login",
        json={
            "username": "query_user",
            "password": "password123456",
        },
    )

    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # 2. 查询一个不存在的用户 ID
    response = client.get(
        "/users/999999999",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 404

def test_get_user_detail_without_token(
    client: TestClient,
):
    # 1. 注册用户
    register_response = client.post(
        "/users",
        json={
            "username": "no_token_user",
            "password": "password123456",
        },
    )

    assert register_response.status_code == 200
    user_id = register_response.json()["data"]["id"]

    # 2. 不携带 Token，直接查询用户详情
    response = client.get(
        f"/users/{user_id}",
    )

    assert response.status_code == 401

def test_update_nonexistent_user(
    client: TestClient,
):
    # 1. 注册并登录一个用户
    register_response = client.post(
        "/users",
        json={
            "username": "update_missing_user",
            "password": "password123456",
        },
    )

    assert register_response.status_code == 200

    login_response = client.post(
        "/login",
        json={
            "username": "update_missing_user",
            "password": "password123456",
        },
    )

    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # 2. 尝试修改一个不存在的用户
    response = client.put(
        "/users/999999999",
        headers={
            "Authorization": f"Bearer {token}",
        },
        json={
            "username": "new_missing_username",
        },
    )

    assert response.status_code == 404

def test_update_to_duplicate_username(
    client: TestClient,
):
    # 1. 注册用户 A
    user_a_response = client.post(
        "/users",
        json={
            "username": "duplicate_update_a",
            "password": "password123456",
        },
    )

    assert user_a_response.status_code == 200
    user_a_id = user_a_response.json()["data"]["id"]

    # 2. 注册用户 B
    user_b_response = client.post(
        "/users",
        json={
            "username": "duplicate_update_b",
            "password": "password123456",
        },
    )

    assert user_b_response.status_code == 200

    # 3. 用户 A 登录
    login_response = client.post(
        "/login",
        json={
            "username": "duplicate_update_a",
            "password": "password123456",
        },
    )

    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # 4. 用户 A 尝试使用用户 B 已经占用的用户名
    response = client.put(
        f"/users/{user_a_id}",
        headers={
            "Authorization": f"Bearer {token}",
        },
        json={
            "username": "duplicate_update_b",
        },
    )

    assert response.status_code == 400