#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""门禁：战斗日志 cue 的**内容半边**（★ R1 · 2026-09-28，C 车道 `c-r2`）。

引擎侧 B1–B6 把「战斗结算里顺手拼一句玩家文案」改成**发表现事件**（cue），并把引擎自己的
兜底模板**删净**（B2 起）⇒ 内容侧不接，整场战斗的每一行都只出
「⚠️ 这条表现没渲染出来（cue 装配/文案缺口，见诊断）」。本文件盯的就是那半边接线。

  [1] **单一真源**：订阅表**不抄第二份名单** —— 装配期现读引擎
      `ext_combat.battle.cues.CUE_NAMES`（引擎加一条点位，本包自动跟上）。
      本包格子的键与 cue 名**同名**（同名即接口，不造映射表）。
  [2] **两个口都装了**：`cue_subs_fn`（订阅表）与 `text_table_fn`
      （`Battle(...)` 没显式传 `text=` 时引擎要的那张表）。
      ★ **两个都必需**：只装前一个 ⇒ 包自己的入口 / 测试直接 `Battle(...)` 时 `self.text is None`
      ⇒ 总线建成空表 ⇒ 每条 cue 一样只出坏数据行（本批实测踩过这一脚）。
  [3] **逐条渲染 62 条 cue** —— 判据是「出了话、不是坏数据行、槽位被填上」，
      **不是**「表里有这一格」（本批 13 支红最初就栽在只看后者）。
  [4] **反证有牙（fail-closed 没被放宽）**：
      ① 摘掉某一格 ⇒ 装配期**当场抛**并**点名是哪条 cue**（不静默丢行）；
      ② 猴补一个假 cue 名进 `CUE_NAMES` ⇒ 同样当场抛（证明按引擎名单逐条对账）。
  [5] **静态守卫**：那 62 句整句不许出现在 `content/*.py` 里（真源只有文案表），
      且 `content/cues.py` 零中文文案字面量。

