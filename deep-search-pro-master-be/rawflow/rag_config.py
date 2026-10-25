import os
from dotenv import load_dotenv
from typing import Tuple, Optional
from pathlib import Path
def _load_ragflow_env() -> Tuple[Optional[str], Optional[str]]:
    """
    加载 RAGFlow 环境变量（优先读取项目根目录 .env，兼容系统环境变量）
    返回值：(api_key, base_url) → 缺失则返回 None
    """
    # 优先加载项目根目录的 .env 文件
    project_root = Path(__file__).resolve().parents[1]
    env_path = project_root / ".env"
    if env_path.is_file():
        load_dotenv(env_path)
    else:
        load_dotenv()  # 兜底：系统环境变量或 CWD 链上的 .env

    api_key = os.getenv("RAGFLOW_API_KEY")
    base_url = os.getenv("RAGFLOW_API_URL")
    return api_key, base_url