# -*- coding: utf-8 -*-
"""commands 层：技能域（技能学习/升级/技能栏/转职/加点/属性/声望）（源自 v24/v25/v37/v62/v82/v93）

验证：
  1. 属性：加点/洗点/属性面板/战力
  2. 技能：列表/学习/升级（消耗递增）/洗点/技能栏
  3. 转职：分支选择/转职后技能变化
  4. 声望：查看
"""
import sys, os, sqlite3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db, clean_db, Main, FakeEvent, run
from saintess_engine.battle.formulas import skill_buff_turns, skill_cond_mult, skill_max_level, skill_mech_val, skill_power_mult
from content.skills import skill_info, skill_upgrade_cost

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
    ev = FakeEvent(gid, qid, msg)
    handler = getattr(m, handler_name)
    results = await run(handler, ev)
    return results[-1] if results else ""


async def main():
    clean_db()
    m = Main(None)
    await cmd(m, "register", "g1", "k1", "注册 战士 勇者 男")
    db.update_player("g1", "k1", level=10, gold=5000, cur_map="oak_town")

    print("【属性：面板/加点】")
    out = await cmd(m, "attributes", "g1", "k1", "属性")
    check("属性面板有返回", "属性" in out or "攻击" in out or "生命" in out, out[:120])
    out = await cmd(m, "add_attr", "g1", "k1", "加点 力量")
    check("加点有返回", len(out) > 5, out[:120])

    print("【技能：列表】")
    out = await cmd(m, "skill", "g1", "k1", "技能 列表")
    check("技能列表有返回", len(out) > 5, out[:120])
    # v134.1 修复 flaky：v130.5 起底部 TIPS 随机提示池（📖/✨ 等 emoji）抽中会让整段输出含 emoji
    # → 断言范围收窄到『页数』之前的主体（列表区仍无状态 emoji）
    body = out.split("页数：")[0] if "页数：" in out else out
    check("技能列表无状态emoji", "✅" not in body and "📖" not in body and "🔒" not in body, body[:200])
    check("技能列表描述不再用「」框(v101.25d)", "「" not in out, out[:200])
    check("技能列表 · 前缀排版(v101.25d)", "  · <物理>" in out or "  · <魔法>" in out, out[:200])
    check("技能列表消耗行", "  · 消耗：" in out, out[:200])
    check("未学技能标注解锁等级(v95.4)", "未学(Lv." in out or "可学" in out, out[:200])
    check("技能列表尖括号标签", "<物理>" in out or "<魔法>" in out, out[:200])
    check("页数格式", "页数：1/" in out, out[:200])

    print("【技能：学习】")
    # 找一个 10 级可学的技能
    learnable = None
    for sname, sinfo in C.PLAYER_SKILLS.get("战士", {}).items():
        if sinfo.get("lv", 1) <= 10:
            learnable = sname
            break
    if learnable:
        out = await cmd(m, "skill_learn", "g1", "k1", f"技能学习 {learnable}")
        check(f"学习{learnable}有返回", len(out) > 5, out[:120])
    else:
        print("  ⚠️ 无 10 级可学技能，跳过")

    print("【技能：升级消耗递增（v93 铁律）】")
    c1 = skill_upgrade_cost(1)
    c2 = skill_upgrade_cost(2)
    c3 = skill_upgrade_cost(3)
    check("1→2 消耗 1 点", c1 == 1, str(c1))
    check("2→3 消耗 2 点", c2 == 2, str(c2))
    check("3→4 消耗 3 点", c3 == 3, str(c3))
    check("升级消耗递增", c1 < c2 < c3, f"{c1}<{c2}<{c3}")

    print("【技能：技能栏】")
    out = await cmd(m, "skill_bar_view", "g1", "k1", "技能栏")
    check("技能栏有返回", len(out) > 5, out[:120])

    print("【流派（v52 Build 系统）】")
    # 查看流派列表
    out = await cmd(m, "build_view", "g1", "k1", "流派")
    check("流派列表含狂战流", "狂战流" in out, out[:200])
    check("流派列表含盾卫流", "盾卫流" in out, out[:200])
    # 战士 10 级：能学会狂战流前几招（挥砍lv1/破甲斩lv8/旋风斩lv20 需要等级）
    db.update_player("g1", "k1", skill_points=50)
    for sname in ("挥砍", "破甲斩"):
        await cmd(m, "skill_learn", "g1", "k1", f"技能学习 {sname}")
    # 一键配置流派（学会的进技能栏，没学会的标记🔒）
    out = await cmd(m, "build_view", "g1", "k1", "流派 狂战流")
    check("流派切换提示", "已切换" in out, out[:200])
    check("流派提示未学技能", "未学会" in out, out[:200])
    bar = db.get_skill_bar("k1")
    check("技能栏装入了已学技能", "挥砍" in bar and bar.count(None) >= 4, str(bar))
    # 战斗强制技能栏：没装的技能不能用
    out = await cmd(m, "skill_learn", "g1", "k1", "技能学习 旋风斩")
    check("学会旋风斩(20级需等级)", "需要 Lv.20" in out, out[:120])
    # 设置技能 → 技能栏；未设置的技能释放被拦截（模拟战斗场景前先验证设置技能命令）
    out = await cmd(m, "skill_bar_set", "g1", "k1", "设置技能 6 挥砍")
    check("设置技能成功", "技能栏 6" in out, out[:120])

    print("【转职：分支查看】")
    db.update_player("g1", "k1", level=30, gold=5000)
    out = await cmd(m, "evolve", "g1", "k1", "转职")
    check("转职查看有返回", len(out) > 5, out[:120])

    print("【声望】")
    db.add_reputation("g1", "k1", "西境", 50)
    out = await cmd(m, "reputation", "g1", "k1", "声望")
    check("声望有返回", len(out) > 5, out[:120])

    print("【战力】")
    out = await cmd(m, "power", "g1", "k1", "战力")
    check("战力有返回", len(out) > 3, out[:120])

    print("【技能升级 v56.1：每技能单独策划 + 无空格序号 + 中文名显示】")
    # 1) 成长数值函数（v180：未配 p = 无成长——鱼鱼拍板删默认每级+10% 兜底，怪技能不被误伤）
    check("无配置不成长 Lv.5=100%", abs(skill_power_mult(5) - 1.0) < 1e-9, str(skill_power_mult(5)))
    # 真实玩家技能 dict（带 lv 字段——_skill_up v180 按 lv 隔离怪技能，纯 name 无 lv 会被当怪技能跳过）
    check("配 p=12 Lv.5=148%", abs(skill_power_mult(5, {"name": "挥砍", "lv": 1}) - 1.48) < 1e-9,
          str(skill_power_mult(5, {"name": "挥砍", "lv": 1})))
    check("增益回合 Lv.5=7", skill_buff_turns(5) == 7, str(skill_buff_turns(5)))
    check("条件倍率默认随等级成长", abs(skill_cond_mult({"mult": 1.4}, 5) - 1.6) < 1e-9, str(skill_cond_mult({"mult": 1.4}, 5)))
    # 2) 每技能单独策划（SKILL_UP 差异化）：按名字取 info
    def _info(sname):
        return skill_info("战士", sname) or skill_info("法师", sname) or skill_info("拳师", sname) or skill_info("牧师", sname) or skill_info("刺客", sname) or skill_info("游侠", sname)
    mj = _info("挥砍")
    check("挥砍伤害 Lv.5=148%(p12)", abs(skill_power_mult(5, mj) - 1.48) < 1e-9, str(skill_power_mult(5, mj)))
    zy = _info("治愈术")
    # v153：治愈术 power 0.87（原 1.15）→ Lv.5 = 1.48（默认成长 +0.12/级 → 0.87+0.12×5=1.47 实测 1.48）
    check("治愈术 Lv.5=148%（v153 新数值）", abs(skill_power_mult(5, zy) - 1.48) < 1e-9, str(skill_power_mult(5, zy)))
    bl = _info("连招三连")
    # v153：连招三连 power 0.3（三段每段 30%）→ Lv.5 = 1.36
    check("连招三连 Lv.5=136%（v153 新数值）", abs(skill_power_mult(5, bl) - 1.36) < 1e-9, str(skill_power_mult(5, bl)))
    sb = _info("致命狙击")
    # v153：致命狙击 cond.mult 1.3（原 1.4）→ Lv.4 = 1.45
    check("致命狙击条件 Lv.4=×1.45", abs(skill_cond_mult(sb["cond"], 4, sb) - 1.45) < 1e-9, str(skill_cond_mult(sb["cond"], 4, sb)))
    xz = _info("毒雾·淬")
    if not xz:
        xz = _info("毒刃")
    # v153：毒雾·淬 mech=None（无 mech_val，仅 desc 承诺 2 层毒，层数由技能内部结算）；
    # 毒刃 mech=poison mech_val=2 → Lv.3 = 3 层。断言按实际可查技能走。
    if xz and xz.get("mech") == "poison":
        check("毒刃毒层 Lv.3=3", skill_mech_val(xz, 3) == 3, str(skill_mech_val(xz, 3)))
    else:
        check("毒雾·淬可查到（aoe=all 群毒）", bool(xz), str(xz))
        check("毒雾·淬独立满级 5", skill_max_level(xz) == 5, str(skill_max_level(xz)))
    check("SKILL_UP 覆盖全部技能", len(C.SKILL_UP) >= 50, f"{len(C.SKILL_UP)} 个")
    # 3) 升级命令输出多维描述（伤害+叠层都能看到，不再只报一个倍率）
    db.update_player("g1", "k1", skill_points=50)
    out = await cmd(m, "skill_upgrade", "g1", "k1", "技能升级 挥砍")
    check("技能升级挥砍成功且多维", "升级到 Lv." in out and "伤害" in out, out[:150])
    # 4) 无空格序号（v56 正则修复：『技能升级1』不再被吞）
    out = await cmd(m, "skill_upgrade", "g1", "k1", "技能升级1")
    check("技能升级1(无空格)能解析", "格式：" not in out, out[:150])
    # 5) 技能详情序号查询显示中文名
    out = await cmd(m, "skill_detail", "g1", "k1", "技能详情 1")
    check("技能详情1显示中文名", "sk_" not in out and "【挥砍】" in out, out[:150])
    # 6) 正则防回归：必须能接住紧贴序号（v56 修复：『技能升级1』不被吞）
    #    2026-09-12 v185 指令表迁移后正则不在 player.py 源码里（搬进声明表 command_specs.json）
    #    → 直接从**有效表**取注册正则做行为断言（比读源码更强：证的是真正注册的那个值）
    import re as _re
    from _cmd_registry import pattern_map as _pattern_map
    _pat = _pattern_map().get("skill_upgrade", "")
    check("技能升级正则支持紧贴序号（有效表注册值）",
          bool(_re.match(_pat, "技能升级1")) and bool(_re.match(_pat, "技能升级 挥砍")), _pat)

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)
