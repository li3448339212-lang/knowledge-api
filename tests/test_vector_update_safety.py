
import pytest
from unittest.mock import patch

from rag.vector_store import vector_store
from rag.embedding_client import embedding_client


def test_failed_embedding_keeps_old_vectors():
    # 模拟第一个文本块成功，第二个文本块失败
    with patch.object(
        embedding_client,
        "get_embedding",
        side_effect=[[0.1, 0.2], []],
    ):
        # 记录删除方法和写入方法是否被调用
        with patch.object(
            vector_store,
            "delete_by_article_id",
        ) as mock_delete:
            with patch.object(
                vector_store.collection,
                "upsert",
            ) as mock_upsert:

                # 应当抛出 ValueError
                with pytest.raises(
                    ValueError,
                    match="文章向量生成失败",
                ):
                    vector_store.update_article(
                        texts=["测试文本一", "测试文本二"],
                        article_id=999999,
                        user_id=1,
                    )

                # 生成失败时，不允许删除旧向量
                mock_delete.assert_not_called()

                # 生成失败时，不允许写入新向量
                mock_upsert.assert_not_called()

def test_empty_texts_delete_old_vectors():
    with patch.object(
        vector_store,
        "delete_by_article_id",
    ) as mock_delete:
        with patch.object(
            vector_store.collection,
            "upsert",
        ) as mock_upsert:
            vector_store.update_article(
                texts=[],
                article_id=999999,
                user_id=1,
            )

            mock_delete.assert_called_once_with(999999)
            mock_upsert.assert_not_called()


def test_successful_embedding_replaces_old_vectors():
    with patch.object(
        embedding_client,
        "get_embedding",
        side_effect=[[0.1, 0.2], [0.3, 0.4]],
    ):
        with patch.object(
            vector_store.collection,
            "get",
            return_value={
                "ids": [],
                "documents": [],
                "embeddings": [],
                "metadatas": [],
            },
        ):
            with patch.object(
                vector_store.collection,
                "upsert",
            ) as mock_upsert:
                with patch.object(
                    vector_store.collection,
                    "delete",
                ) as mock_delete:
                    vector_store.update_article(
                        texts=["测试文本一", "测试文本二"],
                        article_id=999999,
                        user_id=1,
                        is_public=True,
                    )

    mock_upsert.assert_called_once_with(
        ids=[
            "article_999999_chunk_0",
            "article_999999_chunk_1",
        ],
        documents=["测试文本一", "测试文本二"],
        embeddings=[
            [0.1, 0.2],
            [0.3, 0.4],
        ],
        metadatas=[
            {
                "article_id": 999999,
                "user_id": 1,
                "is_public": True,
            },
            {
                "article_id": 999999,
                "user_id": 1,
                "is_public": True,
            },
        ],
    )

    # 没有旧数据时，不应该额外删除数据
    mock_delete.assert_not_called()



def test_upsert_failure_restores_old_vectors():
    old_embedding = [[0.5, 0.6]]

    with patch.object(
        embedding_client,
        "get_embedding",
        return_value=[0.1, 0.2],
    ):
        with patch.object(
            vector_store.collection,
            "get",
            return_value={
                "ids": ["article_999999_chunk_0"],
                "documents": ["旧文章内容"],
                "embeddings": old_embedding,
                "metadatas": [
                    {
                        "article_id": 999999,
                        "user_id": 1,
                        "is_public": False,
                    }
                ],
            },
        ):
            with patch.object(
                vector_store.collection,
                "upsert",
                side_effect=[
                    RuntimeError("模拟向量写入失败"),
                    None,
                ],
            ) as mock_upsert:
                with patch.object(
                    vector_store.collection,
                    "delete",
                ) as mock_delete:
                    with pytest.raises(
                        RuntimeError,
                        match="模拟向量写入失败",
                    ):
                        vector_store.update_article(
                            texts=["新文章内容"],
                            article_id=999999,
                            user_id=1,
                        )

    # 第一次写入新数据失败，第二次调用用于恢复旧数据
    assert mock_upsert.call_count == 2

    # 旧 ID 与新 ID 相同，不应该被当作额外数据删除
    mock_delete.assert_not_called()

    # 验证第二次调用确实尝试恢复旧文章
    restored_call = mock_upsert.call_args_list[1]
    assert restored_call.kwargs["ids"] == [
        "article_999999_chunk_0"
    ]
    assert restored_call.kwargs["documents"] == ["旧文章内容"]


