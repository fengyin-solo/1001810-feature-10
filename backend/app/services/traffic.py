"""占道许可业务规则：状态流转、字段校验、整表导入与筛选口径都收在这里。"""
from __future__ import annotations

import csv
import io
import re
from datetime import date
from typing import Any

from app.store import store

DATE_PATTERN = re.compile(r"\d{4}\D\d{1,2}\D\d{1,2}|\d{8}")

MODULE = "traffic"
REQUIRED_FIELDS = ["许可编号", "申请单位", "占道位置"]
# 表格里会出现的业务列（许可状态由内部 status 映射，不允许从导入行直接写入）
TABLE_FIELDS = ["许可编号", "申请单位", "占道位置", "占道面积", "起止日期", "审批人员", "恢复期限"]
MATCH_FIELDS = ("申请单位", "占道位置")
STATUS_ORDER = ["待审批", "已批准", "施工中", "已恢复"]
ACTION_RULES = {"提交审批": "已批准", "确认批准": "施工中", "确认恢复": "已恢复"}
NEGATIVE_ACTIONS = []


def _cell(row: dict[str, Any], field: str) -> str:
    """取一个单元格并去掉首尾空白；None、数字都按字符串处理。"""
    return str(row.get(field) or "").strip()


def _parse_date(value: str) -> date | None:
    """宽松解析日期：兼容 2026-09-01 / 2026/9/1 / 20260901 等常见表格写法。"""
    match = DATE_PATTERN.search(str(value or ""))
    if match is None:
        return None
    digits = re.findall(r"\d+", match.group())
    if len(digits) == 1 and len(digits[0]) == 8:  # 紧凑格式 20260901
        digits = [digits[0][:4], digits[0][4:6], digits[0][6:]]
    try:
        year, month, day = (int(part) for part in digits[:3])
    except ValueError:
        return None
    if year < 100:  # 两位年份按本世纪处理
        year += 2000
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_period(text: str) -> tuple[date | None, date | None]:
    """把「起止日期」拆成起止两个日期；只填一个日期时视为当天起止相同。"""
    dates = [item for item in (_parse_date(m.group()) for m in DATE_PATTERN.finditer(str(text or ""))) if item]
    if not dates:
        return None, None
    if len(dates) == 1:
        return dates[0], dates[0]
    return min(dates[0], dates[-1]), max(dates[0], dates[-1])


def _serialize(entry: dict[str, Any]) -> dict[str, Any]:
    """列表/导出统一出口：内部 status 渲染成「许可状态」，并补全所有业务列。"""
    item: dict[str, Any] = {"id": entry.get("id")}
    for field in TABLE_FIELDS:
        item[field] = entry.get(field, "")
    item["备注说明"] = entry.get("备注说明", "")
    item["许可状态"] = entry.get("status", "")
    return item


