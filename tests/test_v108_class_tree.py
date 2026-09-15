# -*- coding: utf-8 -*-
"""v112 职业树·主题线制测试（test_v108_class_tree.py，v112 重写）

覆盖：
 1. 数据完整性：6 隐藏线 src_base；战士守线改名；职业名+分支名无重名；档位全名全部可路由
 2. 修为继承：40 级转 = T1；60 级转 = T2（直接）；90 级转 = T3；技能按等级继承（线级+流派）
 3. 等级门槛拦截：40 级转 T2/T3 被拒
 4. 同职业逐阶升 T1→T2→T3；跳档拦截；已是高阶提示；跨职业直接 T3（修为继承）
 5. 『转职』无参数（隐藏职业）显示下一阶 / 已满
 6. 『转职重置』隐藏职业回渊源根基（付费）
 7. 六线统一 40/60/90 档位 + 流派路由（『转职 收割』→ 暮影线收割流派）

运行：python tests/test_v108_class_tree.py（exit=0 全绿）
"""
import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import C, db, clean_db, Main, run, make_player

passed = failed = 0

def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")

async def cmd(m, handler_name, gid, qid, msg):
    ev = __import__("conftest").FakeEvent(gid, qid, msg)
    handler = getattr(m, handler_name)
    results = await run(handler, ev)
    return "".join(str(x) for x in results)


async def evolve_via_tutor(m, gid, qid, tutor_npc, tier_opt):
    """基础职业导师转职：对话 → 选『我想转职』→ 选路线（玩家须已在导师所在图）"""
    await cmd(m, "talk_choice", gid, qid, f"对话 {tutor_npc}")
    await cmd(m, "talk_choice", gid, qid, "3")  # 『我想转职！』
    return await cmd(m, "talk_choice", gid, qid, str(tier_opt))


