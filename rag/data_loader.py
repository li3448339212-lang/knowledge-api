import sys
import os

# 解决模块导入路径问题
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from database import SessionLocal
from models import Article
from rag.text_splitter import text_splitter
from rag.vector_store import vector_store

def load_articles_to_vector_store():
    """
    从 MySQL 数据库中读取所有文章，切分后存入向量库
    """
    db = SessionLocal()
    try:
        articles = db.query(Article).filter(
            Article.is_deleted == False
        ).all()

        if not articles:
            print("⚠️ 数据库中没有文章，跳过加载。")
            return

        print(f"📖 从数据库读取到 {len(articles)} 篇文章，正在处理...")

        # 【修改】：逐篇加载，并绑定 article.id
        for article in articles:
            full_text = f"{article.title}\n{article.content}"
            chunks = text_splitter.split_text(full_text)
            if chunks:
                vector_store.update_article(
                    chunks,
                    article_id=article.id,
                    user_id=article.user_id,
                    is_public=article.is_public
                )

    except Exception as e:
        print(f"❌ 加载文章失败: {e}")
    finally:
        db.close()
if __name__ == "__main__":
    load_articles_to_vector_store()