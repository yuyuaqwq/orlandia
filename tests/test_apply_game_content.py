# -*- coding: utf-8 -*-
"""S7 单一装配入口验收（★ P5C-REPOINT 后：观测/调用口 = 包内 `content/apply.py`）。

规格：docs/ENGINE_CONTENT_SPLIT_PLAN.md §6.6（apply_game_content 收敛）+ §7 S7。
本测试守住三条契约：

  A 接口      —— 入口存在、单参可调、返回原 actor
                 （原 A2「旧调用点清单」随宿主清单文件删除退休，见 t_a 注释）
  B 顺序契约  —— ①install → ②equip → ③mech → ④bar → ⑤cond → ⑤b element → ⑥food
                 （+ mech 内部 bar→cond 先跑）。★ B8（2026-09-13）：观测对象 = **包内实现**
                 （`content.apply` 的 `install_engine` / `_equip` / `_class_mech` / `_bar_procs` /
                 `_cond_procs` / `_element_procs` / `_food_proc`）；★ P5C-REPOINT：`APPLY` 本体
                 即 `content.apply`，宿主 `game/content_rules/apply.py` 薄壳已随 game/** 删除。
  C 引擎装配  —— boot()（原 ensure_engine_configured）幂等；规则表装载
                 （原 C2「委托 bootstrap.package_apply」随宿主中转层删除退休，见 t_c 注释）
  D 幂等      —— 同一 actor 连调 1 次 vs 2 次，序列化字节相同；零额外状态键
  E 并列对照  —— 入口 == 「EP.apply_to_actor + CM.apply_class_mech」并列调用逐字节
                 （★ P5C-REPOINT 后并列调用方 = 包内 `content.mech.equip` / `content.mech.class_mech`；
                  原「旧命令层」版本已随 game/** 删除，这里保留的是同一逐字节对照口径）
  F 数值抽样  —— 装备上限词条 / 推条注入 / 条件乘区 / 食物 四类效果照旧落地

跑法：python tests/test_apply_game_content.py（exit=0 全绿）
"""
import json
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_apply_game_content.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)

from saintess_engine import config as _b2c
from _engine_harness import boot as _eng_cfg; _eng_cfg()  # ★ P5C-REPOINT：宿主装配壳已删 → 测试侧引擎通道装配口
from saintess_engine import make_actor
from _engine_harness import C  # ★ P5C-REPOINT：包内聚合门面（原 game.content）
from content import apply as APPLY  # ★ P5C-REPOINT：装配入口真源 = 包内 content.apply（宿主壳已删）
from content.mech import bar_procs as BAR  # ★ B18-REPOINT：直取包内实现本体（宿主同名壳不再被测试引用）
from content.mech import cond_procs as COND  # ★ P5C-REPOINT：直取包内真源（原 battle_cond_procs）
from content.mech import equip as EP  # ★ P5C-REPOINT：直取包内真源（原 battle_equip_proc）
from content.mech import food_proc as FOOD  # ★ P5C-REPOINT：直取包内真源（原 battle_food_proc）
from content.mech import class_mech as CM  # ★ P5C-REPOINT：直取包内真源（原 class_mech_proc）
from content.mech.params import BAR_INJECT_FIELDS
from content.mech.we_data import WEAPON_EFFECT_DATA

# ------------------------------------------------------------
# ★ B8 观测对象同源搬迁（2026-09-13）：装配实现已归内容包
#   ★ P5C-REPOINT（2026-09-15）：`APPLY` 现在**就是**包内 `content.apply`（宿主薄壳
#   `game/content_rules/apply.py` 随 game/** 删除）——`_PKG` 因此 = 该模块自身，不再是
#   「经宿主唯一包加载口取回的包内模块」。它的 `install_engine`（模块全局）与 `_equip` /
#   `_class_mech` / `_bar_procs` / `_cond_procs` / `_element_procs` / `_food_proc` 六个模块对象，
#   就是包内 `apply_game_content` 按 ①install→②equip→③mech→④bar→⑤cond→⑤b element→⑥food
#   **调时取属性**的那批对象（`_step("equip", _equip.apply_to_actor, actor)`），故 patch
#   模块属性对观测生效 —— 与生产同源。
#   EP / CM / FOOD / COND / BAR import 仍是 E 组「并列调用对照」的被调方（现已 = 包内实现本体）。
# ------------------------------------------------------------
_PKG = APPLY        # ★ P5C-REPOINT：包内真源本体（原 APPLY._pkg_apply()）