async def main():
    clean_db()
    m = Main(None)

    print("[1] 数据完整性")
    hidden = {k: v for k, v in C.CLASSES.items() if v.get("hidden")}
    # v151 隐藏职业已删（龙裔/时咒/星语/暗影/暮影/苦修 6 线）——无隐藏职业
    check("隐藏职业 0 线（v151 已删）", len(hidden) == 0, str(len(hidden)))
    check("基础职业 7 线（v153 新增诗人）", len([k for k in C.CLASSES if not C.CLASSES[k].get("hidden") and k != "cls_novice"]) == 7,
          str([k for k in C.CLASSES]))
    check("全部有 src_base 且为血缘职业",
          all(v.get("src_base") and not C.CLASSES[v["src_base"]].get("hidden") for v in hidden.values()),
          str([(k, v.get("src_base")) for k, v in hidden.items() if not v.get("src_base") or C.CLASSES.get(v["src_base"], {}).get("hidden")]))
    zb = C.CLASSES["cls_zhan_shi"]["evolve_branches"]
    check("战士守线改名 坚盾卫士/坚城统帅",
          zb[2] == ["狂战统领", "坚盾卫士"] and zb[3] == ["战争领主", "坚城统帅"], str(zb))
    # 命名唯一性：职业名 + 全部档位名
    names = []
    for cls_id, cls in C.CLASSES.items():
        names.append(cls["name"])
        for t, brs in (cls.get("evolve_branches") or {}).items():
            names.extend(brs)
    dup_raw = [n for n in set(names) if names.count(n) > 1]
    # v112.3：诗人回归牧师攻线后，已无『职业名 == 自身 T1 档位名』的隐藏线（原独立诗人职业），
    # 合法自匹配集合为空——职业名/档位名全库必须严格无重名
    legal_self = {cls["name"] for cls in C.CLASSES.values() if cls.get("hidden")}
    dup = [n for n in dup_raw if n not in legal_self]
    check("职业名+档位名无重名", not dup, str(dup))
    # v113：隐藏档位全名 = 18 名，全部可路由——v151 已删隐藏职业 → 0 名
    routes = m._hidden_class_routes()
    hidden_names = []
    for cls_id, cls in hidden.items():
        for t, brs in (cls.get("evolve_branches") or {}).items():
            hidden_names.extend(brs)
    check("隐藏档位名全部入路由表(0, v151 已删)",
          all(n in routes for n in hidden_names) and len(hidden_names) == 0,
          f"{len(hidden_names)} 名 / 路由 {len(routes)}")
    # v113：路由带流派索引——v151 无隐藏职业，路由表为空
    check("路由表为空（v151 无隐藏职业）", len(routes) == 0, str(len(routes)))

    print("[2] 修为继承（转职 tier 按等级）")
    # v151 隐藏职业已删：隐藏传承链路全部移除——修为继承验证改为基础职业 30/60/90 导师转职
    # 战士导师·格里姆（白鹿城·白鹿广场）；等级达标即对话转职，'3'=转职入口，'1'=攻线
    make_player("g1", "p1", "修一", "战士", level=30)
    db.update_player("g1", "p1", cur_map="white_deer", cur_subarea="white_deer_1")
    out = await evolve_via_tutor(m, "g1", "p1", "老兵·格里姆", 1)
    p = db.get_player("g1", "p1")
    check("30 级转狂战士 = T1(战士攻线)", p and p["class_name"] == "cls_zhan_shi" and p["class_tier"] == 1,
          str(p and (p["class_name"], p["class_tier"])))
    make_player("g1", "p2", "修二", "战士", level=60)
    db.update_player("g1", "p2", cur_map="white_deer", cur_subarea="white_deer_1")
    await evolve_via_tutor(m, "g1", "p2", "老兵·格里姆", 1)   # T1（30 级达标）
    await cmd(m, "talk_choice", "g1", "p2", "0")              # 结束对话
    out = await evolve_via_tutor(m, "g1", "p2", "老兵·格里姆", 1)  # T2
    p = db.get_player("g1", "p2")
    check("60 级转狂战统领 = T2", p["class_name"] == "cls_zhan_shi" and p["class_tier"] == 2,
          str((p["class_name"], p["class_tier"])))
    check("T2 文案显示狂战统领", "狂战统领" in out, out[:150])
    make_player("g1", "p3", "修三", "战士", level=90)
    db.update_player("g1", "p3", cur_map="white_deer", cur_subarea="white_deer_1")
    await evolve_via_tutor(m, "g1", "p3", "老兵·格里姆", 1)   # T1
    await cmd(m, "talk_choice", "g1", "p3", "0")
    await evolve_via_tutor(m, "g1", "p3", "老兵·格里姆", 1)   # T2
    await cmd(m, "talk_choice", "g1", "p3", "0")
    out = await evolve_via_tutor(m, "g1", "p3", "老兵·格里姆", 1)  # T3
    p = db.get_player("g1", "p3")
    check("90 级转战争领主 = T3", p["class_name"] == "cls_zhan_shi" and p["class_tier"] == 3,
          str((p["class_name"], p["class_tier"])))
    # v112 技能继承：导师转职自动授各档分支奥义（_evolve_auto_skills：二转取本分支
    # lv≥60 最低、三转取 lv≥90 最低）——按引擎同口径计算期望
    # v153：BRANCH_SKILLS 分支键只登记 T1 档位名（狂战士/盾卫士），二/三转档位名
    # 在 evolve_branches（狂战统领/战争领主）→ 用 T1 档位名查技能、按档位门槛取
    def _auto_expect(_t, _bn):
        _t1name = C.CLASSES["cls_zhan_shi"]["evolve_branches"][1][0]  # 狂战士（攻线 T1 名）
        _cand = [(int(_i.get("lv", 0)), _i.get("name", _s)) for _s, _i in
                 C.BRANCH_SKILLS["cls_zhan_shi"]["branches"][_t][_t1name].items()
                 if _i.get("lv", 0) >= (60 if _t == 2 else 90)]
        return _cand[0][1] if _cand else None
    auto_expect = {_auto_expect(2, "狂战统领"), _auto_expect(3, "战争领主")} - {None}
    check("转职自动授分支奥义", bool(auto_expect) and set(p["learned_skills"]) == auto_expect,
          f"got {set(p['learned_skills'])} expect {auto_expect}")

    print("[3] 等级门槛拦截")
    # 40 级法师直接转 T2/T3：evolve 命令只提示找导师（等级门槛在导师对话处拦）——
    # 转职命令本身对 tier=0 玩家一律提示导师；等级校验改由导师对话拦截（下节验证）
    make_player("g1", "p4", "修四", "法师", level=40)
    out = await cmd(m, "evolve", "g1", "p4", "转职 元素术士")
    check("40 级转元素术士被指引导师", "导师" in out, out[:150])
    out = await cmd(m, "evolve", "g1", "p4", "转职 元素贤者")
    check("40 级转元素贤者被指引导师", "导师" in out, out[:150])
    # 40 级法师找导师转 T2 → 对话层 Lv.60 拦截
    db.update_player("g1", "p4", cur_map="white_deer", cur_subarea="white_deer_4")
    await cmd(m, "talk_choice", "g1", "p4", "对话 法师导师·艾琳")
    out = await cmd(m, "talk_choice", "g1", "p4", "3")
    check("40 级找导师转 T2 无转职选项", "转职" not in out, out[:150])

    print("[4] 同职业逐阶升 + 跳档/跨职业")
    # p4 40级法师：先转 T1（30 级达标）→ 升 60 → 转 T2 → 升 90 → 转 T3
    db.update_player("g1", "p4", cur_map="white_deer", cur_subarea="white_deer_1")
    out = await evolve_via_tutor(m, "g1", "p4", "大法师·艾德琳", 1)
    p = db.get_player("g1", "p4")
    check("40 级法师转 T1 元素法师", p["class_tier"] == 1, str(p["class_tier"]))
    await cmd(m, "talk_choice", "g1", "p4", "0")
    db.update_player("g1", "p4", level=60)
    out = await evolve_via_tutor(m, "g1", "p4", "大法师·艾德琳", 1)
    p = db.get_player("g1", "p4")
    check("T1→T2 逐阶升", p["class_tier"] == 2, str(p["class_tier"]))
    await cmd(m, "talk_choice", "g1", "p4", "0")
    db.update_player("g1", "p4", level=90)
    out = await evolve_via_tutor(m, "g1", "p4", "大法师·艾德琳", 1)
    p = db.get_player("g1", "p4")
    check("T2→T3 逐阶升", p["class_tier"] == 3, str(p["class_tier"]))
    # 满阶后再找导师：无转职入口
    await cmd(m, "talk_choice", "g1", "p4", "0")
    out = await cmd(m, "talk_choice", "g1", "p4", "对话 大法师·艾德琳")
    check("满阶导师对话无转职入口", "转职" not in out, out[:120])
    # 跨职业 90 级战士找战士导师逐阶升到 T3（修为继承）
    make_player("g1", "p5", "修五", "战士", level=90)
    db.update_player("g1", "p5", cur_map="white_deer", cur_subarea="white_deer_1")
    await evolve_via_tutor(m, "g1", "p5", "老兵·格里姆", 1)   # T1
    await cmd(m, "talk_choice", "g1", "p5", "0")
    await evolve_via_tutor(m, "g1", "p5", "老兵·格里姆", 1)   # T2
    await cmd(m, "talk_choice", "g1", "p5", "0")
    out = await evolve_via_tutor(m, "g1", "p5", "老兵·格里姆", 1)  # T3
    p = db.get_player("g1", "p5")
    check("90 级战士导师逐阶升到 T3 成功", p["class_tier"] == 3, str((p["class_tier"])))
    # 同职业 T1 跳 T3 拦截：已转 T1 的 90 级 → 导师只给 T2 入口（『继续转职』，无『最终转职』）
    make_player("g1", "p6", "修六", "法师", level=90)
    db.update_player("g1", "p6", cur_map="white_deer", cur_subarea="white_deer_1")
    await evolve_via_tutor(m, "g1", "p6", "大法师·艾德琳", 1)
    p = db.get_player("g1", "p6")
    check("T1 转职成功", p["class_tier"] == 1, str(p["class_tier"]))
    await cmd(m, "talk_choice", "g1", "p6", "0")
    out = await cmd(m, "talk_choice", "g1", "p6", "对话 大法师·艾德琳")
    check("T1 跳 T3 被拦（导师只给 T2 入口）", "继续转职" in out and "最终转职" not in out, out[:150])
    await cmd(m, "talk_choice", "g1", "p6", "3")
    await cmd(m, "talk_choice", "g1", "p6", "1")
    p = db.get_player("g1", "p6")
    check("T2 逐阶升成功", p["class_tier"] == 2, str(p["class_tier"]))

    print("[5] 『转职』无参数（基础职业进化之路）")
    out = await cmd(m, "evolve", "g1", "p6", "转职")
    check("基础职业显示可选路线", "可选路线" in out and "元素贤者" in out, out[:150])
    out = await cmd(m, "evolve", "g1", "p3", "转职")
    check("满阶显示已完成全部转职", "已完成全部转职" in out, out[:120])

    print("[6] 『转职重置』回根基职业")
    # p5 已 T3 → 重置回战士
    db.update_player("g1", "p5", gold=5000)
    gold0 = db.get_player("g1", "p5")["gold"]
    out = await cmd(m, "evolve_reset", "g1", "p5", "转职重置")
    p = db.get_player("g1", "p5")
    check("重置回战士", p["class_name"] == "cls_zhan_shi" and p["class_tier"] == 0 and p["evolve_path"] == 0,
          str((p["class_name"], p["class_tier"], p["evolve_path"])))
    check("重置扣费", p["gold"] < gold0, str(p["gold"]))
    check("重置文案回根基", "转职重置成功" in out and "回到基础职业" in out, out[:150])

    print("[7] 统一 30/60/90 档位")
    # 牧师 30 级导师转神谕者（攻线 T1）——牧师导师·圣殿执事·莉亚（白鹿城·白鹿广场）
    make_player("g1", "p7b", "亡语", "牧师", level=30)
    db.update_player("g1", "p7b", cur_map="white_deer", cur_subarea="white_deer_1")
    out = await evolve_via_tutor(m, "g1", "p7b", "圣殿执事·莉亚", 1)
    p = db.get_player("g1", "p7b")
    check("30 级神谕者 = T1(牧师攻线)",
          p["class_name"] == "cls_mu_shi" and p["class_tier"] == 1 and p["evolve_path"] == 1,
          str((p["class_name"], p["class_tier"], p["evolve_path"])))
    # 刺客 60 级导师转 T2 攻线（暗影之刃）→ 90 级升 T3（无影之刃）
    make_player("g1", "p8", "影修", "刺客", level=60)
    db.update_player("g1", "p8", cur_map="ironharbor", cur_subarea="ironharbor_1")
    await evolve_via_tutor(m, "g1", "p8", "暗影渡鸦", 1)   # T1
    await cmd(m, "talk_choice", "g1", "p8", "0")
    out = await evolve_via_tutor(m, "g1", "p8", "暗影渡鸦", 1)  # T2
    p = db.get_player("g1", "p8")
    check("60 级『转职 暗影之刃』= T2 攻线",
          p["class_name"] == "cls_ci_ke" and p["class_tier"] == 2 and p["evolve_path"] == 1,
          str((p["class_name"], p["class_tier"], p["evolve_path"])))
    await cmd(m, "talk_choice", "g1", "p8", "0")
    db.update_player("g1", "p8", level=90)
    out = await evolve_via_tutor(m, "g1", "p8", "暗影渡鸦", 1)  # T3
    p = db.get_player("g1", "p8")
    check("升 T3 无影之刃保留攻线",
          p["class_tier"] == 3 and p["evolve_path"] == 1 and "无影之刃" in out,
          str((p["class_tier"], p["evolve_path"], out[:80])))
    # 拳师 30 级导师转格斗士（攻线 T1）——拳师导师·船帮武师·老陈（铁港城·港口广场）
    make_player("g1", "p8b", "拳修", "拳师", level=30)
    db.update_player("g1", "p8b", cur_map="ironharbor", cur_subarea="ironharbor_1")
    out = await evolve_via_tutor(m, "g1", "p8b", "船帮武师·老陈", 1)
    p = db.get_player("g1", "p8b")
    check("30 级『转职 格斗士』= T1 攻线",
          p["class_name"] == "cls_wu_seng" and p["class_tier"] == 1 and p["evolve_path"] == 1,
          str((p["class_name"], p["class_tier"], p["evolve_path"])))

    print("[8] 转职拦截（等级/位阶校验仍生效）")
    # 40 级战士找导师：无 T2 转职入口（Lv.60 门槛在导师处拦）
    make_player("g1", "p9", "修九", "战士", level=40)
    db.update_player("g1", "p9", cur_map="white_deer", cur_subarea="white_deer_1")
    await cmd(m, "talk_choice", "g1", "p9", "对话 老兵·格里姆")
    out = await cmd(m, "talk_choice", "g1", "p9", "3")
    check("40 级找导师无 T2 转职入口", "继续转职" not in out, out[:150])
    # 40 级找导师转 T1 成功（30 级达标）→ 升 90 后同职业只能逐阶
    await cmd(m, "talk_choice", "g1", "p9", "3")
    out = await cmd(m, "talk_choice", "g1", "p9", "1")
    p = db.get_player("g1", "p9")
    check("40 级导师转 T1 成功", p["class_tier"] == 1, str(p["class_tier"]))
    await cmd(m, "talk_choice", "g1", "p9", "0")
    db.update_player("g1", "p9", level=90)
    # T1 跳 T3 拦截（战士版）：T1 → 导师只给 T2 入口（狂战统领路线）
    await cmd(m, "talk_choice", "g1", "p9", "对话 老兵·格里姆")
    out = await cmd(m, "talk_choice", "g1", "p9", "3")
    check("T1 跳 T3 被拦（导师只给 T2 入口）", "狂战统领" in out and "战争领主" not in out, out[:150])
    await cmd(m, "talk_choice", "g1", "p9", "1")
    p = db.get_player("g1", "p9")
    check("战士 T2 逐阶升成功", p["class_tier"] == 2, str(p["class_tier"]))
    # 90 级新手战士找导师：只给 T1 入口（位阶从 0 起逐阶）
    make_player("g1", "p12", "修十二", "战士", level=90)
    db.update_player("g1", "p12", cur_map="white_deer", cur_subarea="white_deer_1")
    await cmd(m, "talk_choice", "g1", "p12", "对话 老兵·格里姆")
    out = await cmd(m, "talk_choice", "g1", "p12", "3")
    check("90 级新手导师只给 T1 入口", "转职为狂战士" in out and "继续转职" not in out, out[:150])

    print(f"\n===== v112 职业树测试: {passed} passed, {failed} failed =====")
    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
