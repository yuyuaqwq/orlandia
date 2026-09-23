# -*- coding: utf-8 -*-
"""U1-I3 冻结门禁：**周期形状**（`extends/ext_life/periodic`）+ **收集形状**（`extends/ext_life/collect`）
把包内 5 处周期点 / 2 处收集点换成引擎形状之后，行为必须逐字节不变。

跑法（工作区根；三个环境变量都指 lane 内）::

    PY="C:/Users/yuyu/AppData/Roaming/uv/tools/astrbot/Scripts/python.exe"
    export GWEN_FRAMEWORK_DIR=<ws>/work/eng GWEN_HOST_DIR=<ws>/work/host \
           GWEN_GAME_DB=<ws>/out/test.db PYTHONUTF8=1
    "$PY" work/pkg/tests/test_u1i3_periodic_collect_frozen.py

判据（作业书 §2.5 / §6.2，逐条打原始输出）
------------------------------------------
 [1] **旧实现逐字冻结** —— 8 处旧实现（`_week_key/_week_state/_save_week_state`、`_claim_supply_box`、
     `_fb_cd_key/feedback_precheck/feedback_submit`、`achievement_panel/claim_reply`、
     `entry_collected/book_progress`、`signin_claim`）整段文本内嵌（`_FROZEN_*`），
     与「改动前」源文件逐字节相同（生成期已对拍，见 `_FROZEN` 说明）。
 [2] **双 sha256** —— 冻结片段文本 sha256 + `inspect.getsource(活实现)` sha256，两边都钉死；
     另钉 `signin_claim` **实际执行的 SQL 文本** sha256（并断言它逐字节等于冻结的那句）。
 [3] **全量/边界比对** —— 旧实现（内嵌文本 `exec` 出来的那一份）与活实现跑同一批输入：
     · 周键：2025-12-01 → 2026-01-31 逐日（含跨年 ISO 周边界）
     · 补给箱：三档 × 跨年/跨月/跨周日期 × 多档初值 × 连领三次（逐行 + event_state 逐键）
     · 连续段：首次 / 连续 7 天 / 断签 / 同日重领 / 跨月 / 跨年（真 SQLite，含行值）
     · 收藏册：5 册全条目 × 名字集合矩阵（逐条 + N/M）
     · 成就面板：4 种参数 × 4 种解锁集 × 3 种已领集 × 2 种成就点
     · 意见箱：末次时间戳矩阵 × now 矩阵（含 30s 边界与坏值）
 [4] **零知识静态扫描** —— `ast` 扫两个新引擎模块的**全部字符串常量**（含 docstring），
     断言无内容侧取值词；再断言零 `datetime`/`time`/`calendar` import（引擎不认识日历）。
 [5] **口径分歧断言** —— 三条有意不统一的判据各一条（空表 `done` / 三态无第四态 / 首次触达 vs 计数）。
 [6] **视图/序列化** —— 形状派生出的视图可 `json.dumps` 且往返相等。
 [7] **有牙反证** —— 猴补破坏 3 处（签到 SQL / 补给箱上限 / 收集判据），每次对应探针必须变红；
     跑完还原（并断言 6 个源文件 sha256 前后一致：**全程不写盘**）。
 [8] **多故障场景** —— 3 条「两处同时坏」（只坏一处证明不了顺序：两条断言各管一段）+ 1 条顺序断言
     （`PeriodCounter.consume` 先判后写；补给箱行序 = 档位声明序，且行序敏感）。

⚠ 「旧实现」是本文件内嵌的**文本**，`exec` 到独立命名空间跑 —— 不是「读代码觉得等价」。
⚠ 冻结的 8 段文本由 `out/gen_u1i3_frozen.py` 从 `base/pkg/**`（改动前副本）逐行切片生成；
  本文件里它们是**成品字面量**，运行期不需要 `base/`。
"""
from __future__ import annotations

import ast
import datetime
import hashlib
import inspect
import json
import os
import sqlite3
import sys
import types

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _paths                                                            # noqa: E402

# ★ 直跑不共享 `test_game_data.db`（与 `test_texts_table.py` 同款口径）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(_paths.TESTS_DIR, "test_u1i3_frozen.db"))

from _engine_harness import db                                           # noqa: E402
from content import cmds_event as _EV                                    # noqa: E402
from content import collection as _LIB                                   # noqa: E402
from content import misc_cmds as _M                                      # noqa: E402
from content import texts as _T                                          # noqa: E402
from content.catalog_quests import ACHIEVEMENTS                          # noqa: E402
from content.flow import weekly_progress as _WP                          # noqa: E402
from content.persistence import social as _SO                            # noqa: E402
import ext_life.collect as _PC                                   # noqa: E402
import ext_life.periodic as _PE                                   # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


