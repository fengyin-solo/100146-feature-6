"""道路设施业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

import re
from typing import Any

from app.store import store

MODULE = "road"
REQUIRED_FIELDS = ["设施编码", "道路名称", "道路等级"]
STATUS_ORDER = ["待移交", "正常养护", "重点观测", "封闭施工"]
ACTION_RULES = {"办理移交": "正常养护", "标记观测": "重点观测", "封闭设施": "封闭施工"}
NEGATIVE_ACTIONS = []

# 设施编码的标准写法：ROAD- 前缀加 4 位数字（如 ROAD-0001）
CODE_PATTERN = re.compile(r"^ROAD-\d{4}$")
# 容错匹配：允许省略分隔符，或用下划线/空格/中文破折号代替连字符
CODE_FUZZY_PATTERN = re.compile(r"^ROAD[-_－— \t]*(\d{1,4})$", re.IGNORECASE)


def normalize_code(raw: str) -> tuple[str | None, str | None]:
    """把用户输入的设施编码归一化成标准写法；写法不合法时返回 (None, 原因)。"""
    value = raw.strip()
    if not value:
        return None, None
    if CODE_PATTERN.match(value):
        return value, None
    matched = CODE_FUZZY_PATTERN.match(value)
    if matched is None:
        if not value.upper().startswith("ROAD"):
            return None, "设施编码需以 ROAD 开头，例如 ROAD-0001"
        if "-" not in value and not re.search(r"\d", value):
            return None, "设施编码缺少编号部分，正确写法如 ROAD-0001"
        return None, "设施编码格式不正确，应为 ROAD- 加 4 位数字，例如 ROAD-0001"
    return f"ROAD-{int(matched.group(1)):04d}", None


class RoadService:
    def list_entries(
        self,
        *,
        code: str | None = None,
        name: str | None = None,
        level: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """按设施编码、道路名称、道路等级过滤，多条件取交集，再做内存分页。"""
        rows = store.rows(MODULE)
        if code:
            rows = [row for row in rows if str(row.get("设施编码", "")) == code]
        if name:
            rows = [row for row in rows if name in str(row.get("道路名称", ""))]
        if level:
            rows = [row for row in rows if level in str(row.get("道路等级", ""))]
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
            return None, f"道路设施 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于道路设施可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"道路设施已{action}"
