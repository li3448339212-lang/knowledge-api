import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY")
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL 未配置")

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY 未配置")