class TrafficService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        unit: str | None = None,
        location: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._filter(keyword=keyword, unit=unit, location=location, status=status)
        total = len(rows)
        start = max(page - 1, 0) * size
        return [_serialize(row) for row in rows[start:start + size]], total

    def _filter(
        self,
        *,
        keyword: str | None = None,
        unit: str | None = None,
        location: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("许可编号", ""))]
        if unit:
            rows = [row for row in rows if unit in str(row.get("申请单位", ""))]
        if location:
            rows = [row for row in rows if location in str(row.get("占道位置", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return rows

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return _serialize(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not _cell(values, field)]
        if missing:
            return None, missing
        entry = self._new_entry(values)
        store.rows(MODULE).append(entry)
        return _serialize(entry), []

    def _new_entry(self, values: dict[str, Any]) -> dict[str, Any]:
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in TABLE_FIELDS:
            entry[field] = _cell(values, field)
        entry["备注说明"] = _cell(values, "备注说明")
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        return entry

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"占道许可 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于占道许可可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return _serialize(entry), f"占道许可已{action}"

    # ------------------------------------------------------------------
    # 整表导入
    # ------------------------------------------------------------------
    def import_rows(self, raw_rows: list[dict[str, Any]], *, today: date | None = None) -> dict[str, Any]:
        """吃下整份占道许可表格。

        按「申请单位 + 占道位置」匹配已有许可：
        - 已批准且今天仍在占道期限内：用表格里的恢复期限续期；
        - 施工中：期限与状态都不动，只补一条导入说明（重复导入不重复记）；
        - 其它状态或对不上规则的行：原样跳过并给出原因，已成功落库的行不受影响。
        """
        today = today or date.today()
        created = 0
        updated = 0
        noted = 0
        failures: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        for index, raw in enumerate(raw_rows, start=2):  # 第 1 行是表头
            row = {key: _cell(raw, key) for key in (*TABLE_FIELDS, "备注说明") if _cell(raw, key)}
            unit, location = row.get("申请单位", ""), row.get("占道位置", "")
            identity = {"行号": index, "申请单位": unit, "占道位置": location,
                        "许可编号": row.get("许可编号", "")}

            missing = [field for field in REQUIRED_FIELDS if not row.get(field)]
            if missing:
                failures.append({**identity, "原因": f"缺少必填字段：{'、'.join(missing)}"})
                continue

            key = (unit, location)
            if key in seen:
                failures.append({**identity, "原因": "与本文件前面的行申请单位、占道位置重复，已跳过"})
                continue
            seen.add(key)

            existing = self._find_match(unit, location)
            if existing is None:
                store.rows(MODULE).append(self._new_entry(row))
                created += 1
                continue

            status = str(existing.get("status") or "")
            if status == "已批准":
                start, end = _parse_period(str(existing.get("起止日期") or ""))
                deadline = _parse_date(str(existing.get("恢复期限") or ""))
                if start is not None and end is not None:
                    within = start <= today <= end
                elif deadline is not None:  # 起止日期缺失时，退回用恢复期限判断
                    within = deadline >= today
                else:
                    within = False
                if not within:
                    failures.append({**identity, "原因": "许可已超出占道期限，不能直接续期，请走重新审批"})
                    continue
                new_deadline = _parse_date(row.get("恢复期限", ""))
                if new_deadline is None:
                    failures.append({**identity, "原因": "恢复期限为空或日期格式无法识别（示例：2026-10-31）"})
                    continue
                existing["恢复期限"] = new_deadline.isoformat()
                updated += 1
                continue

            if status == "施工中":
                note = (
                    f"{today.isoformat()} 批量导入：申请单位申报恢复期限 "
                    f"{row.get('恢复期限') or '未填写'}，施工记录不变更"
                )
                remarks = str(existing.get("备注说明") or "")
                if note not in remarks:
                    existing["备注说明"] = f"{remarks}；{note}".strip("；") if remarks else note
                    noted += 1
                continue

            failures.append({
                **identity,
                "原因": f"当前许可状态为「{status}」，仅「已批准（期限内）」可续期、「施工中」可补说明",
            })

        return {
            "ok": True,
            "created": created,
            "updated": updated,
            "noted": noted,
            "failed": len(failures),
            "total": len(raw_rows),
            "failures": failures,
        }

    def _find_match(self, unit: str, location: str) -> dict[str, Any] | None:
        for row in store.rows(MODULE):
            if str(row.get("申请单位") or "").strip() == unit and \
                    str(row.get("占道位置") or "").strip() == location:
                return row
        return None

    @staticmethod
    def parse_csv(content: bytes) -> list[dict[str, str]]:
        """解析上传的 CSV 表格（兼容带 BOM 的 Excel 导出）；表头需含申请单位、占道位置。"""
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None:
            raise ValueError("表格没有表头，请按模板填写：许可编号、申请单位、占道位置、恢复期限等列")
        headers = {name.strip() for name in reader.fieldnames if name}
        missing_headers = [name for name in MATCH_FIELDS if name not in headers]
        if missing_headers:
            raise ValueError(f"表头缺少列：{'、'.join(missing_headers)}")
        return [{(key or "").strip(): (value or "") for key, value in row.items()} for row in reader]

    def export_csv(
        self,
        *,
        keyword: str | None = None,
        unit: str | None = None,
        location: str | None = None,
        status: str | None = None,
    ) -> str:
        """导出当前筛选范围下的清单为 CSV，口径与列表接口保持一致。"""
        rows, _ = self.list_entries(
            keyword=keyword, unit=unit, location=location, status=status, page=1, size=100000
        )
        columns = [*TABLE_FIELDS, "许可状态", "备注说明"]
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in columns})
        return buffer.getvalue()
