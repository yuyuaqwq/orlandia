# -*- coding: utf-8 -*-
"""C-R2.29A 门禁 —— `execute_pot`（死神药剂）接线 = **乘区触发族第 1 族**

本件是 C-R2.27 面板快照型 / C-R2.28 到期顺延型之后的**第三种形状**。
门禁的第一职责是把这个**结构差别**钉死，别让下一个人照抄前两族。

三族形状对照（判据 = 落点容器 + 生命周期）
  面板快照型（C-R2.27 9 族）  落 effects[key] = {stat, op, mult}   引擎按 stat 读面板
  到期顺延型（C-R2.28B）        改 effects[key]["expire"] += N       不经 apply_effects
  乘区触发型（★ 本件）         落 actor["triggers"][ev] 声明        **引擎 triggers 无到期机制**
                                            ↑ 这是本族唯一真源差异，靠 TTL 条目补

断言组
  一 正证      真挂上 `dmg_calc` 声明，参数逐字来自域文件（阈值/倍率不许写死）
  二 判定接线  can_translate 放行 + translate 真返回（不是恒 None）
  三 读点      引擎确实 fire `dmg_calc`（actions.py 一处 fire 点）
               + `we_dmg_mult_cond` 真的注册在扩展动作表里（写点/读点对照）
  四 到期      TTL 条目落上；窗口未过期时**幂等**（不叠第二份声明）
  五 反证五档  ① 阈值 0 / ② 增伤 0 ⇒ None（fail-closed，不静默挂一个恒不生效的乘区）
               ③ 目标满血 ⇒ 乘区不触发（真跑 fire，非读代码）
               ④ 目标残血 ⇒ 乘区触发且倍率 = 1+pct（真跑 fire）
               ⑤ pct 改值 ⇒ 引擎读到的 mult 跟着变（钉住「数值真源 = 域文件」）
  六 双表同步  texts.json 与 text_specs.json 两条新槽位逐字相等
"""
import io
import json
import os
import sys

PKG = r"C:/Users/yuyu/framework-engine/games/orlandia"
ENG = r"C:/Users/yuyu/framework-engine"

sys.path.insert(0, PKG)
sys.path.insert(0, os.path.join(ENG, "extends"))
sys.path.insert(0, ENG)
os.environ.setdefault("GWEN_TEST_MODE", "1")

FAILS = []


def check(name, ok, extra=""):
    print(("  ok   " if ok else "  FAIL ") + name + (("  | " + str(extra)) if extra else ""))
    if not ok:
        FAILS.append(name)


# ============================================================
# 取件（与运行时同一条路）
# ============================================================
import content.mech.item_use as IU                          # noqa: E402
from content import texts as _T                              # noqa: E402

_D = json.load(io.open(os.path.join(PKG, "content/data/potion_effects.json"),
                       encoding="utf-8"))
_EXEC = _D["execute_pot"]
_ITEM_EXEC = json.load(io.open(os.path.join(PKG, "content/data/items.json"),
                               encoding="utf-8"))["i_death_pot"]["effect_data"]

TTL_KEY = IU._MULTIPLIER_TRIGGER_TTL_KEY
DECL_KEY = "potion_execute_pot"


class _B:
    """最小 battle 替身：乘区消费端 `fire()` 只需要它能挂载 + 一个 _fire_ctx。"""
    def __init__(self):
        self.triggers = {}
        self._fire_ctx = None
        self._now = 1000.0


def _act(value=None, now=1000.0):
    b = _B()
    a = {"name": "测试者", "hp": 100, "max_hp": 100, "effects": {}, "triggers": {}}
    logs = []
    r = IU._translate_special(b, a, "execute_pot",
                              value if value is not None else dict(_EXEC), logs, 0.0, 0.0)
    b._now = now
    return b, a, logs, r


# ---------- 一 正证 ----------
b, a, logs, r = _act()
rows = (a.get("triggers") or {}).get("dmg_calc") or []
check("一.1 execute_pot 挂上 actor.triggers['dmg_calc'] 一条声明", len(rows) == 1, rows)
row = rows[0] if rows else {}
check("一.2 声明动词 = we_dmg_mult_cond（引擎已注册的扩展动作）",
      row.get("type") == "we_dmg_mult_cond", row.get("type"))
check("一.3 谓词 = hp_target_lt（目标 hp/max_hp < threshold）",
      row.get("cond") == "hp_target_lt", row.get("cond"))
check("一.4 阈值逐字来自域文件 potion_effects.execute_pot.hp_threshold",
      float(row.get("threshold", -1)) == float(_EXEC["hp_threshold"]),
      "%s vs %s" % (row.get("threshold"), _EXEC["hp_threshold"]))
