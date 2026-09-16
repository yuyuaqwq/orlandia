# -*- coding: utf-8 -*-
"""v123 列表翻页快捷键 + 快捷指令后缀 正式测试。

需求（2026-08-16 鱼鱼）：『发送 + 或 +n 向后 1/n 页；- 类似；= 直接跳转指定页；
快捷指令支持附带后缀（绑定 n→前往，n1=前往 1）』

覆盖清单：
  1. 翻页基础：last_list 状态 page=2 → '+2' 转发『背包 4』（_run_shortcut 重建指令）
  2. 越界 clamp：'+5' 超上界 → 5；'-' 越下界 → 1；'-5' → 1；'=0'/'=99' 同理
  3. 『=』跳页：'=4' → 第 4 页
  4. 全角等价：'＋2'/'－'/'＝3'/'＋'/'+０' 与半角行为一致
  5. 无状态：没写过 last_list 发 '+' → 提示『先打开一个列表』，不转发
  6. 『=』无数字 → 提示跳页用法，不转发
  7. 快捷后缀（v123b）：字母前缀透传（绑『n→前往』发『n3』=前往 3，大写归一）；数字全量不拆（绑『13』发『13』触发，绑『1』发『14』静默）；gm_/help 保护
  8. 字母最长前缀：绑『goto→技能』『goto3』→『技能 3』不误拆『g』
  9. 列表接入冒烟：『背包』渲染后 last_list cmd='背包'；'+' 真实翻页；绑『1→背包』发『13』
     端到端到第 3 页；『技能列表』免空格不回归且记录状态
 10. 守卫：无角色发 '+' → 注册提示（require_player）

转发文本断言用实例级替换 _run_shortcut 捕获（白盒，精确验证重建指令文本）；
另配真实转发端到端（背包渲染页码）验证整链路。

环境铁律：私有库 tests/test_v123_page_flip.db（绝不碰生产库），*.db 已 gitignore。

运行：python tests/test_v123_page_flip.py（exit=0 通过）
"""
import json
import os
import sys

os.environ["GWEN_GAME_DB"] = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "test_v123_page_flip.db")
os.environ["GWEN_TEST_MODE"] = "1"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import db, FakeEvent, run, clean_db, make_player  # noqa: E402
from _engine_harness import Main  # noqa: E402
from _engine_harness import harness as _harness  # noqa: E402

# ★ 终态驱动口的静态表口径修正（**待主线修 `_engine_harness.py`**）：
# `HostShell._build_static_handlers()` 直接取包内声明表全文（`content/data/commands.json`
# 按字母序），于是**平台停服 gate** `_maint_gate` 落在第 0 位 —— 它的正则只有 At 前缀、
# 无 `$` 锚定（设计上匹配一切消息），在 `saintess_engine.command.router.find_static`
# 「首个命中即返回」的口径下把**全部指令**都吃掉了（`_run_shortcut` 静默返回空）。
# 旧宿主 `_host_handler_finder` 是按 `name.startswith("_")` **显式跳过**私有 handler 的
# （见 `game/commands/base.py:163`），测试侧的静态表兜底也应同口径。
# 本文件按同一口径把私有键从静态表剔除（命令面一字未减：195 键 → 193 键，只少 gate）。
def _static_without_private():
    return [(rx, k) for rx, k in _harness().declarations_for_static()
            if not k.startswith("_")]


Main._static_source = staticmethod(_static_without_private)

passed = failed = 0

GID, QID = "g1", "q1"


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")


# ---------- 通用夹具 ----------
def seed_bag(n=17):
    """17 件材料 → 背包 2 页（每页 10 件，第 2 页有 7 件，v127.2）。"""
    for i in range(1, n + 1):
        db.add_item(GID, QID, f"mat_t{i}",
                    {"name": f"测试材料{i}", "type": "材料", "stackable": False})


def set_last_list(cmd="背包", page=2, pages=5):
    db.set_event_state(f"last_list_{QID}",
                       json.dumps({"cmd": cmd, "page": page, "pages": pages},
                                  ensure_ascii=False))


async def flip(m, text):
    """跑 page_flip：实例级替换 _run_shortcut 捕获转发文本。

    返回 (回复列表, 转发文本列表)。替换在 finally 恢复，不污染后续端到端测试。
    """
    captured = []

    async def fake_run_shortcut(event, cmd_text):
        captured.append(cmd_text)
        yield None

    orig = m._run_shortcut
    m._run_shortcut = fake_run_shortcut
    try:
        ev = FakeEvent(GID, QID, text)
        replies = [r for r in await run(m.page_flip, ev) if r is not None]
    finally:
        m._run_shortcut = orig
    return replies, captured


