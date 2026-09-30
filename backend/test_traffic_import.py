"""整表导入端到端验证：用 TestClient 打真实接口，表格用 openpyxl 现造。"""
import io
import sys
from datetime import date, timedelta

from openpyxl import Workbook
from fastapi.testclient import TestClient

from app.main import app
from app.store import store

client = TestClient(app)

HEADERS = ["许可编号", "申请单位", "占道位置", "占道面积", "起止日期", "审批人员", "恢复期限"]


def xlsx_bytes(rows):
    wb = Workbook()
    ws = wb.active
    ws.append(HEADERS)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


today = date.today()
in_start = (today - timedelta(days=5)).isoformat()
in_end = (today + timedelta(days=20)).isoformat()
future_start = (today + timedelta(days=10)).isoformat()

# 准备库内许可：已批准且在占道期内 / 已批准但超期 / 施工中 / 已恢复
rows = store.rows("traffic")
rows.clear()
rows.extend([
    {"id": 1, "status": "已批准", "pending": True, "abnormal": False,
     "许可编号": "TRAF-A", "申请单位": "甲单位", "占道位置": "和平路1号",
     "起止日期": f"{in_start}~{in_end}", "恢复期限": in_end, "许可状态": "已批准"},
    {"id": 2, "status": "已批准", "pending": True, "abnormal": False,
     "许可编号": "TRAF-B", "申请单位": "乙单位", "占道位置": "解放路2号",
     "起止日期": "2025-01-01~2025-02-01", "恢复期限": "2025-02-01", "许可状态": "已批准"},
    {"id": 3, "status": "施工中", "pending": False, "abnormal": False,
     "许可编号": "TRAF-C", "申请单位": "丙单位", "占道位置": "建设路3号",
     "起止日期": f"{in_start}~{in_end}", "许可状态": "施工中"},
    {"id": 4, "status": "已恢复", "pending": False, "abnormal": False,
     "许可编号": "TRAF-D", "申请单位": "丁单位", "占道位置": "胜利路4号",
     "许可状态": "已恢复"},
])
start_count = len(rows)

new_deadline = (today + timedelta(days=45)).isoformat()
table_rows = [
    # 1 已批准在期内 -> 更新恢复期限
    ["TRAF-A", "甲单位", "和平路1号", "100㎡", f"{in_start}~{in_end}", "张三", new_deadline],
    # 2 已批准但超期 -> 失败标因
    ["TRAF-B", "乙单位", "解放路2号", "50㎡", "2025-01-01~2025-02-01", "李四", new_deadline],
    # 3 施工中 -> 只补说明
    ["TRAF-C", "丙单位", "建设路3号", "30㎡", f"{in_start}~{in_end}", "王五", new_deadline],
    # 4 已恢复 -> 失败标因
    ["TRAF-D", "丁单位", "胜利路4号", "20㎡", "", "赵六", new_deadline],
    # 5 对不上 -> 新增
    ["TRAF-NEW1", "戊单位", "朝阳路5号", "80㎡", f"{in_start}~{in_end}", "孙七", new_deadline],
    # 6 缺申请单位 -> 失败
    ["TRAF-NEW2", "", "开发区6号", "10㎡", "", "", new_deadline],
    # 7 同表内与第5行重复（同单位同位置不同编号）-> 重复跳过
    ["TRAF-NEW3", "戊单位", "朝阳路5号", "80㎡", "", "", new_deadline],
    # 8 许可编号冲突但单位位置对不上 -> 失败
    ["TRAF-A", "庚单位", "高新区7号", "10㎡", "", "", new_deadline],
    # 9 日期无法识别的已批准许可 -> 用库里的日期能识别，应成功更新
    # （这行复用甲单位+和平路1号会被当重复跳过，故省略）
]

resp = client.post(
    "/api/traffic/import",
    files={"file": ("许可清单.xlsx", xlsx_bytes(table_rows),
                    "application/vnd.openxmlxmlformats-officedocument.spreadsheetml.sheet")},
)
assert resp.status_code == 200, resp.text
first = resp.json()
print("首次导入:", first["summary"])
assert first["total"] == 8, first
assert first["created"] == 1, first
assert first["updated"] == 1, first
assert first["noted"] == 1, first
assert first["unchanged"] == 1, first
assert first["failed"] == 4, first
reasons = {(f["line"], f["reason"]) for f in first["failures"]}
assert any(f["line"] == 2 and "不在占道期限内" in f["reason"] for f in first["failures"])
assert any(f["line"] == 4 and "已恢复" in f["reason"] for f in first["failures"])
assert any(f["line"] == 6 and "缺少必填字段" in f["reason"] for f in first["failures"])
assert any(f["line"] == 8 and "已被其他占道许可占用" in f["reason"] for f in first["failures"])

