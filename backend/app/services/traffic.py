"""占道许可业务规则：状态流转、字段校验、批量导入与筛选口径都收在这里。"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.store import store

MODULE = "traffic"
REQUIRED_FIELDS = ["许可编号", "申请单位", "占道位置"]
DATA_FIELDS = [
    "许可编号", "申请单位", "占道位置", "占道面积",
    "起止日期", "审批人员", "恢复期限", "许可状态",
]
STATUS_ORDER = ["待审批", "已批准", "施工中", "已恢复"]
ACTION_RULES = {"提交审批": "已批准", "确认批准": "施工中", "确认恢复": "已恢复"}
NEGATIVE_ACTIONS = []

# 起止日期里的日期片段：2026-09-01 / 2026/9/1 / 2026年9月1日 都认
_DATE_PATTERN = re.compile(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})")


def _parse_dates(text: Any) -> tuple[date | None, date | None]:
    """把「2026-09-01~2026-09-30」解析成起止日期；只写一个日期时起止相同。"""
    if not text:
        return None, None
    if isinstance(text, date):
        return text, text
    matches = _DATE_PATTERN.findall(str(text))
    if not matches:
        return None, None
    try:
        start = date(int(matches[0][0]), int(matches[0][1]), int(matches[0][2]))
        end_parts = matches[-1]
        end = date(int(end_parts[0]), int(end_parts[1]), int(end_parts[2]))
    except ValueError:
        return None, None
    return start, end


def _parse_one_date(text: Any) -> date | None:
    if isinstance(text, date):
        return text
    start, _ = _parse_dates(text)
    return start


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


class TrafficService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("许可编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

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
        # 列表展示用的是「许可状态」字段，状态流转时一并同步，避免界面与流程脱节
        entry["许可状态"] = target
        return entry, f"占道许可已{action}"

    def import_rows(self, raw_rows: list[dict[str, Any]]) -> dict[str, Any]:
        """整表导入：按申请单位+占道位置匹配已有许可，逐行处理、互不回滚。

        - 已批准且仍在占道期限内：用表格里的恢复期限更新许可（改一条）
        - 施工中：只追加一条说明，不动许可字段（补说明一条）
        - 其余许可（含已批准但超期、已恢复等）与缺字段、编号冲突的行：不处理并标原因
        - 对不上已有许可的行：作为新许可登记；同表重复行跳过，保证重复导入不多许可
        """
        rows = store.rows(MODULE)
        result: dict[str, Any] = {
            "created": 0,
            "updated": 0,
            "noted": 0,
            "unchanged": 0,
            "total": len(raw_rows),
            "failures": [],
        }
        # 本次导入已经处理过的「申请单位|占道位置」，同表重复与再次导入都走同一套口径
        seen_keys: set[str] = set()
        next_id = max((int(row.get("id", 0)) for row in rows), default=0) + 1

        for line_no, raw in enumerate(raw_rows, start=1):
            data = {field: _text(raw.get(field)) for field in DATA_FIELDS}
            fail = lambda reason: result["failures"].append(
                {"line": line_no, "reason": reason, "data": data}
            )

            if not any(data.values()):
                # 空行不计入失败，也不占统计
                result["total"] -= 1
                continue

            missing = [field for field in REQUIRED_FIELDS if not data[field]]
            if missing:
                fail(f"缺少必填字段：{'、'.join(missing)}")
                continue

            match_key = f"{data['申请单位']}|{data['占道位置']}"
            if match_key in seen_keys:
                # 本批次已处理过同一申请单位+占道位置（同表重复行或重复导入），跳过不改
                result["unchanged"] += 1
                continue

            entry = next(
                (
                    row for row in rows
                    if _text(row.get("申请单位")) == data["申请单位"]
                    and _text(row.get("占道位置")) == data["占道位置"]
                ),
                None,
            )

            if entry is None:
                exists_no = next(
                    (row for row in rows if _text(row.get("许可编号")) == data["许可编号"]),
                    None,
                )
                if exists_no is not None:
                    fail(f"许可编号 {data['许可编号']} 已被其他占道许可占用")
                    continue
                new_entry = {"id": next_id}
                next_id += 1
                for field in DATA_FIELDS:
                    if data[field]:
                        new_entry[field] = data[field]
                new_entry["status"] = STATUS_ORDER[0]
                new_entry["许可状态"] = STATUS_ORDER[0]
                new_entry["pending"] = True
                new_entry["abnormal"] = False
                rows.append(new_entry)
                seen_keys.add(match_key)
                result["created"] += 1
                continue

            seen_keys.add(match_key)
            status = _text(entry.get("status"))
            if status == "待审批":
                # 许可还没批，库里已有同单位同位置的登记：重复导入按已存在跳过
                result["unchanged"] += 1
            elif status == "已批准":
                start, end = _parse_dates(entry.get("起止日期"))
                if start is None:
                    # 库里的起止日期认不出来时，再给表格一次机会
                    start, end = _parse_dates(data["起止日期"])
                if start is None:
                    fail("占道起止日期无法识别，无法判断是否在占道期限内")
                    continue
                today = date.today()
                if today < start or (end is not None and today > end):
                    span = start.isoformat() if end is None else f"{start.isoformat()}~{end.isoformat()}"
                    fail(f"已批准许可不在占道期限内（{span}），不能更新恢复期限")
                    continue
                new_deadline = _parse_one_date(data["恢复期限"])
                if new_deadline is None:
                    fail("恢复期限缺失或日期格式无法识别")
                    continue
                if _text(entry.get("恢复期限")) == new_deadline.isoformat():
                    result["unchanged"] += 1
                    continue
                entry["恢复期限"] = new_deadline.isoformat()
                result["updated"] += 1
            elif status == "施工中":
                deadline_text = data["恢复期限"]
                note = (
                    f"{date.today().isoformat()} 批量导入：{data['许可编号']} 申报恢复期限 {deadline_text}，施工中仅登记说明"
                    if deadline_text
                    else f"{date.today().isoformat()} 批量导入：{data['许可编号']} 未填写恢复期限，施工中仅登记说明"
                )
                notes = _text(entry.get("备注"))
                # 同一条说明（同一申报编号+同一期限，日期前缀可能不同）重复导入不再追加
                fingerprint = note.split(" ", 1)[1]
                if any(fingerprint in line.split(" ", 1)[-1] for line in notes.splitlines()):
                    result["unchanged"] += 1
                else:
                    entry["备注"] = note if not notes else f"{notes}\n{note}"
                    result["noted"] += 1
            else:
                fail(f"许可当前状态为「{status or '未知'}」，不支持按导入更新")

        failed = len(result["failures"])
        summary = (
            f"共处理 {result['total']} 行：新增 {result['created']} 条，"
            f"更新恢复期限 {result['updated']} 条，施工中补说明 {result['noted']} 条"
        )
        if result["unchanged"]:
            summary += f"，重复跳过 {result['unchanged']} 条"
        if failed:
            summary += f"，{failed} 行未处理（已在下方标原因，其余成功部分均已保留）"
        result["failed"] = failed
        result["summary"] = summary
        return result
