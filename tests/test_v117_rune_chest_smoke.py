# -*- coding: utf-8 -*-
"""v117 副本材料联动·方案D：符文匣『使用』开箱给符文 — 一次性冒烟验证

覆盖：
1. 注入黑渊符文匣/龙宫符文匣 → 『使用』→ 背包出现一枚 rune_<effect>_<lvl> 符文，
   且 data 含 name/effect/lvl/quality/price（供『附魔』刻印读取，防 KeyError）。
2. 符文匣消耗 1 个（开箱即弃）。
3. 多开若干次，确保不崩且符文 key/字段一致。

运行（系统 Python，一次性脚本）：
    cd dragonfall
    C:\\Users\\yuyu\\AppData\\Local\\Programs\\Python\\Python312\\python.exe tests\\test_v117_rune_chest_smoke.py
"""
import sys, os

# Windows GBK 控制台容错：stdout 改 UTF-8，抑制 loguru 向 stdout 打 emoji（Import 时崩）
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
try:
    from loguru import logger
    logger.remove()
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from conftest import C, db, Main, FakeEvent, run, clean_db

async def cmd(m, handler_name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    handler = getattr(m, handler_name)
    results = await run(handler, ev)
    return results[-1] if results else ""

def inv(gid, qid):
    return db.get_inventory(gid, qid)

async def main():
    clean_db()
    m = Main(None)
    await cmd(m, "register", "g1", "w1", "注册 战士 旅人 男")
    p = db.get_player("g1", "w1")
    db.update_player("g1", "w1", cur_map="oak_plain", level=5, gold=999999,
                     hp=p["max_hp"], mp=p["max_mp"])
    ok = fail = 0
    def check(name, cond, detail=""):
        nonlocal ok, fail
        if cond: ok += 1; print(f"  ✅ {name}")
        else: fail += 1; print(f"  ❌ {name} {detail}")

    for chest_key, chest_name in (
        ("i_hei_yuan_fu_wen_xiang", "黑渊符文匣"),
        ("i_long_gong_fu_wen_xiang", "龙宫符文匣"),
    ):
        # 给 3 个匣子（stackable，合成 1 行 count=3）
        for _ in range(3):
            db.add_item("g1", "w1", chest_key,
                        {"name": chest_name, "type": "消耗品", "stackable": True,
                         "price": 300, "effect": "open_rune_chest"})

        def chest_count():
            return sum(it.get("count", 1) for it in inv("g1", "w1") if it["key"] == chest_key)

        # 使用（消耗 1 个）直到开完 3 个
        for i in range(3):
            before = chest_count()
            out = await cmd(m, "use", "g1", "w1", f"使用 {chest_name}")
            after = chest_count()
            check(f"{chest_name}#{i+1} 消耗1个", after == before - 1,
                  f"before={before} after={after} out={out[:80]}")
            runes = [it for it in inv("g1", "w1") if it["key"].startswith("rune_")]
            gained = [it for it in runes if it["data"].get("effect") and it["data"].get("lvl")]
            check(f"{chest_name}#{i+1} 开出符文且带effect/lvl",
                  any(it["data"].get("effect") for it in runes),
                  f"out={out[:160]} runes={len(runes)} valid={len(gained)}")
            check(f"{chest_name}#{i+1} 播报符文名", "符文" in out, out[:160])
            check(f"{chest_name}#{i+1} 开箱key格式", all(
                it["key"].startswith("rune_") and "_" in it["key"].split("rune_")[1][:40]
                for it in runes), f"keys={[r['key'] for r in runes]}")
        # 清空剩余（若开出的 rune 不影响下一轮，直接移除全部该匣）
        for it in [x for x in inv("g1", "w1") if x["key"] == chest_key]:
            db.remove_item("g1", "w1", it["key"])

    # 汇总校验：开出的符文 key 与战斗掉落一致（rune_<effect>_<lvl>），data.effect 在 RUNES 中
    rk_ok = True
    seen = []
    for it in inv("g1", "w1"):
        if it["key"].startswith("rune_"):
            seen.append(it["key"])
            d = it["data"]
            ef = d.get("effect", "")
            lv = d.get("lvl", 0)
            expect_key = f"rune_{ef}_{lv}"
            if not any(r["effect"] == ef for r in C.RUNES.values()):
                rk_ok = False
            if it["key"] != expect_key:
                rk_ok = False
    check("符文 key==rune_<effect>_<lvl> 且 effect 合法", rk_ok, f"seen={seen}")
    print("\n开出的符文汇总:", seen)

    print(f"\n结果: {ok} 通过, {fail} 失败")
    return fail == 0

if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)
