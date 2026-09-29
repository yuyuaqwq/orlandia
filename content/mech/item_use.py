# -*- coding: utf-8 -*-
"""saintess_engine 战斗内道具翻译器（v181.N5b4-5a I2）。

把旧引擎道具 payload（item_templates 模板产物，引擎无关中间语言）翻译成
saintess_engine actor 效果。核心不变式：效果全部落到 saintess_engine actor
（hp/mp/buffs/hot/food_effects + effects 容器条目），只调 saintess_engine 动词
（landing.heal_actor / effects.apply_effects / actor 容器直写），
引擎零道具名词。

架构（docs/archive/REFACTOR_v181P4_N5B5a_use_item_design.md §1/§2）：
    economy.use() 副本/野外战斗内分支
      → action_override 回调 (battle, action, actor, payload, target)
      → 本模块 translate(battle, actor, payload)
      → 返回 (logs, cast, recover) 或 None（未覆盖 → 调用方提示不扣道具不占刻）

payload 全谱（对齐旧 battle._do_use_item 解析序）：
    "123"              绝对恢复 HP（半身人 item_effect 加成）
    "mana:N"           回蓝
    "hm:hp,mp"         双恢复
    "buff:k1,k2"       属性增益 3 刻（EFFECT_ACTIONS 查表翻译）
    "special:kind[:json]"  特殊分发（EFFECT_ACTIONS / shield 动词 / 缺口）
    "foodfx:id,id"     食物效果（落 actor["food_effects"] 容器 + shield 特判；
                       词条执行 = 装配层批，见设计 §8）
    "hot:hp%,mp%,turns"  持续恢复（写 actor["hot"]，schedule 周期结算）
    "0"                无数值（stamina 已由 economy 处理）
    ";cast:N" / ";recovery:M" 尾缀  **两段**耗时（各自数字秒，相加落 ct；
                       cast 缺省 1.0 对齐旧 CAST_ITEM/FOOD，recovery 缺省 0.0）

数值路径（零硬编码）：buff 族查 EFFECT_ACTIONS（game/data/battle_rules.py，
N7.5b 药水/食物别名已对齐 BUFF_MULT）；shield 族读 payload json 或
potion_effects.DEFAULTS（items.py effect_data 扫描权威）；heal 加成读
engine.race_stats。缺字段 = 无此行为。

★ B8.2 线4 端口（2026-09-13，包内 `content/mech/item_use.py`）
--------------------------------------------------------------
真源（只读，未改一行）：`game/commands/battle_item_use.py`（393 行）。
本文件 = 真源**逐字搬入**，只改「import 层」五处（正文/文案/正则/数值一字未动）：

| 真源写法 | 包内写法 | 说明 |
|---|---|---|
| `from ..content_rules.apply import ensure_engine_configured`（:52） | `from ..apply import install_engine` | 包内装配入口（同一个 `install_engine`，幂等） |
| `from ..core.potion_effects import DEFAULTS`（:58） | `from ..effects.potion_effects import DEFAULTS` | 药水默认表已进包（content/effects/potion_effects.py）；导出器实测 `items.json` effect/effect_data 逐项相等 |
| `from ..services.battle_food_proc import install_food_fx`（:162） | `from .food_proc import install_food_fx` | 食物装配层已进包（content/mech/food_proc.py，B8 端口） |
| `from ..data.food_effect_data import FOOD_EFFECT_PARAMS / FOOD_EFFECT_NAMES`（:170 :181） | `_food_params()`（读包内域 `content/data/food_effects.json`） | 数值/展示名单源；19 条与真源逐项相等（`name` 字段即 FOOD_EFFECT_NAMES） |
| `from ..content_rules.panel import race_stats`（:320） | `from ..panel import race_stats` | 面板已进包（content/panel.py，D3 批次） |

调用方契约不变（宿主命令层 `game/commands/battle_item_use.py` 薄壳再导出）：
    translate(battle, actor, payload[, target]) -> (logs, cast, recover) | None
    can_translate(payload) -> bool
    make_override() -> callable(battle, action, actor, skill_name, target)
对拍证据：`overnight/_l4_snapshot.py`（改包前后逐字节等价）+ `_l4_dep_audit.py`（依赖同源）。
"""
from __future__ import annotations

