"""读取环境变量配置。"""
import os

from dotenv import load_dotenv

load_dotenv()

# 数据库地址，默认使用项目目录下的 SQLite 文件。
DATABASE_URL = os.getenv("APP_DATABASE_URL", "sqlite:///./chatbot.db")
