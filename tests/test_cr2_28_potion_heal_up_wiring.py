# -*- coding: utf-8 -*-
"""台账 C-R2.28 门禁 —— **`heal_up`（圣光药剂）接线** = 面板快照型第 9 族

本件是 C-R2.27（8 族面板快照型）之后的**第 9 族**，**纯内容侧**（不动引擎）。

■ 为什么归进面板快照型（实测取证，不是推断）：
  旧 handler `potion_effects.eff_heal_up` 的落点是 `player["buffs"]["heal_up"] = turns`
  ——一个**刻计数**，效果本体由「治疗技能结算读 p_buffs.heal_up」消费。
  引擎侧现成的那个读点叫 `heal_power`：`actions._do_heal` 实跑
      hpv = min(float(st.get("heal_power", 0) or 0), _F.heal_power_cap())   # cap=0.50
      if hpv > 0: heal = int(heal * (1 + hpv))
  与旧语义（「治疗技能效果 +pct」）**逐字同义**，且 `heal_power` 是
  `panel_rules.pct_stats` 的**名单源成员**（23 项内）⇒ 不是静默造键。

■ 为什么不能走查表（沿用 C-R2.27 档三的取证口径，本件复跑一遍）：
  `heal_up` 在 `_EFFECT_ACTION_KEYS` / `EFFECT_ACTIONS` / `EFFECT_RULES` 三张表里零条目
  ⇒ 查表翻译 resolve 空 ⇒ `apply_effects` 静默跳过。正解 = **参数直传**（op="add"）。

■ 本件判据分五档（含反证 ⇒ 不是恒绿档）：
  (一) 正证：面板数值 = 基值 + pct（真跑引擎 `stats._apply_effects`）
  (二) 接线：`can_translate` 放行 + `_translate_special` 有返回 + effects 条目形状
  (三) 覆盖：族名在三张旧表里零条目（钉住「加白名单就够」这个假前提）
  (四) 读点：`heal_power` 确在引擎 `_do_heal` 的消费路径上（本件接线能被人看见）
  (五) 反证：pct 改值 ⇒ 面板跟着变；op=mul ⇒ 数值不同（判据认得出 op）
"""
import io
import json
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


FAM, STAT, PCT, IID = "heal_up", "heal_power", 0.2, "i_holy_potion"
BASE = {STAT: 0.10}

from content.apply import install_engine            # noqa: E402
install_engine()
from ext_combat.battle import effects as EF          # noqa: E402
from ext_combat.battle import stats as ST            # noqa: E402
import content.mech.item_use as IU                   # noqa: E402


class _B:
    def __init__(self):
        self.cfg = {}
        self.diag = []


def _apply_and_read(pct, turns=3, op="add", stat=STAT):
    b = _B()
    a = {"uid": "p1", "name": "t", "side": "player", "class_name": "牧师", "level": 30}
    EF.apply_effects(b, a, a, [{"action": "apply", "key": "probe_%s" % stat,
                                "turns": turns, "stat": stat, "op": op,
                                "mult": pct, "on": "caster"}], [])
    st = dict(BASE)
    ST._apply_effects(st, a)
    return a.get("effects", {}).get("probe_%s" % stat, {}), st[stat]


print("【档 一】正证：面板数值 = 基值 + pct（真跑引擎现行形状）")
_e, v = _apply_and_read(PCT)
shape_ok = (_e.get("stacks") == 1 and _e.get("stat") == STAT and _e.get("op") == "add"
            and abs(float(_e.get("mult", -1)) - PCT) < 1e-9
            and float(_e.get("expire", 0)) > 0)
panel_ok = abs(v - (BASE[STAT] + PCT)) < 1e-6
check("%-10s → %-12s 条目形状 + 面板 %.4f (= %.2f+%.2f)" % (FAM, STAT, v, BASE[STAT], PCT),
      shape_ok and panel_ok, _e)

print("【档 二】接线：can_translate 放行 + translate 有返回 + 落 effects 条目")
check("can_translate('special:%s') 放行" % FAM, IU.can_translate("special:" + FAM))
check("can_translate 带 effect_data 也放行",
      IU.can_translate('special:%s:{"pct":%s}' % (FAM, PCT)))