# ══════════════════════════════════════════════════════════════════════════════
# [1] 旧实现逐字冻结（成品字面量；生成器从 base/pkg/** 逐行切片）
# ══════════════════════════════════════════════════════════════════════════════
_FROZEN_WEEK_KEY = 'def _week_key(qq_id) -> str:\n    """周状态 event_state key：weekly_{qq_id}_{ISO年}-W{周}（跨年自动换 key）。"""\n    y, w, _wd = datetime.date.today().isocalendar()\n    return f"weekly_{qq_id}_{y}-W{w:02d}"\n'
_FROZEN_WEEK_STATE = 'def _week_state(qq_id):\n    """读取本周状态（无记录返回 None）。"""\n    raw = db.get_event_state(_week_key(qq_id))\n    if not raw:\n        return None\n    try:\n        st = json.loads(raw)\n        if not isinstance(st, dict):\n            return None\n        st.setdefault("tasks", {})\n        st.setdefault("done_n", 0)\n        return st\n    except Exception:\n        return None\n'
_FROZEN_WEEK_SAVE = 'def _save_week_state(qq_id, st):\n    db.set_event_state(_week_key(qq_id), json.dumps(st, ensure_ascii=False))\n'
_FROZEN_SUPPLY = 'def _claim_supply_box(env) -> list:\n    """领取每日补给箱（SUPPLY_BOX 3 档，限额用 event_state 记日期/周）。\n\n    限额口径（方案 3.8）：\n    - supply_mat 材料箱：每日 1 个\n    - supply_tool 道具箱：每日 1 个（原设计累计 3 个每日任务，简化按日限）\n    - supply_rich 豪华箱：每周 ≤2 个（原设计累计 7 个每日任务，简化按周限）\n    """\n    qq_id = env.uid\n    today = datetime.date.today().isoformat()\n    # 周起始（周一）\n    monday = (datetime.date.today() - datetime.timedelta(days=datetime.date.today().weekday())).isoformat()\n    boxes = _SUPPLY_BOX or []\n    if not boxes:\n        return [T.static("supply.missing")]\n    lines = [T.static("supply.title"), "━━━━━━━━━━━━"]\n    claimed_any = False\n    for box in boxes:\n        bid = box.get("id", "")\n        limit = box.get("limit", "")\n        # 限额判定\n        if limit == "daily_1":\n            key = f"supply_{bid}_{qq_id}_{today}"\n            if get_event_state(key):\n                lines.append(T.text("supply.daily_done", name=box.get("name", bid)))\n                continue\n            set_event_state(key, "1")\n        elif limit == "daily3":\n            key = f"supply_{bid}_{qq_id}_{today}"\n            if get_event_state(key):\n                lines.append(T.text("supply.daily_done", name=box.get("name", bid)))\n                continue\n            set_event_state(key, "1")\n        elif limit == "weekly2_daily7":\n            # 每周 ≤2：数本周已领次数\n            wk = f"supply_{bid}_{qq_id}_wk_{monday}"\n            cnt = int(get_event_state(wk) or 0)\n            if cnt >= 2:\n                lines.append(T.text("supply.weekly_done", name=box.get("name", bid),\n                                    cnt=cnt))\n                continue\n            set_event_state(wk, str(cnt + 1))\n        else:\n            continue\n        # 发放\n        got = _grant_items(env, box.get("items", []))\n        claimed_any = True\n        if got:\n            lines.append(T.text("supply.granted", name=box.get("name", bid),\n                                items="、".join(got)))\n    if not claimed_any:\n        lines.append(T.static("supply.all_done"))\n    lines.append("")\n    lines.append(T.static("supply.tip"))\n    return lines\n'
_FROZEN_FB_KEY = 'def _fb_cd_key(qq_id) -> str:\n    return "fb_cd_%s" % qq_id\n'
_FROZEN_FB_PRECHECK = 'def feedback_precheck(args: str, qq_id, now_ts: float):\n    """意见箱前置校验（真源 :401-416 逐行等价）：返回拒绝文案；放行 → `None`。\n\n    频控读 `event_state`（`fb_cd_<qq>`）；读失败/值坏 → 视为「没提过」（真源同款 try/except）。\n    """\n    if not args:\n        return MSG_EMPTY\n    if len(args) > FEEDBACK_MAX_LEN:\n        return MSG_TOO_LONG\n    # q11 低风险项：同 qq 30 秒内限 1 条（意见箱防刷屏），沿用 event_state 存末次提交时间戳\n    try:\n        _last_ts = float(db.get_event_state(_fb_cd_key(qq_id)) or 0)\n    except (TypeError, ValueError):\n        _last_ts = 0.0\n    if now_ts - _last_ts < FEEDBACK_CD_SECONDS:\n        return MSG_TOO_FAST\n    return None\n'
_FROZEN_FB_SUBMIT = 'def feedback_submit(group_id, qq_id, args: str, now_ts: float) -> dict:\n    """入库 + 记频控时间戳 + 回执文案（真源 :417-425 逐行等价；异常**不吞**，调用方记日志 + 回执）。"""\n    fid = db.add_feedback(qq_id, group_id, args)\n    # 持续成功的频控：仅成功后更新时间戳，避免失败的尝试锁住玩家再次提交\n    db.set_event_state(_fb_cd_key(qq_id), str(now_ts))\n    text = ("📮 收到你的意见啦！(编号 #%s)\\n「%s」\\n\\n"\n            "我会整理给鱼鱼看的，感谢你让这个世界变得更好✂️" % (fid, args))\n    return {"fid": fid, "text": text}\n'
_FROZEN_ACH_PANEL = 'def achievement_panel(raw: str, table, unlocked, claimed, points: int) -> list:\n    """成就面板行（真源 `commands/misc.py:achievements` 的 :340-390 逐行等价）。\n\n    `table` = 成就表（`[{id,cat,name,desc,cond,points,reward,…}]`，**源列表序** —— 分类明细的\n    渲染顺序即它）；`unlocked`/`claimed` = 已解锁 / 已领取的成就 id 集合（宿主从 DB 取）；\n    `points` = 成就点（宿主 core 算）。返回行列表（宿主还要补 "" + 底部随机提示行）。\n    """\n    cat = raw if raw in ACH_CATS else ""\n    achs = [a for a in table if (not cat or a["cat"] == cat)]\n    if cat:\n        title = "🏅 【成就·%s】" % cat\n    else:\n        title = "🏅 【成就】"\n    total_all = len(table)\n    got_all = len(unlocked)\n    pending_cnt = len([a for a in table\n                       if a["id"] in unlocked and a["id"] not in claimed and a.get("reward")])\n    lines = [title, "━━━━━━━━━━━━"]\n    if pending_cnt:\n        lines.append("🎁 %d 个成就奖励待领取！『成就 领取』一键领取" % pending_cnt)\n    if cat:\n        lines.append("解锁 %d/%d 个" % (sum(1 for a in achs if a["id"] in unlocked), len(achs)))\n        for a in achs:\n            mark = "✅" if a["id"] in unlocked else "⬜"\n            rw = a.get("reward") or {}\n            # v105 M18 P3：奖励 key 显示中文（经验/金币），对齐解锁提示 _reward_txt\n            # v140 波2：items 物品奖励也显示（《物品名》×N）\n            rw_parts = []\n            for k, v in rw.items():\n                if k == "items":\n                    for _ik, _ic in (v or {}).items():\n                        rw_parts.append("%s×%s" % (item_name(_ik), _ic))\n                else:\n                    rw_parts.append("%s+%s" % (_RW_CN.get(k, k), v))\n            rw_txt = "（%s）" % "、".join(rw_parts) if rw_parts else ""\n            if a["id"] in unlocked and a["id"] not in claimed and rw:\n                mark = "🎁"\n            lines.append("%s %s：%s%s" % (mark, a["name"], a["desc"], rw_txt))\n    else:\n        lines.append("总进度：%d/%d\u3000🏆 成就点：%s" % (got_all, total_all, points))\n        for c in ACH_CATS:\n            sub = [a for a in table if a["cat"] == c]\n            got_c = sum(1 for a in sub if a["id"] in unlocked)\n            lines.append("%s %s：%d/%d(『成就 %s』查看明细)"\n                         % ("✅" if got_c == len(sub) else "⬜", c, got_c, len(sub), c))\n    return lines\n'
_FROZEN_CLAIM_REPLY = 'def claim_reply(lines, err) -> str:\n    """『成就 领取』的一整条回执（真源 :334-338 逐行等价）。"""\n    return ("🎁 %s" % err) if err else "\\n".join(lines)\n'
_FROZEN_ENTRY_COLLECTED = 'def entry_collected(entry, inv_names, best_names) -> bool:\n    """一条收藏条目是否已收集（`key`/`name` 任一命中背包名或图鉴怪名）。"""\n    k = (entry or {}).get("key", "") or ""\n    nm = (entry or {}).get("name", "") or ""\n    return bool(k in inv_names or nm in inv_names or k in best_names or nm in best_names)\n'
_FROZEN_BOOK_PROGRESS = 'def book_progress(book, inv_names, best_names) -> tuple:\n    """返回 `(已收集数, 总条目数)` —— 判定口径见本文件头。"""\n    rows = entries(book)\n    got = sum(1 for e in rows if entry_collected(e, inv_names, best_names))\n    return got, len(rows)\n'
_FROZEN_SIGNIN_CLAIM = 'def signin_claim(group_id, qq_id, today, yesterday):\n    """F1 P1-4：原子签到认领（防并发重领）。\n\n    单事务内以条件 UPDATE 判定本次是否首次成功（WHERE last_date<>today）。并发双请求\n    经 BEGIN IMMEDIATE 串行化：首个 rowcount=1（认领成功），后者事务内重读 last_date\n    已等于 today → rowcount=0 → 返回 claimed=False。比命令层「读判断→发金子→再 save」非原子。\n    返回 (claimed, streak, total)；claimed=False 时 streak/total 为 None。\n    行为零变化：认领成功后的奖励发放仍由命令层执行。\n    """\n    with atomic() as conn:\n        # 确保行存在（老档无 signin 行也自愈），再条件更新\n        conn.execute(\n            "INSERT OR IGNORE INTO signin (qq_id, last_date, streak, total) VALUES (?,?,?,0)",\n            (qq_id, "", 0),\n        )\n        cur = conn.execute(\n            "UPDATE signin SET "\n            "last_date=?, "\n            "streak=CASE WHEN last_date=? THEN streak+1 ELSE 1 END, "\n            "total=total+1 "\n            "WHERE qq_id=? AND last_date<>?",\n            (today, yesterday, qq_id, today),\n        )\n        if cur.rowcount == 0:\n            return False, None, None\n        row = conn.execute("SELECT streak, total FROM signin WHERE qq_id=?", (qq_id,)).fetchone()\n        return True, row["streak"], row["total"]\n'
_FROZEN_SIGNIN_SQL = 'UPDATE signin SET last_date=?, streak=CASE WHEN last_date=? THEN streak+1 ELSE 1 END, total=total+1 WHERE qq_id=? AND last_date<>?'

