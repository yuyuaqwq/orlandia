# -*- coding: utf-8 -*-
"""批 C 验收（2026-09-11）：收尾死字段 —— wake_on_hit 接线 + 三处死声明清理。

覆盖（任意一条变红 = 死字段被退回 / 接线被改坏）：
  1. `wake_on_hit` 接线：受击打醒改读**通用字段**
     - `sleep` 声明了该字段 → 行为与接线前一致（零变化）
     - **数据驱动**：临时注入一个全新态（带 `wake_on_hit`）→ 同样被打醒
       （证明引擎不再硬编码 `"sleep"`，即纯度违规已修）
     - 不带该字段的态 → 不打醒
  2. 清理确认：`on_threshold` 与 `bleed` 的 `period.type` / `per_layer` 已删
     （防被回退；这三个都是「声明了没人读」的死字段）
  3. 孤儿防护：删掉这三个字段后，相关机制仍走各自的现行实现
     （狂暴 = 主动投入 / 流血 DOT 仍会跳）

跑法：python tests/test_v181_batch_c_deadfields.py（exit=0 全绿）
"""
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_batch_c.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from saintess_engine import config as _b2c  # noqa: E402
from _engine_harness import boot as _eng_cfg; _eng_cfg()  # noqa: E402
from ext_combat import Battle as B2, make_actor  # noqa: E402
from ext_combat.battle.landing import deal_damage  # noqa: E402
from ext_combat.battle.schedule import _settle_time_effects  # noqa: E402
from saintess_engine import config as EC  # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


def mk_pair():
    p = make_actor(uid="p1", name="法师", side="player", kind="player",
                   human_controlled=True, class_name="cls_fa_shi", level=40,
                   hp=3000, max_hp=3000, mp=300, max_mp=300,
                   atk=100, matk=200, spd=20, crit=0.0, equipment={}, skills=[],
                   learned_skills=[], **{"def": 30, "mdef": 30})
    e = make_actor(uid="e1", name="木桩", side="enemy", kind="monster",
                   hp=100000, max_hp=100000, atk=10, matk=10, spd=10, crit=0.0, level=40,
                   **{"def": 10, "mdef": 10})
    e["effects"] = {}
    e["dodge"] = 0.0
    e["block"] = 0.0
    return p, e, B2(btype="monster", sides={"player": [p], "enemy": [e]})


# ============================================================
# 1. wake_on_hit 接线
# ============================================================

def test_1_wake_on_hit():
    print("【1. wake_on_hit：受击打醒改读通用字段（引擎不再认态名）】")
    p, e, b = mk_pair()

    # (a) 现行数据：sleep 声明 wake_on_hit=True → 打醒（零变化）
    e["effects"] = {"sleep": {"mode": "skip", "expire": 99.0, "stacks": 1}}
    logs = []
    deal_damage(b, p, e, 50, logs)
    check("sleep（已声明 wake_on_hit）受击被打醒",
          "sleep" not in (e.get("effects") or {}), f"effects={list((e.get('effects') or {}).keys())}")
    check("打醒有日志提示", any("惊醒" in str(x) for x in logs), f"logs={logs}")

    # (b) 数据驱动：注入一个**全新态**（引擎不认识的名字）也带 wake_on_hit → 同样打醒
    rules = EC.get_effect_rules()
    rules["__test_wake_alt"] = {"cap": 1, "consume": {"mode": "skip"}, "wake_on_hit": True}
    try:
        p2, e2, b2 = mk_pair()
        e2["effects"] = {"__test_wake_alt": {"mode": "skip", "expire": 99.0, "stacks": 1}}
        deal_damage(b2, p2, e2, 50, [])
        check("★ 数据驱动：全新态（名字引擎不认识）带 wake_on_hit 也被打醒",
              "__test_wake_alt" not in (e2.get("effects") or {}),
              f"effects={list((e2.get('effects') or {}).keys())}")
    finally:
        rules.pop("__test_wake_alt", None)

    # (c) 不带 wake_on_hit 的态 → 不打醒
    p3, e3, b3 = mk_pair()
    e3["effects"] = {"poison": {"stacks": 3}}
    deal_damage(b3, p3, e3, 50, [])
    check("不带 wake_on_hit 的态（毒）受击**不**被移除",
          (e3.get("effects") or {}).get("poison", {}).get("stacks") == 3,
          f"effects={e3.get('effects')}")

    # (d) 引擎源码里不应再有硬编码的 "sleep" 判断（纯度违规已修）
    from ext_combat.battle import landing as L
    src = open(L.__file__, encoding="utf-8").read()
    check("引擎 landing 内不再硬编码 get(\"effects\", {}).get(\"sleep\")",
          'get("effects", {}).get("sleep")' not in src, "仍存在硬编码")
    check("引擎 landing 改为读 wake_on_hit 字段", 'wake_on_hit' in src, "")


