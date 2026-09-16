# -*- coding: utf-8 -*-
"""门禁：『gm_重载』资料表热重载 —— 幂等 / 改盘真生效 / 坏数据 fail-closed / 非 GM 被拦。

**为什么要有这个文件**：热重载最危险的失败态不是报错，是**假绿** ——
命令回报「重载完成」，但命令层读到的还是旧值（包内模块级**派生缓存**没跟着重建）。
所以本门禁不比回报文案，比「**重载后命令层读出什么**」与磁盘是否一致：

  1. 无改动 → 报「无变化」、值不变
  2. **改盘但不重载** → 读到的仍是旧值（证明变化只可能来自重载，而不是别的东西顺带刷了）
  3. **重载** → 命令层读到新值（★ 端到端：这才是本命令存在的意义）
  4. 幂等：连续再重载 → 无变化、值稳定、注册面不变
  5. 坏数据 → fail-closed 点名域，**旧数据仍可读**（不清空、不静默降级）
  6. 非 GM → 被 `guards=("hook:gm",)` 拦在 handler 之前
  7. `gm_帮助` 收录了新指令

改盘用 `effect_rules` 域（85 条、规则表），**无论成败都在 `finally` 里按原字节还原**。
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import db, clean_db, Main, FakeEvent, run  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(HERE)
RULES_JSON = os.path.join(PKG_ROOT, "content", "rules", "effect_rules.json")
GM, NON_GM = "1454832774", "999999999"
KEY = "affix_bleed"

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {str(detail)[:300]}")


async def cmd(m, handler_name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    results = await run(getattr(m, handler_name), ev)
    return results[-1] if results else ""


def _write_rules(doc):
    with io.open(RULES_JSON, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")


async def main():
    clean_db()
    m = Main(None)
    db.set_event_state("gm_whitelist", json.dumps([GM], ensure_ascii=False))

    import content.catalog_rules as CR

    try:
        from content import command_handlers as _handlers
    except Exception:                                        # noqa: BLE001
        _handlers = None

    orig = io.open(RULES_JSON, "rb").read()
    try:
        print("【1. 基线：磁盘未改动 → 报『无变化』且值不变】")
        base = CR.EFFECT_RULES[KEY]["cap"]
        out = await cmd(m, "gm_reload", "g1", GM, "gm_重载")
        check("回报含『重载完成』", "重载完成" in out, out[:200])
        check("无改动时报『无变化』", "无变化" in out, out[:200])
        check("值不变", CR.EFFECT_RULES[KEY]["cap"] == base, CR.EFFECT_RULES[KEY])

        print("【2. 改盘但不重载 → 命令层读到的仍是旧值】")
        doc = json.loads(orig.decode("utf-8"))
        doc[KEY]["cap"] = base + 7
        _write_rules(doc)
        check("改盘不重载：仍是旧值（证明变化只来自重载）",
              CR.EFFECT_RULES[KEY]["cap"] == base, CR.EFFECT_RULES[KEY])

        print("【3. ★ 重载 → 命令层读到新值（端到端）】")
        out = await cmd(m, "gm_reload", "g1", GM, "gm_重载")
        # 报告按**条数**列变化（值改动不改条数 ⇒ 不进「有变化的表」），故这里只验它给出汇总口径
        check("回报给出表数/集合数汇总", "张表" in out and "个集合" in out, out[:300])
        check("★ 派生缓存跟着刷新（读到新值）",
              CR.EFFECT_RULES[KEY]["cap"] == base + 7, CR.EFFECT_RULES[KEY])

        print("【4. 幂等：再重载一次 → 无变化、值稳定、注册面不变】")
        n0 = len(_handlers()) if _handlers else None
        out = await cmd(m, "gm_reload", "g1", GM, "gm_重载")
        check("第二次报『无变化』", "无变化" in out, out[:200])
        check("值稳定", CR.EFFECT_RULES[KEY]["cap"] == base + 7, CR.EFFECT_RULES[KEY])
        if _handlers:
            check("注册面不变（无重复登记）", len(_handlers()) == n0, (n0, len(_handlers())))

        print("【5. 坏数据 → fail-closed 点名，且旧数据仍可读】")
        with io.open(RULES_JSON, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("{ 这不是合法 JSON")
        out = await cmd(m, "gm_reload", "g1", GM, "gm_重载")
        check("回报失败且点名域", "❌" in out and "effect_rules" in out, out[:300])
        check("旧数据仍可读（没被清空/静默降级）",
              CR.EFFECT_RULES[KEY]["cap"] == base + 7, CR.EFFECT_RULES[KEY])

        print("【6. 非 GM 身份 → 守卫拦在 handler 之前】")
        out = await cmd(m, "gm_reload", "g1", NON_GM, "gm_重载")
        check("非 GM 拿不到重载结果", "重载完成" not in out, out[:200])

        print("【7. gm_帮助 收录新指令】")
        out = await cmd(m, "gm_help", "g1", GM, "gm_帮助")
        check("帮助含 gm_重载", "gm_重载" in out, out[:200])
    finally:
        with io.open(RULES_JSON, "wb") as fh:                 # 原字节还原
            fh.write(orig)
        try:
            await cmd(m, "gm_reload", "g1", GM, "gm_重载")
        except Exception:                                    # noqa: BLE001
            pass

    print(f"\n结果：{passed} 通过 / {failed} 失败")
    return 1 if failed else 0


if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(main()))
