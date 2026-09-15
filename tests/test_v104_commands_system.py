# -*- coding: utf-8 -*-
"""v104 命令/系统修复回归（M24 命令框架 + GM/停服/注销/意见 系统）

9 组断言（对应 v104 审计 M24 与相关模块修复项）：
1. 双 handler 单回复：『副业任务』『转职重置』『烹饪列表』『副本地图』
   → 模拟 AstrBot 分发（全量正则匹配 + priority 排序）后各只回 1 条结果
2. GM 白名单默认拒绝：清空白名单 + 无 GWEN_GM_QQ → gm_发金币 被拒；
   白名单(库/环境变量)命中 → 放行
3. gm_伤害 无 require_player：无角色 GM 发 gm_伤害 → 不被 REGISTER_HINT 拦
   （静态：gm.py 无 require_player；行为：倍率设置成功）
4. 移动别名：『移动 1』与『前往 1』等价（同起点 → 同回复、同落点）
5. 停服 gate：停服时『物品 2』『周围』『离开副本』被 _GameCmdFilter 命中
   并被 _maint_gate 拦截（registry 键补全生效）；日常聊天不误拦；GM 放行
6. 命令矩阵：全部注册正则两两无冲突（代表输入断言恰好 1 命中，
   复用 test_v87_command_matrix.py 数据集）
7. 帮助补全：CMD_HELP 系含 v104 新增指令（编年史/移动/转职重置/副本地图等）
8. 注销清理：注销后 event_state 按键后缀 0 残留、props_use/pet_dex 清空，
   重注册不串模式状态（del_confirm 亦失效）
9. feedback reply：get_feedback 返回行含 reply 字段（v104 补列回归）

运行：python tests/test_v104_commands_system.py（exit=0 通过）
"""
import ast
import json
import os
import re
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db, Main, FakeEvent, run, clean_db  # noqa: E402

passed = failed = 0
findings = []  # 发现的真实问题（不阻断 exit=0，写入报告）


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")


def finding(name, detail=""):
    findings.append(f"{name} {detail}".strip())
    print(f"  ⚠️ FINDING: {name} {detail}")


# ---------- AST 扫描 @filter.regex（与 test_v87_command_matrix.py 同源） ----------
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# ★ P5F-REPOINT: 原宿主壳 `game/commands`（随删壳批消失）→ 包内真源 `content/`（同下面 gm.py 的落点）
CMD_DIR = os.path.join(PLUGIN_DIR, "content")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cmd_registry import patterns_with_meta  # noqa: E402


# 装饰器扫描：统一走 tests/_cmd_registry.py（@filter.regex 字面量 + @declared 声明都认）
DECORATORS = patterns_with_meta()


async def dispatch(m, gid, qid, text):
    """模拟 AstrBot 分发：所有正则匹配的 handler 按 priority 降序执行，
    收集全部回复（未 stop_event 则继续分发 → 双回复可复现）。
    返回 (回复列表, 命中的 handler 名列表)。"""
    ev = FakeEvent(gid, qid, text)
    hit_names = []
    for name, (pat, _p, _f) in DECORATORS.items():
        if name == "_maint_gate":  # 全局 gate 另测（item 5）
            continue
        try:
            if re.compile(pat).search(text):
                hit_names.append(name)
        except re.error:
            continue
    hit_names.sort(key=lambda n: -(DECORATORS[n][1] or 0))
    out = []
    for name in hit_names:
        h = getattr(m, name, None)
        if h is None:
            continue
        try:
            out.extend(await run(h, ev))
        except Exception as e:
            out.append(f"<EXC {name}: {type(e).__name__}: {e}>")
        if ev._stopped:
            break
    return out, hit_names


# ================= 1. 双 handler 单回复 =================
async def test_double_handler_single_reply(m):
    print("【1. 双 handler 单回复（v104 M24 P0 修复）】")
    clean_db()
    await dispatch(m, "g1", "q1", "注册 战士 单回复 男")
    cases = [
        ("副业任务", "daily_prof"),
        ("转职重置", "evolve_reset"),
        ("烹饪列表", "cooking_list"),
        ("副本地图", "instance_map_view_cmd"),
    ]
    for text, expect in cases:
        out, hits = await dispatch(m, "g1", "q1", text)
        check(f"『{text}』命中恰 1 handler={expect}（实际 {hits}）",
              hits == [expect], str(hits))
        check(f"『{text}』只回 1 条结果（实际 {len(out)} 条）",
              len(out) == 1, f"回复数={len(out)}: {str(out)[:200]}")
        if out:
            check(f"『{text}』回复非空", len(out[0]) > 0, "")


