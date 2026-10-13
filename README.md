# Knowledge API

基于 FastAPI、MySQL 和 Redis 开发的知识文章管理 API 项目，用于学习后端开发、RESTful API 设计、用户认证、数据库操作和权限控制。

## 一、项目介绍

本项目是一个个人学习与实践项目，主要实现用户管理和文章管理，并逐步加入文章互动、数据统计、缓存和数据库迁移等功能。

主要功能包括：

* 用户注册、登录和个人信息管理
* 基于 JWT 的身份认证
* 基于用户角色的权限控制
* 文章创建、查询、更新和删除
* 文章软删除与恢复
* 文章列表分页、关键词搜索和排序
* 文章点赞与取消点赞
* 文章收藏与取消收藏
* 文章评论与评论管理
* 文章浏览记录和浏览量统计
* Redis 文章详情缓存
* SQLAlchemy ORM 数据库操作
* Alembic 数据库迁移
* 自定义异常处理和日志记录

> 说明：以上为项目已实现或已开发的功能范围。具体功能是否在当前版本中全部正常运行，应以实际代码和测试结果为准。

## 二、技术栈

| 技术               | 用途             |
| ---------------- | -------------- |
| Python           | 后端开发语言         |
| FastAPI          | Web API 框架     |
| MySQL            | 关系型数据库         |
| SQLAlchemy       | ORM 与数据库操作     |
| Pydantic         | 请求参数验证与响应数据建模  |
| JWT              | 用户身份认证         |
| Passlib / bcrypt | 密码哈希与验证        |
| Redis            | 文章缓存           |
| Alembic          | 数据库结构迁移        |
| Uvicorn          | ASGI 应用服务器     |
| Swagger UI       | 在线 API 文档与接口调试 |

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
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/
├── routers/
│   ├── users.py
│   └── articles.py
├── services/
│   └── article_service.py
└── tests/
    ├── conftest.py
    ├── test_users.py
    ├── test_login.py
    ├── test_articles.py
    ├── test_admin.py
    ├── test_article_interactions.py
    └── test_article_service.py
```

实际目录以本地项目为准；如果存在其他文件或子目录，请保留。

### 核心文件说明

* `main.py`：创建 FastAPI 应用、注册路由、中间件和异常处理器。
* `config.py`：读取应用配置。
* `database.py`：数据库连接、SQLAlchemy 基础配置及数据库会话依赖。
* `models.py`：定义用户、文章、点赞、收藏、评论和浏览记录等数据库模型。
* `schemas.py`：定义请求参数、响应结构和数据验证规则。
* `security.py`：密码哈希、密码验证、JWT 生成与身份认证。
* `exceptions.py`：自定义业务异常及其处理器。
* `logger.py`：配置控制台和文件日志。
* `redis_client.py`：Redis 客户端配置。
* `routers/users.py`：用户相关 API。
* `routers/articles.py`：文章及互动相关 API。
* `services/article_service.py`：文章业务逻辑。
* `alembic/versions/`：数据库迁移脚本。

## 四、环境要求

开始运行前，请准备：

* Windows 系统或其他支持 Python 的操作系统
* Python 版本与项目依赖兼容
* MySQL 服务
* Redis 服务
* VS Code 或其他 Python 开发工具

项目开发过程中使用过 Python 3.13。实际运行时应以依赖安装结果为准。

## 五、安装项目

### 1. 进入项目目录

```powershell
cd D:\knowledge-api
```

### 2. 创建虚拟环境

如果项目已经有 `venv`，可以跳过创建步骤。

```powershell
python -m venv venv
```

### 3. 激活虚拟环境

```powershell
.\venv\Scripts\Activate.ps1
```

如果使用的是 Windows 命令提示符（CMD），可以运行：

```bat
venv\Scripts\activate.bat
```

### 4. 安装依赖

如果已经维护了 `requirements.txt`：

```powershell
python -m pip install -r requirements.txt
```

如果还没有依赖清单，应先根据实际项目导入情况整理并生成，不要直接假设所有依赖版本。

## 六、环境变量配置

在项目根目录创建 `.env` 文件。变量名称必须与 `config.py` 中实际读取的名称一致。

示例：

```dotenv
DATABASE_URL=mysql+pymysql://用户名:密码@127.0.0.1:3306/knowledge_db
SECRET_KEY=替换为随机生成的高强度密钥
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_DB=0
```

以上是配置示例，并不代表当前项目一定使用这些精确变量名称。请以 `config.py` 和 `redis_client.py` 的实现为准。

注意事项：

1. 将数据库用户名和密码替换为自己的配置。
2. JWT 密钥应使用足够随机且保密的值。
3. 不要将真实 `.env` 文件提交到公开代码仓库。
4. 不要在日志、接口响应或代码中暴露数据库密码和 JWT 密钥。
5. 如果数据库连接使用特殊字符作为密码，需要正确进行 URL 编码。

## 七、数据库初始化与迁移

项目使用 SQLAlchemy 管理数据库模型，并通过 Alembic 管理数据库结构变更。

### 1. 创建数据库

先在 MySQL 中创建项目使用的数据库，例如：

```sql
CREATE DATABASE knowledge_db
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;
```

如果数据库已经存在，无需重复创建。

### 2. 检查迁移状态

```powershell
alembic current
```

查看当前数据库所处的迁移版本。

### 3. 查看迁移历史

```powershell
alembic history
```

检查项目已有的迁移脚本。

### 4. 应用迁移

```powershell
alembic upgrade head
```

此命令将数据库迁移到当前迁移链的最新版本。

### 5. 生成新的迁移

修改模型后，如果确实需要调整数据库结构，可以执行：

```powershell
alembic revision --autogenerate -m "describe_schema_change"
```

生成脚本后，应先检查迁移内容，再执行：

```powershell
alembic upgrade head
```

不要在未检查自动生成脚本的情况下，直接对重要数据库执行迁移。迁移操作前应做好数据备份。

## 八、启动项目

在项目根目录并激活虚拟环境后运行：

```powershell
python -m uvicorn main:app --reload
```

如果项目使用根目录下的虚拟环境，也可以运行：

```powershell
.\venv\Scripts\python.exe -m uvicorn main:app --reload
```

默认本地地址通常为：

* API 根路径：`http://127.0.0.1:8000/`
* Swagger 文档：`http://127.0.0.1:8000/docs`
* OpenAPI JSON：`http://127.0.0.1:8000/openapi.json`

