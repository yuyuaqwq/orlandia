# -*- coding: utf-8 -*-
"""内容侧技能表读取（包内版）—— 逐字搬自游戏仓 `game/content_rules/skills.py`（220 行）。

真源：`C:/Users/yuyu/qqbot/data/plugins/dragonfall/game/content_rules/skills.py`
包内改动面 = **本块说明 + 下面 import/数据层（域读入）+ 末尾 2 行接线别名**，14 个函数体一字不改。
逐字证据 = `overnight/d3_skills_verify.py`（逐行 diff + 逐字段对拍，全绿）。

包内版说明（D3 技能批，2026-09-13）—— **逐字搬**，只改 import 段与数据层读口
--------------------------------------------------------------
| 真源 | 包内等价物 | 说明 |
|---|---|---|
| `from .. import content as C` | 下面 `class _ContentShim` + `C = _ContentShim()`（**W6 后只剩 `resolve`**） | 真源读聚合层 5 个符号（`PLAYER_SKILLS` / `BRANCH_SKILLS` / `TUTOR_SKILLS` / `SKILL_UP` + `resolve`）；W6 起 4 张表调用点直接读**本模块**同名模块级对象（shim 当年就是回指它们 = 同一个对象，值零变化），`C` 上只剩函数名句柄 `resolve` |
| （隐式）三张源表 | `_shape_three_tables(_T.SKILLS, _T.CLASSES)` | 包内 `content/data/skills.json` 是三表**扁平化**产物（305 条，条目带 `owner_class` / `source` / `tier` / `branch`，见游戏仓 `scripts/export_game_package.py:161 derive_skills`）→ 这里按导出器追加的 4 个字段**逆折回**真源形状（`{cls:{name,skills}}` / `{cls:{name,branches:{tier:{线:{名:info}}}}}` / `{cls:{sk:info}}`），并从条目里剥掉那 4 个追加字段 —— 于是 `skill_info` 返回的 info **与真源逐字段相等**（导出器只追加、不改值，`_put` 源码可查） |
| `from saintess_engine.battle.formulas import skill_max_level` | 同左（引擎侧纯公式，路径不变） | `skill_upgrade_cost` 用 |
| `game/data/skill_up.py:SKILL_UP` | `content/data/skill_up.json`（`skill_up` 域）→ `saintess_engine.records` 读入本模块 `SKILL_UP` | 305 条，键值逐一等于源表；落盘外层键是**字典序**（落盘规范），消费点只按 key 取、`_skill_up_name_index()` 只按 `name`（305 个 `name` 互不相同）定位，故键序不参与取值。读不到 / 坏 JSON → 导入期 raise（技能成长是引擎 `skill_up` hook，缺表 = 全技能无声无成长） |

真源读的游戏仓表（4 张）↔ 包内读口（W6 后调用点直读模块级同名对象）：

    PLAYER_SKILLS  ← content/data/skills.json（source == "player"，`_shape_three_tables` 逆折）
    BRANCH_SKILLS  ← content/data/skills.json（source == "branch"；tier/branch 还原嵌套）
    TUTOR_SKILLS   ← content/data/skills.json（source == "tutor"）
    SKILL_UP       ← content/data/skill_up.json（`skill_up` 域，`Records` 读入）
    C.resolve(...) ← content/tables.py:resolve（= 游戏仓 `game/core/index.py:47`）—— 函数名句柄，保留

已知差异（逐条 + 证据见 `overnight/d3-skills-port.md`）
----------------------------------------------------
1. `TUTOR_SKILLS` 里**空表职业键**（真源 `cls_zhan_shi` / `cls_you_xia` = `{}`）在包内域里没有对应条目
   → 逆折出的 tutor 表少这两个键。**行为等价**：`skill_info` 的导师环是 `(TUTOR_SKILLS or {}).get(cls, {}).get(...)`，
   键缺失 = 空表，结果同为 `None`；`_build_skill_key_index` 遍历空表不产出条目。
2. `resolve("skills", …)`：真源索引只有 **67** 个名字（`PLAYER_SKILLS` 扁平 + `TUTOR`，`game/data/_assembly.py:166-180`），
   包内 `tables.resolve` 覆盖 **305** 个（含分支）。**语义等价**：分支技能 key 与 `name` 逐条相同（238/238），
   真源对分支名是「查不到原样返回」、包内是「查到 key」—— 两者返回同一个字符串。
3. 引擎 hook 受体名：真源私有名 `_skill_up`（`game/bootstrap.py` 直挂）；包内给公开别名 `skill_up`（末尾 2 行），
   `skill_level_of` / `branch_path_index` / `skills_for_level` 等非 hook 函数由调用方 import。
"""
from __future__ import annotations