# ================= 2. GM 白名单默认拒绝 =================
async def test_gm_whitelist(m):
    print("【2. GM 白名单默认拒绝（v104.1 M24 P1 修复）】")
    clean_db()
    os.environ.pop("GWEN_GM_QQ", None)
    # 目标玩家（收金币方）
    await dispatch(m, "g1", "t1", "注册 战士 阿金 男")
    gold0 = db.get_player("g1", "t1")["gold"]

    # 2a. 空白名单 + 无环境变量 → 拒绝
    out, hits = await dispatch(m, "g1", "evil1", "gm_发金币 t1 100")
    check("空白名单 gm_发金币 命中 gm_give_gold", hits == ["gm_give_gold"], str(hits))
    check("空白名单被拒（⛔ 提示）", len(out) == 1 and "⛔" in out[0], str(out)[:120])
    check("空白名单金币未变动", db.get_player("g1", "t1")["gold"] == gold0,
          f"gold={db.get_player('g1','t1')['gold']}")

    # 2b. 数据库白名单命中 → 放行
    db.set_event_state("gm_whitelist", json.dumps(["evil1"]))
    out, _ = await dispatch(m, "g1", "evil1", "gm_发金币 t1 100")
    check("库白名单放行（已给 100 金币）",
          len(out) == 1 and "已给" in out[0] and db.get_player("g1", "t1")["gold"] == gold0 + 100,
          str(out)[:120])

    # 2c. 白名单内其他人仍被拒
    out, _ = await dispatch(m, "g1", "evil3", "gm_发金币 t1 1")
    check("非白名单用户仍被拒", len(out) == 1 and "⛔" in out[0], str(out)[:120])

    # 2d. 环境变量白名单 → 放行
    db.delete_event_state("gm_whitelist")
    os.environ["GWEN_GM_QQ"] = "evil2"
    out, _ = await dispatch(m, "g1", "evil2", "gm_发金币 t1 50")
    check("环境变量白名单放行",
          len(out) == 1 and "已给" in out[0] and db.get_player("g1", "t1")["gold"] == gold0 + 150,
          str(out)[:120])
    os.environ.pop("GWEN_GM_QQ", None)
    db.delete_event_state("gm_whitelist")


# ================= 3. gm_伤害 无 require_player =================
async def test_gm_boss_dmg_no_require_player(m):
    print("【3. gm_伤害 无 require_player（v104 M24 P1 修复）】")
    clean_db()
    os.environ.pop("GWEN_GM_QQ", None)
    # 静态：gm.py 全文无 require_player
    # ★ P5F-REPOINT: 原读宿主壳 `game/commands/gm.py`（随删壳批消失）→ 包内实现
    #   `content/gm.py`（同名实现面；登记面 = `content/cmds_gm.py`，两者都无 require_player）。
    gm_src = open(os.path.join(CMD_DIR, "gm.py"), encoding="utf-8").read()
    check("gm.py 无 require_player 装饰器", "require_player" not in gm_src, "")
    # 行为：gm_ 前缀身份（无角色）直接可用
    out, hits = await dispatch(m, "g1", "gm_x1", "gm_伤害 10")
    check("gm_伤害 命中 gm_boss_dmg", hits == ["gm_boss_dmg"], str(hits))
    check("无角色 GM 不被 REGISTER_HINT 拦",
          len(out) == 1 and "你还没有角色" not in out[0], str(out)[:120])
    check("gm_伤害 正常执行（倍率已设置）",
          len(out) == 1 and "倍率" in out[0] and float(db.get_event_state("boss_dmg_gm_x1") or 0) == 10.0,
          f"out={str(out)[:120]} state={db.get_event_state('boss_dmg_gm_x1')}")
    # 行为对照：无参查询同样不被拦
    out, _ = await dispatch(m, "g1", "gm_x1", "gm_伤害")
    check("gm_伤害 无参查询不被拦", len(out) == 1 and "你还没有角色" not in out[0], str(out)[:120])