import json
import re
from typing import Optional

from ext_combat.battle import game_config as _b2config   # 游戏配置取件面（第 7 批从引擎 config 搬来）
from ext_combat.battle.landing import heal_actor

from .. import texts as _T              # 文案表（C 档 PRE3-a：mech 散件句壳 → 单源）

# payload 尾部 cast/recovery 剥离（同旧 battle._item_payload_cast 剥离正则）
_CAST_RE = re.compile(r"(?:^|[;&,])\s*(?:cast|recovery):[\d.]+")

# 默认道具耗时（对齐旧引擎 CAST_ITEM=CAST_FOOD=1.0——use_item 走绝对秒，
# 不按 spd 缩放；旧 _after_actor_ct cast_mult 直用）
_DEFAULT_CAST = 1.0
# 默认**第二段**（收招）耗时：payload 没写 `recovery:` 就是 0（= 只有一段，行为不变）
_DEFAULT_RECOVER = 0.0


def _food_params() -> dict:
    """食物效果表（包内域 `content/data/food_effects.json`；数值 + `name` 展示名单源）。

    读口复用 `content/mech/food_proc.py` 的 `_food_params()`（同一份 JSON、同一份缓存）——
    不复制第二份读表器。真源此处读 `game/data/food_effect_data.FOOD_EFFECT_PARAMS /
    FOOD_EFFECT_NAMES`（同一张表的两半，导出器单向产出本 JSON）。
    """
    from .food_proc import _food_params as _fp
    return _fp()

def _load_effect_actions():
    """EFFECT_ACTIONS（游戏规则配置，命令层延迟加载）。"""
    from ..apply import install_engine as _eng_cfg; _eng_cfg()
    return _b2config.get_effect_actions()


def _load_potion_defaults():
    """特殊药水默认数值（items.py effect_data 扫描权威）。"""
    from ..effects.potion_effects import DEFAULTS as _D
    return _D


def _find_effect_action_name(table: dict, container_key: str) -> Optional[str]:
    """容器键（actor.buffs 里的 key，如 atk_up/food_atk_up）→ EFFECT_ACTIONS 名词。

    N7.5b 药水别名条目动作的 key 字段即 buffs 容器键（buff_atk → key=atk_up）。
    扫表反查首个命中（首现为准，数值全表一致约定）。
    """
    for name, acts in table.items():
        if not isinstance(acts, list):
            continue
        for a in acts:
            if isinstance(a, dict) and a.get("action") in ("apply", "buff") \
                    and a.get("key") == container_key:
                return name
    return None


# ------------------------------------------------------------
# 主入口
# ------------------------------------------------------------

def make_override():
    """saintess_engine action_override 回调工厂（I3：instance_battle/野外 from_state 后注入）。

    引擎 act() 遇非内置 action（use_item）问回调：签名
    (battle, action, actor, skill_name, target) -> (logs, cast, recover)；
    logs=None（或整条返回 None）→ 未消费（回落「未知行动类型」，命令层不占刻不扣道具）。
    翻译器把 payload（经 skill_name 参数透传）→ 引擎动词。
    """
    def _override(battle, action, actor, skill_name, target):
        if action != "use_item":
            return None, None
        return translate(battle, actor, skill_name or "", target)
    return _override


def can_translate(payload: str) -> bool:
    """纯判定 payload 翻译器能否处理（无副作用，不建 battle/actor）。

    供 economy.use() 在 remove_item 前调用：不能翻译（机制型缺口
    summon/trap/phoenix/...）→ 提示「战斗内效果未迁移」且不扣道具不占刻。
    """
    if not payload or not str(payload).strip():
        return False
    _p = str(payload).strip()
    # 剥 cast/recovery 尾缀后判前缀
    _body = re.sub(r"(?:^|[;&,])\s*(?:cast|recovery):[\d.]+", "", _p).rstrip(";,")
    if not _body:
        return True  # 仅 cast（占刻无效果——食物体力类）
    if _body.startswith(("foodfx:", "hot:", "mana:", "hm:", "buff:", "purify:")):
        return True
    if _body.startswith("special:"):
        _k = _body[8:]
        _kind = _k.split(":", 1)[0] if ":" in _k else _k
        # 面板快照型族（C-R2.27）与上两组并列 ——
        #   判定口径必须与 `_translate_special` 的分诊一致，
        #   否则出现「判定能过、执行返回 None」的双源。
        if (_kind in _EFFECT_ACTION_KEYS or _kind in _SHIELD_KINDS
                or _kind in _PANEL_SNAPSHOT_KINDS
                or _kind in _EXPIRE_EXTEND_KINDS
                or _kind in _MULTIPLIER_TRIGGER_KINDS):
            return True
        # 其余机制型 special → 缺口
        return False
    try:
        int(_body or "x")
        return True  # 纯数字 heal
    except ValueError:
        return False


