# -*- coding: utf-8 -*-
"""包内社交·宠物/坐骑域（`content/social_pet.py`）—— 真源 `game/commands/social.py` 的宠物/坐骑编排。

真源（游戏仓 `qqbot/data/plugins/dragonfall`，**只读**）
--------------------------------------------------------
| 真源 | 本文件搬什么 |
|---|---|
| `game/commands/social.py:672-729 pet_view` | 宠物面板（饱食度衰减结算+持久化 / 品质 / 出处 / 技能 / 亲密度 / 加成行） |
| `game/commands/social.py:751-898 pet_feed` | 喂养全族：无参食物清单 / 批量双格式解析 / 食物白名单 / 单次与批量结算（升级循环） |
| `game/commands/social.py:917-993 mount_cmd` | 骑乘/下马/坐骑面板（拥有校验 / 获取渠道提示 / 等级门槛 / 面板行） |
| `game/commands/social.py:688-703 pet_rename` | 改名（**B12-L1**：宠物存在守卫 + 取前 8 字 + 落库 + 文案，见 `pet_rename_run`） |
| `game/commands/social.py:716-728 pet_release` | 放生（**B12-L1**：宠物存在守卫 + 落库 + 文案，见 `pet_release_run`） |

**未搬**（留在命令层的 IO/渲染壳）：`_tip(...)` 随机提示行、`_strip_cmd` 解析、
`yield event.plain_result`（B12-L1 起 `pet_rename` / `pet_release` 的正文已进本模块）。

宿主耦合替身（**只改两类东西**：① 存储层 ② 读表口）
----------------------------------------------------
| 真源写法 | 包内写法 | 说明 |
|---|---|---|
| `from .. import db` + `db.xxx(...)` | 模块级 `db` = 惰性宿主代理 `_HostDB` | 正文 `db.xxx` 一行未改；注入优先 → 已加载宿主模块（**不 import**） |
| `ITEMS` / `MATERIALS` / `PET_POOL` / `MOUNT_BY_KEY` / `MOUNT_POOL`（真源写法 `C.<名>`） | **包内门面直取**：`catalog_items`（`_ci`）/ `catalog_life`（`_cl`） | ★ B14-2 L6：切共享门面（宿主 `game/data` 删掉后本域仍能活）；`b14_catalog_gate.py` 对拍逐值 + 键序相等 |
| `C.PET_MAX_LEVEL` / `C.PET_SKILL_UNLOCK_LV` / `C.pet_exp_need()` / `C.pet_exp_bonus()` / `C.pct_str()` / `C.pet_skill_label()` / `C.pet_quality_label()` | **两名数据表切包内门面** `catalog_b143`（`_b143`，★ B14-3 2026-09-14；两名的域 B14-3 已建、门禁逐值相等）；其余 `C.<函数名>` 仍走 `bind_host(content=C)` 注入的**读表口** `_content()` | `PET_MAX_LEVEL` / `PET_SKILL_UNLOCK_LV` 原为缺口名，B14-3 收口后切净；函数名句柄非数据名，按总则保留 |
| `from ..data.equipment import QUALITY as _Q`（坐骑面板品质色） | `QUALITY()`（`bind_host(quality=C.QUALITY)` 注入；兜底 ★ B14-3 改读包内门面 `_b143.QUALITY`） | `QUALITY` 的域已由 B14-3 建立（`catalog_b143`，门禁逐值+键序相等）→ 兜底不再直取宿主 `game/data` |

返回结构（与真源逐字一致）
--------------------------
`pet_view(qq_id)` → `(lines, has_pet)`：`has_pet=True` 时 lines = 面板主体行（**未含** `_tip` 行，
由命令层补）；`False` 时 lines = `[无宠物文案]`（含图鉴行时是**一条**含 `\n` 的消息）。
`pet_feed(group_id, qq_id, mat_name)` → 待 yield 的**消息 list**（真源每个分支 yield 一条 → 单元素 list）。
`mount_run(group_id, qq_id, player, raw, cmd)` → 同上（面板分支是**一条多行消息**）。
`pet_rename_run(qq_id, raw_name)` / `pet_release_run(qq_id)` → 待 yield 的消息 list（B12-L1 收口搬入）。

用法::

    from content import social_pet as SP
    SP.bind_host(db, content=C, quality=C.QUALITY)
    lines, has_pet = SP.pet_view(qq_id)
"""
from __future__ import annotations