_OBS = {
    "install": (_PKG, "install_engine"),                    # ① 引擎配置（旧 load_game_defaults 实体）
    "equip":   (_PKG._equip, "apply_to_actor"),              # ② 装备/词条/武器特效
    "mech":    (_PKG._class_mech, "apply_class_mech"),       # ③ 职业 mech
    "bar":     (_PKG._bar_procs, "apply_bar_procs"),         # ④ 挂敌身条
    "cond":    (_PKG._cond_procs, "apply_cond_procs"),       # ⑤ 技能条件乘区
    "element": (_PKG._element_procs, "apply_element_procs"),  # ⑤b 元素机制
    "food":    (_PKG._food_proc, "install_food_fx"),         # ⑥ 食物（仅 ctx 传 aids 时）
}
_ORIG_ATTRS = {(m, a): getattr(m, a) for (m, a) in _OBS.values()}


def _restore(names):
    for n in names:
        mod, attr = _OBS[n]
        setattr(mod, attr, _ORIG_ATTRS[(mod, attr)])


PASS = 0
FAIL = 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        FAILURES.append(f"{name}: {detail}")
        print(f"  ❌ {name} {detail}")


def d(o):
    """稳定序列化（对拍用）。"""
    return json.dumps(o, sort_keys=True, default=str)


# ------------------------------------------------------------
# 夹具：从数据表动态取真实技能/装备（不硬编码游戏内容）
# ------------------------------------------------------------

def _skills_of(cid):
    t = C.PLAYER_SKILLS.get(cid) or {}
    return (t.get("skills") if isinstance(t, dict) and "skills" in t else t) or {}


def _pick(cid, pred, n=1):
    return [k for k, v in _skills_of(cid).items() if isinstance(v, dict) and pred(v)][:n]


def _bar_skills(cid):
    return _pick(cid, lambda v: any(v.get(f) for f in (BAR_INJECT_FIELDS or {})), 2)


def _cond_skills(cid):
    return _pick(cid, lambda v: isinstance(v.get("cond"), dict), 2)


def _weapon_key():
    for k, v in (WEAPON_EFFECT_DATA or {}).items():
        try:
            if EP.triggers_for_key(k):
                return k
        except Exception:
            continue
    return None


_WE_KEY = _weapon_key()
_BAR_SK = _bar_skills("cls_wu_seng")
_COND_SK = _cond_skills("cls_wu_seng")


def mk(cid, name, learned=(), uid="p", equipment=None, level=40):
    a = make_actor(uid=uid, name=name, side="player", kind="player",
                   human_controlled=True, class_name=cid, level=level,
                   hp=3000, max_hp=3000, mp=300, max_mp=300,
                   atk=80, matk=220, spd=12, crit=0.05,
                   skills=[], learned_skills=list(learned),
                   race=None, evolve_path=0, class_tier=0, attributes={},
                   **{"def": 40, "mdef": 60})
    if equipment:
        a["equipment"] = equipment
    return a


def _eq_affix(aid, slot="weapon", quality="purple", we=None):
    item = {"slot": slot, "quality": quality, "affixes": [aid], "stats": {}}
    if we:
        item["weapon_effect"] = we
    return {slot: item}


CASES = [
    ("武僧·推条+条件+上限词条", mk("cls_wu_seng", "武僧",
                              learned=_BAR_SK + _COND_SK, uid="p1",
                              equipment=_eq_affix("rage_forge", we=_WE_KEY))),
    ("牧师·cap 词条", mk("cls_mu_shi", "牧师", learned=_pick("cls_mu_shi", lambda v: True, 2),
                      uid="p2", equipment=_eq_affix("divine_radiance"))),
    ("诗人·旋律", mk("cls_shi_ren", "诗人", learned=_pick("cls_shi_ren", lambda v: v.get("mech"), 2),
                  uid="p3")),
    ("白板战士", mk("cls_zhan_shi", "战士", uid="p4")),
]


def apply_old(a):
    """并列调用路径（原 `commands/combat.py::_open_battle` 逐字：播种 bonus → EP → CM；
    ★ P5C-REPOINT 后 EP/CM = 包内 `content.mech.equip` / `content.mech.class_mech` 本体）。"""
    try:
        a["bonus"] = {"panel": {}, "cap": {}, "cost": {}}
    except Exception:
        pass
    EP.apply_to_actor(a)
    CM.apply_class_mech(a)
    return a


# ============================================================
# A 接口
# ============================================================

