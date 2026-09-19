# -*- coding: utf-8 -*-
"""N5B P1 验证：通用怪 AI 决策器（条件优先级表）。

- normalize_ai：旧格式 {skill_chance, weights} → weighted moves（幂等）
- priority：守卫命中顺序 / AND 组合 / 未知谓词不命中 / 空 when 恒真
- 谓词：self_hp_lt/gt / hostile_lowest_hp_lt / round_mod（act_count）/ cd_ok
- weighted：固定 seed 抽样 / skill_chance 回落
- actor_auto 端到端：带 ai 怪战斗自选技能（真实 MONSTER_MODS ai 数据）
- 2026-09-11：决策器加「可执行性过滤」（技能放不出 → 跳过，见 ai._move_castable）
  → 本文件是**决策语义**单测，use 的 ms_* 假技能名真实技能表里不存在，故
  mk_battle 直接给最小 _skill_index（真实索引由内容侧 hook 装配）。

跑法：python tests/test_monster_ai_p1.py
"""
import os
import sys
import tempfile
import json
import random

os.environ["GWEN_GAME_DB"] = os.path.join(tempfile.mkdtemp(), "game.db")
os.environ["GWEN_TEST_MODE"] = "1"
_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
sys.path.insert(0, _PLUGIN_DIR)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _engine_harness import boot as _eng_cfg; _eng_cfg()  # noqa: E402

from _engine_harness import C  # noqa: E402
from _engine_harness import db  # noqa: E402
db.init_db()

from saintess_engine import ai as AI  # noqa: E402
from saintess_engine import Battle as B2  # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


# 决策器单测用的假技能名（真实技能表无此键）
STUB_REFS = ("ms_low", "ms_mid", "ms_never", "ms_fallback", "ms_rhythm",
             "ms_finish", "ms_skill_a", "ms_a", "ms_b")


def _stub_index(*refs):
    """最小技能索引（引擎 info 契约：name = 冷却表键）。

    真实索引由内容侧 hook 装配（skill_lookup / monster_skill_fn）；本文件只验
    决策语义，假技能名在真实技能表查不到 → 会被「可执行性过滤」挡掉，故直接给。
    """
    return {r: {"name": r, "cd": 0, "mp": 0} for r in refs}


def mk_battle(mon_hp_ratio=1.0, player_hp_ratio=1.0, with_player=True):
    """怪（带 ai 可后续塞）+ 可选玩家。"""
    mon = {"uid": "e_ai", "id": "b_test", "name": "测试怪", "role": "boss",
           "is_boss": True, "side": "enemy",
           "hp": int(1000 * mon_hp_ratio), "max_hp": 1000,
           "atk": 100, "matk": 100, "def": 10, "mdef": 10, "spd": 80,
           "lv": 20, "skills": [], "effects": {}, "shields": {},
           "cooldown": {}, "auto_act": None, "act_count": 0, "ct": 0.0}
    sides = {"enemy": [mon]}
    if with_player:
        sides["player"] = [{"uid": "p_1", "name": "勇者", "side": "player",
                            "hp": int(5000 * player_hp_ratio), "max_hp": 5000,
                            "atk": 100, "matk": 100, "def": 50, "mdef": 50,
                            "spd": 50, "lv": 20, "effects": {}, "shields": {},
                            "ct": 0.0}]
    b = B2("instance", sides=sides)
    b._now = 100.0
    mon["_skill_index"] = _stub_index(*STUB_REFS)   # 可执行性过滤需索引
    return b, mon


def test_1_normalize():
    print("【1. normalize_ai：旧格式 weights → weighted moves（幂等）】")
    mon = {"ai": {"skill_chance": 0.6, "weights": {"ms_a": 4, "ms_b": 2, "ms_c": 1}}}
    ai = AI.normalize_ai(mon)
    check("转 weighted", ai.get("select") == "weighted", str(ai))
    check("moves 3 条", len(ai.get("moves") or []) == 3, str(ai.get("moves")))
    check("weight 保留", any(m.get("weight") == 4 for m in ai["moves"]), str(ai["moves"]))
    check("skill_chance 保留", ai.get("skill_chance") == 0.6, str(ai.get("skill_chance")))
    check("写回 actor.ai", mon["ai"] is ai)
    # 幂等
    ai2 = AI.normalize_ai(mon)
    check("幂等（二次不重复转换）", ai2 is ai and len(ai2["moves"]) == 3)
    # 无 ai
    check("无 ai → None", AI.normalize_ai({"hp": 1}) is None)


