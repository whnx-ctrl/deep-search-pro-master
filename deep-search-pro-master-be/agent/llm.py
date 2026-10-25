import os
from pathlib import Path
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

# 从项目根目录加载 .env（不依赖进程 CWD）
_project_root = Path(__file__).resolve().parents[1]
_env_path = _project_root / ".env"
if _env_path.is_file():
    load_dotenv(_env_path)
else:
    load_dotenv()
# OPENAI_API_KEY / OPENAI_BASE_URL 等由 init_chat_model + OpenAI 兼容协议读取。
# LLM_MODEL 是标准配置名；保留旧变量以兼容已经跑通的本机 .env。
model_name = os.getenv("LLM_MODEL") or os.getenv("LLM_QWEN3.5")
if not model_name:
    raise RuntimeError("缺少 LLM_MODEL，请在后端 .env 中配置可访问的模型名称")

model = init_chat_model(
    model=model_name,
    model_provider="openai"
)
