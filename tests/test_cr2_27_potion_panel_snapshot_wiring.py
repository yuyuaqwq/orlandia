# -*- coding: utf-8 -*-
"""台账 C-R2.27 门禁 —— **8 个面板快照型战斗药水在引擎现行 `effects` 形状下真跑通**

本件接的是 §0.37 登记的 C-R2.27 第 1 条（落点换形状），**纯内容侧**（不动引擎）。

■ 本轮实测到的三个前提（上一轮台账把其中两条当成了「机械可做」，实测修正）：
  ① 8 个族名**既不在** `_EFFECT_ACTION_KEYS`（21）**也不在** `EFFECT_RULES`（106）
     ⇒ 「往白名单加个键就通」是**假前提**：查表翻译要求 `EFFECT_ACTIONS[kind]` 有动作，
     而这 8 个族在 `EFFECT_ACTIONS`(70) 里也**零条目** ⇒ 走查表必然 resolve 空、
     `apply_effects` 静默跳过（`if not actions and etype not in ACTION_HANDLERS: continue`）。
     ⇒ 正解是**参数直传**（引擎快照型分支读 `params` 的 `stat/op/mult`），
     与 `item_use._translate_special` 里 shield 族**同一手法**。
  ② 面板快照型必须是 `op:"add"`（不是 `mul`）：这 8 个都是**比例属性**
     （`dodge/block/crit_dmg/lifesteal/thorns/magic_reduce/pene_phys/pene_magi`
     全在 `panel_rules.pct_stats` 内、值是 0.0–1.0 的比例）⇒ `mul` 会把
     `dodge 0.20 × 1.15` 变成 0.23（比例被放大 15%），语义错。
  ③ ★ **`eff` 里的 pct 必须真的落到面板上** —— 引擎 `_apply_effects` 的 add 分支是
     `st[stat] = float(st.get(stat,0)) + float(mult)`，**键不在 st 里也照样加**
     ⇒ 「静默造键」是真的（见反证档），但**面板侧这 8 个键本来就存在**
     （`pct_stats` + `optional_stats` 声明、面板聚合时按 0 起算）⇒ 不会变成孤儿键。

■ 本件判据分四档（含反证 ⇒ 不是恒绿档）：
  (一) 正证档：逐族真跑 `apply_effects` + `stats._apply_effects`，
        断言 effects 条目形状（stacks/stat/op/mult）与**面板数值 = 基值 + pct**。
  (二) 接线档：8 个族经 `item_use.translate` 真实入口进来（不再是 `None` 缺口）。
  (三) 覆盖档：族名**不在**两张旧表里（防止下一个人以为「加白名单就够」而删掉直传路）。
  (四) 反证档：把 pct 换成别的值 ⇒ 面板数值必须跟着变（判据不是恒真）。
"""
import os
import sys

PKG = r"C:/Users/yuyu/framework-engine/games/orlandia"
ENG = r"C:/Users/yuyu/framework-engine"
sys.path.insert(0, PKG)
sys.path.insert(0, os.path.join(ENG, "extends"))
os.environ.setdefault("GWEN_TEST_MODE", "1")

FAILS = []


def check(name, ok, extra=""):
    print(("  ok   " if ok else "  FAIL ") + name + (("  | " + str(extra)) if extra else ""))
    if not ok:
        FAILS.append(name)


# 族 → (面板 stat 键, 物品 effect_data.pct, 样本物品 id)
# ★ 数值真源 = `content/data/items.json` 的 `effect_data.pct`（逐族现取，见档五）
FAMILIES = (
    ("dodge_pot", "dodge", 0.15, "i_shadowstep_pot"),
    ("block_pot", "block", 0.15, "i_block_pot"),
    ("crit_dmg_pot", "crit_dmg", 0.25, "i_crit_dmg_pot"),
    ("lifesteal_pot", "lifesteal", 0.15, "i_lifesteal_pot"),
    ("thorns_pot", "thorns", 0.30, "i_thorn_pot"),
    ("pene_pot", "pene_phys", 0.15, "i_pene_pot"),
    ("pene_magi_pot", "pene_magi", 0.15, "i_pene_magi_pot"),
    ("magic_resist", "magic_reduce", 0.15, "i_abyss_crystal_potion"),
)
BASE = {"dodge": 0.20, "block": 0.05, "crit_dmg": 0.50, "lifesteal": 0.00,
        "thorns": 0.00, "pene_phys": 0.00, "pene_magi": 0.00, "magic_reduce": 0.00}

from content.apply import install_engine            # noqa: E402
install_engine()
from ext_combat.battle import effects as EF          # noqa: E402
from ext_combat.battle import stats as ST            # noqa: E402
import content.mech.item_use as IU                   # noqa: E402


class _B:
    def __init__(self):
        self.cfg = {}
        self.diag = []


