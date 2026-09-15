# -*- coding: utf-8 -*-
"""v83 收藏鱼集成测试：_settle_fishing 彩蛋判定"""
import sys, os, random, asyncio
PLUGIN_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "plugins", "dragonfall"))
sys.path.insert(0, PLUGIN_DIR)
sys.path.insert(0, os.path.join(PLUGIN_DIR, "tests"))
# v105 R3 修复：原路径计算错误（多拼一层 data/），且 conftest 已 setdefault 正确 TEST_DB，这里不再手动设置
# os.environ["GWEN_GAME_DB"] = os.path.join(PLUGIN_DIR, "test_game_data.db")

from _engine_harness import clean_db, make_player  # noqa: E402
from _engine_harness import C, db  # noqa: E402
from _engine_harness import Main  # noqa: E402

passed = failed = 0
def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ✅", name)
    else:
        failed += 1
        print("  ❌", name, detail)

async def main():
    clean_db()
    m = Main(None)
    # 注册玩家（make_player: 战士 旅人）
    make_player("g1", "w1", "旅人", "战士")
    db.init_stats("g1", "w1")
    db.update_player("g1", "w1", cur_map="oak_plain")
    db.add_prof_exp("g1", "w1", "fishing", 0)

    # 伪造等待状态
    import time
    st = {"finish": time.time() - 10, "type": "fishing", "spot": "橡木溪流", "spot_map": "oak_plain"}
    db.set_event_state(f"prof_wait_w1", json.dumps(st, ensure_ascii=False))

    # 强制彩蛋命中：monkeypatch roll_collect_fish
    # ★ 终态打桩落点 = 包内真源模块 `content.fishing`（`content/facade.py::_NAME_SRC`
    #   把 `roll_collect_fish` 直指 `content.fishing`；旧宿主下 `game.content` 是真模块）。
    import content.fishing as _fishing_mod
    orig = _fishing_mod.roll_collect_fish
    calls = {"n": 0}
    def fake_roll(spot_id=None, is_night=False):
        calls["n"] += 1
        return {"id": "mat_rainbow_kite", "name": "虹彩龙鲤", "chance": 1.0}
    _fishing_mod.roll_collect_fish = fake_roll
    try:
        out = m._settle_fishing("g1", "w1", st)
    finally:
        _fishing_mod.roll_collect_fish = orig
    check("彩蛋命中提示", out and "虹彩龙鲤" in out and "彩蛋收藏品" in out, str(out)[:200])
    # 入包
    check("收藏鱼入包", db.count_item("g1", "w1", "mat_rainbow_kite") >= 1, "")
    # 计数
    import sqlite3
    conn = sqlite3.connect(db.db_path())
    r = conn.execute("SELECT catch_collect FROM stats WHERE qq_id='w1'").fetchone()
    conn.close()
    check("catch_collect 计数", r and r[0] >= 1, str(r))

    # 概率路径：未命中时无彩蛋文案（v110.5 X3：真实 roll_collect_fish 为随机 → 必须固定
    # seed 才稳定。oak_plain 仅虹彩龙鲤(spots=None, chance=0.0005) 可判定，seed(1) 首个
    # random()≈0.134 恒≥0.0005 → 必 miss）
    random.seed(1)
    out2 = m._settle_fishing("g1", "w1", st)
    check("未命中无彩蛋", out2 and "彩蛋收藏品" not in out2, str(out2)[:200])

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    import json
    sys.exit(0 if asyncio.run(main()) else 1)