def translate(battle, actor: dict, payload: str,
              target: Optional[dict] = None) -> Optional[tuple]:
    """道具 payload → (logs, cast, recover)。未覆盖（机制型缺口）→ None。

    调用方（action_override 回调）收到 None → 提示「战斗内效果未迁移，
    请在战斗外使用」，不扣道具不占刻。
    """
    if not payload:
        return None
    logs: list = []
    cast = _DEFAULT_CAST
    recover = _DEFAULT_RECOVER
    # 剥离 cast/recovery **两段**（耗时由调用方推进，不污染效果解析）
    # ★ T14 修掉旧「二选一降级」：两段并存时旧码只取 cast、静默吞掉 recovery。
    _payload = payload.strip()
    _m = re.search(r"(?:^|[;&,])\s*cast:([\d.]+)", _payload)
    if _m:
        cast = float(_m.group(1))
    _m2 = re.search(r"(?:^|[;&,])\s*recovery:([\d.]+)", _payload)
    if _m2:
        recover = float(_m2.group(1))
    if _m or _m2:
        _payload = _CAST_RE.sub("", _payload).rstrip(";,")

    # ---- 1. foodfx（食物效果：本场战斗词条族；落容器 + shield 特判 + N10-B7 装配）----
    if _payload.startswith("foodfx:"):
        aids = [a for a in _payload[7:].split(",") if a]
        if not aids:
            return None
        _fe = actor.setdefault("food_effects", [])
        for a in aids:
            if a not in _fe:
                _fe.append(a)
        # N10-B7：food aid → actor["triggers"] 装配（skill_hit/on_taken/dmg_calc 事件）
        # + effects period 周期声明（回春/冥想/晨曦）——复用 battle_food_proc 翻译表。
        # shield 特判不在此（下方独立处理）；翻译表数值读 food_effect_data 权威表。
        try:
            from .food_proc import install_food_fx
            install_food_fx(actor, aids, logs)
        except Exception:
            pass  # 装配异常不阻断吃料理（效果缺省无，文案照播——缺口可见性由测试保证）
        # shield 特判（对齐旧 _do_use_item：圣餐面包等立即给盾——数值读
        # food_effect_data 权威表）
        if "shield" in aids:
            try:
                _sh = _food_params().get("shield") or {}
                # ★ 审计 L246 同族：回落只认 None。合法值 0.0（圣餐面包 0% 盾 =
                #   「吃下去不套盾」）会被原 `or 0.10` 静默吞成 10% ⇒ 数据面写 0
                #   表达出的「无盾」在实机上照样吃到一个 10% 盾（food_effects.json
                #   的 shield.pct 是声明式字段，0 与「键缺失」语义不同）。
                _shp = _sh.get("pct")
                _sh_pct = 0.10 if _shp is None else float(_shp)
                _sh_turns = int(_sh.get("turns", 3) or 3)
                from ext_combat.battle.effects import apply_effects
                apply_effects(battle, actor, actor,
                              [{"action": "shield", "key": "food_shield",
                                "pct": _sh_pct, "turns": _sh_turns,
                                "on": "caster"}], logs)
            except Exception:
                pass  # 数据异常不阻断（护盾段可选）
        _names = [(_food_params().get(a) or {}).get("name", a) for a in aids]
        logs.append(_T.text("iu.food_fx", names='、'.join(_names)))
        return logs, cast, recover

    # ---- 1.5 purify 净化卷轴（I5：模板只判定，清除在翻译器）----
    # 清玩家侧全部存活 actor 的可净化负面（EFFECT_RULES period/on=target/cleanse；
    # sleep 不可净化）。旧模板直改 p_buffs 已随 saintess_engine 失效——负面权威在 actor.effects。
    if _payload == "purify:1":
        from ext_combat.battle.effects import apply_effects
        _cleaned = []
        _holders = []
        try:
            for _a in (battle.sides_of("player") if hasattr(battle, "sides_of") else []):
                if isinstance(_a, dict) and int(_a.get("hp", 0) or 0) > 0:
                    _holders.append(_a)
        except Exception:
            _holders = []
        if not _holders and isinstance(actor, dict):
            _holders = [actor]
        for _h in _holders:
            _before = set((_h.get("effects") or {}).keys())
            apply_effects(battle, _h, _h, [{"action": "cleanse"}], [])
            _after = set((_h.get("effects") or {}).keys())
            _rem = _before - _after
            if _rem:
                _cleaned.append((_h.get("name", "?"), sorted(_rem)))
        if _cleaned:
            _lines = [f"{_nm}：{'、'.join(_ks)}" for _nm, _ks in _cleaned]
            logs.append(_T.text("iu.purify_ok", lines='; '.join(_lines)))
        else:
            logs.append(_T.static("iu.purify_none"))
        return logs, cast, recover

    # ---- 2. hot（持续恢复：effects["regen_hot"] period 声明，schedule 周期结算）----
    if _payload.startswith("hot:"):
        _p = _payload[4:].split(",")
        hpct = float(_p[0]) if _p and _p[0] else 0.0
        mpct = float(_p[1]) if len(_p) > 1 and _p[1] else 0.0
        turns = int(_p[2]) if len(_p) > 2 and _p[2] else 3
        # V 系列：hot = effects["regen_hot"] 条目 + period 声明（动态数值随条目走）
        # 首跳延迟 1s + 每 interval 跳一次，turns 次后到期清（schedule 统一周期段）
        ef = actor.setdefault("effects", {})
        entry = ef.setdefault("regen_hot", {"stacks": 1})
        entry["period"] = {"dir": "heal", "interval": 1.0,
                           "heal_pct": hpct, "mana_pct": mpct,
                           "turns": turns}
        # 到期 = 首跳延迟后跳 turns 次：expire 兜底（schedule 用 dot_next 计数，见周期段）
        _desc = []
        if hpct > 0:
            _desc.append(_T.text("iu.hot_hp", pct=int(hpct * 100)))
        if mpct > 0:
            _desc.append(_T.text("iu.hot_mp", pct=int(mpct * 100)))
        logs.append(_T.text("iu.food_hot", desc='、'.join(_desc), turns=turns))
        return logs, cast, recover

    # ---- 3. mana 回蓝 ----
    if _payload.startswith("mana:"):
        mv = int(_payload[5:])
        if mv > 0:
            before = int(actor.get("mp", 0) or 0)
            _mx = int(actor.get("max_mp", before) or before)
            actor["mp"] = min(_mx, before + mv)
            _real = int(actor["mp"]) - before
            logs.append(_T.text("iu.mana", real=_real, mp=actor['mp'], mx=_mx))
        return logs, cast, recover

    # ---- 4. hm 双恢复 ----
    if _payload.startswith("hm:"):
        _p = _payload[3:].split(",")
        hv = int(_p[0]) if _p and _p[0] else 0
        mv = int(_p[1]) if len(_p) > 1 and _p[1] else 0
        msgs = []
        if hv > 0:
            before = int(actor.get("hp", 0) or 0)
            heal_actor(battle, actor, hv, logs)
            _real = int(actor.get("hp", 0) or 0) - before
            if _real > 0:
                msgs.append(_T.text("item.heal_flat", hp=_real))
        if mv > 0:
            before = int(actor.get("mp", 0) or 0)
            _mx = int(actor.get("max_mp", before) or before)
            actor["mp"] = min(_mx, before + mv)
            _real = int(actor["mp"]) - before
            if _real > 0:
                msgs.append(_T.text("item.mana_flat", mp=_real))
        logs.append(_T.text("iu.hm", msgs='、'.join(msgs)))
        return logs, cast, recover

    # ---- 5. special 特殊分发 ----
    if _payload.startswith("special:"):
        kind = _payload[8:]
        value = None
        if ":" in kind:
            _k, _, _j = kind.partition(":")
            try:
                _d = json.loads(_j)
                if isinstance(_d, dict) and _d:
                    value = _d
                    kind = _k
            except Exception:
                pass
        return _translate_special(battle, actor, kind, value, logs, cast, recover)

    # ---- 6. buff 属性增益（EFFECT_ACTIONS 查表）----
    if _payload.startswith("buff:"):
        kind = _payload[5:]
        keys = [k for k in kind.split(",") if k]
        if not keys:
            return None
        table = _load_effect_actions()
        # payload key（= buffs 容器键 atk_up/food_atk_up/...）→ EFFECT_ACTIONS
        # 名词（N7.5b 药水别名 buff_atk/... 的动作 key 字段即容器键）——扫表反查
        from ext_combat.battle.effects import apply_effects
        applied = []
        for _k in keys:
            _name = _find_effect_action_name(table, _k)
            if not _name:
                continue  # 单键未覆盖 → 跳过（整串已覆盖才播报）
            # 3 刻制（对齐旧 buff 持续 3 刻）；turns 由调用方给（映射动作无 turns）
            apply_effects(battle, actor, actor,
                          [{"type": _name, "turns": 3, "on": "caster"}], logs)
            applied.append(_k)
        if not applied:
            return None
        _food = any(k.startswith("food_") for k in applied)
        _nm = "、".join(applied)
        logs.append(_T.text("iu.buff", head='🍖 你吃下了料理' if _food else '🧪 你饮下战斗药水', nm=_nm))
        return logs, cast, recover

    # ---- 7. 纯数字 heal ----
    try:
        heal = int(_payload or 0)
    except ValueError:
        return None
    if heal > 0:
        # 半身人灵巧双手：消耗品效果 +10%（对齐旧 _do_use_item 4153-4156）
        rr = None
        try:
            from ..panel import race_stats
            rr = race_stats(actor.get("race")).get("item_effect")
        except Exception:
            rr = None
        if rr:
            heal = max(1, int(heal * (1 + rr)))
        before = int(actor.get("hp", 0) or 0)
        heal_actor(battle, actor, heal, logs)
        _real = int(actor.get("hp", 0) or 0) - before
        if _real > 0:
            logs.append(_T.text("iu.heal", real=_real, hp=actor['hp'], maxhp=actor.get('max_hp', '?')))
        else:
            logs.append(_T.static("iu.item_used"))
    else:
        logs.append(_T.static("iu.item_used"))
    return logs, cast, recover