# ★ B14-2 L6：数据表切包内门面（宿主 `game/data` 删掉后本域仍能活）
from . import catalog_items as _ci        # ITEMS / MATERIALS
from . import catalog_life as _cl         # PET_POOL / MOUNT_POOL / MOUNT_BY_KEY
from . import catalog_b143 as _b143       # B14-3：PET_MAX_LEVEL / PET_SKILL_UNLOCK_LV（原缺口名已建域）
from . import texts as _T                 # C 档 20d（2026-09-19）：文案表读口（本文件首次接入）

# ============================================================
# ① 宿主替身口（存储层 / 读表口 / 品质色表）
# ============================================================
from saintess_engine.wire import Wire

#: 注入句柄面（`bind_host()` 写；`None` = 没给）——槽名 = `bind_host` 形参名
_WIRE = Wire()

from ._hostref import HOST_PKG, HOST_PKG_FALLBACK, make_bound_host  # 宿主包名常量单源（P0-3）


def bind_host(db=None, content=None, quality=None):
    """宿主替身注入（幂等；宿主薄壳在 import 期调用）。"""
    _WIRE.bind(db=db, content=content, quality=quality)


_bound_host = make_bound_host(_WIRE, "social_pet")


class _HostDB:
    """惰性宿主存储层代理（真源 `from .. import db`）——`db.xxx` 正文不动，属性访问时解析。"""

    def __getattr__(self, name):
        return getattr(_bound_host("db"), name)


db = _HostDB()


def _content():
    """宿主内容读表口（真源 `from .. import content as C`）。"""
    return _bound_host("content")


def QUALITY() -> dict:
    """装备品质色表（真源 `from ..data.equipment import QUALITY`；注入优先）。

    ★ B14-3（2026-09-14）：兜底来源由宿主 `game/data/equipment.py` 换成包内门面
    `catalog_b143.QUALITY`（门禁 `b14_catalog_gate.py` 逐值 + 键序相等）。
    """
    _q = _WIRE.handles().get("quality")
    if _q is not None:
        return _q
    return _b143.QUALITY


# ============================================================
# ② 宠物面板（真源 `social.py:672-729 pet_view`）
# ============================================================

def pet_view(qq_id):
    """宠物面板行。返回 `(lines, has_pet)`。

    - 无宠物：`lines = [文案]`（含图鉴收集行时是**一条**含 `\\n` 的消息）、`has_pet=False`；
    - 有宠物：`lines` = 面板主体行（未含 `_tip`），且**先落库饱食度衰减**（真源同序）。
    """
    C = _content()
    pet = db.pet_get(qq_id)
    # 饱食度自然衰减（每小时 -1）先结算再展示
    pet = db.pet_decay_satiety(pet)
    if not pet:
        dex = db.pet_dex_get(qq_id)
        dex_line = ""
        if dex:
            names = [next((p["name"] for p in _cl.PET_POOL if p["key"] == k), k) for k in dex]
            dex_line = _T.text("pet.dex_line", names='、'.join(names))
        return [_T.text("pet.none_dex", dex=dex_line)], False
    pdef = next((p for p in _cl.PET_POOL if p["key"] == pet["pet_key"]), None)
    icon = pdef["icon"] if pdef else "🐾"
    # 饱食度衰减持久化
    db.pet_update(qq_id, satiety=pet["satiety"], last_sat_time=pet["last_sat_time"])
    sat = pet["satiety"]
    # v104 M17 P2：面板加成按饱食度显示实际值（与战斗实算一致：饱食度=0 减半）
    # v133.2：品质分级加成（pet_exp_bonus），显示去尾零（白宠 0.5%/级 → +0.5%）
    _pb = C.pet_exp_bonus(pet)
    if sat <= 0:
        _pb = _pb / 2
    bonus = C.pct_str(_pb)
    skill_line = ""
    if pdef:
        skill_line = _T.text("pet.skill_line", skill=C.pet_skill_label(pet['pet_key']),
                              lv=int(_b143.PET_SKILL_UNLOCK_LV))
    if sat <= 0:
        skill_line = _T.static("pet.skill_dead")
    lines = [
        _T.text("pet.header", icon=icon, name=pdef['name'] if pdef else pet['name']),
        f"━━━━━━━━━━━━",
        _T.text("pet.name_line", name=pet['name'], lv=pet['level'], max=_b143.PET_MAX_LEVEL),
    ]
    # v101.14 品质/出处展示
    if pdef:
        ql = C.pet_quality_label(pet["pet_key"])
        if ql:
            lines.append(_T.text("pet.quality", quality=ql))
        if pdef.get("source"):
            lines.append(_T.text("pet.source", source=pdef['source']))
    if skill_line:
        lines.append(skill_line.lstrip("\n"))
    lines.append(_T.text("pet.satiety", sat=sat))
    # v104 M17 P3：亲密度展示（bond 原本只写不读）
    bond = pet.get("bond", 0)
    bond_line = _T.text("pet.bond", bond=bond)
    if bond >= 50:
        bond_line += _T.static("pet.bond_bonus")
    lines.append(bond_line)
    lines.append(_T.text("pet.exp_bonus", bonus=bonus) + (_T.static("pet.exp_halved") if sat <= 0 else ""))
    lines.append("━━━━━━━━━━━━")
    return lines, True