def test_2_priority_order():
    print("【2. priority：守卫命中顺序 + AND 组合 + 未知谓词 + 恒真】")
    b, mon = mk_battle(mon_hp_ratio=0.90)
    mon["ai"] = {
        "select": "priority",
        "fallback": {"type": "attack"},
        "moves": [
            {"when": {"self_hp_lt": 0.50}, "then": {"type": "skill", "skill": "ms_low"}},
            {"when": {"self_hp_lt": 0.95, "self_hp_gt": 0.80},
             "then": {"type": "skill", "skill": "ms_mid"}},
            {"when": {"unknown_pred": 1}, "then": {"type": "skill", "skill": "ms_never"}},
            {"when": {}, "then": {"type": "skill", "skill": "ms_fallback"}},
        ],
    }
    mv = AI.resolve_ai_move(b, mon)
    check("90% 血命中 ms_mid（第二条）", (mv or {}).get("skill") == "ms_mid", str(mv))
    mon["hp"] = 400
    mv2 = AI.resolve_ai_move(b, mon)
    check("40% 血命中 ms_low（第一条优先）", (mv2 or {}).get("skill") == "ms_low", str(mv2))
    mon["hp"] = 990
    mv3 = AI.resolve_ai_move(b, mon)
    check("99% 血过全部条件 → 恒真 fallback",
          (mv3 or {}).get("skill") == "ms_fallback", str(mv3))


def test_3_round_mod():
    print("【3. round_mod：act_count 节奏】")
    b, mon = mk_battle()
    mon["ai"] = {"select": "priority", "moves": [
        {"when": {"round_mod": [3, 1]}, "then": {"type": "skill", "skill": "ms_rhythm"}},
    ]}
    hits = []
    for n in range(1, 8):
        mon["act_count"] = n
        mv = AI.resolve_ai_move(b, mon)
        hits.append((mv or {}).get("skill"))
    check("act_count 1/4/7 命中（%3==1）", hits == ["ms_rhythm", None, None,
                                                    "ms_rhythm", None, None,
                                                    "ms_rhythm"], str(hits))


def test_4_hostile_low():
    print("【4. hostile_lowest_hp_lt：玩家残血追击】")
    b, mon = mk_battle(player_hp_ratio=0.20)
    mon["ai"] = {"select": "priority", "moves": [
        {"when": {"hostile_lowest_hp_lt": 0.30},
         "then": {"type": "skill", "skill": "ms_finish"}},
    ]}
    mv = AI.resolve_ai_move(b, mon)
    check("玩家 20% 血触发追击", (mv or {}).get("skill") == "ms_finish", str(mv))
    b2, mon2 = mk_battle(player_hp_ratio=0.80)
    mon2["ai"] = mon["ai"]
    mv2 = AI.resolve_ai_move(b2, mon2)
    check("玩家 80% 血不触发", mv2 is None, str(mv2))


def test_5_cd_ok():
    print("【5. cd_ok：技能冷却内不选 / 到期可选】")
    b, mon = mk_battle()
    b._now = 100.0
    # cooldown 表 key = 技能 name（actions.py 写入口径）
    mon["cooldown"] = {"测试招名": 105.0}  # 冷却到 105
    mon["ai"] = {"select": "priority", "moves": [
        {"when": {"cd_ok": "ms_skill_a"}, "then": {"type": "skill", "skill": "ms_skill_a"}},
    ]}
    # ms_skill_a 有索引（stub）且无冷却 → 可选
    mv = AI.resolve_ai_move(b, mon)
    check("无冷却可选", (mv or {}).get("skill") == "ms_skill_a", str(mv))
    # 真实技能 id（ms_nu_hou）：重建 Battle 让真实索引并入 stub 索引
    b3, mon3 = mk_battle()
    b3._now = 100.0
    mon3["skills"] = ["ms_nu_hou"]  # 咕噜的怒吼（真实技能）
    # 重新建 battle 以索引技能（Battle 构造时 _index_skills）
    sides3 = {"enemy": [mon3]}
    b3 = B2("instance", sides=sides3)
    b3._now = 100.0
    # 查真实技能 name（actor._skill_index 构造时挂）
    info = (mon3.get("_skill_index") or {}).get("ms_nu_hou")
    check("技能索引可用", info is not None and bool(info.get("name")), str(info)[:80])
    if info:
        nm = info["name"]
        mon3["cooldown"] = {nm: 200.0}
        mon3["ai"] = {"select": "priority", "moves": [
            {"when": {"cd_ok": "ms_nu_hou"}, "then": {"type": "skill", "skill": "ms_nu_hou"}},
        ]}
        mv3 = AI.resolve_ai_move(b3, mon3)
        check("冷却内不选（now=100 < 200）", mv3 is None, str(mv3))
        b3._now = 201.0
        mv4 = AI.resolve_ai_move(b3, mon3)
        check("冷却到期可选", (mv4 or {}).get("skill") == "ms_nu_hou", str(mv4))


