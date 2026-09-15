# -*- coding: utf-8 -*-
"""v113 隐藏线血脉传承测试（test_v113_bloodline.py）

覆盖：
1. 数据完整性：6 试炼任务 require_race 全配；6 导师对话树存在且 start 合法
2. 对话条件：race_is / hidden_unlocked / not_hidden_current 注册且筛选正确
3. 血脉拒绝：非对应种族找导师对话 → 导师拒绝（无传承选项）
4. 血脉认可：对应种族找导师 → 显示试炼/传承选项
5. 『接取』指令种族门槛：非对应种族接试炼被拒
6. 对话传承：解锁后导师对话『接受传承』→ 转职成功（async hidden_evolve）
7. 传承后：导师对话不再显示传承选项
"""
import sys, os, asyncio
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
        print(f"  ❌ {name} {str(detail)[:200]}")


async def cmd(m, handler_name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    handler = getattr(m, handler_name)
    results = await run(handler, ev)
    return "".join(str(x) for x in results)


# 六线映射：导师 / 种族 / 隐藏线 / 地图（导师新位置）/ 导师所在子区域 / 血脉台词关键词
# v151：6 隐藏职业（龙裔/时咒/星语/暗影/暮影/苦修）已全部删除——血脉传承链路随职业删除，
# 本测试改为验证：导师 NPC 与数据残留清理 + 基础职业导师转职链路仍正常
LINES = [
    ("npc_dragon_veteran", "dragonborn", "cls_dragon_oath", "dusk_ridge_road", "dusk_ridge_road_1", "龙骨山脉"),
    ("npc_chrono_warden", "human", "cls_chronomancer", "white_deer", "white_deer_4", "人类的求知欲"),
    ("npc_astrologer", "elf", "cls_wild_hunter", "starlake", "starlake_1", "银月精灵"),
    ("npc_grave_watcher", "orc", "cls_hymn", "border_castle", "border_castle_1", "战血"),
    ("npc_shadow_master", "halfling", "cls_shadow_blade", "jade_port", "jade_port_1", "灵巧的血脉"),
    ("npc_wusheng_monk", "dwarf", "cls_wu_sheng", "anvil_fort", "anvil_fort_gate", "筋骨如铁"),
]


async def main():
    clean_db()
    m = Main(None)

    print("【1. 数据完整性（v151：隐藏职业已删）】")
    for sq in C.SIDE_QUESTS:
        if sq.get("unlock_class"):
            check(f"{sq['id']} require_race 配置", bool(sq.get("require_race")), str(sq))
    # v151：CLASSES 无隐藏职业、SIDE_QUESTS 无 unlock_class 试炼（血脉传承链已删）
    hidden = {k: v for k, v in C.CLASSES.items() if v.get("hidden")}
    check("CLASSES 无隐藏职业（v151 已删）", len(hidden) == 0, str(list(hidden)))
    unlock_qs = [sq for sq in C.SIDE_QUESTS if sq.get("unlock_class")]
    check("无 unlock_class 试炼任务（v151 已删）", len(unlock_qs) == 0, str(len(unlock_qs)))
    # 基础职业导师 NPC 仍驻留且对话树可用
    for nid in ("npc_warrior_tutor", "npc_mage_tutor", "npc_priest_tutor"):
        dlg = C.DIALOGUES.get(nid)
        npc = C.NPCS.get(nid, {})
        check(f"{nid} 对话树存在", bool(dlg and dlg.get("start") in (dlg.get("nodes") or {})),
              str(dlg and dlg.get("start")))
        check(f"{nid} 导师驻地图存在", bool(npc.get("map") in C.MAP_BY_ID), str(npc.get("map")))

    print("【2. 基础职业导师转职闭环】")
    # 30 级战士 → 战士导师（白鹿城·白鹿广场）转攻线 T1
    await cmd(m, "register", "g1", "w1", "注册 战士 人类战 男")
    db.update_player("g1", "w1", level=30, cur_map="white_deer", cur_subarea="white_deer_1")
    await cmd(m, "talk_choice", "g1", "w1", "对话 老兵·格里姆")
    await cmd(m, "talk_choice", "g1", "w1", "3")
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    p = db.get_player("g1", "w1")
    check("30 级战士转职 T1 成功", p["class_tier"] == 1 and p["evolve_path"] == 1,
          str((p["class_tier"], p["evolve_path"])))
    check("转职文案显示狂战士", "狂战士" in out, out[:150])

    print("【3. 转职重置回根基】")
    db.update_player("g1", "w1", gold=5000)
    gold0 = db.get_player("g1", "w1")["gold"]
    out = await cmd(m, "evolve_reset", "g1", "w1", "转职重置")
    p = db.get_player("g1", "w1")
    check("重置回战士根基", p["class_name"] == "cls_zhan_shi" and p["class_tier"] == 0,
          str((p["class_name"], p["class_tier"])))
    check("重置扣费", p["gold"] < gold0, str(p["gold"]))

    print("【4. 等级门槛（导师对话层拦截）】")
    await cmd(m, "register", "g1", "w2", "注册 法师 人类法2 男")
    db.update_player("g1", "w2", level=40, cur_map="white_deer", cur_subarea="white_deer_1")
    await cmd(m, "talk_choice", "g1", "w2", "对话 大法师·艾德琳")
    out = await cmd(m, "talk_choice", "g1", "w2", "3")
    check("40 级法师无 T2 转职入口（Lv.60 门槛）", "继续转职" not in out, out[:150])

    print()
    print(f"===== v113 血脉传承测试: {passed} passed, {failed} failed =====")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