import os

from saintess_engine.battle.formulas import skill_max_level  # noqa: F401
from saintess_engine.records import Records

from . import tables as _T

_HERE = os.path.dirname(os.path.abspath(__file__))          # <pkg>/content
_PKG_ROOT = os.path.dirname(_HERE)                          # <pkg>

# ============================================================
# 数据层：包内扁平域 → 真源三表形状（原文 `from .. import content as C` 的等价物）
# ============================================================

# 导出器 `derive_skills` 追加的 4 个字段（不在真源 info 里，逆折时剥掉）
_ADDED_FIELDS = ("owner_class", "source", "tier", "branch")


def _shape_three_tables(skills: dict, classes: dict) -> tuple:
    """`content/data/skills.json`（305 条扁平）→ 真源三表 `(PLAYER, BRANCH, TUTOR)`。

    只按条目自带的 `source` 分表、`owner_class` 归职业、`tier`/`branch` 还原嵌套层级；
    条目里剥掉导出器追加的 4 个字段（`owner_class` / `source` / `tier` / `branch`），
    其余键值**原样带着** —— 于是 info dict 与真源逐字段相等（零默认值、零改写）。
    缺字段/形状不认识的条目**跳过**（不抛；坏域的调用方本来就 `if not info` 跳过）。
    """
    player: dict = {}
    branch: dict = {}
    tutor: dict = {}
    for key, entry in (skills or {}).items():
        if not isinstance(entry, dict):
            continue
        info = {k: v for k, v in entry.items() if k not in _ADDED_FIELDS}
        cls_id = entry.get("owner_class")
        if not cls_id:
            continue
        cls_name = classes.get(cls_id, {}).get("name") if isinstance(classes, dict) else None
        src = entry.get("source")
        if src == "player":
            player.setdefault(cls_id, {"name": cls_name, "skills": {}})["skills"][key] = info
        elif src == "branch":
            tier = entry.get("tier")
            line = entry.get("branch")
            if tier is None or line is None:
                continue
            tiers = branch.setdefault(cls_id, {"name": cls_name, "branches": {}})["branches"]
            tiers.setdefault(int(tier), {}).setdefault(line, {})[key] = info
        elif src == "tutor":
            tutor.setdefault(cls_id, {})[key] = info
    return player, branch, tutor


PLAYER_SKILLS, BRANCH_SKILLS, TUTOR_SKILLS = _shape_three_tables(_T.SKILLS, _T.CLASSES)

# 技能升级成长表（每技能独立成长曲线 + 独立满级）—— 域 `content/data/skill_up.json`（305 条）
# 字段：p=每级伤害/治疗倍率 +x%；c=每级条件倍率 +c；m=每 m 级叠层 +1；l=每级吸血比例 +2%；max=满级
# key = 稳定 id（基础/导师技 = 技能表现存 sk_id；分支技 = sk_br_<pinyin>），每条带 name=中文名
_R_UP = Records(_PKG_ROOT, "skill_up", sub="content/data")
if _R_UP.missing:
    raise ValueError(
        "skill_up 域读不到（%s）：技能成长表是引擎 skill_up hook 的唯一来源，"
        "缺表 = 全技能无声无成长 —— 报错，不许静默给空表" % (_R_UP.path,))
