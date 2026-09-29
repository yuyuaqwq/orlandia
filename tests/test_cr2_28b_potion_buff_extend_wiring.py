# -*- coding: utf-8 -*-
"""台账 C-R2.28 门禁 B —— **`buff_extend`（时之延香）接线** = 到期顺延族（第 1 族）

本件是 C-R2.27（面板快照型 8 族）/ C-R2.28A（heal_up）之后的**第二种形状**：
不是「给 actor 加一条新状态」，而是**改已落条目的到期时刻**。

■ 为什么归进「到期顺延族」（实测取证）：
  旧 handler `potion_effects.eff_buff_extend` 的落点是
      p_buffs[k] = 原刻数 + N        （逐个刻计数顺延）
  但现行到期**只有一个真源** = effects 条目的 `expire`
  （`landing._apply_damage` 那批已把第二本账 `reduce_left` 整个删掉）
  ⇒ 正解是**顺延 expire**，不新建任何形状、不动引擎。
  旧 handler 的战斗面只有 `p_buffs` 遍历 ⇒ **零 battle 替身回调**。

■ 与面板快照型的关键区别（口径钉在门禁里，别下一个人搞混）：
  面板快照型 = **参数直传** `apply_effects(..., stat/op/mult)`；
  本件 = **直接改容器** `entry["expire"] += N`，不经过 apply_effects。
  因为「给已有条目的到期加 N」这件事在引擎里**没有对应动词**（apply 只管新挂/叠层）。

■ 判据六档（含反证 ⇒ 不是恒绿档）：
  (一) 正证：已落条目的 expire 真被顺延
  (二) 豁免：旧 handler 原样搬来的一次性/控制类键**不被延**
  (三) 无到期不延：无 expire 的标记类条目**不动**（顺延它没有语义）
  (四) 接线：can_translate 放行 + translate 有返回 + 玩家可见文案已发
  (五) 反证：extend_turns 改值 ⇒ 顺延量跟着变；缺参/零参 ⇒ 不静默放行
  (六) 双表同步：texts.json 与 text_specs.json 必须都有该槽位且逐字相同
"""
import io
import json
import os
import sys

PKG = r"C:/Users/yuyu/framework-engine/games/orlandia"
ENG = r"C:/Users/yuyu/framework-engine"
sys.path.insert(0, PKG)
sys.path.insert(0, os.path.join(ENG, "extends"))
sys.path.append(ENG)
os.environ.setdefault("GWEN_TEST_MODE", "1")

FAILS = []


def check(name, ok, extra=""):
    print(("  ok   " if ok else "  FAIL ") + name + (("  | " + str(extra)) if extra else ""))
    if not ok:
        FAILS.append(name)


from content.apply import install_engine            # noqa: E402
install_engine()
import content.mech.item_use as IU                   # noqa: E402

FAM = "buff_extend"
IID = "i_shi_zhi_yan_xiang"


class _B:
    def __init__(self, now=10.0):
        self.cfg = {}
        self.diag = []
        self._now = now


def _actor():
    return {"uid": "p1", "name": "t", "side": "player", "class_name": "战士", "level": 30,
            "effects": {
                "potion_dodge_pot": {"stacks": 1, "expire": 13.0, "stat": "dodge",
                                     "op": "add", "mult": 0.15},
                "potion_heal_up": {"stacks": 1, "expire": 11.5, "stat": "heal_power",
                                   "op": "add", "mult": 0.2},
                "next_atk_up": {"stacks": 1, "expire": 20.0},
                "noexpire_mark": {"stacks": 1},
            }}


def _run(extend):
    a = _actor()
    logs = []
    r = IU._translate_special(_B(), a, FAM, {"extend_turns": extend}, logs, 1.4, 0.0)
    return r, a, logs


print("【档 一】正证：已落条目的 expire 真被顺延（extend_turns=2）")
_r, a, logs = _run(2)
ef = a["effects"]
check("potion_dodge_pot 13.0 → %.1f" % ef["potion_dodge_pot"]["expire"],
      abs(ef["potion_dodge_pot"]["expire"] - 15.0) < 1e-9, ef["potion_dodge_pot"])
check("potion_heal_up 11.5 → %.1f" % ef["potion_heal_up"]["expire"],
      abs(ef["potion_heal_up"]["expire"] - 13.5) < 1e-9, ef["potion_heal_up"])
