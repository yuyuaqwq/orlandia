# -*- coding: utf-8 -*-
"""v98.3 注册表扩展性验收：注册新条件/格式器 = 零改动分发骨架

验证四个新注册表（dialogue_conds/title_conds/race_talent_display/hidden_cond）：
1. 注册新条件后，check_need/_earned_titles 等分发骨架立即生效
2. 未知 key 的安全降级（对话条件放行 / 称号不获得 / 天赋不显示 / 隐藏怪按 any）
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db, Main, FakeEvent, run, clean_db

async def cmd(m, handler_name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    handler = getattr(m, handler_name)
    results = await run(handler, ev)
    return results[-1] if results else ""

async def main():
    clean_db()
    m = Main(None)
    ok = fail = 0
    def check(name, cond, detail=""):
        nonlocal ok, fail
        if cond: ok += 1; print(f"  ✅ {name}")
        else: fail += 1; print(f"  ❌ {name} {detail}")

    def _raises_valueerror(fn, *args):
        try:
            fn(*args)
            return False
        except ValueError:
            return True

    from content import dialogue_conds as DC  # ★ B18-REPOINT：直取包内实现本体（宿主同名壳不再被测试引用）
    from content import title_conds as TC
    from content import race_talent_display as RTD
    from content import hidden_cond as HC

    # ---- 1. dialogue_conds：注册新条件立即生效 ----
    DC.register("always_true")(lambda ctx, v: True)
    DC.register("never_true")(lambda ctx, v: False)
    check("注册后 check_need 立即识别新条件",
          DC.CONDITIONS["always_true"]({}, None) and not DC.CONDITIONS["never_true"]({}, None), "")
    from content.dialogue import check_need
    check("check_need 走注册表(新条件 true 放行)", check_need({"always_true": 1}, {}), "")
    check("check_need 走注册表(新条件 false 拦截)", not check_need({"never_true": 1}, {}), "")
    check("未知条件键测试环境告警(v104 改)", _raises_valueerror(check_need, {"future_key_xx": 1}, {}), "")

    # ---- 2. title_conds：注册新称号条件 ----
    TC.register("test_title_99")(lambda ctx: ctx._focus.get("level", 0) >= 99)
    tctx = TC.TitleCtx("g1", "w1", {"level": 50}, {}, {}, {})
    check("title 注册表直接调用", TC.CONDITIONS["test_title_99"](tctx) is False, "")
    tctx2 = TC.TitleCtx("g1", "w1", {"level": 100}, {}, {}, {})
    check("title 注册表条件判定正确", TC.CONDITIONS["test_title_99"](tctx2) is True, "")
    # _earned_titles 走注册表（数据里没有 test_title_99，不崩 + 未知 id 安全降级 False）
    await cmd(m, "register", "g1", "w1", "注册 战士 旅人 男")
    earned = m.economy_cmds._earned_titles("g1", "w1", db.get_player("g1", "w1")) if hasattr(m, "economy_cmds") else None
    # Main 聚合后直接找方法
    if earned is None:
        # 直接实例化 EconomyCmds 太重，改用 title 注册表 + titles 数据一致性检查
        check("TITLES 所有 id 都有条件函数或 pro_ 前缀", all(
            t["id"] in TC.CONDITIONS or t["id"].startswith("pro_") for t in C.TITLES), "")

    # ---- 3. race_talent_display：未知 key 不显示 ----
    check("未知天赋 key 返回 None(不显示)", RTD.format_talent("future_trait", 0.5, "未来天赋") is None, "")
    check("已知天赋格式化正常", "+10%" in RTD.format_talent("hp_mult", 1.1, "强健")
          and "强健" in RTD.format_talent("hp_mult", 1.1, "强健"), "")

    # ---- 4. hidden_cond：注册新环境 + 关键词扩展 ----
    HC.ENV_KEYWORDS["test_env"] = ("testenv",)
    HC.register("test_env_only")(lambda ctx: ctx.env("test_env"))
    check("新环境关键词生效", HC.envs_of("xx_testenv_yy")["test_env"] is True, "")
    ctx_env = HC.HiddenCtx("xx_testenv_yy", {}, False, HC.envs_of("xx_testenv_yy"))
    check("新 cond 注册生效", HC.check_cond("test_env_only", ctx_env) is True, "")
    ctx_no = HC.HiddenCtx("oak_plain", {}, False, HC.envs_of("oak_plain"))
    check("新 cond 未命中返回 False", HC.check_cond("test_env_only", ctx_no) is False, "")
    check("未知 cond 按 any 处理", HC.check_cond("future_cond_xx", ctx_no) is True, "")

    # ---- 5. 既有条件全覆盖检查（防漏注册）----
    # dialogue 数据里用到的 need key 必须全部在注册表
    used_need_keys = set()
    for nid, npc in (C.NPCS or {}).items():
        dlg = npc.get("dialogue") if isinstance(npc, dict) else None
    # 直接扫数据文件里 need dict 的 key
    # ★ P5D-REPOINT：包侧聚合门面 `C` 没有 `__file__`（它是 `content.facade._Aggregate` 句柄，
    #   不是模块）⇒ 数据目录锚点改用**真源包根**（`content` 是命名空间包：`__file__` 为 None，
    #   用 `__path__[0]`；原语义 = 内容层数据目录 `content/data/`）。
    import re
    import content as _content_pkg
    _data_dir = os.path.join(list(_content_pkg.__path__)[0], "data")
    for fname in ("npcs.py", "dialogues.py"):
        fpath = os.path.join(_data_dir, fname)
        if os.path.exists(fpath):
            src = open(fpath, encoding="utf-8").read()
            for mm in re.finditer(r'"need"\s*:\s*\{([^}]*)\}', src):
                # 只匹配顶层 key（排除 evolve_ready 等 dict 值内部的字段）
                for km in re.finditer(r'"([a-z_]+)"\s*:\s*(?!\{)', mm.group(1)):
                    used_need_keys.add(km.group(1))
    # tier/level 是 evolve_ready 条件值内部的字段（非顶层 need key），正则限制排除
    missing = sorted((used_need_keys - {"tier", "level"}) - set(DC.CONDITIONS.keys()))
    check(f"对话数据 need key 全部注册 (共 {len(used_need_keys)})", not missing, f"缺: {missing}")

    # hidden cond 全部注册
    hconds = {h.get("cond", "any") for h in C.HIDDEN_MONSTERS.values()}
    missing_h = sorted(hconds - set(HC.CONDITIONS.keys()))
    check(f"隐藏怪 cond 全部注册 (共 {len(hconds)})", not missing_h, f"缺: {missing_h}")

    # title id 全部注册（或 pro_ 前缀）
    tids = {t["id"] for t in C.TITLES}
    missing_t = sorted(t for t in tids if t not in TC.CONDITIONS and not t.startswith("pro_"))
    check(f"称号 id 全部注册 (共 {len(tids)})", not missing_t, f"缺: {missing_t}")

    print(f"\n结果: {ok} 通过, {fail} 失败")
    return fail == 0

if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)