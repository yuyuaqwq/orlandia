# -*- coding: utf-8 -*-
"""v97.7 数据完整性验证：道具总数、模板字段合法性、关键道具抽查"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db, Main, FakeEvent, run, clean_db

async def cmd(m, handler_name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    handler = getattr(m, handler_name)
    results = await run(handler, ev)
    return results[-1] if results else ""

async def main():
    clean_db()
    m = Main(None)
    ok = fail = 0
    def check(name, cond, detail=""):
        nonlocal ok, fail
        if cond: ok += 1; print(f"  ✅ {name}")
        else: fail += 1; print(f"  ❌ {name} {detail}")

    # 包内真源（原 `game.core.item_templates` 薄壳 → `content/item_templates.py`）
    from content import item_templates as IT

    # ---- 1. 数量 ----
    # CONSUMABLES 已合并进 ITEMS（data/items.py 底部 ITEMS.update(CONSUMABLES)）
    items_all = C.ITEMS
    consum = {k: v for k, v in items_all.items() if k.startswith("i_")}
    n_cons = len(consum)
    check("消耗品总数 ≥ 195 (v105 清扫清理死数据后)", n_cons >= 195, f"实际 {n_cons}")
    print(f"    消耗品总数: {n_cons}")

    # ---- 2. 模板分派完整性：所有道具都能 infer 出模板 ----
    bad = []
    for k, v in consum.items():
        tpl = IT.infer_template(v)
        if tpl not in IT.TEMPLATES:
            bad.append((k, tpl))
    check("所有消耗品可分派到已注册模板", not bad, str(bad[:5]))

    # ---- 3. 关键新道具字段抽查 ----
    check("神愈药水 heal=1.0", consum["i_treat_divine"]["heal"] == 1.0, str(consum.get("i_treat_divine")))
    check("龙蛋煎饼 复合字段", consum["i_dragon_egg_pancake"].get("heal") == 0.4 and consum["i_dragon_egg_pancake"].get("stamina") == 45, "")
    check("战圣药剂 buff_atk_big_def", consum["i_warsaint_pot"]["effect"] == "buff_atk_big_def", "")
    check("国王赦书 clear_red", consum["i_king_pardon"]["effect"] == "clear_red", "")
    check("龙晶箱 open_chest", consum["i_chest_dragon"]["effect"] == "open_chest", "")
    check("龙裔蛋 pet_key", C.make_pet_egg("pet_drake")["pet_key"] == "pet_drake", "")
    check("雪狼缰绳 mount_key", C.make_mount_rein("mount_wolf")["mount_key"] == "mount_wolf", "")
    check("余烬行者徽章 收藏品", consum["i_mem_emberwalker"]["type"] == "收藏品", "")

    # ---- 4. 新道具实际使用（战斗外）----
    await cmd(m, "register", "g1", "w1", "注册 战士 旅人 男")
    db.update_player("g1", "w1", cur_map="oak_plain", level=5, gold=999999)
    p = db.get_player("g1", "w1")
    db.update_player("g1", "w1", hp=int(p["max_hp"] * 0.5), mp=int(p["max_mp"] * 0.5))
    p = db.get_player("g1", "w1")
    hp0, mp0 = p["hp"], p["mp"]

    # 神愈药水回满
    db.add_item("g1", "w1", "t1", {"name": "神愈药水", "type": "消耗品", "stackable": True,
                "heal": 1.0, "price": 300})
    out = await cmd(m, "use", "g1", "w1", "使用 神愈药水")
    p = db.get_player("g1", "w1")
    check("神愈药水回满 HP", p["hp"] == p["max_hp"], f"hp={p['hp']}/{p['max_hp']} out={out[:80]}")
    check("神愈药水已消耗", not any(it["key"] == "t1" for it in db.get_inventory("g1", "w1")), "")

    # 草药茶 复合恢复（先扣体力，否则体力满时 _add_stamina 返回 0 无体力文案）
    import time as _t
    db.update_player("g1", "w1", hp=int(p["max_hp"] * 0.5), mp=int(p["max_mp"] * 0.5),
                     stamina=0, stamina_ts=int(_t.time()))
    p = db.get_player("g1", "w1")
    db.add_item("g1", "w1", "t2", {"name": "草药茶", "type": "消耗品", "stackable": True,
                "heal": 0.1, "mana": 0.1, "stamina": 15, "price": 8})
    out = await cmd(m, "use", "g1", "w1", "使用 草药茶")
    p = db.get_player("g1", "w1")
    check("草药茶回血", p["hp"] > hp0, f"hp={p['hp']}")
    check("草药茶回体力", "体力" in out, out[:120])

    # 幸运金币（lucky 模板）
    db.add_item("g1", "w1", "t3", {"name": "幸运金币", "type": "消耗品", "stackable": True,
                "effect": "lucky", "price": 300})
    out = await cmd(m, "use", "g1", "w1", "使用 幸运金币")
    check("幸运金币生效", "幸运" in out and "50%" in out, out[:120])

    # 白银箱（open_chest 模板）
    db.add_item("g1", "w1", "t4", {"name": "白银箱", "type": "消耗品", "stackable": True,
                "effect": "open_chest", "price": 350})
    out = await cmd(m, "use", "g1", "w1", "使用 白银箱")
    check("白银箱开箱", "你打开了" in out and "金币" in out, out[:120])

    # 龙裔蛋（pet_egg 模板）
    db.add_item("g1", "w1", "t5", {"name": "龙裔蛋", "type": "宠物蛋", "stackable": True,
                "pet_key": "pet_drake", "price": 500})
    out = await cmd(m, "use", "g1", "w1", "使用 龙裔蛋")
    check("龙裔蛋孵化", "破壳而出" in out and "龙裔幼崽" in out, out[:150])

    # 雪狼缰绳（mount 模板）
    db.add_item("g1", "w1", "t6", {"name": "雪狼缰绳", "type": "坐骑", "stackable": True,
                "mount_key": "mount_wolf", "price": 3000})
    out = await cmd(m, "use", "g1", "w1", "使用 雪狼缰绳")
    check("雪狼缰绳解锁坐骑", "雪狼" in out and "蹭了蹭你" in out, out[:150])

    # 龙鳞残片（none 模板 → 不能使用）
    db.add_item("g1", "w1", "t7", {"name": "龙鳞残片", "type": "收藏品", "stackable": True,
                "price": 300})
    out = await cmd(m, "use", "g1", "w1", "使用 龙鳞残片")
    check("收藏品不能使用", "不能使用" in out, out[:120])
    check("收藏品未消耗", any(it["key"] == "t7" for it in db.get_inventory("g1", "w1")), "")

    # 战斗外 buff 药水提示（战圣药剂）
    db.add_item("g1", "w1", "t8", {"name": "战圣药剂", "type": "消耗品", "stackable": True,
                "effect": "buff_atk_def", "price": 350})
    out = await cmd(m, "use", "g1", "w1", "使用 战圣药剂")
    check("战圣药剂战斗外提示", "战斗" in out, out[:120])

    print(f"\n结果: {ok} 通过, {fail} 失败")
    return fail == 0

if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)