# ============================================================
# 2. 死声明已清理（防回退）
# ============================================================

def test_2_removed_dead_fields():
    print("【2. 死声明清理确认（on_threshold / period.type / period.per_layer）】")
    from content.mech.params import EFFECT_RULES

    zy = EFFECT_RULES.get("zhan_yi") or {}
    check("zhan_yi 已删 on_threshold（原「满 10 进狂暴」与现行为冲突）",
          "on_threshold" not in zy, f"keys={sorted(zy.keys())}")

    bl = (EFFECT_RULES.get("bleed") or {}).get("period") or {}
    check("bleed.period 已删 type", "type" not in bl, f"period={bl}")
    check("bleed.period 已删 per_layer", "per_layer" not in bl, f"period={bl}")
    check("bleed.period 保留 dir/interval（引擎真读的两个键）",
          bl.get("dir") == "damage" and "interval" in bl, f"period={bl}")

    # 全仓不应再有这两个死子字段的声明（引擎侧仍不读，数据侧清干净）
    # B16 收口：宿主 game/data 已删 —— EFFECT_RULES 声明真源 = 包内 content/rules/effect_rules.json
    src = open(os.path.join(PLUGIN_DIR,
                            "content", "rules", "effect_rules.json"), encoding="utf-8").read()
    check("effect_rules 声明表内已无 on_threshold 声明", '"on_threshold"' not in src, "仍存在")
    check("EFFECT_RULES 全表无条目再声明 on_threshold",
          not [k for k, v in EFFECT_RULES.items()
               if isinstance(v, dict) and "on_threshold" in v], "仍存在")
    # ⚠️ 只查 EFFECT_RULES 的 period 子字典 —— `per_layer` 在 MECH_CASH 里是**活字段**
    #    （finisher 每层 +10% / 磐核 +70% 等由 class_mech_proc 读），别误伤。
    bad_periods = [k for k, v in EFFECT_RULES.items()
                   if isinstance(v, dict) and isinstance(v.get("period"), dict)
                   and ("per_layer" in v["period"] or "type" in v["period"])]
    check("EFFECT_RULES 所有 period 子字典内无死键（type / per_layer）",
          not bad_periods, f"命中={bad_periods}")


# ============================================================
# 3. 孤儿防护：机制仍走现行实现
# ============================================================

def test_3_orphan_guard():
    print("【3. 孤儿防护：删声明后机制仍可用】")
    from content.mech.params import EFFECT_RULES
    from content.mech.class_data import MECH_CASH
    # 狂暴走主动投入（血祭）——删 on_threshold 不影响的证据：MECH_CASH 仍在
    check("狂暴仍由 MECH_CASH.zhan_yi_fury（主动投入）承接",
          "zhan_yi_fury" in MECH_CASH
          and MECH_CASH["zhan_yi_fury"].get("mode") == "fury_enter",
          f"={MECH_CASH.get('zhan_yi_fury')}")
    check("战意 stat_scale 仍在（每层攻击 +4%）",
          (EFFECT_RULES.get("zhan_yi") or {}).get("stat_scale") == {"atk": 0.04},
          f"={EFFECT_RULES.get('zhan_yi')}")

    # 流血 DOT 仍会跳（删 type/per_layer 是删死键，不改变跳伤害）
    p, e, b = mk_pair()
    e["effects"] = {"bleed": {"stacks": 2,
                              "period": {"dir": "damage", "interval": 1.0}}}
    b._now = 0.0
    _settle_time_effects(b, [])
    hp_before = e["hp"]
    b._now = 1.0
    _settle_time_effects(b, [])
    check("流血仍每刻跳伤害（删死键不影响结算）", e["hp"] < hp_before,
          f"{hp_before} → {e['hp']}")


def main():
    test_1_wake_on_hit()
    test_2_removed_dead_fields()
    test_3_orphan_guard()
    print(f"\n== 结果：通过 {PASS} / 共 {PASS + FAIL} ==")
    if FAILURES:
        for f in FAILURES:
            print("  FAIL:", f)
        sys.exit(1)
    print("全绿 ✅")


if __name__ == "__main__":
    main()