async def shortcut_capture(m, text, shortcuts):
    """跑 shortcut_trigger：捕获转发文本（同上替换法）。"""
    db.update_player(GID, QID, shortcuts=shortcuts)
    captured = []

    async def fake_run_shortcut(event, cmd_text):
        captured.append(cmd_text)
        yield None

    orig = m._run_shortcut
    m._run_shortcut = fake_run_shortcut
    try:
        ev = FakeEvent(GID, QID, text)
        replies = [r for r in await run(m.shortcut_trigger, ev) if r is not None]
    finally:
        m._run_shortcut = orig
    return replies, captured


# ---------- 1. 翻页基础 ----------
async def test_flip_basic_forward(m):
    print("【1. 翻页基础：+ / +n 转发页码正确】")
    clean_db()
    make_player(GID, QID)
    seed_bag()
    cases = [
        ("+2", "背包 4"),   # page 2 → 4
        ("+", "背包 3"),    # 无数字 → +1
        ("+1", "背包 3"),
        ("-1", "背包 1"),
        ("＋2", "背包 4"),  # 全角
        ("+０", "背包 2"),  # 全角 0 → 原地
    ]
    for msg, expect in cases:
        set_last_list()
        _, captured = await flip(m, msg)
        check(f"『{msg}』→ 转发『{expect}』（实际 {captured}）",
              captured == [expect], str(captured))
    # At 前缀兼容
    set_last_list()
    _, captured = await flip(m, "[At:123] +2")
    check("『[At:123] +2』→ 转发『背包 4』", captured == ["背包 4"], str(captured))


# ---------- 2. 越界 clamp ----------
async def test_flip_clamp(m):
    print("【2. 越界 clamp：[1, pages]】")
    clean_db()
    make_player(GID, QID)
    seed_bag()
    set_last_list(page=4, pages=5)
    _, c = await flip(m, "+5")
    check("page=4 '+5' → clamp 上界 5", c == ["背包 5"], str(c))
    _, c = await flip(m, "-")
    check("page=4 '-' → 正常回 3（未越界）", c == ["背包 3"], str(c))
    _, c = await flip(m, "-5")
    check("page=4 '-5' → clamp 下界 1", c == ["背包 1"], str(c))
    set_last_list(page=1, pages=5)
    _, c = await flip(m, "-")
    check("page=1 '-' → clamp 下界 1", c == ["背包 1"], str(c))
    _, c = await flip(m, "=0")
    check("'=0' → clamp 1", c == ["背包 1"], str(c))
    _, c = await flip(m, "=99")
    check("'=99' → clamp 5", c == ["背包 5"], str(c))


# ---------- 3. 『=』跳页 ----------
async def test_flip_jump(m):
    print("【3. 『=』跳页】")
    clean_db()
    make_player(GID, QID)
    seed_bag()
    set_last_list(page=1, pages=5)
    for msg, expect in [("=4", "背包 4"), ("＝3", "背包 3"), ("=5", "背包 5")]:
        _, captured = await flip(m, msg)
        check(f"『{msg}』→ 转发『{expect}』", captured == [expect], str(captured))


# ---------- 4. 全角等价 ----------
async def test_flip_fullwidth(m):
    print("【4. 全角 ＋－＝ 等价半角】")
    clean_db()
    make_player(GID, QID)
    seed_bag()
    cases = [
        ("＋", "背包 3"),   # 全角 + → +1
        ("＋2", "背包 4"),
        ("－", "背包 1"),   # 全角 - → -1
        ("＝3", "背包 3"),  # 全角 = 跳页
    ]
    for msg, expect in cases:
        set_last_list()
        _, captured = await flip(m, msg)
        check(f"『{msg}』→ 转发『{expect}』", captured == [expect], str(captured))


