"""道路设施接口：维护道路设施，覆盖办理移交、标记观测、封闭设施等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.road import RoadService

router = APIRouter(prefix="/api/road", tags=["道路设施"])

service = RoadService()

LIST_FIELDS = ["设施编码", "道路名称", "道路等级", "起止桩号", "路面结构", "管养单位", "建成年份", "设施状态"]
STATUSES = ["待移交", "正常养护", "重点观测", "封闭施工"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    code: str | None = Query(default=None, description="按设施编码检索，大小写与短横线写法不敏感"),
    name: str | None = Query(default=None, description="按道路名称检索"),
    level: str | None = Query(default=None, description="按道路等级检索"),
    status: str | None = Query(default=None, description="待移交、正常养护、重点观测、封闭施工"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按设施编码、道路名称、道路等级取交集过滤道路设施列表。

    条件写错或页码越界时返回 400 并说明原因；查不到数据时返回空页，不报错。
    """
    items, total, error = service.list_entries(
        code=code, name=name, level=level, status=status, page=page, size=size
    )
    if error:
        raise HTTPException(status_code=400, detail=error)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries(
    code: str | None = Query(default=None, description="同列表的设施编码条件"),
    name: str | None = Query(default=None, description="同列表的道路名称条件"),
    level: str | None = Query(default=None, description="同列表的道路等级条件"),
    status: str | None = Query(default=None, description="同列表的设施状态条件"),
) -> dict[str, Any]:
    """导出道路设施清单：与列表共用一套筛选口径，保证两边条数对得上。"""
    items, error = service.filter_entries(code=code, name=name, level=level, status=status)
    if error:
        raise HTTPException(status_code=400, detail=error)
    return {"module": "road", "total": len(items), "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条道路设施明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"道路设施 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条道路设施，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="道路设施已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条道路设施执行办理移交、标记观测、封闭设施；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
