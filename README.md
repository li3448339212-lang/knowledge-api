# Knowledge API

基于 FastAPI 构建的智能知识库管理与 RAG 问答系统，集成用户认证、文章管理、权限控制、Redis 缓存、向量检索和大语言模型问答能力。

项目使用 MySQL 存储业务数据，使用 ChromaDB 存储文章向量，通过 Ollama 提供本地 Embedding 和大语言模型服务，并支持 Docker Compose 部署。

## 一、项目介绍

本项目是一个个人学习与实践项目，目标是构建一个具备完整后端业务能力和 RAG 知识库问答能力的应用。

主要功能包括：

### 1. 用户与文章管理
- 用户注册、登录和个人信息管理
- 基于 JWT 的身份认证
- 基于用户角色的权限控制
- 文章创建、查询、更新和删除
- 文章软删除与恢复
- 文章列表分页、关键词搜索和排序
- 文章点赞、收藏和评论
- 文章浏览记录和浏览量统计

### 2. 缓存与数据库管理
- Redis 文章详情缓存
- SQLAlchemy ORM 数据库操作
- Alembic 数据库迁移
- 数据库事务管理
- 自定义异常处理和日志记录

### 3. RAG 知识库问答
- 将文章内容切分为文本块
- 使用 Embedding 模型生成文本向量
- 将向量存储到 ChromaDB
- 根据用户问题进行向量相似度检索
- 将检索结果提供给大语言模型生成回答
- 返回答案及相关来源文章

### 4. 向量数据可靠性
- 文章向量更新
- 文章删除后的向量清理
- 向量清理失败后的补偿任务
- 向量同步失败后的补偿任务
- 后台定时处理待重试任务
- 使用任务状态和租约机制管理任务执行

## 二、技术栈

| 技术 | 用途 |
|---|---|
| Python 3.13 | 后端开发语言 |
| FastAPI | Web API 框架 |
| MySQL | 关系型数据库 |
| SQLAlchemy | ORM 与数据库操作 |
| Pydantic | 请求参数验证与响应建模 |
| JWT | 用户身份认证 |
| Passlib / bcrypt | 密码哈希与验证 |
| Redis | 文章缓存 |
| Alembic | 数据库结构迁移 |
| ChromaDB | 向量数据库 |
| Ollama | 本地模型服务 |
| nomic-embed-text | 文本 Embedding 模型 |
| Qwen 系列模型 | 本地大语言模型 |
| Uvicorn | ASGI 应用服务器 |
| Docker | 应用容器化 |
| Docker Compose | 容器编排与部署 |
| Pytest | 自动化测试 |

## 三、项目目录结构

```text
knowledge-api/
├── main.py
├── config.py
├── database.py
├── models.py
├── schemas.py
├── security.py
├── exceptions.py
├── logger.py
├── redis_client.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── .env.example
├── .gitignore
├── README.md
│
├── routers/
│   ├── users.py
│   ├── articles.py
│   └── ...
│
├── services/
│   └── article_service.py
│
├── rag/
│   ├── embedding_client.py
│   ├── vector_store.py
│   ├── text_splitter.py
│   ├── rag_engine.py
│   └── cleanup_tasks.py
│
├── alembic/
│   ├── env.py
│   └── versions/
│
└── tests/
    ├── conftest.py
    ├── test_users.py
    ├── test_login.py
    ├── test_articles.py
    └── ...
```

实际目录以项目当前代码为准。

### 核心文件说明

- `main.py`：创建 FastAPI 应用、注册路由和异常处理器，并管理应用生命周期及后台任务。
- `config.py`：读取应用环境变量。
- `database.py`：数据库连接、SQLAlchemy 基础配置及数据库会话依赖。
- `models.py`：定义用户、文章及向量任务等数据库模型。
- `schemas.py`：定义请求参数、响应结构和数据验证规则。
- `security.py`：密码哈希、密码验证、JWT 生成与身份认证。
- `redis_client.py`：Redis 客户端配置。
- `rag/embedding_client.py`：调用 Ollama Embedding 接口生成文本向量。
- `rag/vector_store.py`：管理 ChromaDB 向量集合和文章向量。
- `rag/text_splitter.py`：文章文本切分。
- `rag/rag_engine.py`：实现 RAG 检索与问答流程。
- `rag/cleanup_tasks.py`：管理向量清理和同步补偿任务。
- `Dockerfile`：定义应用镜像构建过程。
- `docker-compose.yml`：定义应用容器运行配置。

