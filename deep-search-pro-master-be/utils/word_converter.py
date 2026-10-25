"""跨平台 Markdown 转 PDF 工具，严格限制资源访问，防止读取外部文件、外网资源"""
from __future__ import annotations

import html
from pathlib import Path
from urllib.parse import unquote, unquote_to_bytes, urlsplit
from urllib.request import url2pathname
from uuid import uuid4

import markdown
from pypdf import PdfReader

# 项目根目录，向上找一层
PROJECT_ROOT = Path(__file__).resolve().parents[1]
# PDF 默认 CSS 样式文件路径
DEFAULT_STYLESHEET = PROJECT_ROOT / "assets" / "pdf" / "default.css"
# 允许嵌入的图片后缀
ALLOWED_IMAGE_SUFFIXES = {".gif", ".jpeg", ".jpg", ".png", ".webp"}
# 允许的 base64 内嵌图片类型
ALLOWED_DATA_IMAGE_TYPES = {
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/webp",
}
# 单张内嵌图片最大：10MB
MAX_DATA_IMAGE_BYTES = 10 * 1024 * 1024


def _inside_workspace(path: Path, workspace: Path) -> Path:
    """校验目标文件必须在当前会话工作目录内，防止路径穿越攻击"""
    target = path.resolve()
    root = workspace.resolve()
    # 不能等于根目录，且必须是根目录的子文件
    if target == root or not target.is_relative_to(root):
        raise ValueError("PDF 转换只能访问当前会话目录中的文件")
    return target


def _validate_data_image(url: str) -> None:
    """校验 base64 内嵌图片（data:image/xxx）：类型合法、大小不超限"""
    header, separator, payload = url.partition(",")
    if not separator:
        raise ValueError("无效的内嵌图片")

    media_type = header[5:].split(";", 1)[0].lower()
    if media_type not in ALLOWED_DATA_IMAGE_TYPES:
        raise ValueError("PDF 仅允许 PNG、JPEG、GIF 或 WebP 内嵌图片")

    # base64 估算解码后大小
    if ";base64" in header.lower():
        decoded_size = len(payload.rstrip("=")) * 3 // 4
    else:
        decoded_size = len(unquote_to_bytes(payload))
    if decoded_size > MAX_DATA_IMAGE_BYTES:
        raise ValueError("PDF 内嵌图片不能超过 10 MiB")


def _load_weasyprint():
    """懒加载 WeasyPrint，同时捕获缺少系统依赖（Pango、字体）的报错"""
    try:
        from weasyprint import CSS, HTML, default_url_fetcher
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            "WeasyPrint 运行库不可用；请在运行环境中安装 Pango、GLib 和中文字体"
        ) from exc
    return CSS, HTML, default_url_fetcher


def _restricted_url_fetcher(workspace: Path, default_url_fetcher):
    """自定义 WeasyPrint 的资源抓取器【核心安全函数】
    禁止 http/https 外网资源；只允许当前会话目录下合法图片 + 合法base64图片
    """
    root = workspace.resolve()

    def fetch(url: str):
        parsed = urlsplit(url)
        scheme = parsed.scheme.lower()

        # base64 内嵌图片，走单独校验
        if scheme == "data":
            _validate_data_image(url)
            return default_url_fetcher(url)

        # 只允许空协议 / file 本地文件协议，拒绝 http/https
        if scheme not in {"", "file"}:
            raise ValueError("PDF 转换不允许访问外部网络资源")

        # file协议 / 相对路径，解析成本地路径
        if scheme == "file":
            resource = Path(url2pathname(unquote(parsed.path)))
        else:
            resource = root / unquote(parsed.path)

        # 校验不能越界，并且是支持的图片格式
        resource = _inside_workspace(resource, root)
        if not resource.is_file() or resource.suffix.lower() not in ALLOWED_IMAGE_SUFFIXES:
            raise ValueError("PDF 只能读取会话目录中的受支持图片")
        return default_url_fetcher(resource.as_uri())

    return fetch


def _render_html(markdown_text: str) -> str:
    """Markdown -> HTML，先转义全部原始html，防止XSS注入，再渲染md语法"""
    safe_markdown = html.escape(markdown_text, quote=False)
    body = markdown.markdown(
        safe_markdown,
        extensions=["tables", "fenced_code", "sane_lists"],
        output_format="html5",
    )
    return (
        "<!doctype html><html lang=\"zh-CN\"><head>"
        "<meta charset=\"utf-8\"><title>研究报告</title>"
        f"</head><body>{body}</body></html>"
    )


def _validate_pdf(path: Path) -> None:
    """校验生成出来的文件是不是合法PDF：文件非空、头部是%PDF-、至少一页"""
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError("PDF 文件未生成")
    with path.open("rb") as stream:
        if stream.read(5) != b"%PDF-":
            raise RuntimeError("生成结果不是有效的 PDF 文件")
    if len(PdfReader(str(path)).pages) < 1:
        raise RuntimeError("生成的 PDF 没有有效页面")


def convert_markdown_to_pdf(
    *,
    md_abs_path: Path,
    pdf_abs_path: Path,
    workspace: Path,
) -> None:
    """
    将工作区内的 Markdown 文件渲染成 PDF
    原子写入：先写 .part 临时文件，校验成功后重命名为目标pdf，避免中途损坏的残文件
    """
    root = workspace.resolve()
    # 校验源md、目标pdf都在会话目录内
    source = _inside_workspace(md_abs_path, root)
    target = _inside_workspace(pdf_abs_path, root)

    if not source.is_file():
        raise FileNotFoundError("Markdown 文件不存在")
    if source.suffix.lower() != ".md" or target.suffix.lower() != ".pdf":
        raise ValueError("仅支持 Markdown 转 PDF")
    if not DEFAULT_STYLESHEET.is_file():
        raise RuntimeError("PDF 默认样式文件不存在")

    CSS, HTML, default_url_fetcher = _load_weasyprint()
    target.parent.mkdir(parents=True, exist_ok=True)
    # 临时文件，带uuid后缀，防止并发冲突
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.part")
    try:
        document = HTML(
            string=_render_html(source.read_text(encoding="utf-8")),
            base_url=source.parent.as_uri(),
            # 传入受限资源抓取器，控制图片加载
            url_fetcher=_restricted_url_fetcher(root, default_url_fetcher),
        )
        document.write_pdf(
            target=str(temporary),
            stylesheets=[CSS(filename=str(DEFAULT_STYLESHEET))],
        )
        # 校验PDF没问题，才改名覆盖正式文件
        _validate_pdf(temporary)
        temporary.replace(target)
    finally:
        # 不管成功失败，清理临时part文件
        temporary.unlink(missing_ok=True)