跑法：python tests/test_battle_cue_text.py（exit=0 全绿）
"""
from __future__ import annotations

import ast
import io
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _paths  # noqa: E402

os.environ.setdefault("GWEN_GAME_DB", os.path.join(_paths.TESTS_DIR, "test_battle_cue_text.db"))

from _check import bind_check                    # noqa: E402
from _engine_harness import boot                 # noqa: E402

passed = 0
failed = 0
check = bind_check(globals(), "passed", "failed")

boot()                                            # 引擎 Host + 包内装配（import 即装，幂等）

from saintess_engine import config as CFG         # noqa: E402
from content import apply as A                    # noqa: E402
from content import battle_text as BT             # noqa: E402
from content import cues as CUES                 # noqa: E402
from content import texts as T                    # noqa: E402
from ext_combat.battle import cues as ECUES      # noqa: E402
from saintess_engine.text import TextTable       # noqa: E402

#: 引擎那条坏数据行 —— **它出现 = 这次 cue 没画出来**（接线失败的现场）
MISS_LINE = "⚠️ 这条表现没渲染出来"

_CONTENT = os.path.join(_paths.PKG_ROOT, "content")


# ══════════════════════════════════════════════════════════════
# [1] 单一真源：订阅表 = 引擎 `CUE_NAMES` 现读
# ══════════════════════════════════════════════════════════════
def t1_single_source():
    print("\n[1] 单一真源（cue 名单不抄第二份）")
    names = CUES.cue_names()
    check("cue 名单 == 引擎 CUE_NAMES（现读，不是 import 期绑定）",
          tuple(names) == tuple(ECUES.CUE_NAMES),
          "%d vs %d" % (len(names), len(ECUES.CUE_NAMES)))
    subs = CUES.subs()
    check("订阅表条数 == 引擎名单条数（多一条即装配期对账该抛）",
          len(subs) == len(ECUES.CUE_NAMES), len(subs))
    check("每条订阅都是单个 kind=text、key 与 cue 名同名",
          all(v == (({"kind": "text", "key": n},)) for n, v in subs.items()), "")
    # ★ 判据查的是「有没有**抄 cue 名单**」，不是「有没有 battle 这个词」——
    #   `ext_combat.battle.cues`（引擎模块路径）里就有 `battle.`，那是取件口不是名单。
    #   口径 = 任何**字符串字面量**里都不许出现一个 cue 名的形状
    #   （`battle.<域>.<事件>` 整串出现 ⇒ 抄了名单）。
    src_cues = _src_of(CUES.__file__)
    lit = [n.value for n in ast.walk(ast.parse(src_cues))
           if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    copied = [s for s in lit if re.search(r"battle\.[a-z_]+\.[a-z_]+", s)]
    check("`content/cues.py` 的字符串字面量里没有 cue 名（名单不抄第二份）",
          not copied, copied[:5])
    check("格子映射同名即接口（cue 名 → texts 槽位名，无映射表）",
          all(k == v for k, v in BT.slots().items()), "")


# ══════════════════════════════════════════════════════════════
# [2] 两个口都装了
# ══════════════════════════════════════════════════════════════
def t2_mounted():
    print("\n[2] 装配（两个口都要）")
    check("`cue_subs_fn` 已挂上（订阅表）",
          CFG.optional_hook("cue_subs_fn") is not None, "")
    check("`text_table_fn` 已挂上（Battle 没显式传 text= 时引擎要的那张表）",
          CFG.optional_hook("text_table_fn") is not None, "")
    check("两个口取到的表是同一张（不新增第二份真源）",
          CFG.optional_hook("cue_subs_fn")() is not None
          and CFG.optional_hook("text_table_fn")() is BT.table(), "")
    src = _src_of(A.__file__)
    check("装配点写在 `content/apply.py::install_engine`（不在 import 期读数据）",
          "cue_subs_fn=" in src and "text_table_fn=" in src, "")
    check("装完回读一次（有 cue 形状却没挂上 ⇒ 当场抛，不静默忽略）",
          "engine_has_cues()" in src, "")


# ══════════════════════════════════════════════════════════════
# [3] 逐条渲染（判据 = 出了话 + 不是坏数据行 + 槽位被填）
# ══════════════════════════════════════════════════════════════
#: 每条 cue 的 payload 槽位从**引擎调用点**现取形状；这里给一组覆盖全部槽位名的样例值。
_PAYLOAD = {
    "name": "试炼者", "dmg": 7, "heal": 3, "value": 5, "red": 2, "absorb": 4,
    "pct": 20, "element": "火", "guard": "铁卫", "target": "试炼者", "turns": 3,
    "key": "试炼者", "n": 2, "cap": "（上限 5）", "amount": 1, "left": 2,
    "cur": 1, "names": "试炼者", "op": "+", "mult": "1.2", "tag": "冰封",
    "action": "未知", "bar": "磐核", "add": 5, "val": 10, "maxcap": 125,
    "count": 1, "before": 30, "after": 20, "mult_pct": 15, "rv": 5, "rk": "核心",
}


def t3_render_every_cue():
    print("\n[3] 逐条渲染（62 条 cue 真跑一遍）")
    tbl = BT.table()
    slots = BT.slots()
    not_declared, bad_line, unfilled = [], [], []
    for cue in sorted(slots):
        if cue not in tbl:
            not_declared.append(cue)
            continue
        line = tbl.render_or(cue, "", **_PAYLOAD)
        if MISS_LINE in line:
            bad_line.append(cue)
            continue
        left = re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)[^}]*\}", line)
        if left:
            unfilled.append((cue, left))
    check("62 条 cue 全部在表里（一条不缺）", not not_declared, not_declared[:5])
    check("62 条 cue 逐条渲染**没有一条**落坏数据行", not bad_line, bad_line[:5])
    check("62 条 cue 渲染后**没有残留占位符**（槽位被真的填上）", not unfilled, unfilled[:5])
    sample = tbl.render_or("battle.landing.damage", "", name="试炼者", dmg=7)
    check("渲染出的是玩家话（不是机器键、不是英文占位）",
          "试炼者" in sample and "{" not in sample, sample)


# ══════════════════════════════════════════════════════════════
# [4] 反证有牙：缺格 / 多一条 cue ⇒ 装配期点名抛
# ══════════════════════════════════════════════════════════════
# ★ 反证**只动进程内的表**，不写 `content/data/text_specs.json`：
#   那份文件是**全仓共享**的（全量跑器并发跑，别处也在读它）—— 本批第一版在这改盘，
#   并发下被别人读到半张表 ⇒ 出现「撤补后少一条」这种**假红**（自己造成的）。
#   口径不变：验的是「缺一格 / 多一条 cue ⇒ 装配期点名抛」，只是换成**进程内替身表**。
def t4_reverse_proof():
    print("\n[4] 反证（fail-closed 没被放宽）")
    global _N0
    _N0 = len(CUES.cue_names())          # 起点值：撤补后必须回到这里
    real_get = BT._spec_table

    # ① 摘掉某一格 ⇒ 当场抛，且**点名是哪条 cue**
    def _thinned():
        t = real_get()
        d = dict(t._specs)
        d.pop("battle.gauge.reflect", None)
        return TextTable(d, name="probe.thin")

    BT._spec_table = _thinned
    BT._CACHE.pop("table", None)
    try:
        CUES.check_domain()
        check("摘掉一格后 `check_domain()` 当场抛（不静默丢行）", False, "没抛")
    except CUES.CueSubsError as e:
        msg = str(e)
        check("摘掉一格后 `check_domain()` 当场抛（不静默丢行）", True, "")
        check("抛出的消息**点名**是哪条 cue（不是「某个格子」）",
              "battle.gauge.reflect" in msg, msg[:140])
    finally:
        BT._spec_table = real_get
        BT._CACHE.pop("table", None)

    check("补回后逐字回到全绿（同一处，不是新表）", not BT.missing_slots(),
          BT.missing_slots()[:3])

    # ② 猴补一个假 cue 名进 `CUE_NAMES` ⇒ 同样当场抛
    _add_fake_cue("battle.fake.probe")
    try:
        BT._CACHE.pop("slots", None)
        CUES.check_domain()
        check("引擎名单多一条而本包没补 ⇒ 当场抛（不是「认表里有的那几条」）",
              False, "没抛")
    except CUES.CueSubsError as e:
        check("引擎名单多一条而本包没补 ⇒ 当场抛（不是「认表里有的那几条」）", True, "")
        check("抛出的消息点名那个假 cue 名", "battle.fake.probe" in str(e), str(e)[:140])
    finally:
        _drop_fake_cue()
        BT._CACHE.pop("slots", None)
        BT._CACHE.pop("table", None)

    _n = len(CUES.cue_names())
    # ★ 判据 = 「**回到本测试开始时那个数**」，不是硬写 62 ——
    #   引擎侧可能正被并发推进（cue 名随批次增长），把绝对值钉死在 62
    #   会在引擎加一条点位那天变成**假红**。本测试的责任是「不许自己改坏它」。
    check("撤补后回到**本测试开始时**那个数（自己没把它改坏）",
          _n == _N0, "start=%d now=%d" % (_N0, _n))
    check("引擎侧 cue 名一条没少（撤补是真还原，不是少一条）",
          set(_CUE_SAVED.get("names") or ()) == set(ECUES.CUE_NAMES),
          "saved=%d engine=%d" % (len(_CUE_SAVED.get("names") or ()),
                                    len(ECUES.CUE_NAMES)))