#: 双 sha256 钉子（生成器填）：冻结片段文本 + `inspect.getsource(活实现)` + 实跑 SQL 文本
_PIN = {'frozen': {'week_key': '6186b40d843b641c98f2974f15c3e7dfa39d3fd2fce562b3c684d67552e95bd8', 'week_state': '3201bf01db4ebaa639578ca5a7ac84d7442fdb6a056bee2e50af52cd70eff108', 'week_save': '8c2c0f2e3a73b7dd2faecaa4a73574119ea831f6f858dd20c840caa71d8b5523', 'supply': '6c0e4cde33bc5fd873a419a57f38d4b38ade44a60659861a2cde00164236f507', 'fb_key': '2fbcaa590539526c0ff379a059c0fb7e32fd846076a853a58c6c93b774062773', 'fb_precheck': '74c5d02de4386b9849e4fb5c376c3e37403654c527cd120df17b56dc61a42b8b', 'fb_submit': '4abffaf252dbf1f150a2a74fb73853154226dd9c1d2662e5cbcec0a3f03507ef', 'ach_panel': '2198675c68eebb949e5a95828387274f7918c78ca878d6b2b69763cee9e7d746', 'claim_reply': 'e45dbcee7d5db40e6c2882cfc42f746a47ac89b437841fa4397ddaf177ab7131', 'entry_collected': '59587da28485dfafff311de1472713de8df1a478fc63603d4727786a05eac6f1', 'book_progress': '7da96b97b6a02cf1a0eb702388d0b95d9fc56fcd0e76d94020541a0ba6c7bd58', 'signin_claim': '40169df76f740d4cc97a27e1fe4517285ccf7297c76e6f8e1f0c9c35f049e844'}, 'live': {'week_key': '6186b40d843b641c98f2974f15c3e7dfa39d3fd2fce562b3c684d67552e95bd8', 'week_state': 'c0e570e777aa4757a026be67299acfc4314b983062bda77e3d1cfcb8dd591812', 'week_save': '036b49308609070ae71361cca0997e8f38ffa5a9e10f83bb8ad1e513b5efaf0a', 'supply': '6c570a9d22ec1c14376cefd0866139979d745b4eb489a9e48f3cff2284aa8fea', 'fb_key': '2fbcaa590539526c0ff379a059c0fb7e32fd846076a853a58c6c93b774062773', 'fb_precheck': '99f2cb1f0baf760112fa3f72661c1fe60082d4ecc173090d8d5430bc84c42d5d', 'fb_submit': '753399e7fd0d164a73acfe935df443d9965f63704b7ce5c567fd24bfb4621274', 'ach_panel': '7ddda69a37a7a0cf8b05e8327c0715be81ff14b0072746063adb975f3169c5fe', 'claim_reply': 'e45dbcee7d5db40e6c2882cfc42f746a47ac89b437841fa4397ddaf177ab7131', 'entry_collected': '59587da28485dfafff311de1472713de8df1a478fc63603d4727786a05eac6f1', 'book_progress': '489bf2e994a5b5682e8b97e2295ecf21d80089129ec5ff982f7e9cffd6acd8d3', 'signin_claim': '5993def5bef1ddf037ecd15ea5d3d36d4175449b4e63011dc085860be40571be'}, 'signin_sql': 'b81daaecf3cc9f9deee20387e4a2e2f0a164ed2426ac4ee37b3089e3cb541381'}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _exec_ns(*sources, **globals_):
    """把冻结片段 `exec` 到独立命名空间（**不 import 包内那份**），返回该命名空间。"""
    ns = dict(globals_)
    for src in sources:
        exec(compile(src, "<frozen>", "exec"), ns)              # noqa: S102
    return ns


def _fn_of(src, name, **globals_):
    return _exec_ns(src, **globals_)[name]


# ══════════════════════════════════════════════════════════════════════════════
# [2] 双 sha256
# ══════════════════════════════════════════════════════════════════════════════
def test_hashes():
    print("【2. 双 sha256：冻结片段文本 + 活实现源码】")
    frozen = {
        "week_key": _FROZEN_WEEK_KEY,
        "week_state": _FROZEN_WEEK_STATE,
        "week_save": _FROZEN_WEEK_SAVE,
        "supply": _FROZEN_SUPPLY,
        "fb_key": _FROZEN_FB_KEY,
        "fb_precheck": _FROZEN_FB_PRECHECK,
        "fb_submit": _FROZEN_FB_SUBMIT,
        "ach_panel": _FROZEN_ACH_PANEL,
        "claim_reply": _FROZEN_CLAIM_REPLY,
        "entry_collected": _FROZEN_ENTRY_COLLECTED,
        "book_progress": _FROZEN_BOOK_PROGRESS,
        "signin_claim": _FROZEN_SIGNIN_CLAIM,
    }
    bad = [k for k, v in frozen.items() if _sha256(v) != _PIN["frozen"][k]]
    check(f"冻结片段文本 sha256 全等（{len(frozen)} 段）", not bad, f"不一致={bad}")

    live = {
        "week_key": inspect.getsource(_WP._week_key),
        "week_state": inspect.getsource(_WP._week_state),
        "week_save": inspect.getsource(_WP._save_week_state),
        "supply": inspect.getsource(_EV._claim_supply_box),
        "fb_key": inspect.getsource(_M._fb_cd_key),
        "fb_precheck": inspect.getsource(_M.feedback_precheck),
        "fb_submit": inspect.getsource(_M.feedback_submit),
        "ach_panel": inspect.getsource(_M.achievement_panel),
        "claim_reply": inspect.getsource(_M.claim_reply),
        "entry_collected": inspect.getsource(_LIB.entry_collected),
        "book_progress": inspect.getsource(_LIB.book_progress),
        "signin_claim": inspect.getsource(_SO.signin_claim),
    }
    bad = [k for k, v in live.items() if _sha256(v) != _PIN["live"][k]]
    check(f"inspect.getsource(活实现) sha256 全等（{len(live)} 段）", not bad, f"不一致={bad}")

    check("signin_claim 实跑 SQL 文本 == 冻结的那句（逐字节）",
          _SO._SIGNIN_CLAIM_SQL == _FROZEN_SIGNIN_SQL,
          f"\n      活={_SO._SIGNIN_CLAIM_SQL!r}\n      冻={_FROZEN_SIGNIN_SQL!r}")
    check("signin_claim 实跑 SQL 文本 sha256 钉死",
          _sha256(_SO._SIGNIN_CLAIM_SQL) == _PIN["signin_sql"],
          _sha256(_SO._SIGNIN_CLAIM_SQL))
    check("SQL 里仍带 `WHERE last_date<>?`（不可重领判据在位）",
          "WHERE qq_id=? AND last_date<>?" in _SO._SIGNIN_CLAIM_SQL)
    check("SQL 里仍带 `streak=CASE WHEN last_date=?`（连续段判据在位）",
          "streak=CASE WHEN last_date=? THEN streak+1 ELSE 1 END" in _SO._SIGNIN_CLAIM_SQL)


