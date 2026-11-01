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
        混合检索：向量语义检索 + BM25 关键词检索 + RRF 排名融合
        """
        if not query or not query.strip():
            return []

        if self.collection.count() == 0:
            return []

        from rag.embedding_client import embedding_client
        from database import SessionLocal
        from models import Article
        from rank_bm25 import BM25Okapi
        import jieba

        # 1. 生成问题向量
        query_vector = embedding_client.get_embedding(query)

        if not query_vector:
            return []

        # 2. 按用户权限获取向量检索结果
        permission_filter = {
            "$or": [
                {"is_public": True},
                {"user_id": int(user_id)}
            ]
        }

        vector_results = self.collection.query(
            query_embeddings=[query_vector],
            n_results=min(top_k * 10, self.collection.count()),
            where=permission_filter,
            include=["documents", "metadatas"]
        )

        vector_documents = vector_results["documents"][0] or []
        vector_metadatas = vector_results["metadatas"][0] or []
        vector_ids = vector_results["ids"][0] or []

        # 3. 获取有权限的全部文本块，供 BM25 检索
        all_results = self.collection.get(
            where=permission_filter,
            include=["documents", "metadatas"]
        )

        all_documents = all_results["documents"] or []
        all_metadatas = all_results["metadatas"] or []
        all_ids = all_results["ids"] or []

        # 4. 检查文章是否存在、是否删除、用户是否有权限
        db = SessionLocal()

        try:
            valid_candidates = {}
            article_cache = {}

            for item_id, text, metadata in zip(
                all_ids,
                all_documents,
                all_metadatas
            ):
                if not text:
                    continue

                metadata = metadata or {}
                article_id = metadata.get("article_id")

                if article_id is None:
                    continue

                if article_id not in article_cache:
                    article_cache[article_id] = db.query(Article).filter(
                        Article.id == article_id,
                        Article.is_deleted == False
                    ).first()

                article = article_cache[article_id]

                if article is None:
                    continue

                is_public = metadata.get("is_public", False)

                if not is_public and article.user_id != int(user_id):
                    continue

                valid_candidates[item_id] = {
                    "text": text,
                    "article_id": article_id
                }

        finally:
            db.close()

        if not valid_candidates:
            return []

        # 5. 建立向量检索排名
        vector_ranks = {}

        rank = 0

        for item_id in vector_ids:
            if item_id in valid_candidates and item_id not in vector_ranks:
                rank += 1
                vector_ranks[item_id] = rank

        # 6. 使用 jieba 中文分词，执行 BM25 检索
        candidate_ids = list(valid_candidates.keys())

        tokenized_query = list(jieba.cut_for_search(query))

        tokenized_docs = [
            list(jieba.cut_for_search(valid_candidates[item_id]["text"]))
            for item_id in candidate_ids
        ]

        bm25 = BM25Okapi(tokenized_docs)
        bm25_scores = bm25.get_scores(tokenized_query)

        bm25_ranks = {}

        ranked_bm25 = sorted(
            zip(candidate_ids, bm25_scores),
            key=lambda item: item[1],
            reverse=True
        )

        rank = 0

        for item_id, score in ranked_bm25:
            if score > 0:
                rank += 1
                bm25_ranks[item_id] = rank

        # 7. 使用 RRF 融合两种检索排名
        rrf_k = 60
        scored_candidates = []

        for item_id, candidate in valid_candidates.items():
            rrf_score = 0.0

            if item_id in vector_ranks:
                rrf_score += 1 / (rrf_k + vector_ranks[item_id])

            if item_id in bm25_ranks:
                rrf_score += 1 / (rrf_k + bm25_ranks[item_id])

            if rrf_score > 0:
                scored_candidates.append({
                    **candidate,
                    "rrf_score": rrf_score
                })

        # 8. 按融合分数从高到低排序
        scored_candidates.sort(
            key=lambda item: item["rrf_score"],
            reverse=True
        )

        logger.info(
            "RRF 混合检索完成，user_id=%s，候选数量=%s，返回数量=%s",
            user_id,
            len(scored_candidates),
            min(top_k, len(scored_candidates))
        )

        return scored_candidates[:top_k]

# 全局向量库实例
vector_store = ChromaVectorStore()
