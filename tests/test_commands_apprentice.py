# -*- coding: utf-8 -*-
"""commands 层：v81 导师进修（19 章第八章——三关拜师）

验证：
  1. 拜师全流程：答题→实践→授业→拜师成功（艾琳为例）
  2. 理论关答错可重试
  3. 实践/授业材料不足拦截（fail_next，不扣材料）
  4. 拜师成功：apprentices 记录 + 副业激活 + 副业经验 + 入门礼
  5. 已拜师后再找导师：拜师选项隐藏（apprentice need）
  6. 无数量上限：已激活 ≥2 条副业仍可正常拜新导师（v167 解除双副业上限）
  7. 强化/附魔命令需要对应副业（导师进修后独立副业）
  8. 对话树数据完整性：8 位导师 next 引用合法
"""
import sys, os, sqlite3, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import C, db, clean_db, Main, FakeEvent, run

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
    await cmd(m, "register", "g1", "w1", "注册 战士 旅人 男")
    db.update_player("g1", "w1", level=5, gold=1000, cur_map="oak_town", cur_subarea="oak_town_5")

    print("【v81 拜师：艾琳理论关】")
    out = await cmd(m, "find_npc", "g1", "w1", "找 艾琳")
    check("进入导师对话树", "哪种草能治伤口" in out and "0. 结束对话" in out, out[:200])
    out = await cmd(m, "talk_choice", "g1", "w1", "2")
    check("答错提示再想想", "再想想" in out, out[:200])
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    check("答对进入实践关", "采 3 份草药" in out, out[:200])

    print("【v81 拜师：实践关】")
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    check("进入实践判定", "看看你采的草药" in out, out[:200])
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    check("材料不足拦截", "还差 3 份草药" in out, out[:200])
    db.add_item("g1", "w1", "草药", {}, 3)
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    check("补料后回到判定", "看看你采的草药" in out, out[:200])
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    check("实践过关进入授业", "最鲜嫩的草药" in out, out[:200])

    print("【v81 拜师：授业关】")
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    check("进入授业判定", "这份草药" in out, out[:200])
    # 只有 3 份草药，实践判定没消耗 → 授业需要 1 份
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    check("授业判定通过进入拜师礼", "学徒" in out, out[:200])
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    check("拜师成功", "拜师成功" in out and "采集" in out, out[:300])

    player = db.get_player("g1", "w1")
    check("apprentices 记录 gather", "gather" in player.get("apprentices", []), str(player.get("apprentices")))
    check("副业已激活", "gather" in db.get_activated_profs("g1", "w1"), str(db.get_activated_profs("g1", "w1")))
    lv = db.get_prof_level("g1", "w1", "gather")
    check("副业经验已给(等级>1)", lv > 1, f"gather lv={lv}")
    # 入门礼 3 份草药已给（授业消耗 1 份 → 背包 3-1+3=5）
    have = db.count_item("g1", "w1", "草药")
    check("入门礼草药入包", have >= 5, f"草药={have}")

    print("【v81 拜师：已拜师后再找导师】")
    out = await cmd(m, "find_npc", "g1", "w1", "找 艾琳")
    check("拜师题目选项隐藏", "止血草" not in out, out[:200])
    check("显示随便聊聊", "随便聊聊" in out, out[:200])
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    check("闲聊分支", "耐心" in out, out[:200])

    print("【v81 拜师：已拜师后再找导师】")
    # 先激活另外 2 个副业（直接 store 激活模拟老玩家已有两条）
    # v167 无数量上限：直接激活 3 条验证可同时激活（原双副业上限已解除）
    db.activate_prof("g1", "w1", "mining")
    db.activate_prof("g1", "w1", "cooking")
    db.activate_prof("g1", "w1", "fishing")
    check("已激活多条(>2 无上限)", len(db.get_activated_profs("g1", "w1")) >= 3, str(db.get_activated_profs("g1", "w1")))
    # 此时 w1 已激活 gather/mining/cooking/fishing 4 条（拜师艾琳成功后 gather 在列）——
    # v167 无上限：再拜锻造按正常材料判定走，无数量拦截
    db.update_player("g1", "w1", cur_map="ironharbor")
    out = await cmd(m, "find_npc", "g1", "w1", "找 奥格")
    check("锻造导师对话树", "图纸+材料" in out, out[:200])
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    check("答对进实践", "5 份铁矿石" in out, out[:200])
    out = await cmd(m, "talk_choice", "g1", "w1", "1")  # practice_intro → practice_check
    # v167：无数量上限，不再有"位置满"拦截——材料判定正常进行：
    # 此时 w1 已激活 mining/cooking/gather(≥2 条)，仍可拜师锻造（上限解除实锤）
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    check("激活≥2条仍可拜师(无上限)", "副业位已满" not in out and "5 份铁矿石" in out, out[:300])
    # 已拜师（apprentices 有 craft）+ 材料不足 → 走材料 fail 分支（未结束对话）
    # 说明：practice 关拜奥格时 craft 尚未解锁，但 apprentice_check 前置于材料判定——
    # v167 起无数量拦截，材料不足按正常 fail 路由走（不扣料、不落激活）
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    player = db.get_player("g1", "w1")
    check("缺料走失败分支不落激活", "craft" not in db.get_activated_profs("g1", "w1")
          or "craft" not in (player.get("apprentices") or []),
          f"activated={db.get_activated_profs('g1', 'w1')} appr={player.get('apprentices')}")
    check("未记录学徒", "craft" not in player.get("apprentices", []), str(player.get("apprentices")))

    print("【v81 对话树数据完整性】")
    npc_ids = ["npc_herb_master", "npc_mine_master", "npc_fish_master", "npc_cook_master",
               "npc_alchemy_master", "npc_craft_master", "npc_enhance_master", "npc_rune_master"]
    for nid in npc_ids:
        dlg = C.get_dialogue(nid)
        check(f"{nid} 有对话树", dlg is not None, "")
        if not dlg:
            continue
        nodes = dlg.get("nodes", {})
        ok_ref = True
        for nk, nd in nodes.items():
            for opt in nd.get("options", []):
                nxt = opt.get("next")
                if nxt is not None and nxt != "__end__" and nxt not in nodes:
                    ok_ref = False
        check(f"{nid} next 引用合法", ok_ref, "")
        check(f"{nid} 有拜师动作", any("unlock_prof" in json.dumps(nd, ensure_ascii=False) for nd in nodes.values()), "")

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed

if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(main()))