def t_a():
    print("【A 接口】")
    check("A1 apply_game_content / 引擎配置装配入口 可导入",
          callable(APPLY.apply_game_content) and callable(_eng_cfg))
    # A2（★ P5C-REPOINT 退休）：原断言 = `len(APPLY.LEGACY_CALL_SITES) >= 5`（宿主
    #   `game/content_rules/apply.py:72` 的「旧命令层调用点清单」，内容是 `game/commands/*.py`
    #   行号，供 S9 收口核对）。game/** 整棵树删除 ⇒ 该清单的**全部条目所指的文件都不再存在**，
    #   包内 `content/apply.py` 也没有（也不该有）这份宿主路径清单 —— 判据不再存在，整条退休。
    a = mk("cls_zhan_shi", "甲", uid="pa")
    r = APPLY.apply_game_content(a)
    check("A3 单参可调（ctx 可选）且返回原 actor", r is a)
    check("A4 空 actor 直接返回（不抛）", APPLY.apply_game_content({}) == {}
          and APPLY.apply_game_content(None) is None)


# ============================================================
# B 顺序契约
# ============================================================

def _spy(rec, name, mod, attr):
    orig = getattr(mod, attr)

    def f(*a, **k):
        rec.append(name)
        return None
    setattr(mod, attr, f)
    return orig


def t_b():
    print("【B 顺序契约（观测对象 = 包内实现；宿主 battle_*_proc 已退役）】")
    # B1/B2：七步入口全部 spy（包内模块属性）→ 观测包内 apply_game_content 自身的调用序
    names = ["install", "equip", "mech", "bar", "cond", "element", "food"]
    rec = []
    saved = [_spy(rec, n, *_OBS[n]) for n in names]
    try:
        APPLY.apply_game_content(mk("cls_zhan_shi", "甲", uid="pb1"))
        check("B1 顶层序 = install→equip→mech→bar→cond→element",
              rec == ["install", "equip", "mech", "bar", "cond", "element"], repr(rec))
        rec.clear()
        APPLY.apply_game_content(mk("cls_zhan_shi", "乙", uid="pb2"),
                                 ctx={"aids": ["__probe_aid__"], "logs": []})
        check("B2 传 aids → 末位追加 food",
              rec == ["install", "equip", "mech", "bar", "cond", "element", "food"], repr(rec))
        rec.clear()
        APPLY.apply_game_content(mk("cls_zhan_shi", "丙", uid="pb3"), ctx={"logs": []})
        check("B2b 不传 aids → 无 food", "food" not in rec, repr(rec))
        rec.clear()
        APPLY.apply_game_content({})
        check("B2c 空 actor → 零装配调用", rec == [], repr(rec))
    finally:
        _restore(names)

    # B3：包内 ① install_engine（= 旧 ensure_engine_configured/load_engine_config 实体）先于 ② equip
    rec2 = []
    _spy(rec2, "install", *_OBS["install"])
    _spy(rec2, "equip", *_OBS["equip"])
    try:
        APPLY.apply_game_content(mk("cls_zhan_shi", "丁", uid="pb4"))
        check("B3 ① 引擎配置装配（install_engine）先于 ② equip",
              rec2[:2] == ["install", "equip"], repr(rec2))
    finally:
        _restore(["install", "equip"])

    # B4：真实 ③ _class_mech + spy ④⑤ bar/cond → mech 内部 bar→cond 先跑，显式 ④⑤ 为幂等空转
    rec3 = []
    saved3 = [_spy(rec3, "bar", *_OBS["bar"]),
              _spy(rec3, "cond", *_OBS["cond"])]
    try:
        APPLY.apply_game_content(mk("cls_wu_seng", "武僧", learned=_BAR_SK + _COND_SK, uid="pb5"))
        check("B4 全链观测序 = bar,cond,bar,cond（mech 内部链先跑；④⑤ 幂等空转）",
              rec3 == ["bar", "cond", "bar", "cond"], repr(rec3))
    finally:
        _restore(["bar", "cond"])


# ============================================================
# C 引擎装配
# ============================================================