# ---------- 5/6. 无状态 / 『=』无数字 ----------
async def test_flip_no_state(m):
    print("【5/6. 无状态提示 / 『=』无数字提示 / 无角色守卫】")
    clean_db()
    make_player(GID, QID)
    replies, captured = await flip(m, "+")
    check("无状态 '+' → 提示『先打开一个列表』",
          len(replies) == 1 and "先打开一个列表" in replies[0], str(replies))
    check("无状态 '+' 不转发", captured == [], str(captured))
    replies, captured = await flip(m, "=")
    check("『=』无数字 → 跳页用法提示",
          len(replies) == 1 and "跳页用法" in replies[0], str(replies))
    check("『=』无数字不转发", captured == [], str(captured))
    # 无玩家：v127.4 静默放行（未注册用户无列表可翻，不再弹"注册"提示；如蚕蛹反馈）
    clean_db()
    replies, captured = await flip(m, "+")
    check("无角色 '+' → 静默放行（不再弹注册提示）",
          replies == [] and captured == [], str(replies))


# ---------- 7. 快捷后缀（v123b：数字全量不拆 / 字母前缀透传） ----------
async def test_shortcut_suffix(m):
    print("【7. 快捷后缀：字母前缀透传（绑『n→前往』『n3』=前往 3）；数字全量不拆】")
    clean_db()
    make_player(GID, QID)
    # 字母前缀：n → 前往
    shortcuts = {"n": "前往"}
    cases = [
        ("n3", ["前往 3"]),
        ("n", ["前往"]),        # 无后缀原样触发
        ("n12", ["前往 12"]),   # 任意剩余并入后缀
        ("N3", ["前往 3"]),     # 大写归一
        ("n3 ", ["前往 3"]),    # 尾随空格
    ]
    for msg, expect in cases:
        _, captured = await shortcut_capture(m, msg, shortcuts)
        check(f"绑『n→前往』发『{msg}』→ 转发 {expect}", captured == expect, str(captured))
    # 数字全量：绑『13』发『13』触发；绑『1』发『14』→ 静默（不拆后缀）
    shortcuts2 = {"13": "技能", "1": "前往"}
    cases2 = [
        ("13", ["技能"]),
        ("１３", ["技能"]),    # 全角整段归一
        ("1", ["前往"]),
    ]
    for msg, expect in cases2:
        _, captured = await shortcut_capture(m, msg, shortcuts2)
        check(f"绑『13/1』发『{msg}』→ 转发 {expect}", captured == expect, str(captured))
    replies, captured = await shortcut_capture(m, "14", {"1": "前往"})
    check("数字不拆后缀：绑『1』发『14』→ 静默", captured == [] and replies == [], f"{captured} {replies}")
    # 未绑定 → 静默（不转发不回复）
    replies, captured = await shortcut_capture(m, "99", shortcuts)
    check("未绑定『99』→ 无转发无回复", captured == [] and replies == [], f"{captured} {replies}")
    # 内置英文指令保护：gm_ 系列 / help 不进快捷
    replies, captured = await shortcut_capture(m, "gm_发金币", {"g": "前往"})
    check("『gm_发金币』不进快捷（gm_ 保护）", captured == [] and replies == [], f"{captured} {replies}")
    replies, captured = await shortcut_capture(m, "help", {"h": "前往"})
    check("『help』不进快捷（help 保护）", captured == [] and replies == [], f"{captured} {replies}")
    # v123c 符号键：单字符符号/中文前缀+后缀透传；翻页符号/At/斜杠被排除
    shortcuts3 = {".": "攻击", "!": "探索"}
    cases3 = [
        (".3", ["攻击 3"]),
        (".", ["攻击"]),
        ("!2", ["探索 2"]),
        ("! ", ["探索"]),       # 尾随空格
    ]
    for msg, expect in cases3:
        _, captured = await shortcut_capture(m, msg, shortcuts3)
        check(f"绑『. / !』发『{msg}』→ 转发 {expect}", captured == expect, str(captured))
    replies, captured = await shortcut_capture(m, "+2", {"+": "攻击"})
    check("『+2』不进快捷（翻页符号保护）", captured == [] and replies == [], f"{captured} {replies}")
    replies, captured = await shortcut_capture(m, "=3", {"=": "攻击"})
    check("『=3』不进快捷（翻页符号保护）", captured == [] and replies == [], f"{captured} {replies}")


