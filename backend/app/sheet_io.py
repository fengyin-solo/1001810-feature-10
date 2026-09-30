"""批量导入表格解析：把 .xlsx / .csv 的首个工作表读成「表头 -> 值」的字典列表。

只负责解析与表头对齐，业务匹配规则在各模块的 service 里。
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime
from typing import Any

from openpyxl import load_workbook


class SheetParseError(ValueError):
    """表格无法解析或表头不可用时抛出，消息直接展示给用户。"""


def _normalize_header(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _cell_to_text(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return value


def parse_sheet(content: bytes, filename: str) -> list[dict[str, Any]]:
    """读取上传文件的字节内容，返回按表头命名的行；空表给可读错误。"""
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if suffix in ("xlsx", "xlsm"):
        return _parse_xlsx(content)
    if suffix == "csv":
        return _parse_csv(content)
    raise SheetParseError("仅支持 .xlsx 或 .csv 格式的表格，请另存后重新导入")


def _parse_xlsx(content: bytes) -> list[dict[str, Any]]:
    try:
        workbook = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    except Exception as exc:  # openpyxl 对坏文件抛的异常类型不一，统一成可读消息
        raise SheetParseError(f"Excel 文件无法读取：{exc}") from exc
    worksheet = workbook.active
    if worksheet is None:
        raise SheetParseError("工作簿里没有可用的工作表")
    rows_iter = worksheet.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration:
        raise SheetParseError("表格没有表头行，请确认第一行是字段名称")
    headers = [_normalize_header(cell) for cell in header_row]
    if not any(headers):
        raise SheetParseError("表头为空，请确认第一行是字段名称")

    result: list[dict[str, Any]] = []
    for row in rows_iter:
        item = {
            headers[index]: _cell_to_text(value)
            for index, value in enumerate(row)
            if index < len(headers) and headers[index]
        }
        result.append(item)
    return result


def _parse_csv(content: bytes) -> list[dict[str, Any]]:
    text: str | None = None
    for encoding in ("utf-8-sig", "gbk", "utf-16"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise SheetParseError("CSV 文件编码无法识别，请另存为 UTF-8 后重试")
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        raise SheetParseError("表格没有表头行，请确认第一行是字段名称")
    headers = [_normalize_header(cell) for cell in header]
    if not any(headers):
        raise SheetParseError("表头为空，请确认第一行是字段名称")

    result: list[dict[str, Any]] = []
    for values in reader:
        item = {
            headers[index]: _cell_to_text(value.strip())
            for index, value in enumerate(values)
            if index < len(headers) and headers[index] and str(value).strip()
        }
        result.append(item)
    return result
