"""占道许可接口：维护占道许可，覆盖提交审批、确认批准、确认恢复、整表导入与清单导出。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from app.schemas import ActionResult, EntryPayload, ImportResult, PageResult
from app.services.traffic import TrafficService
from app.sheet_io import SheetParseError, parse_sheet

router = APIRouter(prefix="/api/traffic", tags=["占道许可"])

service = TrafficService()

LIST_FIELDS = ["许可编号", "申请单位", "占道位置", "占道面积", "起止日期", "审批人员", "恢复期限", "许可状态", "备注"]
STATUSES = ["待审批", "已批准", "施工中", "已恢复"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按许可编号检索"),
    status: str | None = Query(default=None, description="待审批、已批准、施工中、已恢复"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按许可编号与状态过滤占道许可列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.post("/import", response_model=ImportResult)
async def import_entries(file: UploadFile = File(..., description="占道许可表格，.xlsx 或 .csv")) -> ImportResult:
    """整表导入占道许可：逐行匹配处理，成功的直接落库，对不上或不能更新的行在结果里标原因。"""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="上传的文件是空的，请确认表格内容后重试")
    try:
        raw_rows = parse_sheet(content, file.filename or "")
    except SheetParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    present = set().union(*(row.keys() for row in raw_rows)) if raw_rows else set()
    missing_headers = [
        field for field in ("许可编号", "申请单位", "占道位置") if field not in present
    ]
    if missing_headers:
        raise HTTPException(
            status_code=400,
            detail=f"表头缺少必填列：{'、'.join(missing_headers)}，请按占道许可清单的表头整理",
        )

    outcome = service.import_rows(raw_rows)
    return ImportResult(**outcome)


@router.get("/export")
def export_entries(
    keyword: str | None = Query(default=None, description="按许可编号检索，与列表一致"),
    status: str | None = Query(default=None, description="待审批、已批准、施工中、已恢复"),
) -> dict[str, Any]:
    """导出占道许可清单：范围与列表当前的关键字、状态过滤条件保持一致。"""
    items, total = service.list_entries(keyword=keyword, status=status, page=1, size=10000)
    return {"module": "traffic", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条占道许可明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"占道许可 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条占道许可，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="占道许可已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条占道许可执行提交审批、确认批准、确认恢复；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