def _apply_and_read(stat, pct, turns=3, op="add"):
    b = _B()
    a = {"uid": "p1", "name": "t", "side": "player", "class_name": "战士", "level": 30}
    EF.apply_effects(b, a, a, [{"action": "apply", "key": "probe_%s" % stat,
                                "turns": turns, "stat": stat, "op": op,
                                "mult": pct, "on": "caster"}], [])
    st = dict(BASE)
    ST._apply_effects(st, a)
    return a.get("effects", {}).get("probe_%s" % stat, {}), st[stat]


print("【档 一】正证：逐族真跑引擎现行形状（快照条目 + 面板数值 = 基值 + pct）")
for fam, stat, pct, iid in FAMILIES:
    e, val = _apply_and_read(stat, pct)
    shape_ok = (e.get("stacks") == 1 and e.get("stat") == stat
                and e.get("op") == "add" and abs(float(e.get("mult", -1)) - pct) < 1e-9
                and float(e.get("expire", 0)) > 0)
    panel_ok = abs(val - (BASE[stat] + pct)) < 1e-6
    check("%-14s → %-13s 条目形状 + 面板 %.4f (= %.2f+%.2f)"
          % (fam, stat, val, BASE[stat], pct), shape_ok and panel_ok, e)

print("【档 二】接线：8 个族经 item_use 真实入口进来（不再是 None 缺口）")
for fam, stat, pct, iid in FAMILIES:
    b = _B()
    a = {"uid": "p1", "name": "t", "side": "player", "class_name": "战士", "level": 30}
    logs = []
    r = IU._translate_special(b, a, fam, {"pct": pct}, logs, 1.4, 0.0)
    check("%-14s translate 有返回（非 None 缺口）" % fam, r is not None, r)
    if r:
        ef = a.get("effects", {})
        got = ef.get("potion_%s" % fam, {})
        check("  └ effects 落条目且 pct=%s" % pct,
              abs(float(got.get("mult", -1)) - pct) < 1e-9
              and got.get("stat") == stat, got)

print("【档 三】覆盖：族名不在两张旧表里（钉住「查表翻译不可行」这个前提）")
from ext_combat.battle import game_config as GC     # noqa: E402
_ea = GC.get_effect_actions()
from ext_combat.battle.state_effects import get_effect_rules  # noqa: E402
_er = get_effect_rules()
_in_wl = [f for f, s, p, i in FAMILIES if f in IU._EFFECT_ACTION_KEYS]
_in_ea = [f for f, s, p, i in FAMILIES if isinstance(_ea.get(f), list) and _ea.get(f)]
_in_er = [f for f, s, p, i in FAMILIES if f in _er]
check("8 族全不在 _EFFECT_ACTION_KEYS（查表路径不通）", not _in_wl, _in_wl)
check("8 族全不在 EFFECT_ACTIONS（查表拿不到动作）", not _in_ea, _in_ea)
check("8 族全不在 EFFECT_RULES（查不到 panel 声明）", not _in_er, _in_er)

print("【档 四】反证：pct 改值 ⇒ 面板数值必须跟着变（判据不是恒真）")
_e1, v1 = _apply_and_read("dodge", 0.15)
_e2, v2 = _apply_and_read("dodge", 0.40)
check("dodge pct 0.15→0.40 时面板 %.4f→%.4f 且相差 0.25" % (v1, v2),
      abs((v2 - v1) - 0.25) < 1e-6, (v1, v2))
_e3, v3 = _apply_and_read("dodge", 0.15, op="mul")
# 引擎 mul 分支 = int(st[stat] * mult)；本代码的 mult 是**增量比例**(0.15)，
# 故 op=mul 得 int(0.20*0.15)=0（向零截断）—— 与 add 的 0.35 不同。
check("反证：op=mul 得 %.4f（≠ add 的 %.4f）⇒ 判据认得出 op（add 才是对的）" % (v3, v1),
      abs(v3 - int(BASE["dodge"] * 0.15)) < 1e-6 and abs(v3 - v1) > 1e-6, (v3, v1))

print("【档 五】数值真源：pct 逐族对齐 items.json 的 effect_data（不写死在探针里）")
import json                                      # noqa: E402
import io                                        # noqa: E402
_items = json.load(io.open(os.path.join(PKG, "content", "data", "items.json"),
                           encoding="utf-8"))
for fam, stat, pct, iid in FAMILIES:
    _it = _items.get(iid) or {}
    _real = float((_it.get("effect_data") or {}).get("pct", -1))
    check("  %-16s effect_data.pct = %.2f（探针用 %.2f）" % (iid, _real, pct),
          abs(_real - pct) < 1e-9, _real)

print()
if FAILS:
    print("【FAIL %d】%s" % (len(FAILS), FAILS))
    sys.exit(1)
print("【全绿】C-R2.27 面板快照型 8 族接线 = 正证 %d + 接线 %d + 覆盖 3 + 反证 2 + 真源 8"
      % (len(FAMILIES), len(FAMILIES) * 2))
