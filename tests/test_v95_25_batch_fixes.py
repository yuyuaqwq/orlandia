# -*- coding: utf-8 -*-
"""v95.25 攒批修复验证：子 agent 反馈 13 项

覆盖：
  1. #127 购买数量语法『购买 名称 数量』+ 全角括号容错
  2. #128 满血用药不消耗
  3. #116 铁港城铁锚酒馆可住宿
  4. #134 住宿提示示例动态化（含当前城镇旅店）
  5. #138 主线接取等级建议（suggest_lv）
  6. #140 死亡惩罚说明（10%）
  7. #145 技能报错显示已学技能（learned_skills）
  8. #150 采药女任务文案不再误导
  9. #135 找 NPC 跨图前缀明确
  10. #133 非出口子区域『前往』列表不列跨图目的地
  11. #47b 主线交付提示不写死『交付任务』
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db, clean_db, Main, FakeEvent, run

passed = failed = 0
def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {str(detail).encode('utf-8', 'replace').decode('utf-8', 'replace')[:300]}")

async def cmd(m, handler_name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    handler = getattr(m, handler_name)
    results = await run(handler, ev)
    return results[-1] if results else ""

async def main():
    clean_db()
    m = Main(None)

    print("【1. #127 购买数量 + 全角括号】")
    await cmd(m, "register", "g1", "w1", "注册 战士 买家 男")
    db.update_player("g1", "w1", gold=50000, cur_map="white_deer", cur_subarea="white_deer_6")
    out = await cmd(m, "buy", "g1", "w1", "购买 治疗药水(中) 6")
    check("购买 6 瓶成功", "×6" in out, out[:200])
    inv = db.get_inventory("g1", "w1")
    pot = [i for i in inv if "治疗药水(中)" in i["data"]["name"]]
    check("背包 6 瓶", sum(i["count"] for i in pot) == 6, str([(i["data"]["name"], i["count"]) for i in inv]))
    p = db.get_player("g1", "w1")
    check("扣 6 倍钱", p["gold"] == 50000 - 6 * 30, f"gold={p['gold']}")
    # 全角括号容错（v152 商店重排：治疗药水(小)只在橡木镇，white_deer_6 卖中级药）
    db.update_player("g1", "w1", cur_map="oak_town", cur_subarea="oak_town_5")
    out = await cmd(m, "buy", "g1", "w1", "购买 治疗药水（小） 2")
    check("全角括号可买", "×2" in out, out[:200])
    db.update_player("g1", "w1", cur_map="white_deer", cur_subarea="white_deer_6")
    # 序号 + 数量（消耗品）
    out = await cmd(m, "buy", "g1", "w1", "购买 1 3")
    check("序号+数量可买", "×3" in out, out[:200])

    print("【2. #128 满血用药不消耗】")
    await cmd(m, "register", "g1", "w2", "注册 战士 血牛 男")
    db.update_player("g1", "w2", hp=1000, max_hp=1000)
    db.add_item("g1", "w2", "pot_mid", {"name": "治疗药水(中)", "type": "消耗品", "stackable": True, "heal": 0.5, "price": 60})
    out = await cmd(m, "use", "g1", "w2", "使用 治疗药水(中)")
    check("满血提示用不着", "用不着" in out, out[:200])
    inv = db.get_inventory("g1", "w2")
    check("物品不消耗", sum(i["count"] for i in inv) == 1, str(inv))

    print("【3. #116 铁锚酒馆住宿】")
    await cmd(m, "register", "g1", "w3", "注册 战士 住客 男")
    db.update_player("g1", "w3", gold=500, hp=10, mp=10, cur_map="ironharbor", cur_subarea="ironharbor_5")
    out = await cmd(m, "rest", "g1", "w3", "住宿")
    check("铁锚酒馆可住宿", "美美地睡了一觉" in out, out[:200])
    p = db.get_player("g1", "w3")
    check("血蓝回满", p["hp"] == p["max_hp"] and p["mp"] == p["max_mp"], f"hp={p['hp']}/{p['max_hp']}")

    print("【4. #134 住宿示例动态化】")
    await cmd(m, "register", "g1", "w4", "注册 战士 路人 男")
    db.update_player("g1", "w4", gold=500, cur_map="ironharbor", cur_subarea="ironharbor_1")
    out = await cmd(m, "rest", "g1", "w4", "住宿")
    check("提示当前城镇旅店", "铁锚酒馆" in out, out[:300])
    check("不再写死橡木镇", "橡木镇旅店" not in out, out[:300])

    print("【5. #138 主线等级建议】")
    await cmd(m, "register", "g1", "w5", "注册 战士 勇者 男")
    # 直接构造 q3_3 pending 状态 + 人在铁港城（城主发布）
    quests = db.get_quests("g1", "w5")
    quests["main_quest"] = "q3_3"
    quests["main_status"] = "pending"
    db.save_quests("g1", "w5", quests)
    db.update_player("g1", "w5", level=12, cur_map="ironharbor", cur_subarea="ironharbor_1")
    out = await cmd(m, "quest_accept", "g1", "w5", "接取 海盗王·独眼杰克")
    check("接取提示建议等级", "建议等级 Lv.25" in out, out[:400])
    p = db.get_player("g1", "w5")
    # v110 审计修复：原 `is not None and True` 恒真（左侧判定被 and True 架空）
    check("仍然接取成功", p.get("class_tier") is not None, str(p.get("class_tier")))
    qs = db.get_quests("g1", "w5")
    check("主线已激活", qs.get("main_status") == "active", str(qs.get("main_status")))

    print("【6. #140 死亡惩罚说明】")
    # 构造一场必败战斗（100 级怪）
    await cmd(m, "register", "g1", "w6", "注册 战士 送头 男")
    db.update_player("g1", "w6", gold=1000, level=1, cur_map="oak_plain", cur_subarea="oak_plain_1")
    # N5b4-6：saintess_engine state（命令层 attack 只认 sides）
    from content import bridge as _BR
    from saintess_engine import Battle as _B2
    pl6 = db.get_player("g1", "w6")
    _BR.prepare_player_for_battle(pl6, {}, db)
    _mon6 = {"name": "测试凶兽", "hp": 99999, "max_hp": 99999, "atk": 9999, "def": 9999,
             "spd": 999, "matk": 1, "mdef": 1, "crit": 0.0, "uid": "e_death", "level": 100,
             "lv": 100, "rank": 1, "reach": 1, "skills": [], "is_boss": False, "is_elite": False}
    _s6 = _BR.build_sides(player=pl6, enemies=[_mon6])
    for _a in _s6.get("player", []):
        _a["bonus"] = {"panel": {}, "cap": {}, "cost": {}}
    db.save_battle("g1", "w6", _B2("monster", sides=_s6, title_bonus={}).to_state())
    out = await cmd(m, "attack", "g1", "w6", "攻击")
    check("死亡提示含 10% 规则", "10% 金币" in out, out[:300])

    print("【7. #145 技能报错显示已学技能】")
    await cmd(m, "register", "g1", "w7", "注册 战士 技能哥 男")
    db.update_player("g1", "w7", learned_skills=["挥砍"])
    pl7 = db.get_player("g1", "w7")
    _BR.prepare_player_for_battle(pl7, {}, db)
    _mon7 = {"name": "测试史莱姆", "hp": 50, "max_hp": 50, "atk": 5, "def": 2, "spd": 3,
             "matk": 1, "mdef": 1, "crit": 0.0, "uid": "e_slime", "level": 1, "lv": 1,
             "rank": 1, "reach": 1, "skills": [], "is_boss": False, "is_elite": False}
    _s7 = _BR.build_sides(player=pl7, enemies=[_mon7])
    for _a in _s7.get("player", []):
        _a["bonus"] = {"panel": {}, "cap": {}, "cost": {}}
    db.save_battle("g1", "w7", _B2("monster", sides=_s7, title_bonus={}).to_state())
    out = await cmd(m, "skill", "g1", "w7", "技能 火球")
    check("报错含已学技能", "挥砍" in out, out[:300])
    check("不再显示遗留列", "你当前的技能：无" not in out, out[:300])

    print("【8. #150 采药女文案】")
    sq = next(q for q in C.SIDE_QUESTS if q["id"] == "side_herb_girl" or q["name"] == "采药女的心愿")
    check("不再误导低阶草丛", "低阶草丛更容易出" not in sq["desc"], sq["desc"][:200])
    check("给了稳定渠道", "草药柜" in sq["desc"], sq["desc"][:200])

    print("【9. #135 找 NPC 跨图前缀】")
    await cmd(m, "register", "g1", "w8", "注册 战士 寻人 男")
    db.update_player("g1", "w8", cur_map="oak_town", cur_subarea="oak_town_1")
    out = await cmd(m, "find_npc", "g1", "w8", "找 老兵·格里姆")
    check("跨图提示明确", "你现在不在这里" in out, out[:300])
    # v113.5 O90：同图但不同子区域（镇长在 oak_town_2，玩家在 oak_town_1）——
    # 不再说"就在你所在的"（把目标位置说成玩家所在），统一"（你现在不在这里）"样式
    out = await cmd(m, "find_npc", "g1", "w8", "找 镇长")
    check("同图不同子区域提示不在", "你现在不在这里" in out, out[:300])
    # 同子区域（巨型野猪精英在 oak_plain_3）：保留"就在你所在的"
    db.update_player("g1", "w8", cur_map="oak_plain", cur_subarea="oak_plain_3")
    out = await cmd(m, "find_npc", "g1", "w8", "找 巨型野猪")
    check("同子区域提示就在", "就在你所在的" in out, out[:300])
    db.update_player("g1", "w8", cur_subarea="oak_plain_1")
    out = await cmd(m, "find_npc", "g1", "w8", "找 巨型野猪")
    check("同图异子区域精英提示不在", "你现在不在这里" in out, out[:300])

    print("【10. #133 非出口列表不列跨图】")
    await cmd(m, "register", "g1", "w9", "注册 战士 逛街 男")
    db.update_player("g1", "w9", cur_map="ironharbor", cur_subarea="ironharbor_2")
    out = await cmd(m, "move", "g1", "w9", "前往 港口广场")
    check("非出口提示出城需先到城门", "出城需先到" in out, out[:300])
    check("不列跨图目的地", "橡木镇" not in out, out[:300])

    print("【11. #47b 主线交付提示】")
    await cmd(m, "register", "g1", "w10", "注册 战士 交付 男")
    quests = db.get_quests("g1", "w10")
    quests["main_quest"] = "q2_2"
    quests["main_status"] = "ready"
    db.save_quests("g1", "w10", quests)
    out = await cmd(m, "quest_view", "g1", "w10", "任务")
    check("交付提示不写死指令", "『交付任务』" not in out.split("主线")[1][:200] if "主线" in out else False, out[:400])
    check("提示回去交付", "回去找" in out, out[:400])

    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    import asyncio
    asyncio.new_event_loop().run_until_complete(main())