## 四、系统架构

项目主要由以下几个部分组成：

```text
                  用户
                   |
                   v
             FastAPI API
                   |
          +--------+--------+
          |        |        |
          v        v        v
        MySQL    Redis    RAG 引擎
          |                 |
          |                 v
          |             文本切分
          |                 |
          |                 v
          |             Embedding
          |                 |
          |                 v
          |             ChromaDB
          |                 |
          |                 v
          |             相似度检索
          |                 |
          |                 v
          |             Ollama LLM
          |                 |
          +--------+--------+
                   |
                   v
                返回结果
```

MySQL 负责保存用户、文章及任务等业务数据。

Redis 负责缓存文章详情，减少重复数据库查询。

ChromaDB 负责保存文章文本向量，支持语义检索。

Ollama 提供本地 Embedding 和大语言模型服务。

## 五、RAG 工作流程

RAG（Retrieval-Augmented Generation，检索增强生成）是本项目的核心功能之一。

### 1. 知识入库

文章创建或更新后：

1. 获取文章文本。
2. 将文章切分成多个文本块。
3. 调用 Embedding 模型生成向量。
4. 将向量及文章元数据写入 ChromaDB。

### 2. 用户提问

用户提交问题后：

1. 接收用户问题。
2. 将问题转换为向量。
3. 在 ChromaDB 中检索相似文本块。
4. 获取相关知识内容。
5. 将问题和检索结果交给大语言模型。
6. 生成回答。
7. 返回回答及来源文章。

### 3. 向量同步补偿

考虑到 MySQL 和 ChromaDB 是两个独立的数据存储系统，项目增加了向量同步补偿机制。

当文章保存成功，但向量同步失败时：

- 创建待处理的向量同步任务。
- 记录任务状态和错误信息。
- 由后台任务定期重试。
- 成功后更新任务状态。
- 超过重试次数后标记为失败。

向量清理也采用类似的补偿机制，降低数据库与向量库数据不一致的风险。

## 六、环境要求

本地开发环境：

- Windows 或其他支持 Python 的操作系统
- Python 3.13
- MySQL
- Redis
- Ollama
- Docker Desktop（使用 Docker 部署时）
- VS Code 或其他 Python 开发工具

Ollama 模型需要根据项目实际配置提前下载。

项目使用过的模型包括：

```text
nomic-embed-text
qwen2.5:7b
qwen2.5:1.5b
qwen3-embedding:4b
```

当前项目默认 Embedding 模型为 `nomic-embed-text`。

## 七、环境变量配置

在项目根目录创建 `.env` 文件。

可以参考以下配置模板，具体变量应与项目当前配置保持一致：

```dotenv
# MySQL
DATABASE_URL=mysql+pymysql://用户名:密码@127.0.0.1:3306/knowledge_db

# JWT
SECRET_KEY=替换为随机生成的高强度密钥

# Redis
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_PASSWORD=替换为Redis密码

# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=nomic-embed-text

# Docker 使用的连接地址
DATABASE_URL_DOCKER=mysql+pymysql://用户名:密码@host.docker.internal:3306/knowledge_db
OLLAMA_BASE_URL_DOCKER=http://host.docker.internal:11434
```

注意：

1. 请根据实际环境修改数据库地址、用户名和密码。
2. Redis 应启用密码验证。
3. JWT 密钥应使用随机生成的高强度值。
4. 不要将真实 `.env` 文件提交到公开代码仓库。
5. 不要在日志或接口响应中暴露密码、密钥和访问令牌。
6. 数据库密码如果包含特殊字符，需要正确进行 URL 编码。

## 八、本地开发运行

### 1. 进入项目目录

```powershell
cd D:\knowledge-api
```

### 2. 创建虚拟环境

```powershell
python -m venv venv
```

如果已经创建过虚拟环境，可以跳过。

### 3. 激活虚拟环境

```powershell
.\venv\Scripts\Activate.ps1
```