def t_c():
    print("【C 引擎配置装配】")
    ok = True
    try:
        _eng_cfg()
        _eng_cfg()
    except Exception as e:
        ok = False
        check("C1 引擎配置装配入口（_engine_harness.boot）连调 2 次无异常", False, repr(e))
    if ok:
        check("C1 引擎配置装配入口（_engine_harness.boot）幂等（连调 2 次）", True)
    # C2（★ P5C-REPOINT 退休）：原断言 = 猴补 `BST.package_apply` 观测
    #   `ensure_engine_configured` 委托「宿主唯一包加载口」。该中转层（`game/bootstrap.py`，
    #   `package_apply()`）随 game/** 整棵树删除；测试侧等价入口 `_engine_harness.boot()`
    #   直接返回已装配的 harness 单例（其内部就是 `load_package`），**不存在**可被观测的
    #   宿主委托点 —— 判据不再存在，整条退休（不是放宽阈值）。
    r = _b2c.get_effect_rules() or {}
    a = _b2c.get_effect_actions() or {}
    check("C3 规则表已装载（EFFECT_RULES/EFFECT_ACTIONS 非空）",
          bool(r) and bool(a), f"rules={len(r)} actions={len(a)}")


# ============================================================
# D 幂等 + 零状态副作用
# ============================================================

