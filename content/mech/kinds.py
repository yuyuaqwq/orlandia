# -*- coding: utf-8 -*-
"""P4 下沉（2026-09-13）：与游戏仓 `game/data/kinds.py` 同内容同源（= 原 `saintess_engine/kinds/__init__.py` 逐字搬）。

下沉原因：引擎内部零消费者（`grep -rn "SkillKind\|K_PHYS\|import kinds" saintess_engine/` 排除自身后为空），中文 kind 词表属**内容侧**；引擎只经 `config.mount(kinds=...)` 注入面（`config.kind_of` → `battle.actions._kind`）读它。

技能/伤害类型域（v176 去魔法字符串重构）。

背景：battle.py 里 `kind == "物理"` 中文字符串散落 30+ 处——
- 拼写错难查（运行时才炸）
- 加新伤害类型要全局 grep 改
- 类型属性（伤害通道/抗性/暴击/吸血/段类型）散在各函数各自 if

本模块集中定义类型域，提供：
  SkillKind   枚举：物理/魔法/魔法·元素/治疗/增益/被动/召唤/真伤/嘲讽
  KIND_*      常量别名（避免 enum 成员比较啰嗦，兼容 == 语义）
  kind_meta() 类型元数据表（段类型 phys/magi/true、是否伤害、吸血通道…）
  kind_is()   前缀/包含匹配（魔法·火 → 魔法）

用法（渐进式替换 battle.py / engine.py / combat.py 的中文比较）：
  if SKIND.is_kind(kind, SKIND.MAGI):        # 魔法 或 魔法·火 都 True
  if kind == SKIND.PHYS:                     # 精确物理
  meta = SKIND.meta(kind)                     # {"seg": "phys", "dmg": True, ...}

★ D7（2026-09-17）「数据进表」：`_KIND_META` 已搬出代码 → 包内域 `content/data/kind_meta.json`
（域 id = `kind_meta`，kind=data，已登记）为**唯一真源**；本文件只留读口 `_read_kind_meta()`。
值/类型/序与搬前逐名对拍相等（`out/raw/00_before.json` ↔ `out/raw/01_after.json`，diff 空）。
"""
from __future__ import annotations

import json
import os

from enum import Enum

# ★ 本模块**必须能按文件路径独立加载**（`tests/test_numeric_skill_kinds.py` 用
#   `spec_from_file_location` 直接 exec 本文件，进程里没有引擎/包上下文）⇒ 读口只用
#   stdlib（json/os），**不 import `saintess_engine.records`**；口径照
#   `records.resolve_domain` 的三道校验（声明在 → kind 有落点 → 文件在盘）自持实现，
#   见下方 `_read_kind_meta()`。

_HERE = os.path.dirname(os.path.abspath(__file__))          # <pkg>/content/mech
_CONTENT = os.path.dirname(_HERE)                           # <pkg>/content
_PKG_ROOT = os.path.dirname(_CONTENT)                       # <pkg>


class SkillKind(str, Enum):
    """技能类型（与 skills.py 数据 kind 字段同值；元素魔法用 '魔法·X' 子串）。"""
    PHYS = "物理"
    MAGI = "魔法"
    HEAL = "治疗"
    BUFF = "增益"
    PASSIVE = "被动"
    SUMMON = "召唤"
    TRUE = "真伤"
    TAUNT = "嘲讽"

    @property
    def seg(self) -> str:
        """伤害段类型：phys/magi/true（engine.calc_damage dmg_type 用）。"""
        return _KIND_META[self]["seg"]

# 便捷常量（字符串值，与数据/旧代码天然兼容）
K_PHYS = SkillKind.PHYS.value
K_MAGI = SkillKind.MAGI.value
K_HEAL = SkillKind.HEAL.value
K_BUFF = SkillKind.BUFF.value
K_PASSIVE = SkillKind.PASSIVE.value
K_SUMMON = SkillKind.SUMMON.value
K_TRUE = SkillKind.TRUE.value
K_TAUNT = SkillKind.TAUNT.value

# 类型元数据（集中定义类型行为，杜绝各函数散落 if）
#   ★ D7（2026-09-17）「数据进表」：本表已搬出代码 → 包内域 `content/data/kind_meta.json`
#   为**唯一真源**（`editor/domains.json` 登记 kind=data）；本处只留读口。
#   类型还原（不还原 = 静默错值）：
#     · JSON 只有 str 键 ⇒ 键还原成 `SkillKind` 成员。`SkillKind` 是 `str, Enum`，
#       成员 == 其值但 **hash 不同**（`Enum.__hash__ = hash(self._name_)`）⇒
#       str 键的表用 `[SkillKind.PHYS]` 查恒 KeyError，必须还原。
#     · `damage` 的 bool 由 json 的 true/false 原样还原（不是 0/1）。
# ============================================================
class KindMetaDomainError(RuntimeError):
    """`kind_meta` 域装载失败（fail-closed：声明缺 / 落点不符 / 文件缺 / 形状错 → 点名抛）。"""