check("translate 有返回（非 None 缺口）", _r is not None, _r)

print("【档 二】豁免：旧 handler 原样搬来的一次性/控制类键不被延")
check("next_atk_up 仍 20.0（在 _EXPIRE_EXTEND_EXEMPT 里）",
      abs(ef["next_atk_up"]["expire"] - 20.0) < 1e-9, ef["next_atk_up"])
check("_EXPIRE_EXTEND_EXEMPT 与旧 handler 的豁免元组一致",
      set(IU._EXPIRE_EXTEND_EXEMPT) == {"next_atk_up", "buff_phys_next", "stealth",
                                        "reduce_all", "stun", "freeze"},
      IU._EXPIRE_EXTEND_EXEMPT)

print("【档 三】无到期不延：标记类条目不动（顺延它没有语义）")
check("noexpire_mark 无 expire 键未被顺延",
      "expire" not in ef["noexpire_mark"] and ef["noexpire_mark"].get("expire") is None,
      ef["noexpire_mark"])

print("【档 四】接线：can_translate 放行 + 玩家可见文案已发")
check("can_translate('special:%s') 放行" % FAM, IU.can_translate("special:" + FAM))
check("can_translate 带 effect_data 也放行",
      IU.can_translate('special:%s:{"extend_turns":2}' % FAM))
check("玩家可见文案已发（非 key 裸串）",
      any("时之延香" in str(x) for x in logs), logs)

print("【档 五】反证：改值跟着变；缺参/零参不静默放行")
_r2, a2, _ = _run(5)
check("extend_turns 2→5 时 dodge 条目 13.0 → %.1f" % a2["effects"]["potion_dodge_pot"]["expire"],
      abs(a2["effects"]["potion_dodge_pot"]["expire"] - 18.0) < 1e-9,
      a2["effects"]["potion_dodge_pot"])
_r0, a0, _ = _run(0)
check("extend_turns=0 ⇒ 返回 None（不静默放行一个 0 顺延）", _r0 is None, _r0)
_rn = IU._translate_special(_B(), _actor(), FAM, {}, [], 1.4, 0.0)
check("缺 extend_turns ⇒ 返回 None（fail-closed）", _rn is None, _rn)
# 反证之反：没有任何可延条目 ⇒ 仍然返回（n=0 ≠ 缺口）
_rz = IU._translate_special(
    _B(), {"uid": "p1", "name": "t", "side": "player", "effects": {}},
    FAM, {"extend_turns": 2}, [], 1.4, 0.0)
check("无可延条目时仍返回（n=0 ≠ 缺口）", _rz is not None, _rz)

print("【档 六】双表同步：texts.json 与 text_specs.json 都有该槽位且逐字相同")
_a = json.load(io.open(os.path.join(PKG, "content", "data", "texts.json"), encoding="utf-8"))
_b = json.load(io.open(os.path.join(PKG, "content", "data", "text_specs.json"), encoding="utf-8"))
check("texts.json 有 iu.buff_extend", "iu.buff_extend" in _a)
check("text_specs.json 有 iu.buff_extend", "iu.buff_extend" in _b)
check("两表逐字相同", _a.get("iu.buff_extend") == _b.get("iu.buff_extend"),
      (_a.get("iu.buff_extend"), _b.get("iu.buff_extend")))
check("槽位声明 = 代码实际传的参数（n/turns）",
      list((_a.get("iu.buff_extend") or {}).get("params") or []) == ["n", "turns"],
      (_a.get("iu.buff_extend") or {}).get("params"))
_ka = [k for k in _a if k.startswith("iu.")]
check("texts.json 的 iu.* 仍升序（定点插入没打乱外层键序）", _ka == sorted(_ka), _ka)
# 数值真源
_items = json.load(io.open(os.path.join(PKG, "content", "data", "items.json"), encoding="utf-8"))
_ed = (_items.get(IID) or {}).get("effect_data") or {}
check("  %-20s effect_data.extend_turns = %s" % (IID, _ed.get("extend_turns")),
      int(_ed.get("extend_turns", -1)) == 2, _ed)

print()
if FAILS:
    print("【FAIL %d】%s" % (len(FAILS), FAILS))
    sys.exit(1)
print("【全绿】C-R2.28B buff_extend 接线 = 正证 3 + 豁免 2 + 无到期 1 + 接线 3 + 反证 4 + 双表 5 + 真源 1")