def t_d():
    print("【D 幂等 / 状态副作用（已知且显式测试）】")
    for label, base in CASES:
        a1 = json.loads(d(base))
        a2 = json.loads(d(base))
        APPLY.apply_game_content(a1)
        APPLY.apply_game_content(a2)
        APPLY.apply_game_content(a2)
        check(f"D1 {label}：1x == 2x", d(a1) == d(a2),
              f"len {len(d(a1))} vs {len(d(a2))}")
    a = mk("cls_wu_seng", "武僧", learned=_BAR_SK + _COND_SK, uid="pd1",
           equipment=_eq_affix("rage_forge", we=_WE_KEY))
    base_keys = set(a.keys())
    APPLY.apply_game_content(a)
    added = set(a.keys()) - base_keys
    allowed = {"bonus", "triggers", "effects", "food_effects", APPLY._MARK}
    check("D2 只新增已知装配容器键 + 声明的幂等标记",
          added <= allowed and APPLY._MARK in added,
          f"added={sorted(added)}")
    # D3：已知副作用——标记随 to_state 落档（显式断言，不做隐藏）
    B2 = __import__("saintess_engine", fromlist=["Battle"]).Battle
    foe = mk("cls_zhan_shi", "怪", uid="pd9")
    foe["side"] = "enemy"
    st = B2("monster", sides={"player": [a], "enemy": [foe]}).to_state()
    check("D3 【已知副作用】幂等标记随 serialize.to_state 落进战斗存档",
          APPLY._MARK in json.dumps(st, default=str))
    # D4：包内单步异常不阻断后续（容错铁律，与真源逐字一致）+ 记入 LAST_ERRORS
    #     观测对象 = 包内 LAST_ERRORS（`_PKG.LAST_ERRORS`；★ P5C-REPOINT 后 `_PKG is APPLY`
    #     = `content.apply` 本体 —— 宿主那份「同文件再留一份恒空 LAST_ERRORS 遮蔽 PEP 562
    #     转发」的假绿源**随 game/content_rules/apply.py 一起删除**，观测口只剩真源一个）。
    bad = mk("cls_wu_seng", "武僧", learned=_BAR_SK + _COND_SK, uid="pd4")
    _bar_mod, _bar_attr = _OBS["bar"]
    orig = _ORIG_ATTRS[(_bar_mod, _bar_attr)]
    setattr(_bar_mod, _bar_attr,
            lambda *x, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    try:
        APPLY.apply_game_content(bad)
    finally:
        setattr(_bar_mod, _bar_attr, orig)
    check("D4 单步异常不上抛、后续步照跑、仍落标记（容错铁律）",
          APPLY._MARK in bad and any(s == "bar" for s, _ in _PKG.LAST_ERRORS),
          f"errors={_PKG.LAST_ERRORS}")
    check("D4b 失败步记入 LAST_ERRORS（排障；不写 actor）",
          all(s not in bad for s, _ in _PKG.LAST_ERRORS) and len(_PKG.LAST_ERRORS) >= 1,
          f"errors={_PKG.LAST_ERRORS}")


# ============================================================
# E 并列对照（★ P5C-REPOINT：并列调用方 = 包内 equip / class_mech，
#   原「旧命令层」EP/CM 宿主壳已随 game/** 删除；逐字节口径一字不变）
# ============================================================

def t_e():
    print("【E 并列对照（EP+CM 并列调用 vs 单一入口）】")
    for i, (label, base) in enumerate(CASES, 1):
        old = json.loads(d(base))
        new = json.loads(d(base))
        apply_old(old)
        APPLY.apply_game_content(new)
        # 唯一允许的差异 = 幂等标记键（新入口独有；见模块 docstring）
        marker = APPLY._MARK
        new_cmp = {k: v for k, v in new.items() if k != marker}
        diff_keys = set(new) - set(old)
        same = d(old) == d(new_cmp)
        check(f"E{i} {label}：除幂等标记外逐字节相同", same,
              "" if same else f"len {len(d(old))} vs {len(d(new_cmp))}")
        check(f"E{i}b {label}：差异键集合 == {{'{marker}'}}",
              diff_keys == {marker}, f"diff={sorted(diff_keys)}")


# ============================================================
# F 数值抽样（装配效果照旧落地）
# ============================================================

def _triggers(a, ev):
    return ((a or {}).get("triggers") or {}).get(ev) or []


def t_f():
    print("【F 数值抽样】")
    a = mk("cls_wu_seng", "武僧", learned=_BAR_SK + _COND_SK, uid="pf1",
           equipment=_eq_affix("rage_forge", we=_WE_KEY))
    APPLY.apply_game_content(a)
    cap = ((a.get("bonus") or {}).get("cap") or {})
    check("F1 rage_forge 上限词条 → bonus.cap.rage == 2", int(cap.get("rage", 0)) == 2, repr(cap))
    bar_hits = [e for e in _triggers(a, "skill_hit")
                if isinstance(e, dict) and e.get("action") == "bar_gain"]
    check("F2 推条技能 → skill_hit 挂 bar_gain 注入", bool(bar_hits), repr(_triggers(a, "skill_hit"))[:160])
    cond_hits = [e for e in _triggers(a, "dmg_calc")
                 if isinstance(e, dict) and e.get("action") == "skill_cond_mult"]
    check("F3 条件技能 → dmg_calc 挂 skill_cond_mult", bool(cond_hits), repr(_triggers(a, "dmg_calc"))[:160])
    if _WE_KEY:
        check("F4 武器特效入装配（weapon_effect → triggers 非空）",
              all(_triggers(a, e) for e in EP.weapon_triggers(a)), f"key={_WE_KEY}")
    else:
        check("F4 武器特效入装配（本库无可用 key，跳过）", True)

    # 食物：仅当 ctx 传 aids
    # B16 收口：宿主 game/data 已删 —— FOOD_EFFECT_PARAMS 真源 = 包内 content/data/food_effects.json
    # （19 条；读口 = 包内 content/mech/food_proc.py:_food_params()）
    from content.mech.food_proc import _food_params
    FOOD_EFFECT_PARAMS = _food_params()
    aid = None
    for k in (FOOD_EFFECT_PARAMS or {}):
        try:
            if FOOD.food_trigger_decls(k) or FOOD.food_period_decl(k):
                aid = k
                break
        except Exception:
            continue
    if aid:
        a2 = mk("cls_zhan_shi", "战士", uid="pf2")
        APPLY.apply_game_content(a2, ctx={"aids": [aid], "logs": []})
        n1 = sum(len(v) for v in (a2.get("triggers") or {}).values())
        APPLY.apply_game_content(a2, ctx={"aids": [aid], "logs": []})
        n2 = sum(len(v) for v in (a2.get("triggers") or {}).values())
        check(f"F5 食物 aid={aid} 装配 + 重调幂等", n1 > 0 and n1 == n2, f"{n1} vs {n2}")
    else:
        check("F5 食物（本库无可用 aid，跳过）", True)
    a3 = mk("cls_zhan_shi", "战士", uid="pf3")
    APPLY.apply_game_content(a3)
    check("F6 不传 aids → 食物容器为空（不乱挂）",
          not (a3.get("triggers") or {}).get("food"), repr(a3.get("food_effects")))


# ============================================================
# 主流程
# ============================================================

def _snapshot_orig():
    """（已退役：观测对象的快照表现在由顶部 `_ORIG_ATTRS` 统一维护 —— 目标 = 包内实现。）"""
    return dict(_ORIG_ATTRS)


def main():
    print("=" * 66)
    print("S7 单一装配入口 apply_game_content —— 验收")
    print("=" * 66)
    t_a()
    t_b()
    t_c()
    t_d()
    t_e()
    t_f()
    print()
    print("=" * 66)
    print(f"通过 {PASS}，失败 {FAIL}")
    if FAILURES:
        for f in FAILURES:
            print(f"  ❌ {f}")
    print("=" * 66)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
