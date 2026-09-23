# -*- coding: utf-8 -*-
"""N5b4-2 验证：命令层战斗闭环数据流（saintess_engine 引擎路径）。

模拟真实命令（explore → attack → victory）在 CombatCmds 改造后的
数据搬运语义——构造走 _open_battle（仪式/sides/装配）、行动走
human_act + sync_player_from_actor 回写、存盘/恢复走 saintess_engine state。

跑法：python tests/test_battle_n5b4_flow.py
"""
import os
import sys
import tempfile

os.environ["GWEN_GAME_DB"] = os.path.join(tempfile.mkdtemp(), "game.db")
os.environ["GWEN_TEST_MODE"] = "1"
_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
sys.path.insert(0, _PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from _engine_harness import boot as _eng_cfg; _eng_cfg()  # noqa: E402

from content import drops as D  # noqa: E402
from _engine_harness import db  # noqa: E402
from _engine_harness import Main  # noqa: E402  （原 game.commands.combat.CombatCmds 壳 → 包内实现）
db.init_db()

# `content.combat_cmds._attach_tlog` 的注入槽（接口表第 11 行冻结名）。
# 旧宿主薄壳 `game/services/battle_bridge.py::attach_tlog` 是**平台件**（读宿主流水
# 开关 + 采集 sink），终态无该薄壳 ⇒ 本测试按同一公开注入槽补回**同款实现**：
# 开关面 = `_engine_harness.tlog_setup`，采集器 = 扩展包 `ext_reward.tlog_collect.BattleTLog`
# （逐字 = 原函数体；未启用流水时返回 b，零行为）。生产侧建议由 `host/**` 属主落地。
from _engine_harness import tlog_setup as _tlog_setup  # noqa: E402
from ext_reward.tlog_collect import BattleTLog as _BattleTLog  # noqa: E402
import content.combat_cmds as _combat_cmds  # noqa: E402


def _host_attach_tlog(b, *, btype="monster", player=None, enemies=None, seed=None):
    try:
        tl = _tlog_setup.tlog()
        if tl is None:
            return b
        _BattleTLog(tl).attach(b, btype=btype, seed=seed, player=player, enemies=enemies)
    except Exception:                                            # noqa: BLE001
        pass
    return b


_combat_cmds.bind_host(attach_tlog=_host_attach_tlog)

PASS = 0
FAIL = 0
FAILURES = []


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


def make_player(cls="战士", level=10, qid=10001):
    return {"qq_id": qid, "group_id": "g1", "name": "流程勇者", "class_name": cls,
            "level": level, "hp": 300, "mp": 50, "max_hp": 300, "max_mp": 50,
            "equipment": {}, "class_tier": 0, "attributes": None,
            "evolve_path": 0, "race": None, "learned_skills": [],
            "cur_map": "test_plain", "cur_subarea": "", "stamina": 100}


def build_wolf():
    map_obj = {"id": "test_plain", "name": "测试平原", "area": "field",
               "type": "field", "lv": 5}
    mon = D.build_monster(("test_wolf", "野狼", "dps", 3, [], []), map_obj)
    return D.build_monster_group(mon, map_obj, make_player())


def test_open_and_attack_loop():
    print("【N5b4-2 explore→attack→存盘→恢复→打完】")
    cmds = Main(None)
    gid, qid = "g_flow", 10001
    player = make_player(qid=qid)
    group = build_wolf()

    # ① explore 构造（_open_battle：仪式 → sides → 装配 → Battle）
    b = cmds._open_battle(player, group, "monster", group_id=gid, qq_id=qid)
    check("构造成功 sides", b is not None and len(b.sides_of("enemy")) == len(group))
    st = b.to_state()
    check("state 含 sides", "sides" in st and "type" in st and st["type"] == "monster")
    db.save_battle(gid, qid, st)
    cmds._lock_battle(gid, qid)

    # ② attack 恢复 + human_act + sync 回写
    row = db.get_battle(gid, qid)
    b2 = cmds._restore_battle(row["state"])
    check("恢复成功", b2 is not None)
    hp0 = b2.sides_of("enemy")[0].get("hp", 0)
    logs, ended, who = b2.human_act("attack", None, b2.focus())
    cmds._sync_battle_player(player, b2)
    dmg = hp0 - b2.sides_of("enemy")[0].get("hp", 0)
    check("普攻造成伤害", dmg > 0, f"dmg={dmg}")
    check("回写 hp 到 player", player.get("hp", 0) <= 300, f"hp={player.get('hp')}")
    # 行动后 db.update_player（命令层真实调用）
    db.update_player(gid, qid, hp=player["hp"], mp=player["mp"],
                     max_hp=player["max_hp"], max_mp=player["max_mp"])
    db.save_battle(gid, qid, b2.to_state())

    # ③ 续战恢复 → 打到结束（auto 模拟多回合玩家输入）
    b3 = None
    guard = 0
    while guard < 60:
        guard += 1
        row = db.get_battle(gid, qid)
        b3 = cmds._restore_battle(row["state"])
        if b3 is None:
            break
        if b3.result:
            break
        logs, ended, who = b3.human_act("attack", None, b3.focus())
        cmds._sync_battle_player(player, b3)
        db.update_player(gid, qid, hp=player["hp"], mp=player["mp"],
                         max_hp=player["max_hp"], max_mp=player["max_mp"])
        if ended:
            db.save_battle(gid, qid, b3.to_state())
            break
        db.save_battle(gid, qid, b3.to_state())
    check("战斗有结果", b3 is not None and b3.result in ("victory", "defeat"),
          f"result={getattr(b3, 'result', None)} guard={guard}")

    # ④ 展示函数在恢复后的 saintess_engine 上不崩
    row = db.get_battle(gid, qid)
    b4 = cmds._restore_battle(row["state"]) if row else None
    if b4 is not None:
        f = cmds._battle_footer(player, b4, cmds._b_enemy(b4) or {})
        check("战后页脚不崩", isinstance(f, str))
    db.clear_battle(gid, qid)
    cmds._unlock_battle(gid, qid)
    check("清战斗", db.get_battle(gid, qid) is None)


def test_legacy_state_cleared():
    print("【N5b4-2 旧格式存档 → 清档重开】")
    cmds = Main(None)
    gid, qid = "g_old", 10002
    legacy = {"type": "monster", "now": 2.0, "round": 1, "result": None,
              "enemy": {"name": "旧怪", "hp": 100, "max_hp": 100}}
    db.save_battle(gid, qid, legacy)
    b = cmds._restore_battle(legacy)
    check("旧格式恢复返回 None", b is None)
    db.clear_battle(gid, qid)
    check("旧格式清档", db.get_battle(gid, qid) is None)


def main():
    print("=== N5b4-2 命令层 saintess_engine 战斗闭环 ===")
    test_open_and_attack_loop()
    test_legacy_state_cleared()
    print(f"\n=== 结果 PASS={PASS} FAIL={FAIL} ===")
    if FAILURES:
        for f in FAILURES:
            print(f"  - {f}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
