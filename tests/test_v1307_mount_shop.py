# -*- coding: utf-8 -*-
"""v130.7 意见#23 坐骑商店位置固化测试（坐骑不再在草药铺/酒馆卖）

背景：economy.py 商店面板坐骑块原条件 `area_id=="oak" and cur==C.START_MAP`
无条件列出老马/小毛驴，艾琳炼药铺(oak_town_5, herb)与橡木桶旅店(oak_town_4, tavern)
也都显示坐骑——违和。修复为与武器块同口径的 sa_kind 白名单
（smith/general 贸易场所才卖坐骑，见 economy.py 4341/4481/4707），购买侧同步拦截。

覆盖：
  ① 草药铺(alchemy)商店面板：无老马/小毛驴/武器（武器块回归），有药剂
  ② 酒馆(heal)商店面板：无老马/小毛驴/武器
  ③ 铁匠铺(smith)商店面板：有老马/小毛驴（坐骑回归上线）+ 武器正常
  ④ 草药铺『购买 老马』→ 拒绝（橡木镇的商人才能买到）
  ⑤ 草药铺『购买 5』→ 没有第 5 号商品（序号列表无坐骑追加）
  ⑥ 酒馆『购买 老马』→ 拒绝
  ⑦ 铁匠铺『购买 老马』→ 成功（扣 500 金、owned 含 mount_horse）
  ⑧ 铁匠铺序号购买坐骑：面板翻页解析老马序号 → 『购买 N』成功
  ⑨ 铁匠铺『购买 小毛驴』→ Lv.5 等级拦截不回归

运行：python tests/test_v1307_mount_shop.py（exit=0 全绿）
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_v1307_mount_shop.db")
os.environ["GWEN_GAME_DB"] = _DB

from _engine_harness import FakeEvent, clean_db, make_player  # noqa: E402
from _engine_harness import Main  # noqa: E402
from _engine_harness import db  # noqa: E402

passed = failed = 0
G, Q = 1095961596, "gm_t1307"


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"✅ {name}")
    else:
        failed += 1
        print(f"❌ {name} {detail}")


async def _cmd(m, handler, msg):
    """直接调用 handler（绕过 filter 正则，支持『商店 2』翻页）"""
    ev = FakeEvent(G, Q, msg)
    out = []
    async for r in getattr(m, handler)(ev):
        out.append(r)
    return str(out[0]) if out else ""


def _set(subarea, level=5, gold=10000):
    """落库橡木镇指定子区域的测试玩家（level 默认 5：老马 lv1/小毛驴 lv5 都能买）"""
    from _engine_harness import db
    make_player(G, Q, "坐骑测试", "战士", level=level)
    db.update_player(G, Q, cur_map="oak_town", cur_subarea=subarea, gold=gold)


async def _all_pages(m, maxpage=12):
    """循环翻页收集商店面板全部文本（v170 橡木铁匠铺扩品后条目变多，翻页上限放宽）"""
    out_all = []
    for page in range(1, maxpage + 1):
        out = await _cmd(m, "shop", "商店" if page == 1 else f"商店 {page}")
        out_all.append(out)
        mt = re.search(r"第 (\d+)/(\d+) 页", out or "")
        if not mt or int(mt.group(1)) >= int(mt.group(2)):
            break
    return "\n".join(out_all)


async def main():
    from _engine_harness import db
    m = Main()

    # ---- ① 草药铺 oak_town_5（herb）：无坐骑、无武器 ----
    clean_db()
    _set("oak_town_5")
    panel = await _all_pages(m)
    check("① 草药铺有药剂配货", "治疗药水(小)" in panel, panel[:150])
    check("① 草药铺无老马", "老马" not in panel, panel[:300])
    check("① 草药铺无小毛驴", "小毛驴" not in panel, panel[:300])
    check("① 草药铺无武器（铁剑回归）", "铁剑" not in panel, panel[:300])

    # ---- ② 酒馆 oak_town_4（tavern）：无坐骑、无武器 ----
    clean_db()
    _set("oak_town_4")
    panel = await _all_pages(m)
    check("② 酒馆无老马", "老马" not in panel, panel[:300])
    check("② 酒馆无小毛驴", "小毛驴" not in panel, panel[:300])
    check("② 酒馆无铁剑", "铁剑" not in panel, panel[:300])

    # ---- ③ 铁匠铺 oak_town_3（smith）：坐骑上线 + 武器正常 ----
    clean_db()
    _set("oak_town_3")
    panel = await _all_pages(m)
    check("③ 铁匠铺有老马条目", "老马（坐骑 Lv.1 商店直购）" in panel, panel[:400])
    check("③ 铁匠铺有小毛驴条目", "小毛驴（坐骑 Lv.5 商店直购）" in panel, panel[:400])
    check("③ 铁匠铺仍有武器", "铁剑" in panel, panel[:400])

    # ---- ④ 草药铺名称购买 → 拒绝 ----
    clean_db()
    _set("oak_town_5")
    r = await _cmd(m, "buy", "购买 老马")
    check("④ 草药铺拒绝买老马", "橡木镇的商人才能买到老马" in r, r[:150])

    # ---- ⑤ 草药铺序号购买（6 件药剂，第 7 号不存在 → 无坐骑追加；v152 补货微效/轻效后原 4→6 件）----
    r = await _cmd(m, "buy", "购买 7")
    check("⑤ 草药铺序号无坐骑", "没有第 7 号商品" in r, r[:150])

    # ---- ⑥ 酒馆名称购买 → 拒绝 ----
    clean_db()
    _set("oak_town_4")
    r = await _cmd(m, "buy", "购买 老马")
    check("⑥ 酒馆拒绝买老马", "橡木镇的商人才能买到老马" in r, r[:150])

    # ---- ⑦ 铁匠铺名称购买 → 成功 ----
    clean_db()
    _set("oak_town_3")
    r = await _cmd(m, "buy", "购买 老马")
    p = db.get_player(G, Q)
    owned = (p.get("mounts") or {}).get("owned") or []
    check("⑦ 铁匠铺买老马成功", "你买了老马" in r, r[:150])
    check("⑦ 金币 10000→9500", p["gold"] == 9500, f"gold={p['gold']}")
    check("⑦ owned 含 mount_horse", "mount_horse" in owned, str(owned))

    # ---- ⑧ 铁匠铺序号购买（翻页解析老马序号，验证序号链路 smith 放行）----
    clean_db()
    _set("oak_town_3")
    idx = None
    # v171 橡木铁匠铺扩品（+粗钢/林语 6 件）后共 44 件/9 页，坐骑在末页（43/44 号）
    for page in range(1, 10):
        out = await _cmd(m, "shop", "商店" if page == 1 else f"商店 {page}")
        for ln in (out or "").splitlines():
            mm = re.match(r"\s*(\d+)\.\s*.*老马", ln)
            if mm:
                idx = int(mm.group(1))
                break
        if idx:
            break
        mt = re.search(r"第 (\d+)/(\d+) 页", out or "")
        if not mt or int(mt.group(1)) >= int(mt.group(2)):
            break
    check("⑧ 铁匠铺面板存在老马序号", idx is not None, "未找到老马条目")
    if idx is not None:
        r = await _cmd(m, "buy", f"购买 {idx}")
        p = db.get_player(G, Q)
        owned = (p.get("mounts") or {}).get("owned") or []
        check("⑧ 序号购买老马成功", "你买了老马" in r and "mount_horse" in owned,
              f"{r[:120]} owned={owned}")

    # ---- ⑨ 小毛驴等级拦截不回归（lv=1 玩家，名称购买路径）----
    clean_db()
    _set("oak_town_3", level=1)
    r = await _cmd(m, "buy", "购买 小毛驴")
    p = db.get_player(G, Q)
    owned = (p.get("mounts") or {}).get("owned") or []
    check("⑨ 小毛驴等级拦截", "需要 Lv.5 才能骑乘" in r, r[:150])
    check("⑨ 未入 owned", "mount_donkey" not in owned, str(owned))

    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)


os_asy = __import__("asyncio")
os_asy.run(main())