# 数据落库检查
a = next(r for r in store.rows("traffic") if r["许可编号"] == "TRAF-A")
assert a["恢复期限"] == new_deadline, a
c = next(r for r in store.rows("traffic") if r["许可编号"] == "TRAF-C")
assert "批量导入" in c.get("备注", ""), c
new1 = next(r for r in store.rows("traffic") if r["许可编号"] == "TRAF-NEW1")
assert new1["status"] == "待审批" and new1["许可状态"] == "待审批"
assert len(store.rows("traffic")) == start_count + 1, store.rows("traffic")

# 成功部分保留：再次整表导入 -> 不新增许可、不重复改
resp2 = client.post(
    "/api/traffic/import",
    files={"file": ("许可清单.xlsx", xlsx_bytes(table_rows), "text/plain")},
)
second = resp2.json()
print("二次导入:", second["summary"])
assert second["created"] == 0, second
assert second["updated"] == 0, second
assert second["noted"] == 0, second
# 甲单位(期限已是新值)/丙单位(说明已存在)/新1(待审批重复)/行7同表重复 -> 4 条跳过
assert second["unchanged"] == 4, second
# 超期、已恢复、缺字段、编号冲突仍标因
assert second["failed"] == 4, second
assert len(store.rows("traffic")) == start_count + 1
c2 = next(r for r in store.rows("traffic") if r["许可编号"] == "TRAF-C")
assert c2["备注"].count("批量导入") == 1, c2  # 说明没有重复追加

# 恢复期限相同的已批准许可 -> unchanged 而非 updated
same_rows = [["TRAF-A", "甲单位", "和平路1号", "100㎡",
              f"{in_start}~{in_end}", "张三", new_deadline]]
# 先清 seen：重新构造一次导入即可（seen 是请求级别的）
resp3 = client.post("/api/traffic/import",
                    files={"file": ("s.xlsx", xlsx_bytes(same_rows), "text/plain")})
third = resp3.json()
print("同期限再导:", third["summary"])
assert third["updated"] == 0 and third["unchanged"] == 1, third

# 导出范围与列表过滤一致
exp_all = client.get("/api/traffic/export").json()
list_all = client.get("/api/traffic?size=200").json()
assert exp_all["total"] == list_all["total"], (exp_all["total"], list_all["total"])
exp_f = client.get("/api/traffic/export", params={"status": "施工中"}).json()
list_f = client.get("/api/traffic", params={"status": "施工中", "size": 200}).json()
assert exp_f["total"] == list_f["total"] == 1
assert exp_f["items"][0]["许可编号"] == "TRAF-C"

# 导出带 keyword
exp_k = client.get("/api/traffic/export", params={"keyword": "TRAF-A"}).json()
assert exp_k["total"] == 1 and exp_k["items"][0]["许可编号"] == "TRAF-A"

# /export 不被 /{entry_id} 吞掉
assert client.get("/api/traffic/export").status_code == 200

# 坏文件 / 缺表头
bad = client.post("/api/traffic/import",
                  files={"file": ("x.xlsx", b"not a real xlsx", "text/plain")})
assert bad.status_code == 400, bad.text
wb = Workbook(); wb.active.append(["编号", "单位", "位置"])
buf = io.BytesIO(); wb.save(buf)
miss = client.post("/api/traffic/import",
                   files={"file": ("m.xlsx", buf.getvalue(), "text/plain")})
assert miss.status_code == 400 and "表头缺少必填列" in miss.json()["detail"], miss.text
empty = client.post("/api/traffic/import",
                    files={"file": ("e.xlsx", b"", "text/plain")})
assert empty.status_code == 400

# CSV 通道
csv_content = ("许可编号,申请单位,占道位置,恢复期限\r\n"
               f"TRAF-CSV,辛单位,黄河路8号,{new_deadline}\r\n").encode("utf-8-sig")
resp_csv = client.post("/api/traffic/import",
                       files={"file": ("c.csv", csv_content, "text/csv")})
assert resp_csv.status_code == 200, resp_csv.text
assert resp_csv.json()["created"] == 1
assert next(r for r in store.rows("traffic") if r["许可编号"] == "TRAF-CSV")

# 动作流转同步「许可状态」字段
client.post(f"/api/traffic/{new1['id']}/actions", json={"values": {"action": "提交审批"}})
new1 = next(r for r in store.rows("traffic") if r["许可编号"] == "TRAF-NEW1")
assert new1["status"] == "已批准" and new1["许可状态"] == "已批准"

# 现在新1已批准且在期内，再导它：更新恢复期限
updated_deadline = (today + timedelta(days=60)).isoformat()
upd_rows = [["TRAF-NEW1", "戊单位", "朝阳路5号", "80㎡",
             f"{in_start}~{in_end}", "孙七", updated_deadline]]
resp4 = client.post("/api/traffic/import",
                    files={"file": ("u.xlsx", xlsx_bytes(upd_rows), "text/plain")})
r4 = resp4.json()
print("新批许可更新:", r4["summary"])
assert r4["updated"] == 1, r4
new1 = next(r for r in store.rows("traffic") if r["许可编号"] == "TRAF-NEW1")
assert new1["恢复期限"] == updated_deadline

print("\n全部断言通过 ✔")