# ---------- 8. 字母最长前缀优先 ----------
async def test_shortcut_full_match_first(m):
    print("【8. 字母最长前缀：绑『goto→技能,n→前往』，『goto3』→『技能 3』不误拆『g』】")
    clean_db()
    make_player(GID, QID)
    shortcuts = {"goto": "技能", "n": "前往"}
    cases = [
        ("goto3", ["技能 3"]),   # 最长前缀命中 goto，剩 3 入后缀
        ("goto", ["技能"]),
        ("GOTO3", ["技能 3"]),   # 大写归一
        ("n5", ["前往 5"]),
        ("n", ["前往"]),
        ("x1", []),              # 未绑定 → 静默
    ]
    for msg, expect in cases:
        _, captured = await shortcut_capture(m, msg, shortcuts)
        check(f"发『{msg}』→ 转发 {expect}", captured == expect, str(captured))


# ---------- 9. 端到端（真实转发链路） ----------
async def test_e2e_page_flip(m):
    print("【9a. 端到端：'+2' → 真实背包第 2 页渲染（越界 clamp）】")
    clean_db()
    make_player(GID, QID)
    seed_bag()
    set_last_list()
    ev = FakeEvent(GID, QID, "+2")
    replies = [r for r in await run(m.page_flip, ev) if r is not None]
    joined = "\n".join(replies)
    check("回复含『第 2/2 页』", "第 2/2 页" in joined, joined[:200])
    check("回复含第 2 页物品『测试材料16』", "测试材料16" in joined, joined[:200])
    check("回复含『共 17 件』", "共 17 件" in joined, joined[:200])


async def test_list_state_smoke(m):
    print("【9b. 列表接入冒烟：『背包』记录 last_list + 『+』真实翻页】")
    clean_db()
    make_player(GID, QID)
    seed_bag()
    ev = FakeEvent(GID, QID, "背包")
    replies = [r for r in await run(m.inventory, ev) if r is not None]
    joined = "\n".join(replies)
    check("『背包』渲染第 1 页", "第 1/2 页" in joined, joined[:120])
    st = json.loads(db.get_event_state(f"last_list_{QID}") or "{}")
    check("last_list cmd='背包'", st.get("cmd") == "背包", str(st))
    check("last_list page=1 pages=2",
          st.get("page") == 1 and st.get("pages") == 2, str(st))
    ev = FakeEvent(GID, QID, "+")
    replies = [r for r in await run(m.page_flip, ev) if r is not None]
    joined = "\n".join(replies)
    check("『+』→ 第 2/2 页", "第 2/2 页" in joined, joined[:200])
    st = json.loads(db.get_event_state(f"last_list_{QID}") or "{}")
    check("翻页后 last_list page=2", st.get("page") == 2, str(st))


async def test_shortcut_suffix_e2e(m):
    print("【9c. 端到端：绑『n→背包』发『n3』→ 真实背包第 3 页渲染】")
    clean_db()
    make_player(GID, QID)
    seed_bag()
    db.update_player(GID, QID, shortcuts={"n": "背包"})
    ev = FakeEvent(GID, QID, "n3")
    replies = [r for r in await run(m.shortcut_trigger, ev) if r is not None]
    joined = "\n".join(replies)
    check("『n3』→ 背包第 3 页(越界clamp到2)", "第 2/2 页" in joined, joined[:200])
    ev = FakeEvent(GID, QID, "n")
    replies = [r for r in await run(m.shortcut_trigger, ev) if r is not None]
    joined = "\n".join(replies)
    check("『n』→ 背包第 1 页", "第 1/2 页" in joined, joined[:200])


# ---------- 10. 免空格不回归 ----------
async def test_skill_list_no_space(m):
    print("【10. 免空格不回归：『技能列表』正常显示并记录状态】")
    clean_db()
    make_player(GID, QID)
    ev = FakeEvent(GID, QID, "技能列表")
    replies = [r for r in await run(m.skill, ev) if r is not None]
    joined = "\n".join(replies)
    check("『技能列表』渲染含『页数：1/』", "页数：1/" in joined, joined[:120])
    st = json.loads(db.get_event_state(f"last_list_{QID}") or "{}")
    check("last_list cmd='技能列表'", st.get("cmd") == "技能列表", str(st))


async def main():
    m = Main(None)
    await test_flip_basic_forward(m)
    await test_flip_clamp(m)
    await test_flip_jump(m)
    await test_flip_fullwidth(m)
    await test_flip_no_state(m)
    await test_shortcut_suffix(m)
    await test_shortcut_full_match_first(m)
    await test_e2e_page_flip(m)
    await test_list_state_smoke(m)
    await test_shortcut_suffix_e2e(m)
    await test_skill_list_no_space(m)
    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0


if __name__ == "__main__":
    import asyncio
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