# ══════════════════════════════════════════════════════════════════════════════
# [3-a] 周期键：全年逐日旧 ↔ 新
# ══════════════════════════════════════════════════════════════════════════════
class _FakeDate(datetime.date):
    """可拨的「今天」（`datetime.date.today()` 的替身）。"""

    _today = datetime.date(2026, 1, 5)

    @classmethod
    def today(cls):
        return cls._today


_DT = types.SimpleNamespace(date=_FakeDate, timedelta=datetime.timedelta)


def _with_fake_today(day):
    _FakeDate._today = day


def test_week_key_full_year():
    print("【3-a. 周键全量：2025-12-01 → 2026-01-31 逐日（含跨年 ISO 周）】")
    old = _fn_of(_FROZEN_WEEK_KEY, "_week_key", datetime=_DT)
    days = [datetime.date(2025, 12, 1) + datetime.timedelta(days=i) for i in range(62)]
    mism = []
    seen = {}
    orig_dt = _WP.datetime
    _WP.datetime = _DT
    try:
        for d in days:
            _with_fake_today(d)
            a, b = old("u1"), _WP._week_key("u1")
            seen[d.isoformat()] = b
            if a != b:
                mism.append((d.isoformat(), a, b))
    finally:
        _WP.datetime = orig_dt
    check(f"逐日周键旧 == 新（{len(days)} 天）", not mism, f"{mism[:3]}")
    check("跨年边界：2025-12-29 → 2026-W01（ISO 周口径未变）",
          seen["2025-12-29"] == "weekly_u1_2026-W01", seen["2025-12-29"])
    check("跨年边界：2026-01-04 → 2026-W01 / 2026-01-05 → 2026-W02",
          (seen["2026-01-04"], seen["2026-01-05"]) == ("weekly_u1_2026-W01", "weekly_u1_2026-W02"),
          (seen["2026-01-04"], seen["2026-01-05"]))
    check("键格式 = weekly_{qq}_{ISO年}-W{周:02d}（逐字冻结）",
          all(v.startswith("weekly_u1_") and "-W" in v and len(v.split("-W")[1]) == 2
              for v in seen.values()))
    _with_fake_today(datetime.date(2026, 1, 5))


def test_week_state_slot():
    print("【3-a′. 周状态键：读/写旧 ↔ 新（同一批原始值）】")
    state = _FakeStore()
    old_ns = _exec_ns(_FROZEN_WEEK_KEY, _FROZEN_WEEK_STATE, _FROZEN_WEEK_SAVE,
                      datetime=_DT, db=state, json=json)
    old_key, old_state, old_save = (old_ns["_week_key"], old_ns["_week_state"],
                                    old_ns["_save_week_state"])
    _with_fake_today(datetime.date(2026, 1, 6))
    orig = (_WP.datetime, _WP.db)
    _WP.datetime, _WP.db = _DT, state
    try:
        raws = [None, "", "{}", '{"tasks":{}}', '{"a":1}', "not-json", "[1,2]",
                '{"tasks":{"x":1}}', '"str"', "0"]
        mism = []
        for raw in raws:
            key = _WP._week_key("q")
            state.d.clear()
            if raw is not None:
                state.d[key] = raw
            a, b = old_state("q"), _WP._week_state("q")
            if a != b:
                mism.append((raw, a, b))
        check(f"坏值/空值/正常值读口旧 == 新（{len(raws)} 例）", not mism, f"{mism[:3]}")
        for st in ({"tasks": {}, "done_n": 0}, {"tasks": {"a": {"prog": 1}}, "done_n": 1}, {"x": 9}):
            state.d.clear()
            old_save("q", dict(st))
            a = dict(state.d)
            state.d.clear()
            _WP._save_week_state("q", dict(st))
            b = dict(state.d)
            if a != b:
                mism.append((st, a, b))
        check("写口旧 == 新（逐字节，含 JSON ensure_ascii=False）", not mism, f"{mism[:3]}")
        state.d.clear()
        _WP._save_week_state("q", {"t": "中文"})
        check("写口落盘仍是 `json.dumps(..., ensure_ascii=False)`（中文不转义）",
              list(state.d.values()) == ['{"t": "中文"}'], state.d)
        check("键逐字：`weekly_{qq}_{ISO年}-W{周:02d}`",
              _WP._week_key("q") == "weekly_q_2026-W02", _WP._week_key("q"))
    finally:
        _WP.datetime, _WP.db = orig
    _with_fake_today(datetime.date(2026, 1, 5))


# ══════════════════════════════════════════════════════════════════════════════
# [3-b] 补给箱：三档 × 日期 × 初值 × 连领三次
# ══════════════════════════════════════════════════════════════════════════════
class _FakeStore:
    """`event_state` 表的最小替身：写口 `str(v)`（与 `persistence.world.set_event_state` 同口径）。"""

    def __init__(self):
        self.d = {}

    def get_event_state(self, key, default=None):
        return self.d.get(key, default)

    def set_event_state(self, key, value):
        self.d[key] = str(value)


class _FakeEnv:
    def __init__(self, uid="u1", group_id="g1"):
        self.uid = uid
        self.group_id = group_id


def _supply_run(which, day, seed, calls=3, boxes=None):
    """旧 / 新各跑一趟「同一天连领 `calls` 次」，返回 (逐次行列表, event_state 终态)。"""
    _with_fake_today(day)
    store = _FakeStore()
    store.d.update(seed)
    env = _FakeEnv()
    orig = (_EV.get_event_state, _EV.set_event_state, _EV.datetime)
    orig_boxes = _EV._SUPPLY_BOX
    _EV.datetime = _DT
    if boxes is not None:
        _EV._SUPPLY_BOX = boxes
    try:
        if which == "old":
            fn = _fn_of(_FROZEN_SUPPLY, "_claim_supply_box",
                        datetime=_DT, T=_T, _SUPPLY_BOX=_EV._SUPPLY_BOX,
                        _grant_items=lambda e, items: list(items),
                        get_event_state=store.get_event_state,
                        set_event_state=store.set_event_state)
        else:
            fn = _EV._claim_supply_box
            _EV.get_event_state, _EV.set_event_state = (store.get_event_state,
                                                        store.set_event_state)
        lines = [fn(env) for _ in range(calls)]
    finally:
        _EV.get_event_state, _EV.set_event_state, _EV.datetime = orig
        _EV._SUPPLY_BOX = orig_boxes
    return lines, dict(store.d)


def _supply_compare(day, seed, calls=3, boxes=None):
    a = _supply_run("old", day, seed, calls, boxes)
    b = _supply_run("new", day, seed, calls, boxes)
    return (a[0] == b[0], a[1] == b[1], a, b)


