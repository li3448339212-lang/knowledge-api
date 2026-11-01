
import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from config import DATABASE_URL
from database import Base
import models


def make_mysql_test_engine():
    """创建指向独立 MySQL 测试数据库的引擎。"""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL 未配置")

    from sqlalchemy.engine import make_url

    url = make_url(DATABASE_URL)
    test_url = url.set(database="knowledge_test_db")

    if url.get_backend_name() != "mysql":
        raise RuntimeError("当前配置不是 MySQL，已停止测试")

    return create_engine(test_url)


engine = make_mysql_test_engine()

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

def create_test_tables():
    """只在独立的 MySQL 测试数据库中创建测试表，并补齐缺失字段。"""

    # 创建尚不存在的表
    Base.metadata.create_all(bind=engine)

    # 检查测试数据库中的实际表结构
    inspector = inspect(engine)

    table_name = "vector_cleanup_tasks"

    if not inspector.has_table(table_name):
        raise RuntimeError(f"测试数据库缺少数据表：{table_name}")

    columns = {
        column["name"]
        for column in inspector.get_columns(table_name)
    }

    # 补齐 locked_at 字段
    with engine.begin() as conn:
        if "locked_at" not in columns:
            conn.execute(
                text(
                    "ALTER TABLE vector_cleanup_tasks "
                    "ADD COLUMN locked_at DATETIME NULL"
                )
            )

        # 补齐 lease_token 字段
        if "lease_token" not in columns:
            conn.execute(
                text(
                    "ALTER TABLE vector_cleanup_tasks "
                    "ADD COLUMN lease_token VARCHAR(36) NULL"
                )
            )

    # 检查并补齐 lease_token 索引
    indexes = {
        index["name"]
        for index in inspect(engine).get_indexes(table_name)
    }

    if "ix_vector_cleanup_tasks_lease_token" not in indexes:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE INDEX ix_vector_cleanup_tasks_lease_token "
                    "ON vector_cleanup_tasks (lease_token)"
                )
            )

def check_mysql_connections():
    """检查两个独立会话是否能获取不同的数据库连接。"""
    with engine.connect() as conn1:
        with engine.connect() as conn2:
            id1 = id(conn1.connection.driver_connection)
            id2 = id(conn2.connection.driver_connection)

            print("连接 1 标识：", id1)
            print("连接 2 标识：", id2)
            print("是否为不同连接：", id1 != id2)