# ------------------------------------------------------------
# special 分诊
# ------------------------------------------------------------

# EFFECT_ACTIONS 直映射键（N7.5b 药水/食物别名已在规则表；此处命中即通用查表翻译）
_EFFECT_ACTION_KEYS = {
    "next_atk_up", "buff_phys_next", "cc_immune", "purify_immune",
    # 纯属性别名（payload buff: 已覆盖，双保险）
    "buff_atk", "buff_def", "buff_spd", "buff_crit", "buff_matk",
    "buff_atk_big", "buff_atk_small", "buff_atk_food",
    "buff_def_food", "buff_spd_small", "buff_spd_food",
    "buff_crit_small", "buff_crit_big", "buff_crit_food",
    "buff_matk_strong", "buff_matk_food", "food_spd_up_small",
}

# shield 动词族：payload kind → 护盾**容器条目 key**（数值读 effect_data/DEFAULTS）
# ★ 收口第 2 批：条目落在 `effects` 容器里（不再是已删的独立容器 `shields`）。
_SHIELD_KINDS = {
    "shield_small": "potion_shield",
    "shield_big": "potion_shield",
    "shield": "food_shield",
}

# 面板快照型族（C-R2.27）：payload kind → **面板 stat 键**。
# 这些都是**比例属性**（全在 `panel_rules.pct_stats` 内、值 0.0-1.0）
#   ↳ op 必须 `"add"`（`mult` 在引擎里是**加成的比例**，不是乘数）。
# 键名同源 = `content/rules/panel_rules.json`、`optional_stats.json`。
_PANEL_SNAPSHOT_KINDS = {
    # C-R2.28：`heal_up`（圣光药剂）—— 治疗技能效果 +pct。落点 = 面板 `heal_power`
    #   （`panel_rules.pct_stats` 名单源内、值 0.0-1.0 比例），
    #   引擎读点 `actions._do_heal`：`min(st["heal_power"], heal_power_cap())` → `heal×(1+v)`。
    #   与上列 8 族同手法（op="add" 参数直传）；不能走查表（门禁档三钉住）。
    "heal_up": "heal_power",
    "dodge_pot": "dodge",
    "block_pot": "block",
    "crit_dmg_pot": "crit_dmg",
    "lifesteal_pot": "lifesteal",
    "thorns_pot": "thorns",
    "pene_pot": "pene_phys",
    "pene_magi_pot": "pene_magi",
    "magic_resist": "magic_reduce",
}