SKILL_UP: dict = _R_UP.all()



class _ContentShim:
    """`game/content.py` 聚合层的包内等价物 —— W6 后**只剩 `resolve`**（函数名句柄）。

    4 张数据表（`PLAYER_SKILLS` / `BRANCH_SKILLS` / `TUTOR_SKILLS` / `SKILL_UP`）W6 起由调用点
    直接读本模块同名模块级对象（shim 原先就是回指它们 ⇒ **同一个对象**，值零变化）。
    """

    @staticmethod
    def resolve(table_name: str, name_or_id: str):
        """名字或 id → id（找不到原样返回）—— `content/tables.py:resolve`（= `game/core/index.py:47`）。"""
        return _T.resolve(table_name, name_or_id)


C = _ContentShim()


# ============================================================
# 技能表读取
# ============================================================

# v48：职业/技能均用 ID 访问。表结构已变 {cls_id: {"name":.., "skills": {sk_id: def}}}
# 兼容 v48 前旧结构 {职业: {技能: def}} 的读取辅助。
def _sk_table(class_name: str) -> dict:
    class_name = C.resolve("classes", class_name)  # v48：统一转 ID
    t = PLAYER_SKILLS.get(class_name, {})
    if isinstance(t, dict) and "skills" in t:
        return t["skills"]
    return t


def _br_table(class_name: str) -> dict:
    class_name = C.resolve("classes", class_name)
    t = BRANCH_SKILLS.get(class_name, {})
    if isinstance(t, dict) and "branches" in t:
        return t["branches"]
    return t


# v177 怪物引用玩家技能：技能 key 全局唯一 → 扫全表缓存 {sk_id: (cls_id, info)}
_SKILL_KEY_INDEX: dict | None = None


def _build_skill_key_index() -> dict:
    """全量玩家技能索引：{sk_id: (所属职业, info)}——覆盖基础职业 + 分支 + 导师。
    供怪物技能引用玩家技能（存储分离、解析一套）与全局技能 key 反查。"""
    idx = {}
    for cls_id, cls in (PLAYER_SKILLS or {}).items():
        if not isinstance(cls, dict):
            continue
        for sk, info in (cls.get("skills") or {}).items():
            if sk not in idx:
                idx[sk] = (cls_id, info)
    for cls_id, brs in (BRANCH_SKILLS or {}).items():
        if not isinstance(brs, dict):
            continue
        for tier, branches in (brs.get("branches") or {}).items():
            for bname, skills in (branches or {}).items():
                for sk, info in (skills or {}).items():
                    if sk not in idx:
                        idx[sk] = (cls_id, info)
    for cls_id, t_skills in (TUTOR_SKILLS or {}).items():
        for sk, info in (t_skills or {}).items():
            if sk not in idx:
                idx[sk] = (cls_id, info)
    return idx


def skill_by_key(key: str) -> dict | None:
    """v177 按技能 key 全局查玩家技能（怪物引用玩家技能用）。查不到返回 None。
    ★ H1 修复（2026-09-18）：同 `skill_info` 发浅副本（引擎技能索引也走本函数）。"""
    global _SKILL_KEY_INDEX
    if _SKILL_KEY_INDEX is None:
        _SKILL_KEY_INDEX = _build_skill_key_index()
    hit = _SKILL_KEY_INDEX.get(key)
    if not hit:
        return None
    _info = hit[1]
    return dict(_info) if isinstance(_info, dict) else _info


def skill_owner_cls(key: str) -> str | None:
    """v177 技能 key 所属职业（怪物引用需知道怪物有没有该技能时用）。"""
    global _SKILL_KEY_INDEX
    if _SKILL_KEY_INDEX is None:
        _SKILL_KEY_INDEX = _build_skill_key_index()
    hit = _SKILL_KEY_INDEX.get(key)
    return hit[0] if hit else None


