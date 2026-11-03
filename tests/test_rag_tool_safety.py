from rag.rag_engine import is_explicit_create_request

def test_readonly_question_does_not_match_create_keywords():
    """只读查询不应被判断为创建文章请求。"""
    question = (
        "请只检索知识库中已有的文章，"
        "告诉我是否存在标题为“AI工具创建测试”的文章。"
        "不要创建、修改或删除任何文章。"
    )

    forbidden_words = [
        "不要创建",
        "不要新建",
        "禁止创建",
        "只查询",
        "只检索",
        "不要修改",
        "不要删除",
    ]

    create_words = [
        "创建文章",
        "新建文章",
        "撰写文章",
        "写一篇文章",
        "写文章",
        "帮我写",
    ]

    blocked = any(word in question for word in forbidden_words)
    wants_create = any(word in question for word in create_words)

    assert blocked is True
    assert wants_create is False


from unittest.mock import patch, MagicMock
from rag.rag_engine import rag_engine


def test_readonly_question_does_not_execute_create_article():
    """只读查询即使收到错误的工具指令，也不能创建文章。"""

    question = (
        "请只检索知识库中已有的文章，"
        "告诉我是否存在标题为“AI工具创建测试”的文章。"
        "不要创建、修改或删除任何文章。"
    )

    # 模拟向量库返回一条已有文章
    search_results = [
        {
            "text": "这是一篇用于测试知识库检索的已有文章内容。",
            "article_id": 18,
        }
    ]

    # 故意模拟大模型错误地要求创建文章
    fake_tool_response = (
        '{"tool_call": {'
        '"name": "create_article", '
        '"arguments": {'
        '"title": "AI工具创建测试", '
        '"content": "这是一篇测试文章。"}'
        '}}'
    )

    # 模拟数据库中已经存在的文章
    fake_article = MagicMock()
    fake_article.id = 18
    fake_article.title = "已有测试文章"

    with (
        patch.object(
            rag_engine,
            "execute_tool",
            return_value="模拟创建成功",
        ) as mock_execute_tool,
        patch(
            "rag.rag_engine.vector_store.search",
            return_value=search_results,
        ),
        patch(
            "rag.llm_client.ollama_client.generate",
            return_value=fake_tool_response,
        ),
        patch("database.SessionLocal") as mock_session_local,
    ):
        mock_db = mock_session_local.return_value
        mock_db.query.return_value.filter.return_value.all.return_value = [
            fake_article
        ]

        result = rag_engine.ask(
            question,
            session_id="safety_test",
            user_id=999999,
        )

        # 核心安全断言：绝不能执行创建工具
        # 允许搜索知识库，但绝不能执行创建文章工具
        assert not any(
            call.args[0] == "create_article"
            for call in mock_execute_tool.call_args_list
        )


def test_explicit_create_request_can_reach_tool():
    """用户明确要求创建文章时，应允许进入工具执行分支。"""
    question = "请帮我写一篇文章，介绍 Python 的基础知识，并保存到知识库。"

    assert any(
        word in question
        for word in ["创建文章", "新建文章", "撰写文章", "写一篇文章", "写文章", "帮我写"]
    )
    assert not any(
        word in question
        for word in ["不要创建", "不要新建", "禁止创建", "只查询", "只检索", "不要修改", "不要删除"]
    )


def test_ambiguous_question_does_not_match_create_keywords():
    """用户没有明确要求创建文章时，不应匹配创建意图。"""
    question = "帮我看看 Python 基础知识。"

    create_words = [
        "创建文章",
        "新建文章",
        "撰写文章",
        "写一篇文章",
        "写文章",
        "帮我写",
    ]

    wants_create = any(word in question for word in create_words)

    assert wants_create is False


def test_real_create_intent_function():
    """验证真实的文章创建意图判断函数。"""

    # 明确要求创建文章
    assert is_explicit_create_request(
        "请帮我写一篇文章，介绍 Python 基础知识。"
    ) is True

    # 明确要求只查询
    assert is_explicit_create_request(
        "请只检索已有文章，不要创建任何文章。"
    ) is False

    # 意图不明确
    assert is_explicit_create_request(
        "帮我看看 Python 基础知识。"
    ) is False

    # 空字符串不能触发创建
    assert is_explicit_create_request("") is False

        # 要求写文章，但明确禁止保存
    assert is_explicit_create_request(
        "帮我写一篇介绍 Python 的文章，但不要保存到知识库。"
    ) is False


def test_create_article_without_user_id_is_rejected():
    """没有用户身份时，创建工具必须立即拒绝。"""
    with patch.object(rag_engine, "execute_tool", wraps=rag_engine.execute_tool) as mock_execute:
        result = mock_execute(
            "create_article",
            {
                "title": "安全测试文章",
                "content": "这篇文章不应该被创建。",
            },
            user_id=None,
        )

    assert "无法确认当前用户身份" in result