# 到期顺延族（C-R2.28）：payload kind → 改**已落 effects 条目的 expire**。
# `buff_extend`（时之延香）= 自身全部增益时长 +N 刻。旧 handler 的落点是
#   `p_buffs[k] = 原刻数 + N`（逐个刻计数顺延），而现行的到期只有一个真源
#   = 条目的 `expire`（`landing._apply_damage` 的收口批同族已把第二本账
#   `reduce_left` 删掉）⇒ 正解是**顺延 expire**，不新建任何形状。
# 豁免名单 = 旧 handler 原样搬过来的一次性/控制类键（语义上不该被延）。
# ★ 不需要任何 battle 替身回调（旧 handler 的战斗面只有 p_buffs 遍历）。
_EXPIRE_EXTEND_KINDS = {"buff_extend"}
# 一次性/控制类豁免（逐字承 `potion_effects.eff_buff_extend` 的同名元组）
_EXPIRE_EXTEND_EXEMPT = ("next_atk_up", "buff_phys_next", "stealth", "reduce_all",
                        "stun", "freeze")


# 乘区触发族（C-R2.29A）：payload kind → `actor["triggers"]` **事件声明**。
# ★ 这是 C-R2.27 面板快照型 / C-R2.28 到期顺延型之外的**第三种形状**：
#   前两者改「actor 身上的状态条目」，本族不落任何 effects 条目 ——
#   它挂的是**事件乘区**（`dmg_calc`/`taken_calc`），由引擎在每次伤害结算时
#   fire 出来、改 `_fire_ctx["mult"]`。语义 = 「条件增伤/条件减伤」。
# 为何不能沿用前两族：面板快照型落 `effects[key]={stat,op,mult}`（引擎按 stat 读），
#   本族是**条件触发**（目标血量低于阈值才生效）⇒ 引擎的面板通道表达不了这个条件。
#
# `execute_pot`（死神药剂）：3 刻内对**生命 < hp_threshold 的敌人**增伤 pct。
# 引擎侧读点 = `we_dmg_mult_cond`（`content/mech/we_procs.py:824`），
#   它已在 `dmg_calc` 事件上 fire，谓词 `cond="hp_target_lt"` 逐字同义
#   （`hp / max_hp < threshold`）。数值真源 = 域文件 `potion_effects.json`
#   的 `execute_pot` = {pct, hp_threshold}，与 `items.json` 的
#   `i_death_pot.effect_data` 同值（后者是物品侧那份拷贝，门禁逐字对拍）。
#
# ★ 装配器与 food 族同源（`content/mech/food_proc.py` 的 `install_food_fx`）：
#   `Compiler(events=EVENTS, key_of=key, owner_key="_owner")` 挂 `actor["triggers"]`。
#   `key_of=key` ⇒ 同 kind 同事件幂等（喝两次不叠两条）。
#   `owner_key="_owner"` ⇒ 挂载期注入归属，`fire()` 消费期再兜底一次
#   （`we_dmg_mult_cond` 读 `params["_owner"]` 判 `hp_self_*` 谓词；
#   本族只用 `hp_target_lt` 但仍按同族惯例挂上）。
# ★ 幂等与到期：`turns` 由 effects 容器管不到 —— 乘区声明**无到期机制**
#   （引擎 `triggers` 是无时限的）。故本族**必须**同时落一个到期标记条目
#   （见 `_translate_special` 分支 5 的 `_MULTIPLIER_TRIGGER_TTL_KEY`），
#   由翻译器在读取时判定是否已过期并 `Compiler.purge` 清掉。
#   —— 这是本族与前两族的**关键结构差异**，别照抄前两族。
_MULTIPLIER_TRIGGER_KINDS = {
    # kind: (事件名, 扩展动作 type, 阈值字段, 数值字段)
    "execute_pot": ("dmg_calc", "we_dmg_mult_cond", "hp_threshold", "pct"),
}
# 到期标记条目键（effects 容器）—— 挂一条**无 stat 的纯状态条目**，
#   只记录 `expire`，让「乘区还有效吗」这件事有唯一真源（= 条目是否过期）。
_MULTIPLIER_TRIGGER_TTL_KEY = "potion_execute_window"