def skills_for_level(class_name: str, level: int) -> list[str]:
    """返回该职业当前等级已解锁的技能 id"""
    skills = _sk_table(class_name)
    return [name for name, info in skills.items() if info["lv"] <= level]


def is_skill_learned(class_name: str, level: int, skill_name: str, learned_skills: list | None = None) -> bool:
    """技能是否已学会(v12：必须『技能学习』花技能点学会才能使用，不再按等级自动解锁)"""
    info = skill_info(class_name, skill_name)
    if not info:
        return False
    # v48：learned_skills 是中文名（store 读回），skill_name 可能是 ID——统一 resolve 比较
    sid = C.resolve("skills", skill_name)
    return sid in [C.resolve("skills", s) for s in (learned_skills or []) if s]


def skill_info(class_name: str, skill_name: str):
    """技能详情：先查基础职业技能表，再查分支专属技能表（v26），最后查导师进阶技能（v95.23）
    v48：skill_name 接受中文名或 ID，统一 resolve 为 ID 再查（表 key 已是 sk_xxx）

    ★ H1 修复（2026-09-18）：返回**浅副本**（1 层 dict）——引擎 `battle._index_one_actor` 把本
    函数返回值原样存进 `actor["_skill_index"]`，而战斗内机制（元素流转 `elem_conv_apply`）要改写
    "本击技能 dict"；原样返回模块级表条目 = 索引项与全局表**同体** → 一次施放永久改写全进程
    技能表（跨玩家/跨战斗漂移）。副本后：改写只落在该 actor 的运行时索引项上，全局表零写；
    表内嵌套容器（exprs 等）仍共享（机制只改 element/mech 顶层键，不触嵌套）。
    """
    skill_name = C.resolve("skills", skill_name)
    info = _sk_table(class_name).get(skill_name)
    if info:
        return dict(info) if isinstance(info, dict) else info
    for tier, branches in _br_table(class_name).items():
        for bname, skills in branches.items():
            if skill_name in skills:
                _hit = skills[skill_name]
                return dict(_hit) if isinstance(_hit, dict) else _hit
    # v95.23 职业导师进阶技能（TUTOR_SKILLS 并入查询链，battle/面板共用）
    t_info = (TUTOR_SKILLS or {}).get(class_name, {}).get(skill_name)
    if t_info:
        return dict(t_info) if isinstance(t_info, dict) else t_info
    return None


def branch_skill_owner(class_name: str, skill_name: str):
    """分支专属技能归属：(tier, 分支名)；非分支技能返回 None(v26)"""
    skill_name = C.resolve("skills", skill_name)
    for tier, branches in _br_table(class_name).items():
        for bname, skills in branches.items():
            if skill_name in skills:
                return tier, bname
    return None


def branch_path_index(class_name: str, tier: int, branch_key: str):
    """分支 key 在该 tier 分支组内的 index（0/1）；找不到返回 None。

    v174：显示层用——BRANCH_SKILLS 分支 key 保持 B1 名（系统约定，如牧师 B2 key 仍
    "神谕者"），需按 tier 内位置映射到 classes.evolve_branches 的档位名（大主教/圣光先知等）。
    """
    try:
        branches = _br_table(class_name)
        blist = list((branches.get(int(tier)) or {}).keys())
        for i, bk in enumerate(blist):
            if bk == branch_key:
                return i
    except Exception:
        return None
    return None


# ============================================================
# 技能升级配置（SKILL_UP 表读）
# ============================================================

# v181 P0B-C：SKILL_UP key 已改稳定 id（见 game/data/skill_up.py 头注）。中文名→id 反查索引，
# 懒构建缓存（SKILL_UP 条目 name 字段 = 技能中文名，构建期自检保证全局唯一）。
_SKILL_UP_NAME_INDEX: dict | None = None