### 4. 安装依赖

```powershell
python -m pip install -r requirements.txt
```

### 5. 数据库迁移

```powershell
alembic upgrade head
```

### 6. 启动项目

```powershell
python -m uvicorn main:app --reload
```

访问：

- API 根路径：`http://127.0.0.1:8000/`
- Swagger 文档：`http://127.0.0.1:8000/docs`
- OpenAPI JSON：`http://127.0.0.1:8000/openapi.json`

## 九、Docker 部署

项目已支持使用 Docker Compose 构建和启动 FastAPI 服务。

### 1. 部署前准备

需要提前准备：

- Docker Desktop
- MySQL 服务
- Redis 服务
- Ollama 服务
- 所需 Ollama 模型

当前部署方案中，MySQL、Redis 和 Ollama 运行在 Docker 容器外部，FastAPI 运行在 Docker 容器中。

### 2. 配置环境变量

在 `.env` 中填写数据库、Redis、JWT 和 Ollama 配置。

Docker 环境使用：

- `DATABASE_URL_DOCKER`
- `OLLAMA_BASE_URL_DOCKER`
- `REDIS_HOST`
- `REDIS_PASSWORD`

其中 `host.docker.internal` 用于容器访问 Windows 宿主机上的服务。

### 3. 构建镜像

```powershell
docker compose build
```

### 4. 启动容器

```powershell
docker compose up -d
```

也可以使用：

```powershell
docker compose up -d --build
```

### 5. 查看容器状态

```powershell
docker compose ps
```

### 6. 查看运行日志

```powershell
docker compose logs --tail=100 api
```

### 7. 测试 Redis 连接

```powershell
docker compose exec api python -c "from redis_client import redis_client; print(redis_client.ping())"
```

### 8. 测试 MySQL 连接

```powershell
docker compose exec api python -c "from database import engine; conn=engine.connect(); print('MySQL连接成功'); conn.close()"
```

### 9. 停止容器

```powershell
docker compose down
```

### 10. 访问 API

浏览器访问：

```text
http://127.0.0.1:8000/docs
```

项目使用本地目录映射保存 ChromaDB 数据：

```yaml
volumes:
  - ./chroma_db:/app/chroma_db
```

这样容器重新创建后，仍然可以使用宿主机中保存的向量数据。

注意：Docker Compose 的 `.env` 文件只用于运行时配置，不应打包进镜像。正式部署前还需要配置网络访问限制、HTTPS、数据备份和生产环境日志。

## 十、主要 API 功能

项目提供用户管理、文章管理和文章互动等 API。

具体路由、参数和响应格式以当前代码及 Swagger 文档为准。

### 用户管理

- 用户注册
- 用户登录
- 查询用户信息
- 更新用户信息
- 用户删除
- 管理员用户管理

### 文章管理

- 创建文章
- 查询文章列表
- 查询文章详情
- 更新文章
- 删除文章
- 查询当前用户文章
- 管理员文章管理
- 恢复已软删除文章

### 文章互动

- 点赞与取消点赞
- 收藏与取消收藏
- 评论与评论管理
- 浏览记录
- 浏览量统计

### RAG 知识库

- 文章向量化
- 知识库向量检索
- 智能问答
- 返回相关来源文章
- 向量同步补偿
- 向量清理补偿

## 十一、身份认证与权限控制

### 1. JWT 身份认证

用户登录成功后获取访问令牌。

调用需要认证的接口时，在请求头中携带：

```text
Authorization: Bearer <access_token>
```

令牌有效期由 `security.py` 中的配置决定。

### 2. 用户角色

项目使用用户角色区分普通用户和管理员。

- 普通用户只能访问权限允许的接口。
- 管理员接口通过管理员权限依赖进行验证。
- 文章更新和删除等操作需要检查文章所有权。

### 3. 文章数据隔离

创建文章时，应从已验证的当前用户信息中获取 `user_id`，而不是信任客户端提交的作者 ID。

修改或删除文章时，应验证当前用户是否拥有该文章。

## 十二、缓存与数据一致性

### Redis 缓存

项目使用 Redis 缓存文章详情，以减少重复数据库查询。

维护缓存时需要注意：

