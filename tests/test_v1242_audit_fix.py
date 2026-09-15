# -*- coding: utf-8 -*-
"""v124.2 审计修复批次·端到端行为锁定测试

覆盖（铁律：GWEN_GAME_DB 必须指向 tests/ 私有临时库，禁用相对路径）：
  1. use 端到端：建号→发物品→『使用 X』命令全链路→任务 ready+物品状态
     - 任务道具（候鸟的信 hq7_1）：不消耗但推进
     - 消耗品（醇香麦酒 s80）：消耗并推进
     - 收藏品改任务道具（商会股份凭证 s74）：不消耗并推进
  2. use 地图校验：hq7_1（map=starlake）跨图使用不推进、同图推进
  3. branch 暗线：s18 选项 2 → flag s18_branch_dark + 白桦的余烬入包 + 无重复发奖
  4. eq:/pet/mount 奖励：s18 善线 → 白桦的护符入包；hq7_3 交付 → 雾羽候鸟缰绳+星羽候鸟蛋入包
  5. unlock：s53 双 side 缺一不可；s75 main 型（进行中/已完成均解锁，按代码语义）
  6. require_stats：hq8_1 craft_count 未达 20 不可接
  7. 称号：s18 善线→北境的恩人 / 暗线→长夜行者；s78 两分支→公正执法者/影子之友（直调 title_conds）
"""
import os
import sys
import asyncio

# ---- 私有临时库（基于 __file__ 的绝对路径；历史坑：相对路径曾污染插件根目录）----
_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_v1242_audit_fix.db")
os.environ["GWEN_GAME_DB"] = _DB
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _engine_harness import C, db, clean_db, Main, FakeEvent, run  # noqa: E402
from content import title_conds as TC  # noqa: E402

# ★ P5D-REPOINT：原宿主薄壳 `game/services/quests_flow.py` 的注入
#   `quests_svc = game.services.quests` 随 game/** 删除而消失（REPOINT_MAP §2：真源 =
#   `content.profession_quests`）。交付/每日推进路径需要它，否则 AttributeError。
from content import profession_quests as _profession_quests  # noqa: E402
from content import quests_flow as _quests_flow  # noqa: E402
_quests_flow.bind_host(quests_svc=_profession_quests)

# ★ P5D-REPOINT（越界登记，包侧缺陷，与 test_numeric_reward_unify 同型）：
#   `content.facade` 的扇出把 `content.reward` 的 `levelup` / `stat_bonus` / `key_to_id`
#   三槽解析成**函数对象**，而包内 `content/reward.py::_resolve` 的协议是「可调用值 =
#   零参活源 thunk，取用时调一次」⇒ 零参调用会 TypeError，被发放路径静默吞掉 ⇒ **奖励物品不入包**。
#   宿主薄壳 `game/reward.py` 绑的正是 thunk（`lambda: <函数>`），随 game/** 退役后该绑定消失。
#   这里按同一注入键同一语义补回三个 thunk（行为逐字同义）。建议包侧修 `_PKG_SURFACE` 后本段可删。
from content import gameplay_rules as _gameplay_rules  # noqa: E402
from content import reward as _reward_mod  # noqa: E402
from content import stat_bonus as _stat_bonus_mod  # noqa: E402
from content.persistence.inventory import _key_to_id as _key_to_id_fn  # noqa: E402
_reward_mod.bind_host(
    levelup=lambda: _gameplay_rules.check_player_level_up,
    stat_bonus=lambda: _stat_bonus_mod.stat_bonus,
    key_to_id=lambda: _key_to_id_fn,
)

PASS = 0
FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} {detail}")


def make_player(qq, lv=72, cur_map="oak_town"):
    db.create_player("g", qq, f"测试{qq}", "cls_warrior", {}, 100, 50, race="human", gender="男")
    db.update_player("g", qq, level=lv, gold=10000, cur_map=cur_map, cur_subarea="",
                     stamina=999999, hp=60, mp=20)
    return db.get_player("g", qq)


def side_quest(sid):
    return next(q for q in C.SIDE_QUESTS if q["id"] == sid)


def set_side(qq, sid, status="active", progress=None):
    q = db.get_quests("g", qq)
    side = dict(q.get("side") or {})
    side[sid] = {"status": status, "progress": progress or {}}
    q["side"] = side
    db.save_quests("g", qq, q)


def side_status(qq, sid):
    return (db.get_quests("g", qq).get("side") or {}).get(sid, {}).get("status")


def add_item(qq, key, data):
    db.add_item("g", qq, key, data)


def inv_count(qq, name):
    return sum(r["count"] for r in db.get_inventory("g", qq) if r["data"].get("name") == name)


