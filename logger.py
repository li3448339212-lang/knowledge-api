
import logging
import os
from logging.handlers import RotatingFileHandler

# 获取当前项目目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 创建日志目录
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# 日志文件路径
LOG_FILE = os.path.join(LOG_DIR, "app.log")

# 日志格式
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"

# 控制台日志
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(LOG_FORMAT))

# 文件日志：单个文件最多 5 MB，保留 3 个备份
file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8"
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter(LOG_FORMAT)

)

# 配置根日志记录器
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# 避免重复添加处理器
if not any(
    isinstance(handler, RotatingFileHandler)
    and getattr(handler, "baseFilename", None)
    == os.path.abspath(LOG_FILE)
    for handler in root_logger.handlers
):
    root_logger.addHandler(file_handler)

if not any(
    isinstance(handler, logging.StreamHandler)
    and not isinstance(handler, RotatingFileHandler)
    for handler in root_logger.handlers
):
    root_logger.addHandler(console_handler)

logger = logging.getLogger(__name__)