1. 文章更新后清理或更新对应缓存。
2. 文章删除或恢复后处理缓存失效。
3. Redis 不可用时，业务是否能够继续运行取决于具体服务实现。

### 向量同步与清理

MySQL 和 ChromaDB 之间的数据同步通过补偿任务处理。

主要考虑：

- 向量生成失败
- 向量写入失败
- 文章删除后的向量清理失败
- 后台任务重复执行
- 任务超过重试次数

任务状态和租约机制用于降低并发执行时的重复处理风险。

## 十三、日志与异常处理

日志模块用于记录应用运行信息和异常。

日志中不应记录：

- 明文密码
- 密码哈希
- JWT 访问令牌
- 数据库连接密码
- JWT 密钥

项目使用自定义业务异常统一处理常见错误，包括：

- `NotFoundError`
- `PermissionDeniedError`
- `BadRequestError`
- `UnauthorizedError`

常见 HTTP 状态码：

| 状态码 | 含义 |
|---|---|
| 200 | 请求成功 |
| 400 | 请求不符合业务要求 |
| 401 | 未通过身份认证 |
| 403 | 没有执行操作的权限 |
| 404 | 资源不存在 |
| 422 | 请求参数验证失败 |
| 500 | 服务器内部错误 |

## 十四、测试

项目使用 Pytest 进行自动化测试。

运行全部测试：

```powershell
pytest -v
```

运行指定测试文件：

```powershell
pytest tests/test_articles.py -v
```

建议重点测试：

- 用户注册和登录
- JWT 身份认证
- 普通用户与管理员权限
- 用户文章归属校验
- 文章创建、更新和删除
- 点赞、收藏和评论
- Redis 缓存失效
- 向量更新和删除
- 向量同步失败后的补偿
- 向量清理失败后的重试
- 任务超过重试次数后的状态处理

具体测试通过情况应以实际 Pytest 执行结果为准。

## 十五、Git 与敏感信息管理

建议在 `.gitignore` 中忽略：

```gitignore
venv/
.venv/
__pycache__/
*.py[cod]
.env
logs/
*.log
.pytest_cache/
chroma_db/
```

注意：

- 不要提交真实 `.env`。
- 不要提交数据库密码和 JWT 密钥。
- 不要将本地虚拟环境提交到仓库。
- 根据实际项目需要决定是否提交 ChromaDB 数据目录。
- 提供 `.env.example` 供其他开发者配置环境。

## 十六、项目部署验收

目前已经完成以下部署验证：

| 验收项目 | 结果 |
|---|---|
| Docker 镜像构建 | 已通过 |
| Docker Compose 启动 | 已通过 |
| FastAPI 容器运行 | 已通过 |
| Swagger 文档访问 | 已通过 |
| MySQL 连接 | 已通过 |
| Redis 密码认证 | 已通过 |
| ChromaDB 初始化 | 已通过 |
| RAG 知识库初始化 | 已通过 |
| RAG 问答请求 | 已通过 |
| 来源文章返回 | 已通过 |

以上结果来自当前开发环境的实际部署过程，不代表已经完成生产环境压力测试或全部自动化测试。

## 十七、后续改进方向

项目后续可以重点完善：

- 完成全量自动化测试与边界测试
- 优化 RAG 检索效果
- 完善向量任务监控和异常告警
- 优化数据库查询与缓存策略
- 完善数据备份和恢复方案
- 增加生产环境 HTTPS 和访问限制
- 完善日志轮转和容器健康检查
- 完善项目部署文档

## 十八、学习目标

通过这个项目，可以实践和掌握：

- Python 后端项目组织
- FastAPI 路由与依赖注入
- SQLAlchemy 数据模型和查询
- Pydantic 数据验证
- JWT 身份认证与权限控制
- MySQL 事务与关联数据管理
- Redis 缓存
- Alembic 数据库迁移
- ChromaDB 向量存储
- Embedding 文本向量化
- RAG 检索增强生成
- Ollama 本地模型调用
- 后台任务与失败补偿机制
- Docker 镜像构建和容器部署
- Pytest 自动化测试

---

**项目名称：Knowledge API**

**项目定位：基于 FastAPI、ChromaDB 和 Ollama 的智能知识库管理与 RAG 问答系统。**