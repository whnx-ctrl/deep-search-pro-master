"""Local application settings. Never return secrets to the browser."""
import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import URL
#集中定义基础路径，其他代码可以直接from...import 调用，避免每个文件重复拼接目录。
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')

def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {
        '1',
        'true',
        'yes',
        'on',
    }

OUTPUT = ROOT / 'output'
UPLOAD = ROOT / 'updated'
DATA = ROOT / 'data'

# 作用是把 Agent 记忆数据库固定到此数据库
CHECKPOINTS = DATA / "checkpoints.sqlite3"

#定义单个上传文件的最大大小。
MAX_FILE_BYTES = 20 * 1024 * 1024

#定义允许上传的文件后缀。
EXTENSIONS = {'.txt', '.md', '.pdf', '.docx', '.xlsx'}

# 工作台 MySQL 配置
APP_MYSQL_HOST = os.getenv(
    'APP_MYSQL_HOST',
    'localhost',
)
APP_MYSQL_PORT = int(
    os.getenv('APP_MYSQL_PORT', '3306')
)
APP_MYSQL_USER = os.getenv(
    'APP_MYSQL_USER',
    '',
)
APP_MYSQL_PASSWORD = os.getenv(
    'APP_MYSQL_PASSWORD',
    '',
)
APP_MYSQL_DATABASE = os.getenv(
    'APP_MYSQL_DATABASE',
    'deep_search_workbench',
)
# 用来连mysql 供 FileRepository使用，然后再将主要业务写在FileService，FileService可能会调用FileRepository里面的方法
APP_DATABASE_URL = URL.create(
    drivername='mysql+asyncmy',
    username=APP_MYSQL_USER,
    password=APP_MYSQL_PASSWORD,
    host=APP_MYSQL_HOST,
    port=APP_MYSQL_PORT,
    database=APP_MYSQL_DATABASE,
    query={
        'charset': 'utf8mb4',
    },
)

# 增加 MinIO 配置
MINIO_ENDPOINT = os.getenv(
    'MINIO_ENDPOINT',
    '127.0.0.1:9000',
)
MINIO_PUBLIC_ENDPOINT = os.getenv(
    'MINIO_PUBLIC_ENDPOINT',
    MINIO_ENDPOINT,
)
MINIO_ACCESS_KEY = os.getenv(
    'MINIO_ACCESS_KEY',
    '',
)
MINIO_SECRET_KEY = os.getenv(
    'MINIO_SECRET_KEY',
    '',
)
MINIO_BUCKET = os.getenv(
    'MINIO_BUCKET',
    'deep-search-files',
)
MINIO_SECURE = env_flag(
    'MINIO_SECURE',
    False,
)
# 设置 MinIO 预签名下载链接的有效时间
MINIO_DOWNLOAD_EXPIRES_SECONDS = int(
    os.getenv(
        'MINIO_DOWNLOAD_EXPIRES_SECONDS',
        '600',
    )
)

#临时工作目录最长保留时间
WORKSPACE_MAX_AGE_HOURS = int(
    os.getenv(
        'WORKSPACE_MAX_AGE_HOURS',
        '24',
    )
)


def capabilities():
    return {
        'search': bool(os.getenv('TAVILY_API_KEY')),
        'database': all(os.getenv(k) for k in ('MYSQL_USER', 'MYSQL_PASSWORD', 'MYSQL_DATABASE')),
        'knowledge': all(os.getenv(k) for k in ('RAGFLOW_API_KEY', 'RAGFLOW_API_URL')),
    }
