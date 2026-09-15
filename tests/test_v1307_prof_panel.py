# -*- coding: utf-8 -*-
"""v130.7 意见#14 副业面板提示收敛固化测试

覆盖：
  ① 『副业』面板只剩 1 行提示类文字（tips profession 随机池行），3 条固定 💡 已收敛
  ② tips.py profession 随机池：条目 ≤20 字、无重复、3 条固定提示的关键信息已进池
  ③ 面板核心信息不回归：标题/已激活数/副业名/等级/经验条/总分
  ④ 『副业 排行』视图同样只 1 行提示
  ⑤ 多次刷新提示有随机性（12 次 ≥2 种）

运行：python tests/test_v1307_prof_panel.py（exit=0 全绿）
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_v1307_prof_panel.db")
os.environ["GWEN_GAME_DB"] = _DB

from _engine_harness import C, FakeEvent, clean_db, make_player  # noqa: E402
from _engine_harness import Main  # noqa: E402

# 声明驱动正则表（原 `game.commands._registry.COMMAND_REGEX` 的终态取件口：
# 声明真源 = 包内 `content/data/commands.json`，经驱动口装配为 `{key: 合并正则}`）。
# ★ 剔除私有键 `_maint_gate`（停服 gate 不是指令；旧 `_host_handler_finder` 显式跳过
#   `name.startswith("_")`）——理由见 test_v1304_use_batch.py 同段注释。
from _engine_harness import harness as _harness  # noqa: E402
COMMAND_REGEX = {k: rx.pattern for rx, k in _harness().declarations_for_static()
                 if not k.startswith("_")}

passed = failed = 0
G, Q = 1095961598, "gm_t1307prof"

# 3 条旧固定 💡 的独特关键词（收敛后不应再出现在面板）
FIXED_OLD = ("练满再选新的", "铁港城", "驯鹿缰绳")


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"✅ {name}")
    else:
        failed += 1
        print(f"❌ {name} {detail}")


def _tip_lines(text):
    """面板中的提示类行（提示统一 💡 前缀；profession 池全中文开头 → 必带 💡）"""
    return [ln for ln in text.split("\n") if ln.startswith("💡")]


async def _cmd(m, cmd):
    """注册表分发，Main 多继承环境（MRO 坑必须实测）

    ★ 终态驱动口（`_engine_harness.Main`）对**声明表命中**的 key 给 async generator、
    对包内实现类方法给 coroutine —— 两种都收（旧宿主壳统一是 async generator）。
    """
    ev = FakeEvent(G, Q, cmd)
    for key, pat in COMMAND_REGEX.items():
        if re.match(pat, cmd):
            fn = getattr(m, key, None)
            if fn:
                gen = fn(ev)
                out = []
                if hasattr(gen, "asend"):
                    async for r in gen:
                        out.append(r)
                else:
                    r = await gen
                    out = list(r) if isinstance(r, (list, tuple)) else ([r] if r else [])
                if out and isinstance(out[0], tuple):
                    return out[0][1]
                return str(out[0]) if out else ""
            return ""
    return ""


async def main():
    from _engine_harness import db
    m = Main()

    # ===== ② profession 池规则（test_v127_tips 兼容子集） =====
    pool = C.TIPS["profession"]
    check("② profession 池 ≥3 条", len(pool) >= 3, f"len={len(pool)}")
    over = [it for it in pool if len(it) > 20]
    check("② profession 池条目 ≤20 字", not over, f"超长={over}")
    dup = [x for x in set(pool) if pool.count(x) > 1]
    check("② profession 池无重复", not dup, f"重复={dup}")
    joined = "|".join(pool)
    # v167：profession 池更新（"每人限 2 条…"→"副业没有数量上限"），
    # 旧 v130.7 关键字『遗忘副业』不再在池内——换用『副业』+『拜师』双关键字验证信息进池
    for kw in ("副业", "拜师", "稀有"):
        check(f"② 固定提示信息已进池『{kw}』", kw in joined, joined)
    check("② profession 池无『限 2 条』旧口径", "限 2 条" not in joined and "每人限" not in joined, joined)
    check("② profession 池含无上限口径", "没有数量上限" in joined, joined)

    # ===== ① 面板收敛 + ③ 核心信息不回归 =====
    clean_db()
    make_player(G, Q, "提示收敛测试", "战士", level=3)
    db.activate_prof(G, Q, "gather")  # 激活采集 → Lv.1

    r0 = await _cmd(m, "副业")
    check("③ 面板标题+已激活数(无分母)", "🧵 【副业面板】" in r0 and "(当前已激活 1 条)" in r0, r0[:120])
    check("③ 副业名/等级/经验条显示", "采集" in r0 and "Lv.1" in r0 and "经验" in r0, r0[:200])
    check("③ 副业总分行", "📊 副业总分：1" in r0, r0[:200])
    for kw in FIXED_OLD:
        check(f"① 面板无固定文案『{kw}』", kw not in r0, r0[:300])

    seen = set()
    for _ in range(12):
        r = await _cmd(m, "副业")
        tips = _tip_lines(r)
        check("① 面板只 1 行提示类文字", len(tips) == 1, f"行数={len(tips)} tip={tips} 输出={r[:200]!r}")
        t = tips[0]
        check("① 提示是 profession 池内条目", t[2:] in pool, f"got={t!r}")
        seen.add(t)
    check("⑤ 提示有随机性（12 次 ≥2 种）", len(seen) >= 2, f"seen={len(seen)}")

    # ===== ④ 排行视图同样只 1 行提示 =====
    rr = await _cmd(m, "副业 排行")
    check("④ 排行标题", "🏆 【副业排行】" in rr, rr[:120])
    tips_r = _tip_lines(rr)
    check("④ 排行只 1 行提示", len(tips_r) == 1, f"tips={tips_r}")

    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)


os_asy = __import__("asyncio")
os_asy.run(main())