# ================= 4. 移动别名 =================
async def test_move_alias(m):
    print("【4. 移动别名『移动 1』≡『前往 1』（v104 P2 M22 修复）】")
    clean_db()
    await dispatch(m, "g1", "q4", "注册 战士 行者 男")
    sa0 = C.MAP_BY_ID["oak_town"]["subareas"][0]["id"]
    db.update_player("g1", "q4", cur_map="oak_town", cur_subarea=sa0)

    # v115 探索见闻：首次到达 oak_town_2 会附加首访奖励文本，使先执行的那次『前往 1』
    # 与复位后『移动 1』回复不一致（前者首访、后者非首访）。预写 visited_subareas 让
    # 两次 alias 调用均为非首访（回复等价），保留"别名回复等价"断言意图。
    # `game.content.exploration_record_visit` 的包内真源 = `content.exploration.record_visit`
    # （REPOINT_MAP §2；包内聚合门面 C 未导出该名）
    from content.exploration import record_visit as _record_visit
    _record_visit("g1", "q4", "oak_town", "oak_town_2")
    before = db.get_player("g1", "q4")["cur_subarea"]  # 起点（期望 ≠ 移动后落点）
    out1, hits1 = await dispatch(m, "g1", "q4", "前往 1")
    land1 = db.get_player("g1", "q4")["cur_subarea"]   # 『前往 1』落点
    check("『前往 1』命中 move", hits1 == ["move"], str(hits1))
    check("『前往 1』确实变更子区域", land1 != before, str(land1))
    db.update_player("g1", "q4", cur_subarea=sa0)  # 复位起点，保证同条件对比
    out2, hits2 = await dispatch(m, "g1", "q4", "移动 1")
    check("『移动 1』命中 move（别名复活）", hits2 == ["move"], str(hits2))
    check("『移动 1』有回复（不无响应）", len(out2) == 1 and len(out2[0]) > 5, str(out2)[:120])
    check("『移动 1』与『前往 1』回复等价", out1 and out2 and _strip_tip(out1[0]) == _strip_tip(out2[0]),
          f"前往={str(out1)[:80]} 移动={str(out2)[:80]}")
    land2 = db.get_player("g1", "q4")["cur_subarea"]   # 『移动 1』落点（复位后同起点）
    check("『移动 1』落点与『前往 1』一致", land2 == land1, f"前往={land1} 移动={land2}")
    check("『移动 1』确实变更子区域", land2 != before, str(land2))
    # 负向：『前往开始』不被 move 抢
    _, hits3 = await dispatch(m, "g1", "q4", "前往开始")
    check("『前往开始』不命中 move", "move" not in hits3, str(hits3))


# ================= 5. 停服 gate =================
async def test_maint_gate(m):
    print("【5. 停服 gate 键补全（v104 M24 P1 修复）】")
    from _engine_harness import GameCmdFilter as _GameCmdFilter
    clean_db()
    gf = _GameCmdFilter()
    db.set_event_state("server_maintenance", "1")

    for text in ["物品 2", "周围", "离开副本"]:
        ev = FakeEvent("g1", "p1", text)
        hit = gf.filter(ev, None)
        check(f"停服 gate 命中『{text}』（registry 键补全）", hit is True, "")
        if hit:
            res = await m._maint_gate(ev)
            check(f"『{text}』被 _maint_gate 静默拦截（v134.7 不回复维护提示，直接无视）",
                  res is None and ev._stopped,
                  f"res={res} stopped={ev._stopped}")
    # 日常聊天不误拦
    ev = FakeEvent("g1", "p1", "今天天气不错，大家晚上好")
    check("日常聊天不被 gate 命中", gf.filter(ev, None) is False, "")
    # GM 身份放行（gate 不产出、不拦截）
    ev = FakeEvent("g1", "gm_x1", "gm_状态")
    check("GM 指令仍被 filter 命中（gate 语义）", gf.filter(ev, None) is True, "")
    res = await m._maint_gate(ev)
    check("GM 身份 _maint_gate 直接放行（0 条产出）", res is None, str(res)[:80])
    # 开服后 gate 放行
    db.delete_event_state("server_maintenance")
    ev = FakeEvent("g1", "p1", "物品 2")
    res = await m._maint_gate(ev)
    check("开服后 _maint_gate 放行（0 条产出）", res is None and not ev._stopped, str(res)[:80])