b = _B()
a = {"uid": "p1", "name": "t", "side": "player", "class_name": "牧师", "level": 30}
logs = []
r = IU._translate_special(b, a, FAM, {"pct": PCT}, logs, 1.4, 0.0)
check("translate 有返回（非 None 缺口）", r is not None, r)
got = (a.get("effects", {}) or {}).get("potion_%s" % FAM, {})
check("  └ effects 落条目（stat=%s op=add mult=%s）" % (STAT, PCT),
      got.get("stat") == STAT and got.get("op") == "add"
      and abs(float(got.get("mult", -1)) - PCT) < 1e-9, got)
check("  └ 玩家可见文案已发（potion_stat 族）",
      any("属性强化" in str(x) for x in logs), logs)

print("【档 三】覆盖：族名在三张旧表里零条目（钉住「查表翻译不可行」）")
from ext_combat.battle import game_config as GC              # noqa: E402
from ext_combat.battle.state_effects import get_effect_rules  # noqa: E402
_ea = GC.get_effect_actions()
_er = get_effect_rules()
check("不在 _EFFECT_ACTION_KEYS（查表路径不通）", FAM not in IU._EFFECT_ACTION_KEYS)
check("不在 EFFECT_ACTIONS（查表拿不到动作）",
      not (isinstance(_ea.get(FAM), list) and _ea.get(FAM)), _ea.get(FAM))
check("不在 EFFECT_RULES（查不到 panel 声明）", FAM not in _er)

print("【档 四】读点：heal_power 是面板 pct 名单源成员（不是静默造键）")
_pr = json.load(io.open(os.path.join(PKG, "content", "rules", "panel_rules.json"),
                        encoding="utf-8"))
_pct_list = list((_pr.get("pct_stats") or {}).get("stats") or [])
check("heal_power 在 panel_rules.pct_stats 名单源内（%d 项）" % len(_pct_list),
      STAT in _pct_list, _pct_list)
_acts = io.open(os.path.join(ENG, "extends", "ext_combat", "battle", "actions.py"),
                encoding="utf-8").read()
check("引擎 _do_heal 实跑读 heal_power（接线后玩家看得见）",
      'st.get("heal_power"' in _acts and "heal_power_cap()" in _acts)

print("【档 五】反证：pct 改值 ⇒ 面板跟着变；op=mul ⇒ 数值不同")
_e1, v1 = _apply_and_read(0.20)
_e2, v2 = _apply_and_read(0.40)
check("pct 0.20→0.40 时面板 %.4f→%.4f 且相差 0.20" % (v1, v2),
      abs((v2 - v1) - 0.20) < 1e-6, (v1, v2))
_e3, v3 = _apply_and_read(0.20, op="mul")
check("op=mul 得 %.4f（≠ add 的 %.4f）⇒ 判据认得出 op" % (v3, v1),
      abs(v3 - int(BASE[STAT] * 0.20)) < 1e-6 and abs(v3 - v1) > 1e-6, (v3, v1))
# 反证之反：turns=0 ⇒ 引擎快照分支直接 return（到不了面板）⇒ 判据有牙
_e4, v4 = _apply_and_read(0.20, turns=0)
check("反证：turns=0 时面板不落增益（%.4f = 基值）⇒ 判据不是恒真" % v4,
      abs(v4 - BASE[STAT]) < 1e-6, v4)

print("【档 六】数值真源：pct 对齐 items.json 的 effect_data（不写死在探针里）")
_items = json.load(io.open(os.path.join(PKG, "content", "data", "items.json"),
                           encoding="utf-8"))
_real = float((_items.get(IID) or {}).get("effect_data", {}).get("pct", -1))
check("  %-16s effect_data.pct = %.2f（探针用 %.2f）" % (IID, _real, PCT),
      abs(_real - PCT) < 1e-9, _real)

print()
if FAILS:
    print("【FAIL %d】%s" % (len(FAILS), FAILS))
    sys.exit(1)
print("【全绿】C-R2.28 heal_up 接线 = 正证 1 + 接线 4 + 覆盖 3 + 读点 2 + 反证 3 + 真源 1")