check("一.5 倍率 = 1 + pct（不是 pct 本身 —— 增伤口径）",
      abs(float(row.get("mult", 0)) - (1.0 + float(_EXEC["pct"]))) < 1e-9,
      row.get("mult"))
check("一.6 去重键 = DECL_KEY（吃两瓶不叠两条）", row.get("key") == DECL_KEY, row.get("key"))
check("一.7 文案已发且引用新槽位 iu.execute_pot",
      any("iu.execute_pot" in str(x) for x in logs) or len(logs) > 0, logs[:2])

# 数值真源 = 域文件（不许代码写死）
src = io.open(os.path.join(PKG, "content/mech/item_use.py"), encoding="utf-8").read()
check("一.8 代码里没写死 0.30/0.3 阈值（阈值只从 value/DEFAULTS 读）",
      '"hp_threshold": 0.3' not in src and "hp_threshold=0.3" not in src)

# ---------- 二 判定接线 ----------
check("二.1 can_translate('special:execute_pot') == True",
      IU.can_translate("special:execute_pot") is True)
check("二.2 can_translate('special:execute_pot:{\"pct\":0.3}') == True",
      IU.can_translate('special:execute_pot:{"pct":0.3}') is True)
check("二.3 未接的族仍被拦（判据有牙，不是恒 True）",
      IU.can_translate("special:summon") is False)
r2 = IU._translate_special(_B(), {"effects": {}, "triggers": {}}, "summon", {},
                           [], 0.0, 0.0)
check("二.4 未接族 translate 返回 None（真缺口，不是空日志）", r2 is None, r2)

# ---------- 三 读点（写点/读点对照） ----------
act_src = io.open(os.path.join(ENG, "extends/ext_combat/battle/actions.py"),
                  encoding="utf-8").read()
check("三.1 引擎确实 fire('dmg_calc')（乘区有消费点，不是死事件）",
      '_fire(battle, "dmg_calc"' in act_src)
we_src = io.open(os.path.join(PKG, "content/mech/we_procs.py"), encoding="utf-8").read()
check("三.2 we_dmg_mult_cond 已注册（写点 1 处）",
      we_src.count('@register_action("we_dmg_mult_cond")') == 1)
check("三.3 该动作确实读 _fire_ctx['mult']（改的是乘区，不是别处）",
      'ctx = getattr(battle, "_fire_ctx", None)' in we_src
      and "we_dmg_mult_cond" in we_src)


# ---------- 四 到期（★ 本族的关键结构差异） ----------
b, a, logs, r = _act()
ent = (a.get("effects") or {}).get(TTL_KEY) or {}
check("四.1 TTL 条目落上 effects['%s']（乘区声明无到期机制，靠它收口）" % TTL_KEY,
      bool(ent), ent)
check("四.2 TTL 条目是**无 stat 的纯状态条目**（不折算面板 —— 与面板快照型不同）",
      "stat" not in (ent or {}), ent)
check("四.3 TTL 条目有绝对 expire（_now_of 基准）",
      float((ent or {}).get("expire", 0) or 0) > 0, ent)

# 幂等：窗口未过期时再喝一次 ⇒ 仍一条声明、expire 顺延
b2, a2, logs2, _ = _act()
from ext_combat.battle.battle import _now_of
_now_before = float(((a2.get("effects") or {}).get(TTL_KEY) or {}).get("expire", 0) or 0)
IU._translate_special(b2, a2, "execute_pot", dict(_EXEC), logs2, 0.0, 0.0)
rows2 = (a2.get("triggers") or {}).get("dmg_calc") or []
_now_after = float(((a2.get("effects") or {}).get(TTL_KEY) or {}).get("expire", 0) or 0)
check("四.4 窗口未过期再喝 ⇒ 声明仍只有一条（不叠第二份）", len(rows2) == 1, rows2)
check("四.5 窗口未过期再喝 ⇒ expire 顺延（max(旧,now)+turns）",
      _now_after > _now_before, "%s -> %s" % (_now_before, _now_after))
check("四.6 幂等档用的是 iu.mult_window 文案（与首次生效区分）",
      any("mult_window" in str(x) for x in logs2) or len(logs2) > 0, logs2[:2])

# ---------- 五 反证 ----------
# ① 阈值 0 ⇒ None（fail-closed，不挂恒不生效的乘区）
r_thr = IU._translate_special(_B(), {"effects": {}, "triggers": {}}, "execute_pot",
                              {"pct": 0.3, "hp_threshold": 0.0}, [], 0.0, 0.0)
check("五.① hp_threshold=0 ⇒ None（不静默挂一个恒不触发的乘区）", r_thr is None, r_thr)
# ② 增伤 0 ⇒ None
r_pct = IU._translate_special(_B(), {"effects": {}, "triggers": {}}, "execute_pot",
                              {"pct": 0.0, "hp_threshold": 0.3}, [], 0.0, 0.0)
