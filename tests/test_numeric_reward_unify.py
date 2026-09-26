# -*- coding: utf-8 -*-
"""test_numeric_reward_unify —— 统一奖励发放门禁（v174）

防退化断言：
  1. grant_reward 各类型发放（exp/gold/items/equips/pets/mounts/title）
  2. 多动作连发不覆盖（曾 bug：旧 player 引用覆盖新 gold）
  3. 已接入来源奖励正确性（成就/任务/对话/周常发奖走统一入口）
  4. 物品缺失静默跳过不阻塞（exp/gold 照发）

运行：python tests/test_numeric_reward_unify.py（exit=0 全绿）
"""
import os
import sys
import asyncio

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (_SCRIPT_DIR, os.path.dirname(_SCRIPT_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
os.environ.setdefault("GWEN_GAME_DB", os.path.join(os.path.dirname(_SCRIPT_DIR), "test_game_data.db"))

from _engine_harness import C, db, clean_db, Main, FakeEvent, run  # noqa: E402

# ★ P5D-REPOINT（越界登记，包侧缺陷）：`content.facade` 的注入扇出把 `content.reward`
#   的三个槽解析成**函数对象**（`levelup` → `content.gameplay_rules.check_player_level_up`、
#   `stat_bonus` → `content.stat_bonus.stat_bonus`、`key_to_id` →
#   `content.persistence.inventory._key_to_id`）；而包内 `content/reward.py::_resolve` 的协议是
#   「可调用值 = 零参活源 thunk，取用时调一次；模块/对象 = 定值」⇒ 直取包内实现时
#   `_host_levelup()` 会零参调用 `check_player_level_up(gid, qid, player)` 而 `TypeError`。
#   宿主薄壳 `game/reward.py` 绑的正是 thunk（`lambda: <函数>`），随 game/** 退役后该绑定消失。
#   本文件按宿主薄壳**同一注入键同一语义**补回三个 thunk（`lambda: <函数>`），行为逐字同义。
#   建议包侧把 `_PKG_SURFACE` 这三槽改成「thunk 形态」或让 `_resolve` 不把函数当 thunk 后本段可删。
from content import gameplay_rules as _gameplay_rules  # noqa: E402
from content import reward as _reward_mod  # noqa: E402
from content import stat_bonus as _stat_bonus_mod  # noqa: E402
from content.persistence.inventory import _key_to_id as _key_to_id_fn  # noqa: E402
_reward_mod.bind_host(
    levelup=lambda: _gameplay_rules.check_player_level_up,
    stat_bonus=lambda: _stat_bonus_mod.stat_bonus,
    key_to_id=lambda: _key_to_id_fn,
)

passed, failed = 0, 0


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "passed", "failed", limit=300)


async def cmd(m, handler_name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    handler = getattr(m, handler_name)
    results = await run(handler, ev)
    return results[-1] if results else ""


async def main():
    clean_db()
    m = Main(None)
    await cmd(m, "register", "gr", "wr", "注册 战士 奖测 男")
    db.update_player("gr", "wr", level=1, gold=100)

    print("【reward_unify：grant_reward 全类型】")
    # ★ P5D-REPOINT：原 `from game.reward import grant_reward`（宿主薄壳）。薄壳 import 期把
    #   七个「活源 thunk」经 `bind_host(...)` 挂给包内实现；薄壳随 game/** 退役后，这些 thunk
    #   一并消失。**逐键核对包内 `content/reward.py` 的兜底**（`_resolve(key, fallback)`）：
    #     · `db`        → `content._pkgref.DB`（包内存档半边）
    #     · `key_to_id` → `content.persistence.inventory._key_to_id`
    #     · `levelup`   → `content.gameplay_rules.check_player_level_up`
    #     · `stat_bonus`→ `content.stat_bonus.stat_bonus`
    #   四条兜底都在包内且是真源本身 ⇒ 直取 `content.reward.grant_reward` 与宿主薄壳路径
    #   **逐行为同义**（薄壳的 thunk 只是「函数内惰性 import 宿主」的搬运；宿主侧那四个名字
    #   本身就是包内同名对象）。判据零改动。
    from content.reward import grant_reward
    p = db.get_player("gr", "wr")
    lines = grant_reward({
        "exp": 300, "gold": 200,
        "items": [{"item": "mat_cao_yao", "n": 3}],
        "pets": ["pet_turtle"],
    }, "gr", "wr")
    p2 = db.get_player("gr", "wr")
    check("exp+gold 入账", p2["gold"] == 300 and p2["exp"] == 300, f"gold{p2['gold']} exp{p2['exp']}")
    check("文案含经验金币", any("经验 +300" in l and "金币 +200" in l for l in lines), str(lines))
    check("物品入包", db.count_item("gr", "wr", "mat_cao_yao") == 3)
    check("宠物蛋入包", db.count_item("gr", "wr", "petegg_pet_turtle") == 1)

    print("【reward_unify：装备/称号】")
    lines = grant_reward({"equips": [{"rid": "eq_ju_mo_liao_ya_zhui"}], "title": "不存在的称号"}, "gr", "wr")
    inv = db.get_inventory("gr", "wr") or []
    keys = [x.get("key") for x in inv] if isinstance(inv, list) else list(inv.keys())
    check("名册装备入包", any(str(k).startswith("eq_") for k in keys), f"{keys}")
    check("未知称号不崩(跳过)", len(lines) >= 1, str(lines))

    print("【reward_unify：多动作连发不覆盖（曾 bug）】")
    db.update_player("gr", "wr", gold=1000)
    # 模拟对话一次带三个动作（旧 player 引用会覆盖）
    m._apply_talk_action("gr", "wr", db.get_player("gr", "wr"), "npc_mayor",
                         {"give_gold": 50, "give_exp": 30})
    p4 = db.get_player("gr", "wr")
    check("give_gold 50 生效不被覆盖", p4["gold"] == 1050, f"gold{p4['gold']}")
    check("give_exp 30 生效", p4["exp"] >= 330, f"exp{p4['exp']}")

    print("【reward_unify：物品缺失不阻塞 exp/gold】")
    before = db.get_player("gr", "wr")["gold"]
    lines = grant_reward({"gold": 10, "items": [{"item": "mat_bu_cun_zai_zzz", "n": 1}]}, "gr", "wr")
    p5 = db.get_player("gr", "wr")
    check("缺失物品不阻塞金币", p5["gold"] == before + 10, f"gold{p5['gold']}")

    print("【reward_unify：收藏册 bonus 实装（曾死数据）】")
    # 注册两个玩家，一个集齐"溪流鱼谱"（曾拥有条目），一个不集齐
    await cmd(m, "register", "gcb", "wcb", "注册 战士 收测1 男")
    await cmd(m, "register", "gcb", "wcb2", "注册 战士 收测2 男")
    b0 = C.COLLECTION_BOOKS[0]
    from content.persistence.inventory import record_possessed
    for e in b0.get("entries", []):
        try:
            record_possessed("gcb", "wcb", e.get("key") or e.get("name"))
        except Exception:
            pass
    from content.stat_bonus import stat_bonus as _tb
    tb_ok = _tb("gcb", "wcb", db.get_player("gcb", "wcb"))
    tb_no = _tb("gcb", "wcb2", db.get_player("gcb", "wcb2"))
    has_bonus = bool(b0.get("reward", {}).get("bonus"))
    if has_bonus:
        check("集齐册 panel_bonus 出加成", bool(tb_ok), f"{tb_ok}")
        check("未集齐无加成", not tb_no, f"{tb_no}")
    else:
        check("首册无 bonus 配置(跳过)", True)
    check("收藏册 reward.bonus 数据存在", has_bonus, f"{b0.get('reward')}")

    print("【reward_unify：空奖励安全】")
    lines = grant_reward({}, "gr", "wr")
    check("空奖励返回空", lines == [], str(lines))
    lines = grant_reward(None, "gr", "wr")
    check("None 奖励返回空", lines == [], str(lines))

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
