# -*- coding: utf-8 -*-
"""v136 Phase 3 符文可制作+可拆卸验收测试。

覆盖：
1. 符文制作（『符文制作 <符文名>』）：材料足 → 成功得符文、扣素材/碎片/金币
2. 符文制作：材料不足拦截（不扣金币不产出）
3. 符文拆卸（『符文拆卸 <装备名> [孔位]』）：拆符文 → 回收符文碎片×等级 + 扣手续费
4. 符文碎片是有效材料（count_item / remove_item 可操作）

要点：
- 铁匠铺位置 oak_town_3（ENHANCE_SMITH_MAPS 内），体力已由 make_player 拉满
- 符文制作走锻造副业经验（craft），无需拜师（_prof_active_check 不强制）
- 拆卸目标 = 装备 enchant 列表里的 effect 项（符文），与属性附魔 stat 项区分
"""
import os
import sys

os.environ.setdefault("GWEN_GAME_DB", os.path.abspath("test_v136_rune_craft.db"))
sys.path.insert(0, "tests")

from conftest import C, db, clean_db, Main, FakeEvent, run  # noqa: E402


def _cmd(m, handler_name, gid, qid, msg):
    """同步跑一个 async handler，返回最后一条 plain_result。"""
    import asyncio
    ev = FakeEvent(gid, qid, msg)
    handler = getattr(m, handler_name)
    results = asyncio.run(run(handler, ev))
    return results[-1] if results else ""


def _smith_player(m, gid, qid, gold=50000):
    """把玩家挪到铁匠铺并给足金币，返回 player dict。"""
    db.update_player(gid, qid, cur_map="oak_town", cur_subarea="oak_town_3", gold=gold)
    return db.get_player(gid, qid)


# ---------- 1. 符文制作：材料足 → 成功 ----------
def test_rune_craft_success():
    clean_db()
    m = Main(None)
    _cmd(m, "register", "g1", "e1", "注册 战士 铁匠 男")
    _smith_player(m, "g1", "e1", gold=100000)
    # 材料：裂鬃獠牙×3 + 符文碎片×3（残忍 rn_brutal 是 purple：素材×3 + 碎片×4）
    # 先查配方消耗（用面板文本断言）；直接按表给足
    cfg = C.RUNE_CRAFT["rn_brutal"]
    shards = C.RUNE_CRAFT_SHARDS["purple"]
    db.add_item("g1", "e1", cfg["mat"],
                {"name": C.display("materials", cfg["mat"]), "type": "材料", "stackable": True, "price": 5},
                cfg["count"])
    db.add_item("g1", "e1", C.RUNE_SHARD_KEY,
                {"name": "符文碎片", "type": "材料", "stackable": True, "price": 100}, shards)
    gold_before = db.get_player("g1", "e1")["gold"]
    out = _cmd(m, "rune_craft", "g1", "e1", "符文制作 残忍")
    assert "符文制作成功" in out, out
    assert "史诗符文·残忍 I" in out, out
    # 扣材料：素材 0、碎片 0
    assert db.count_item("g1", "e1", C.display("materials", cfg["mat"])) == 0
    assert db.count_item("g1", "e1", "符文碎片") == 0
    # 扣金币 = cost//2（1500//2=750）
    fee = C.RUNES["rn_brutal"]["cost"] // 2
    assert db.get_player("g1", "e1")["gold"] == gold_before - fee
    # 产出 1 级符文
    assert db.count_item("g1", "e1", "史诗符文·残忍 I") == 1


