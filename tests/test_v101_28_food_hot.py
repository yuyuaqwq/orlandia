# -*- coding: utf-8 -*-
"""v101.28 食物持续恢复（hot）专项测试：
1. 食物 infer_template → food；药水仍 → heal（互不干扰）
2. tpl_food 战斗内 payload = "hot:比例,比例,回合"
3. _do_use_item hot: 分支 → 设置 p_hot + 播报
4. 每回合开始 hot 结算（回血/回蓝 + 剩余回合 + 结束清理）
5. tpl_food 战斗外 = 即时回复（合并播报）
"""
import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ["GWEN_GAME_DB"] = os.path.join(PLUGIN_DIR, "test_game_data.db")
sys.path.insert(0, PLUGIN_DIR)

from _engine_harness import C
from content import item_templates as IT


PASS = 0
FAIL = 0
from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL")

# ---- 1. infer_template 分流 ----
print("== 1. 模板分流 ==")
food = {"name": "麦酒", "price": 10, "hot": 0.05, "hot_turns": 3, "hot_mana": 0.06,
        "heal": 0.15, "mana": 0.15, "stamina": 15}
potion = {"name": "治疗药水(小)", "price": 10, "heal": 0.2}
check("食物带 hot → food 模板", IT.infer_template(food) == "food")
check("药水无 hot → heal 模板", IT.infer_template(potion) == "heal")

# 真实数据抽查
ale = C.ITEMS.get("i_ale", {})
check("真实麦酒有 hot 字段", "hot" in ale, str(ale))
check("真实麦酒 hot=0.05", ale.get("hot") == 0.05)
check("真实麦酒 desc 含持续恢复说明", "战斗中每刻" in ale.get("desc", ""), ale.get("desc", ""))
treat = C.ITEMS.get("i_treat_s", {})
check("治疗药水无 hot 字段", "hot" not in treat)
check("治疗药水 desc 未污染", "战斗中每刻" not in treat.get("desc", ""))
check("真实麦酒 infer→food", IT.infer_template(ale) == "food")
check("真实药水 infer→heal", IT.infer_template(treat) == "heal")

# ---- 2. tpl_food 战斗内 payload ----
print("== 2. tpl_food payload ==")
class FakeCtx:
    def __init__(self, battle):
        self.battle = battle
        self.data = ale
        self._focus = {"hp": 100, "max_hp": 100, "mp": 50, "max_mp": 100}
    def _db(self):
        class D:
            def update_player(self, *a, **k): pass
        return D()
    def hook(self, name, *a, **k):
        if name == "stamina_msg":
            return ""
        return 0

r = IT.TEMPLATES["food"](FakeCtx(battle=True))
check("战斗内 payload=hot:0.05,0.06,3", r.payload == "hot:0.05,0.06,3", r.payload)

# ---- 3. (N10 删旧：战斗内 hot 全链路已由 saintess_engine regen_hot period 验证——
#    test_battle_n10_b7_food test_honey_regen + battle_item_use hot: 分支覆盖，
#    旧 Battle.actor_turn hot 段退役) ----

# ---- 4. 战斗外即时回复 ----
print("== 4. tpl_food 战斗外 ==")
class CtxOut:
    def __init__(self):
        self.battle = None
        self.data = ale
        self._focus = {"hp": 50, "max_hp": 100, "mp": 20, "max_mp": 100}
        self.group_id = "g1"
        self.qq_id = "q1"
        self.removed = False
    def _db(self):
        class D:
            def update_player(self, g, q, **k): pass
        return D()
    def hook(self, name, *a, **k):
        if name == "stamina_msg":
            return "⚡ 恢复 15 点体力(85/100)\n"
        if name == "add_stamina":
            return 15
        return 0

co = CtxOut()
ro = IT.TEMPLATES["food"](co)
check("战斗外即时回血文案", "恢复 15 点生命" in ro.text, ro.text)
check("战斗外带体力文案", "恢复 15 点体力" in ro.text, ro.text)

# 满血且无 stamina/mana 需求 → 拦截
class CtxFull:
    def __init__(self):
        self.battle = None
        self.data = {"name": "炖菜", "heal": 0.4, "hot": 0.06, "hot_turns": 3}
        self._focus = {"hp": 100, "max_hp": 100, "mp": 100, "max_mp": 100}
        self.group_id = "g1"
        self.qq_id = "q1"
    def _db(self):
        class D:
            def update_player(self, *a, **k): pass
        return D()
    def hook(self, name, *a, **k): return ""
rf = IT.TEMPLATES["food"](CtxFull())
check("满血纯治疗拦截不消耗", rf.consume is False and "满的" in rf.text, rf.text)

# ---- 5. 数据完整性 ----
print("== 5. 数据完整性 ==")
food_keys = [k for k, v in C.ITEMS.items()
             if isinstance(v, dict) and v.get("hot_turns") is not None]
buff_food_keys = [k for k, v in C.ITEMS.items()
                  if isinstance(v, dict) and v.get("effect")
                  and (v.get("heal") or v.get("mana") or v.get("stamina") is not None)]
