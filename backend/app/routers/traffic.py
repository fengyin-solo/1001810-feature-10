"""占道许可接口：维护占道许可，覆盖提交审批、确认批准、确认恢复与整表导入导出。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.traffic import TrafficService

router = APIRouter(prefix="/api/traffic", tags=["占道许可"])

service = TrafficService()

LIST_FIELDS = ["许可编号", "申请单位", "占道位置", "占道面积", "起止日期", "审批人员", "恢复期限", "许可状态"]
STATUSES = ["待审批", "已批准", "施工中", "已恢复"]


class ImportPayload(BaseModel):
    """整表导入入参：前端把所选 CSV 表格读成文本后提交，避免引入文件上传依赖。"""

    filename: str | None = None
    content: str = ""


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按许可编号检索"),
    unit: str | None = Query(default=None, description="按申请单位模糊检索"),
    location: str | None = Query(default=None, description="按占道位置模糊检索"),
    status: str | None = Query(default=None, description="待审批、已批准、施工中、已恢复"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按许可编号、申请单位、占道位置与状态过滤占道许可列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword, unit=unit, location=location, status=status, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries(
    keyword: str | None = Query(default=None, description="按许可编号检索，与列表筛选一致"),
    unit: str | None = Query(default=None, description="按申请单位过滤，与列表筛选一致"),
    location: str | None = Query(default=None, description="按占道位置过滤，与列表筛选一致"),
    status: str | None = Query(default=None, description="按许可状态过滤，与列表筛选一致"),
    format: str = Query(default="json", description="导出格式：json 或 csv"),
) -> dict[str, Any] | Response:
    """导出占道许可清单：范围严格跟随列表当前的关键字、申请单位、占道位置与状态筛选条件。"""
    if str(format).lower() == "csv":
        csv_text = service.export_csv(keyword=keyword, unit=unit, location=location, status=status)
        return Response(
            content="\ufeff" + csv_text,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="traffic_permits.csv"'},
        )
    items, total = service.list_entries(
        keyword=keyword, unit=unit, location=location, status=status, page=1, size=100000
    )
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


@router.post("/import")
def import_entries(payload: ImportPayload) -> dict[str, Any]:
    """整表导入占道许可（CSV 文本）。

    已成功落库的行会保留，对不上规则的行放在 failures 里逐行说明原因；
    同一份表重复导入不会新增重复许可，结束时返回本次新添、更新、补说明的条数。
    """
    if not payload.content.strip():
        raise HTTPException(status_code=400, detail="上传的表格是空的，没有可导入的行")
    try:
        rows = TrafficService.parse_csv(payload.content.encode("utf-8"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not rows:
        raise HTTPException(status_code=400, detail="表格里只有表头，没有数据行")
    return service.import_rows(rows)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条占道许可执行提交审批、确认批准、确认恢复；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