def test_supply_matrix():
    print("【3-b. 补给箱三档：跨年/跨月/跨周 × 多档初值 × 连领三次】")
    days = [datetime.date(2025, 12, 29), datetime.date(2025, 12, 31),
            datetime.date(2026, 1, 1), datetime.date(2026, 1, 4),
            datetime.date(2026, 1, 5), datetime.date(2026, 1, 11),
            datetime.date(2026, 1, 12), datetime.date(2026, 2, 1),
            datetime.date(2026, 2, 2), datetime.date(2026, 2, 28)]
    line_bad, state_bad, n = [], [], 0
    for day in days:
        monday = (day - datetime.timedelta(days=day.weekday())).isoformat()
        tn = day.isoformat()
        seeds = [
            {},
            {"supply_supply_mat_u1_" + tn: "1"},
            {"supply_supply_tool_u1_" + tn: "1", "supply_supply_mat_u1_" + tn: "1"},
            {"supply_supply_rich_u1_wk_" + monday: "1"},
            {"supply_supply_rich_u1_wk_" + monday: "2"},
            {"supply_supply_rich_u1_wk_" + monday: "2",
             "supply_supply_mat_u1_" + tn: "1",
             "supply_supply_tool_u1_" + tn: "1"},
        ]
        for seed in seeds:
            n += 1
            ok_l, ok_s, a, b = _supply_compare(day, seed)
            if not ok_l:
                line_bad.append((tn, seed, a[0][-1], b[0][-1]))
            if not ok_s:
                state_bad.append((tn, seed, a[1], b[1]))
    check(f"逐行旧 == 新（{n} 例 × 连领 3 次）", not line_bad, f"{line_bad[:2]}")
    check(f"event_state 逐键旧 == 新（{n} 例）", not state_bad, f"{state_bad[:2]}")

    # 三档的分支边界（同一批断言同时钉旧 == 新）
    day = datetime.date(2026, 1, 5)          # 周一
    first = _supply_run("new", day, {}, calls=1)
    text1 = "\n".join(first[0][0])
    check("首次：三档都发放（材料箱/道具箱/豪华箱都在回执里）",
          all(name in text1 for name in ("每日材料箱", "每日道具箱", "每日豪华箱")), first[0][0])
    check("首次：落盘三键 = 两个每日键 `1` + 一个本周键 `1`",
          first[1] == {"supply_supply_mat_u1_2026-01-05": "1",
                       "supply_supply_tool_u1_2026-01-05": "1",
                       "supply_supply_rich_u1_wk_2026-01-05": "1"}, first[1])
    second = _supply_run("new", day, first[1], calls=1)
    check("第二次：每日两档走 `daily_done`、豪华箱走第 2 次发放（本周键 → 2）",
          "每日材料箱" in "\n".join(second[0][0]) and
          second[1]["supply_supply_rich_u1_wk_2026-01-05"] == "2", second[0][0])
    third = _supply_run("new", day, second[1], calls=1)
    check("第三次：豪华箱 `weekly_done`（本周 ≤2 生效）且本周键停在 2",
          any("每日豪华箱" in ln for ln in third[0][0])
          and third[1]["supply_supply_rich_u1_wk_2026-01-05"] == "2", third[0][0])
    check("第三次：`all_done` 兜底分支被走到",
          _T.static("supply.all_done") in third[0][0], third[0][0])
    for tag, seed in (("首次", {}), ("第二次", first[1]), ("第三次", second[1])):
        ok_l, ok_s, a, b = _supply_compare(day, seed, calls=1)
        check(f"{tag}分支：旧 == 新（行 + 状态）", ok_l and ok_s, (a, b))

    # 兜底分支逐条（§6.2：每条兜底分支各一断言）
    empty_new = _supply_run("new", day, {}, calls=1, boxes=[])
    empty_old = _supply_run("old", day, {}, calls=1, boxes=[])
    check("兜底①：档位表为空 → `supply.missing` 单行（旧 == 新）",
          empty_new == empty_old and empty_new[0][0] == [_T.static("supply.missing")],
          empty_new[0][0])
    unknown = [dict(_EV._SUPPLY_BOX[0], limit="nope")]
    unk_new = _supply_run("new", day, {}, calls=1, boxes=unknown)
    unk_old = _supply_run("old", day, {}, calls=1, boxes=unknown)
    check("兜底②：`limit` 不在三档内 → 静默跳过（不发物、一个字节不写），旧 == 新",
          unk_new == unk_old and unk_new[1] == {}
          and _T.static("supply.all_done") in unk_new[0][0], unk_new[0][0])


# ══════════════════════════════════════════════════════════════════════════════
# [3-c] 连续段：真 SQLite 旧 ↔ 新
# ══════════════════════════════════════════════════════════════════════════════
def _db_path():
    getter = getattr(db, "db_path", None)
    return getter() if callable(getter) else db.DB_PATH


def _signin_seq(fn, qq, steps):
    db.init_db()
    conn = sqlite3.connect(_db_path())
    try:
        conn.execute("DELETE FROM signin WHERE qq_id=?", (qq,))
        conn.commit()
    finally:
        conn.close()
    out = [fn("g1", qq, today, yest) for (today, yest) in steps]
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT last_date, streak, total FROM signin WHERE qq_id=?",
                           (qq,)).fetchone()
        got = dict(row) if row else None
    finally:
        conn.close()
    return out, got


_SIGNIN_CASES = {
    "first": [("2026-01-01", "2025-12-31")],
    "consecutive7": [((datetime.date(2026, 1, 1) + datetime.timedelta(days=i)).isoformat(),
                      (datetime.date(2025, 12, 31) + datetime.timedelta(days=i)).isoformat())
                     for i in range(7)],
    "same_day_twice": [("2026-01-01", "2025-12-31"), ("2026-01-01", "2025-12-31")],
    "gap": [("2026-01-01", "2025-12-31"), ("2026-01-05", "2026-01-04")],
    "cross_month": [("2026-01-31", "2026-01-30"), ("2026-02-01", "2026-01-31")],
    "cross_year": [("2025-12-31", "2025-12-30"), ("2026-01-01", "2025-12-31")],
    "wrong_yesterday": [("2026-01-01", "2025-12-31"), ("2026-01-10", "2026-01-09")],
    "streak_reset_then_consecutive": [("2026-01-01", "2025-12-31"),
                                      ("2026-01-03", "2026-01-02"),
                                      ("2026-01-04", "2026-01-03")],
}


def test_signin_matrix():
    print("【3-c. 连续段（streak/total）：真 SQLite 旧 ↔ 新】")
    old_fn = _fn_of(_FROZEN_SIGNIN_CLAIM, "signin_claim", atomic=_SO.atomic)
    bad = []
    for name, steps in _SIGNIN_CASES.items():
        a = _signin_seq(old_fn, "t_old_" + name, steps)
        b = _signin_seq(_SO.signin_claim, "t_new_" + name, steps)
        if a != b:
            bad.append((name, a, b))
    check(f"8 类序列（首次/连续/同日重领/断签/跨月/跨年/错位明天/断后续签）旧 == 新",
          not bad, f"{bad[:2]}")
    out, row = _signin_seq(_SO.signin_claim, "t_probe", _SIGNIN_CASES["consecutive7"])
    check("连续 7 天：streak 1..7 / total 7", [o[1] for o in out] == list(range(1, 8))
          and row == {"last_date": "2026-01-07", "streak": 7, "total": 7}, (out, row))
    out, row = _signin_seq(_SO.signin_claim, "t_probe2", _SIGNIN_CASES["same_day_twice"])
    check("同日第二次：claimed=False 且 streak/total 都是 None（SQL 条件 UPDATE 语义不变）",
          out[1] == (False, None, None) and row["total"] == 1, (out, row))
    out, row = _signin_seq(_SO.signin_claim, "t_probe3", _SIGNIN_CASES["gap"])
    check("断签：streak 归 1，total 继续累加", [o[1] for o in out] == [1, 1] and row["total"] == 2,
          (out, row))