def test_rollback_failure_raises_clear_error():
    with patch.object(
        embedding_client,
        "get_embedding",
        return_value=[0.1, 0.2],
    ):
        with patch.object(
            vector_store.collection,
            "get",
            return_value={
                "ids": ["article_999999_chunk_0"],
                "documents": ["旧文章内容"],
                "embeddings": [[0.5, 0.6]],
                "metadatas": [
                    {
                        "article_id": 999999,
                        "user_id": 1,
                        "is_public": False,
                    }
                ],
            },
        ):
            # 第一次调用模拟新向量写入失败，
            # 第二次调用模拟旧向量恢复失败。
            with patch.object(
                vector_store.collection,
                "upsert",
                side_effect=[
                    RuntimeError("模拟新向量写入失败"),
                    RuntimeError("模拟旧向量恢复失败"),
                ],
            ):
                with pytest.raises(
                    RuntimeError,
                    match="回滚失败",
                ):
                    vector_store.update_article(
                        texts=["新文章内容"],
                        article_id=999999,
                        user_id=1,
                    )


def test_successful_update_deletes_extra_old_chunks():
    with patch.object(
        embedding_client,
        "get_embedding",
        side_effect=[[0.1, 0.2], [0.3, 0.4]],
    ):
        with patch.object(
            vector_store.collection,
            "get",
            return_value={
                "ids": [
                    "article_999999_chunk_0",
                    "article_999999_chunk_1",
                    "article_999999_chunk_2",
                ],
                "documents": [
                    "旧文本一",
                    "旧文本二",
                    "旧文本三",
                ],
                "embeddings": [
                    [0.5, 0.6],
                    [0.7, 0.8],
                    [0.9, 1.0],
                ],
                "metadatas": [
                    {
                        "article_id": 999999,
                        "user_id": 1,
                        "is_public": False,
                    }
                    for _ in range(3)
                ],
            },
        ):
            with patch.object(
                vector_store.collection,
                "upsert",
            ) as mock_upsert:
                with patch.object(
                    vector_store.collection,
                    "delete",
                ) as mock_delete:
                    vector_store.update_article(
                        texts=["新文本一", "新文本二"],
                        article_id=999999,
                        user_id=1,
                    )

    mock_upsert.assert_called_once()

    mock_delete.assert_called_once_with(
        ids=["article_999999_chunk_2"]
    )


def test_read_old_vectors_failure_does_not_write_or_delete():
    with patch.object(
        embedding_client,
        "get_embedding",
        return_value=[0.1, 0.2],
    ):
        with patch.object(
            vector_store.collection,
            "get",
            side_effect=RuntimeError("模拟读取旧向量失败"),
        ):
            with patch.object(
                vector_store.collection,
                "upsert",
            ) as mock_upsert:
                with patch.object(
                    vector_store.collection,
                    "delete",
                ) as mock_delete:
                    with pytest.raises(
                        RuntimeError,
                        match="模拟读取旧向量失败",
                    ):
                        vector_store.update_article(
                            texts=["新文章内容"],
                            article_id=999999,
                            user_id=1,
                        )

    mock_upsert.assert_not_called()
    mock_delete.assert_not_called()


def test_cleanup_extra_old_chunks_failure_is_reported():
    with patch.object(
        embedding_client,
        "get_embedding",
        side_effect=[[0.1, 0.2]],
    ):
        with patch.object(
            vector_store.collection,
            "get",
            return_value={
                "ids": [
                    "article_999999_chunk_0",
                    "article_999999_chunk_1",
                ],
                "documents": ["旧文本一", "旧文本二"],
                "embeddings": [
                    [0.5, 0.6],
                    [0.7, 0.8],
                ],
                "metadatas": [
                    {
                        "article_id": 999999,
                        "user_id": 1,
                        "is_public": False,
                    }
                    for _ in range(2)
                ],
            },
        ):
            with patch.object(
                vector_store.collection,
                "upsert",
            ) as mock_upsert:
                with patch.object(
                    vector_store.collection,
                    "delete",
                    side_effect=RuntimeError("模拟清理失败"),
                ) as mock_delete:
                    with pytest.raises(
                        RuntimeError,
                        match="模拟清理失败",
                    ):
                        vector_store.update_article(
                            texts=["新文本一"],
                            article_id=999999,
                            user_id=1,
                        )

    # 第一次 upsert 写入新向量，第二次 upsert 恢复旧向量
    assert mock_upsert.call_count == 2

    # 第一次删除多余旧向量失败，回滚时第二次删除也失败
    assert mock_delete.call_count == 1