def test_rune_craft_resolve_by_id_and_substring():
    clean_db()
    m = Main(None)
    _cmd(m, "register", "g1", "e1", "注册 战士 铁匠 男")
    _smith_player(m, "g1", "e1", gold=100000)
    # rn_burn 是 blue：素材×2 + 碎片×3
    cfg = C.RUNE_CRAFT["rn_burn"]
    shards = C.RUNE_CRAFT_SHARDS["blue"]
    db.add_item("g1", "e1", cfg["mat"],
                {"name": C.display("materials", cfg["mat"]), "type": "材料", "stackable": True, "price": 5},
                cfg["count"] * 2)
    db.add_item("g1", "e1", C.RUNE_SHARD_KEY,
                {"name": "符文碎片", "type": "材料", "stackable": True, "price": 100}, shards * 2)
    # 中文子串『灼』→ 灼热
    out = _cmd(m, "rune_craft", "g1", "e1", "符文制作 灼")
    assert "符文制作成功" in out and "稀有符文·灼热 I" in out, out
    # 残量校验：第一次做掉素材×2/碎片×3，剩素材×2/碎片×3 再做一次 ID 形式
    out2 = _cmd(m, "rune_craft", "g1", "e1", "符文制作 rn_burn")
    assert "符文制作成功" in out2, out2
    assert db.count_item("g1", "e1", "稀有符文·灼热 I") == 2


# ---------- 2. 符文制作：材料不足拦截 ----------
def test_rune_craft_material_shortage():
    clean_db()
    m = Main(None)
    _cmd(m, "register", "g1", "e1", "注册 战士 铁匠 男")
    _smith_player(m, "g1", "e1", gold=100000)
    # 素材不足（0 个）
    out = _cmd(m, "rune_craft", "g1", "e1", "符文制作 残忍")
    assert "材料不足" in out, out
    gold_after = db.get_player("g1", "e1")["gold"]
    assert gold_after == 100000, "材料不足不应扣金币"
    assert db.count_item("g1", "e1", "史诗符文·残忍 I") == 0
    # 素材足但碎片不足
    cfg = C.RUNE_CRAFT["rn_brutal"]
    db.add_item("g1", "e1", cfg["mat"],
                {"name": C.display("materials", cfg["mat"]), "type": "材料", "stackable": True, "price": 5},
                cfg["count"])
    out = _cmd(m, "rune_craft", "g1", "e1", "符文制作 残忍")
    assert "符文碎片不足" in out, out
    assert db.get_player("g1", "e1")["gold"] == 100000
    # 金币不足
    db.add_item("g1", "e1", C.RUNE_SHARD_KEY,
                {"name": "符文碎片", "type": "材料", "stackable": True, "price": 100},
                C.RUNE_CRAFT_SHARDS["purple"])
    db.update_player("g1", "e1", gold=10)
    out = _cmd(m, "rune_craft", "g1", "e1", "符文制作 残忍")
    assert "金币" in out and "你只有" in out, out
    assert db.count_item("g1", "e1", "史诗符文·残忍 I") == 0


def test_rune_craft_requires_smith():
    clean_db()
    m = Main(None)
    _cmd(m, "register", "g1", "e1", "注册 战士 铁匠 男")
    # 不在铁匠铺（默认出生点）
    out = _cmd(m, "rune_craft", "g1", "e1", "符文制作 残忍")
    assert "铁匠铺" in out, out


# ---------- 3. 符文拆卸 ----------
def _mk_equip_with_rune(name="铁剑", quality="blue", runes=((1, "brutal"),)):
    """构造一件带符文的装备 data（enchant 里 effect 项 = 符文）。"""
    enchant = [{"effect": eff, "lvl": lv} for lv, eff in runes]
    return {
        "slot": "weapon", "lv": 20, "quality": quality, "name": name,
        "stats": {"atk": 10}, "affixes": [], "enchant": enchant,
    }


def test_rune_remove_success():
    clean_db()
    m = Main(None)
    _cmd(m, "register", "g1", "e1", "注册 战士 铁匠 男")
    _smith_player(m, "g1", "e1", gold=100000)
    eq = _mk_equip_with_rune(runes=((1, "brutal"), (2, "burn")))
    db.add_item("g1", "e1", "eq_test1", eq)
    gold_before = db.get_player("g1", "e1")["gold"]
    # 默认拆最后一个符文（burn Lv.2 → 手续费 2000，碎片×2）
    out = _cmd(m, "rune_remove", "g1", "e1", "符文拆卸 铁剑")
    assert "符文拆卸成功" in out and "灼热" in out, out
    assert "碎片×2" in out, out
    assert db.get_player("g1", "e1")["gold"] == gold_before - 2000
    assert db.count_item("g1", "e1", "符文碎片") == 2
    # 装备 enchant 只剩 brutal
    eq2 = db.get_inventory("g1", "e1")[0]["data"]
    assert [e.get("effect") for e in eq2["enchant"]] == ["brutal"]
    # 显式孔位 1 → 拆 brutal（Lv.1 → 手续费 1000，碎片×1）
    out2 = _cmd(m, "rune_remove", "g1", "e1", "符文拆卸 铁剑 1")
    assert "符文拆卸成功" in out2 and "残忍" in out2, out2
    assert db.count_item("g1", "e1", "符文碎片") == 3
    eq3 = db.get_inventory("g1", "e1")[0]["data"]
    assert eq3["enchant"] == []


