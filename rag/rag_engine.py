from rag.vector_store import vector_store
from collections import defaultdict
from uuid import uuid4
import time



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
        "新建文章",
        "撰写文章",
        "写一篇文章",
        "写文章",
        "帮我写",
        "帮我创建",
        "创建并保存",
    ]

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
        # 内存中的对话历史缓存
        self.chat_history = defaultdict(list)

        # 暂存等待用户确认的文章创建请求
        self.pending_article_confirmations = {}
        print("RAG 引擎初始化完成，已连接 ChromaDB 知识库，并开启多轮对话记忆。")

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

        # 执行前先删除待确认记录，防止同一编号被重复使用
        self.pending_article_confirmations.pop(confirmation_id, None)

        return self.execute_tool(
            "create_article",
            {
                "title": pending["title"],
                "content": pending["content"],
            },
            user_id=user_id,
        )

    def get_tools(self) -> list[dict]:
        """定义 AI 可以使用的工具（Function Calling）"""
        return [
            {
                "name": "create_article",
                "description": "当用户要求创建、编写、发布一篇文章时，调用此工具。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "文章的标题"
                        },
                        "content": {
                            "type": "string",
                            "description": "文章的正文内容"
                        }
                    },
                    "required": ["title", "content"]
                }
            }
        ]

    def execute_tool(self, tool_name: str, tool_args: dict, user_id: int = None) -> str:
        """执行具体的工具操作"""
        if tool_name == "create_article":
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
                    title=tool_args["title"],
                    content=tool_args["content"],
                    user_id=user_id
                )

                db.add(new_article)
                db.commit()
                db.refresh(new_article)

                # 数据库创建成功后，单独处理向量库同步
                try:
                    from rag.text_splitter import text_splitter

                    chunks = text_splitter.split_text(new_article.content)
                    vector_store.update_article(
                        chunks,
                        article_id=new_article.id,
                        user_id=new_article.user_id,
                        is_public=new_article.is_public
                    )
                except Exception as e:
                    print(
                        f"警告：文章 ID {new_article.id} 已保存到 MySQL，"
                        f"但同步 ChromaDB 失败：{e}"
                    )
                    return (
                        f"文章《{new_article.title}》已创建，"
                        f"ID 为 {new_article.id}，但知识库同步失败。"
                    )

                return (
                    f"文章《{new_article.title}》已成功创建，"
                    f"ID 为 {new_article.id}，并已同步至知识库！"
                )

            except Exception as e:
                db.rollback()
                return f"创建文章失败：{str(e)}"
            finally:
                db.close()
        return "未知的工具名称"

    def ask(self, question: str, session_id: str = "default", user_id: int = None) -> dict:
        """
        核心问答方法：检索 + 记忆 + 生成 + 代码级精准来源过滤 + 工具调用
        """
        print(f"\n正在处理问题 (Session: {session_id}): {question}")

        # 1. 检索
        if user_id is None:
            return {
                "answer": "请先登录后再使用知识库检索。",
                "sources": []
            }


        search_results = vector_store.search(
            question,
            user_id=user_id
        )
        session_id = f"{user_id}:{session_id}"

        # 没有检索结果时，普通问答直接返回；
        # 明确要求创建文章时，继续调用大模型生成待确认请求。
        if not search_results:
            if not is_explicit_create_request(question):
                return {
                    "answer": "抱歉，当前知识库中没有找到相关信息。",
                    "sources": []
                }

            search_results = []


        # 2. 组装上下文 & 收集来源
        context_parts = []
        valid_sources = []
        seen_ids = set()

        for result in search_results:
            text = result.get("text", "").strip()
            if len(text) < 10:
                continue

            context_parts.append(text)
            aid = result.get("article_id")
            if aid and aid not in seen_ids:
                seen_ids.add(aid)
                valid_sources.append(aid)

        if not context_parts:
            if not is_explicit_create_request(question):
                return {
                    "answer": "抱歉，当前知识库中没有找到相关信息。",
                    "sources": []
                }

        context = "\n\n".join(context_parts)

        # 3. 从数据库查出文章标题
        source_details = []
        if valid_sources:
            from database import SessionLocal
            from models import Article
            db = SessionLocal()
            try:
                articles = db.query(Article).filter(
                    Article.id.in_(valid_sources),
                    Article.is_deleted == False
                ).all()
                for art in articles:
                    source_details.append({
                        "article_id": art.id,
                        "title": art.title,
                        "url": f"/articles/{art.id}"
                    })
            finally:
                db.close()

        # 4. 格式化历史对话
        history_text = ""
        if self.chat_history[session_id]:
            history_lines = []
            for msg in self.chat_history[session_id]:
                role = "用户" if msg["role"] == "user" else "AI助手"
                history_lines.append(f"{role}: {msg['content']}")
            history_text = "\n".join(history_lines)

        # 5. 构建包含历史记忆的提示词
        prompt = f"""你是一个专业的知识助手。请严格根据以下参考资料和历史对话回答问题。

参考资料：
{context}

历史对话：
{history_text if history_text else "无"}

用户最新问题：{question}

要求：
1. 仅根据参考资料回答，绝对不要使用你自己的外部知识。
2. 结合历史对话理解用户的最新问题（例如代词"它"指的是什么）。
3. 如果参考资料不足以回答问题，请直接回复："知识库中暂无相关信息"。
4. 直接给出答案，不要提及"根据参考资料"等废话。"""

        # 6. 调用大模型（支持工具调用）
        from rag.llm_client import ollama_client
        import json

        # 获取当前允许使用的工具定义
        tools = self.get_tools()

        # 先让大模型判断是否需要调用工具
        tools_prompt = f"""你是一个专业的知识库问答助手。请严格遵守以下规则：
        1. 普通问答仅根据参考资料回答，不使用外部知识。
        2. 结合历史对话理解用户的最新问题。
        3. 如果参考资料不足以回答问题，回复："知识库中暂无相关信息"。
        4. 普通回答直接给出答案，不要提及"根据参考资料"等废话。
        5. 只有在用户明确要求创建并保存文章时，才可以提出 create_article 工具调用。

你可以使用以下工具：
{json.dumps(tools, ensure_ascii=False, indent=2)}

必须严格遵守以下规则：
1. 只有当用户明确要求新建、创建或撰写文章，并希望保存到知识库时，才可以调用 create_article。
2. 搜索、查询、检索、查看、核实或列出已有文章时，绝对不能调用 create_article。
3. 用户明确要求只查询、不要创建、不要修改或不要删除时，不能调用工具。
4. 用户要求总结已有文章时，不能调用 create_article。
5. 用户意图不明确时，不得调用 create_article，应先询问用户。
6. 需要创建文章时，只能返回合法 JSON：
{{"tool_call": {{"name": "create_article", "arguments": {{"title": "文章标题", "content": "文章正文"}}}}}}
7. 不需要调用工具时，直接用中文回答，不要返回 JSON。
"""

        full_prompt = f"{tools_prompt}\n\n参考资料：\n{context}\n\n历史对话：\n{history_text if history_text else '无'}\n\n用户最新问题：{question}"

        raw_response = ollama_client.generate(full_prompt)

        # 检查大模型是否返回了工具调用指令
        answer = raw_response
        final_sources = []
        tool_used = False


        try:
            response_json = json.loads(raw_response)

            if isinstance(response_json, dict) and "tool_call" in response_json:
                tool_call = response_json["tool_call"]

                if not isinstance(tool_call, dict):
                    answer = "工具调用格式不正确，未执行任何操作。"

                elif tool_call.get("name") != "create_article":
                    answer = "暂不支持该工具，未执行任何操作。"

                else:
                    tool_args = tool_call.get("arguments", {})

                    if not isinstance(tool_args, dict):
                        answer = "工具参数格式不正确，未执行任何操作。"

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
                            answer = "文章标题或正文无效，未执行创建操作。"

                        elif not is_explicit_create_request(question):
                            # 用户没有明确要求创建并保存时，拒绝工具调用
                            answer = "本次请求未明确要求创建文章，因此没有执行创建操作。"

                        else:
                            print("AI 提出了创建文章请求，等待用户确认。")

                            confirmation_id = self.create_pending_confirmation(
                                title=title.strip(),
                                content=content.strip(),
                                user_id=user_id,
                            )

                            answer = (
                                "AI 已生成一篇待确认的文章，尚未创建到数据库。\n"
                                f"标题：{title.strip()}\n"
                                f"确认编号：{confirmation_id}\n"
                                "请先检查文章内容，再通过确认接口决定是否创建。"
                            )

                            tool_used = True
                            pending_confirmation = {
                                "confirmation_id": confirmation_id,
                                "title": title.strip(),
                                "content": content.strip(),
                            }

        except json.JSONDecodeError:
            # 大模型返回的不是 JSON，按普通回答处理
            pass


        # 7. 存入记忆
        self.chat_history[session_id].append({"role": "user", "content": question})
        self.chat_history[session_id].append({"role": "assistant", "content": answer})
        self.chat_history[session_id] = self.chat_history[session_id][-10:]

        # 8. 代码级精准过滤（仅对非工具调用的回答生效）
        if "暂无相关信息" not in answer and "抱歉" not in answer and not tool_used:
            import jieba
            query_words = [w for w in jieba.cut(question) if len(w) > 1 and w not in ["什么", "怎么", "如何", "哪些", "请问"]]
            for result in search_results:
                text = result.get("text", "")
                aid = result.get("article_id")
                if query_words and any(word in text for word in query_words):
                    for s in source_details:
                        if s["article_id"] == aid and s not in final_sources:
                            final_sources.append(s)

        result = {
            "answer": answer,
            "sources": final_sources
        }

        if "pending_confirmation" in locals():
            result["pending_confirmation"] = pending_confirmation

        return result


# 全局引擎实例
rag_engine = RAGEngine()