# ============================================================
# ③ 喂养（真源 `social.py:751-898 pet_feed`）—— 返回待 yield 的消息 list
# ============================================================

def pet_feed(group_id, qq_id, mat_name: str):
    """喂养：无参列食物 / 批量双格式 / 白名单校验 / 结算（含升级循环）。

    真源每个分支 yield 一条 → 本函数**单元素 list**（命令层 `for ln in …: yield`）。
    """
    C = _content()
    pet = db.pet_get(qq_id)
    # 饱食度自然衰减先结算
    pet = db.pet_decay_satiety(pet)
    if not pet:
        return [_T.static("pet.none")]
    db.pet_update(qq_id, satiety=pet["satiety"], last_sat_time=pet["last_sat_time"])
    if not mat_name:
        # #117 喂养列表看不见：无参『喂养』列出背包可喂食物（名+数量+序号），照抄即可喂
        def _is_feed_food(it):
            d = it["data"]
            if d.get("food") or d.get("type") == "鱼":
                return True
            cfg = _ci.ITEMS.get(it["key"]) or _ci.MATERIALS.get(it["key"]) or {}
            return bool(cfg.get("food"))

        _foods = [it for it in db.get_inventory(group_id, qq_id) if _is_feed_food(it)]
        if _foods:
            _food_lines = "、".join(
                f"{i}.{it['data'].get('name', it['key'])}×{it.get('count', 1)}"
                for i, it in enumerate(_foods, 1)
            )
            return [_T.text("pet.feed_list", foods=_food_lines,
                            name=_foods[0]['data'].get('name', ''))]
        return [_T.static("pet.feed_no_food")]
    # v130.7 意见#21：批量喂养『喂养 <名>*<数量>』/『喂养 <名> <数量>』双格式
    # （对齐 v130.4『使用』批量解析）；名字后带数量时名字按子串/序号匹配
    qty = 1
    _qty_raw = None

    def _is_qty_token(tok: str) -> bool:
        return tok.isdecimal() or (tok.startswith("-") and len(tok) > 1 and tok[1:].isdecimal())

    _it_parts = mat_name.split()
    if len(_it_parts) >= 2 and _is_qty_token(_it_parts[-1]):
        _qty_raw = _it_parts[-1]
        mat_name = " ".join(_it_parts[:-1])
    elif "*" in mat_name:
        _head, _, _tail = mat_name.rpartition("*")
        _tail = _tail.strip()
        if _is_qty_token(_tail):
            _qty_raw = _tail
            mat_name = _head.strip()
        else:
            return [_T.static("pet.feed_qty_fmt")]
    if _qty_raw is not None:
        try:
            qty = int(_qty_raw)
        except ValueError:
            return [_T.static("pet.feed_qty_bad")]
        if qty < 1:
            return [_T.static("pet.feed_qty_min")]
    # v130.7 意见#22：喂养只能吃食物——白名单 = 带 food 标记的食物 + 鱼（原"材料/鱼中非食物"已剔除）
    items = db.get_inventory(group_id, qq_id)
    FOOD_TYPES = {"鱼"}

    def _is_feed_food(it):
        d = it["data"]
        if d.get("food") or d.get("type") in FOOD_TYPES:
            return True
        # v126.3 瘦身存储水合只带类字段，food 标记按 key 回查配置表（材料/消耗品同一判定）
        cfg = _ci.ITEMS.get(it["key"]) or _ci.MATERIALS.get(it["key"]) or {}
        return bool(cfg.get("food"))

    target = None
    if mat_name.isdigit():
        mats = [it for it in items if _is_feed_food(it)]
        idx = int(mat_name)
        if idx < 1 or idx > len(mats):
            return [_T.text("pet.feed_no_idx", idx=idx, total=len(mats))]
        target = mats[idx - 1]
    else:
        for it in items:
            d = it["data"]
            if _is_feed_food(it) and mat_name in d["name"]:
                target = it
                break
    if not target:
        return [_T.text("pet.feed_no_mat", mat=mat_name)]
    # v130.7 意见#21：批量喂养（对齐 v130.4『使用』批量模板）——
    # 数量超持有显式报错不扣物；循环每次扣 1 + 喂 1 次（饱食度 +30 上限 100、
    # 亲密度 +5 封顶 100、经验 +10），饱食度到 100 自动停，超上限部分不扣物品
    if qty > 1:
        if qty > target.get("count", 1):
            return [_T.text("pet.feed_max", count=target.get('count', 1), name=target['data']['name'])]
        fed = 0
        _lv0 = pet["level"]
        _lv_end = _lv0
        for _k in range(qty):
            if pet["satiety"] >= 100:
                break
            db.remove_item(group_id, qq_id, target["key"])
            _sat = min(100, pet["satiety"] + 30)
            # v105 M17 P3-6：亲密度封顶 100（面板显示 x/100，此前 99→104 显示 104/100）
            _bond = min(100, pet["bond"] + 5)
            _exp = pet["exp"] + 10
            _lv = pet["level"]
            while _lv < _b143.PET_MAX_LEVEL and _exp >= C.pet_exp_need(_lv):
                _exp -= C.pet_exp_need(_lv)
                _lv += 1
            if _lv >= _b143.PET_MAX_LEVEL:
                _exp = min(_exp, C.pet_exp_need(_b143.PET_MAX_LEVEL) - 1)
            db.pet_update(qq_id, satiety=_sat, bond=_bond, exp=_exp, level=_lv)
            pet = {**pet, "satiety": _sat, "bond": _bond, "exp": _exp, "level": _lv}
            _lv_end = _lv
            fed += 1
        _lv_s = _T.text("pet.levelup", lv=_lv_end) if _lv_end > _lv0 else ""
        _full_s = _T.static("pet.feed_full") if fed < qty and pet["satiety"] >= 100 else ""
        return [
            _T.text("pet.feed_batch", pet=pet['name'], fed=fed,
                    food=target['data']['name'], fed2=fed, qty=qty, full=_full_s, lv=_lv_s)
        ]
    # 喂食：饱食度 +30（24 章四），亲密度 +5，经验 +10
    db.remove_item(group_id, qq_id, target["key"])
    sat = min(100, pet["satiety"] + 30)
    # v105 M17 P3-6：亲密度封顶 100（面板显示 x/100，此前 99→104 显示 104/100）
    bond = min(100, pet["bond"] + 5)
    exp = pet["exp"] + 10
    lv = pet["level"]
    while lv < _b143.PET_MAX_LEVEL and exp >= C.pet_exp_need(lv):
        exp -= C.pet_exp_need(lv)
        lv += 1
    if lv >= _b143.PET_MAX_LEVEL:
        exp = min(exp, C.pet_exp_need(_b143.PET_MAX_LEVEL) - 1)
    db.pet_update(qq_id, satiety=sat, bond=bond, exp=exp, level=lv)
    lv_str = _T.text("pet.levelup", lv=lv) if lv > pet["level"] else ""
    return [_T.text("pet.feed_one", pet=pet['name'], food=target['data']['name'], lv=lv_str)]


