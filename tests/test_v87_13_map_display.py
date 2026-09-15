# -*- coding: utf-8 -*-
"""v87.13 验证：①地图显示子区域描述 ②设施/场景拆分 ③对话中禁移动"""
import sys, os, asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import FakeEvent, run, clean_db, Main, db

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

    # 注册 + 初始在 oak_town
    ev = FakeEvent("g1", "1001", "注册 战士 甲 男")
    await run(m.register, ev)
    p = db.get_player("g1", "1001")
    check("注册", p is not None)

    # ① 地图命令：显示子区域描述（oak_town_1 冒险者广场）
    ev = FakeEvent("g1", "1001", "地图")
    r = "".join(str(x) for x in await run(m.map_view, ev)) if hasattr(m, "map_view") else ""
    # 找地图命令方法名
    if not r:
        for name in dir(m):
            if "map" in name.lower() and name not in ("map_view",):
                pass
    # 直接找 handler：搜注册表太重，直接看输出是否含子区域 desc
    print("  [地图面板]", r[:300].replace("\n", " | "))
    check("① 描述含子区域名（冒险者广场）", "冒险者广场" in r, r[:200])
    check("① 含设施区标题", "此地设施" in r, r[:300])
    # v132 场景拆两区：🔎 可探索触发（POI）/ ✨ 可交互场景（PROPS）
    check("① 含场景区标题", ("可探索触发" in r) or ("可交互场景" in r), r[:300])

    # ② 移动命令到达后也有设施/场景
    # v87.15 星形可达：广场出发序号 1 = 镇长办公处（oak_town_2）
    ev = FakeEvent("g1", "1001", "前往 1")
    r2 = "".join(str(x) for x in await run(m.move, ev))
    p2 = db.get_player("g1", "1001")
    print("  [移动2]", r2[:200].replace("\n", " | "))
    check("② 移动到镇长办公处", p2["cur_subarea"] == "oak_town_2", str(p2.get("cur_subarea")))
    check("② 描述为子区域描述", "镇长办公处" in r2, r2[:200])

    # 地图命令在 oak_town_2 应显示子区域 desc（橡木镇·镇长办公处）
    ev = FakeEvent("g1", "1001", "地图")
    r3 = "".join(str(x) for x in await run(m.map_view, ev))
    print("  [地图@镇长办公处]", r3[:250].replace("\n", " | "))
    check("①b 子区域描述显示镇长办公处", "镇长办公处" in r3, r3[:200])

    # ③ 对话中禁止移动：先找 NPC 对话
    # oak_town_2 镇长办公处有什么 NPC？直接设置 talk state 模拟
    db.set_talk_state("g1", "1001", "npc_mayor", "start")
    ev = FakeEvent("g1", "1001", "前往 1")
    r4 = "".join(str(x) for x in await run(m.move, ev))
    print("  [对话中移动]", r4[:120])
    check("③ 对话中移动被阻止", "交谈中" in r4 or "结束谈话" in r4, r4[:120])
    p4 = db.get_player("g1", "1001")
    check("③ 位置未变", p4["cur_subarea"] == "oak_town_2", str(p4.get("cur_subarea")))

    # 结束对话后可以移动
    db.clear_talk_state("g1", "1001")
    ev = FakeEvent("g1", "1001", "前往 1")
    r5 = "".join(str(x) for x in await run(m.move, ev))
    p5 = db.get_player("g1", "1001")
    check("③ 结束对话后可移动", p5["cur_subarea"] == "oak_town_1", f"{r5[:80]} | {p5.get('cur_subarea')}")

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