def _skill_up_name_index() -> dict:
    global _SKILL_UP_NAME_INDEX
    if _SKILL_UP_NAME_INDEX is None:
        _idx = {}
        for _sid, _cfg in (SKILL_UP or {}).items():
            _nm = _cfg.get("name") if isinstance(_cfg, dict) else None
            if _nm and _nm not in _idx:  # 首个赢（自检已保证 name 唯一，防御性 setdefault）
                _idx[_nm] = _sid
        _SKILL_UP_NAME_INDEX = _idx
    return _SKILL_UP_NAME_INDEX


def _skill_up(info: dict | None) -> dict:
    """按技能 info 查升级配置（v181 P0B-C：key 用稳定 id，不再用中文显示名）。

    v180 隔离：仅玩家可升级技能（带 lv 学习等级字段）参与 SKILL_UP 查表——
    怪技能（MONSTER_SKILLS，无 lv）即使 name 与玩家技能撞名（圣光弹/雷击/龙爪等 14 个）
    也不会误配玩家成长曲线（v180 P4 删默认成长后，撞名怪技能曾吃到玩家同名配置 p=10~12）。

    v181 P0B-C（方案 C，docs/archive/REFACTOR_P0B_skill_up_dedup.md §4 Step2）：
    SKILL_UP key 已从中文名改为稳定 id（基础/导师 = 技能表现存 sk_id；分支 = sk_br_<pinyin>），
    每条条目带 name=中文名。skill_info 返回的 info 不带 id 字段（三表查询链只给 info dict），
    故在此用 info['name'] 经『中文名→id』索引反查稳定 id 后按 id 查表；查不到（无配置/防御）
    再回落 SKILL_UP.get(name)——data 层当前无中文 key，此处为兼容历史语义（将来若有人
    把旧中文名当 key 塞回 SKILL_UP 不至于静默失效）。"""
    if not info:
        return {}
    if info.get("lv") is None:
        return {}
    _name = info.get("name", "")
    _sid = _skill_up_name_index().get(_name)
    if _sid:
        _hit = SKILL_UP.get(_sid)
        if _hit is not None:
            return _hit
    return SKILL_UP.get(_name) or {}


def skill_upgrade_cost(cur_lv: int, info: dict | None = None) -> int:
    """升级消耗（递增）：Lv.1→2 花1点，2→3 花2点，3→4 花3点，4→5 花4点
    v56.4：达到该技能独立满级（max）后返回 0"""
    mx = skill_max_level(info)
    if cur_lv < 1 or cur_lv >= mx:
        return 0
    return cur_lv


# ============================================================
# 技能等级查询（玩家档 + 技能 id resolve）
# ============================================================

def skill_level_of(player: dict, skill_name: str) -> int:
    """技能等级查询（v46+ 兼容）：store 读库后 skill_levels 的 key 是中文名（players.py:113 display 转换），
    入参可能是 ID 或中文名——统一 resolve 后匹配，查不到按未升级 Lv.1。
    修复 #259：技能列表/详情/战斗内此前用 ID 直接查 key 恒 fallback Lv.1（战斗内实际按 Lv.1 计算）。"""
    levels = player.get("skill_levels") or {}
    if not levels:
        return 1
    sid = C.resolve("skills", skill_name)
    for k, v in levels.items():
        if k and C.resolve("skills", k) == sid:
            return int(v or 1)
    return 1


# ============================================================
# 接线别名（**非**真源内容；真源由 `game/bootstrap.py` 直挂 hook，包内由 `content/apply.py` 挂）
# 引擎 `skill_up_fn` 受体就是这里这个函数（`fn(info) -> dict`），真源私有名 `_skill_up`，
# 包内给公开别名以免 apply.py 引私有名。逐字搬以外的**唯一**新增（2 行）。
# ============================================================
skill_up = _skill_up


__all__ = [
    "PLAYER_SKILLS", "BRANCH_SKILLS", "TUTOR_SKILLS", "SKILL_UP",
    "skill_info", "skill_by_key", "skill_owner_cls", "skills_for_level",
    "is_skill_learned", "branch_skill_owner", "branch_path_index",
    "skill_up", "skill_upgrade_cost", "skill_level_of",
]