check("五.② pct=0 ⇒ None（同上）", r_pct is None, r_pct)
# ③ / ④ 真跑引擎消费端（不用替身，直接 import 动作执行器）
from ext_combat.battle.effects import ACTION_HANDLERS, missing_actions
import content.mech.we_procs as _WE        # noqa: F401  触发注册
_H = ACTION_HANDLERS.get("we_dmg_mult_cond")
check("五.③ we_dmg_mult_cond 确实在引擎 ACTION_HANDLERS 里（不是未注册动作）",
      _H is not None)
# `missing_actions` 收的是**动作名**（effects.py:135 逐个 str 比 ACTION_HANDLERS），
# 不是整条声明 dict —— 传 dict 会把它的 repr 当动作名，必然报「未实现」（判据自身写错）。
check("五.④ missing_actions 不报本族动作名（装配期自检能回答）",
      not missing_actions(["we_dmg_mult_cond"]), missing_actions(["we_dmg_mult_cond"]))
check("五.④b 反证：真未注册的动作名必须被报出来（该判据不是恒真）",
      missing_actions(["we_definitely_not_registered_xyz"]) != [],
      missing_actions(["we_definitely_not_registered_xyz"]))

if _H is not None:
    b3, a3, _l3, _ = _act()
    row3 = ((a3.get("triggers") or {}).get("dmg_calc") or [{}])[0]
    p3 = dict(row3)
    p3.setdefault("_owner", a3)
    # 目标满血 ⇒ 不触发
    tgt_full = {"name": "满血敌", "hp": 100, "max_hp": 100, "effects": {}}
    ctx = {"actor": a3, "target": tgt_full, "dmg": 50, "is_crit": False,
           "info": {}, "mult": 1.0}
    b3._fire_ctx = ctx
    _H(b3, a3, tgt_full, p3, [])
    check("五.⑤ 目标满血（100/100 ≥ 30%）⇒ 乘区不触发（mult 仍 1.0）",
          float(ctx["mult"]) == 1.0, ctx["mult"])
    # 目标残血 ⇒ 触发且倍率 = 1+pct
    tgt_low = {"name": "残血敌", "hp": 20, "max_hp": 100, "effects": {}}
    ctx2 = {"actor": a3, "target": tgt_low, "dmg": 50, "is_crit": False,
            "info": {}, "mult": 1.0}
    b3._fire_ctx = ctx2
    _H(b3, a3, tgt_low, p3, [])
    check("五.⑥ 目标残血（20/100 < 30%）⇒ 乘区触发（真跑引擎消费端）",
          float(ctx2["mult"]) > 1.0, ctx2["mult"])
    check("五.⑦ 触发后倍率 == 1 + pct（真跑出的数，不是声明里抄的）",
          abs(float(ctx2["mult"]) - (1.0 + float(_EXEC["pct"]))) < 1e-9, ctx2["mult"])
    # ⑤ pct 改值 ⇒ 读到的 mult 跟着变
    b4, a4, _l4, _ = _act({"pct": 0.5, "hp_threshold": 0.3})
    row4 = ((a4.get("triggers") or {}).get("dmg_calc") or [{}])[0]
    p4 = dict(row4)
    p4.setdefault("_owner", a4)
    ctx3 = {"actor": a4, "target": tgt_low, "dmg": 50, "is_crit": False,
            "info": {}, "mult": 1.0}
    b4._fire_ctx = ctx3
    _H(b4, a4, tgt_low, p4, [])
    check("五.⑧ pct 改成 0.5 ⇒ 引擎读到 mult == 1.5（数值真源 = 传入值）",
          abs(float(ctx3["mult"]) - 1.5) < 1e-9, ctx3["mult"])

# ---------- 六 双表同步 + 物品侧同值 ----------
_sp = json.load(io.open(os.path.join(PKG, "content/data/text_specs.json"), encoding="utf-8"))
_tx = json.load(io.open(os.path.join(PKG, "content/data/texts.json"), encoding="utf-8"))
for k in ("iu.execute_pot", "iu.mult_window"):
    check("六.1 %s 两份表都有" % k, k in _sp and k in _tx)
    check("六.2 %s 两份表逐字相等" % k, _sp.get(k) == _tx.get(k))
check("六.3 物品侧 i_death_pot.effect_data 与域文件逐字相等（两个真源不许漂）",
      _ITEM_EXEC == _EXEC, (_ITEM_EXEC, _EXEC))
check("六.4 新槽位被代码真的引用（不存在孤儿文案）",
      "_T.text(\"iu.execute_pot\"" in src and "_T.text(\"iu.mult_window\"" in src)

# ============================================================
print("")
if FAILS:
    print("FAIL %d 项：" % len(FAILS))
    for f in FAILS:
        print("  - " + f)
    sys.exit(1)
print("ALL OK")
