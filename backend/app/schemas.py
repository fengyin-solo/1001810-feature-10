"""接口出入参模型：列表分页、动作结果与各模块的明细结构。"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    size: int = 20


class ActionResult(BaseModel):
    ok: bool
    message: str
    entry: dict[str, Any] | None = None


class ImportFailure(BaseModel):
    """批量导入中未处理的一行：行号、原因与该行原始内容。"""

    line: int
    reason: str
    data: dict[str, Any] = Field(default_factory=dict)


class ImportResult(BaseModel):
    """整表导入的逐行处理结果；成功部分已落库，失败行在这里标原因。"""

    ok: bool = True
    total: int = 0
    created: int = 0
    updated: int = 0
    noted: int = 0
    unchanged: int = 0
    failed: int = 0
    summary: str
    failures: list[ImportFailure] = Field(default_factory=list)


class EntryPayload(BaseModel):
    """登记或修改一条业务记录时提交的字段集合。"""

    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None



class PipeEntry(BaseModel):
    """管段明细结构。"""

    field_0: str | None = None  # 管段编号
    field_1: str | None = None  # 管道类别
    field_2: str | None = None  # 起点井号
    field_3: str | None = None  # 终点井号
    field_4: str | None = None  # 管径规格
    field_5: str | None = None  # 管材类型
    field_6: str | None = None  # 埋设深度
    field_7: str | None = None  # 管段状态

class ManholeEntry(BaseModel):
    """检查井明细结构。"""

    field_0: str | None = None  # 井编号
    field_1: str | None = None  # 所在道路
    field_2: str | None = None  # 井盖类别
    field_3: str | None = None  # 井室深度
    field_4: str | None = None  # 井室尺寸
    field_5: str | None = None  # 上次清掏日
    field_6: str | None = None  # 责任班组
    field_7: str | None = None  # 检查井状态

class ValveEntry(BaseModel):
    """阀门明细结构。"""

    field_0: str | None = None  # 阀门编号
    field_1: str | None = None  # 阀门类别
    field_2: str | None = None  # 所在管段
    field_3: str | None = None  # 公称直径
    field_4: str | None = None  # 操作方向
    field_5: str | None = None  # 上次启闭日
    field_6: str | None = None  # 责任人员
    field_7: str | None = None  # 阀门状态

class PumpstationEntry(BaseModel):
    """泵站明细结构。"""

    field_0: str | None = None  # 泵站编号
    field_1: str | None = None  # 泵站名称
    field_2: str | None = None  # 服务区域
    field_3: str | None = None  # 装机台数
    field_4: str | None = None  # 设计流量
    field_5: str | None = None  # 上次检修日
    field_6: str | None = None  # 值守方式
    field_7: str | None = None  # 泵站状态

class PatrolEntry(BaseModel):
    """巡查单明细结构。"""

    field_0: str | None = None  # 巡查单号
    field_1: str | None = None  # 巡查路线
    field_2: str | None = None  # 巡查人员
    field_3: str | None = None  # 巡查日期
    field_4: str | None = None  # 巡查里程
    field_5: str | None = None  # 发现问题数
    field_6: str | None = None  # 巡查时长
    field_7: str | None = None  # 巡查状态

class DefectEntry(BaseModel):
    """缺陷记录明细结构。"""

    field_0: str | None = None  # 缺陷编号
    field_1: str | None = None  # 所在管段
    field_2: str | None = None  # 缺陷类别
    field_3: str | None = None  # 缺陷位置
    field_4: str | None = None  # 严重等级
    field_5: str | None = None  # 发现日期
    field_6: str | None = None  # 登记人员
    field_7: str | None = None  # 缺陷状态

class CctvEntry(BaseModel):
    """检测报告明细结构。"""

    field_0: str | None = None  # 检测编号
    field_1: str | None = None  # 检测管段
    field_2: str | None = None  # 检测设备
    field_3: str | None = None  # 检测长度
    field_4: str | None = None  # 缺陷等级
    field_5: str | None = None  # 检测人员
    field_6: str | None = None  # 检测日期
    field_7: str | None = None  # 检测状态

class RepairEntry(BaseModel):
    """修复单明细结构。"""

    field_0: str | None = None  # 修复单号
    field_1: str | None = None  # 关联缺陷
    field_2: str | None = None  # 修复方式
    field_3: str | None = None  # 承接单位
    field_4: str | None = None  # 开挖范围
    field_5: str | None = None  # 完成日期
    field_6: str | None = None  # 监理人员
    field_7: str | None = None  # 修复状态

class PressureEntry(BaseModel):
    """压力记录明细结构。"""

    field_0: str | None = None  # 监测编号
    field_1: str | None = None  # 监测点位
    field_2: str | None = None  # 监测时段
    field_3: str | None = None  # 平均压力
    field_4: str | None = None  # 峰值压力
    field_5: str | None = None  # 越限次数
    field_6: str | None = None  # 采集人员
    field_7: str | None = None  # 监测状态

class FlowEntry(BaseModel):
    """流量记录明细结构。"""

    field_0: str | None = None  # 监测编号
    field_1: str | None = None  # 监测断面
    field_2: str | None = None  # 监测时段
    field_3: str | None = None  # 平均流量
    field_4: str | None = None  # 峰值流量
    field_5: str | None = None  # 累计流量
    field_6: str | None = None  # 采集人员
    field_7: str | None = None  # 监测状态

class LeakEntry(BaseModel):
    """排查记录明细结构。"""

    field_0: str | None = None  # 排查编号
    field_1: str | None = None  # 排查区域
    field_2: str | None = None  # 排查方式
    field_3: str | None = None  # 疑似点位
    field_4: str | None = None  # 检出数量
    field_5: str | None = None  # 排查人员
    field_6: str | None = None  # 排查日期
    field_7: str | None = None  # 排查状态

class DredgeEntry(BaseModel):
    """清淤单明细结构。"""

    field_0: str | None = None  # 清淤单号
    field_1: str | None = None  # 清淤管段
    field_2: str | None = None  # 淤积厚度
    field_3: str | None = None  # 清淤长度
    field_4: str | None = None  # 清出泥量
    field_5: str | None = None  # 作业班组
    field_6: str | None = None  # 完成日期
    field_7: str | None = None  # 清淤状态

class MaterialEntry(BaseModel):
    """养护材料明细结构。"""

    field_0: str | None = None  # 材料编号
    field_1: str | None = None  # 材料名称
    field_2: str | None = None  # 规格型号
    field_3: str | None = None  # 结存数量
    field_4: str | None = None  # 计量单位
    field_5: str | None = None  # 存放场地
    field_6: str | None = None  # 保管人员
    field_7: str | None = None  # 材料状态

class EquipEntry(BaseModel):
    """养护机械明细结构。"""

    field_0: str | None = None  # 机械编号
    field_1: str | None = None  # 机械名称
    field_2: str | None = None  # 机械型号
    field_3: str | None = None  # 停放场地
    field_4: str | None = None  # 上次保养日
    field_5: str | None = None  # 下次保养日
    field_6: str | None = None  # 责任人
    field_7: str | None = None  # 机械状态

class TrafficEntry(BaseModel):
    """占道许可明细结构。"""

    field_0: str | None = None  # 许可编号
    field_1: str | None = None  # 申请单位
    field_2: str | None = None  # 占道位置
    field_3: str | None = None  # 占道面积
    field_4: str | None = None  # 起止日期
    field_5: str | None = None  # 审批人员
    field_6: str | None = None  # 恢复期限
    field_7: str | None = None  # 许可状态

class ComplaintEntry(BaseModel):
    """诉求记录明细结构。"""

    field_0: str | None = None  # 诉求编号
    field_1: str | None = None  # 诉求来源
    field_2: str | None = None  # 诉求内容
    field_3: str | None = None  # 涉及管段
    field_4: str | None = None  # 受理人员
    field_5: str | None = None  # 处理措施
    field_6: str | None = None  # 办理期限
    field_7: str | None = None  # 诉求状态

class FundEntry(BaseModel):
    """资金记录明细结构。"""

    field_0: str | None = None  # 资金编号
    field_1: str | None = None  # 费用类别
    field_2: str | None = None  # 项目名称
    field_3: str | None = None  # 批复金额
    field_4: str | None = None  # 已用金额
    field_5: str | None = None  # 剩余额度
    field_6: str | None = None  # 审批人员
    field_7: str | None = None  # 资金状态

class ArchiveEntry(BaseModel):
    """档案记录明细结构。"""

    field_0: str | None = None  # 档案编号
    field_1: str | None = None  # 关联管段
    field_2: str | None = None  # 档案类别
    field_3: str | None = None  # 资料名称
    field_4: str | None = None  # 存放位置
    field_5: str | None = None  # 归档人员
    field_6: str | None = None  # 归档日期
    field_7: str | None = None  # 档案状态
