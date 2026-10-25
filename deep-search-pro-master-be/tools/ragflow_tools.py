"""RAGFlow chat tools with guaranteed temporary-session cleanup."""
import logging
from langchain_core.tools import tool
from ragflow_sdk import RAGFlow
from rawflow.rag_config import _load_ragflow_env
from api.monitor import monitor

api_key, base_url = _load_ragflow_env()
ragflow_client = RAGFlow(api_key=api_key, base_url=base_url)


@tool
def get_assistant_list() -> str:
    """查询知识库助手名称、描述和关联数据集，提问前先调用。"""
    monitor.report_tool('知识库助手列表')
    try:
        chats = ragflow_client.list_chats()
        # 遍历全部 RAGFlow 助手，每个助手生成一行文本，包含助手名、描述、关联知识库（多个知识库用顿号隔开）；
        # 助手之间换行分隔；没有助手就返回提示文本
        # chat.name = "产品助手"
        # chat.description = "查询产品文档"
        # chat.datasets = [{"name":"产品手册"},{"name":"FAQ知识库"}]
        return '\n'.join(
            f'助手：{chat.name}；说明：{chat.description}；知识库：' +
            '、'.join(d.get('name', '') for d in (chat.datasets or []) if isinstance(d, dict))
            for chat in chats
        ) or '没有可用的知识库助手'
    except Exception:
        logging.exception('RAGFlow list failed')
        return '知识库暂时不可用，请检查后端配置与服务状态'


@tool
def create_ask_delete(chat_name: str, question: str) -> str:
    """向指定知识库助手提问，结束后清理临时会话。"""
    monitor.report_tool('知识库检索', {'chat_name': chat_name, 'question': question})
    chat = session = None
    try:
        chats = ragflow_client.list_chats(name=chat_name)
        if not chats:
            return '未找到该知识库助手，请先查询助手列表'
        chat = chats[0]
        session = chat.create_session(name='workbench_temp')
        # Chat completions use cumulative answer snapshots in RAGFlow SDK.
        result = ''
        for part in session.ask(question=question, stream=True):
            result = part.content #RAGFlow SDK 返回的流式片段可能是“到当前为止的完整文本"，所以不用+=
        return result or '知识库未返回内容'
    except Exception:
        logging.exception('RAGFlow ask failed')
        return '知识库提问失败，请检查后端日志'
    finally:
        if chat and session:
            try:
                chat.delete_sessions(ids=[session.id])
            except Exception:
                logging.exception('RAGFlow cleanup failed')