开发阶段可以使用 `--reload`。部署到生产环境时，应根据部署方案配置工作进程、日志、网络访问和安全策略。

## 九、主要 API 功能

以下为项目接口的功能分类。具体路径、请求参数和响应格式以当前代码及 Swagger 文档为准。

### 用户管理

| 方法     | 路径                       | 功能               |
| ------ | ------------------------ | ---------------- |
| POST   | `/users`                 | 创建用户             |
| GET    | `/users`                 | 查询用户列表，按实际权限限制访问 |
| GET    | `/users/{user_id}`       | 查询指定用户           |
| PUT    | `/users/{user_id}`       | 更新用户信息           |
| DELETE | `/users/{user_id}`       | 删除用户             |
| POST   | `/login`                 | 用户登录             |
| DELETE | `/admin/users/{user_id}` | 管理员删除用户          |

### 文章管理

| 方法     | 路径                                     | 功能        |
| ------ | -------------------------------------- | --------- |
| POST   | `/articles`                            | 创建文章      |
| GET    | `/articles`                            | 查询文章列表    |
| GET    | `/articles/{article_id}`               | 查询文章详情    |
| PUT    | `/articles/{article_id}`               | 更新文章      |
| DELETE | `/articles/{article_id}`               | 删除文章      |
| GET    | `/my_articles`                         | 查询当前用户的文章 |
| GET    | `/admin/articles`                      | 管理员查询文章   |
| DELETE | `/admin/articles/{article_id}`         | 管理员删除文章   |
| POST   | `/admin/articles/{article_id}/restore` | 恢复已软删除的文章 |

### 文章互动

| 方法     | 路径                                | 功能       |
| ------ | --------------------------------- | -------- |
| POST   | `/articles/{article_id}/like`     | 点赞文章     |
| DELETE | `/articles/{article_id}/like`     | 取消点赞     |
| GET    | `/articles/{article_id}/likes`    | 查询文章点赞信息 |
| POST   | `/articles/{article_id}/favorite` | 收藏文章     |
| DELETE | `/articles/{article_id}/favorite` | 取消收藏     |
| GET    | `/my_likes`                       | 查询我的点赞   |
| GET    | `/my_favorites`                   | 查询我的收藏   |
| POST   | `/articles/{article_id}/comments` | 发表评论     |
| GET    | `/articles/{article_id}/comments` | 查询文章评论   |
| DELETE | `/articles/comments/{comment_id}` | 删除自己的评论  |
| DELETE | `/admin/comments/{comment_id}`    | 管理员删除评论  |

### 浏览统计

| 方法  | 路径                                  | 功能       |
| --- | ----------------------------------- | -------- |
| GET | `/articles/{article_id}/views`      | 查询文章浏览记录 |
| GET | `/articles/{article_id}/view-stats` | 查询文章浏览统计 |

部分接口可能需要 JWT 身份认证，管理员接口还需要管理员权限。请通过 `/docs` 确认当前实际注册的接口。

## 十、身份认证与权限控制

### 1. JWT 身份认证

登录成功后，API 返回访问令牌：

```json
{
  "access_token": "实际返回的令牌",
  "token_type": "bearer"
}
```

调用需要身份认证的接口时，应在请求头中携带：

```text
Authorization: Bearer <access_token>
```

令牌有效期由 `security.py` 中的配置决定。

### 2. 用户角色

项目使用用户角色区分普通用户和管理员。

