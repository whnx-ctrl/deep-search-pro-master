"""Agent assembly and execution. HTTP lifecycle and final status live in api.server."""
import asyncio
from pathlib import Path
# from langgraph.checkpoint.memory import InMemorySaver 升级为持久化储存，用lifespan启动
from deepagents import create_deep_agent
from langchain_core.messages import AIMessage
from api.settings import OUTPUT, capabilities
from api.context import set_session_context, get_thread_context, set_thread_context, reset_session_context
from api.monitor import monitor
from agent.llm import model
from agent.prompts import main_agent_content
from tools.markdown_tools import generate_markdown
from tools.pdf_tools import convert_md_to_pdf
from tools.upload_file_read_tool import read_file_content

#新增动态加载子 Agent，读取全局配置开关，运行时判断启用哪些子 Agent，不是硬编码全部写死
available = capabilities()
subagents = []
if available['search']:
    from agent.subagents.network_search_agent import network_search_agent
    subagents.append(network_search_agent)
if available['database']:
    from agent.subagents.database_query_agent import database_query_agent
    subagents.append(database_query_agent)
if available['knowledge']:
    from agent.subagents.knowledge_base_agent import knowledge_base_agent
    subagents.append(knowledge_base_agent)

names = '、'.join(agent['name'] for agent in subagents) or '暂无外部助手'


_main_agent = None

def get_main_agent(checkpointer):
    global _main_agent
    if _main_agent is None:
        _main_agent = create_deep_agent(
            model=model,
            system_prompt=(
                main_agent_content["system_prompt"]
                + f"\n本次实际可用助手：{names}。"
                  "未配置的能力不能调用，请明确告知限制。"
                  "文档由主智能体直接调用工具生成。"
            ),
            tools=[
                generate_markdown,
                convert_md_to_pdf,
                read_file_content,
            ],
            checkpointer=checkpointer,
            subagents=subagents,
        )
    return _main_agent


async def run_deep_agent(task_query, session_id, checkpointer, file_service):
    session_dir = OUTPUT / f'session_{session_id}'
    session_token = set_session_context(str(session_dir))
    thread_token = set_thread_context(session_id)
    main_agent = get_main_agent(checkpointer)
    try:
        # 在 Agent 开始前，将 MySQL 中登记、MinIO 中保存的会话文件完整地恢复到本地临时目录
        # 并记录输入文件指纹，供 Agent 结束后识别生成文件
        input_manifest = (
            await file_service.prepare_workspace(
                thread_uuid=session_id,
                workspace=session_dir,
            )
        )
        files = sorted(input_manifest.keys())
        monitor.report_session_dir(str(session_dir))
        instruction = (
            f'\n【工作环境】当前会话目录：{session_dir.name}。'
            '创建文件只传会话内相对路径；读取上传文件只传文件名。'
            f'当前可读取文件：{files}。如有相关上传资料先读取。'
        )
        result = ''
        async for chunk in main_agent.astream(
            {'messages': [{'role': 'user', 'content': task_query + instruction}]},
            config={'configurable': {'thread_id': session_id}}, stream_mode='updates',
        ):
            for node_name, state in chunk.items():
                if node_name != 'model' or not isinstance(state, dict):
                    continue
                messages = state.get('messages', [])
                if not messages or not isinstance(messages[-1], AIMessage):
                    continue
                message = messages[-1]
                for call in message.tool_calls:
                    if call['name'] == 'task':
                        monitor.report_assistant(call['args'].get('subagent_type', '助手'),
                                                 {'description': call['args'].get('description', '')})
                if not message.tool_calls and message.content:
                    content = message.content
                    result = content if isinstance(content, str) else '\n'.join(
                        block.get('text', '') for block in content if isinstance(block, dict)
                    )
        if not result.strip():
            raise RuntimeError('模型未返回最终回答')
        await file_service.publish_generated_files(
            thread_uuid=session_id,
            workspace=session_dir,
            # 与执行前清单比较，只发布新增或被修改的文件。
            input_manifest=input_manifest,
        )

        return result
    finally:
        reset_session_context(session_token, thread_token)
        await file_service.cleanup_workspace(
            session_dir,
        )

