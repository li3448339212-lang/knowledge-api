from rag.vector_store import vector_store
from collections import defaultdict
from uuid import uuid4
import time
import logging
import threading

logger = logging.getLogger(__name__)


def is_explicit_create_request(question: str) -> bool:
    """判断用户是否明确要求创建并保存文章。"""
    if not isinstance(question, str) or not question.strip():
        return False

    forbidden_words = [
        "不要创建",
        "不要新建",
        "禁止创建",
        "只查询",
        "只检索",
        "不要修改",
        "不要删除",
        "不要保存",
        "不保存",
        "无需保存",
        "不用保存",
        "别保存",
        "不要存入知识库",
        "不要保存到知识库",
        "不要写入知识库",
        "只需要在聊天中展示",
        "只在聊天中展示",
        "只需要展示",
        "仅展示",
        "不要存入",
        "不要入库",
    ]

    create_words = [
        "创建文章",
        "创建一篇文章",
        "创建一篇",
        "新建文章",
        "新建一篇文章",
        "新建一篇",
        "撰写文章",
        "写一篇文章",
        "写文章",
        "帮我写",
        "帮我创建",
        "帮我新建",
        "请创建",
        "请新建",
        "创建并保存",
    ]

    # 用户只是在询问创建方法，不代表要求实际创建文章
    informational_patterns = [
        "介绍一下如何创建",
        "介绍如何创建",
        "讲解如何创建",
        "如何创建文章",
        "怎么创建文章",
        "怎样创建文章",
        "如何新建文章",
        "怎么新建文章",
        "怎样新建文章",
    ]

    if any(word in question for word in informational_patterns):
        return False

    # 明确禁止操作时，优先阻止创建
    if any(word in question for word in forbidden_words):
        return False

    return any(word in question for word in create_words)