def test_confirmation_only_allows_requesting_user():
    """其他用户不能确认并创建文章。"""
    pending = {
        "title": "安全测试文章",
        "content": "这是一篇待确认的测试文章。",
        "user_id": 100,
        "created_at": __import__("time").time(),
    }

    with patch.dict(
        rag_engine.pending_article_confirmations,
        {"test-confirmation-id": pending},
        clear=False,
    ), patch.object(
        rag_engine,
        "execute_tool",
        return_value="模拟创建成功",
    ) as mock_execute:
        result = rag_engine.confirm_article_creation(
            "test-confirmation-id",
            user_id=200,
        )

        assert "无权确认" in result
        mock_execute.assert_not_called()


def test_confirmation_can_only_be_used_once():
    """同一确认编号不能重复创建文章。"""
    pending = {
        "title": "安全测试文章",
        "content": "这是一篇待确认的测试文章。",
        "user_id": 100,
        "created_at": __import__("time").time(),
    }

    with patch.dict(
        rag_engine.pending_article_confirmations,
        {"test-confirmation-once": pending},
        clear=False,
    ), patch.object(
        rag_engine,
        "execute_tool",
        return_value="模拟创建成功",
    ) as mock_execute:
        first_result = rag_engine.confirm_article_creation(
            "test-confirmation-once",
            user_id=100,
        )
        second_result = rag_engine.confirm_article_creation(
            "test-confirmation-once",
            user_id=100,
        )

        assert first_result == "模拟创建成功"
        assert "不存在" in second_result or "已经使用" in second_result
        mock_execute.assert_called_once()


def test_expired_confirmation_is_rejected():
    """超过 10 分钟的确认请求必须失效。"""
    import time

    pending = {
        "title": "过期测试文章",
        "content": "这篇文章的确认请求已经过期。",
        "user_id": 100,
        "created_at": time.time() - 601,
    }

    with patch.dict(
        rag_engine.pending_article_confirmations,
        {"test-confirmation-expired": pending},
        clear=False,
    ), patch.object(
        rag_engine,
        "execute_tool",
        return_value="模拟创建成功",
    ) as mock_execute:
        result = rag_engine.confirm_article_creation(
            "test-confirmation-expired",
            user_id=100,
        )

        assert "已过期" in result
        mock_execute.assert_not_called()
        assert (
            "test-confirmation-expired"
            not in rag_engine.pending_article_confirmations
        )


def test_explicit_create_request_requires_confirmation():
    """明确提出创建请求时，只生成待确认记录，不直接创建文章。"""
    question = "请帮我写一篇介绍 Python 基础知识的文章，并保存到知识库。"

    search_results = [
        {
            "text": "Python 是一种常用的编程语言。",
            "article_id": 18,
        }
    ]

    fake_tool_response = (
        '{"tool_call": {'
        '"name": "create_article", '
        '"arguments": {'
        '"title": "Python 基础知识", '
        '"content": "Python 是一种常用的编程语言。"}'
        '}}'
    )

    fake_article = MagicMock()
    fake_article.id = 18
    fake_article.title = "已有测试文章"

    with (
        patch.object(
            rag_engine,
            "execute_tool",
            return_value="模拟创建成功",
        ) as mock_execute_tool,
        patch(
            "rag.rag_engine.vector_store.search",
            return_value=search_results,
        ),
        patch(
            "rag.llm_client.ollama_client.chat",
            side_effect=[
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "create_article",
                                "arguments": {
                                    "title": "Python 基础知识",
                                    "content": "Python 是一种常用的编程语言。",
                                },
                            }
                        }
                    ],
                },
                {
                    "content": "文章已经生成，等待用户确认。",
                    "tool_calls": [],
                },
            ],
        ),
        patch("database.SessionLocal") as mock_session_local,
    ):
        mock_db = mock_session_local.return_value
        mock_db.query.return_value.filter.return_value.all.return_value = [
            fake_article
        ]

        result = rag_engine.ask(
            question,
            session_id="confirmation_test",
            user_id=999999,
        )

        # AI 不得直接执行真正的文章创建工具
        mock_execute_tool.assert_not_called()

        # 必须返回待用户确认的信息
        assert "pending_confirmation" in result
        pending = result["pending_confirmation"]
        assert pending["title"] == "Python 基础知识"
        assert pending["content"] == "Python 是一种常用的编程语言。"
        assert pending["confirmation_id"]

        # 待确认记录必须绑定发起请求的用户
        stored = rag_engine.pending_article_confirmations[
            pending["confirmation_id"]
        ]
        assert stored["user_id"] == 999999

        # 测试结束后清理临时待确认记录
        rag_engine.pending_article_confirmations.pop(
            pending["confirmation_id"], None
        )


def test_confirm_create_requires_authentication(client):
    """未登录用户不能调用文章确认接口。"""
    response = client.post(
        "/ai/confirm-create",
        json={
            "confirmation_id": "test-confirmation-id"
        },
    )

    assert response.status_code == 401