# ================= 6. 命令矩阵 =================
def test_command_matrix():
    print("【6. 命令矩阵两两无冲突（代表输入恰好 1 命中）】")
    from test_v87_command_matrix import (POOL, REPRESENTATIVES, EXEMPT_DOUBLE,
                                         EXTRA_POSITIVE, NEGATIVE)

    def hits(text):
        t = text.strip()
        return {name for name, rx in POOL.items() if rx.match(t)}

    missing = sorted(set(DECORATORS) - {"_maint_gate"} - set(REPRESENTATIVES))
    check("矩阵覆盖全部注册 handler（_maint_gate 除外）", not missing, f"缺: {missing}")
    for name, inp in sorted(REPRESENTATIVES.items()):
        got = hits(inp)
        if inp in EXEMPT_DOUBLE:
            want, why = EXEMPT_DOUBLE[inp]
            check(f"『{inp}』豁免双注册（{name}）", got == want,
                  f"实际 {sorted(got)}（{why}）")
        else:
            check(f"『{inp}』→ 恰好 1 命中={name}", got == {name}, f"实际 {sorted(got)}")
    for inp, want in EXTRA_POSITIVE:
        got = hits(inp)
        check(f"『{inp}』→ {sorted(want)}", got == want, f"实际 {sorted(got)}")
    for inp in NEGATIVE:
        got = hits(inp)
        check(f"负面『{inp}』0 命中", not got, f"实际 {sorted(got)}")


# ================= 7. 帮助补全 =================
async def test_help(m):
    print("【7. 帮助补全（v104 P3 M24 修复）】")
    from content.misc_cmds import CMD_HELP, CMD_HELP_CHAR, CMD_HELP_ADV
    from content.misc_cmds import (
        CMD_HELP_BATTLE, CMD_HELP_SKILL, CMD_HELP_PROF, CMD_HELP_ITEM,
        CMD_HELP_INSTANCE, CMD_HELP_SOCIAL, CMD_HELP_WORLD, CMD_HELP_OTHER,
    )
    all_help = "\n".join([
        CMD_HELP, CMD_HELP_CHAR, CMD_HELP_ADV,
        CMD_HELP_BATTLE, CMD_HELP_SKILL, CMD_HELP_PROF,
        CMD_HELP_ITEM, CMD_HELP_INSTANCE, CMD_HELP_SOCIAL,
        CMD_HELP_WORLD, CMD_HELP_OTHER,
    ])
    # v114.6 帮助精简：主面板只排系统标题；副本内指令/接取/转职重置收录在对应分类子面板
    for kw in ["编年史", "移动", "位置", "赶路", "转职重置", "副本地图", "荣誉", "交互",
               "接取", "调查", "撤退", "竞拍", "帮助"]:
        check(f"帮助文案含『{kw}』", kw in all_help, "")
    # 行为：『帮助』主面板 / 『帮助 世界』分类
    out, hits = await dispatch(m, "g1", "p1", "帮助")
    check("『帮助』命中 help_cmd 且单条", hits == ["help_cmd"] and len(out) == 1, str(hits))
    # v114.6 鱼鱼拍板：帮助主面板只排系统标题，不展开详细指令
    check("『帮助』主面板只排系统标题", out and "角色系统" in out[0] and "冒险系统" in out[0]
          and "编年史" not in out[0] and "移动" not in out[0], str(out)[:120])
    out, _ = await dispatch(m, "g1", "p1", "帮助 世界")
    check("『帮助 世界』分类回复正常", out and "移动" in out[0], str(out)[:120])
    if "声望商店" not in all_help:
        finding("帮助文案未收录『声望商店』（v104 批次3 新增指令，CMD_HELP_WORLD 只有『声望 图鉴 百科』）",
                "→ 建议 CMD_HELP_WORLD【声望】行补『声望商店 <势力>』")