def has_item(qq, name):
    return inv_count(qq, name) > 0


async def use_cmd(m, qq, item):
    ev = FakeEvent("g", qq, f"使用 {item}")
    out = await run(m.use, ev)
    return "\n".join(str(r) for r in out)


# ================= 1. use 端到端 =================
async def section_use(m):
    print("【1. use 端到端】")
    # A. 任务道具：候鸟的信（hq7_1，map=starlake）——不消耗但推进
    qq = "u_a_letter"
    make_player(qq, 60, cur_map="starlake")
    set_side(qq, "hq7_1", "active")
    add_item(qq, "mat_hou_niao_de_xin", dict(C.MATERIALS["mat_hou_niao_de_xin"]))
    check("A0 初始背包含候鸟的信×1", inv_count(qq, "候鸟的信") == 1)
    txt = await use_cmd(m, qq, "候鸟的信")
    check("A1 使用『候鸟的信』→ hq7_1 ready", side_status(qq, "hq7_1") == "ready",
          f"status={side_status(qq, 'hq7_1')}")
    check("A2 使用播报含目标达成", "目标达成" in txt, txt[:80])
    check("A3 任务道具未消耗", inv_count(qq, "候鸟的信") == 1,
          f"count={inv_count(qq, '候鸟的信')}")

    # B. 消耗品：醇香麦酒（s80，map=frost_horn）——消耗并推进
    qq = "u_b_ale"
    make_player(qq, 45, cur_map="frost_horn")
    set_side(qq, "s80", "active")
    add_item(qq, "i_ale", dict(C.ITEMS["i_ale"]))
    check("B0 初始背包含醇香麦酒×1", inv_count(qq, "醇香麦酒") == 1)
    txt = await use_cmd(m, qq, "醇香麦酒")
    check("B1 使用『醇香麦酒』→ s80 ready", side_status(qq, "s80") == "ready",
          f"status={side_status(qq, 's80')}")
    check("B2 消耗品已消耗", inv_count(qq, "醇香麦酒") == 0,
          f"count={inv_count(qq, '醇香麦酒')}")
    check("B3 使用播报含恢复效果", "恢复" in txt, txt[:80])

    # C. 收藏品→任务道具：商会股份凭证（s74，map=ironharbor）——不消耗并推进
    qq = "u_c_voucher"
    make_player(qq, 60, cur_map="ironharbor")
    set_side(qq, "s74", "active")
    add_item(qq, "i_shang_hui_gu_fen_ping_zheng", dict(C.ITEMS["i_shang_hui_gu_fen_ping_zheng"]))
    check("C0 初始背包含商会股份凭证×1", inv_count(qq, "商会股份凭证") == 1)
    txt = await use_cmd(m, qq, "商会股份凭证")
    check("C1 使用『商会股份凭证』→ s74 ready", side_status(qq, "s74") == "ready",
          f"status={side_status(qq, 's74')}")
    check("C2 凭证未消耗", inv_count(qq, "商会股份凭证") == 1,
          f"count={inv_count(qq, '商会股份凭证')}")


# ================= 2. use 地图校验 =================
async def section_use_map(m):
    print("【2. use 地图校验（hq7_1 map=starlake）】")
    qq = "u_d_map"
    make_player(qq, 60, cur_map="oak_town")
    set_side(qq, "hq7_1", "active")
    add_item(qq, "mat_hou_niao_de_xin", dict(C.MATERIALS["mat_hou_niao_de_xin"]))
    await use_cmd(m, qq, "候鸟的信")
    check("D1 跨图使用不推进（仍 active）", side_status(qq, "hq7_1") == "active",
          f"status={side_status(qq, 'hq7_1')}")
    check("D2 跨图使用不消耗任务道具", inv_count(qq, "候鸟的信") == 1)
    db.update_player("g", qq, cur_map="starlake")
    txt = await use_cmd(m, qq, "候鸟的信")
    check("D3 同图使用推进 ready", side_status(qq, "hq7_1") == "ready",
          f"status={side_status(qq, 'hq7_1')}")
    check("D4 同图使用播报含目标达成", "目标达成" in txt, txt[:80])


