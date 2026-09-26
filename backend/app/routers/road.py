"""道路设施接口：维护道路设施，覆盖办理移交、标记观测、封闭设施等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.road import RoadService, normalize_code

router = APIRouter(prefix="/api/road", tags=["道路设施"])

service = RoadService()

LIST_FIELDS = ["设施编码", "道路名称", "道路等级", "起止桩号", "路面结构", "管养单位", "建成年份", "设施状态"]
STATUSES = ["待移交", "正常养护", "重点观测", "封闭施工"]


def _parse_filters(code: str | None, name: str | None, level: str | None) -> tuple[str, str, str]:
    """归一化三个筛选条件：名称、等级去掉首尾空白；编码先校验写法。"""
    code = (code or "").strip()
    name = (name or "").strip()
    level = (level or "").strip()
    if code:
        normalized, error = normalize_code(code)
        if error:
            raise HTTPException(status_code=400, detail=error)
        code = normalized or ""
    return code, name, level


def _ensure_page_in_range(page: int, size: int, total: int) -> None:
    """页码越过最后一页时给出可读说明，而不是默默返回一个空列表。"""
    max_page = max(1, (total + size - 1) // size)
    if page > max_page:
        raise HTTPException(
            status_code=400,
            detail=f"第 {page} 页不存在：按当前条件共 {total} 条记录，最多只能翻到第 {max_page} 页",
        )


@router.get("", response_model=PageResult[dict])
def list_entries(
    code: str | None = None,
    name: str | None = None,
    level: str | None = None,
    status: str | None = None,
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按设施编码、道路名称、道路等级过滤列表，多条件取交集；没有数据时返回空页，不报错。"""
    if page < 1:
        raise HTTPException(status_code=400, detail="页码必须从 1 开始")
    if size < 1:
        raise HTTPException(status_code=400, detail="每页条数至少为 1")
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    normalized_code, name, level = _parse_filters(code, name, level)
    status = (status or "").strip() or None
    items, total = service.list_entries(
        code=normalized_code or None,
        name=name or None,
        level=level or None,
        status=status,
        page=page,
        size=size,
    )
    _ensure_page_in_range(page, size, total)
    return PageResult(items=items, total=total, page=page, size=size)


# 注意：/export 必须声明在 /{entry_id} 之前，否则路径会被整数入参的接口拦截
@router.get("/export")
def export_entries(
    code: str | None = None,
    name: str | None = None,
    level: str | None = None,
) -> dict[str, Any]:
    """导出道路设施清单：与列表使用同一套筛选口径，保证导出数量与页脚总数一致。"""
    normalized_code, name, level = _parse_filters(code, name, level)
    items, total = service.list_entries(
        code=normalized_code or None,
        name=name or None,
        level=level or None,
        page=1,
        size=10000,
    )
    return {"module": "road", "total": total, "items": items}


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