check("hot 食物总量 ≥ 30", len(food_keys) >= 30, str(len(food_keys)))
check("战斗料理(增益) ≥ 5", len(buff_food_keys) >= 5, str(buff_food_keys))
check("矮人烈酒 desc 修复(无'3 场战斗')", "3 场战斗" not in C.ITEMS.get("i_dwarf_liquor", {}).get("desc", ""))
check("矮人烈酒走 food_buff", IT.infer_template(C.ITEMS["i_dwarf_liquor"]) == "food_buff")
check("矮人烈酒非 buff_atk(原 30% 超模)", C.ITEMS["i_dwarf_liquor"].get("effect") != "buff_atk")
affix_food_keys = [k for k, v in C.ITEMS.items()
                   if isinstance(v, dict) and v.get("food_effect")
                   and (v.get("heal") or v.get("mana") or v.get("stamina") is not None)]
check("效果料理(food_effect) ≥ 15", len(affix_food_keys) >= 15, str(len(affix_food_keys)))
bad = []
for k in food_keys:
    v = C.ITEMS[k]
    if not (1 <= v.get("hot_turns", 0) <= 5):
        bad.append((k, "turns", v.get("hot_turns")))
    h = v.get("hot") or 0
    hm = v.get("hot_mana") or 0
    if h < 0 or h > 0.3 or hm < 0 or hm > 0.3:
        bad.append((k, "hot", (h, hm)))
check("hot 数值全部合法", not bad, str(bad[:3]))

# ---- 6. food_buff 模板 ----
print("== 6. food_buff 战斗料理 ==")
burger = C.ITEMS["i_deer_burger"]
class BufCtx:
    def __init__(self, battle):
        self.battle = battle
        self.data = burger
        self._focus = {"hp": 50, "max_hp": 100, "mp": 50, "max_mp": 100}
        self.group_id = "g1"
        self.qq_id = "q1"
    def _db(self):
        class D:
            def update_player(self, *a, **k): pass
        return D()
    def hook(self, n, *a, **k):
        if n == "stamina_msg":
            return "⚡ 恢复 35 点体力(85/100)\n"
        return 0

rb = IT.TEMPLATES["food_buff"](BufCtx(battle=True))
check("汉堡战斗内 payload=buff:food_def_up", rb.payload == "buff:food_def_up", rb.payload)
ro = IT.TEMPLATES["food_buff"](BufCtx(battle=False))
check("汉堡战斗外即时回血+体力", "恢复 30 点生命" in ro.text and "恢复 35 点体力" in ro.text, ro.text)

# 战斗内吃料理播报（food_ 前缀 → 料理文案；saintess_engine N10：buff: 翻译走 battle_item_use）
from ext_combat import Battle as _B2
from ext_combat import make_actor as _mk2
from saintess_engine import config as _b2cfg
from _engine_harness import boot as _eng_cfg; _eng_cfg()
_p2 = _mk2(uid="p_q1", name="试吃", side="player", kind="player", human_controlled=True,
           class_name="cls_zhan_shi", level=1, hp=100, max_hp=100, mp=50, max_mp=100,
           atk=10, matk=5, spd=10, crit=0.0, equipment={}, skills=[], learned_skills=[],
           race="human", evolve_path=0, class_tier=0, attributes={}, **{"def": 20, "mdef": 10})
_e2 = _mk2(uid="e_0", name="野狗", side="enemy", kind="monster", level=1,
           hp=500, max_hp=500, atk=5, matk=5, spd=5, crit=0.0, exp=0, gold=0,
           **{"def": 0, "mdef": 0})
_b2 = _B2(btype="monster", sides={"player": [_p2], "enemy": [_e2]})
from content.mech.item_use import translate as _tr_food
_l2, _c2, _r2 = _tr_food(_b2, _p2, "buff:food_def_up")
check("料理播报(非'饮下战斗药水')", any("吃下了料理" in str(l) for l in (_l2 or [])), str(_l2)[:120])

# ---- 7. food_effect 效果料理 ----
print("== 7. food_effect 效果料理 ==")
snake = C.ITEMS["i_snake_soup"]
check("蛇羹 infer→food_effect", IT.infer_template(snake) == "food_effect", str(snake.get("food_effect")))
check("蛇羹 desc 含【吸血】", "【吸血】" in snake.get("desc", ""), snake.get("desc", ""))
class AffCtx:
    def __init__(self, battle):
        self.battle = battle
        self.data = snake
        self._focus = {"hp": 50, "max_hp": 100, "mp": 50, "max_mp": 100}
        self.group_id = "g1"
        self.qq_id = "q1"
    def _db(self):
        class D:
            def update_player(self, *a, **k): pass
        return D()
    def hook(self, n, *a, **k):
        if n == "stamina_msg":
            return "⚡ 恢复 25 点体力(85/100)\n"
        return 0
ra = IT.TEMPLATES["food_effect"](AffCtx(battle=True))
check("蛇羹战斗内 payload=foodfx:lifesteal", ra.payload == "foodfx:lifesteal", ra.payload)
ro2 = IT.TEMPLATES["food_effect"](AffCtx(battle=False))
check("蛇羹战斗外恢复", "恢复 20 点生命" in ro2.text, ro2.text)

# (N10 删旧：战斗内 foodfx 效果段退役——蛇羹吸血/圣餐面包盾/回春回合回复已由
#  saintess_engine B7 覆盖，见 test_battle_n10_b7_food test_snake_soup_lifesteal /
#  test_sacred_bread_shield / test_honey_regen；此处只保留模板层 payload 验证)

print(f"\n结果: {PASS} 通过, {FAIL} 失败")
sys.exit(1 if FAIL else 0)