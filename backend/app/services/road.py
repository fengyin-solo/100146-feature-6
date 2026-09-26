"""道路设施业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

import math
import re
from typing import Any

from app.store import store

MODULE = "road"
REQUIRED_FIELDS = ["设施编码", "道路名称", "道路等级"]
STATUS_ORDER = ["待移交", "正常养护", "重点观测", "封闭施工"]
ACTION_RULES = {"办理移交": "正常养护", "标记观测": "重点观测", "封闭设施": "封闭施工"}
NEGATIVE_ACTIONS: list[str] = []

PAGE_SIZE_MAX = 200
CODE_EXAMPLE = "ROAD-0001"
# 设施编码只会出现字母、数字、短横线；查询时忽略大小写与短横线、空格
CODE_ALLOWED_CHARS = re.compile(r"^[0-9A-Za-z\-\s]+$")
CODE_SINGLE_CHAR = re.compile(r"[0-9A-Za-z\-\s]")
CODE_SEPARATORS = re.compile(r"[-\s]+")


def normalize_code(text: str) -> str:
    """设施编码归一化：去掉短横线与空格并转大写，让 ROAD-0001、road0001 等写法互相命中。"""
    return CODE_SEPARATORS.sub("", text).upper()


def _contains(haystack: Any, needle: str) -> bool:
    return needle.lower() in str(haystack or "").lower()


class RoadService:
    def filter_entries(
        self,
        *,
        code: str | None = None,
        name: str | None = None,
        level: str | None = None,
        status: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """按设施编码、道路名称、道路等级、设施状态取交集过滤。

        返回 (匹配记录, 错误说明)；错误说明不为 None 表示条件本身写错了，
        由路由层转成可读的 400 响应，而不是静默返回空表。
        """
        rows = store.rows(MODULE)
        code_key = (code or "").strip()
        if code_key:
            if not CODE_ALLOWED_CHARS.match(code_key):
                bad = "、".join(sorted({ch for ch in code_key if not CODE_SINGLE_CHAR.match(ch)}))
                return [], f"设施编码只由字母、数字和短横线组成（如 {CODE_EXAMPLE}），当前输入包含不支持的字符：{bad}"
            key = normalize_code(code_key)
            rows = [row for row in rows if key in normalize_code(str(row.get("设施编码", "")))]
        name_key = (name or "").strip()
        if name_key:
            rows = [row for row in rows if _contains(row.get("道路名称"), name_key)]
        level_key = (level or "").strip()
        if level_key:
            rows = [row for row in rows if _contains(row.get("道路等级"), level_key)]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return rows, None

    def list_entries(
        self,
        *,
        code: str | None = None,
        name: str | None = None,
        level: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int, str | None]:
        """过滤加分页；条件写错或页码越界时返回可读说明，而不是静默给空页。"""
        if page < 1:
            return [], 0, f"页码从 1 开始，第 {page} 页不存在"
        if size < 1:
            return [], 0, "每页条数至少为 1"
        if size > PAGE_SIZE_MAX:
            return [], 0, f"每页最多 {PAGE_SIZE_MAX} 条，请缩小分页范围"
        rows, error = self.filter_entries(code=code, name=name, level=level, status=status)
        if error:
            return [], 0, error
        total = len(rows)
        pages = max(1, math.ceil(total / size))
        if page > pages:
            return [], total, f"第 {page} 页超出范围：当前筛选条件下共 {total} 条记录、{pages} 页"
        start = (page - 1) * size
        return rows[start:start + size], total, None

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
        entry["设施状态"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"道路设施 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于道路设施可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["设施状态"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"道路设施已{action}"
