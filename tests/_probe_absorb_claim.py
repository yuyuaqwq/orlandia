# -*- coding: utf-8 -*-
"""★ 反证探针：摘掉 `absorb` 声明 ⇒ 护盾不吸收（当场红）。

这是**反证**，不是绿判据：它断言的是「声明是吸收型的唯一开关」这件事
在**奥兰迪亚包的真实声明表**上成立。引擎侧同款反证在
`tests/test_state_container_r2.py` 的 ⑤⑥ 两条。

跑法（在 games/orlandia 根）：
    unset GWEN_FRAMEWORK_DIR SAINTESS_EXTENDS
    export GWEN_FRAMEWORK_DIR=<引擎根>
    export GWEN_HOST_DIR=<宿主根>
    python tests/_probe_absorb_claim.py [--expect-no-absorb]

判据
----
① 装包（`content.apply.install_engine()`）后，`absorb_keys` 能认出**奥兰迪亚自己声明的**
   那些护盾 key（`we_bedrock` / `food_shield` / `shield` / `heal_overflow` …）——证明
   包内 `rules/effect_rules.json` 的 `"absorb": true` 真的被引擎读到了。
② ★ **反证**：把某一条的 `absorb` 从**挂载中的表**里摘掉 ⇒ 同一个 actor 上那条护盾
   **不再吸收**（伤害全额落到血上，护盾 value 一分不掉）。
③ 承伤落地仍只经引擎 `landing.deal_damage` 一条路（这里不自己实现吸收逻辑）。
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
FW = os.environ.get("GWEN_FRAMEWORK_DIR", "")

for p in (HERE, PKG):
    if p not in sys.path:
        sys.path.insert(0, p)
if FW:
    for p in (FW, os.path.join(FW, "extends")):
        if p not in sys.path:
            sys.path.insert(0, p)

import content.apply as APP                                   # noqa: E402
from content.gameplay import EFFECT_ACTIONS                     # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []


def check(label, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  ✅ %s" % label)
    else:
        FAIL += 1
        FAILURES.append("%s  —— %s" % (label, detail))
        print("  ❌ %s  —— %s" % (label, detail))


APP.install_engine()

from ext_combat.battle import landing as LND                   # noqa: E402
from ext_combat.battle import state_effects as SE               # noqa: E402
from ext_combat.battle.actors import make_actor, open_entry    # noqa: E402
from ext_combat.battle.battle import Battle                    # noqa: E402
from ext_combat.battle.game_config import get_effect_rules     # noqa: E402

RULES = get_effect_rules()


def _mk(uid, side, hp=500):
    return make_actor(uid, uid, side, human_controlled=(side == "player"),
                      **{"hp": hp, "max_hp": hp, "atk": 10, "matk": 10, "def": 0,
                         "mdef": 0, "spd": 50, "stats_spd": 50, "dodge": 0.0,
                         "block": 0.0})


def _bt(a, b):
    return Battle(btype="monster", sides={"player": [a], "enemy": [b]},
                  seed_ct=False)


# ============================================================
# ① 包内声明表真的被引擎读到了
# ============================================================
print("\n【① 奥兰迪亚声明表里的 absorb 声明真的生效】")
declared_absorb = sorted(k for k, v in RULES.items()
                         if isinstance(v, dict) and v.get("absorb"))
check("① 装包后 EFFECT_RULES 里声明了 absorb 的 key 数量 > 0（实测 %d 条）"
      % len(declared_absorb), len(declared_absorb) > 0, str(declared_absorb[:8]))
check("① 装备词条护盾 key `we_bedrock` 声明了 absorb",
      bool((RULES.get("we_bedrock") or {}).get("absorb")),
      repr(RULES.get("we_bedrock")))

t, src = _mk("t", "enemy"), _mk("src", "player")
bt = _bt(t, src)
open_entry(t, "we_bedrock", stacks=1, value=60, expire=99.0)
check("① `absorb_keys` 认出奥兰迪亚自己声明的 key（引擎只问声明、不认键名）",
      "we_bedrock" in SE.absorb_keys(t), str(SE.absorb_keys(t)))

lg = []
real = LND.deal_damage(bt, src, t, 40, lg, dmg_kind="phys")
check("① 有声明 ⇒ 真吸收（40 伤害被 60 的盾吃光，扣血 0）",
      real == 0 and int(t["hp"]) == 500 and (t["effects"].get("we_bedrock") or {}).get("value") == 20,
      "real=%s hp=%s entry=%s" % (real, t["hp"], (t["effects"] or {}).get("we_bedrock")))

# ============================================================
# ② ★ 反证：摘掉 absorb 声明 ⇒ 同一条护盾不再吸收
# ============================================================
print("\n【② ★ 反证：摘掉 absorb 声明 ⇒ 护盾不吸收（不掉的血）】")
prev = RULES.get("we_bedrock")
RULES["we_bedrock"] = {k: v for k, v in (prev or {}).items() if k != "absorb"}
try:
    t2, src2 = _mk("t2", "enemy"), _mk("src2", "player")
    bt2 = _bt(t2, src2)
    open_entry(t2, "we_bedrock", stacks=1, value=60, expire=99.0)
    check("★ ② 摘掉声明后 absorb_keys 认不出它（判定纯看声明）",
          "we_bedrock" not in SE.absorb_keys(t2), str(SE.absorb_keys(t2)))
    lg = []
    real2 = LND.deal_damage(bt2, src2, t2, 40, lg, dmg_kind="phys")
    check("★ ② 摘掉声明 ⇒ 伤害全额落到血上（real=40，护盾 value 原封不动 60）",
          real2 == 40 and int(t2["hp"]) == 460
          and (t2["effects"].get("we_bedrock") or {}).get("value") == 60,
          "real=%s hp=%s entry=%s" % (real2, t2["hp"], (t2["effects"] or {}).get("we_bedrock")))
    # 声明加回去 ⇒ 立刻恢复吸收（证明缺的就是那一条声明）
    RULES["we_bedrock"] = prev
    lg = []
    real3 = LND.deal_damage(bt2, src2, t2, 40, lg, dmg_kind="phys")
    check("★ ② 声明加回去 ⇒ 同一个键立刻恢复吸收（40 全被吃光）",
          real3 == 0 and int(t2["hp"]) == 460
          and (t2["effects"].get("we_bedrock") or {}).get("value") == 20,
          "real=%s hp=%s entry=%s" % (real3, t2["hp"], (t2["effects"] or {}).get("we_bedrock")))
finally:
    if prev is not None:
        RULES["we_bedrock"] = prev

# ============================================================
# ③ halve 已从包侧声明面清零（只写不读的死字段不该再出现）
# ============================================================
print("\n【③ halve 死字段已从包侧声明面清零】")
_hits = [k for k, acts in EFFECT_ACTIONS.items()
         if isinstance(acts, list) and any(isinstance(a, dict) and "halve" in a for a in acts)]
check("③ EFFECT_ACTIONS 里已无任何 `halve` 键（实测命中 %d 条）" % len(_hits),
      not _hits, str(_hits[:6]))

print("\n===== 结果：通过 %d / 共 %d =====" % (PASS, PASS + FAIL))
if FAILURES:
    print("失败明细：")
    for x in FAILURES:
        print("  - " + x)
sys.exit(1 if FAIL else 0)