def test_6_weighted_dist():
    print("【6. weighted：权重分布 + skill_chance 回落】")
    random.seed(42)
    b, mon = mk_battle()
    mon["ai"] = {
        "select": "weighted", "skill_chance": 1.0,
        "moves": [
            {"when": {}, "then": {"type": "skill", "skill": "ms_a"}, "weight": 3.0},
            {"when": {}, "then": {"type": "skill", "skill": "ms_b"}, "weight": 1.0},
        ],
    }
    cnt = {"ms_a": 0, "ms_b": 0}
    for _ in range(400):
        mv = AI.resolve_ai_move(b, mon)
        if mv:
            cnt[mv.get("skill")] = cnt.get(mv.get("skill"), 0) + 1
    total = cnt["ms_a"] + cnt["ms_b"]
    ra = cnt["ms_a"] / max(1, total)
    check("ms_a 占比 ≈75%（3:1 容差 ±12%）", 0.63 <= ra <= 0.87,
          f"a={cnt['ms_a']} b={cnt['ms_b']} ra={ra}")
    # skill_chance=0.3 → 大量回落
    mon["ai"]["skill_chance"] = 0.3
    none_cnt = 0
    for _ in range(400):
        if AI.resolve_ai_move(b, mon) is None:
            none_cnt += 1
    check("chance 0.3 → 回落 ≈70%（容差 ±15%）", 0.55 <= none_cnt / 400 <= 0.85,
          f"none={none_cnt}")


def test_7_actor_auto_real_monster():
    print("【7. actor_auto 端到端：真实咕噜 ai.weights 战斗自选技能】")
    from _engine_harness import C
    # 咕噜 MONSTER_MODS ai 数据
    src = C.MONSTER_MODS.get("b_goblin_chief", {}).get("ai") or {}
    check("真实 ai 数据存在", bool(src.get("weights")), str(src)[:120])
    # 构建 actor（真实怪 + skills 让技能可解析）
    mon = {"uid": "e_goblin", "id": "b_goblin_chief", "name": "哥布林酋长·咕噜",
           "role": "boss", "is_boss": True, "side": "enemy",
           "hp": 5000, "max_hp": 5000, "atk": 200, "matk": 150, "def": 50,
           "mdef": 50, "spd": 80, "lv": 20, "skills": ["ms_lve_duo_h_ling",
                                                        "ms_lian_zhan",
                                                        "ms_zhao_huan"],
           "effects": {}, "shields": {}, "cooldown": {}, "auto_act": None,
           "ai": dict(src), "act_count": 0, "ct": 0.0}
    b = B2("instance", sides={
        "enemy": [mon],
        "player": [{"uid": "p_1", "name": "勇者", "side": "player",
                    "hp": 999999, "max_hp": 999999, "atk": 100, "matk": 100,
                    "def": 50, "mdef": 50, "spd": 50, "lv": 20, "effects": {},
                    "shields": {}, "ct": 0.0}],
    })
    b._now = 0.0
    used = set()
    random.seed(7)
    for i in range(20):
        logs, ended = b.actor_auto(mon)
        # 日志里应有技能名（若放了技能）
        for l in logs:
            for sk in ("连斩", "怒吼", "掠夺"):
                if sk in str(l):
                    used.add(sk)
    check("战斗内用出技能（连斩/怒吼/掠夺至少一类）", len(used) > 0, f"used={used}")
    check("act_count 累计 20", mon.get("act_count") == 20, f"n={mon.get('act_count')}")


def main():
    print("N5B P1 通用怪 AI 决策器")
    test_1_normalize()
    test_2_priority_order()
    test_3_round_mod()
    test_4_hostile_low()
    test_5_cd_ok()
    test_6_weighted_dist()
    test_7_actor_auto_real_monster()
    print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
    if FAILURES:
        for f in FAILURES:
            print(" -", f)
        sys.exit(1)


if __name__ == "__main__":
    main()