def _translate_special(battle, actor, kind: str, value, logs: list, cast: float,
                       recover: float):
    """special 分诊：EFFECT_ACTIONS 直映射 / shield 动词 / 缺口 None。"""
    if not kind:
        return None
    # 1. EFFECT_ACTIONS 直映射（next_atk_up 等一次性/免疫——hit/纯状态 buff）
    if kind in _EFFECT_ACTION_KEYS:
        table = _load_effect_actions()
        mapped = table.get(kind)
        if isinstance(mapped, list) and mapped:
            from ext_combat.battle.effects import apply_effects
            # hit 型 buff 出手消费，expire 仅兜底 → turns 给大（装配层同族惯例），
            # 消费即清；无 turns 的动作（act_buff 要求 turns>0）会不挂
            apply_effects(battle, actor, actor,
                          [{"type": kind, "turns": 999, "on": "caster"}], logs)
            logs.append(_T.static("iu.potion_ready"))
            return logs, cast, recover
    # 2. shield 动词族（value=物品 effect_data 或 DEFAULTS；turns 缺省 3）
    if kind in _SHIELD_KINDS:
        _key = _SHIELD_KINDS[kind]
        _ed = value if isinstance(value, dict) and value else \
            (_load_potion_defaults().get(kind) or {})
        pct = float(_ed.get("pct", 0.0) or 0.0)
        turns = int(_ed.get("turns", 3) or 3)
        if pct <= 0:
            pct = 0.10  # 兜底（无数据声明 = 旧 shield 药默认 10% max_hp）
        from ext_combat.battle.effects import apply_effects
        apply_effects(battle, actor, actor,
                      [{"action": "shield", "key": _key, "pct": pct,
                        "turns": turns, "on": "caster"}], logs)
        logs.append(_T.text("iu.shield", pct=int(pct * 100), turns=turns))
        return logs, cast, recover
    # 3. 面板快照型（pct 比例属性增益，C-R2.27）
    #    与 shield 族同手法（参数直传）。不能走查表：这 8 族在
    #    `EFFECT_ACTIONS`/`EFFECT_RULES` 两表均零条目（门禁档三钉住）。
    if kind in _PANEL_SNAPSHOT_KINDS:
        _st = _PANEL_SNAPSHOT_KINDS[kind]
        _ed = value if isinstance(value, dict) and value else \
            (_load_potion_defaults().get(kind) or {})
        pct = float(_ed.get("pct", 0.0) or 0.0)
        turns = int(_ed.get("turns", 3) or 3)
        if pct <= 0:
            return None
        from ext_combat.battle.effects import apply_effects
        # op="add"：这几个都是**比例属性**（pct_stats 内，0.0-1.0）
        #   —— `mul` 会把 `dodge 0.20 × 1.15` 变 0.23（比例被放大 15%），语义错。
        # stat/op/mult 直传（引擎快照型分支读 params，不查表）。
        apply_effects(battle, actor, actor,
                      [{"action": "apply", "key": "potion_%s" % kind,
                        "turns": turns, "stat": _st, "op": "add",
                        "mult": pct, "on": "caster"}], logs)
        logs.append(_T.text("iu.potion_stat", pct=int(pct * 100), turns=turns))
        return logs, cast, recover
    # 4. 到期顺延族（C-R2.28）—— 改**已落条目**的 expire，不新建形状
    #    `turns` 语义与面板快照型一致（默认 3 刻），但**到期顺延量**从
    #    `value.extend_turns` 读（数据侧 i_shi_zhi_yan_xiang = {"extend_turns": 2}）。
    if kind in _EXPIRE_EXTEND_KINDS:
        ext = int(value.get("extend_turns", 0) or 0) if isinstance(value, dict) else 0
        if ext <= 0:
            return None
        from ext_combat.battle.battle import _now_of
        ef = actor.get("effects") or {}
        now = _now_of(battle)
        n = 0
        for k in list(ef):
            _e = ef.get(k)
            if not isinstance(_e, dict) or k in _EXPIRE_EXTEND_EXEMPT:
                continue
            # 只延「有绝对到期时刻」的条目（无 expire 的 = 不计时的一次性标记，
            # 顺延它没有语义）—— 与旧 p_buffs 刻计数口径的差别在注释里写明。
            if float(_e.get("expire", 0) or 0) <= 0:
                continue
            _e["expire"] = float(_e["expire"]) + float(ext)
            n += 1
        logs.append(_T.text("iu.buff_extend", n=n, turns=ext))
        return logs, cast, recover
    # 5. 乘区触发族（C-R2.29A）—— 挂 `actor["triggers"]` 事件声明，不落面板
    if kind in _MULTIPLIER_TRIGGER_KINDS:
        _ev, _act, _thr_f, _val_f = _MULTIPLIER_TRIGGER_KINDS[kind]
        _ed = value if isinstance(value, dict) and value else             (_load_potion_defaults().get(kind) or {})
        _thr = float(_ed.get(_thr_f, 0.0) or 0.0)
        _pct = float(_ed.get(_val_f, 0.0) or 0.0)
        _turns = int(_ed.get("turns", 3) or 3)
        # 门槛校验：阈值与增伤都必须是 (0,1] 内的正值，否则不构成「条件增伤」
        if _thr <= 0 or _pct <= 0:
            return None
        from ext_combat.battle.battle import _now_of
        from ext_combat.battle.declarations import Compiler as _Compiler
        from ext_combat.battle.effect_triggers import EVENTS as _EVENTS
        _now = _now_of(battle)
        # 已有窗口且未过期 ⇒ 幂等重挂（清旧声明重挂，避免 key 判重留下过期参数）
        _old = (actor.get("effects") or {}).get(_MULTIPLIER_TRIGGER_TTL_KEY) or {}
        _oexp = float(_old.get("expire", 0) or 0)
        if _oexp > 0 and _oexp > _now:
            # 窗口仍在 ⇒ 只延后到期，不重挂声明（重挂会把同一份乘区挂两遍）
            _old["expire"] = _oexp + _turns
            from ext_combat.battle.effects import apply_effects
            apply_effects(battle, actor, actor,
                          [{"action": "apply", "key": _MULTIPLIER_TRIGGER_TTL_KEY,
                            "turns": _turns, "on": "caster"}], [])
            logs.append(_T.text("iu.mult_window", turns=_turns))
            return logs, cast, recover
        # 窗口已过（首次喝 or 上一轮结束）⇒ 挂乘区声明 + 新窗口
        _c = _Compiler(events=_EVENTS, key_of=lambda d: d.get("key"),
                       owner_key="_owner")
        _c.mount(actor, {_ev: [{"type": _act, "key": "potion_%s" % kind,
                                "cond": "hp_target_lt", "threshold": _thr,
                                "mult": 1.0 + _pct, "tag": "💀处决"}]},
                 merge="replace")
        from ext_combat.battle.effects import apply_effects
        apply_effects(battle, actor, actor,
                      [{"action": "apply", "key": _MULTIPLIER_TRIGGER_TTL_KEY,
                        "turns": _turns, "on": "caster"}], [])
        logs.append(_T.text("iu.execute_pot", hp_th=int(_thr * 100), pct=int(_pct * 100)))
        return logs, cast, recover
    # 6. 机制型真缺口（装配层/职业批）→ None：调用方提示不扣道具
    return None
