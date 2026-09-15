# -*- coding: utf-8 -*-
"""v87.13b 验证：移动到达展示与『地图』展示一致（子区域级信息）"""
import sys, os, asyncio, random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import FakeEvent, run, clean_db, Main, db

random.seed(20260810)  # 固定 seed：消除移动撞怪(25%)的随机性，保证场景行稳定

passed = failed = 0
def check(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")

async def main():
    clean_db()
    db.init_db()
    m = Main(None)
    # 直接落库玩家（register 有群绑定逻辑，make_player 更稳）
    from conftest import make_player
    make_player("g1", "1001", "甲", "战士")
    p = db.get_player("g1", "1001")
    check("造玩家", p is not None)
    # 玩家初始位置 oak_town（广场 oak_town_1）
    db.update_player("g1", "1001", cur_map="oak_town", cur_subarea="oak_town_1")

    # v87.14 空间连接：出城需先到出口子区域
    # v87.16 街道链：广场 → 东大街(5) → 镇郊(1) → 橡木平原(2)
    ev = FakeEvent("g1", "1001", "前往 5")
    r0 = "".join(str(x) for x in await run(m.move, ev))
    print("  [到东大街]", r0[:120].replace("\n", " | "))
    p = db.get_player("g1", "1001")
    check("到达东大街", p["cur_subarea"] == "oak_town_street", str(p.get("cur_subarea")))
    ev = FakeEvent("g1", "1001", "前往 1")
    r0 = "".join(str(x) for x in await run(m.move, ev))
    p = db.get_player("g1", "1001")
    check("到达镇郊", p["cur_subarea"] == "oak_town_outskirts", str(p.get("cur_subarea")))

    # oak_town 的邻居：橡木平原 oak_plain
    # v87.16 镇郊 vis_sas=[东大街] 1 个，邻居序号从 2 开始
    # 移动 2（橡木平原）→ 落点 oak_plain_1 草地边缘
    ev = FakeEvent("g1", "1001", "前往 2")
    r1 = "".join(str(x) for x in await run(m.move, ev))
    p1 = db.get_player("g1", "1001")
    print("  [跨图移动7]", r1[:300].replace("\n", " | "))
    check("落点 oak_plain_1", p1["cur_map"] == "oak_plain" and p1["cur_subarea"] == "oak_plain_1",
          f"{p1['cur_map']}:{p1['cur_subarea']}")
    # v101.15 撞怪分支显式处理：移动撞怪时展示为战斗界面（无场景行，设计如此）。
    # 曾依赖固定 seed 保证不撞怪，但新增随机调用（如坐骑 stamina_reduce 判定）会
    # 打乱序列——测试不再依赖运气，撞怪时单独断言战斗界面并跳过场景对比。
    ambushed = ("还没站稳" in r1) or ("拦住了去路" in r1)
    if ambushed:
        check("撞怪展示战斗界面", "你的行动" in r1 and "❤️" in r1, r1[:300])
        print("  [撞怪分支] 移动撞怪，场景一致性跳过（战斗界面优先）")
    else:
        check("移动展示含子区域描述", "草地边缘" in r1, r1[:150])
        # 场景应显示 oak_plain_1 的元素（橡木平原界碑）
        check("移动展示含目标场景元素", "界碑" in r1 or "橡木平原" in r1, r1[:300])

    # 然后发『地图』对比
    ev = FakeEvent("g1", "1001", "地图")
    r2 = "".join(str(x) for x in await run(m.map_view, ev))
    print("  [地图@草地边缘]", r2[:300].replace("\n", " | "))
    check("地图展示含子区域描述", "草地边缘" in r2, r2[:150])
    check("地图展示含场景元素", "界碑" in r2 or "橡木平原" in r2, r2[:300])

    # 一致性：移动到达的场景行 ⊆ 地图展示的场景行（都显示草地边缘的 PROPS）
    # 提取"✨ 场景"后的行
    def scene_lines(text):
        out = []
        in_scene = False
        for ln in text.split("\n"):
            if "✨ 场景" in ln:
                in_scene = True
                continue
            if in_scene:
                # 场景元素行以两个空格缩进（"  " + join）；撞怪等后续内容无缩进 → 截断
                if ln.strip() and not ln.startswith("  "):
                    break
                if ln.strip():
                    out.append(ln.strip())
        return out
    s1 = scene_lines(r1)
    s2 = scene_lines(r2)
    print(f"  移动场景行: {s1}")
    print(f"  地图场景行: {s2}")
    if ambushed:
        # 撞怪分支：移动展示为战斗界面，无场景行；『地图』仍应正常展示场景
        check("撞怪后地图仍展示场景", len(s2) >= 4, f"{s2}")
        check("撞怪分支地图含界碑", any("界碑" in x for x in s2), f"{s2}")
    else:
        check("移动与地图场景一致", set(s1) == set(s2), f"{s1} vs {s2}")

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
