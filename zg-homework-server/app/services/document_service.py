"""文档解析与 PDF 生成（迭代 v2.1、PRD 5.5）。

职责：
- 从上传的 PDF / word 文档中抽取纯文本，供文章正文入库
- 把文章正文排版为 PDF，供客户端导出下载

中文字体：reportlab 内置 Adobe CID 字体 `STSong-Light`，无需外部字体文件。
"""

import io
import re
from xml.sax.saxutils import escape

# reportlab 内置中文 CID 字体
_CN_FONT = "STSong-Light"

# 抽取结果中的「乱码」特征：控制字符与替换字符
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_REPLACEMENT = "�"

# 支持的文件扩展名
SUPPORTED_EXTENSIONS = ("pdf", "docx")


class DocumentParseError(ValueError):
    """文档无法解析（格式损坏 / 抽取结果为空 / 抽取结果疑似乱码）。"""


def _looks_broken(text: str) -> bool:
    """判断抽取结果是否疑似乱码。

    pypdf 遇到使用 CID 字体且无 ToUnicode 映射的 PDF 时，
    会抽出大量控制字符或替换字符 —— 这类结果对用户毫无意义，
    应直接报错让用户改用「粘贴正文」，而不是存一堆乱码进库。
    """
    if not text.strip():
        return True
    ctrl = len(_CTRL_RE.findall(text))
    if ctrl > max(3, len(text) * 0.01):
        return True
    if text.count(_REPLACEMENT) > max(3, len(text) * 0.01):
        return True
    return False


def extract_text_from_pdf(data: bytes) -> str:
    """抽取 PDF 正文。失败抛 DocumentParseError。"""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        pages = [(page.extract_text() or "") for page in reader.pages]
    except DocumentParseError:
        raise
    except Exception as exc:  # noqa: BLE001 —— pypdf 异常类型繁多，统一转业务错误
        raise DocumentParseError(f"PDF 解析失败：{exc}") from exc

    text = "\n".join(p.strip() for p in pages if p and p.strip()).strip()
    if _looks_broken(text):
        raise DocumentParseError("无法从该 PDF 解析出正文，请直接粘贴正文文本")
    return text


def extract_text_from_docx(data: bytes) -> str:
    """抽取 word（.docx）正文。失败抛 DocumentParseError。"""
    try:
        from docx import Document

        doc = Document(io.BytesIO(data))
        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
    except DocumentParseError:
        raise
    except Exception as exc:  # noqa: BLE001 —— python-docx 异常类型繁多，统一转业务错误
        raise DocumentParseError(f"Word 文档解析失败：{exc}") from exc

    text = "\n".join(paragraphs).strip()
    if not text:
        raise DocumentParseError("该 Word 文档没有可读取的正文")
    return text


def extract_text(data: bytes, suffix: str) -> str:
    """按扩展名分派到对应的抽取实现。"""
    suffix = (suffix or "").lower().lstrip(".")
    if suffix == "pdf":
        return extract_text_from_pdf(data)
    if suffix == "docx":
        return extract_text_from_docx(data)
    raise DocumentParseError(f"不支持的文件类型：{suffix or '未知'}")


def render_text_to_pdf(title: str, text: str) -> bytes:
    """把标题 + 正文排版为 PDF 字节流。"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    try:
        pdfmetrics.registerFont(UnicodeCIDFont(_CN_FONT))
    except Exception:  # noqa: BLE001 —— 重复注册无害
        pass

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        title=title or "文章",
        author="zg-homework",
        leftMargin=56,
        rightMargin=56,
        topMargin=56,
        bottomMargin=56,
    )
    title_style = ParagraphStyle(
        "CnTitle", fontName=_CN_FONT, fontSize=18, leading=26, spaceAfter=14
    )
    body_style = ParagraphStyle(
        "CnBody", fontName=_CN_FONT, fontSize=11, leading=19, spaceAfter=4
    )

    story = [Paragraph(escape(title or "文章"), title_style), Spacer(1, 6)]
    for line in (text or "").splitlines():
        line = line.rstrip()
        story.append(Paragraph(escape(line) if line.strip() else "&nbsp;", body_style))

    doc.build(story)
    return buf.getvalue()
