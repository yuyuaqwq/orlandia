# -*- coding: utf-8 -*-
"""N5b4-1 验证：命令层展示辅助函数在 saintess_engine 战斗上正确工作。

展示函数（combat.CombatCmds._status_line/_resource_line/_battle_footer/
_battle_formation_panel）N5b4-1 改读 player dict + b.sides——本测试用
saintess_engine Battle 构造真实战斗（装备装配 → 开战 → 出手挂 buff → 展示），
断言：
- 玩家 buff dict 形态（N7.1 {expire:绝对秒}）折算剩余刻显示
- 护盾 expire_at 折算
- 敌方状态（saintess_engine actor buffs 同 dict 形态）
- 面板/页脚输出不崩（saintess_engine 无 .enemies 属性 → sides 读法）

跑法：python tests/test_battle_n5b4_display.py
"""
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
TEST_DB = os.path.join(PLUGIN_DIR, "test_battle_n5b4_display.db")
os.environ.setdefault("GWEN_GAME_DB", TEST_DB)
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from saintess_engine import config as _b2config  # noqa: E402
from _engine_harness import boot as _eng_cfg; _eng_cfg()  # noqa: E402
from ext_combat import Battle as B2, make_actor  # noqa: E402
from _engine_harness import Main as CombatCmds  # noqa: E402  （原 game.commands.combat 壳 → 驱动口）

PASS = 0
FAIL = 0
FAILURES = []


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")



def stk(a, k, d=0):
    """V 系列：读效果叠层数 effects[key].stacks。"""
    e = (a or {}).get("effects") or {}
    ent = e.get(k)
    return int(ent.get("stacks", 0) or 0) if isinstance(ent, dict) else int(d)


def ent(a, k):
    """V 系列：读效果条目 dict effects[key]。"""
    e = (a or {}).get("effects") or {}
    return e.get(k) or {}


def mk_player():
    return {"qq_id": "1001", "group_id": "g1", "name": "展示勇者", "class_name": "战士",
            "level": 10, "hp": 200, "mp": 50, "max_hp": 200, "max_mp": 50,
            "equipment": {}, "class_tier": 0, "attributes": None,
            "evolve_path": 0, "race": None, "learned_skills": [],
            # v181.M-R3：player["resources"] 死字段（无生产写入）——测试不再构造
            "stacks": {}, "buffs": {}, "shields": {}}


def mk_enemy():
    return make_actor(uid="e1", name="山贼头目", side="enemy", kind="monster",
                      human_controlled=False, level=10,
                      hp=3000, max_hp=4000, atk=20, spd=10,
                      **{"def": 10})


def new_battle(player, enemy):
    sides = {"player": [make_actor(uid="p1", name=player.get("name", "你"),
                                   side="player", kind="player",
                                   human_controlled=True, class_name="战士",
                                   level=10, hp=player.get("hp", 200),
                                   max_hp=player.get("max_hp", 200),
                                   mp=player.get("mp", 50), max_mp=50,
                                   atk=40, spd=50, equipment={},
                                   skills=[], learned_skills=[],
                                   **{"def": 10})],
             "enemy": [enemy]}
    return B2("monster", sides=sides)


def test_status_line_battle_buffs():
    print("【N5b4-1 saintess_engine dict buff 形态折算】")
    cmds = CombatCmds(None)
    player = mk_player()
    enemy = mk_enemy()
    b = new_battle(player, enemy)
    focus = b.focus()
    # saintess_engine buff dict 形态：atk_up 绝对到期 50.0（now=0 → 剩 50 刻）
    focus.setdefault("effects", {})["atk_up"] = {"stacks": 1, "expire": 50.0, "stat": "atk",
                                                "op": "mul", "mult": 1.3}
    # 控制类 dict（stun 剩 3 刻：now=0 + turns 3）
    focus["effects"]["stun"] = {"stacks": 1, "expire": 3.0, "mode": "skip"}
    # 护盾 dict：expire_at 折算（now=0，剩 5 刻）
    focus.setdefault("shields", {})["we_test"] = {"value": 100, "expire_at": 5.0}
    # 真实命令层流程：行动后 sync_player_from_actor 回写 player dict（展示读 player）
    from content import bridge as BR
    BR.sync_player_from_actor(player, focus)
    s = cmds._status_line(player, b)
    check("atk_up dict → 剩50刻", "⚔️攻击↑(剩50刻)" in s, s)
    check("stun dict → 剩3刻", "🌀眩晕(剩3刻)" in s, s)
    check("护盾 100 → 5刻", "✨护盾100(5刻)" in s, s)
    # 敌方 dict buff（def_down 剩 8 刻）
    enemy.setdefault("effects", {})["def_down"] = {"stacks": 1, "expire": 8.0, "stat": "def",
                                                  "op": "mul", "mult": 0.8}
    s2 = cmds._status_line(player, b)
    check("敌方 def_down dict → 剩8刻", "💔破甲(剩8刻)" in s2, s2)


def test_resource_and_footer_battle():
    print("【N5b4-1 _resource_line / _battle_footer 在 saintess_engine 上不崩】")
    cmds = CombatCmds(None)
    player = mk_player()
    enemy = mk_enemy()
    b = new_battle(player, enemy)
    focus = b.focus()
    focus.setdefault("effects", {})["atk_up"] = {"stacks": 1, "expire": 50.0, "stat": "atk",
                                                "op": "mul", "mult": 1.3}
    # v181.M-R3：资源行改读 saintess_engine actor.effects 叠层（player.resources 为死字段，
    # 无生产写入）——无白名单资源叠层 → 空串安全
    rl0 = cmds._resource_line(player, b)
    check("无职业资源叠层 → 空串", rl0 == "", rl0)
    # 构造 actor effects zhan_yi 5 层 → 行含层数与上限（EFFECT_RULES cap=10）
    focus.setdefault("effects", {})["zhan_yi"] = {"stacks": 5}
    rl = cmds._resource_line(player, b)
    check("资源行含战意层数", "战意" in rl and "5" in rl and "/10" in rl, rl)
    # 页脚整体不崩（saintess_engine 无 .enemies 属性 → sides 读法关键路径）
    f = cmds._battle_footer(player, b, enemy)
    check("页脚含玩家血蓝", "200/200" in f, f)
    check("页脚含站位图怪物", "山贼头目" in f, f)
    # 战斗推进后展示仍不崩（advance 自动怪动一下）
    logs = []
    b.auto_run(logs, max_steps=3)
    f2 = cmds._battle_footer(player, b, enemy)
    check("推进后页脚不崩", isinstance(f2, str) and len(f2) > 0, repr(f2[:100]))


def main():
    print("=== N5b4-1 展示层 saintess_engine 适配测试 ===")
    test_status_line_battle_buffs()
    test_resource_and_footer_battle()
    print(f"\n=== 结果 PASS={PASS} FAIL={FAIL} ===")
    if FAILURES:
        for f in FAILURES:
            print(f"  - {f}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
