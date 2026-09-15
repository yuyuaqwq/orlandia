# -*- coding: utf-8 -*-
"""v95.23 职业体系改造：见习注册 → 行会就职 → 导师进阶技能 → 导师转职

验证：
  1. 新格式注册『注册 <名字> [种族]』→ 见习冒险者（无职业技能）
  2. 旧格式『注册 <职业> <名字>』兼容保留
  3. 见习技能学习被拦（引导就职）
  4. 行会接待员·小艾对话就职：选职业 → 属性重算 + 基础技能书
  5. 就职后技能学习正常
  6. 导师进阶技能：等级/金币门槛 + 学会不耗技能点
  7. 『转职』指令：等级到了引导找导师
  8. 导师对话转职（Lv.30 → 分支选择）
"""
import sys, os
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

    print("【1. 新格式注册 → 见习冒险者】")
    out = await cmd(m, "register", "g1", "w1", "注册 新手甲 精灵 男")
    check("注册成功", "欢迎来到奥兰迪亚大陆" in out, out[:200])
    check("职业为见习", "见习冒险者" in out, out[:200])
    p = db.get_player("g1", "w1")
    check("class_name=cls_novice", p["class_name"] == "cls_novice", p.get("class_name", ""))
    check("种族=银月精灵", p.get("race") == "elf", str(p.get("race")))
    check("注册引导就职", "行会接待员·小艾" in out, out[:300])
    check("见习无初始技能", len(p.get("learned_skills") or []) == 0, str(p.get("learned_skills")))

    print("【2. 见习技能学习被拦】")
    out = await cmd(m, "skill_learn", "g1", "w1", "技能学习 斩击")
    check("见习无法学技能", "见习冒险者还没有职业技能" in out, out[:200])

    print("【3. 旧格式注册兼容】")
    out = await cmd(m, "register", "g2", "w2", "注册 法师 旧人 男")
    check("旧格式仍可注册职业", "职业：🔮 法师" in out or "法师" in out, out[:200])
    p2 = db.get_player("g2", "w2")
    check("旧格式职业=cls_fa_shi", p2["class_name"] == "cls_fa_shi", p2.get("class_name", ""))
    check("旧格式有初始技能", len(p2.get("learned_skills") or []) >= 1, str(p2.get("learned_skills")))

    print("【4. 行会就职流程】")
    out = await cmd(m, "find_npc", "g1", "w1", "找 小艾")
    check("小艾对话打开", "新人就职登记" in out, out[:300])
    check("职业选项列出", "战士" in out and "法师" in out and "拳师" in out, out[:400])
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    check("选择战士→确认节点", "确定就职为战士" in out, out[:300])
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    check("就职成功", "就职【🛡️ 战士】" in out or "就职【战士】" in out, out[:400])
    check("基础技能书赠送", "基础技能书" in out, out[:400])
    p = db.get_player("g1", "w1")
    check("class 变为战士", p["class_name"] == "cls_zhan_shi", p.get("class_name", ""))
    check("学会了初始技能", len(p.get("learned_skills") or []) >= 1, str(p.get("learned_skills")))
    # 属性按战士重算（v104 修复：用 max_hp 计算值，精灵月缺 ×0.95 → 142）
    check("属性重算为战士 max_hp", p.get("max_hp", 0) >= 140, f"max_hp={p.get('max_hp')}")

    print("【5. 就职后技能学习正常】")
    out = await cmd(m, "skill_learn", "g1", "w1", "技能学习 1")
    check("技能学习有返回", len(out) > 5, out[:200])

    print("【6. 已就职再找小艾不显示就职选项】")
    out = await cmd(m, "find_npc", "g1", "w1", "找 小艾")
    check("就职选项隐藏", "确定就职" not in out, out[:400])
    check("闲聊选项在", "随便聊聊" in out, out[:400])

    print("【7. 导师进阶技能门槛】")
    db.update_player("g1", "w1", cur_map="white_deer", cur_subarea="white_deer_1", level=5, gold=1000)
    out = await cmd(m, "find_npc", "g1", "w1", "找 格里姆")
    check("战士导师对话", "破甲斩" in out or "三板斧" in out, out[:400])
    # 等级 5 < 8 → 等级拦截（v104 R3 修复门槛倒挂：以 skills.py 真实技能等级为准，破甲斩 Lv.8）
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    check("等级不足拦截", "Lv.8" in out and "学得动" in out, out[:400])
    # 升到 8 级、金币不足
    db.update_player("g1", "w1", level=8, gold=100)
    out = await cmd(m, "find_npc", "g1", "w1", "找 格里姆")
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    check("金币不足拦截", "学费 800 金币" in out, out[:400])
    # 金币够 → 学会
    db.update_player("g1", "w1", level=8, gold=5000)
    out = await cmd(m, "find_npc", "g1", "w1", "找 格里姆")
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    check("学会破甲斩", "学会了进阶技能『破甲斩』" in out, out[:500])
    p = db.get_player("g1", "w1")
    check("破甲斩入 learned_skills", "破甲斩" in (p.get("learned_skills") or []), str(p.get("learned_skills")))
    check("金币扣 800", p.get("gold", 0) == 4200, f"gold={p.get('gold')}")

    print("【8. 非本职业导师不显示教学】")
    out = await cmd(m, "find_npc", "g1", "w1", "找 艾德琳")
    # v110.5 X3：恒真断言替换——战士(非法师)拜访法师导师，输出不得泄漏法师专属技能；
    # 旧名『奥术脉冲』v110.1 已改『魔力脉冲』，若输出仍含旧名即红。
    check("法师导师无战士教学选项", "奥术脉冲" not in out, out[:300])
    check("战士邀导师不展示法师专属『魔力脉冲』", "魔力脉冲" not in out, out[:300])
    # 正向对照（数据级）：法师(cls_fa_shi)拜访 npc_mage_tutor 的 welcome 节点，
    # 『魔力脉冲』教学选项必须可见（保证新旧命名一致、对话树仍在配置）。
    _mdlg = C.get_dialogue("npc_mage_tutor")
    _ctx = {"player": {"class_name": "cls_fa_shi", "level": 30, "gold": 99999},
            "quests": {"main_quest": None, "main_status": "pending",
                       "completed_main": [], "side": {}},
            "flags": [], "npc_id": "npc_mage_tutor"}
    _opts = C.visible_options(_mdlg, _mdlg["nodes"]["welcome"], _ctx)
    check("法师导师教学菜单含『魔力脉冲』(新名,next=teach_ao_shu)",
          any("魔力脉冲" in o["text"] and o.get("next") == "teach_ao_shu" for o in _opts),
          str([o["text"] for o in _opts]))
    # 反向：战士语境下该选项必须被过滤掉（可见选项过滤有效）
    _opts_war = C.visible_options(
        _mdlg, _mdlg["nodes"]["welcome"],
        {"player": {"class_name": "cls_zhan_shi", "level": 30, "gold": 99999},
         "quests": {"main_quest": None, "main_status": "pending",
                    "completed_main": [], "side": {}},
         "flags": [], "npc_id": "npc_mage_tutor"})
    check("战士语境法师教学选项被过滤（无『魔力脉冲』）",
          all("魔力脉冲" not in o["text"] for o in _opts_war),
          str([o["text"] for o in _opts_war]))

    print("【9. 转职指令引导找导师】")
    db.update_player("g1", "w1", level=30)
    out = await cmd(m, "evolve", "g1", "w1", "转职")
    check("引导找导师", "老兵·格里姆" in out and "白鹿广场" in out, out[:400])
    check("不再直接转职", "转职成功" not in out, out[:400])

    print("【10. 导师对话转职（Lv.30）】")
    out = await cmd(m, "find_npc", "g1", "w1", "找 格里姆")
    check("转职选项出现", "我想转职" in out, out[:400])
    out = await cmd(m, "talk_choice", "g1", "w1", "3")
    check("分支选择", "狂战士" in out and "盾卫士" in out, out[:400])
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    check("转职成功", "转职成功" in out and "狂战士" in out, out[:500])
    p = db.get_player("g1", "w1")
    check("class_tier=1", p.get("class_tier") == 1, str(p.get("class_tier")))
    check("evolve_path=1(进攻)", p.get("evolve_path") == 1, str(p.get("evolve_path")))

    print("【11. 见习不可直接学其他职业技能（回归）】")
    await cmd(m, "register", "g3", "w3", "注册 见习二号 男")
    p3 = db.get_player("g3", "w3")
    check("第三个号也是见习", p3["class_name"] == "cls_novice", p3.get("class_name", ""))

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0

import asyncio
sys.exit(0 if asyncio.run(main()) else 1)
