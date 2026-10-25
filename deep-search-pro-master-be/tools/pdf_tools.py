import logging
from pathlib import Path

try:
    from typing import Annotated, Optional
except ImportError:
    from typing_extensions import Annotated, Optional

from langchain_core.tools import tool
from api.monitor import monitor
from api.context import get_session_context
from utils.path_utils import resolve_path
from utils.word_converter import convert_markdown_to_pdf


@tool
def convert_md_to_pdf(
        md_filename: Annotated[str, "要转换的Markdown文档路径（包含.md后缀）"],
        pdf_filename: Annotated[Optional[str], "输出的PDF文件路径（可选，默认与源文件同名）"] = None
) -> str:
    """将 Markdown 文档转换为 PDF；本层只负责会话路径校验和工具响应。"""
    monitor.report_tool("Markdown转PDF工具")

    try:
        # 1. 路径预处理
        session_dir = get_session_context()
        md_path = Path(md_filename).with_suffix('.md')
        md_abs_path = Path(resolve_path(str(md_path), session_dir))

        # 2. 检查源文件
        if not md_abs_path.is_file():
            return "错误：Markdown 文件不存在"

        # 3. 确定输出路径
        if pdf_filename:
            pdf_path = Path(pdf_filename).with_suffix('.pdf')
            pdf_abs_path = Path(resolve_path(str(pdf_path), session_dir))
        else:
            pdf_abs_path = Path(
                resolve_path(str(md_abs_path.with_suffix('.pdf')), session_dir)
            )

        # 4. 使用跨平台 WeasyPrint 转换；转换器会再次校验资源边界并原子写入。
        convert_markdown_to_pdf(
            md_abs_path=md_abs_path,
            pdf_abs_path=pdf_abs_path,
            workspace=Path(session_dir),
        )
        return f"PDF 文件已成功生成：{pdf_abs_path.name}"

    except Exception as exc:
        logging.exception("Markdown 转 PDF 失败")
        return f"转换失败：{exc}"