# ══════════════════════════════════════════════════════════════════════════════
# [3-d] 收藏册：5 册全条目 × 名字集合矩阵
# ══════════════════════════════════════════════════════════════════════════════
def test_collection_matrix():
    print("【3-d. 收藏册 N/M：5 册全条目 × 名字集合矩阵】")
    old_ns = _exec_ns(_FROZEN_ENTRY_COLLECTED, _FROZEN_BOOK_PROGRESS, entries=_LIB.entries)
    old_entry, old_prog = old_ns["entry_collected"], old_ns["book_progress"]
    books = _LIB.books()
    check("收藏册读到 5 册（真域）", len(books) == 5, len(books))
    bad, n = [], 0
    for book in books:
        rows = _LIB.entries(book)
        keys = [e.get("key", "") for e in rows]
        names = [e.get("name", "") for e in rows]
        sets = [set(), set(names), set(keys), set(names) | set(keys)]
        for k in range(1, len(rows) + 1):
            sets.append(set(names[:k]))
            sets.append(set(keys[:k]))
            sets.append(set(names[:k]) | set(keys[k:]))
        for inv in sets:
            for best in sets:
                n += 1
                a = old_prog(book, inv, best)
                b = _LIB.book_progress(book, inv, best)
                if a != b:
                    bad.append((book["id"], len(inv), len(best), a, b))
                for e in rows:
                    if old_entry(e, inv, best) != _LIB.entry_collected(e, inv, best):
                        bad.append((book["id"], "entry", e.get("key")))
    check(f"book_progress 旧 == 新（{n} 组名字集合）", not bad, f"{bad[:3]}")
    total_entries = sum(len(_LIB.entries(b)) for b in books)
    check(f"覆盖 5 册全条目（{total_entries} 条）逐条判定", total_entries == 42, total_entries)
    # 空册 / 空集合边界
    check("空册 (0,0) 且 done（口径分歧 ②）",
          _LIB.book_progress({"entries": []}, set(), set()) == (0, 0))
    full = set()
    for b in books:
        for e in _LIB.entries(b):
            full.add(e["name"])
    got_all = [_LIB.book_progress(b, full, set()) for b in books]
    check("全命中：每册 got == total",
          all(g == t for g, t in got_all), got_all)


# ══════════════════════════════════════════════════════════════════════════════
# [3-e] 成就面板 + 领取回执
# ══════════════════════════════════════════════════════════════════════════════
def test_achievement_matrix():
    print("【3-e. 成就面板 + 领取回执：参数矩阵旧 ↔ 新】")
    old_ns = _exec_ns(_FROZEN_ACH_PANEL, _FROZEN_CLAIM_REPLY,
                      ACH_CATS=_M.ACH_CATS, _RW_CN=_M._RW_CN, item_name=_M.item_name)
    old_panel, old_reply = old_ns["achievement_panel"], old_ns["claim_reply"]
    ids = [a["id"] for a in ACHIEVEMENTS]
    check("成就表非空（真域）", len(ids) > 0, len(ids))
    bad, n = [], 0
    for raw in ("", "战斗", "隐藏", "不存在"):
        for unlocked in (set(), set(ids[:3]), set(ids), set(ids[:3]) | {"inst_clear_x"}):
            for claimed in (set(), {ids[0]}, set(ids)):
                for points in (0, 7):
                    n += 1
                    a = old_panel(raw, ACHIEVEMENTS, unlocked, claimed, points)
                    b = _M.achievement_panel(raw, ACHIEVEMENTS, set(unlocked), set(claimed), points)
                    if a != b:
                        bad.append((raw, len(unlocked), len(claimed), points,
                                    [x for x in a if x not in b][:2],
                                    [x for x in b if x not in a][:2]))
    check(f"面板逐行旧 == 新（{n} 组参数）", not bad, f"{bad[:1]}")
    check("领取回执旧 == 新（空 err / 非空 err）",
          all(old_reply(*c) == _M.claim_reply(*c)
              for c in ((["a", "b"], ""), ([], "没有待领取的成就奖励～"), ([], None))),
          "")
    # 关键标记：可领 🎁 / 未达成 ⬜ / 已领 ✅（用真表第一项构造；标记只在「按分类」分支逐条渲染）
    a0 = ACHIEVEMENTS[0]
    cat0 = a0["cat"]
    ready = _M.achievement_panel(cat0, ACHIEVEMENTS, {a0["id"]}, set(), 0)
    if a0.get("reward"):
        check("达成未领 → 🎁（可领标记口径不变）",
              any(ln.startswith("🎁") and a0["name"] in ln for ln in ready), ready[:4])
    claimed = _M.achievement_panel(cat0, ACHIEVEMENTS, {a0["id"]}, {a0["id"]}, 0)
    check("达成已领 → ✅", any(ln.startswith("✅") and a0["name"] in ln for ln in claimed),
          claimed[:4])
    locked = _M.achievement_panel(cat0, ACHIEVEMENTS, set(), set(), 0)
    check("未达成 → ⬜", any(ln.startswith("⬜") and a0["name"] in ln for ln in locked), locked[:4])


# ══════════════════════════════════════════════════════════════════════════════
# [3-f] 意见箱频控
# ══════════════════════════════════════════════════════════════════════════════
class _FakeFeedbackDB(_FakeStore):
    def add_feedback(self, qq_id, group_id, args):
        return "F1"


def test_feedback_matrix():
    print("【3-f. 意见箱频控（末次触达 + 30s 窗口）旧 ↔ 新】")
    store = _FakeFeedbackDB()
    old_ns = _exec_ns(_FROZEN_FB_KEY, _FROZEN_FB_PRECHECK, _FROZEN_FB_SUBMIT,
                      db=store, MSG_EMPTY=_M.MSG_EMPTY, MSG_TOO_LONG=_M.MSG_TOO_LONG,
                      MSG_TOO_FAST=_M.MSG_TOO_FAST, FEEDBACK_CD_SECONDS=_M.FEEDBACK_CD_SECONDS,
                      FEEDBACK_MAX_LEN=_M.FEEDBACK_MAX_LEN)
    old_pre, old_sub = old_ns["feedback_precheck"], old_ns["feedback_submit"]
    _orig_db = _M.db
    _M.db = store
    try:
        bad, n = [], 0
        for last in (None, "", "0", "abc", "1000.5", "1000", " 1000 "):
            for now in (1000.0, 1029.9, 1030.0, 1030.1, 2000.0):
                n += 1
                key = "fb_cd_qq1"
                for args in ("", "x" * 201, "正常意见"):
                    store.d.clear()
                    if last is not None:
                        store.d[key] = last
                    a = old_pre(args, "qq1", now)
                    store.d.clear()
                    if last is not None:
                        store.d[key] = last
                    b = _M.feedback_precheck(args, "qq1", now)
                    if a != b:
                        bad.append((last, now, args[:4], a, b))
        check(f"precheck 旧 == 新（{n} 组 × 3 种参数）", not bad, f"{bad[:3]}")
        store.d.clear()
        store.d["fb_cd_qq1"] = "1000.0"
        a = old_sub("g1", "qq1", "hi", 1030.5)
        a_state = dict(store.d)
        store.d.clear()
        store.d["fb_cd_qq1"] = "1000.0"
        b = _M.feedback_submit("g1", "qq1", "hi", 1030.5)
        b_state = dict(store.d)
        check("submit 回执与落盘时间戳旧 == 新", a == b and a_state == b_state,
              (a, a_state, b, b_state))
        check("时间戳落盘 = `str(now_ts)`（逐字节）", b_state["fb_cd_qq1"] == "1030.5", b_state)
    finally:
        _M.db = _orig_db


# ══════════════════════════════════════════════════════════════════════════════
# [4] 零知识静态扫描
# ══════════════════════════════════════════════════════════════════════════════
_VALUE_WORDS = ("签到", "收藏册", "成就", "金币", "补给箱", "奥兰迪亚", "余烬",
                "破绽", "每日", "每周", "周一", "时区")
_CALENDAR_MODULES = ("datetime", "time", "calendar", "zoneinfo", "dateutil")