def test_other_user_cannot_confirm_pending_article(client, test_db):
    """用户 B 不能确认用户 A 的待创建文章。"""
    from models import User
    from security import hash_password, create_access_token

    db = test_db()
    try:
        user_a = User(
            username="confirm_user_a",
            password=hash_password("test_password_a"),
        )
        user_b = User(
            username="confirm_user_b",
            password=hash_password("test_password_b"),
        )
        db.add_all([user_a, user_b])
        db.commit()
        db.refresh(user_a)
        db.refresh(user_b)

        user_a_id = user_a.id
        user_b_id = user_b.id
    finally:
        db.close()

    confirmation_id = "test-other-user-confirmation"
    pending = {
        "title": "待确认测试文章",
        "content": "这篇文章仅用于安全测试。",
        "user_id": user_a_id,
        "created_at": __import__("time").time(),
    }

    token_b = create_access_token({"user_id": user_b_id})

    from unittest.mock import patch

    with (
        patch.dict(
            rag_engine.pending_article_confirmations,
            {confirmation_id: pending},
            clear=False,
        ),
        patch.object(
            rag_engine,
            "execute_tool",
            return_value="模拟创建成功",
        ) as mock_execute,
    ):
        response = client.post(
            "/ai/confirm-create",
            json={"confirmation_id": confirmation_id},
            headers={"Authorization": f"Bearer {token_b}"},
        )

        assert response.status_code == 400
        assert "无权确认" in response.json()["detail"]
        mock_execute.assert_not_called()

    rag_engine.pending_article_confirmations.pop(confirmation_id, None)


def test_owner_can_confirm_pending_article(client, test_db):
    """文章所属用户确认后，才允许执行创建工具。"""
    from models import User
    from security import hash_password, create_access_token
    from unittest.mock import patch

    db = test_db()
    try:
        user = User(
            username="confirm_owner",
            password=hash_password("test_password_owner"),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
    finally:
        db.close()

    confirmation_id = "test-owner-confirmation"
    pending = {
        "title": "用户确认的测试文章",
        "content": "只有用户确认后才允许创建。",
        "user_id": user_id,
        "created_at": __import__("time").time(),
    }

    token = create_access_token({"user_id": user_id})

    with (
        patch.dict(
            rag_engine.pending_article_confirmations,
            {confirmation_id: pending},
            clear=False,
        ),
        patch.object(
            rag_engine,
            "execute_tool",
            return_value="模拟创建成功",
        ) as mock_execute,
    ):
        response = client.post(
            "/ai/confirm-create",
            json={"confirmation_id": confirmation_id},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.json()["data"]["answer"] == "模拟创建成功"

        mock_execute.assert_called_once_with(
            "create_article",
            {
                "title": "用户确认的测试文章",
                "content": "只有用户确认后才允许创建。",
            },
            user_id=user_id,
        )

        # 同一编号再次使用，必须失败，不能再次创建
        second_response = client.post(
            "/ai/confirm-create",
            json={"confirmation_id": confirmation_id},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert second_response.status_code == 400
        assert mock_execute.call_count == 1

    rag_engine.pending_article_confirmations.pop(confirmation_id, None)



def test_confirm_create_returns_error_when_article_creation_fails():
    """文章创建失败时，应返回明确的失败结果。"""
    from unittest.mock import MagicMock
    import time
    engine = rag_engine

    confirmation_id = "test-create-failure"
    user_id = 1

    engine.pending_article_confirmations[confirmation_id] = {
        "user_id": user_id,
        "title": "测试文章",
        "content": "测试内容",
        "created_at": time.time(),
    }

    # 模拟文章创建失败
    original_create_article = engine.execute_tool
    engine.execute_tool = MagicMock(
        side_effect=RuntimeError("模拟数据库写入失败")
    )

    try:
        result = engine.confirm_article_creation(
            confirmation_id=confirmation_id,
            user_id=user_id,
        )

        assert "创建文章失败" in result or "确认失败" in result

    finally:
        engine.execute_tool = original_create_article
        engine.pending_article_confirmations.pop(
            confirmation_id, None
        )


def test_explicit_create_request_works_without_search_results(monkeypatch):
    """没有检索结果时，明确的创建请求仍应生成待确认记录。"""
    from rag.rag_engine import RAGEngine
    from unittest.mock import patch

    engine = RAGEngine()

    # 模拟向量检索没有找到相关内容
    monkeypatch.setattr(
        "rag.rag_engine.vector_store.search",
        lambda *args, **kwargs: [],
    )

    # 模拟大模型生成创建文章的工具调用
    responses = iter([
        {
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "create_article",
                        "arguments": {
                            "title": "测试文章",
                            "content": "这是一篇测试文章内容。",
                        },
                    }
                }
            ],
        },
        {
            "content": "文章已经生成，等待用户确认。",
            "tool_calls": [],
        },
    ])

    monkeypatch.setattr(
        "rag.llm_client.ollama_client.chat",
        lambda *args, **kwargs: next(responses),
    )

    result = engine.ask(
        "请创建文章，介绍 FastAPI 的基础知识",
        user_id=123,
    )

    assert "pending_confirmation" in result
    assert result["pending_confirmation"]["title"] == "测试文章"
    assert len(engine.pending_article_confirmations) == 1

        # 明确要求只展示，不保存到知识库
    assert is_explicit_create_request(
        "帮我写一篇介绍 Python 基础知识的文章，但不要保存到知识库，只需要在聊天中展示。"
    ) is False