# ================= 3. branch 暗线 =================
def section_branch_dark(m):
    print("【3. s18 分支暗线】")
    qq = "u_e_s18d"
    make_player(qq, 72, cur_map="black_forest")
    set_side(qq, "s18", "ready", progress={"腐牙萨满·嚎骨": 1, "白桦": 1})
    lines1 = m._complete_side_quest("g", qq, "s18")
    txt1 = "\n".join(lines1)
    check("E1 首次交付输出分支选项", "选择" in txt1 or "序号" in txt1 or "数字" in txt1, txt1[:60])
    check("E2 首次交付未完成（仍 ready）", side_status(qq, "s18") == "ready")
    st = (db.get_quests("g", qq).get("side") or {})["s18"]
    check("E3 branch_wait 置位", st.get("branch_wait") is True)
    gold0 = db.get_player("g", qq)["gold"]
    m._complete_side_quest("g", qq, "s18", branch_choice="2")
    check("E4 暗线选择后 done", side_status(qq, "s18") == "done")
    flags = db.get_talk_flags("g", qq, "npc_north_hunter")
    check("E5 flag s18_branch_dark 写入（铁弓桶）", "s18_branch_dark" in flags, flags)
    check("E6 白桦的余烬入包", has_item(qq, "白桦的余烬"))
    gold1 = db.get_player("g", qq)["gold"]
    check("E7 暗线分支金币入账 +5500", gold1 >= gold0 + 5500, f"{gold0}->{gold1}")
    cnt = inv_count(qq, "白桦的余烬")
    lines3 = m._complete_side_quest("g", qq, "s18", branch_choice="2")
    check("E8 重复交付被拒（无重复发奖）", "还没完成" in "\n".join(lines3), "\n".join(lines3)[:60])
    check("E9 重复交付后金币不变", db.get_player("g", qq)["gold"] == gold1)
    check("E10 重复交付后余烬不重复", inv_count(qq, "白桦的余烬") == cnt)


# ================= 4. eq:/pet/mount 奖励 =================
def section_rewards(m):
    print("【4. eq:/pet/mount 奖励】")
    # F. s18 善线 → eq:白桦的护符
    qq = "u_f_s18l"
    make_player(qq, 72, cur_map="black_forest")
    set_side(qq, "s18", "ready", progress={"腐牙萨满·嚎骨": 1, "白桦": 1})
    m._complete_side_quest("g", qq, "s18")
    m._complete_side_quest("g", qq, "s18", branch_choice="1")
    check("F1 s18 善线 done", side_status(qq, "s18") == "done")
    check("F2 白桦的护符入包", has_item(qq, "白桦的护符"))
    check("F3 护符为装备（带 slot）",
          any(r["data"].get("slot") for r in db.get_inventory("g", qq)
              if r["data"].get("name") == "白桦的护符"))

    # G. hq7_3 交付 → reward_mount + reward_pet（直调 _complete_side_quest 设前置状态）
    qq = "u_g_hq7_3"
    make_player(qq, 60, cur_map="dawn_city")
    set_side(qq, "hq7_3", "ready")
    m._complete_side_quest("g", qq, "hq7_3")
    check("G1 hq7_3 done", side_status(qq, "hq7_3") == "done")
    check("G2 雾羽候鸟缰绳入包", has_item(qq, "雾羽候鸟缰绳"))
    check("G3 星羽候鸟蛋入包", has_item(qq, "星羽候鸟蛋"))
    check("G4 缰绳 type=坐骑",
          any(r["data"].get("type") == "坐骑" and r["data"].get("name") == "雾羽候鸟缰绳"
              for r in db.get_inventory("g", qq)))

    # L. s78 两分支 flag 写入 + 分支奖励
    qq = "u_l_s78j"
    make_player(qq, 50, cur_map="white_deer")
    set_side(qq, "s78", "ready")
    m._complete_side_quest("g", qq, "s78")
    m._complete_side_quest("g", qq, "s78", branch_choice="1")
    check("L1 s78 正义线 done", side_status(qq, "s78") == "done")
    check("L2 flag s78_branch_justice 写入（米洛桶）",
          "s78_branch_justice" in db.get_talk_flags("g", qq, "npc_apprentice_milo"),
          db.get_talk_flags("g", qq, "npc_apprentice_milo"))
    check("L3 晨曦城卫兵嘉奖令入包", has_item(qq, "晨曦城卫兵嘉奖令"))

    qq = "u_l_s78m"
    make_player(qq, 50, cur_map="white_deer")
    set_side(qq, "s78", "ready")
    m._complete_side_quest("g", qq, "s78")
    m._complete_side_quest("g", qq, "s78", branch_choice="2")
    check("L4 s78 义气线 done", side_status(qq, "s78") == "done")
    check("L5 flag s78_branch_mercy 写入（米洛桶）",
          "s78_branch_mercy" in db.get_talk_flags("g", qq, "npc_apprentice_milo"),
          db.get_talk_flags("g", qq, "npc_apprentice_milo"))
    check("L6 猫眼石胸针入包", has_item(qq, "猫眼石胸针"))