def _read_kind_meta() -> dict:
    """读 `content/data/kind_meta.json` 的 `KIND_META` 段 → `{SkillKind: {...}}`（fail-closed）。

    ★ D7 读口。**本模块不能 import 引擎**（见文件上方说明）⇒ 这里用 stdlib 实现与
    `saintess_engine.records.resolve_domain` 同口径的三道校验 + 值形状校验；任一不满足即
    `KindMetaDomainError` **点名抛**（域文件缺 / 声明缺 / 落点不符 / 键型不符 → 绝不静默给空表）。
    """
    decl_path = os.path.join(_PKG_ROOT, "editor", "domains.json")
    try:
        with open(decl_path, encoding="utf-8") as f:
            decl = json.load(f)
    except FileNotFoundError:
        raise KindMetaDomainError("包内域声明文件不存在：%s（拒绝装载，不静默给空表）"
                                  % (decl_path,))
    except Exception as exc:                                  # noqa: BLE001
        raise KindMetaDomainError("包内域声明读不了 / 坏 JSON：%s（%s: %s）"
                                  % (decl_path, type(exc).__name__, exc))
    entry = decl.get("kind_meta") if isinstance(decl, dict) else None
    if not isinstance(entry, dict):
        raise KindMetaDomainError("域 kind_meta 不在包内域声明里（%s）—— 声明缺项，拒绝装载"
                                  % (decl_path,))
    kind_dir = entry.get("kind")
    if kind_dir not in ("data", "rules"):
        raise KindMetaDomainError("域 kind_meta 的 kind=%r 没有对应落点（已知 data/rules）"
                                  % (kind_dir,))
    path = os.path.join(_PKG_ROOT, "content", kind_dir, "kind_meta.json")
    if not os.path.isfile(path):
        raise KindMetaDomainError("域 kind_meta 声明的文件不在盘上：%s —— 缺表即报错，"
                                  "不许静默给空表" % (path,))
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except Exception as exc:                                  # noqa: BLE001
        raise KindMetaDomainError("域文件读不了 / 坏 JSON：%s（%s: %s）"
                                  % (path, type(exc).__name__, exc))
    raw = doc.get("KIND_META") if isinstance(doc, dict) else None
    if not isinstance(raw, dict) or not raw:
        raise KindMetaDomainError("域文件 %s 的 KIND_META 段不是非空映射：%r"
                                  % (path, raw))
    out: dict = {}
    for name, meta in raw.items():
        try:
            member = SkillKind(name)
        except ValueError as exc:
            raise KindMetaDomainError(
                "kind_meta 域的键 %r 不是合法 SkillKind（合法值=%r）"
                % (name, [m.value for m in SkillKind])) from exc
        out[member] = meta
    return out


_KIND_META = _read_kind_meta()

# 伤害型 kind（物理/魔法/魔法·X/真伤）
_DMG_KINDS = {SkillKind.PHYS, SkillKind.MAGI, SkillKind.TRUE}


def is_damage_kind(kind: str) -> bool:
    """kind 是否为伤害类型（含元素魔法前缀 魔法·火 等）。"""
    if not kind:
        return False
    base = kind.split("·")[0] if "·" in kind else kind
    try:
        return SkillKind(base) in _DMG_KINDS
    except ValueError:
        return False


def is_kind(kind: str, target: SkillKind) -> bool:
    """kind 是否为目标类型（魔法·火 也算 魔法；精确类型 == 同值）。"""
    if not kind:
        return False
    if "·" in kind and target is SkillKind.MAGI:
        return kind.startswith(SkillKind.MAGI.value)
    return kind == target.value


def seg_of(kind: str) -> str:
    """段类型（phys/magi/true）。元素魔法/治疗/增益 → magi；真伤 → true。未知 kind → magi 保守。"""
    if not kind:
        return "magi"
    if "·" in kind:
        return "magi"
    try:
        return _KIND_META[SkillKind(kind)]["seg"]
    except ValueError:
        # 未知 kind：若以 魔法 开头（未来元素）按 magi；否则保守 magi
        return "magi"


def lifesteal_channel_of(kind: str) -> str:
    """吸血通道（phys/magi/true/空=不吸血）。"""
    if not kind or "·" in kind:
        # 元素魔法 → magi 通道
        return "magi" if kind and "·" in kind else ""
    try:
        return _KIND_META[SkillKind(kind)]["lifesteal"]
    except ValueError:
        return ""