class RAGEngine:
    """
    RAG 引擎核心类
    负责协调向量检索、大模型生成以及多轮对话记忆
    """

    def __init__(self):
        # 保护共享内存数据的线程锁
        self._state_lock = threading.RLock()
        self._confirming_ids = set()
        
        # 内存中的对话历史缓存
        self.chat_history = defaultdict(list)

        # 记录每个会话最后活跃的时间
        self.chat_history_last_active = {}

        # 暂存等待用户确认的文章创建请求
        self.pending_article_confirmations = {}

        print("RAG 引擎初始化完成，已连接 ChromaDB 知识库，并开启多轮对话记忆。")

    def cleanup_expired_sessions(self):
        """清理超过 1 小时没有活动的对话会话。"""

        current_time = time.time()
        expire_seconds = 3600

        with self._state_lock:
            expired_sessions = [
                session_id
                for session_id, last_active
                in self.chat_history_last_active.items()
                if current_time - last_active > expire_seconds
            ]

            for session_id in expired_sessions:
                self.chat_history.pop(session_id, None)
                self.chat_history_last_active.pop(session_id, None)

        if expired_sessions:
            logger.info(
                "已清理 %s 个过期对话会话",
                len(expired_sessions),
            )

    def cleanup_expired_confirmations(self):
        """清理超过 10 分钟的待确认文章请求。"""

        current_time = time.time()
        expire_seconds = 600
        removed_ids = []

        with self._state_lock:
            expired_ids = [
                confirmation_id
                for confirmation_id, pending
                in self.pending_article_confirmations.items()
                if current_time - pending["created_at"] > expire_seconds
            ]

            for confirmation_id in expired_ids:
                # 正在创建文章的请求暂时不清理
                if confirmation_id not in self._confirming_ids:
                    self.pending_article_confirmations.pop(
                        confirmation_id,
                        None,
                    )
                    removed_ids.append(confirmation_id)

        if removed_ids:
            logger.info(
                "已清理 %s 个过期的文章确认请求",
                len(removed_ids),
            )

    def create_pending_confirmation(
        self,
        title: str,
        content: str,
        user_id: int,
    ) -> str:
        """保存待用户确认的文章，并返回确认编号。"""
        confirmation_id = uuid4().hex

        self.pending_article_confirmations[confirmation_id] = {
            "title": title,
            "content": content,
            "user_id": user_id,
            "created_at": time.time(),
        }

        return confirmation_id

    
    def confirm_article_creation(
        self,
        confirmation_id: str,
        user_id: int,
    ) -> str:
        """验证用户的确认请求，通过后才创建文章。"""

        if not confirmation_id or user_id is None:
            return "确认失败：确认编号或用户身份无效。"

        # 先清理其他过期请求，再验证当前请求
        self.cleanup_expired_confirmations()

        # 验证请求并抢占处理权
        with self._state_lock:
            pending = self.pending_article_confirmations.get(confirmation_id)

            if pending is None:
                return "确认失败：请求不存在、已过期或已经使用。"

            # 只能由发起请求的用户确认
            if pending["user_id"] != user_id:
                return "确认失败：你无权确认此请求。"

            # 请求超过 10 分钟后失效
            if time.time() - pending["created_at"] > 600:
                self.pending_article_confirmations.pop(confirmation_id, None)
                return "确认失败：请求已过期，请重新发起。"

            # 防止同一个请求被重复处理
            if confirmation_id in self._confirming_ids:
                return "确认失败：该请求正在处理中，请勿重复确认。"

            self._confirming_ids.add(confirmation_id)

        try:
            try:
                result = self.execute_tool(
                    "create_article",
                    {
                        "title": pending["title"],
                        "content": pending["content"],
                    },
                    user_id=user_id,
                )

            except Exception:
                logger.exception(
                    "确认创建文章失败，confirmation_id=%s，user_id=%s",
                    confirmation_id,
                    user_id,
                )

                return "创建文章失败：保存文章时发生错误，请稍后重试。"

            # execute_tool 可能捕获数据库异常并返回错误字符串
            if isinstance(result, str) and result.startswith("创建文章失败："):
                return result

            # 创建成功后删除待确认记录
            with self._state_lock:
                self.pending_article_confirmations.pop(
                    confirmation_id,
                    None,
                )

            return result

        finally:
            # 无论成功还是失败，都释放处理标记
            with self._state_lock:
                self._confirming_ids.discard(confirmation_id)

    
    
    def get_tools(self) -> list[dict]:
        """定义 Ollama 原生 Function Calling 工具。"""

        return [
            {
                "type": "function",
                "function": {
                    "name": "search_articles",
                    "description": (
                        "搜索知识库中的文章内容。"
                        "用户寻找相关资料或提出知识库问题时调用。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "搜索关键词或用户的问题",
                            },
                            "top_k": {
                                "type": "integer",
                                "description": "返回结果数量，范围 1 到 10",
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_article_detail",
                    "description": "根据文章 ID 获取文章完整内容。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "article_id": {
                                "type": "integer",
                                "description": "文章 ID",
                            },
                        },
                        "required": ["article_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_article",
                    "description": (
                        "用户明确要求创建并保存新文章时调用。"
                        "实际创建前必须经过用户确认。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {
                                "type": "string",
                                "description": "文章标题",
                            },
                            "content": {
                                "type": "string",
                                "description": "文章正文",
                            },
                        },
                        "required": ["title", "content"],
                    },
                },
            },
        ]



    
    def execute_tool(self,
        tool_name: str,
        tool_args: dict,
        user_id: int = None,
    ) -> str:
        """执行 Agent 工具操作。"""

        # 1. 搜索知识库文章
        if tool_name == "search_articles":
            if user_id is None:
                return "搜索失败：无法确认当前用户身份，请先登录。"

            query = tool_args.get("query")
            top_k = tool_args.get("top_k", 3)

            if not isinstance(query, str) or not query.strip():
                return "搜索失败：搜索关键词不能为空。"

            if not isinstance(top_k, int) or isinstance(top_k, bool):
                return "搜索失败：top_k 必须是整数。"

            if not 1 <= top_k <= 10:
                return "搜索失败：top_k 必须在 1 到 10 之间。"

            try:
                results = vector_store.search(
                    query=query.strip(),
                    user_id=user_id,
                    top_k=top_k,
                )

                if not results:
                    return "没有找到相关的文章内容。"

                return {
                    "message": "知识库搜索完成",
                    "results": [
                        {
                            "article_id": item["article_id"],
                            "rrf_score": item.get("rrf_score", 0),
                            "text": item["text"],
                        }
                        for item in results
                    ],
                }

            except Exception:
                logger.exception(
                    "Agent 搜索文章失败，user_id=%s",
                    user_id,
                )
                return "搜索失败：知识库暂时无法完成检索。"

        # 2. 查询单篇文章详情
        elif tool_name == "get_article_detail":
            if user_id is None:
                return "查询失败：无法确认当前用户身份，请先登录。"

            article_id = tool_args.get("article_id")

            if (
                not isinstance(article_id, int)
                or isinstance(article_id, bool)
                or article_id <= 0
            ):
                return "查询失败：文章 ID 必须是正整数。"

            from database import SessionLocal
            from models import Article

            from sqlalchemy import or_

            db = SessionLocal()

            try:
                article = db.query(Article).filter(
                    Article.id == article_id,
                    Article.is_deleted == False,
                    or_(
                        Article.user_id == user_id,
                        Article.is_public == True,
                    ),
                ).first()

                if article is None:
                    return "没有找到该文章，或者你没有权限查看该文章。"

                return (
                    f"文章详情："
                    f"\n文章 ID：{article.id}"
                    f"\n标题：{article.title}"
                    f"\n作者 ID：{article.user_id}"
                    f"\n正文：\n{article.content}"
                )

            except Exception:
                logger.exception(
                    "Agent 查询文章详情失败，article_id=%s，user_id=%s",
                    article_id,
                    user_id,
                )
                return "查询失败：读取文章时发生错误。"

            finally:
                db.close()

        # 3. 创建文章
        elif tool_name == "create_article":
            if user_id is None:
                return "创建文章失败：无法确认当前用户身份，请先登录。"

            title = tool_args.get("title")
            content = tool_args.get("content")

            if not isinstance(title, str) or not title.strip():
                return "创建文章失败：文章标题不能为空。"

            if len(title.strip()) > 200:
                return "创建文章失败：文章标题不能超过 200 个字符。"

            if not isinstance(content, str) or not content.strip():
                return "创建文章失败：文章内容不能为空。"

            from database import SessionLocal
            from models import Article

            db = SessionLocal()

            try:
                new_article = Article(
                    title=title.strip(),
                    content=content.strip(),
                    user_id=user_id,
                )

                db.add(new_article)
                db.commit()
                db.refresh(new_article)

                # 数据库创建成功后，单独处理向量库同步
                try:
                    from rag.text_splitter import text_splitter

                    chunks = text_splitter.split_text(
                        new_article.content
                    )

                    vector_store.update_article(
                        chunks,
                        article_id=new_article.id,
                        user_id=new_article.user_id,
                        is_public=new_article.is_public,
                    )

                except Exception as e:
                    logger.exception(
                        "文章已保存到 MySQL，但同步 ChromaDB 失败，article_id=%s",
                        new_article.id,
                    )

                    # 保存向量同步任务，交给后台 Worker 自动重试
                    try:
                        from rag.cleanup_tasks import create_vector_sync_task

                        create_vector_sync_task(
                            db,
                            new_article.id,
                            str(e),
                        )

                    except Exception:
                        logger.exception(
                            "文章已创建，但保存向量同步任务失败，article_id=%s",
                            new_article.id,
                        )

                    return (
                        f"文章《{new_article.title}》已成功创建，"
                        f"ID 为 {new_article.id}。"
                        "但知识库向量同步失败，系统已尝试创建后台补偿任务。"
                    )

                return (
                    f"文章《{new_article.title}》已成功创建，"
                    f"ID 为 {new_article.id}，并已同步至知识库！"
                )

            except Exception as e:
                db.rollback()

                logger.exception(
                    "创建文章失败，user_id=%s",
                    user_id,
                )

                return f"创建文章失败：{str(e)}"

            finally:
                db.close()

        return "未知的工具名称"


    
    def ask(
        self,
        question: str,
        session_id: str = "default",
        user_id: int = None,
    ) -> dict:
        """
        RAG + 原生 Function Calling 多步骤 Agent。
        最多执行 5 轮工具调用。
        """

        import json
        from rag.llm_client import ollama_client

        print(f"\n正在处理问题 (Session: {session_id}): {question}")

        # 1. 检查用户身份
        if user_id is None:
            return {
                "answer": "请先登录后再使用知识库检索。",
                "sources": [],
            }

        # 2. 检索知识库
        try:
            search_results = vector_store.search(
                question,
                user_id=user_id,
            )
        except Exception:
            logger.exception("RAG 检索失败，user_id=%s", user_id)
            search_results = []

        session_id = f"{user_id}:{session_id}"

        self.cleanup_expired_sessions()

        with self._state_lock:
            self.chat_history_last_active[session_id] = time.time()
            history = list(self.chat_history[session_id])

        self.cleanup_expired_confirmations()

        explicit_create = is_explicit_create_request(question)

        if not search_results and not explicit_create:
            return {
                "answer": "抱歉，当前知识库中没有找到相关信息。",
                "sources": [],
            }

        # 3. 组装 RAG 上下文和来源
        context_parts = []
        valid_sources = []
        seen_ids = set()

        for result in search_results:
            text = result.get("text", "").strip()

            if len(text) < 10:
                continue

            context_parts.append(text)

            article_id = result.get("article_id")

            if article_id and article_id not in seen_ids:
                seen_ids.add(article_id)
                valid_sources.append(article_id)

        context = "\n\n".join(context_parts)

        # 4. 查询来源文章标题
        source_details = []

        if valid_sources:
            from database import SessionLocal
            from models import Article
            from sqlalchemy import or_

            db = SessionLocal()

            try:
                articles = db.query(Article).filter(
                    Article.id.in_(valid_sources),
                    Article.is_deleted == False,
                    or_(
                        Article.is_public == True,
                        Article.user_id == user_id,
                    ),
                ).all()

                for article in articles:
                    source_details.append({
                        "article_id": article.id,
                        "title": article.title,
                        "url": f"/articles/{article.id}",
                    })

            finally:
                db.close()

        # 5. 构建历史消息
        messages = [
            {
                "role": "system",
                "content": f"""你是一个专业的知识库 Agent。

    当前用户 ID：{user_id}

    参考资料：
    {context if context else "当前没有检索到参考资料。"}

    历史对话用于理解用户的上下文。

    规则：
    1. 普通知识库问题优先使用参考资料回答。
    2. 参考资料不足时，可以调用 search_articles 搜索知识库。
    3. 用户要求读取指定文章时，可以调用 get_article_detail。
    4. 用户明确要求创建并保存文章时，必须立即调用 create_article 工具生成待确认请求，不得只用自然语言询问用户是否确认。
    5. 搜索、查询、阅读、总结已有文章时，禁止调用 create_article。
    6. 用户意图不明确时，不得创建文章。
    7. 不得编造文章内容、标题或搜索结果。
    8. 只能使用工具返回的内容作为知识库事实依据。
    9. 文章创建工具只会生成待确认请求，不代表文章已经保存。
    10. 使用中文回答用户。"""
            }
        ]

        for msg in history:
            messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })

        messages.append({
            "role": "user",
            "content": question,
        })

        # 6. 获取工具定义
        tools = self.get_tools()

        # 7. 多步骤 Agent 执行循环
        max_tool_rounds = 5
        tool_used = False
        pending_confirmation = None
        tool_errors = []
        raw_response = ""

        for round_index in range(max_tool_rounds + 1):

            try:
                message = ollama_client.chat(
                    messages=messages,
                    tools=tools,
                )

            except Exception:
                logger.exception(
                    "Agent 调用 Ollama 失败，user_id=%s",
                    user_id,
                )

                return {
                    "answer": "AI 服务暂时无法正常响应，请稍后重试。",
                    "sources": source_details,
                }

            if not isinstance(message, dict):
                return {
                    "answer": "AI 返回的数据格式不正确。",
                    "sources": [],
                }

            raw_response = message.get("content", "") or ""
            tool_calls = message.get("tool_calls") or []

            # 没有工具调用，说明模型已经生成最终回答
            if not tool_calls:
                break

            # 达到最大工具调用轮数
            if round_index >= max_tool_rounds:
                logger.warning(
                    "Agent 达到最大工具调用轮数，user_id=%s",
                    user_id,
                )
                raw_response = (
                    "本次任务执行步骤过多，已达到最大工具调用次数。"
                    "请尝试拆分问题后重新提问。"
                )
                break

            # 保存模型的工具调用消息
            messages.append({
                "role": "assistant",
                "content": raw_response,
                "tool_calls": tool_calls,
            })

            # 8. 执行本轮所有工具调用
            for tool_call in tool_calls:

                tool_name = "unknown"
                function_data = tool_call.get("function", {})
                if not isinstance(function_data, dict):
                    tool_result = "工具调用格式错误。"

                else:
                    tool_name = function_data.get("name")
                    tool_args = function_data.get("arguments", {})

                    if isinstance(tool_args, str):
                        try:
                            tool_args = json.loads(tool_args)
                        except json.JSONDecodeError:
                            tool_args = None

                    if not isinstance(tool_args, dict):
                        tool_result = "工具参数格式错误，无法执行。"

                    elif tool_name not in {
                        "search_articles",
                        "get_article_detail",
                        "create_article",
                    }:
                        tool_result = "不支持该工具，未执行任何操作。"

                    elif tool_name == "create_article":

                        # 再次检查用户是否明确要求创建文章
                        if not explicit_create:
                            tool_result = (
                                "用户没有明确要求创建并保存文章，"
                                "因此拒绝创建操作。"
                            )

                        else:
                            title = tool_args.get("title")
                            content = tool_args.get("content")

                            if (
                                not isinstance(title, str)
                                or not title.strip()
                                or len(title.strip()) > 200
                                or not isinstance(content, str)
                                or not content.strip()
                            ):
                                tool_result = "文章标题或正文无效，未创建待确认请求。"

                            else:
                                confirmation_id = self.create_pending_confirmation(
                                    title=title.strip(),
                                    content=content.strip(),
                                    user_id=user_id,
                                )

                                pending_confirmation = {
                                    "confirmation_id": confirmation_id,
                                    "title": title.strip(),
                                    "content": content.strip(),
                                }

                                tool_result = (
                                    "文章内容已生成待确认请求，尚未保存到数据库。"
                                    f"\n标题：{title.strip()}"
                                    f"\n确认编号：{confirmation_id}"
                                    "\n请等待用户检查并确认。"
                                )

                        tool_used = True

                    else:
                        logger.info(
                            "Agent 正在执行工具：%s，参数：%s",
                            tool_name,
                            tool_args,
                        )

                        tool_result = self.execute_tool(
                            tool_name,
                            tool_args,
                            user_id=user_id,
                        )

                    tool_used = True

                # 记录工具执行错误
                if (
                    isinstance(tool_result, str)
                    and tool_result.startswith(("搜索失败：", "查询失败："))
                ):
                    tool_errors.append(tool_result)

                # 提取搜索结果中的文章信息，统一来源格式并去重
                if (
                    tool_name == "search_articles"
                    and isinstance(tool_result, dict)
                ):
                    for item in tool_result.get("results", []):
                        if not isinstance(item, dict):
                            continue

                        article_id = item.get("article_id")

                        if article_id is None:
                            continue

                        # 同时检查新旧两种字段，避免重复添加
                        exists = any(
                            source.get("article_id", source.get("id")) == article_id
                            for source in source_details
                        )

                        if not exists:
                            source_details.append({
                                "article_id": article_id,
                                "title": f"文章 {article_id}",
                                "url": f"/articles/{article_id}",
                            })

                # 将工具结果转换为 JSON 字符串，再返回给模型
                if isinstance(tool_result, (dict, list)):
                    tool_content = json.dumps(
                        tool_result,
                        ensure_ascii=False,
                    )
                else:
                    tool_content = str(tool_result)

                messages.append({
                    "role": "tool",
                    "tool_name": tool_name,
                    "content": tool_content,
                })

        # 9. 整理最终回答
        answer = raw_response.strip()

        if not answer:
            answer = "本次任务没有生成有效回答，请重新尝试。"

        # 如果创建文章已生成待确认请求，明确展示确认信息
        if pending_confirmation is not None:
            answer = (
                "AI 已生成一篇待确认的文章，尚未创建到数据库。\n"
                f"标题：{pending_confirmation['title']}\n"
                f"确认编号：{pending_confirmation['confirmation_id']}\n"
                "请先检查文章内容，再通过确认接口决定是否创建。"
            )

        # 10. 保存对话历史
        with self._state_lock:
            self.chat_history[session_id].append({
                "role": "user",
                "content": question,
            })

            self.chat_history[session_id].append({
                "role": "assistant",
                "content": answer,
            })

            self.chat_history[session_id] = (
                self.chat_history[session_id][-10:]
            )

        # 11. 筛选最终来源
        final_sources = []

        if (
            "暂无相关信息" not in answer
            and "抱歉" not in answer
        ):
            if tool_used:
                # Agent 使用工具时，保留工具搜索到的来源
                final_sources = source_details.copy()

            else:
                # 普通 RAG 问答沿用原来的来源匹配逻辑
                context_article_ids = {
                    source["article_id"]
                    for source in source_details
                }

                retrieved_article_ids = {
                    item.get("article_id")
                    for item in search_results
                    if item.get("article_id") is not None
                }

                matched_article_ids = (
                    context_article_ids & retrieved_article_ids
                )

                final_sources = [
                    source
                    for source in source_details
                    if source["article_id"] in matched_article_ids
                ]

        # 12. 返回结果
        result = {
            "answer": answer,
            "sources": final_sources,
        }

        if pending_confirmation is not None:
            result["pending_confirmation"] = pending_confirmation

        if tool_errors:
            result["tool_errors"] = tool_errors

        return result



# 全局引擎实例
rag_engine = RAGEngine()