# ============================================================
# ④ 坐骑（真源 `social.py:917-993 mount_cmd`）—— 返回待 yield 的消息 list
# ============================================================

def mount_run(group_id, qq_id, player, raw: str, msg: str, cmd: str, tip_fn):
    """骑乘 / 下马 / 坐骑面板。返回待 yield 的**消息 list**（真源每个分支 yield 一条）。

    三个 I/O 读数与一个提示壳由命令层给（本域不碰事件对象）：
      · `raw` = `self._strip_cmd(event, "骑乘")`（仅当消息以 骑乘/[At: 开头时非空）
      · `msg` = `event.get_message_str()`（**未 strip** —— 真源的 `startswith` 判据就是它）
      · `cmd` = `event.get_message_str().strip()`（下马前缀判据）
      · `tip_fn` = `self._tip("mount")` 的**惰性**壳（`lambda: self._tip("mount")`）——
        面板「有坐骑」分支才调用它。惰性是硬要求：真源也只在该分支取随机提示，
        提前调用会多消耗一次 `random` 抽签（提示池随机序列错位）。
    """
    C = _content()
    # 下马
    if cmd.startswith("下马") or raw.startswith("下马"):
        mounts = player.get("mounts") or {}
        if mounts.get("active"):
            mounts["active"] = None
            db.update_player(group_id, qq_id, mounts=mounts)
            return [_T.static("mount.dismount")]
        return [_T.static("mount.none_active")]
    # 骑乘/购买（带参数）
    if msg.startswith(("骑乘", "[At:")) or raw:
        name = (raw or "").strip()
        mounts = player.get("mounts") or {}
        owned = mounts.get("owned") or []
        # 骑乘
        if name:
            target = None
            for mk in owned:
                m = _cl.MOUNT_BY_KEY.get(mk)
                if m and name in (m["name"], mk):
                    target = m
                    break
            if not target:
                # 未拥有的坐骑 → 提示
                for m in _cl.MOUNT_POOL:
                    if name in (m["name"], m["key"]):
                        # v105 M17 P3-4：提示按真实渠道（商店直购/desc 括号渠道），
                        # 此前驼马/驯鹿/独角兽等生活渠道坐骑也提示打精英/Boss，误导玩家
                        if (m.get("price") or 0) > 0:
                            _tip = _T.text("mount.buy_hint", name=m['name'])
                        else:
                            _d = m.get("desc", "")
                            _ch = _d[_d.rindex("(") + 1:] if "(" in _d else ""
                            if "『" in _ch:
                                _ch = _ch.split("『")[0]
                            _tip = _T.text("mount.unlock_hint", channel=_ch or '打精英/Boss 掉缰绳')
                        return [_T.text("mount.not_owned", name=m['name'], tip=_tip)]
                return [_T.text("mount.no_such", name=name)]
            if player["level"] < target["lv"]:
                return [_T.text("mount.lv_gate", name=target['name'], lv=target['lv'], plv=player['level'])]
            mounts["active"] = target["key"]
            db.update_player(group_id, qq_id, mounts=mounts)
            return [_T.text("mount.ride_ok", icon=target['icon'], name=target['name'], desc=target['desc'])]
    # 坐骑面板
    mounts = player.get("mounts") or {}
    owned = mounts.get("owned") or []
    active = mounts.get("active")
    _Q = QUALITY()

    def _q_label(m):
        q = _Q.get(m.get("quality", "white"), {})
        return f"{q.get('color', '⚪')}{q.get('name', '普通')}"

    lines = [_T.static("mount.panel_title"), "━━━━━━━━━━━━"]
    if not owned:
        lines.append(_T.static("mount.panel_empty"))
    for mk in owned:
        m = _cl.MOUNT_BY_KEY.get(mk)
        if not m:
            continue
        mark = " 🟢 骑乘中" if active == mk else ""
        lines.append(f"{_q_label(m)} {m['icon']} {m['name']}{mark} — {m['desc']}")
    if owned:
        lines.append("")
        lines.append(tip_fn())
    else:
        lines.append("")
        lines.append(_T.static("mount.obtainable") + "、".join(f"{_q_label(m)}{m['name']}" for m in _cl.MOUNT_POOL))
    return ["\n".join(lines)]


