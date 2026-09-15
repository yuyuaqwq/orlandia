# -*- coding: utf-8 -*-
"""v99.5 成就条件注册表验收：achievement_conds

验收标准（设计文档）：
1. 扩展性：注册新条件类型 → cond_met 立即生效，无需改 achievements.py
2. 安全降级：未知 type → False（不报错）
3. 全覆盖：成就数据用到的 cond type 全部有注册
4. 行为等价：抽样验证关键条件（level/kills/prof_lv/flag/quest_done/faction 受限）

独立运行：python tests/test_v99_05_achievement_conds.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db  # noqa: F401
from content import achievement_conds as AC  # ★ B18-REPOINT：直取包内实现本体（宿主同名壳不再被测试引用）
from content.achievements import cond_met
# ★ PFIX P5（2026-09-15）：打桩面 = **实现本体**。
#   条件实现（`content/achievement_conds.py`）读的是包内存储层 `content/_pkgref.DB`
#   （= `content.persistence`）；conftest 的 `db` 是宿主 `game/db.py`（`game/store/**`
#   对包内实现的**拷贝壳**）⇒ 改写 `db.get_quests` / `db.count_item` 只落在宿主命名空间，
#   包内实现读自己的绑定 ⇒ 静默 no-op（与 P1 同型缺陷，且 PATCHAUDIT 的哨兵看不见：
#   它扫的是「宿主**模块名**的改写」，`db` 是从 conftest 拿来的别名）。
#   故这里把桩打到实现本体的同名函数上（与 test_v97_05 的 P1 修法同口径）。
import content.persistence as _PDB  # noqa: E402  包内存储层（实现本体）

PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}")


player = {"qq_id": "q1", "class_name": "cls_zhan_shi", "level": 15,
          "learned_skills": ["a", "b"], "evolve_path": 1,
          "apprentices": ["x"], "hidden_class_unlock": ["cls_mu_shi"]}
stats = {"kills": 50, "deaths": 1, "elite_kills": 5, "boss_kills": 2,
         "inst_clears": 3, "party_count": 2, "world_events": 1, "visited_areas": 10}
profs = {"gather": {"lv": 5}, "mine": {"lv": 12}}
extra = {"flags": {"met_old_man": True}, "fish_king": True,
         "quest_done": "quest_hidden_1", "inst_ids": {"inst_a"}}


# ============ 1. 扩展性 ============
print("【1. 扩展性】")
BEFORE = set(AC.COND_CHECKS.keys())


@AC.register("test_fake_cond")
def _c_test_fake(player, stats, profs, extra, cond):
    return True


check("注册新条件后 COND_CHECKS 含新 key", "test_fake_cond" in AC.COND_CHECKS)
check("新条件立即生效", cond_met(player, stats, profs, extra, {"type": "test_fake_cond"}) is True)
AC.COND_CHECKS.pop("test_fake_cond")

# ============ 2. 安全降级 ============
print("【2. 安全降级】")
check("未知 type → False", cond_met(player, stats, profs, extra, {"type": "not_a_type"}) is False)
check("空 cond → False", cond_met(player, stats, profs, extra, {}) is False)
check("None cond → False", cond_met(player, stats, profs, extra, None) is False)

# ============ 3. 行为抽样 ============
print("【3. 行为抽样】")
check("registered（有 player）", cond_met(player, stats, profs, extra, {"type": "registered"}) is True)
check("level（15 ≥ 15）", cond_met(player, stats, profs, extra, {"type": "level", "value": 15}) is True)
check("level 未达标", cond_met(player, stats, profs, extra, {"type": "level", "value": 16}) is False)
check("kills（50 ≥ 50）", cond_met(player, stats, profs, extra, {"type": "kills", "value": 50}) is True)
check("kills no_death（有死亡不满足）", cond_met(player, stats, profs, extra, {"type": "kills", "value": 50, "no_death": True}) is False)
check("elite（5 ≥ 5）", cond_met(player, stats, profs, extra, {"type": "elite", "value": 5}) is True)
check("prof_lv（mine 12 ≥ 10）", cond_met(player, stats, profs, extra, {"type": "prof_lv", "key": "mine", "value": 10}) is True)
check("prof_any10（mine 12）", cond_met(player, stats, profs, extra, {"type": "prof_any10"}) is True)
check("flag（met_old_man）", cond_met(player, stats, profs, extra, {"type": "flag", "flag": "met_old_man"}) is True)
check("flag 未设置", cond_met(player, stats, profs, extra, {"type": "flag", "flag": "nope"}) is False)
check("fish_king（extra）", cond_met(player, stats, profs, extra, {"type": "fish_king"}) is True)
check("quest_done（extra 命中）", cond_met(player, stats, profs, extra, {"type": "quest_done", "key": "quest_hidden_1"}) is True)
check("quest_done（extra 未命中→历史恒 False）", cond_met(player, stats, profs, extra, {"type": "quest_done", "key": "quest_other"}) is False)
check("item_has（历史恒 False，group_id 缺失）", cond_met(player, stats, profs, extra, {"type": "item_has", "key": "xxx"}) is False)
check("faction（国战延迟）", cond_met(player, stats, profs, extra, {"type": "faction"}) is False)
check("inst_id（extra 集合命中）", cond_met(player, stats, profs, extra, {"type": "inst_id", "inst": "inst_a"}) is True)
check("hidden_monsters_all（空集合）", cond_met(player, stats, profs, extra, {"type": "hidden_monsters_all"}) is False)
check("hidden_class（已解锁）", cond_met(player, stats, profs, extra, {"type": "hidden_class", "key": "cls_mu_shi"}) is True)

# ============ 3.5 quest_done / item_has 修复（v100.3b） ============
print("【3.5 quest_done/item_has 修复】")
check("无 group_id 时 quest_done 保持旧行为（False）",
      cond_met(player, stats, profs, extra, {"type": "quest_done", "key": "s_hidden_ember"}) is False)
check("无 group_id 时 item_has 保持旧行为（False）",
      cond_met(player, stats, profs, extra, {"type": "item_has", "key": "eq_starfall_sword"}) is False)
_extra2 = {}
_db_orig_quests = _PDB.get_quests
_PDB.get_quests = lambda gid, qq: {"side": {"s_hidden_ember": {"status": "done"}, "s_hidden_library": {"status": "active"}}}
check("quest_done：side status=done 解锁", cond_met(player, stats, profs, _extra2, {"type": "quest_done", "key": "s_hidden_ember"}, "g1") is True)
check("quest_done：side status=active 不解锁", cond_met(player, stats, profs, _extra2, {"type": "quest_done", "key": "s_hidden_library"}, "g1") is False)
check("quest_done：未知任务不解锁", cond_met(player, stats, profs, _extra2, {"type": "quest_done", "key": "s_unknown"}, "g1") is False)
_PDB.get_quests = _db_orig_quests
_db_orig_count = _PDB.count_item
_PDB.count_item = lambda gid, qq, name: 1 if name == "星陨之剑" else 0
check("item_has：背包持有解锁", cond_met(player, stats, profs, _extra2, {"type": "item_has", "key": "eq_starfall_sword"}, "g1") is True)
_PDB.count_item = lambda gid, qq, name: 0
_p2 = dict(player); _p2["equipment"] = {"weapon": {"name": "星陨之剑"}}
check("item_has：已装备解锁", cond_met(_p2, stats, profs, _extra2, {"type": "item_has", "key": "eq_starfall_sword"}, "g1") is True)
check("item_has：都没有不解锁", cond_met(player, stats, profs, _extra2, {"type": "item_has", "key": "eq_starfall_sword"}, "g1") is False)
check("extra 副本注入不污染调用方", "_group_id" not in _extra2)
_PDB.count_item = _db_orig_count

# ============ 4. 全覆盖 ============
print("【4. 数据覆盖检查】")
import json
# B16 收口：宿主 game/data 已删 —— 成就条件真源 = 包内域 content/data/achievements.json
# （原口径 = 正则扫 .py 源码里的 `"type": "..."`；改结构遍历全量 JSON，取值集合实测 44 == 44 全等）
_ACH_JSON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "content", "data", "achievements.json")
with open(_ACH_JSON, encoding="utf-8") as _f:
    _ACH_RAW = json.load(_f)

def _collect_cond_types(node, out):
    if isinstance(node, dict):
        if isinstance(node.get("type"), str):
            out.add(node["type"])
        for _v in node.values():
            _collect_cond_types(_v, out)
    elif isinstance(node, list):
        for _v in node:
            _collect_cond_types(_v, out)

data_types = set()
_collect_cond_types(_ACH_RAW, data_types)
registered = set(AC.COND_CHECKS.keys())
missing = data_types - registered
check(f"成就数据 cond type 全覆盖（数据 {len(data_types)} 种）", not missing)
if missing:
    print("  缺失:", sorted(missing))
# v151：hidden_class/hidden_class_lv（隐藏职业解锁）与 skill_has 为引擎保留条件——
# 隐藏职业全删后成就表无引用（保留供未来数据挂载/兼容旧档判定），不在孤儿告警范围
_reserved = {"test_fake_cond", "hidden_class", "hidden_class_lv", "skill_has"}
check("注册表无孤儿（除测试外全部被数据使用）", registered - data_types - _reserved == set())

print()
print(f"结果: {PASS} 通过, {FAIL} 失败")
sys.exit(1 if FAIL else 0)
