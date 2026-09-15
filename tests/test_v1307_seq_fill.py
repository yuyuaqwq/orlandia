# -*- coding: utf-8 -*-
"""v130.7 F08 意见#30(补) 序号兼容 6 处 固化测试（学习/烹饪/合成/代工/附魔）

覆盖（isdigit 早分支 + 与面板同源列表取第 N 项）：
  ① 『学习 <序号>』= 『背包 图纸』面板第 N 张图纸；越界报错；名称直填不回归
  ② 『烹饪 <序号>』= 『烹饪列表』面板第 N 道料理；名称直填不回归
  ③ 『合成 <序号>』= 『炼金』面板第 N 个配方；名称直填不回归
  ④ 『代工 <序号>』= 『锻造』面板第 N 个可锻造配方；越界报错；名称直填不回归
  ⑤ 『附魔 <序号> <属性>』= 『背包』面板全局序号第 N 件（须为装备）；
      非装备报错；越界报错；名称直填不回归
  （『卸下』部位为固定枚举且无带序号装备面板 → 本次跳过，见任务卡 F08）

运行：python tests/test_v1307_seq_fill.py（exit=0 全绿）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _engine_harness import C, db, FakeEvent, run, clean_db, make_player  # noqa: E402
from _engine_harness import Main  # noqa: E402

passed = failed = 0
G = "f08_g"
Q_L = "f08_q_learn"
Q_C = "f08_q_cook"
Q_A = "f08_q_alc"
Q_F = "f08_q_forge"
Q_E = "f08_q_ench"


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"✅ {name}")
    else:
        failed += 1
        print(f"❌ {name} {str(detail)[:220]}")


async def cmd(m, handler_name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    out = []
    async for r in getattr(m, handler_name)(ev):
        out.append(r)
    return "\n".join(str(x) for x in out)


def prof_setup(gid, qid, key):
    """拜师模拟 + 副业激活（对齐既有测试写法）"""
    db.update_player(gid, qid, apprentices=[key])
    db.activate_prof(gid, qid, key)


def inv_names(gid, qid):
    return [(it["key"], it["data"].get("name", ""), it["count"]) for it in db.get_inventory(gid, qid)]


async def main():
    m = Main(None)

    # ================= ① 学习 =================
    print("【① 学习：『学习 <序号>』= 『背包 图纸』面板第 N 张】")
    clean_db()
    make_player(G, Q_L, "学图", "战士", level=5)
    db.add_item(G, Q_L, "mat_f08_tie_kuang", {"name": "铁矿石", "type": "矿石"}, 1)      # 背包第 1 位：非图纸
    db.add_item(G, Q_L, "bp_f08_a", {"name": "食谱图纸·香草烤兽肉", "type": "图纸"}, 1)
    db.add_item(G, Q_L, "bp_f08_b", {"name": "奥拉圣印图纸", "type": "图纸"}, 1)
    r = await cmd(m, "learn", G, Q_L, "学习 99")
    check("① 越界报错『没有第 99 张图纸』", "没有第 99 张图纸" in r, r[:120])
    r = await cmd(m, "learn", G, Q_L, "学习 2")
    check("① 『学习 2』= 第 2 张图纸（跳过第 1 位非图纸项）", "研读了【奥拉圣印图纸】" in r, r[:120])
    p = db.get_player(G, Q_L)
    learned = p.get("learned_blueprints") or []
    check("① learned_blueprints 只含第 2 张", learned == ["奥拉圣印图纸"], str(learned))
    inv = inv_names(G, Q_L)
    check("① 第 2 张图纸已消耗、第 1 张还在",
          all(k != "bp_f08_b" for k, _, _ in inv) and any(k == "bp_f08_a" for k, _, _ in inv), str(inv))
    r = await cmd(m, "learn", G, Q_L, "学习 食谱图纸·香草烤兽肉")
    check("① 名称直填不回归（第 1 张）", "研读了【食谱图纸·香草烤兽肉】" in r, r[:120])

    # ================= ② 烹饪 =================
    print("【② 烹饪：『烹饪 <序号>』= 『烹饪列表』面板第 N 道】")
    clean_db()
    make_player(G, Q_C, "厨神", "战士", level=5)
    prof_setup(G, Q_C, "cooking")
    db.add_item(G, Q_C, "mat_shi_lai_mu_nian_ye", {"name": C.display("materials", "mat_shi_lai_mu_nian_ye"), "type": "材料"}, 3)
    r = await cmd(m, "cooking", G, Q_C, "烹饪 1")
    check("② 『烹饪 1』= 面板第 1 道『史莱姆果冻』", "烹饪成功！【史莱姆果冻】" in r, r[:160])
    db.add_item(G, Q_C, "mat_she_pi", {"name": C.display("materials", "mat_she_pi"), "type": "材料"}, 3)
    r = await cmd(m, "cooking", G, Q_C, "烹饪 蛇羹")
    check("② 名称直填不回归", "烹饪成功！【蛇羹】" in r, r[:160])

    # ================= ③ 合成（炼金） =================
    print("【③ 合成：『合成 <序号>』= 『炼金』面板第 N 个配方】")
    clean_db()
    make_player(G, Q_A, "炼药师", "战士", level=5)
    prof_setup(G, Q_A, "alchemy")
    db.add_item(G, Q_A, "mat_lang_pi", {"name": C.display("materials", "mat_lang_pi"), "type": "材料"}, 1)
    r = await cmd(m, "alchemy_craft", G, Q_A, "合成 1")
    check("③ 『合成 1』= 面板第 1 个『治疗药水(小)』", "炼金成功】合成了【治疗药水(小)】" in r, r[:160])
    db.add_item(G, Q_A, "mat_shi_xi_lin", {"name": C.display("materials", "mat_shi_xi_lin"), "type": "材料"}, 1)
    r = await cmd(m, "alchemy_craft", G, Q_A, "合成 魔法药水(小)")
    check("③ 名称直填不回归", "炼金成功】合成了【魔法药水(小)】" in r, r[:160])

    # ================= ④ 代工 =================
    print("【④ 代工：『代工 <序号>』= 『锻造』面板第 N 个可锻造配方】")
    clean_db()
    make_player(G, Q_F, "铁匠客户", "战士", level=10)
    db.update_player(G, Q_F, cur_map="oak_town", cur_subarea="oak_town_3")  # 老铁铺（craft funcs）
    db.add_item(G, Q_F, "mat_shi_lai_mu_nian_ye", {"name": C.display("materials", "mat_shi_lai_mu_nian_ye"), "type": "材料"}, 20)
    db.add_item(G, Q_F, "mat_qing_xiang_mu", {"name": C.display("materials", "mat_qing_xiang_mu"), "type": "材料"}, 5)  # v167：猎弓用青橡木
    db.add_item(G, Q_F, "mat_cu_tie", {"name": C.display("materials", "mat_cu_tie"), "type": "材料"}, 5)  # v167：铁剑用粗铁
    r = await cmd(m, "craft_commission", G, Q_F, "代工 99")
    check("④ 越界报错『没有第 99 个可代工配方』", "没有第 99 个可代工配方" in r, r[:120])
    r = await cmd(m, "craft_commission", G, Q_F, "代工 1")
    check("④ 『代工 1』= 锻造面板第 1 个『猎弓』（lv2 最低档）",
          "代工完成！" in r and "【猎弓】" in r, r[:160])
    r = await cmd(m, "craft_commission", G, Q_F, "代工 铁剑")
    check("④ 名称直填不回归", "代工完成！" in r and "【铁剑】" in r, r[:160])

    # ================= ⑤ 附魔 =================
    print("【⑤ 附魔：『附魔 <序号> <属性>』= 『背包』面板全局序号第 N 件（须为装备）】")
    clean_db()
    make_player(G, Q_E, "附魔师", "战士", level=10)
    db.update_player(G, Q_E, gold=1000, cur_map="oak_town", cur_subarea="oak_town_3")
    prof_setup(G, Q_E, "enchant")
    db.add_prof_exp(G, Q_E, "enchant", 20)  # Lv.1→2（need(1)=20），附魔门槛 Lv.2
    db.add_item(G, Q_E, "eq_f08_blade", {"name": "烈焰之刃", "type": "装备", "slot": "weapon", "quality": "blue", "lv": 5}, 1)
    db.add_item(G, Q_E, "mat_f08_liao_ya", {"name": "魔狼獠牙", "type": "材料"}, 1)
    r = await cmd(m, "enchant", G, Q_E, "附魔 99 攻击")
    check("⑤ 越界报错『没有第 99 件物品』", "没有第 99 件物品" in r, r[:120])
    r = await cmd(m, "enchant", G, Q_E, "附魔 2 攻击")
    check("⑤ 第 2 件非装备 → 明确报错", "不是装备，不能附魔" in r, r[:120])
    r = await cmd(m, "enchant", G, Q_E, "附魔 1 锋锐")
    check("⑤ 序号已解析为装备名（走到属性名校验）", "没有『锋锐』这个附魔属性" in r, r[:120])
    r = await cmd(m, "enchant", G, Q_E, "附魔 1 攻击")
    check("⑤ 『附魔 1 攻击』= 对背包第 1 件可附魔装备附魔", "附魔成功！【烈焰之刃】获得 攻击" in r, r[:160])
    # 名称直填回归走独立场景（蓝装仅 1 槽，序号用例已占满）
    clean_db()
    make_player(G, Q_E, "附魔师", "战士", level=10)
    db.update_player(G, Q_E, gold=1000, cur_map="oak_town", cur_subarea="oak_town_3")
    prof_setup(G, Q_E, "enchant")
    db.add_prof_exp(G, Q_E, "enchant", 20)
    db.add_item(G, Q_E, "eq_f08_blade", {"name": "烈焰之刃", "type": "装备", "slot": "weapon", "quality": "blue", "lv": 5}, 1)
    db.add_item(G, Q_E, "mat_f08_liao_ya", {"name": "魔狼獠牙", "type": "材料"}, 1)
    r = await cmd(m, "enchant", G, Q_E, "附魔 烈焰之刃 攻击")
    check("⑤ 名称直填不回归", "附魔成功！【烈焰之刃】获得 攻击" in r, r[:160])

    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)


import asyncio

asyncio.run(main())