# ============================================================
# ⑤ 改名 / 放生（**B12-L1** 收口搬入；真源 `social.py:688-703 pet_rename` /
#    `social.py:716-728 pet_release`）—— 返回待 yield 的消息 list
# ============================================================

def pet_rename_run(qq_id, raw_name):
    """宠物改名：宠物存在守卫 → 名字取前 8 字 → 落库。返回待 yield 的消息 list。

    真源顺序：先 `db.pet_get` 守卫（无宠物直接返回），再 `self._strip_cmd(event,"宠物改名")`
    取参。`raw_name` = 命令层 `self._strip_cmd(event, "宠物改名")` 的原样字符串
    （`strip()` 与 `[:8]` 截断是真源语义，留在包内）。
    """
    pet = db.pet_get(qq_id)
    if not pet:
        return [_T.static("pet.rename_none")]
    new_name = (raw_name or "").strip()[:8]
    if not new_name:
        return [_T.static("pet.rename_fmt")]
    db.pet_update(qq_id, name=new_name)
    return [_T.text("pet.rename_ok", name=new_name)]


def pet_release_run(qq_id):
    """放生宠物：存在守卫 → `db.pet_delete`。返回待 yield 的消息 list（真源逐字）。

    图鉴记录保留（24 章三：放生后宠物蛋可重新掉落，图鉴记录保留）。
    """
    pet = db.pet_get(qq_id)
    if not pet:
        return [_T.static("pet.release_none")]
    db.pet_delete(qq_id)
    return [_T.text("pet.release_ok", name=pet['name'])]