# ================= 5. unlock =================
def section_unlock(m):
    print("【5. unlock 多条件】")
    # H. s53 双 side 缺一不可
    qq = "u_h_s53"
    make_player(qq, 50, cur_map="white_deer")
    sq53 = side_quest("s53")
    q = db.get_quests("g", qq)
    check("H1 s53 无前置时不可解锁", m._sq_unlocked(q, sq53) is False)
    side = dict(q.get("side") or {})
    side["s23"] = {"status": "done"}
    q["side"] = side
    check("H2 s53 仅完成 s23 仍不可解锁", m._sq_unlocked(q, sq53) is False)
    side["s4"] = {"status": "done"}
    q["side"] = side
    check("H3 s53 双前置均 done 才解锁", m._sq_unlocked(q, sq53) is True)

    # I. s75 main 型 unlock（代码语义：main_quest 命中或 completed_main 包含）
    qq = "u_i_s75"
    make_player(qq, 40, cur_map="dawn_city")
    sq75 = side_quest("s75")
    q = db.get_quests("g", qq)
    check("I1 s75 无主线进度不可解锁", m._sq_unlocked(q, sq75) is False)
    q["main_quest"] = "q6_1"
    check("I2 s75 主线 q6_1 进行中即解锁（main_quest 命中）", m._sq_unlocked(q, sq75) is True)
    q2 = db.get_quests("g", qq)
    q2["main_quest"] = None
    q2["completed_main"] = ["q6_1"]
    check("I3 s75 主线 q6_1 已完成即解锁（completed_main）", m._sq_unlocked(q2, sq75) is True)


# ================= 6. require_stats =================
def section_stats(m):
    print("【6. require_stats（hq8_1 craft_count≥20）】")
    qq = "u_j_hq8"
    make_player(qq, 75, cur_map="anvil_fort")
    sq81 = side_quest("hq8_1")
    check("J1 无锻造记录不可接", m._sq_stats_met(db.get_player("g", qq), sq81) is False)
    db.init_stats("g", qq)
    db.bump_stats("g", qq, craft_count=19)
    check("J2 craft_count=19 仍不可接", m._sq_stats_met(db.get_player("g", qq), sq81) is False)
    db.bump_stats("g", qq, craft_count=1)
    check("J3 craft_count=20 可接", m._sq_stats_met(db.get_player("g", qq), sq81) is True)


# ================= 7. 称号 =================
def title_ctx(qq):
    p = db.get_player("g", qq)
    return TC.TitleCtx("g", qq, p, db.get_stats("g", qq) or {},
                       db.get_reputation("g", qq), db.get_quests("g", qq))


def section_titles(m):
    print("【7. 称号判定（title_conds 直调）】")
    qq = "u_k_fresh"
    make_player(qq, 72)
    ctx = title_ctx(qq)
    check("K0 无进度四称号全 False",
          not TC.CONDITIONS["north_benefactor"](ctx)
          and not TC.CONDITIONS["nightwalker"](ctx)
          and not TC.CONDITIONS["just_enforcer"](ctx)
          and not TC.CONDITIONS["shadow_friend"](ctx))
    ctx = title_ctx("u_f_s18l")
    check("K1 s18 善线→北境的恩人 True", TC.CONDITIONS["north_benefactor"](ctx) is True)
    check("K2 s18 善线→长夜行者 False", TC.CONDITIONS["nightwalker"](ctx) is False)
    ctx = title_ctx("u_e_s18d")
    check("K3 s18 暗线→长夜行者 True", TC.CONDITIONS["nightwalker"](ctx) is True)
    check("K4 s18 暗线→北境的恩人 False", TC.CONDITIONS["north_benefactor"](ctx) is False)
    ctx = title_ctx("u_l_s78j")
    check("K5 s78 正义线→公正执法者 True", TC.CONDITIONS["just_enforcer"](ctx) is True)
    check("K6 s78 正义线→影子之友 False", TC.CONDITIONS["shadow_friend"](ctx) is False)
    ctx = title_ctx("u_l_s78m")
    check("K7 s78 义气线→影子之友 True", TC.CONDITIONS["shadow_friend"](ctx) is True)
    check("K8 s78 义气线→公正执法者 False", TC.CONDITIONS["just_enforcer"](ctx) is False)


async def main():
    clean_db()
    w = Main(None)
    await section_use(w)
    await section_use_map(w)
    section_branch_dark(w)
    section_rewards(w)
    section_unlock(w)
    section_stats(w)
    section_titles(w)
    print(f"\n结果: {PASS} 通过, {FAIL} 失败")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