def _scan_engine_module(path):
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src, filename=path)
    hits, imports = [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for w in _VALUE_WORDS:
                if w in node.value:
                    hits.append((node.lineno, w, node.value[:40]))
        if isinstance(node, ast.Import):
            imports += [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if not node.level:
                imports.append((node.module or "").split(".")[0])
    return hits, imports


def test_zero_knowledge():
    print("【4. 零知识静态扫描（ast 扫新引擎模块的全部字符串常量 + import）】")
    check("注册表：本批两个形状**没有**注册表（无类型/动词/策略登记面，故无登记表断言）",
          not any(hasattr(m, n) for m in (_PE, _PC)
                  for n in ("register", "REGISTRY", "_REGISTRY", "register_type")),
          [n for m in (_PE, _PC) for n in ("register", "REGISTRY") if hasattr(m, n)])
    for rel in ("extends/ext_life/periodic/__init__.py", "extends/ext_life/collect/__init__.py"):
        path = os.path.join(_paths.ENGINE_ROOT, *rel.split("/"))
        hits, imports = _scan_engine_module(path)
        check(f"{rel}：零内容侧取值词（{len(_VALUE_WORDS)} 词表）", not hits, f"{hits[:3]}")
        bad_imp = sorted(set(imports) & set(_CALENDAR_MODULES))
        check(f"{rel}：零日历/时间模块 import（引擎不认识日历）", not bad_imp, bad_imp)
        # ★ 2026-09-23 第 4 批：这些形状搬进扩展包后要引引擎通用件（_validators 等）——
        #   判据放宽为「标准库 + 引擎包 saintess_engine」，仍然挡住任何第三方依赖。
        check(f"{rel}：只 import 标准库 + 引擎通用件",
              not [i for i in imports
                   if i not in sys.stdlib_module_names and not i.startswith("saintess_engine")],
              imports)


# ══════════════════════════════════════════════════════════════════════════════
# [5] 口径分歧断言
# ══════════════════════════════════════════════════════════════════════════════
def test_divergences():
    print("【5. 口径分歧断言（有意不统一处）】")
    check("① `Tally.done` 对空表为 True（= 包内 `got == total` 口径）",
          _PC.Tally([], hit=lambda r: True).done is True)
    check("① 空表 got/total = (0, 0)",
          _PC.Tally([], hit=lambda r: True).progress() == (0, 0))
    check("② 达成但无物可领 → CLAIMED（三态里没有第四态）",
          _PC.tier_state(reached=True, claimed=False, claimable=False) == _PC.CLAIMED)
    check("② 未达成 → LOCKED / 已领 → CLAIMED / 达成可领 → READY",
          (_PC.tier_state(reached=False, claimed=False),
           _PC.tier_state(reached=True, claimed=True),
           _PC.tier_state(reached=True, claimed=False)) ==
          (_PC.LOCKED, _PC.CLAIMED, _PC.READY))
    check("② 未达成**优先于**已领（两份输入自相矛盾时按 LOCKED 算 = 包内 `✅ if 已解锁 else ⬜`）",
          _PC.tier_state(reached=False, claimed=True) == _PC.LOCKED)
    store = _FakeStore()
    store.d["k"] = "0"
    counter = _PE.PeriodCounter(store.get_event_state, store.set_event_state, "k")
    check("③ 首次触达 = 「键下没有任何记录」：存档里是字面量 `0` 时算**已触达**",
          counter.first_touch() is False and counter.used() == 0, (counter.first_touch(), counter.used()))
    store2 = _FakeStore()
    check("③ 键缺失时首次触达 True / 计数 0",
          _PE.PeriodCounter(store2.get_event_state, store2.set_event_state, "k").first_touch() is True)
    st = _PE.Streak()
    try:
        st.next_value("2026-01-01", "2026-01-01", "2025-12-31", 3)
        ok = False
    except ValueError:
        ok = True
    check("④ 同一周期已认领 → `Streak.next_value` 显式报错（不可重领）", ok)
    check("④ 连续 → +step；断签 → reset_to",
          (st.next_value("2026-01-01", "2026-01-02", "2026-01-01", 6),
           st.next_value("2025-12-20", "2026-01-02", "2026-01-01", 6)) == (7, 1))


# ══════════════════════════════════════════════════════════════════════════════
# [6] 视图 / 序列化
# ══════════════════════════════════════════════════════════════════════════════
def test_views_json():
    print("【6. 视图/序列化（纯 JSON 可 dumps + 往返）】")
    tiers = [{"key": "a", "need": 1}, {"key": "b", "need": 2}]
    claimed = {"a"}
    board = _PC.TierBoard(tiers, claimed=claimed, key=lambda t: t["key"],
                          reached=lambda t: t["need"] <= 2)
    views = {
        "states": board.states(),
        "counts": board.counts(),
        "progress": _PC.Tally(tiers, hit=lambda t: t["key"] in claimed).progress(),
        "slot": _PE.PeriodSlot(lambda k: "v", lambda k, v: None, "k").read(),
    }
    dumped = {k: json.dumps(v, ensure_ascii=False) for k, v in views.items()}
    check("states/counts/progress/read 都可 json.dumps",
          all(isinstance(v, str) for v in dumped.values()), dumped)
    check("往返相等",
          all(json.loads(dumped[k]) == json.loads(json.dumps(v)) for k, v in views.items()))
    check("states 值域 ⊂ {locked, ready, claimed}",
          set(views["states"].values()) <= {_PC.LOCKED, _PC.READY, _PC.CLAIMED},
          views["states"])
    check("counts 三态齐全且合计 = 档位数",
          set(views["counts"]) == {_PC.LOCKED, _PC.READY, _PC.CLAIMED}
          and sum(views["counts"].values()) == len(tiers), views["counts"])


# ══════════════════════════════════════════════════════════════════════════════
# [7]/[8] 有牙反证 + 多故障场景
# ══════════════════════════════════════════════════════════════════════════════
def _probe_supply():
    """补给箱旧 ↔ 新是否出现差异（True = 坏了）。"""
    day = datetime.date(2026, 1, 5)
    tn = day.isoformat()
    for seed in ({}, {"supply_supply_mat_u1_" + tn: "1"},
                 {"supply_supply_rich_u1_wk_2026-01-05": "2"}):
        ok_l, ok_s, _a, _b = _supply_compare(day, seed)
        if not (ok_l and ok_s):
            return True
    return False


def _probe_signin():
    old_fn = _fn_of(_FROZEN_SIGNIN_CLAIM, "signin_claim", atomic=_SO.atomic)
    try:
        for name, steps in _SIGNIN_CASES.items():
            if _signin_seq(old_fn, "m_o_" + name, steps) != _signin_seq(_SO.signin_claim,
                                                                       "m_n_" + name, steps):
                return True
    except Exception:                                        # noqa: BLE001
        return True
    return False


def _probe_collection():
    old_ns = _exec_ns(_FROZEN_ENTRY_COLLECTED, _FROZEN_BOOK_PROGRESS, entries=_LIB.entries)
    for book in _LIB.books():
        rows = _LIB.entries(book)
        inv = {e.get("name", "") for e in rows[:3]}
        if old_ns["book_progress"](book, inv, set()) != _LIB.book_progress(book, inv, set()):
            return True
    return False


def _probe_ach():
    old_ns = _exec_ns(_FROZEN_ACH_PANEL, _FROZEN_CLAIM_REPLY,
                      ACH_CATS=_M.ACH_CATS, _RW_CN=_M._RW_CN, item_name=_M.item_name)
    ids = [a["id"] for a in ACHIEVEMENTS]
    for unlocked, claimed in ((set(ids[:3]), set()), (set(ids), {ids[0]}), (set(), set())):
        a = old_ns["achievement_panel"]("", ACHIEVEMENTS, unlocked, claimed, 3)
        b = _M.achievement_panel("", ACHIEVEMENTS, set(unlocked), set(claimed), 3)
        if a != b:
            return True
    return False


def _probe_fb():
    store = _FakeFeedbackDB()
    old_ns = _exec_ns(_FROZEN_FB_KEY, _FROZEN_FB_PRECHECK, _FROZEN_FB_SUBMIT,
                      db=store, MSG_EMPTY=_M.MSG_EMPTY, MSG_TOO_LONG=_M.MSG_TOO_LONG,
                      MSG_TOO_FAST=_M.MSG_TOO_FAST, FEEDBACK_CD_SECONDS=_M.FEEDBACK_CD_SECONDS,
                      FEEDBACK_MAX_LEN=_M.FEEDBACK_MAX_LEN)
    _orig_db = _M.db
    _M.db = store
    try:
        for last, now in ((None, 1000.0), ("1000", 1029.9), ("1000", 1030.0), ("abc", 5.0)):
            for args in ("", "正常"):
                store.d.clear()
                if last is not None:
                    store.d["fb_cd_q"] = last
                a = old_ns["feedback_precheck"](args, "q", now)
                store.d.clear()
                if last is not None:
                    store.d["fb_cd_q"] = last
                b = _M.feedback_precheck(args, "q", now)
                if a != b:
                    return True
    finally:
        _M.db = _orig_db
    return False


class _Patch:
    """猴补上下文（进入记原值，退出原地还原；**不写盘**）。"""

    def __init__(self, obj, name, value):
        self.obj, self.name, self.value = obj, name, value
        self.had = hasattr(obj, name)
        self.old = getattr(obj, name, None)

    def __enter__(self):
        setattr(self.obj, self.name, self.value)
        return self

    def __exit__(self, *exc):
        if self.had:
            setattr(self.obj, self.name, self.old)
        else:
            delattr(self.obj, self.name)
        return False


def _break_signin():
    return _Patch(_SO, "_SIGNIN_CLAIM_SQL", _SO._SIGNIN_CLAIM_SQL.replace("streak+1", "streak+5"))


def _break_supply():
    # 破坏周期计数：`used()` 恒 0 ⇒ 每周上限（≤2）再也拦不住（补给箱行为必须变）
    return _Patch(_PE.PeriodCounter, "used", lambda self: 0)


def _break_collection():
    return _Patch(_LIB, "entry_collected", lambda entry, inv, best: True)


def _break_ach():
    # 破坏引擎三态机：把所有「达成」都当成未达成 ⇒ 面板 🎁/待领计数必变
    return _Patch(_PC, "tier_state",
                  lambda reached, claimed, claimable=True:
                  _PC.CLAIMED if claimed else _PC.LOCKED)


def _break_fb():
    class _AlwaysReady:
        def ready(self, now):
            return True

        def touch(self, now):
            return None
    return _Patch(_M, "_fb_cd", lambda qq_id: _AlwaysReady())


_BREAKS = {
    "signin_sql": (_break_signin, _probe_signin),
    "supply_cap": (_break_supply, _probe_supply),
    "collection_hit": (_break_collection, _probe_collection),
    "achievement_claimable": (_break_ach, _probe_ach),
    "feedback_ready": (_break_fb, _probe_fb),
}


def test_teeth():
    print("【7. 有牙反证：猴补破坏 3 处 → 门禁必须变红（跑完原地还原）】")
    files = ["content/cmds_event.py", "content/misc_cmds.py", "content/flow/weekly_progress.py",
             "content/persistence/social.py", "content/achievements.py", "content/collection.py"]
    before = {f: _sha256(open(os.path.join(_paths.PKG_ROOT, *f.split("/")), encoding="utf-8")
                         .read()) for f in files}
    for name, (breaker, probe) in _BREAKS.items():
        check(f"反证：未破坏时 `{name}` 探针为 False（真实现成立）", probe() is False)
    for name in ("signin_sql", "supply_cap", "collection_hit"):
        breaker, probe = _BREAKS[name]
        with breaker():
            check(f"反证：破坏 `{name}` → 探针必须变红", probe() is True)
        check(f"反证：还原 `{name}` 后探针回绿", probe() is False)
    after = {f: _sha256(open(os.path.join(_paths.PKG_ROOT, *f.split("/")), encoding="utf-8")
                        .read()) for f in files}
    check("全程零写盘：6 个源文件 sha256 前后一致", before == after,
          [f for f in files if before[f] != after[f]])


def test_multi_fault():
    print("【8. 多故障场景：3 条「两处同时坏」+ 1 条顺序断言】")
    pairs = [
        ("signin_sql", "supply_cap"),
        ("collection_hit", "achievement_claimable"),
        ("supply_cap", "feedback_ready"),
    ]
    for a, b in pairs:
        with _BREAKS[a][0](), _BREAKS[b][0]():
            ra, rb = _BREAKS[a][1](), _BREAKS[b][1]()
        check(f"两处同时坏（{a} + {b}）：两条断言各管一段，都变红",
              ra is True and rb is True, (ra, rb))
        check(f"两处同时坏（{a} + {b}）：还原后两条都回绿",
              _BREAKS[a][1]() is False and _BREAKS[b][1]() is False, "")
    with _BREAKS["supply_cap"][0](), _BREAKS["signin_sql"][0]():
        r1, r2, r3 = _BREAKS["supply_cap"][1](), _BREAKS["signin_sql"][1](), _probe_collection()
    check("两处同时坏时**第三处**仍绿（证明不是「一个探针管全部」）",
          r1 is True and r2 is True and r3 is False, (r1, r2, r3))

    print("  ── 顺序断言 ──")
    store = _FakeStore()
    store.d["c"] = "1"
    counter = _PE.PeriodCounter(store.get_event_state, store.set_event_state, "c")
    raised = False
    try:
        counter.consume(cap=1)
    except _PE.PeriodLimitExceeded:
        raised = True
    check("顺序①：`consume` **先判后写** —— 超上限抛错且存储一个字节未动",
          raised and store.d == {"c": "1"}, store.d)

    # 顺序②：发放行序 = 档位声明序，且门禁对行序敏感（倒序档位表必须改变行序）
    day = datetime.date(2026, 1, 5)
    ok_l, ok_s, a, b = _supply_compare(day, {})
    order_ok = (a[0] == b[0])
    boxes = list(_EV._SUPPLY_BOX)
    names = [bx["name"] for bx in boxes]

    def _box_seq(lines):
        out = []
        for ln in lines:
            for nm in names:
                if nm in ln:
                    out.append(nm)
        return out

    fwd = _box_seq(_supply_run("new", day, {}, boxes=list(boxes))[0][0])
    rev_boxes = list(reversed(boxes))
    rev = _box_seq(_supply_run("new", day, {}, boxes=rev_boxes)[0][0])
    check("顺序②：三档发放行序 = 档位声明序（旧 == 新）",
          order_ok and fwd == names, (order_ok, fwd, names))
    check("顺序②′：倒序档位表 → 行序**随之倒过来**（门禁真的在看行序，不是碰巧相等）",
          rev == list(reversed(names)) and fwd != rev, (fwd, rev))


def main() -> int:
    print("==" * 36)
    print("U1-I3 冻结门禁：周期形状（periodic）+ 收集形状（collect）")
    print("==" * 36)
    test_hashes()
    test_week_key_full_year()
    test_week_state_slot()
    test_supply_matrix()
    test_signin_matrix()
    test_collection_matrix()
    test_achievement_matrix()
    test_feedback_matrix()
    test_zero_knowledge()
    test_divergences()
    test_views_json()
    test_teeth()
    test_multi_fault()
    print(f"\n{'-' * 46}\n结果：通过 {PASS} / 共 {PASS + FAIL}")
    if FAILURES:
        print("失败项：")
        for f in FAILURES:
            print("  ❌", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
