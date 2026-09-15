# -*- coding: utf-8 -*-
"""v130.8 意见#31 副本列表钥匙需求引导固化测试。

覆盖：
  ① 『副本』列表（_instance_list）有钥匙副本在 Boss 行下追加
     🔑 需『钥匙名』：获取途径（断言 沉船湾=幽灵船票/沉船湾墓地采集、
     旧王陵=王陵钥匙/白鹿城铁匠铺购买 两例，且钥匙行紧跟其 Boss 行）
  ② 无 key_item 副本（哥布林营地，缺省 key_item）不显示 🔑 行
  ③ 列表其余结构不回归：序号标题行 / 每副本一条 Boss·掉落行

运行：python tests/test_v1308_key_guide.py（exit=0 全绿）
"""
import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from conftest import C, clean_db, Main, FakeEvent, run, make_player  # noqa: E402

G, Q = 1095961598, "gm_v1308_key"

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"✅ {name}")
    else:
        failed += 1
        print(f"❌ {name} {detail}")


async def _instance_list(m, gid, qid):
    ev = FakeEvent(gid, qid, "副本")
    results = await run(m.instance_cmd, ev)
    return results[-1] if results else ""


async def main():
    m = Main()
    clean_db()
    # 满级玩家：列表全部 ✅ 解锁态（mark 只由等级决定），断言不受等级锁干扰
    make_player(G, Q, "钥匙引导测试", "战士", level=100)
    out = await _instance_list(m, G, Q)
    lines = out.splitlines()

    # ---- ① 有钥匙副本：🔑 行 = 钥匙名 + 获取途径，紧跟其 Boss 行 ----
    k1 = "🔑 需『幽灵船票』：沉船湾墓地采集"
    check("① 沉船湾钥匙引导行", k1 in out, out[:400])
    idx = next(i for i, l in enumerate(lines) if k1 in l)
    check("① 钥匙行紧跟沉船湾 Boss 行",
          lines[idx - 1].startswith("   👹 Boss：幽灵船长·克罗") and "掉落：" in lines[idx - 1],
          f"上一行={lines[idx - 1]!r}")

    k2 = "🔑 需『王陵钥匙』：白鹿城铁匠铺购买(500 金)"
    check("① 旧王陵钥匙引导行", k2 in out, out[:400])
    idx2 = next(i for i, l in enumerate(lines) if k2 in l)
    check("① 钥匙行紧跟旧王陵 Boss 行",
          lines[idx2 - 1].startswith("   👹 Boss：古王·奥德里克") and "掉落：" in lines[idx2 - 1],
          f"上一行={lines[idx2 - 1]!r}")

    # ---- ② 无 key_item 副本（哥布林营地）不显示 🔑 行 ----
    gi = next(i for i, l in enumerate(lines) if "👺 哥布林营地" in l)
    boss_i = next(i for i, l in enumerate(lines) if "👹 Boss" in l and i > gi)
    nxt = next(i for i, l in enumerate(lines)
               if l and l[0].isdigit() and i > boss_i)
    seg = lines[gi:nxt]
    check("② 哥布林营地块无🔑行", "🔑" not in "\n".join(seg), f"seg={seg}")
    check("② 哥布林营地 Boss 行在", any("👹 Boss" in l for l in seg), seg)

    # ---- ③ 结构不回归：序号标题行 / 每副本一条 Boss·掉落行 ----
    titles = [l for l in lines if l and l[0].isdigit() and ". " in l]
    check("③ 序号标题行数与副本数一致", len(titles) == len(C.INSTANCES),
          f"titles={len(titles)} insts={len(C.INSTANCES)}")
    check("③ 序号从1开始", titles[0].startswith("1. "), titles[:2])
    boss_list = [l for l in lines if "👹 Boss" in l and "掉落：" in l]
    check("③ Boss·掉落行数与副本数一致", len(boss_list) == len(C.INSTANCES),
          f"boss={len(boss_list)} insts={len(C.INSTANCES)}")

    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)


asyncio.run(main())