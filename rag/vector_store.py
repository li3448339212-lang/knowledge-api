import chromadb
import numpy as np
import os
import logging

logger = logging.getLogger(__name__)

class ChromaVectorStore:
    """
    基于 ChromaDB 的持久化向量数据库
    负责存储文本块、向量，并提供相似度检索及按文章ID管理的功能
    """

    def __init__(self):
        # 设置本地持久化路径，数据保存在项目根目录的 chroma_db 文件夹下
        persist_directory = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chroma_db")

        # 初始化 ChromaDB 持久化客户端
        self.client = chromadb.PersistentClient(path=persist_directory)

        # 获取或创建一个名为 "knowledge_base" 的集合（相当于表）
        # 使用 cosine 余弦相似度作为距离度量
        self.collection = self.client.get_or_create_collection(
            name="knowledge_base",
            metadata={"hnsw:space": "cosine"}
        )
        print(f"✅ ChromaDB 初始化完成，当前知识库共有 {self.collection.count()} 条记录。")

    def add_texts(
        self,
        texts: list[str],
        article_id: int,
        user_id: int,
        is_public: bool = False
    ):
        """
        批量添加文本块到 ChromaDB
        """
        if not texts:
            return

        print(f"正在向 ChromaDB 写入 {len(texts)} 个文本块...")

        # 为每个文本块生成唯一 ID
        ids = [f"article_{article_id}_chunk_{i}" for i in range(len(texts))]

        # 调用外部 Embedding 客户端生成向量
        from rag.embedding_client import embedding_client
        embeddings = [embedding_client.get_embedding(text) for text in texts]

        # 过滤掉生成失败的向量
        valid_data = [(ids[i], texts[i], embeddings[i]) for i in range(len(texts)) if embeddings[i]]

        if valid_data:
            valid_ids, valid_texts, valid_embeddings = zip(*valid_data)
            # ChromaDB 要求 metadata 的值必须是 str, int, float, bool
            metadatas = [
                {
                    "article_id": int(article_id),
                    "user_id": int(user_id),
                    "is_public": bool(is_public),
                }
                for _ in valid_ids
            ]

            self.collection.upsert(
                ids=list(valid_ids),
                documents=list(valid_texts),
                embeddings=list(valid_embeddings),
                metadatas=metadatas
            )
        print(f"✅ 成功向 ChromaDB 写入 {len(valid_data)} 个向量！")

    def delete_by_article_id(self, article_id: int):
        """
        根据文章 ID 删除该文章的所有文本块
        """
        try:
            deleted_count = self.collection.delete(
                where={"article_id": int(article_id)}
            )

            logger.info(
                "文章向量清理完成, article_id=%s",
                article_id,
            )

            return deleted_count

        except Exception:
            logger.exception(
                "文章向量清理失败, article_id=%s",
                article_id,
            )
            raise



    def update_article(
        self,
        texts: list[str],
        article_id: int,
        user_id: int,
        is_public: bool = False
    ):
        """
        安全更新文章向量：
        先备份旧数据，再写入新数据；
        写入失败时尝试恢复旧数据。
        """
        article_id = int(article_id)

        # 空文本列表表示删除文章的全部向量
        if not texts:
            self.delete_by_article_id(article_id)
            return

        from rag.embedding_client import embedding_client

        # 第一步：生成全部新向量
        embeddings = [
            embedding_client.get_embedding(text)
            for text in texts
        ]

        if any(not embedding for embedding in embeddings):
            raise ValueError("文章向量生成失败，已取消更新")

        new_ids = [
            f"article_{article_id}_chunk_{i}"
            for i in range(len(texts))
        ]

        metadatas = [
            {
                "article_id": article_id,
                "user_id": int(user_id),
                "is_public": bool(is_public),
            }
            for _ in texts
        ]

        # 第二步：读取并备份该文章的旧向量
        old_data = self.collection.get(
            where={"article_id": article_id},
            include=["documents", "embeddings", "metadatas"],
        )

        old_ids = old_data["ids"]
        old_documents = old_data["documents"] or []
        old_embeddings = old_data["embeddings"]
        old_metadatas = old_data["metadatas"] or []

        # 第三步：先尝试写入新向量，不提前删除旧数据
        try:
            self.collection.upsert(
                ids=new_ids,
                documents=texts,
                embeddings=embeddings,
                metadatas=metadatas,
            )
        except Exception as write_error:
            # 第四步：写入失败，尝试恢复旧数据
            try:
                if old_ids:
                    self.collection.upsert(
                        ids=old_ids,
                        documents=old_documents,
                        embeddings=old_embeddings.tolist()
                        if hasattr(old_embeddings, "tolist")
                        else old_embeddings,
                        metadatas=old_metadatas,
                    )

                # 清理可能已经写入的新 ID
                # 仅删除不属于原有 ID 的新记录
                extra_ids = [
                    item_id for item_id in new_ids
                    if item_id not in old_ids
                ]

                if extra_ids:
                    self.collection.delete(ids=extra_ids)

            except Exception as rollback_error:
                raise RuntimeError(
                    "向量更新失败，且回滚失败；请检查向量库数据"
                ) from rollback_error

            raise write_error

        # 第五步：新数据写入成功后，删除多余的旧文本块
        extra_old_ids = [
            item_id for item_id in old_ids
            if item_id not in new_ids
        ]

        if extra_old_ids:
            try:
                self.collection.delete(ids=extra_old_ids)

            except Exception as cleanup_error:
                try:
                    # 恢复原来的所有向量
                    if old_ids:
                        self.collection.upsert(
                            ids=old_ids,
                            documents=old_documents,
                            embeddings=old_embeddings.tolist()
                            if hasattr(old_embeddings, "tolist")
                            else old_embeddings,
                            metadatas=old_metadatas,
                        )

                    # 删除本次新增、原来不存在的向量
                    extra_new_ids = [
                        item_id for item_id in new_ids
                        if item_id not in old_ids
                    ]

                    if extra_new_ids:
                        self.collection.delete(ids=extra_new_ids)

                except Exception as rollback_error:
                    raise RuntimeError(
                        "清理旧向量失败，且回滚失败；请检查向量库数据"
                    ) from rollback_error

                raise cleanup_error


    def search(
        self,
        query: str,
        user_id: int,
        top_k: int = 3
    ) -> list[dict]:
        """
        混合检索：向量语义检索 + BM25 关键词过滤
        """
        if self.collection.count() == 0:
            return []

        from rag.embedding_client import embedding_client
        query_vector = embedding_client.get_embedding(query)
        if not query_vector:
            return []

        # 1. 先从 ChromaDB 中多捞一些候选数据（比如 10 条），作为候选池
        candidate_results = self.collection.query(
            query_embeddings=[query_vector],
            n_results=min(top_k * 3, self.collection.count()),
            where={
                "$or": [
                    {"is_public": True},
                    {"user_id": int(user_id)}
                ]
            },
            include=["documents", "metadatas"]
        )

        if not candidate_results or not candidate_results['documents']:
            return []

        # 2. 构建候选池
        candidates = []
        doc_texts = []

        # 2. 收集候选文章，并过滤已软删除的文章
        from database import SessionLocal
        from models import Article

        db = SessionLocal()
        try:
            for i in range(len(candidate_results["documents"][0])):
                text = candidate_results["documents"][0][i]
                meta = candidate_results["metadatas"][0][i]
                article_id = meta.get("article_id")

                # 查询 MySQL，确认文章存在且没有被软删除
                article = db.query(Article).filter(
                    Article.id == article_id,
                    Article.is_deleted == False
                ).first()

                if article is None:
                    continue

                candidates.append({
                    "text": text,
                    "article_id": article_id
                })
                doc_texts.append(text)
        finally:
            db.close()

        # 没有有效候选文章时，直接返回空列表
        if not candidates:
            return []


        # 3. 使用 BM25 进行关键词打分过滤
        from rank_bm25 import BM25Okapi
        import jieba  # 用于中文分词

        # 对问题和文档进行分词
        tokenized_query = list(jieba.cut_for_search(query))
        tokenized_docs = [list(jieba.cut_for_search(doc)) for doc in doc_texts]

        bm25 = BM25Okapi(tokenized_docs)
        scores = bm25.get_scores(tokenized_query)

        # 4. 将 BM25 分数与原始数据绑定，并按分数降序排序
        scored_candidates = []
        for i, score in enumerate(scores):
            # 只有当 BM25 得分大于 0（即至少包含一个有效关键词）时才保留
            if score > 0:
                candidates[i]["bm25_score"] = score
                scored_candidates.append(candidates[i])

        scored_candidates.sort(key=lambda x: x["bm25_score"], reverse=True)
        print("BM25 排序后的候选结果：", scored_candidates)

        # 5. 返回得分最高的 top_k 个结果
        return scored_candidates[:top_k]

# 全局向量库实例
vector_store = ChromaVectorStore()