def test_rune_remove_insufficient_gold():
    clean_db()
    m = Main(None)
    _cmd(m, "register", "g1", "e1", "注册 战士 铁匠 男")
    _smith_player(m, "g1", "e1", gold=500)
    eq = _mk_equip_with_rune(runes=((3, "chain"),))
    db.add_item("g1", "e1", "eq_test2", eq)
    out = _cmd(m, "rune_remove", "g1", "e1", "符文拆卸 铁剑")
    assert "3000" in out and "金币" in out, out
    assert db.count_item("g1", "e1", "符文碎片") == 0
    assert db.get_player("g1", "e1")["gold"] == 500


def test_rune_remove_no_rune_and_missing_equip():
    clean_db()
    m = Main(None)
    _cmd(m, "register", "g1", "e1", "注册 战士 铁匠 男")
    _smith_player(m, "g1", "e1", gold=100000)
    # 无符文装备
    eq = _mk_equip_with_rune(runes=())
    db.add_item("g1", "e1", "eq_test3", eq)
    out = _cmd(m, "rune_remove", "g1", "e1", "符文拆卸 铁剑")
    assert "没有刻印任何符文" in out, out
    # 装备不存在
    out2 = _cmd(m, "rune_remove", "g1", "e1", "符文拆卸 不存在之剑")
    assert "没有叫" in out2, out2


def test_rune_remove_equipped_weapon():
    clean_db()
    m = Main(None)
    _cmd(m, "register", "g1", "e1", "注册 战士 铁匠 男")
    _smith_player(m, "g1", "e1", gold=100000)
    eq = _mk_equip_with_rune(name="烈焰之刃", quality="purple", runes=((2, "thorns"),))
    db.update_player("g1", "e1", equipment={"weapon": eq})
    out = _cmd(m, "rune_remove", "g1", "e1", "符文拆卸 烈焰之刃")
    assert "符文拆卸成功" in out and "荆棘" in out, out
    p = db.get_player("g1", "e1")
    assert p["equipment"]["weapon"]["enchant"] == []
    assert db.count_item("g1", "e1", "符文碎片") == 2


# ---------- 4. 符文碎片是有效材料 ----------
def test_rune_shard_valid_material():
    clean_db()
    m = Main(None)
    _cmd(m, "register", "g1", "e1", "注册 战士 铁匠 男")
    # 材料表定义存在
    assert C.RUNE_SHARD_KEY in C.MATERIALS
    assert C.MATERIALS[C.RUNE_SHARD_KEY]["name"] == "符文碎片"
    assert C.MATERIALS[C.RUNE_SHARD_KEY]["price"] == 100
    # 可堆叠入库 / count / remove
    db.add_item("g1", "e1", C.RUNE_SHARD_KEY,
                {"name": "符文碎片", "type": "材料", "stackable": True, "price": 100}, 5)
    assert db.count_item("g1", "e1", "符文碎片") == 5
    db.add_item("g1", "e1", C.RUNE_SHARD_KEY,
                {"name": "符文碎片", "type": "材料", "stackable": True, "price": 100}, 2)
    assert db.count_item("g1", "e1", "符文碎片") == 7
    assert db.remove_item("g1", "e1", C.RUNE_SHARD_KEY, 3)
    assert db.count_item("g1", "e1", "符文碎片") == 4
    # 制作面板展示配方（移到铁匠铺）
    _smith_player(m, "g1", "e1", gold=100000)
    out = _cmd(m, "rune_craft", "g1", "e1", "符文制作")
    assert "符文制作" in out and "符文碎片" in out, out[:200]


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-x", "-q"]))