# ================= 8. 注销清理 =================
async def test_delete_account_cleanup(m):
    print("【8. 注销清理（v104 M01/M24 修复：event_state 0 残留）】")
    clean_db()
    await dispatch(m, "g1", "q8", "注册 战士 要注销 男")
    # 造各种按 qq 后缀存储的状态
    db.set_event_state(f"move_mode:{'q8'}", "1")
    db.set_event_state(f"item_view_mode:{'q8'}", "1")
    db.set_event_state("daily_fortune_g1_q8", "1")
    db.set_event_state("boss_dmg_q8", "2.5")
    db.set_event_state("talk_g1_q8", "xxx")
    db.set_event_state(f"del_confirm_{'q8'}", str(int(time.time())))
    db.set_event_state("server_maintenance", "1")  # 全局键，必须保留
    conn = sqlite3.connect(db.db_path())
    try:
        conn.execute("INSERT INTO props_use (qq_id, used) VALUES (?,?)", ("q8", "{}"))
        conn.execute("INSERT INTO pet_dex (qq_id, pet_key, hatched) VALUES (?,?,?)",
                     ("q8", "野狼", 1))
        conn.commit()
    finally:
        conn.close()

    out, _ = await dispatch(m, "g1", "q8", "注销")
    check("『注销』发起确认", len(out) == 1 and "确认" in out[0], str(out)[:100])
    out, _ = await dispatch(m, "g1", "q8", "注销 确认")
    check("『注销 确认』执行删除", len(out) == 1 and "落幕" in out[0], str(out)[:100])
    check("玩家已删除", db.get_player("g1", "q8") is None, "")
    for key in [f"move_mode:{'q8'}", f"item_view_mode:{'q8'}", "daily_fortune_g1_q8",
                "boss_dmg_q8", "talk_g1_q8", f"del_confirm_{'q8'}"]:
        check(f"event_state『{key}』已清理", db.get_event_state(key) is None,
              f"残留={db.get_event_state(key)}")
    check("全局键 server_maintenance 保留", db.get_event_state("server_maintenance") == "1", "")
    conn = sqlite3.connect(db.db_path())
    try:
        n_props = conn.execute("SELECT COUNT(*) FROM props_use WHERE qq_id='q8'").fetchone()[0]
        n_dex = conn.execute("SELECT COUNT(*) FROM pet_dex WHERE qq_id='q8'").fetchone()[0]
    finally:
        conn.close()
    check("props_use 0 残留", n_props == 0, f"残留 {n_props} 行")
    check("pet_dex 0 残留", n_dex == 0, f"残留 {n_dex} 行")
    # 重注册不串模式状态
    await dispatch(m, "g1", "q8", "注册 战士 重生者 男")
    check("重注册成功", db.get_player("g1", "q8") is not None, "")
    check("重注册后 move_mode 不串", db.get_event_state(f"move_mode:{'q8'}") is None, "")
    check("重注册后 del_confirm 不串（防呆缺口已修）",
          db.get_event_state(f"del_confirm_{'q8'}") is None, "")
    db.delete_event_state("server_maintenance")


# ================= 9. feedback reply =================
async def test_feedback_reply(m):
    print("【9. feedback reply 字段（v104 M24 P2 修复）】")
    clean_db()
    os.environ.pop("HERMES_WEBHOOK_URL", None)
    fid = db.add_feedback("q9", "g9", "测试：想要坐骑系统")
    rows = db.get_feedback()
    check("add_feedback 返回编号", fid > 0, f"fid={fid}")
    check("get_feedback 有记录", len(rows) >= 1, "")
    row = rows[0]
    check("get_feedback 行含 reply 字段（v104 补列）",
          "reply" in row.keys(), f"keys={list(row.keys())}")
    check("新意见 reply 默认空", row["reply"] in (None, ""), f"reply={row['reply']!r}")
    rows_new = db.get_feedback(status="new")
    check("get_feedback(status='new') 含 reply", rows_new and "reply" in rows_new[0].keys(), "")
    # 行为：意见箱 handler 正常收
    out, hits = await dispatch(m, "g9", "q9", "意见 希望增加双人坐骑")
    check("『意见』命中 feedback_cmd", hits == ["feedback_cmd"], str(hits))
    check("『意见』回复含编号回执", len(out) == 1 and "收到你的意见" in out[0], str(out)[:120])


async def main():
    m = Main(None)
    await test_double_handler_single_reply(m)
    await test_gm_whitelist(m)
    await test_gm_boss_dmg_no_require_player(m)
    await test_move_alias(m)
    await test_maint_gate(m)
    test_command_matrix()
    await test_help(m)
    await test_delete_account_cleanup(m)
    await test_feedback_reply(m)

    print(f"\n结果: {passed} 通过, {failed} 失败")
    if findings:
        print(f"发现 {len(findings)} 个真实问题（不阻断）:")
        for f_ in findings:
            print(f"  ⚠️ {f_}")
    return failed == 0


def _strip_tip(text):
    """v127 随机提示库：剥离 💡 提示行后比较别名回复核心内容（提示随机是设计特性）。"""
    return "\n".join(l for l in text.split("\n") if "💡" not in l)



if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)
