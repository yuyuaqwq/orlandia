# -*- coding: utf-8 -*-
"""v134.1 意见#47 冒烟：技能列表多等级效果曲线渲染（英雄联盟式）"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db, clean_db, make_player  # noqa: E402
from _engine_harness import Main  # noqa: E402

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")


def main():
    clean_db()
    m = Main()
    for cls, lv, name in (("战士", 10, "战士"), ("牧师", 15, "牧师"), ("刺客", 12, "刺客")):
        g = f"g_{cls}"
        q = f"q_{cls}"
        make_player(g, q, name, cls, level=lv)
        db.update_player(g, q, skill_points=500, cur_map="oak_town")
        p = m._player(g, q)
        # 学 3 个技能（含增益/治疗），升不同等级
        sid = None
        _table = C.PLAYER_SKILLS.get(C.resolve("classes", cls), {})
        # v134.1 意见#47：PLAYER_SKILLS[cls] 结构为 {"name":中文名, "skills":{技能表}}，取内层 skills
        if isinstance(_table, dict) and "skills" in _table:
            _table = _table["skills"]
        for sname, sinfo in _table.items():
            if isinstance(sinfo, dict) and sinfo.get("lv", 1) <= lv:
                sid = sname
                break
        if not sid:
            print(f"  ⚠️ {cls} 无可用技能，跳过")
            continue
        s1 = sid
        # 直接改库标记已学（learned_skills/skill_levels 写 ID——store 读回才稳定，中文名会被 resolve 混淆）
        db.update_player(g, q, learned_skills=[s1], skill_levels={s1: 1})
        p = m._player(g, q)
        out = m._skill_list_page(p, 1)
        print(f"\n== {cls} Lv.{lv} 技能列表 ==")
        for ln in out.splitlines():
            if ln.startswith(("1.", "  · ")):
                print(f"  {ln}")
        # v134.4 意见#57：曲线从列表移到『技能详情』——列表不再含等级曲线（desc/曲线）
        # 页数行『页数：1/4』含 /，不能用 / 判断；检查技能条目区无曲线特征（伤害%/持续回合）
        _no_curve = ("· 伤害" not in out and "· 持续" not in out
                     and "· 恢复" not in out and "· 防御" not in out and "· 魔攻" not in out)
        check(f"{cls} 技能列表不再显示描述/曲线", _no_curve, out[:200])
        # 详情应显示当前等级效果曲线
        det = m._skill_detail_msg(p, s1) if hasattr(m, "_skill_detail_msg") else None
        if det is None:
            # 走 handler 路径（序号 1）
            import asyncio
            from _engine_harness import FakeEvent, run
            ev = FakeEvent(g, q, "技能详情 1")
            _r = asyncio.run(run(m.skill_detail, ev))
            det = _r[0] if _r else ""
        check(f"{cls} 技能详情有等级曲线", "/" in det or "%" in det, det[:200])
        # 升级到 Lv.3 后详情曲线应保持全等级展示
        db.update_player(g, q, skill_levels={s1: 3})
        p3 = m._player(g, q)
        out3 = m._skill_list_page(p3, 1)
        check(f"{cls} 技能列表升级后仍无曲线", "112%" not in out3 and "148%" not in out3, out3[:200])
    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)


main()