* 普通用户通过身份认证后访问允许的接口。
* 管理员接口通过 `get_admin_user` 检查角色。
* 当前用户身份和角色由数据库记录核实。
* 文章更新和删除等操作应检查文章所有权。

### 3. 文章数据隔离

用户创建文章时，应从已验证的当前用户信息中获取 `user_id`，而不是信任客户端提交的作者 ID。

修改或删除文章时，应验证当前用户是否拥有该文章，管理员操作则按相应权限规则执行。

## 十一、文章缓存

项目使用 Redis 缓存文章详情，以减少部分重复数据库查询。

缓存相关代码主要位于：

* `redis_client.py`
* `services/article_service.py`

维护缓存时需要注意：

1. 文章内容更新后应清理或更新对应缓存。
2. 文章删除或恢复后应考虑缓存失效。
3. 删除用户并连带删除文章时，应清理这些文章的缓存。
4. Redis 不可用时，业务是否能够继续运行取决于具体服务实现。
5. 如果将来新增缓存键，需要同步维护失效逻辑。

## 十二、数据库事务与数据清理

项目使用数据库事务管理多步写入操作。出现异常时，应回滚未完成的事务。

用户删除功能需要考虑关联数据，包括：

* 用户拥有的文章
* 点赞记录
* 收藏记录
* 评论记录
* 浏览记录

删除用户的文章时，也要清理其他用户与这些文章关联的数据，避免外键冲突或遗留记录。

文章软删除与用户彻底删除是不同的业务行为，应根据实际需求分别处理。

## 十三、日志与异常处理

### 日志

日志模块主要位于 `logger.py`，用于记录应用运行信息和 HTTP 请求。

日志中不应记录：

* 明文密码
* 密码哈希
* JWT 访问令牌
* 数据库连接密码
* JWT 密钥

日志目录和轮转设置应与实际配置保持一致。

### 异常处理

`exceptions.py` 定义了业务异常，包括：

* `NotFoundError`
* `PermissionDeniedError`
* `BadRequestError`
* `UnauthorizedError`

`main.py` 负责注册对应处理器，并对请求参数验证错误进行统一处理。

常见 HTTP 状态码：

| 状态码 | 含义        |
| --- | --------- |
| 200 | 请求成功      |
| 400 | 请求不符合业务要求 |
| 401 | 未通过身份认证   |
| 403 | 没有执行操作的权限 |
| 404 | 资源不存在     |
| 422 | 请求参数验证失败  |
| 500 | 服务器内部错误   |

## 十四、开发与测试建议

开发新功能时，建议遵循以下流程：

1. 在 `models.py` 中设计数据库模型。
2. 在 `schemas.py` 中定义请求和响应结构。
3. 使用 Alembic 管理数据库结构变更。
4. 在 `services/` 中实现业务逻辑。
5. 在 `routers/` 中定义 API 路由和依赖。
6. 在 `security.py` 中复用身份认证和权限依赖。
7. 在 `/docs` 中验证接口参数、响应和错误情况。
8. 对关键权限与数据删除逻辑进行测试。

优先测试以下场景：

* 未登录访问需要认证的接口。
* 普通用户访问管理员接口。
* 用户修改或删除其他用户的文章。
* 重复点赞和重复收藏。
* 查询不存在的文章。
* 删除用户时清理关联数据。
* Redis 缓存失效后重新读取文章。
* 请求参数错误时的统一响应。
* 数据库操作失败时的事务回滚。

## 十五、Git 与敏感信息

建议在 `.gitignore` 中忽略本地环境、密钥和日志，例如：

```gitignore
venv/
.venv/
__pycache__/
*.py[cod]
.env
logs/
.pytest_cache/
```

项目根目录提供了 `.env.example` 配置模板，供开发者参考并创建自己的 `.env` 文件。请在 `.env` 中填写实际的数据库连接信息和随机密钥，不要将真实密码或密钥提交到 Git 仓库。

## 十六、后续改进方向

项目可以在现有功能基础上继续完善：

* 为关键业务编写自动化测试。
* 为点赞、收藏和评论接口补充边界测试。
* 优化文章列表与互动列表的查询性能。
* 检查数据库索引和查询计划。
* 完善数据库备份与迁移回滚方案。
* 根据部署需求增加 Docker 配置。
* 配置生产环境日志、HTTPS 和访问限制。
* 完善 API 文档、版本管理与错误响应规范。

## 十七、学习目标

通过这个项目，可以逐步掌握：

* Python 后端项目的组织方式
* FastAPI 路由与依赖注入
* SQLAlchemy 数据模型和查询
* Pydantic 数据验证
* JWT 身份认证与角色授权
* MySQL 事务和关联数据管理
* Redis 缓存与缓存失效
* Alembic 数据库迁移
* 异常处理与日志配置
* RESTful API 的设计和调试

本项目主要用于学习和实践。用于生产环境前，应完成自动化测试、安全检查、部署配置和数据备份方案的验证。
