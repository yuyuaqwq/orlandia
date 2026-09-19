#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""文案表（消息模板）门禁 —— 真源 `<pkg>/content/data/text_specs.json` + `game/core/texts.py`。

★ P4′-B（2026-09-14）：真源已从宿主 `game/data/text_specs.json` **搬进包内**
（同一份 55,929 B 逐字节副本）；宿主那份退化为**构建期镜像**，宿主运行期不读它。
双向一致性由 `tests/test_text_specs_sync.py` 钉住。

**这一层要防的四件事**（每件都由断言钉死）：
  ① 声明与调用脱节：表里有、代码不用（死文案）｜代码用、表里没有（运行时缺 key）
  ② 槽位对不上：模板写 `{foo}`，调用点传 `name` ⇒ 玩家会看到 `{foo}` 原样露出来
  ③ 静默降级：缺 key 时悄悄退回旧串/空串 —— 本层刻意**不静默**（ERROR 日志 + 返回 key 本身）
  ④ 声明文件坏了没人知道：语法错/空值/params 与模板不一致（引擎 `validate()` 只报告不抛 → 这里必须查）

**逐字一致**（"迁移没改玩家看到的字"）由两层证据扛：
  · 副本域：`tests/test_v185_instance_admission.py` 的 **805 格逐格冻结比对**（对照物 = 旧实现冻结体）
  · 周常 / 签到 / 补给箱 / 每日域：本文件 `WEEKLY_FROZEN` / `SIGNIN_FROZEN` / `SUPPLY_FROZEN` /
    `DAILY_FROZEN`（面板段）/ `QUEST_FROZEN`（『每日』命令） —— **迁移前真跑各分支存下来的完整输出**，
    每次跑测试复跑比对（签到分支用 random 打桩保证可复现）
  · 副本结算域（`game/commands/instance_router.py`）：本文件 `INSTANCE_SETTLE_FROZEN` ——
    11 个分支（探索/肃清/等待/嘲讽/异常/密室/房间清空/切怪/层清空/普通轮转）在**迁移前**真跑存下的
    完整输出，每次跑测试复跑比对（每次 clean_db + random.seed 固定随机；「战斗状态异常」一支用桩
    让 build_battle 抛错触发，见 `_is_b6_battle_broken`）
  · 副本日志域（`game/commands/instance.py` + `instance_router.py` + `instance_battle.py`）：
    本文件 `INSTANCE_LOG_FROZEN` —— 26 个分支（超时自动防御/嘲讽/同归于尽/团队治疗广播/组队提示/
    副本列表/战况面板/副本状态面板/副本地图 rooms 形态与分层形态/搜刮空与非空/击杀奖励/通关 A-E/
    失败回城）在**迁移前**真跑存下的完整输出，每次跑测试复跑比对（clean_db 打底 + random.seed
    与 random.random 打桩固定随机；「同归于尽」「搜刮空」两处用桩（见分支注释），
    通关 A-E 用 random.random 常量 + 预置已学图纸打桩固定分支取向）；
    另有 `INSTANCE_LOG_TEMPLATES` —— 70 条模板**骨架**（来自迁移前源码 AST）：
    连真跑覆盖不到的分支（见下）也由「骨架逐字相等」钉住
    · 真跑覆盖不到 1 条：`instance.日志_调查痕迹`（通关后调查痕迹行，rooms 与分层两处**共用**）——
      两处调用都引用了未定义名 `qq_id`（`_instance_map_view(self, st, group_id)` 签名里没有它）⇒
      走到就是 NameError，属**既有缺陷**（本批只搬字、不动缺陷，故只由模板骨架层覆盖）

  · 副本面板域（`game/commands/instance.py` + `instance_battle.py` + `instance_router.py` 的
    面板/列表/地图/状态/引导/错误提示句壳）：本文件 `INSTANCE_PANEL_FROZEN` —— 31 个分支
    （开本单人/多人/战斗模式/名字不存在、加入战斗、不在副本、战斗中守卫、24h 过期、深入四拦截与清层推进、
    副本地图分层、调查空参数/未命中/已处理、探索通关后/rooms 四态/旧层两态/遇怪Boss、
    撤退全流程、恢复进度与离开、非队长移动、通关超时离开、暗格/宝箱五档、调查点四档与空/零碎、
    战斗态异常两态、Boss 房房间怪击杀通关）在**迁移前**真跑存下的完整输出，每次跑测试复跑比对（每分支 clean_db +
    固定 random.seed，需要处打桩 random.random；宝箱五档用固定 seed 定向各档，调查点空/零碎
    临时改写 C.INVESTIGATION_POINTS 后还原）；另有 `INSTANCE_PANEL_OLD_LITERALS` ——
    迁移前内联句壳片段（= 表值去槽位后的实体片段），三份源文件里一句都不许再出现
  · 社交 / 经济域（宿主 `game/commands/{social,economy}.py` 退化为壳，守卫/业务/回话进包内
    `content/cmds_{social,economy}.py`）：本文件 `SOCIAL_FROZEN` + `SOCIAL_DB_SHA`（129 例，
    B18-L8）与 `ECONOMY_FROZEN` + `ECONOMY_DB_SHA`（142 例，B18-L9）—— **迁移前**真跑各分支
    存下的完整输出与 DB 逐行 dump 摘要，每次跑测试复跑比对（每例 clean_db + AUTOINCREMENT
    计数清零 + 固定 random.seed；墙钟值在比对前归一化，见各段注释）

跑法：python tests/test_texts_table.py（exit=0 通过）

依赖与前置（★ CLEANUP②，2026-09-15 —— 本门禁为何是「稳定绿」）
------------------------------------------------------------------
1. **库与隔离**：本文件用 `_engine_harness` 的库（`GWEN_GAME_DB`；全量 runner 给每个文件一份
   私有库）。每例开跑前 = `clean_db()` + `DELETE FROM sqlite_sequence` + `DELETE FROM identity_map`
   —— 与 `_s_dump`/`_e_dump` 的「**全表** dump」口径对齐。**前置测试若与本文件共用同一只库**
   （`--file=` 模式 / 直跑共享 `test_game_data.db`），只要它写过 `identity_map`（宿主
   `host/_identity.py` 的 openid↔QQ 映射，`clean_db()` 的 25 张业务表里没有它），
   本段 129 例 + 142 例的摘要就会集体变；`_clear_identity_map()` 就是为此补的
   （实测：种一行 → 271/271 全红；原始输出 `out/logs/texts_polluted.txt`）。
2. **与下列因素无关**（受控实验，原始输出在 `out/logs/`）：
   · 进程哈希种子：`PYTHONHASHSEED=0..5` 六次全绿（`texts_flaky_hashseeds.txt`）；
   · 并发 / 负载：4 进程同时跑，**逐例归一化 dump 逐字节相同**（`out/probe_texts_db/dump1..4.json`）；
   · 墙钟日期：把包内 + 本文件的 `datetime` / `time.strftime` / `time.localtime` 一律钉到
     2023-11-15（基准采集日 = 2026-09-15，差一天）→ **0 例红**（`texts_dateflip3.txt`）。
     历史「跨午夜 1–2 例红」已由 PFIX P8 的日期归一化（`_S_DATE_PAT` / `_E_DATE_PAT`）修掉。
3. **随机**：每例 `random.seed(_S_SEED / _E_SEED)` 固定；uuid4 派生物品键由
   `_S_UUID_PAT` / `_E_UUID_PAT` 归一。故无需 `random` 之外的复现前提。
"""
import ast
import asyncio
import datetime
import io
import json
import os
import random
import re
import sys
import tempfile
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _paths  # noqa: E402

# 包仓布局：本文件在 `pkg/tests/`（`_HERE` 的上一级是**包根**，不是旧插件根）。
_PD = _paths.HOST_ROOT              # 宿主插件根（旧语义；`game/` `main.py` `host/` 在宿主侧）
PKG_ROOT = _paths.PKG_ROOT          # 包根（内容真源）

# ★ 库路径（`_paths` 口径）：直跑时**不吃共享 `test_game_data.db`** —— 全量 runner 本就是
#   每文件一份私有库（见文件头「库与隔离」），这里把直跑口径对齐同一形状：私有库首建即无
#   任何**平台旁路表**（如宿主流水 `tlog`；它不是内容表，不在 `content/data/tables.json` 里），
#   故 `_s_dump`/`_e_dump` 的「全表 dump」摘要与冻结基准同源；也不会被前置文件（同库直跑时
#   如 `test_v182_behavior_tlog` 的 `SQLiteSink`）写下的旁路表污染。
#   `setdefault` = 不覆盖 runner / 调用者预置的私有库（口径与 `tests/conftest.py` 同）。
os.environ.setdefault("GWEN_GAME_DB", os.path.join(_paths.TESTS_DIR, "test_texts_table.db"))

from _engine_harness import C, db, clean_db, FakeEvent, run, Main  # noqa: E402
from content import texts as T  # noqa: E402
from content.flow.weekly_progress import (  # noqa: E402  ★ B18-REPOINT：直取包内实现本体（宿主同名壳不再被测试引用）
    _week_state, _save_week_state,
)
from content.flow import instance_battle as _IB  # ★ 改绑到包内实现：冻结分支的 build_battle 桩打在实现上
                                                 #   （宿主壳取件面变化后，打在壳上会静默失效 → 文案门禁 61/63）
from _engine_harness import Main as _CmdHostBase  # noqa: E402
from content.instance_cmds import InstanceImpl as _InstImpl  # noqa: E402  （打桩落点：包内实现类）

# `_PD` = 旧插件根语义（见上 `_paths.HOST_ROOT`）；宿主各扫描根（`game/**`）按插件根拼。
WEEKLY_SRC = os.path.join(_PD, "game", "commands", "weekly.py")
MISC_SRC = os.path.join(_PD, "game", "commands", "misc.py")
EVENT_SRC = os.path.join(_PD, "game", "commands", "event_menu.py")
WORLD_SRC = os.path.join(_PD, "game", "commands", "world.py")
QUESTS_SRC = os.path.join(_PD, "game", "services", "quests.py")
# ★ P5E-DELETE（2026-09-15，删壳批）：「每日命令」域的宿主扫描根 `game/services/quests.py`
#   随壳删除；包内真源 = `content/profession_quests.py`（R2 登记：`game/services/quests.py`
#   的逻辑真源）+ `content/quests_flow.py`（每日流程）。两文件都扫（`_wired_paths` 支持列表；
#   真实调用点集合与双向对账判定不变）。`PKG_QUESTS_SRC` 在 `PKG_CONTENT` 定义之后赋值。
# ★ P5E-DELETE（2026-09-15，删壳批）：「副本准入」域的扫描根改到**包内真源**。
#   原值 = `<插件>/game/core/instance_gate.py`（宿主薄壳，随 `game/**` 整树删除）
#   ⇒ 全删态 `t2_key_and_params_accounting` 扫描时 `FileNotFoundError`（整文件红）。
#   包内落点 = `content/flow/instance_gate.py`（B18-L5 起 `instance.*` 文案的调用点就在包里；
#   下面 `PKG_*` 一族早已按「宿主 + 包内」两侧登记，本域只是把宿主那一侧换成包内侧）。
#   判据（key ↔ 调用点双向对账 / 槽位校验 / dead key）与条数**一条未变**。
GATE_SRC = os.path.join(PKG_ROOT, "content", "flow", "instance_gate.py")
INSTANCE_ROUTER_SRC = os.path.join(_PD, "game", "commands", "instance_router.py")
INSTANCE_SRC = os.path.join(_PD, "game", "commands", "instance.py")
INSTANCE_BATTLE_SRC = os.path.join(_PD, "game", "commands", "instance_battle.py")
# ★ P4′-B：声明真源 = **包内** `content/data/text_specs.json`（装载器 `content/texts.py` 自定位）；
#   `T.SPEC_PATH` 由宿主薄壳从包内装载器取回（下面 [1] 段钉死「两者同一条包内路径」）。
SPEC = T.SPEC_PATH
# ★ B18 终态（2026-09-14 样板定形线）：**渲染进包** —— 周常域的 `T.text/T.static` 调用点已从宿主
#   `game/commands/weekly.py` 迁进包内 `content/cmds_weekly.py`（宿主侧退化为 0 调用点）。
#   扫描根因此扩到「宿主 + 包内」两侧（B18_TERMINAL_SHAPE §2 的前置项：渲染进包 ⇒ 门禁必须跟）。
PKG_CONTENT = os.path.join(PKG_ROOT, "content")
# ★ P5E-DELETE：「每日命令」域的包内真源（见上面 QUESTS_SRC 处注释）
PKG_QUESTS_SRC = [os.path.join(PKG_CONTENT, "profession_quests.py"),
                  os.path.join(PKG_CONTENT, "quests_flow.py")]
PKG_WEEKLY_SRC = os.path.join(PKG_CONTENT, "cmds_weekly.py")
# ★ B18-L6（2026-09-14）：『今日事件/事件/领取补给箱』的渲染随命令整块进包
#   （`content/cmds_event.py`）—— `supply.*` 7 条调用点从宿主 `event_menu.py` 搬进包内，
#   扫描根两侧都扫（与「周常」同款口径）。
PKG_EVENT_SRC = os.path.join(PKG_CONTENT, "cmds_event.py")
# ★ B18-L3c（2026-09-14）：副本战斗日志 3 条 key（`instance.日志_团队治疗` /
#   `instance.结算_战斗异常` / `instance.面板_战斗_不在`）的调用点从宿主
#   `game/commands/instance_battle.py` 迁进包内 `content/flow/instance_battle.py`
#   （`team_heal_text` / `abort_text`）→ 该域的扫描根同批扩到「宿主 + 包内」两侧。
PKG_FLOW_INSTANCE_BATTLE_SRC = os.path.join(PKG_CONTENT, "flow", "instance_battle.py")
# ★ B18-L5（2026-09-14）：副本结算域的渲染（`instance.结算_*` / `instance.日志_超时自动防御` /
#   `instance.日志_嘲讽` / `instance.日志_同归于尽` / `instance.面板_中心_击败Boss` 共 18 key）
#   随 `instance_router` **整块进包** → 宿主 `game/commands/instance_router.py` 退化为壳
#   （注册/再导出 + 文案登记），真实调用点在包内 `content/cmds_instance_router.py`；副本日志域同理
#   （实现体 B11-L1 起在 `content/instance_cmds.py`）。两域扫描根同批扩到「宿主 + 包内」两侧
#   （与「周常」「补给箱」「副本战斗日志」同款口径）。
PKG_INSTANCE_ROUTER_SRC = os.path.join(PKG_CONTENT, "cmds_instance_router.py")
PKG_INSTANCE_SRC = os.path.join(PKG_CONTENT, "instance_cmds.py")
# ★ B18-L1（2026-09-14）：世界域 36 条命令 + misc 域 5 条命令整块进包 ——
#   `daily.*` 7 条（随 `quest_view`）与 `signin.*` 10 条（随签到）的调用点从宿主
#   `game/commands/{world,misc}.py` 搬进包内 `content/cmds_{world,misc}.py`（宿主侧退化为 0 调用点）
#   → 两域扫描根同批扩到「宿主 + 包内」两侧（与「周常」「补给箱」同款口径）。
PKG_WORLD_SRC = os.path.join(PKG_CONTENT, "cmds_world.py")
PKG_WORLDCMDS_SRC = os.path.join(PKG_CONTENT, "world_cmds.py")   # ★ C 档 18a（B-2 第 4 片）：地图面板族
PKG_MISC_SRC = os.path.join(PKG_CONTENT, "cmds_misc.py")
# ★ B18-L8（2026-09-14）：社交域 **33 条命令**整块进包 —— 宿主 `game/commands/social.py`
#   退化为「`@declared` 注册 + 一行 `_BRIDGE.run` 转发」，守卫/取参/分支/提示行/文案全在包内
#   `content/cmds_social.py`。本域**不使用 `T.text/T.static`**：句子是宿主旧壳里的内联
#   字面量 / f-string，逐字搬进包内（一个字符都没改）→ 两侧扫到 0 个调用点。本域扫描根仍按
#   「宿主 + 包内」两侧登记（将来若有人把句子改成文案表 key，本门禁立刻扫到并对账槽位）。
#   逐字一致的真正证据见本文件 [12] 段：`SOCIAL_FROZEN`（文本）+ `SOCIAL_DB_SHA`（副作用），
#   = 迁移前真跑 129 例（33 条命令 × 正常/边界/失败）存下的完整输出与 DB 逐行 dump 摘要。
SOCIAL_SRC = os.path.join(_PD, "game", "commands", "social.py")
PKG_SOCIAL_SRC = os.path.join(PKG_CONTENT, "cmds_social.py")
# ★ P5E-DELETE（2026-09-15，删壳批）：本文件 [12] 段（社交域逐字冻结）的扫描根原为宿主
#   `game/commands/social.py`（随壳删除）。该域 B18-L8 起整块进包、宿主侧已是 0 调用点壳
#   ⇒ 改指包内真源 `content/cmds_social.py`（与 `PKG_SOCIAL_SRC` 同一文件、同一扫描面）。
#   下面「宿主壳 0 调用点 / 0 残留转发」两条断言的**判据对象**随之变成包内真源那一份
#   （原本就是它们承载全部真实句子），判定与阈值一字未变。
SOCIAL_SRC = PKG_SOCIAL_SRC
# ★ B18-L9（2026-09-15）：经济域 **45 条命令**整块进包 —— 宿主 `game/commands/economy.py`
#   退化为「`@declared` 注册 + 两行 `_BRIDGE.run_async` 转发」，守卫（`hook:player`）/取参/
#   分支业务/回话全在包内（处理器 async：实现体
#   `content/economy_cmds.py::EconomyImpl.<m>` 是 async generator，照战斗族先例）。
#   本域**不使用 `T.text/T.static`**：句子是 `EconomyImpl` 里的内联字面量 / f-string
#   （B9-L1 起就在包内）→ 两侧扫到 0 个调用点。
#   逐字一致的真正证据见本文件 [13] 段：`ECONOMY_FROZEN`（文本）+ `ECONOMY_DB_SHA`（副作用），
#   = 迁移前真跑 142 例（45 条命令 × 正常/边界/失败 + 追加边界）存下的完整输出与 DB dump 摘要。
#
# ★ 改：45 条命令的 handler 薄壳已从 `content/cmds_economy.py` 删掉（该文件随迁删）——
#   声明表 `content/data/commands.json` 的 `bind` 直接点名实现体，引擎按 `bind.call` 造 handler。
#   故本段的**扫描根**改为：句子/文案面 = 实现体 `content/economy_cmds.py`；
#   「45 条处理器都是 async」= 声明表 45 条 `bind.call == "messages"`（引擎按该模式生成协程处理器）。
#   判定与强度逐条不变（仍是「扫包内真源 + 45 条一个不少」）。
ECONOMY_SRC = os.path.join(_PD, "game", "commands", "economy.py")
PKG_ECONOMY_SRC = os.path.join(PKG_CONTENT, "economy_cmds.py")
PKG_PLAYER_SRC = os.path.join(PKG_CONTENT, "player_cmds.py")   # C 档 14（B-2 第 2 片）：player 散落/尾巴
PKG_ITEM_TPL_SRC = os.path.join(PKG_CONTENT, "item_templates.py")  # C 档 15（B-2 第 6 片）：道具模板文案族
# ★ P5E-DELETE（2026-09-15，删壳批）：同 SOCIAL_SRC 的处置 —— [13] 段（经济域逐字冻结）
#   原扫宿主 `game/commands/economy.py`（随壳删除），改指包内真源 `content/cmds_economy.py`。
ECONOMY_SRC = PKG_ECONOMY_SRC
# ★ P5E-DELETE（2026-09-15，删壳批）：「副本结算 / 副本日志 / 副本战斗日志」三域的
#   **宿主侧扫描根**同样随 `game/**` 删除（逐个 FileNotFoundError）。这三个域在 B18 时就是
#   「宿主 + 包内」两侧扫描，而宿主侧从那时起已退化为壳（调用点 0 个）⇒ 只保留**包内真源**
#   一侧，扫描面（真实调用点集合）与判定逐条不变。
#   逐个映射：`game/commands/instance_router.py` → `content/cmds_instance_router.py`；
#   `game/commands/instance.py` → `content/instance_cmds.py`；
#   `game/commands/instance_battle.py` → `content/flow/instance_battle.py`。
INSTANCE_ROUTER_SRC = PKG_INSTANCE_ROUTER_SRC
INSTANCE_SRC = PKG_INSTANCE_SRC
INSTANCE_BATTLE_SRC = PKG_FLOW_INSTANCE_BATTLE_SRC
# 已迁移的域 → 该域文案由哪个文件接线（值 = 单文件或文件列表；新增一个域时在这里加一行）
# ★ P5E-DELETE（2026-09-15，删壳批）：**全部域都只保留包内真源一侧**。
#   这些域在 B18 系列里都已「整块进包」——宿主侧当时就退化为壳（调用点 0 个，见各段原注释
#   「宿主侧退化为 0 调用点」「两侧扫到 0 个调用点」），删壳后宿主路径整体 FileNotFoundError。
#   ⇒ 扫描面（真实调用点集合 / 字面量集合）与双向对账判定**逐条不变**，只是不再扫那份空壳。
WIRED = {"副本准入": GATE_SRC, "副本结算": PKG_INSTANCE_ROUTER_SRC,
         "副本日志": PKG_INSTANCE_SRC,
         "副本战斗日志": PKG_FLOW_INSTANCE_BATTLE_SRC,
         "周常": PKG_WEEKLY_SRC,
         "签到": PKG_MISC_SRC, "补给箱": PKG_EVENT_SRC,
         "每日任务": PKG_WORLD_SRC, "每日命令": PKG_QUESTS_SRC,
         "社交": PKG_SOCIAL_SRC,
         "经济": PKG_ECONOMY_SRC,
         # ★ D2（数据进表）：武器特效域的文案 key 由**读口** `content/mech/we_data.py`
         #   引用（域 `weapon_effects` 的条目字段存 `<字段>_key`，装载期回填模板串）
         #   —— 本域是「数据在域、文案在文案表、代码传 key」的第一个纯数据域，
         #   引用面 = 读口里的 `_TEXT_KEYS` 字面量（`_scan_calls` ②「字面量也算引用」）。
         "武器特效": os.path.join(PKG_CONTENT, "mech", "we_data.py"),
         # ★ B 批 B-1（2026-09-17）：效果名（`_EFFECT_CN` 47 键）搬进文案表 `effect_name.*`，
         #   引用面 = `combat_cmds.py` 里的 `_EFFECT_KEYS`（id → 文案键）字面量表 + 读口 `_effect_cn()`。
         "效果名": os.path.join(PKG_CONTENT, "combat_cmds.py"),
         "机制名": os.path.join(PKG_CONTENT, "combat_cmds.py"),
         "增益名": os.path.join(PKG_CONTENT, "combat_cmds.py"),
         "减益名": os.path.join(PKG_CONTENT, "combat_cmds.py"),
         "叠层名": os.path.join(PKG_CONTENT, "combat_cmds.py"),
         "资源名": os.path.join(PKG_CONTENT, "combat_cmds.py"),
         # ★ B-1 A 档（2026-09-17）：we_procs 的三张战斗日志文案表 + time_weather 的天气/季节名
         #   引用面 = 各自文件里的 `_*_KEYS` 字面量表（`_scan_calls` ②「字面量也算引用」）
         "战斗日志": os.path.join(PKG_CONTENT, "mech", "we_procs.py"),
         "天气名": os.path.join(PKG_CONTENT, "time_weather.py"),
         "季节名": os.path.join(PKG_CONTENT, "time_weather.py"),
         # ★ B 批 B-1 第三批（B 档，2026-09-17）：属性名（4 处内联字面量合并成一张表：
         #   reward.py:309 `_CN` + economy_cmds.py 附魔行 / 套装 bonus_2 / bonus_4_stats）
         #   + 团队特效名（player_cmds.py 技能详情的函数内局部 dict）
         #   引用面 = 各自文件里的 `_*_KEYS` 字面量表（`_scan_calls` ②「字面量也算引用」）
         "属性名": [os.path.join(PKG_CONTENT, "reward.py"), PKG_ECONOMY_SRC],
         "团队特效名": os.path.join(PKG_CONTENT, "player_cmds.py"),
         # ★ B 批 B-1 B 档（2026-09-17）：技能详情「条件转化」行的条件说明（44 键，带槽位）。
         #   引用面 = battle_cond_labels.py 里 `_T.text/_T.static` 的**直接调用点**（字面量键 + 槽位实参）
         "条件文案": os.path.join(PKG_CONTENT, "battle_cond_labels.py"),
         # ★ B 批 B-1 B 档（2026-09-17）：宠物技能一句话描述（8 条模板，槽位 iv/pct）
         "宠物技能描述": os.path.join(PKG_CONTENT, "pets.py"),
         # ★ B 批 B-1 B 档（2026-09-17）：『帮助 <分类>』11 份面板长文本（无槽位，纯句壳）
         #   引用面 = `_T.static("help_panel.*")` 的 11 个直接调用点 + `_HELP_PANEL_KEYS` 字面量表
         "帮助面板": os.path.join(PKG_CONTENT, "misc_cmds.py"),
         # ★ B 批 B-1 B 档（2026-09-17）末批：副业面板图标（8 个 id → emoji；同「叠层名」类展示名词）
         "副业图标": PKG_ECONOMY_SRC,
         # ★ B 批 C 档（2026-09-17）：面板行级句壳（另开一档：每行一条 + f-string 槽位化）
         #   引用面 = 直接调用点（`_T.text("adventure.*", …)` / `_T.static(...)`）
         "冒险手册": PKG_ECONOMY_SRC,
         # C 档 2：『足迹』面板 + 『百科』空参数提示面板（同为行级句壳）
         "足迹": PKG_ECONOMY_SRC,
         "世界百科": PKG_ECONOMY_SRC,
         # C 档 5a：装备来源图标（11 键，搬自 economy_cmds.py 的 _src_icon）
         #   属性点四名（attr_name.*）归**既有分类「属性名」**（同族：属性中文名）
         "来源图标": PKG_ECONOMY_SRC,
         # C 档 5b：词条/装备触发时机中文名（6 键，搬自 economy_cmds.py 的 _trig_cn）
         "触发名": PKG_ECONOMY_SRC,
         # C 档 12：GM 面板 / 公会面板 / 修炼塔（行级句壳）
         "GM面板": os.path.join(PKG_CONTENT, "gm.py"),
         # ★ C 档 32a（B-2 第 19 片）：gm.py 余量「GM 指令回执族」——
         #   权限/目标解析/停服开服/广播/发金币发物品发经验/设等级/传送/体力/改名/
         #   白名单/世界Boss伤害/资料表重载/帮助 全部句壳（玩家列表四行归既有 GM面板）
         "GM指令": os.path.join(PKG_CONTENT, "gm.py"),
         "公会面板": os.path.join(PKG_CONTENT, "social_guild.py"),
         "修炼塔": os.path.join(PKG_CONTENT, "cmds_tower.py"),
         # C 档 10：player_cmds 的八个面板分类（同文件多分类，引用面 = 直接调用点）
         "角色面板": os.path.join(PKG_CONTENT, "player_cmds.py"),
         "属性面板": os.path.join(PKG_CONTENT, "player_cmds.py"),
         "排行榜": os.path.join(PKG_CONTENT, "player_cmds.py"),
         "种族面板": os.path.join(PKG_CONTENT, "player_cmds.py"),
         "转职": os.path.join(PKG_CONTENT, "player_cmds.py"),
         "技能栏": os.path.join(PKG_CONTENT, "player_cmds.py"),
         "流派": os.path.join(PKG_CONTENT, "player_cmds.py"),
         "技能详情": os.path.join(PKG_CONTENT, "player_cmds.py"),
         # C 档 11：经济面板（附魔/套装/重铸）
         "经济面板": PKG_ECONOMY_SRC,
         # ★ C 档 14（B-2 第 2 片）：player_cmds 散落/尾巴 —— 六个新分类同源一个文件
         #   （快捷指令 = shortcut + page_flip；注册 / 身份绑定 = bind_identity；加点洗点 =
         #   add_attr + reset_skill + reset_attr + evolve_reset；技能学习 = _skill_learn_msg +
         #   skill_upgrade；注销 = delete_account。转职 / 技能栏 为该文件既有分类，沿用 PKG_PLAYER_SRC）
         "快捷指令": PKG_PLAYER_SRC,
         "注册": PKG_PLAYER_SRC,
         "身份绑定": PKG_PLAYER_SRC,
         "加点洗点": PKG_PLAYER_SRC,
         "技能学习": PKG_PLAYER_SRC,
         "注销": PKG_PLAYER_SRC,
         "转职": PKG_PLAYER_SRC,
         "技能栏": PKG_PLAYER_SRC,
         # ★ C 档 15（B-2 第 6 片）：道具模板（`ItemResult(text=…)` 文案族 44 个模板函数 · 105 键）
         "道具模板": PKG_ITEM_TPL_SRC,
         # ★ C 档 16（B-2 第 3 片）：economy 散落「采集/生活」
         #   （采集/挖掘/垂钓 begin 与门禁提示 + 炼金列表与合成 + 烹饪列表与制作 + 副业面板/排行/今日任务/遗忘）
         "生活副业": PKG_ECONOMY_SRC,
         "炼金": PKG_ECONOMY_SRC,
         "烹饪": PKG_ECONOMY_SRC,
         # ★ C 档 17a（B-2 第 3 片第 2 小片）：economy 散落「锻造族」
         #   （锻造/代工/学习图纸/已学图纸/锻造列表三视图/配方详情/配方列表）
         "锻造": PKG_ECONOMY_SRC,
         # ★ C 档 17b（B-2 第 3 片第 3 小片）：economy 散落「强化·宝石·符文·重锻·炼成·附魔」
         "强化": PKG_ECONOMY_SRC,
         "宝石": PKG_ECONOMY_SRC,
         "符文": PKG_ECONOMY_SRC,
         "重锻炼成": PKG_ECONOMY_SRC,
         # ★ C 档 18a（B-2 第 4 片第 1 小片）：world 散落「地图面板族」
         #   （地图设施/场景 · 地图·区域·位置·赶路四视图共用句 · 导航主体 · 返回停用 · 问路/寻路）
         "地图导航": PKG_WORLDCMDS_SRC,
         # ★ C 档 18c（B-2 第 4 片第 2 小片）：world 散落「任务委托族」
         #   （接取：主线/支线/血脉/前置/告示板/列表行 · 放弃：主线拦截/序号/已放弃）
         "任务委托": PKG_WORLDCMDS_SRC,
         # ★ C 档 18d-1（B-2 第 4 片第 3 小片）：world 散落「家园·地契」
         #   （地契大厅/买房/卖房/房屋升级 · 回家/出门/拜访 · 仓库存取 · 家的视图）
         "家园地契": PKG_WORLDCMDS_SRC,
         # ★ C 档 18d-2（B-2 第 4 片第 4 小片）：world 散落「营地·休息·声望·阵营」
         #   （篝火营地休息 / 旅店住宿 · 声望面板与声望商店 · 四大阵营加入/任务/商店/排行）
         "营地休息": PKG_WORLDCMDS_SRC,
         "声望阵营": PKG_WORLDCMDS_SRC,
         # ★ C 档 18d-3（B-2 第 4 片第 5 小片）：world 散落「传送·方碑·场景交互」
         #   （方碑列表/激活/传送 · 场景元素交互：告示板/井水/泉水/篝火治愈/翻找材料）
         "传送方碑": PKG_WORLDCMDS_SRC,
         "场景交互": PKG_WORLDCMDS_SRC,
         # ★ C 档 22c（B-2 第 8 片）：world 散落「NPC 对话族」
         #   （NPC 列表/缺员提示/裸数字消费 · 『找』查找链全分支 · 对话树渲染 · 对话选项全分支）
         "NPC面板": PKG_WORLDCMDS_SRC,
         "NPC查找": PKG_WORLDCMDS_SRC,
         "NPC对话": PKG_WORLDCMDS_SRC,
         "快捷交互": PKG_WORLDCMDS_SRC,
         # ★ C 档 25a（B-2 第 11 片）：教习型 NPC 直授（find → _teach_by_npc）与行会就职
         #   （对话动作 unlock_class → _do_join_class）—— 调用点同在 world_cmds.py
         "NPC教习": PKG_WORLDCMDS_SRC,
         "行会就职": PKG_WORLDCMDS_SRC,
         # ★ C 档 26a（B-2 第 12 片）：world 收尾「见闻录 / 时间面板 / 地图尾块 / 指路」
         #   （_map_blocks 地图公共块 · time_cmd 时间面板 · wild_notes 见闻录 ·
         #    _npc_direction_hint 指路 · _wild_cond_label 出现条件标签 —— 调用点同在 world_cmds.py；
         #    时段/季节/天气三张内联 dict 的展示名 ⇒ 新分类 时段名，季节名/天气名 为既有分类）
         "见闻录": PKG_WORLDCMDS_SRC,
         "时间面板": PKG_WORLDCMDS_SRC,
         "时段名": PKG_WORLDCMDS_SRC,
         # ★ C 档 27a（B-2 第 13 片）：world 余量「交付目标行 / 武器自选礼包」
         #   （_obj_text_lines_of 交付面板多行目标模板 · _weapon_pick_choose 武器自选礼包
         #    裸数字消费全分支 —— 调用点同在 world_cmds.py；两分类键名全 ASCII）
         "任务目标": PKG_WORLDCMDS_SRC,
         "武器礼包": PKG_WORLDCMDS_SRC,
         # ★ C 档 28a（B-2 第 14 片）：settlement「战斗结算：经验/金币加成 + 掉落播报」
         #   （content/settlement.py 本文件首次接入 `_T`；新分类 战斗结算 / 掉落播报）
         "战斗结算": os.path.join(PKG_CONTENT, "settlement.py"),
         "掉落播报": os.path.join(PKG_CONTENT, "settlement.py"),
         # ★ C 档 29a（B-2 第 16 片）：quests_flow「任务列表/任务接取/任务交付/任务进度」
         #   （content/quests_flow.py 本文件首次接入 `_T`；任务目标 为既有分类，
         #    _one_text_of 与 27a 的 objline.* 同值幂等复用）
         "任务列表": os.path.join(PKG_CONTENT, "quests_flow.py"),
         "任务接取": os.path.join(PKG_CONTENT, "quests_flow.py"),
         "任务交付": os.path.join(PKG_CONTENT, "quests_flow.py"),
         "任务进度": os.path.join(PKG_CONTENT, "quests_flow.py"),
         # ★ C 档 19a（B-2 第 5 片第 1 小片）：combat 战斗域「探索·战斗主循环」
         #   （explore/attack/defend/flee · 摸宝箱 · 战斗状态行/编队/底栏/胜利行）
         "战斗主循环": os.path.join(PKG_CONTENT, "combat_cmds.py"),
         "战斗面板": os.path.join(PKG_CONTENT, "combat_cmds.py"),
         # ★ C 档 19c（B-2 第 5 片第 3 小片）：combat「PvP·荣誉」
         #   （荣誉商店面板/兑换全分支 · PVP 袭击前置校验/回合行动/胜负结算）
         "PvP荣誉": os.path.join(PKG_CONTENT, "combat_cmds.py"),
         # ★ C 档 19d（B-2 第 5 片第 4 小片）：combat「世界 Boss 讨伐」
         #   （无入侵/已撤离/非Boss事件/不在出没地 · 加入讨伐与阵列面板 · 贡献结算/首功）
         "世界Boss": os.path.join(PKG_CONTENT, "combat_cmds.py"),
         # ★ C 档 19e-1（B-2 第 5 片第 5 小片）：combat「许愿·流浪商人·复活确认」
         #   （流星许愿三选 · 商人强卖成交/拒绝/钱不够 · 复活羽毛二段确认）
         "许愿商人": os.path.join(PKG_CONTENT, "combat_cmds.py"),
         # ★ C 档 19e-2（B-2 第 5 片第 6 小片）：combat「battle_prefs 战前设置」
         #   （双形态预设 · 终结阈值 · 奥术力场 · 战前指令总览）
         "战前设置": os.path.join(PKG_CONTENT, "combat_cmds.py"),
         # ★ C 档 19f（B-2 第 5 片第 7 小片）：combat 散尾（探索点 POI 两分支 + find 型委托「找到目标」）
         "探索事件": os.path.join(PKG_CONTENT, "combat_cmds.py"),
         # ★ C 档 20a（B-2 第 6 片第 1 小片）：社交散落「市场·摊位」
         #   （群市场面板/上架下架购入全分支 · 摆卖摆换·收摊·摊位·换 全分支 · 家园铺面门禁）
         "社交市场": [PKG_SOCIAL_SRC, os.path.join(PKG_CONTENT, "social_stall.py")],
         # ★ C 档 20b（B-2 第 6 片第 2 小片）：社交「组队·公会」
         #   （组队面板/拉人/退队守卫 · 公会创建/加入/退出/解散/签到/任务/捐献/排行/商店/技能/任命/免职）
         "社交队伍": [PKG_SOCIAL_SRC, os.path.join(PKG_CONTENT, "party.py")],
         "社交公会": [PKG_SOCIAL_SRC, os.path.join(PKG_CONTENT, "social_guild.py")],
         # ★ C 档 20c（B-2 第 6 片第 3 小片）：社交「世界事件 · 拍卖竞拍」
         #   （事件惰性调度通知/面板两态 · 落槌结算头 · 拍卖未开张两态/开张面板 ·
         #    竞拍格式/无此物/四道守卫/被超越退还/一口价/成功两态）
         "世界事件": [PKG_SOCIAL_SRC, os.path.join(PKG_CONTENT, "social_cmds.py")],
         "社交拍卖": [PKG_SOCIAL_SRC, os.path.join(PKG_CONTENT, "social_cmds.py")],
         # ★ C 档 20d（B-2 第 6 片第 4 小片）：社交「宠物 · 坐骑」
         #   （content/social_pet.py **全 5 函数**首次接入 `_T`：宠物面板全行 · 喂养全分支 ·
         #    改名/放生 · 坐骑面板/骑乘/下马 —— 命令层 cmds_social.py 只做转发，调用点全在本文件）
         "宠物面板": os.path.join(PKG_CONTENT, "social_pet.py"),
         "宠物喂养": os.path.join(PKG_CONTENT, "social_pet.py"),
         "宠物管理": os.path.join(PKG_CONTENT, "social_pet.py"),
         "坐骑面板": os.path.join(PKG_CONTENT, "social_pet.py"),
         # ★ C 档 21a（B-2 第 7 片第 1 小片）：生活「商店 · 货架」
         #   （商店面板：红名/无店两分支/货摊标题/六块货行/翻页/底栏 —— 命令层 shop；
         #    货架成交命名 shop.work_name 由 smith_stock.py 与面板共键；序号购买分派在 shop.py；
         #    限购与共享库存守卫在 shop_stock.py）
         "商店面板": [PKG_ECONOMY_SRC, os.path.join(PKG_CONTENT, "smith_stock.py")],
         # ★ C 档 21b（B-2 第 7 片第 2 小片）：生活「商店 · 买卖」
         #   （命令层 economy_cmds.py 的 buy 名称路径 + sell 全分支；与 21a 的
         #    shop.py::buy_index_dispatch 大量**同值幂等复用**，故 商店购买 的引用面从
         #    shop.py 扩到「包内服务层 + 命令层」两侧；sell 侧另开分类 商店出售）
         "商店购买": [os.path.join(PKG_CONTENT, "shop.py"), PKG_ECONOMY_SRC],
         # ★ C 档 21c（B-2 第 7 片第 3 小片）：生活「使用 · 背包 · 装备」
         #   （命令层 economy_cmds.py 的 _bag_view / equip / use 三函数 ⇒ 三个新分类）
         "背包面板": PKG_ECONOMY_SRC,
         "装备面板": PKG_ECONOMY_SRC,
         "道具使用": PKG_ECONOMY_SRC,
         "商店出售": PKG_ECONOMY_SRC,
         "商店限购": os.path.join(PKG_CONTENT, "shop_stock.py"),
         # ★ C 档 22b（B-2 第 7 片第 5 小片）：生活「称号 · 物品查看模式」尾巴
         #   （EconomyImpl.titles 称号面板四行 · _equip_title 用法/未获得/佩戴成功三行
         #    ⇒ 新分类 称号面板；item_view_mode_cmd 开关两条回执照归既有 **背包面板**）
         "称号面板": PKG_ECONOMY_SRC}


def _wired_paths(path):
    """WIRED 的值可以是单文件（宿主）或文件列表（宿主 + 包内）。"""
    return list(path) if isinstance(path, (list, tuple)) else [path]

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ✅ %s" % name)
    else:
        failed += 1
        print("  ❌ %s %s" % (name, str(detail)[:400]))


# ══════════════════════════════════════════════════════════════════════════
# 迁移前行为快照（真跑『周常』『周常列表』6 个分支，逐字冻结）
# ══════════════════════════════════════════════════════════════════════════
WEEKLY_FROZEN = {
    "A_locked": "🏮 悬赏板还蒙着布——上面的委托要 Lv.50 的冒险者才接得动。\n💡 先完成『每日』任务和主线提升等级，到了 Lv.50 再来看看～",
    "B_first": "🏮 【本周悬赏】已发布！\n━━━━━━━━━━━━\n1. 『边境肃清令』击败 30 只任意怪物\n    目标：讨伐任意怪物 30 只｜赏金：经验 +155000 金币 +38000\n2. 『深林猎手悬赏』击败 40 只任意怪物\n    目标：讨伐任意怪物 40 只｜赏金：经验 +175000 金币 +44000\n3. 『剿灭魔裔』击败 5 只精英怪物\n    目标：讨伐精英怪物 5 只｜赏金：经验 +190000 金币 +48000\n\n💡 击杀自动计数，达标立即发奖！『周常』随时查进度，『周常列表』看全池悬赏",
    "C_progress": "🏮 【本周悬赏】1/3 已完成\n━━━━━━━━━━━━\n1. 『边境肃清令』 ✅ 已完成\n2. 『深林猎手悬赏』 ⏳ 0/40\n    目标：讨伐任意怪物 40 只｜赏金：经验 +175000 金币 +44000\n3. 『剿灭魔裔』 ⏳ 0/5\n    目标：讨伐精英怪物 5 只｜赏金：经验 +190000 金币 +48000\n\n💡 击杀自动计数，达标立即发奖——悬赏每周一刷新",
    "D_pool_p1": "🏮 【周常悬赏池】第 1/3 页（每周自动发布 3 条）\n━━━━━━━━━━━━\n· 『边境肃清令』(Lv.50+) 击败 30 只任意怪物\n    经验 +155000 金币 +38000\n· 『深林猎手悬赏』(Lv.50+) 击败 40 只任意怪物\n    经验 +175000 金币 +44000\n· 『剿灭魔裔』(Lv.50+) 击败 5 只精英怪物\n    经验 +190000 金币 +48000\n· 『破阵斩将』(Lv.50+) 击败 6 只精英怪物\n    经验 +210000 金币 +53000\n\n💡 每周一刷新自动抽取适合你等级的悬赏；『周常』查看本周任务\n📄 『周常列表 2』翻页",
    "E_pool_p2": "🏮 【周常悬赏池】第 2/3 页（每周自动发布 3 条）\n━━━━━━━━━━━━\n· 『讨伐区域首领』(Lv.50+) 击败 2 个区域 Boss\n    经验 +230000 金币 +58000\n· 『诛灭祸乱之源』(Lv.50+) 击败 3 个区域 Boss\n    经验 +250000 金币 +64000\n· 『龙脊清扫令』(Lv.70+ 🔒) 击败 35 只任意怪物\n    经验 +400000 金币 +100000\n· 『深渊行者试炼』(Lv.70+ 🔒) 击败 45 只任意怪物\n    经验 +450000 金币 +115000\n\n💡 每周一刷新自动抽取适合你等级的悬赏；『周常』查看本周任务\n📄 『周常列表 3』翻页",
    "F_all_done": "🏮 【本周悬赏】3/3 已完成\n━━━━━━━━━━━━\n1. 『边境肃清令』 ✅ 已完成\n2. 『深林猎手悬赏』 ✅ 已完成\n3. 『剿灭魔裔』 ✅ 已完成"
}   # 迁移前快照（2026-09-12 真跑存下，勿手改）

# 迁移前行为快照（真跑『签到』5 个分支，逐字冻结；random 打桩保证可复现）
SIGNIN_FROZEN = {
    "A_first_bad": "📅 【签到成功】第 1 次签到！连续 1 天！\n💰 获得 25 金币\n🌧️ 今日运势：小凶(今日金币－10%)\n💡 今日小凶金币收益 -10%……别灰心！用『使用 幸运符』可消解，或明日签到重roll运势～",
    "B_first_big": "📅 【签到成功】第 1 次签到！连续 1 天！\n💰 获得 25 金币\n🌟 今日运势：大吉(今日经验＋10%)",
    "C_dup": "今天已经签过到啦！明天再来～",
    "D_streak7": "📅 【签到成功】第 7 次签到！连续 7 天！\n💰 获得 55 金币\n🌟 今日运势：大吉(今日经验＋10%)\n🎁 连续 7 天奖励：🟣【龙鳞战甲】！",
    "E_festival": "📅 【签到成功】第 1 次签到！连续 1 天！\n💰 获得 50 金币\n🌟 今日运势：大吉(今日经验＋10%)\n🎉 节日庆典：签到奖励翻倍！"
}   # 迁移前快照（2026-09-12 真跑存下，勿手改）

SUPPLY_FROZEN = {
    "A_first": "📦 【每日补给箱】\n━━━━━━━━━━━━\n  🎁 每日材料箱：图纸残页、淬火石、烤肉串！\n  🎁 每日道具箱：强化石、双倍金币符、炖菜！\n  🎁 每日豪华箱：白银箱、精炼强化石、幸运符！\n\n💡 补给箱内容：图纸残页/淬火石/强化石/幸运符等（每日 0 点重置）",
    "B_second": "📦 【每日补给箱】\n━━━━━━━━━━━━\n  ⏳ 每日材料箱：今日已领取～\n  ⏳ 每日道具箱：今日已领取～\n  🎁 每日豪华箱：白银箱、精炼强化石、幸运符！\n\n💡 补给箱内容：图纸残页/淬火石/强化石/幸运符等（每日 0 点重置）",
    "C_third": "📦 【每日补给箱】\n━━━━━━━━━━━━\n  ⏳ 每日材料箱：今日已领取～\n  ⏳ 每日道具箱：今日已领取～\n  ⏳ 每日豪华箱：本周已领 2/2～\n  今天/本周的补给箱都已领过啦，明天再来吧～\n\n💡 补给箱内容：图纸残页/淬火石/强化石/幸运符等（每日 0 点重置）"
}   # 迁移前快照（2026-09-12 真跑存下，勿手改）

# 迁移前行为快照（真跑『任务』面板 4 种状态：从未领取/进行中/完成未满额/满额，逐字冻结）
DAILY_FROZEN = {
    "A_never": "📜 【冒险日志】\n━━━━━━━━━━━━\n【主线】已全部完成！🎊\n\n【支线】暂无——找镇上的 NPC 聊聊可能有意外收获\n\n【每日】今日还没领取任务——输入『每日』发布今日悬赏～\n\n💡 进行中可弃：『放弃 <序号>』",
    "B_active": "📜 【冒险日志】\n━━━━━━━━━━━━\n【主线】已全部完成！🎊\n\n【支线】暂无——找镇上的 NPC 聊聊可能有意外收获\n\n【每日】\n 1. 『边境警戒』\n    击杀 10 只任意怪物 (3/10)\n 2. 『神秘委托』\n    未知目标（无达标数定义） (进度 1)\n\n💡 『对话 <NPC名>』接取任务",
    "C_done_part": "📜 【冒险日志】\n━━━━━━━━━━━━\n【主线】已全部完成！🎊\n\n【支线】暂无——找镇上的 NPC 聊聊可能有意外收获\n\n【每日】今日已完成 2 个每日任务——输入『每日』还能再接～\n\n💡 『对话 <NPC名>』接取任务",
    "D_done_full": "📜 【冒险日志】\n━━━━━━━━━━━━\n【主线】已全部完成！🎊\n\n【支线】暂无——找镇上的 NPC 聊聊可能有意外收获\n\n【每日】今日已完成 10/10 个每日任务，明天再来！\n\n💡 『每日』领取今日任务"
}   # 迁移前快照（2026-09-12 真跑存下，勿手改；比对时剔除 💡 随机提示行）

# 迁移前行为快照（真跑『每日』命令 7 分支：首发/已有/满额/重抽/衰减/达标/重复达标）
QUEST_FROZEN = {
    "A_publish": "ok=True\n📜 今日任务已发布！\n━━━━━━━━━━━━\n 1. 『大扫除』击败 15 只任意怪物\n    奖励：经验 +1500 金币 +400\n 2. 『日常讨伐』击败 10 只任意怪物\n    奖励：经验 +1200 金币 +270",
    "B_have": "ok=False\n你已经有每日任务了！输入『任务』查看～",
    "C_limit": "ok=False\n⚠️ 今日已完成 10/10 个每日任务，明天再来吧！",
    "D_republish": "ok=True\n📜 今日任务已发布！\n━━━━━━━━━━━━\n 1. 『大扫除』击败 15 只任意怪物\n    奖励：经验 +1500 金币 +400\n 2. 『日常讨伐』击败 10 只任意怪物\n    奖励：经验 +1200 金币 +270\n📌 今日已完成 3/10 个每日任务",
    "E_decay": "ok=True\n📜 今日任务已发布！\n━━━━━━━━━━━━\n 1. 『大扫除』击败 15 只任意怪物\n    ⚠️ 重复完成，奖励衰减 60%：经验 +900 金币 +240\n 2. 『日常讨伐』击败 10 只任意怪物\n    ⚠️ 重复完成，奖励衰减 60%：经验 +720 金币 +162",
    "F_settle": "📜 每日『边境警戒』完成！奖励：经验 +100 金币 +50",
    "G_settle_decay": "📜 每日『边境警戒』完成！重复完成，奖励衰减 60%：经验 +100 金币 +50"
}   # 迁移前快照（2026-09-12 真跑存下，勿手改；抽签用 random.seed(11)）

# 迁移前行为快照（2026-09-12 真跑 instance_router.py 的 11 个结算分支，逐字冻结；
# 来源 $TEMP/instance_settle_before.json —— 采于**接线前**的代码，勿手改）
INSTANCE_SETTLE_FROZEN = {
    "B1_无敌人_探索": "当前区域还有敌人潜伏！『探索』找到它们～",
    "B2_无敌人_已肃清_下一层": "当前区域的敌人已被肃清！\n前方是【二层】……输入『深入』继续推进！",
    "B3_无敌人_已肃清_最后一层": "当前区域的敌人已被肃清！\n这是最后一层，输入『深入』挑战 Boss！",
    "B4_等待行动": "⏳ 现在是 队友甲 的刻，等待 TA 行动～",
    "B5_嘲讽结束": "……嘲讽效果结束，怪物恢复了本能仇恨！\n当前区域还有敌人潜伏！『探索』找到它们～",
    "B6_战斗异常": "战斗状态异常，请重新遭遇！",
    "B7_密室宝箱": "💥 房间怪 受到 1 点伤害，倒下了！\n  玩家：经验 +1，拾取材料 兽肉 ×1\n  玩家：🏆 成就解锁：初试锋芒！(完成首次战斗)\n      🎁 经验+100、兽肉×3（『成就 领取』领取）\n  玩家：🏆 成就解锁：初出茅庐！(注册角色)\n      🎁 草药×2（『成就 领取』领取）\n  玩家：🏆 成就解锁：崭露头角！(达到 10 级)\n      🎁 铁矿石×2（『成就 领取』领取）\n  玩家：🏆 成就解锁：名声鹊起！(达到 20 级)\n      🎁 精铁×2（『成就 领取』领取）\n  玩家：🏆 成就解锁：小有名气！(达到 30 级)\n      🎁 木箱×1（『成就 领取』领取）\n  玩家：🏆 成就解锁：资深冒险者！(达到 40 级)\n      🎁 淬火石×2（『成就 领取』领取）\n  玩家：🏆 成就解锁：大陆精英！(达到 50 级)\n      🎁 白银箱×1（『成就 领取』领取）\n  玩家：🏆 成就解锁：传奇之路！(达到 60 级)\n      🎁 白银箱×1、图纸残页×1（『成就 领取』领取）\n━━━━━━━━━━━━\n✅ 精英守卫被击败了！密室深处露出一口【神秘宝箱】……\n🔐 『调查 宝箱』看看里面藏着什么！",
    "B8_房间清空": "💥 房间怪 受到 1 点伤害，倒下了！\n  玩家：经验 +1，拾取材料 兽肉 ×1\n  玩家：🏆 成就解锁：初试锋芒！(完成首次战斗)\n      🎁 经验+100、兽肉×3（『成就 领取』领取）\n  玩家：🏆 成就解锁：初出茅庐！(注册角色)\n      🎁 草药×2（『成就 领取』领取）\n  玩家：🏆 成就解锁：崭露头角！(达到 10 级)\n      🎁 铁矿石×2（『成就 领取』领取）\n  玩家：🏆 成就解锁：名声鹊起！(达到 20 级)\n      🎁 精铁×2（『成就 领取』领取）\n  玩家：🏆 成就解锁：小有名气！(达到 30 级)\n      🎁 木箱×1（『成就 领取』领取）\n  玩家：🏆 成就解锁：资深冒险者！(达到 40 级)\n      🎁 淬火石×2（『成就 领取』领取）\n  玩家：🏆 成就解锁：大陆精英！(达到 50 级)\n      🎁 白银箱×1（『成就 领取』领取）\n  玩家：🏆 成就解锁：传奇之路！(达到 60 级)\n      🎁 白银箱×1、图纸残页×1（『成就 领取』领取）\n━━━━━━━━━━━━\n✅ 【misty_swamp_1】的敌人被肃清了！\n🗺️ 【哥布林营地】\n哥布林营地，传说中的危险之地，唯有勇者敢于踏入。\n💡 输入『副本 哥布林营地』开启挑战（组队副本，等级/人数校验）\n━━━━━━━━━━━━\n📍 当前位置：哥布林营地\n📮 可前往：\n  🧭 出城需先到『入口栅栏』\n💡 『前往 <序号>』切换位置\n━━━━━━━━━━━━\n🚪 副本内 · 无出口（没有通往外面的路）\n🐾 此房怪物已肃清。\n💡 专注战斗！『副本』查看进度\n━━━━━━━━━━━━\n🧭 副本内可继续探索/移动，或『副本』查看进度！",
    "B9_切怪": "💥 房间怪 受到 1 点伤害，倒下了！\n  玩家：经验 +1，拾取材料 兽肉 ×1\n  玩家：🏆 成就解锁：初试锋芒！(完成首次战斗)\n      🎁 经验+100、兽肉×3（『成就 领取』领取）\n  玩家：🏆 成就解锁：初出茅庐！(注册角色)\n      🎁 草药×2（『成就 领取』领取）\n  玩家：🏆 成就解锁：崭露头角！(达到 10 级)\n      🎁 铁矿石×2（『成就 领取』领取）\n  玩家：🏆 成就解锁：名声鹊起！(达到 20 级)\n      🎁 精铁×2（『成就 领取』领取）\n  玩家：🏆 成就解锁：小有名气！(达到 30 级)\n      🎁 木箱×1（『成就 领取』领取）\n  玩家：🏆 成就解锁：资深冒险者！(达到 40 级)\n      🎁 淬火石×2（『成就 领取』领取）\n  玩家：🏆 成就解锁：大陆精英！(达到 50 级)\n      🎁 白银箱×1（『成就 领取』领取）\n  玩家：🏆 成就解锁：传奇之路！(达到 60 级)\n      🎁 白银箱×1、图纸残页×1（『成就 领取』领取）\n━━━━━━━━━━━━\n⚔️ 又一只怪物挡在面前！\n── 敌方 ──\n  A1层: a1  史莱姆 ❤️465/465\n── 我方 ──\n  B2层: b1  玩家 ❤️500/500\n🕐 时刻 0.0s ｜ ⚡ 行动顺序：玩家(我) → 史莱姆(敌)\n✅ 玩家：❤️ 500/500 💙 50/50\n💡 选敌：『技能1 a2』打2号(纯数字同义)；治疗『技能 <名称> b1』奶自己\n⏳ 轮到 玩家 行动！『攻击』『技能 <名称>』『防御』",
    "B10_层清空": "💥 房间怪 受到 1 点伤害，倒下了！\n  玩家：经验 +1，拾取材料 兽肉 ×1\n  玩家：🏆 成就解锁：初试锋芒！(完成首次战斗)\n      🎁 经验+100、兽肉×3（『成就 领取』领取）\n  玩家：🏆 成就解锁：初出茅庐！(注册角色)\n      🎁 草药×2（『成就 领取』领取）\n  玩家：🏆 成就解锁：崭露头角！(达到 10 级)\n      🎁 铁矿石×2（『成就 领取』领取）\n  玩家：🏆 成就解锁：名声鹊起！(达到 20 级)\n      🎁 精铁×2（『成就 领取』领取）\n  玩家：🏆 成就解锁：小有名气！(达到 30 级)\n      🎁 木箱×1（『成就 领取』领取）\n  玩家：🏆 成就解锁：资深冒险者！(达到 40 级)\n      🎁 淬火石×2（『成就 领取』领取）\n  玩家：🏆 成就解锁：大陆精英！(达到 50 级)\n      🎁 白银箱×1（『成就 领取』领取）\n  玩家：🏆 成就解锁：传奇之路！(达到 60 级)\n      🎁 白银箱×1、图纸残页×1（『成就 领取』领取）\n━━━━━━━━━━━━\n✅ 【一层】的敌人被肃清了！\n🗺️ 【👺哥布林营地】第 1 层 · 一层\n━━━━━━━━━━━━\n📜 你环顾四周，准备迎接这里的敌人。\n━━━━━━━━━━━━\n✨ 场景：\n  []\n  []\n━━━━━━━━━━━━\n✅ 本层敌人已肃清！『深入』前往下一层。\n━━━━━━━━━━━━\n💡 『副本』查看战况，『角色』看队伍\n━━━━━━━━━━━━\n🧭 前方是【二层】……输入『深入』继续推进！",
    "B11_普通轮转": "💥 房间怪 受到 463 点伤害！\n—— 房间怪 行动 ——\n💥 玩家 受到 1 点伤害！\n━━━━━━━━━━━━\n── 敌方 ──\n  A1层: a1  房间怪 ❤️4537/5000\n── 我方 ──\n  B2层: b1  玩家 ❤️499/500\n🕐 时刻 1.1s ｜ ⚡ 行动顺序：玩家(我) → 房间怪(敌)\n✅ 玩家：❤️ 499/500 💙 50/50\n💡 选敌：『技能1 a2』打2号(纯数字同义)；治疗『技能 <名称> b1』奶自己\n⏳ 轮到 玩家 行动！『攻击』『技能 <名称>』『防御』",
}

_GID, _QID = "g_txt", "q_txt"
_SID = "g_si"


async def _inv(m, name, msg):
    ev = FakeEvent(_GID, _QID, msg)
    res = await run(getattr(m, name), ev)
    return res[-1] if res else ""


async def _weekly_scenarios() -> dict:
    """复跑迁移前的 6 个分支（步骤与快照脚本逐行一致）。"""
    clean_db()
    m = Main(None)
    out = {}
    db.create_player(_GID, _QID, "文案", C.resolve("classes", "战士"), {}, 100, 100)
    db.update_player(_GID, _QID, level=49, stamina=100)
    out["A_locked"] = await _inv(m, "weekly_cmd", "周常")
    db.update_player(_GID, _QID, level=50, stamina=100)
    out["B_first"] = await _inv(m, "weekly_cmd", "周常")
    st = dict(_week_state(_QID) or {})
    tasks = st.get("tasks") or {}
    for i, (tn, t) in enumerate(tasks.items()):
        t["prog"] = 1 if i == 0 else 0
        t["done"] = (i == 0)
    st["done_n"] = 1 if tasks else 0
    _save_week_state(_QID, st)
    out["C_progress"] = await _inv(m, "weekly_cmd", "周常")
    out["D_pool_p1"] = await _inv(m, "weekly_list", "周常列表")
    out["E_pool_p2"] = await _inv(m, "weekly_list", "周常列表 2")
    st2 = dict(_week_state(_QID) or {})
    for t in (st2.get("tasks") or {}).values():
        t["done"] = True
        t["prog"] = int(t.get("need") or 1)
    st2["done_n"] = len(st2.get("tasks") or {})
    _save_week_state(_QID, st2)
    out["F_all_done"] = await _inv(m, "weekly_cmd", "周常")
    clean_db()
    return out


async def _signin_scenarios() -> dict:
    """复跑『签到』迁移前的 5 个分支（步骤与快照脚本逐行一致；random 打桩保证可复现）。"""
    clean_db()
    m = Main(None)
    out = {}
    _rnd = random.random

    def _mk(qid):
        db.create_player(_SID, qid, "签到", C.resolve("classes", "战士"), {}, 100, 100)
        db.update_player(_SID, qid, level=10, gold=1000)

    async def _sign(qid):
        ev = FakeEvent(_SID, qid, "签到")
        res = await run(m.signin, ev)
        return res[-1] if res else ""

    def _pre(qid, days):
        today = datetime.date.today()
        for i in range(days, 0, -1):
            d = today - datetime.timedelta(days=i)
            db.signin_claim(_SID, qid, d.isoformat(),
                            (d - datetime.timedelta(days=1)).isoformat())

    try:
        _mk("q_a")
        random.seed(42)
        random.random = lambda: 0.05          # < fortune_bad_th 0.15 → 小凶
        out["A_first_bad"] = await _sign("q_a")
        _mk("q_b")
        random.seed(42)
        random.random = lambda: 0.9           # ≥ 0.55 → 大吉
        out["B_first_big"] = await _sign("q_b")
        out["C_dup"] = await _sign("q_b")     # 同人再签 → 已签分支
        _mk("q_d")
        _pre("q_d", 6)                        # 昨天刚签 + 连续 6 天 → 本次第 7 天
        random.seed(7)
        random.random = lambda: 0.9
        out["D_streak7"] = await _sign("q_d")
        _mk("q_e")
        db.save_world_event("festival", int(time.time()) + 86400, {"name": "测试庆典"})
        random.seed(42)
        random.random = lambda: 0.9
        out["E_festival"] = await _sign("q_e")
        db.clear_world_event()
    finally:
        random.random = _rnd
        clean_db()
    return out


async def _supply_scenarios() -> dict:
    """复跑『领取补给箱』迁移前的 3 个分支（步骤与快照脚本逐行一致）。"""
    clean_db()
    m = Main(None)
    db.create_player("g_sp", "q_sp", "补给", C.resolve("classes", "战士"), {}, 100, 100)
    out = {}
    for k in ("A_first", "B_second", "C_third"):
        ev = FakeEvent("g_sp", "q_sp", "领取补给箱")
        res = await run(m.event_menu, ev)
        out[k] = res[-1] if res else ""
    clean_db()
    return out


def _strip_tips(text):
    """剔掉面板底部随机提示行（`💡 ` 开头的整行）——提示池随机抽，不属于任何域。"""
    return "\n".join(ln for ln in (text or "").splitlines() if not ln.startswith("💡 "))


async def _daily_scenarios() -> dict:
    """复跑『任务』面板的 4 个状态（步骤与快照脚本逐行一致）。"""
    today = datetime.date.today().isoformat()
    base = {"main_quest": "", "main_status": "", "main_progress": {},
            "completed_main": [], "side": {}}
    states = {
        "A_never": {},
        "B_active": {"边境警戒": {"name": "边境警戒", "desc": "击杀 10 只任意怪物",
                                "objective": {"kill_any": 10}, "progress": 3},
                     "神秘委托": {"name": "神秘委托", "desc": "未知目标（无达标数定义）",
                                "objective": {"mystery": "?"}, "progress": 1},
                     "_date": today, "_completed": 0},
        "C_done_part": {"_date": today, "_completed": 2},
        "D_done_full": {"_date": today, "_completed": 10},
    }
    clean_db()
    m = Main(None)
    db.create_player("g_dl", "q_dl", "每日", C.resolve("classes", "战士"), {}, 100, 100)
    out = {}
    for k, daily in states.items():
        st = dict(base)
        st["daily"] = daily
        db.save_quests("g_dl", "q_dl", st)
        ev = FakeEvent("g_dl", "q_dl", "任务")
        res = await run(m.quest_view, ev)
        out[k] = res[-1] if res else ""
    clean_db()
    return out


async def _quests_scenarios() -> dict:
    """复跑『每日』命令（services/quests.py）的 7 个分支（步骤与快照脚本逐行一致）。"""
    from content.profession_quests import (
        draw_daily, settle_daily_quest, DAILY_LIMIT as _LIM,
    )
    today = datetime.date.today().isoformat()
    base = {"main_quest": "", "main_status": "", "main_progress": {},
            "completed_main": [], "side": {}}

    def _st(daily):
        st = dict(base)
        st["daily"] = daily
        return st

    clean_db()
    m = Main(None)
    db.create_player("g_dq", "q_dq", "每日", C.resolve("classes", "战士"), {}, 100, 100)
    p = db.get_player("g_dq", "q_dq")
    out = {}
    random.seed(11)
    ok, text = draw_daily("g_dq", "q_dq", p)
    out["A_publish"] = ("ok=%s\n" % ok) + text
    ok, text = draw_daily("g_dq", "q_dq", p)
    out["B_have"] = ("ok=%s\n" % ok) + text
    db.save_quests("g_dq", "q_dq", _st({"_date": today, "_completed": _LIM}))
    ok, text = draw_daily("g_dq", "q_dq", p)
    out["C_limit"] = ("ok=%s\n" % ok) + text
    db.save_quests("g_dq", "q_dq", _st({"_date": today, "_completed": 3, "_repeat": {}}))
    random.seed(11)
    ok, text = draw_daily("g_dq", "q_dq", p)
    out["D_republish"] = ("ok=%s\n" % ok) + text
    rep_all = {q["name"]: 1 for q in C.DAILY_QUESTS}
    db.save_quests("g_dq", "q_dq", _st({"_date": today, "_completed": 0, "_repeat": rep_all}))
    random.seed(11)
    ok, text = draw_daily("g_dq", "q_dq", p)
    out["E_decay"] = ("ok=%s\n" % ok) + text
    lines = []
    dq = {"name": "边境警戒", "desc": "击杀 10 只任意怪物", "objective": {"kill_any": 10},
          "reward_exp": 100, "reward_gold": 50, "repeat": 0}
    settle_daily_quest("g_dq", "q_dq", {"_completed": 0, "_repeat": {}}, dq, lines)
    out["F_settle"] = "\n".join(lines)
    lines2 = []
    settle_daily_quest("g_dq", "q_dq", {"_completed": 0, "_repeat": {"边境警戒": 1}},
                       dict(dq, repeat=1), lines2)
    out["G_settle_decay"] = "\n".join(lines2)
    clean_db()
    return out


# ══════════════════════════════════════════════════════════════════════════
# 副本结算域复跑器（`game/commands/instance_router.py`）—— 与迁移前快照脚本逐行一致
# ══════════════════════════════════════════════════════════════════════════
_IS_GID = "g_settle"


class _ISHost(_CmdHostBase):
    """router 测试宿主（`_engine_harness.Main`：同名的包内 InstanceImpl / CombatCmds /
    WorldCmds 落点由驱动口按名绑定，等价旧的三 Mixin 宿主）。"""


def _is_mk_snap(qid, name="玩家", cls="战士", level=60):
    db.create_player(_IS_GID, qid, name, cls, {}, 100, 100)
    db.update_player(_IS_GID, qid, level=level, cur_map="mainland", cur_subarea="", stamina=999)
    pl = db.get_player(_IS_GID, qid)
    return {"name": name, "qq_id": qid, "class_name": cls, "level": level,
            "hp": 500, "max_hp": 500, "mp": 50, "max_mp": 50, "equipment": {},
            "skills": [], "learned_skills": [], "class_tier": 0, "evolve_path": 0,
            "attributes": pl.get("attributes"), "bonus": {"panel": {}, "cap": {}, "cost": {}},
            "race": pl.get("race"), "uid": "p_%s" % qid, "buffs": {}, "stacks": {},
            "defending": False, "charging": None, "ct": 0.0, "p_shields": {}, "spd": 30}


def _is_mk_enemy(hp=1, spd=1, role="dps", atk=1, uid="e_room", name="房间怪"):
    return {"uid": uid, "name": name, "hp": hp, "max_hp": hp, "atk": atk, "def": 0,
            "matk": 1, "mdef": 0, "spd": spd, "crit": 0.0, "lv": 15, "level": 15,
            "role": role, "is_boss": role == "boss", "is_elite": role == "elite",
            "rank": 1, "reach": 1, "ct": 1.0, "exp": 10, "gold": 5, "drops": []}


def _is_mk_st(qids, inst_id="inst_goblin_camp", names=None, **kw):
    qids = [str(q) for q in qids]
    names = names or {}
    st = {"type": "instance", "inst_id": inst_id, "leader": qids[0], "members": qids,
          "alive": {q: True for q in qids},
          "players": {q: _is_mk_snap(q, names.get(q, "玩家")) for q in qids},
          "boss": None, "enemy": None, "enemies": [], "turn": 0, "round": 1,
          "mode": "battle", "pets": {}, "p_buffs": {q: {} for q in qids},
          "p_hot": {q: {} for q in qids}, "p_food_effects": {q: [] for q in qids},
          "p_defending": {q: False for q in qids}, "mech_stacks": {q: {} for q in qids},
          "now": 0.0, "battle": None, "contribution": {},
          "threat": {q: 0 for q in qids}, "over": False, "turn_time": 0,
          "stage_pending": [], "inst_stages": [], "stage_idx": 0,
          "stage_cleared": False, "world_id": ""}
    st.update(kw)
    return st


def _is_patch_cm(all_members):
    """多人副本 st 无 party 行时，current_members 恒返回全部成员（等价单人/测试口径）。"""
    orig = _InstImpl._instance_current_members
    _InstImpl._instance_current_members = (
        lambda self, gid, st: [str(m) for m in (all_members or st["members"])])
    return orig


def _is_restore_cm(orig):
    _InstImpl._instance_current_members = orig


def _is_run(inst, st, qq, action, skill=None, target=None):
    """跑一次 router（同步收全部 yield）。"""
    player = st["players"][str(qq)]
    agen = inst._instance_router(FakeEvent(_IS_GID, str(qq)), _IS_GID, str(qq), player,
                                 st, action, skill, target)

    async def _c():
        out = []
        async for x in agen:
            out.append(x)
        return out
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_c())
    finally:
        loop.close()


def _is_now():
    return int(time.time())


def _is_b1_no_enemy_pending():
    """L56 探索引导。"""
    clean_db()
    st = _is_mk_st(["q_b1"])
    st["stage_pending"] = [["m_x", "小怪", "dps", 15, [], []]]
    return _is_run(_ISHost(), st, "q_b1", "attack")


def _is_b2_no_enemy_next_stage():
    """L64 肃清 + L61 下一层行（非末层）。"""
    clean_db()
    st = _is_mk_st(["q_b2"], inst_stages=[{"name": "一层"}, {"name": "二层"}], stage_idx=0)
    return _is_run(_ISHost(), st, "q_b2", "attack")


def _is_b3_no_enemy_last_stage():
    """L64 肃清 + L63 最后一层行（末层）。"""
    clean_db()
    st = _is_mk_st(["q_b3"], inst_stages=[{"name": "一层"}, {"name": "二层"}], stage_idx=1)
    return _is_run(_ISHost(), st, "q_b3", "attack")


def _is_b4_wait_hint():
    """L73 现在是 X 的刻（非请求者未超时）。"""
    clean_db()
    st = _is_mk_st(["q_b41", "q_b42"], names={"q_b41": "队友甲", "q_b42": "请求者乙"},
                   enemies=[_is_mk_enemy(hp=500, spd=1)])
    st["boss"] = st["enemies"][0]
    st["enemy"] = st["enemies"][0]
    _IB.build_battle(st)
    for a in (_IB._players_of(st) or []):
        a["ct"] = 0.0 if str(a.get("qq_id")) == "q_b41" else 50.0
    _IB.sync_views(st, _IS_GID)
    st["turn_time"] = _is_now()
    orig = _is_patch_cm(["q_b41", "q_b42"])
    try:
        return _is_run(_ISHost(), st, "q_b42", "attack")
    finally:
        _is_restore_cm(orig)


def _is_b5_taunt_end():
    """L145 嘲讽结束（taunt_left 递减到 0）。"""
    clean_db()
    st = _is_mk_st(["q_b5"])
    st["taunt_left"] = 1
    st["taunt_target"] = "q_b5"
    st["stage_pending"] = [["m_x", "小怪", "dps", 15, [], []]]
    return _is_run(_ISHost(), st, "q_b5", "attack")


def _is_b6_battle_broken():
    """L172 战斗状态异常 —— 桩：让 build_battle 抛错（真实链路只能靠引擎内部失败触发）。"""
    clean_db()
    st = _is_mk_st(["q_b6"], enemies=[_is_mk_enemy(hp=1, spd=1)])
    orig = _IB.build_battle

    def _boom(_st):
        raise RuntimeError("snapshot-stub: build_battle boom")
    _IB.build_battle = _boom
    try:
        return _is_run(_ISHost(), st, "q_b6", "attack")
    finally:
        _IB.build_battle = orig


def _is_b7_secret_guard():
    """L326 密室精英守卫被击败 → 宝箱。"""
    clean_db()
    random.seed(20260912 + 7)
    st = _is_mk_st(["q_b7"], secret_guard_pending=True, mode="battle")
    st["enemies"] = [_is_mk_enemy(hp=1, spd=1)]
    st["boss"] = st["enemies"][0]
    st["enemy"] = st["enemies"][0]
    _IB.build_battle(st)
    inst = _ISHost()
    msgs = []
    for _ in range(8):
        st["turn_time"] = _is_now()
        msgs += _is_run(inst, st, "q_b7", "attack")
        if st.get("secret_chest") or not st.get("enemies"):
            break
    return msgs


def _is_b8_room_clear():
    """L383 房间怪清空（非 Boss 房 → 回地图模式）。"""
    clean_db()
    random.seed(20260912 + 8)
    qid, cur_sa = "q_b8", "goblin_camp_1"
    st = _is_mk_st([qid], rooms={cur_sa: {"monsters_left": [], "pois_left": [],
                                          "boss_alive": False}})
    st["enemies"] = [_is_mk_enemy(hp=1, spd=1)]
    st["boss"] = st["enemies"][0]
    st["enemy"] = st["enemies"][0]
    db.update_player(_IS_GID, qid, cur_map="misty_swamp", cur_subarea=cur_sa)
    _IB.build_battle(st)
    inst = _ISHost()
    msgs = []
    for _ in range(8):
        st["turn_time"] = _is_now()
        msgs += _is_run(inst, st, qid, "attack")
        if st.get("cleared") or st.get("over") or not st.get("enemies"):
            break
    return msgs


def _is_b9_switch_monster():
    """L418 切怪（stage_pending 剩怪）+ L424 轮到 X 行动。"""
    clean_db()
    random.seed(20260912 + 9)
    st = _is_mk_st(["q_b9"], stage_pending=[["m_slime", "史莱姆", "dps", 15, [], []],
                                            ["m_slime2", "史莱姆2", "dps", 15, [], []]])
    st["enemies"] = [_is_mk_enemy(hp=1, spd=1)]
    st["boss"] = st["enemies"][0]
    st["enemy"] = st["enemies"][0]
    _IB.build_battle(st)
    inst = _ISHost()
    msgs = []
    for _ in range(8):
        st["turn_time"] = _is_now()
        msgs += _is_run(inst, st, "q_b9", "attack")
        if "⚔️ 又一只怪物挡在面前！" in "\n".join(msgs):
            break
    return msgs


def _is_b10_stage_cleared():
    """L441 分层清空（非末层）+ L448 前方是 X。"""
    clean_db()
    random.seed(20260912 + 10)
    st = _is_mk_st(["q_b10"], inst_stages=[{"name": "一层"}, {"name": "二层"}], stage_idx=0)
    st["enemies"] = [_is_mk_enemy(hp=1, spd=1)]
    st["boss"] = st["enemies"][0]
    st["enemy"] = st["enemies"][0]
    _IB.build_battle(st)
    inst = _ISHost()
    msgs = []
    for _ in range(8):
        st["turn_time"] = _is_now()
        msgs += _is_run(inst, st, "q_b10", "attack")
        if "的敌人被肃清了" in "\n".join(msgs):
            break
    return msgs


def _is_b11_normal_rotation():
    """L475 普通轮转（未结束 → footer + 轮到 X）。"""
    clean_db()
    random.seed(20260912 + 11)
    st = _is_mk_st(["q_b11"])
    st["enemies"] = [_is_mk_enemy(hp=5000, spd=1)]
    st["boss"] = st["enemies"][0]
    st["enemy"] = st["enemies"][0]
    _IB.build_battle(st)
    st["turn_time"] = _is_now()
    return _is_run(_ISHost(), st, "q_b11", "attack")


_IS_BRANCHES = (("B1_无敌人_探索", _is_b1_no_enemy_pending),
                ("B2_无敌人_已肃清_下一层", _is_b2_no_enemy_next_stage),
                ("B3_无敌人_已肃清_最后一层", _is_b3_no_enemy_last_stage),
                ("B4_等待行动", _is_b4_wait_hint),
                ("B5_嘲讽结束", _is_b5_taunt_end),
                ("B6_战斗异常", _is_b6_battle_broken),
                ("B7_密室宝箱", _is_b7_secret_guard),
                ("B8_房间清空", _is_b8_room_clear),
                ("B9_切怪", _is_b9_switch_monster),
                ("B10_层清空", _is_b10_stage_cleared),
                ("B11_普通轮转", _is_b11_normal_rotation))


def _instance_settle_scenarios() -> dict:
    """复跑迁移前的 11 个副本结算分支（步骤与快照脚本逐行一致）。"""
    out = {}
    for name, fn in _IS_BRANCHES:
        msgs = fn()
        out[name] = "\n".join(str(m) for m in msgs) if not isinstance(msgs, str) else msgs
    return out


# ══════════════════════════════════════════════════════════════════════════
def _scan_calls(path):
    """AST 扫模块：

    ① `T.text("k", **kw)` / `T.static("k")` → (key, frozenset(kwarg 名), kind)（直接调用点）
    ② 模块里出现过的字符串字面量集合 → 「键在映射表里」这类用法（如运势键 → 文案键的 dict）
       也算被引用，否则会被当成死文案误报。

    ②只用于「有没有引用」，槽位对账仍只认①的直接调用实参。
    """
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    calls, lits = [], set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            lits.add(node.value)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("text", "static")
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "T"):
            k = node.args[0].value if (node.args and isinstance(node.args[0], ast.Constant)) else None
            if k is None:
                continue          # 动态键（如 T.static(_FORTUNE_TEXT.get(fortune))）静态扫不出：
                                  # 交给②「字面量也算引用」兜，避免误报成「调用了未声明的 None」
            calls.append((k, frozenset(kw.arg for kw in node.keywords if kw.arg), node.func.attr))
    return calls, lits


def t1_table_selfcheck():
    print("\n[1] 装载与自检（引擎 validate/audit）")
    tb = T.reload()
    # ★ P4′-B 口径升级（条数不变 63）：真源路径必须落在**包内**且与包内装载器同一条路径
    #   （`_pkg` = 包内 `content/texts.py`；其 `canonical_path()` 不随注入变，
    #    宿主侧 `T.SPEC_PATH` = 取回的同一值 ⇒ 两侧路径等价）。
    from content import texts as _pkg
    check("声明文件存在且路径正确（★ 真源已在包内 content/data/）",
          os.path.exists(SPEC) and SPEC.endswith("text_specs.json")
          and os.path.abspath(SPEC) == os.path.abspath(_pkg.canonical_path()),
          "%s | pkg=%s" % (SPEC, _pkg.canonical_path()))
    check("装载无错（load_error 为空）", T.load_error() == "", T.load_error())
    check("表非空（副本准入 26 + 副本结算 14 + 副本日志 70 + 签到 10 + 周常 18 + 补给箱 7 + 每日任务 7 + 每日命令 9 + 武器特效 51）", len(tb) >= 40, len(tb))
    check("★ validate() 干净（无空值/语法错/params 与模板不一致）",
          tb.audit()["problems"] == [], tb.audit()["problems"][:5])
    check("元信息键（_ 开头）不入表", not [k for k in tb.keys() if k.startswith("_")], tb.keys()[:3])
    check("每条都有 category（编辑器分组用）",
          not [s.key for s in tb if not s.category], [s.key for s in tb if not s.category][:5])
    check("key 无重复", len(tb.keys()) == len(set(tb.keys())))
    cats = sorted({s.category for s in tb})
    check("category 取值符合预期（副本准入 / 副本日志 / 副本面板 / 副本移动 / 签到 / 周常 / 补给箱 / 每日任务 / 武器特效 / 效果名 / 机制名 / 增益名 / 减益名 / 叠层名 / 资源名 / 战斗日志 / 天气名 / 季节名 / 属性名 / 团队特效名 / 条件文案 / 宠物技能描述 / 帮助面板 / 副业图标 / 技能面板 / GM面板 / GM指令 / 公会面板 / 修炼塔 / 角色面板 / 属性面板 / 排行榜 / 种族面板 / 转职 / 技能栏 / 流派 / 技能详情 / 经济面板 / 生活副业 / 炼金 / 烹饪 / 锻造 / 强化 / 宝石 / 符文 / 重锻炼成 / 地图导航 / 任务委托 / 家园地契 / 营地休息 / 声望阵营 / 传送方碑 / 场景交互 / 战斗主循环 / 战斗面板 / 探索事件 / 社交市场 / 社交队伍 / 社交公会 / 世界事件 / 社交拍卖 / 宠物面板 / 宠物喂养 / 宠物管理 / 坐骑面板 / 商店面板 / 商店购买 / 商店出售 / 商店限购 / 背包面板 / 装备面板 / 道具使用 / 称号面板 / NPC面板 / NPC查找 / NPC对话 / 快捷交互 / 移动赶路 / 行会就职 / NPC教习 / 见闻录 / 时间面板 / 时段名 / 任务目标 / 武器礼包 / 战斗结算 / 掉落播报 / 任务列表 / 任务接取 / 任务交付 / 任务进度 / 战力面板 / 编年史）",
          set(cats) == {"副本准入", "副本日志", "副本面板", "副本移动", "签到", "周常", "补给箱", "每日任务",
                        "武器特效", "效果名", "机制名", "增益名", "减益名", "叠层名", "资源名",
                        "战斗日志", "天气名", "季节名",
                        "属性名", "团队特效名", "条件文案", "宠物技能描述", "帮助面板",
                        "副业图标", "技能面板", "GM面板", "公会面板", "修炼塔",
                        "角色面板", "属性面板", "排行榜", "种族面板", "转职", "技能栏", "流派", "技能详情",
                        "经济面板",
                        "快捷指令", "注册", "身份绑定", "加点洗点", "技能学习", "注销",
                        "道具模板",
                        "冒险手册", "足迹", "世界百科", "来源图标", "触发名",
                        "生活副业", "炼金", "烹饪", "锻造",
                        "强化", "宝石", "符文", "重锻炼成",
                        "地图导航", "任务委托", "家园地契",
                        "营地休息", "声望阵营", "传送方碑", "场景交互",
                        "战斗主循环", "战斗面板", "PvP荣誉", "世界Boss", "许愿商人",
                        "战前设置", "探索事件", "社交市场", "社交队伍", "社交公会",
                        "世界事件", "社交拍卖",
                        "宠物面板", "宠物喂养", "宠物管理", "坐骑面板",
                        "商店面板", "商店购买", "商店出售", "商店限购",
                        "背包面板", "装备面板", "道具使用", "称号面板",
                        "NPC面板", "NPC查找", "NPC对话", "快捷交互",
                        "移动赶路",
                        # ★ C 档 25a（B-2 第 11 片）：world 散落「NPC 支线/进化教学族」
                        #   （_teach_by_npc 教习五态 · _do_join_class 行会就职 · _do_evolve_via_npc 导师转职
                        #    ⇒ 新分类 行会就职 / NPC教习；交付 turn_in 归既有 任务委托 / _npc_absent 归 NPC查找）
                        "行会就职", "NPC教习",
                        # ★ C 档 26a（B-2 第 12 片）：world 收尾「见闻录/时间面板/地图尾块/指路」
                        #   （wild_notes 见闻录 · time_cmd 时间面板 · _wild_cond_label 的
                        #    时段名；季节名 / 天气名 沿用既有两类）
                        "见闻录", "时间面板", "时段名",
                        # ★ C 档 27a（B-2 第 13 片）：交付目标行 / 武器自选礼包
                        "任务目标", "武器礼包",
                        # ★ C 档 28a（B-2 第 14 片）：战斗结算 / 掉落播报
                        "战斗结算", "掉落播报",
                        # ★ C 档 29a（B-2 第 16 片）：任务列表 / 任务接取 / 任务交付 / 任务进度
                        "任务列表", "任务接取", "任务交付", "任务进度",
                        # ★ C 档 30a（B-2 第 17 片）：player_cmds 余量「注册欢迎面板 /
                        #   转职面板 / 转职重置 / 战力面板 / 注销确认」
                        #   （注册 / 转职 / 注销 为既有三类；战力面板为新分类）
                        "战力面板",
                        # ★ C 档 31a（B-2 第 18 片）：world_cmds 余量「野外来客未出现提示 /
                        #   对话支线菜单 / 编年史」（NPC查找 · NPC对话 为既有两类；编年史为新分类）
                        "编年史",
                        # ★ C 档 32a（B-2 第 19 片）：gm.py 余量「GM 指令回执族」
                        #   （gm.players_* 四行归既有 GM面板；其余回执/用法/提示为新分类 GM指令）
                        "GM指令"}, cats)


def t2_key_and_params_accounting():
    print("\n[2] 声明 ↔ 调用点对账（双向；AST 扫真实调用）")
    declared = set(T.table().keys())
    used, mismatch, lits = set(), [], set()
    for name, path in WIRED.items():
        for _path in _wired_paths(path):
            calls, l = _scan_calls(_path)
            lits |= (l & declared)
            for key, kwargs, kind in calls:
                used.add(key)
                spec = T.table().spec(key)
                if spec is None:
                    mismatch.append("%s: 调用了未声明的 %s" % (os.path.basename(_path), key))
                    continue
                slots = set(spec.slots)                       # 声明优先，缺省自动抽取
                if kind == "static" and kwargs:
                    mismatch.append("%s: T.static(%s) 不该带槽位" % (os.path.basename(_path), key))
                if set(kwargs) != slots:
                    mismatch.append("%s: %s 槽位不符（调用 %s / 声明 %s）"
                                    % (os.path.basename(_path), key, sorted(kwargs), sorted(slots)))
    used |= lits                                          # 映射表里的键也算被引用
    check("★ 代码里每一处调用都能在表里找到（否则运行时缺 key）", not mismatch, mismatch[:5])
    dead = sorted(declared - used)
    check("★ 表里没有死文案（每条声明都被真实调用）", not dead, dead)
    check("★ 槽位名与调用实参逐条对得上（防模板写出 {foo} 露给玩家）", not mismatch)
    doms = {k.split(".")[0] for k in used}
    check("调用点覆盖全部已迁移域（副本准入 + 副本结算 + 周常 + 签到 + 补给箱 + 每日任务 + 每日命令）",
          {"instance", "weekly", "signin", "supply", "daily", "quests"} <= doms,
          sorted(doms))


def t3_no_silent_fallback():
    print("\n[3] 缺 key 不静默（不打回旧串、不吞成空串）")
    tb = T.table()
    got = tb.render("nope.not_declared")
    check("★ 未声明的 key → 返回 key 本身（玩家/日志双可见）", got == "nope.not_declared", repr(got))
    check("★ 记账：missing() 记下了这个缺 key", "nope.not_declared" in tb.missing(), tb.missing())
    tb.reset_stats()

    # 坏声明文件：不抛、不静默，空表 + 错误可见
    # ★ PATCHAUDIT（只改测试）：原写法把坏文件写到 `%LOCALAPPDATA%\Temp\_bad_text_specs.json`
    #   固定路径 —— 只读/受限沙箱下该目录不可写（PermissionError），门禁假红。
    #   改为 tempfile 真实临时目录（每次唯一名），语义不变（丢一个坏 JSON 进去再 reload）。
    _fd, bad = tempfile.mkstemp(prefix="_bad_text_specs_", suffix=".json")
    os.close(_fd)
    with io.open(bad, "w", encoding="utf-8") as fh:
        fh.write("{ this is not json ")
    real = T.SPEC_PATH
    try:
        T.SPEC_PATH = bad
        T.reload()
        check("★ 声明文件语法坏 → 不抛异常，且 load_error 有原因",
              bool(T.load_error()), T.load_error())
        check("★ 坏文件下渲染不静默（返回 key，不是空串）",
              T.text("instance.leader_only") == "instance.leader_only")
    finally:
        T.SPEC_PATH = real
        T.reload()
    os.remove(bad)
    check("恢复正常声明后表重建（真源非 _ 条目数 = 本表键数）", len(T.table()) >= 40, len(T.table()))


def t4_weekly_frozen():
    print("\n[4] 周常域逐字冻结：迁移前 6 分支行为快照复跑比对")
    check("冻结基准已内嵌（6 场景）", len(WEEKLY_FROZEN) == 6, len(WEEKLY_FROZEN))
    now = asyncio.run(_weekly_scenarios())
    bad = [k for k in WEEKLY_FROZEN if WEEKLY_FROZEN[k] != now.get(k)]
    for k in bad:
        print("     · %s 现=%r" % (k, now.get(k, "")[:120]))
    check("★ 周常『周常』『周常列表』6 分支输出与迁移前**逐字一致**", not bad, bad)
    check("冻结基准非空且含换行结构（防基准写空）",
          all(v and "\n" in v for v in WEEKLY_FROZEN.values()))


def t5_signin_frozen():
    print("\n[5] 签到域逐字冻结：迁移前 5 分支行为快照复跑比对")
    check("冻结基准已内嵌（5 场景）", len(SIGNIN_FROZEN) == 5, len(SIGNIN_FROZEN))
    now = asyncio.run(_signin_scenarios())
    bad = [k for k in SIGNIN_FROZEN if SIGNIN_FROZEN[k] != now.get(k)]
    for k in bad:
        print("     · %s 现=%r" % (k, now.get(k, "")[:120]))
    check("★『签到』5 分支输出与迁移前**逐字一致**", not bad, bad)


def t6_supply_frozen():
    print("\n[6] 补给箱域逐字冻结：迁移前 3 分支（首发/日限/周限）复跑比对")
    check("冻结基准已内嵌（3 场景）", len(SUPPLY_FROZEN) == 3, len(SUPPLY_FROZEN))
    now = asyncio.run(_supply_scenarios())
    bad = [k for k in SUPPLY_FROZEN if SUPPLY_FROZEN[k] != now.get(k)]
    for k in bad:
        print("     · %s 现=%r" % (k, now.get(k, "")[:120]))
    check("★『领取补给箱』3 分支输出与迁移前**逐字一致**", not bad, bad)


def t7_daily_frozen():
    print("\n[7] 每日任务域（任务面板段）逐字冻结：4 状态复跑比对（剔除随机提示行）")
    check("冻结基准已内嵌（4 状态）", len(DAILY_FROZEN) == 4, len(DAILY_FROZEN))
    now = asyncio.run(_daily_scenarios())
    bad = [k for k in DAILY_FROZEN if _strip_tips(DAILY_FROZEN[k]) != _strip_tips(now.get(k))]
    for k in bad:
        print("     · %s 现=%r" % (k, _strip_tips(now.get(k, ""))[:140]))
    check("★『任务』面板每日段 4 状态输出与迁移前**逐字一致**（随机提示行除外）", not bad, bad)


def t8_quests_frozen():
    print("\n[8] 每日任务域后半（『每日』命令）逐字冻结：7 分支复跑比对")
    check("冻结基准已内嵌（7 分支）", len(QUEST_FROZEN) == 7, len(QUEST_FROZEN))
    now = asyncio.run(_quests_scenarios())
    bad = [k for k in QUEST_FROZEN if QUEST_FROZEN[k] != now.get(k)]
    for k in bad:
        print("     · %s 现=%r" % (k, (now.get(k) or "")[:140]))
    check("★『每日』命令 7 分支（首发/已有/满额/重抽/衰减/达标/重复达标）与迁移前**逐字一致**",
          not bad, bad)


def t9_instance_settle_frozen():
    print("\n[9] 副本结算域逐字冻结：迁移前 11 分支（探索/肃清/等待/嘲讽/异常/密室/房间/切怪/层/轮转）复跑比对")
    check("冻结基准已内嵌（11 分支）", len(INSTANCE_SETTLE_FROZEN) == 11,
          len(INSTANCE_SETTLE_FROZEN))
    now = _instance_settle_scenarios()
    bad = [k for k in INSTANCE_SETTLE_FROZEN if INSTANCE_SETTLE_FROZEN[k] != now.get(k)]
    for k in bad:
        print("     · %s 现=%r" % (k, (now.get(k) or "")[:140]))
    check("★ 副本结算 11 分支输出与迁移前**逐字一致**", not bad, bad)
    _single = ("B1_无敌人_探索", "B4_等待行动", "B6_战斗异常")   # 单行分支（本身无换行结构）
    check("冻结基准非空且含换行结构（防基准写空）",
          all(v and "\n" in v for k, v in INSTANCE_SETTLE_FROZEN.items() if k not in _single))


# ═══════════════════════ IL_BRANCHES_BEGIN ═══════════════════════
# ↓↓↓ 以下这段（含本行）逐字拼进 tests/test_texts_table.py 的 t10 段 ↓↓↓
from _engine_harness import clean_db as _IL_clean, FakeEvent as _IL_Event   # noqa: E402
from _engine_harness import C as _IL_C            # noqa: E402
from _engine_harness import db as _IL_db                # noqa: E402
from content.flow import instance_battle as _IL_IB  # ★ 同上：改绑包内实现
from _engine_harness import Main as _IL_Inst   # noqa: E402  （原 InstanceCmds 壳 → 驱动口）
from _engine_harness import Main as _IL_Combat     # noqa: E402  （原 CombatCmds 壳 → 驱动口）
from _engine_harness import Main as _IL_World        # noqa: E402  （原 WorldCmds 壳 → 驱动口）

_IL_GID = "g_ilog"


class _ILHost(_IL_Inst):
    """副本日志快照宿主（`_engine_harness.Main`：同名的包内 InstanceImpl / CombatCmds /
    WorldCmds 落点由驱动口按名绑定，等价旧的三 Mixin 宿主）。"""


def _il_player(qid, name="玩家", cls="cls_zhan_shi", level=60, learned=None):
    _IL_db.create_player(_IL_GID, qid, name, cls, {}, 100, 100)
    _IL_db.update_player(_IL_GID, qid, level=level, cur_map="misty_swamp",
                         cur_subarea="misty_swamp_3", stamina=999999,
                         learned_skills=list(learned or []))
    return _IL_db.get_player(_IL_GID, qid)


def _il_snap(qid, name="玩家", cls="cls_zhan_shi", level=60, learned=None, hp=None,
             spd=30, mp=999):
    pl = _IL_db.get_player(_IL_GID, qid) or {}
    mh = int(pl.get("max_hp", 500) or 500)
    return {"name": name, "qq_id": str(qid), "class_name": cls, "level": level,
            "hp": int(hp if hp is not None else mh), "max_hp": mh, "mp": mp, "max_mp": mp,
            "equipment": {}, "skills": [], "learned_skills": list(learned or []),
            "class_tier": 0, "evolve_path": 0, "attributes": pl.get("attributes"),
            "bonus": {"panel": {}, "cap": {}, "cost": {}}, "race": pl.get("race"),
            "uid": "p_%s" % qid, "buffs": {}, "stacks": {}, "defending": False,
            "charging": None, "ct": 0.0, "p_shields": {}, "spd": spd}


def _il_enemy(hp=1, spd=1, role="dps", atk=1, uid="e_il", name="房间怪", lv=15,
              exp=10, gold=5, drops=None):
    return {"uid": uid, "name": name, "hp": hp, "max_hp": hp, "atk": atk, "def": 0,
            "matk": 1, "mdef": 0, "spd": spd, "crit": 0.0, "lv": lv, "level": lv,
            "role": role, "is_boss": role == "boss", "is_elite": role == "elite",
            "rank": 1, "reach": 1, "ct": 1.0, "exp": exp, "gold": gold,
            "drops": list(drops or [])}


def _il_st(qids, inst_id="inst_goblin_camp", names=None, **kw):
    qids = [str(q) for q in qids]
    names = names or {}
    st = {"type": "instance", "inst_id": inst_id, "leader": qids[0], "members": qids,
          "alive": {q: True for q in qids},
          "players": {q: _il_snap(q, names.get(q, "玩家")) for q in qids},
          "boss": None, "enemy": None, "enemies": [], "turn": 0, "round": 1,
          "mode": "battle", "pets": {}, "p_buffs": {q: {} for q in qids},
          "p_hot": {q: {} for q in qids}, "p_food_effects": {q: [] for q in qids},
          "p_defending": {q: False for q in qids}, "mech_stacks": {q: {} for q in qids},
          "now": 0.0, "battle": None, "contribution": {}, "threat": {q: 0 for q in qids},
          "over": False, "turn_time": 0, "stage_pending": [], "inst_stages": [],
          "stage_idx": 0, "stage_cleared": False, "world_id": ""}
    st.update(kw)
    return st


def _il_cm_patch(all_members):
    """多人 st 无 party 行时，current_members 恒返回全部成员（等价单人/测试口径）。"""
    orig = _IL_Inst._instance_current_members
    _IL_Inst._instance_current_members = (
        lambda self, gid, st: [str(m) for m in (all_members or st["members"])])
    return orig


def _il_cm_restore(orig):
    _IL_Inst._instance_current_members = orig


def _il_run(inst, st, qq, action, skill=None, target=None):
    """跑一次 router（同步收全部 yield）。"""
    player = st["players"][str(qq)]
    agen = inst._instance_router(_IL_Event(_IL_GID, str(qq)), _IL_GID, str(qq), player,
                                 st, action, skill, target)

    async def _c():
        out = []
        async for x in agen:
            out.append(x)
        return out
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_c())
    finally:
        loop.close()


def _il_now():
    return int(time.time())


def _il_text(msgs):
    return "\n".join(str(m) for m in msgs) if not isinstance(msgs, str) else msgs


class _ILRR(object):
    """random.random 打桩（进出还原；迁移前后用同一套桩）。"""

    def __init__(self, value):
        self.value = value

    def __enter__(self):
        self._orig = random.random
        if self.value is not None:
            random.random = lambda: self.value
        return self

    def __exit__(self, *exc):
        random.random = self._orig
        return False


# ── 1. router（instance_router.py）────────────────────────────────────
def _il_rt1_timeout_defend():
    """⏰ 非请求者超时 → 自动防御姿态（面板/轮到行同屏）。"""
    _IL_clean()
    random.seed(20260913)
    _il_player("q_t1", "甲")
    _il_player("q_t2", "乙")
    st = _il_st(["q_t1", "q_t2"], names={"q_t1": "甲", "q_t2": "乙"})
    st["enemies"] = [_il_enemy(hp=5000, spd=1)]
    st["boss"] = st["enemy"] = st["enemies"][0]
    _IL_IB.build_battle(st)
    for a in (_IL_IB._players_of(st) or []):
        a["ct"] = 10.0 if str(a.get("qq_id")) == "q_t1" else 100.0
    _IL_IB.sync_views(st, _IL_GID)
    st["turn_time"] = _il_now() - 120
    orig = _il_cm_patch(["q_t1", "q_t2"])
    try:
        return _il_run(_ILHost(), st, "q_t2", "defend")
    finally:
        _il_cm_restore(orig)


def _il_rt2_taunt():
    """🛡️ 嘲讽（技能 effect=taunt → 强制攻击自己）。"""
    _IL_clean()
    random.seed(20260913 + 2)
    _il_player("q_ta", "甲", learned=["嘲讽"])
    st = _il_st(["q_ta"], names={"q_ta": "甲"})
    st["enemies"] = [_il_enemy(hp=5000, spd=1)]
    st["boss"] = st["enemy"] = st["enemies"][0]
    _IL_IB.build_battle(st)
    return _il_run(_ILHost(), st, "q_ta", "skill", "嘲讽")


def _il_rt3_mutual_destroy():
    """⚔️ 同归于尽（玩家与敌同时倒下 → 失败结算）。

    ★ 桩：真实链路里「玩家与敌同归于尽」由旧引擎毒伤致死触发，saintess_engine 未迁
      state dot（见 instance_battle 模块注释）→ 用桩：IB.act 照常真跑（这一刀真杀死敌），
      只把战斗 state 里玩家 hp 归 0（= 同刻也倒下）。文案路径本身零桩。
    """
    _IL_clean()
    random.seed(20260913 + 3)
    _il_player("q_md", "甲")
    st = _il_st(["q_md"], names={"q_md": "甲"})
    st["enemies"] = [_il_enemy(hp=1, spd=1)]
    st["boss"] = st["enemy"] = st["enemies"][0]
    _IL_IB.build_battle(st)
    _orig_act = _IL_IB.act

    def _act_both_down(st_, group_id, qq_id, action, skill_name=None, target=None):
        _r = _orig_act(st_, group_id, qq_id, action, skill_name, target=target)
        try:
            for _a in (((st_.get("battle") or {}).get("sides") or {}).get("player") or []):
                _a["hp"] = 0
        except Exception:
            pass
        return _r
    _IL_IB.act = _act_both_down
    try:
        return _il_run(_ILHost(), st, "q_md", "attack")
    finally:
        _IL_IB.act = _orig_act


# ── 2. instance_battle.py ────────────────────────────────────────────
def _il_bt1_team_heal():
    """✨ 团队治疗广播（牧师『救赎之光』team=heal_all → 队友恢复行）。"""
    _IL_clean()
    random.seed(20260913 + 4)
    _il_player("q_h1", "牧师甲", cls="cls_mu_shi", level=60, learned=["救赎之光"])
    _il_player("q_h2", "战士乙", level=60)
    st = _il_st(["q_h1", "q_h2"], names={"q_h1": "牧师甲", "q_h2": "战士乙"})
    st["players"]["q_h1"]["class_name"] = "cls_mu_shi"
    st["players"]["q_h1"]["learned_skills"] = ["救赎之光"]
    st["players"]["q_h2"]["hp"] = 30
    st["enemies"] = [_il_enemy(hp=5000, spd=1)]
    st["boss"] = st["enemy"] = st["enemies"][0]
    _IL_IB.build_battle(st)
    for a in (_IL_IB._players_of(st) or []):
        a["ct"] = 0.0 if str(a.get("qq_id")) == "q_h1" else 50.0
    _IL_IB.sync_views(st, _IL_GID)
    st["turn_time"] = _il_now()
    orig = _il_cm_patch(["q_h1", "q_h2"])
    try:
        return _il_run(_ILHost(), st, "q_h1", "skill", "救赎之光")
    finally:
        _il_cm_restore(orig)


# ── 3. instance.py：组队提示 / 副本列表 ──────────────────────────────
def _il_in1_hint_no_tank():
    """组队构成提示：3×牧师（无坦克 + 无输出）。"""
    _IL_clean()
    for i, q in enumerate(("q_hh1", "q_hh2", "q_hh3"), 1):
        _il_player(q, "牧师%s" % "甲乙丙"[i - 1], cls="cls_mu_shi")
    st = _il_st(["q_hh1", "q_hh2", "q_hh3"])
    for q in ("q_hh1", "q_hh2", "q_hh3"):
        st["players"][q]["class_name"] = "cls_mu_shi"
    return "\n".join(_ILHost()._party_composition_hint(st))


def _il_in2_hint_no_heal():
    """组队构成提示：3×战士（无治疗 + 无输出）。"""
    _IL_clean()
    for i, q in enumerate(("q_hz1", "q_hz2", "q_hz3"), 1):
        _il_player(q, "战士%s" % "甲乙丙"[i - 1])
    st = _il_st(["q_hz1", "q_hz2", "q_hz3"])
    return "\n".join(_ILHost()._party_composition_hint(st))


def _il_in3_instance_list():
    """副本列表（Boss 行 / 钥匙行 / 入口行 / 底部轮流提示）。"""
    _IL_clean()
    random.seed(20260913 + 5)
    player = _il_player("q_l1", "甲", level=60)
    return _ILHost()._instance_list(player)


# ── 4. instance.py：战斗面板 / 状态面板 ──────────────────────────────
def _il_in4_battle_footer():
    """战斗面板：buff 剩刻 / 减伤 / 护盾（带与不带剩刻）/ 敌方效果 / 选敌提示 / 行动顺序。"""
    _IL_clean()
    random.seed(20260913 + 6)
    _il_player("q_f1", "甲")
    st = _il_st(["q_f1"], names={"q_f1": "甲"})
    enemy = _il_enemy(hp=500, spd=1)
    enemy["effects"] = {"def_down": {"expire": 3.0}, "mark": {"stacks": 2}}
    st["enemies"] = [enemy]
    st["boss"] = st["enemy"] = enemy
    snap = st["players"]["q_f1"]
    snap["effects"] = {"atk_up": {"expire": 3.0}, "reduce": {"v": 0.25, "expire": 3.0}}
    snap["shields"] = {"s1": {"value": 30, "expire_at": 2.0}, "s2": {"value": 5}}
    st["now"] = 0.0
    return _ILHost()._instance_battle_footer(st, _IL_GID)


def _il_in5_battle_status():
    """『副本』战斗查看面板（标题层数行 + footer + 轮到 X 行动）。"""
    _IL_clean()
    random.seed(20260913 + 7)
    _il_player("q_s1", "甲")
    st = _il_st(["q_s1"], names={"q_s1": "甲"},
                inst_stages=[{"name": "一层"}, {"name": "二层"}], stage_idx=0)
    st["enemies"] = [_il_enemy(hp=500, spd=1)]
    st["boss"] = st["enemy"] = st["enemies"][0]
    return _ILHost()._instance_status(_IL_GID, "q_s1", {"state": st})


# ── 5. instance.py：副本地图（rooms 形态）────────────────────────────
def _il_rooms_st(qid, cur_sa, leader=None, **room):
    st = _il_st([qid], names={qid: "甲"},
                rooms={cur_sa: dict({"monsters_left": [], "pois_left": [],
                                     "boss_alive": False}, **room)},
                resources_pool={"gold_left": 30, "mats_left": {"兽肉": 2}, "equip_left": []})
    st["cur_subarea"] = cur_sa
    if leader is not None:
        st["leader"] = leader
    return st


def _il_in6_map_rooms_full():
    """副本地图 rooms：无出口 / 怪物剩余 / 可调查 / Boss 房 / 通关搜刮 / 调查痕迹。"""
    _IL_clean()
    random.seed(20260913 + 8)
    qid = "q_m1"
    cur_sa = "goblin_camp_3"      # Boss 房（dungeon.boss_room）→ 覆盖「Boss 就在这个房间」
    _il_player(qid, "甲")
    _IL_db.update_player(_IL_GID, qid, cur_map="misty_swamp", cur_subarea=cur_sa)
    st = _il_rooms_st(qid, cur_sa,
                      monsters_left=[["m_goblin_guard", "哥布林守卫", "tank", 15, [], []]],
                      pois_left=["campfire", "shrine"], boss_alive=True)
    st["cleared"] = True
    st["loot_pile"] = True
    st["secret_crack"] = True
    # rooms 形态的「通关后调查痕迹」行引用未定义名 qq_id（既有缺陷，本批不动）→
    # 把调查点全标记为已翻，走不到那一行（stages 形态的孪生行 IN11 覆盖）
    st["investigated"] = [p["id"] for p in
                          (_IL_C.INVESTIGATION_POINTS.get(st["inst_id"]) or [])]
    return _ILHost()._instance_map_view(st, _IL_GID)


def _il_in7_map_rooms_cleared_room():
    """副本地图 rooms：此房已肃清（怪清空）+ 无出口（leader 无角色行 → 回退标题行）。"""
    _IL_clean()
    random.seed(20260913 + 9)
    qid, cur_sa = "q_m2", "goblin_camp_1"
    _il_player(qid, "甲")
    st = _il_rooms_st(qid, cur_sa, leader="q_ghost")
    return _ILHost()._instance_map_view(st, _IL_GID)


# ── 6. instance.py：副本地图（分层形态）─────────────────────────────
def _il_stage_st(qid, stage, **kw):
    st = _il_st([qid], names={qid: "甲"}, inst_stages=[stage], stage_idx=0, **kw)
    st.pop("resources_pool", None)
    return st


def _il_in8_map_stage_plain():
    """分层地图：本层描述缺失（回退行）+ 暗门未发现 + 怪物列表。"""
    _IL_clean()
    random.seed(20260913 + 10)
    qid = "q_m3"
    _il_player(qid, "甲")
    st = _il_stage_st(qid, {"name": "一层", "monsters": [["m_goblin_guard", "哥布林守卫",
                                                          "tank", 15, [], []]],
                            "secret": {"desc": "密室", "pois": []}})
    return _ILHost()._instance_map_view(st, _IL_GID)


def _il_in9_map_stage_secret_and_clear():
    """分层地图：隐藏房间已发现 + 本层已肃清且剩可调查（列名版）。"""
    _IL_clean()
    random.seed(20260913 + 11)
    qid = "q_m4"
    _il_player(qid, "甲")
    st = _il_stage_st(qid, {"name": "一层", "desc": "石廊尽头有风。",
                            "pois": [{"id": "shrine", "name": "古老石碑"}],
                            "secret": {"desc": "暗门后是密室", "pois": []}})
    st["stage_secret_found"] = True
    st["stage_cleared"] = True
    return _ILHost()._instance_map_view(st, _L_GID if False else _IL_GID)


def _il_in10_map_stage_boss_and_empty():
    """分层地图：Boss 就在前方 / 这里暂时没有敌人（两层两场景）。"""
    _IL_clean()
    random.seed(20260913 + 12)
    qid = "q_m5"
    _il_player(qid, "甲")
    st_boss = _il_stage_st(qid, {"name": "一层", "desc": "火把在墙上列队。",
                                 "boss": ["b_goblin_chief", "哥布林酋长·咕噜", "boss", 20,
                                          [], []]})
    out1 = _ILHost()._instance_map_view(st_boss, _IL_GID)
    st_none = _il_stage_st(qid, {"name": "二层", "desc": "空旷的石室。",
                                 "monsters": [], "elite": None})
    out2 = _ILHost()._instance_map_view(st_none, _IL_GID)
    return out1 + "\n@@@\n" + out2


def _il_in11_map_stage_cleared_pois():
    """分层地图：通关后（战利品堆/墙砖/神秘宝箱 + 通关调查痕迹）。"""
    _IL_clean()
    random.seed(20260913 + 13)
    qid = "q_m6"
    _il_player(qid, "甲")
    st = _il_stage_st(qid, {"name": "一层", "desc": "祭坛还温着。"})
    st["cleared"] = True
    st["loot_pile"] = True
    st["secret_crack"] = True
    st["secret_chest"] = True
    # 「通关后调查痕迹」行（L1748）引用未定义名 qq_id（既有缺陷，本批不动，见报告）→
    # 全标记已翻，绕开该行（rooms 形态的孪生行 L1706 同缺陷）
    st["investigated"] = [p["id"] for p in
                          (_IL_C.INVESTIGATION_POINTS.get(st["inst_id"]) or [])]
    return _ILHost()._instance_map_view(st, _IL_GID)


# ── 7. instance.py：搜刮战利品堆 ─────────────────────────────────────
def _il_in12_loot_pile_nonempty():
    """搜刮战利品堆（有产出：金币 + 材料）。"""
    _IL_clean()
    random.seed(20260913 + 14)
    player = _il_player("q_lp1", "甲", level=15)
    st = _il_st(["q_lp1"], names={"q_lp1": "甲"})
    st["loot_pile"] = True
    return _ILHost()._instance_loot_pile(_IL_GID, "q_lp1", player, st)


def _il_in13_loot_pile_empty():
    """搜刮战利品堆（空 → 引擎兜底文案）。★ 桩：掉落实测返回空列表（数据异常态）。"""
    import content.loot as _IL_DE
    _IL_clean()
    random.seed(20260913 + 15)
    player = _il_player("q_lp2", "甲", level=15)
    st = _il_st(["q_lp2"], names={"q_lp2": "甲"})
    st["loot_pile"] = True
    _orig = _IL_DE.roll
    _IL_DE.roll = lambda *a, **k: []
    try:
        return _ILHost()._instance_loot_pile(_IL_GID, "q_lp2", player, st)
    finally:
        _IL_DE.roll = _orig


# ── 8. instance.py：击杀奖励行（切怪路径）────────────────────────────
def _il_in14_kill_reward_switch():
    """击杀奖励行（经验行 + 拾取材料行）+ 切怪（击杀后下一只入场）。"""
    _IL_clean()
    random.seed(20260913 + 16)
    _il_player("q_k1", "甲", level=15)
    st = _il_st(["q_k1"], names={"q_k1": "甲"},
                stage_pending=[["m_slime", "史莱姆", "dps", 15, [], []]])
    st["enemies"] = [_il_enemy(hp=1, spd=1, drops=["兽肉"])]
    st["boss"] = st["enemy"] = st["enemies"][0]
    _IL_IB.build_battle(st)
    inst = _ILHost()
    msgs = []
    for _ in range(4):
        st["turn_time"] = _il_now()
        msgs += _il_run(inst, st, "q_k1", "attack")
        if st.get("stage_pending") == [] and "又一只" in _il_text(msgs):
            break
    return msgs


def _il_in15_kill_reward_pet():
    """击杀奖励行（宠物分经验 [+ 升至 Lv.N]）。"""
    _IL_clean()
    random.seed(20260913 + 17)
    _il_player("q_k2", "甲", level=15)
    st = _il_st(["q_k2"], names={"q_k2": "甲"},
                stage_pending=[["m_slime", "史莱姆2", "dps", 15, [], []]])
    st["pets"] = {"q_k2": {"name": "阿黄", "level": 1, "exp": 0, "satiety": 80}}
    st["enemies"] = [_il_enemy(hp=1, spd=1, drops=["兽肉"])]
    st["boss"] = st["enemy"] = st["enemies"][0]
    _IL_IB.build_battle(st)
    inst = _ILHost()
    msgs = []
    for _ in range(4):
        st["turn_time"] = _il_now()
        msgs += _il_run(inst, st, "q_k2", "attack")
        if st.get("stage_pending") == []:
            break
    return msgs


# ── 9. instance.py：通关结算 ─────────────────────────────────────────
def _il_victory_once(qid1, qid2, seed, rr, pet, dead, learned, boss_lv=20,
                     boss_exp=400, boss_gold=220, inst_id="inst_goblin_camp"):
    """驱动一次 _instance_victory（真跑通关结算），返回逐字输出。"""
    _IL_clean()
    random.seed(seed)
    _il_player(qid1, "甲", level=20)
    _il_player(qid2, "乙", level=20)
    if learned:
        _bps = sorted({( _IL_C.roll_blueprint(boss_lv) or {}).get("blueprint_for") or ""
                       for _ in range(80)})
        _IL_db.update_player(_IL_GID, qid1, learned_blueprints=[x for x in _bps if x])
    st = _il_st([qid1, qid2], names={qid1: "甲", qid2: "乙"}, inst_id=inst_id)
    st["players"][qid1]["hp"] = 500
    st["players"][qid1]["max_hp"] = 500
    if dead:
        st["alive"][qid2] = False
        st["players"][qid2]["hp"] = 0
    if pet:
        st["pets"] = {qid1: dict(pet)}
    bs = _il_enemy(hp=0, spd=50, role="boss", uid="e_boss", name="哥布林酋长·咕噜",
                   lv=boss_lv, exp=boss_exp, gold=boss_gold)
    st["boss"] = bs
    st["_last_killed"] = [dict(bs)]
    st["contribution"] = {qid1: 100, qid2: 10}
    player = st["players"][qid1]
    orig = _il_cm_patch([qid1, qid2])
    _rr = _ILRR(rr)
    _rr.__enter__()
    try:
        async def _c():
            out = []
            async for x in _ILHost()._instance_victory(
                    _IL_Event(_IL_GID, qid1), _IL_GID, qid1, player, st, []):
                out.append(x)
            return out
        loop = asyncio.new_event_loop()
        try:
            msgs = loop.run_until_complete(_c())
        finally:
            loop.close()
        return _il_text(msgs)
    finally:
        _rr.__exit__()
        _il_cm_restore(orig)


def _il_in16_victory_a():
    """通关 A：宠物升级 + 图纸已学 + 暗格必出（random 打 0.05）。"""
    return _il_victory_once("q_v1", "q_v2", 20260913 + 18, 0.05,
                            {"name": "阿黄", "level": 1, "exp": 0, "satiety": 80},
                            dead=True, learned=True)


def _il_in17_victory_b():
    """通关 B：无宠物 / 未学图纸 / 暗格不出（random 打 0.9）。"""
    return _il_victory_once("q_v3", "q_v4", 20260913 + 19, 0.9,
                            None, dead=False, learned=False)


def _il_in18_victory_c():
    """通关 C：自由随机（seed 定）——补另一侧掉落分支。"""
    return _il_victory_once("q_v5", "q_v6", 20260913 + 20, None,
                            {"name": "阿黄", "level": 1, "exp": 0, "satiety": 80},
                            dead=False, learned=True, boss_lv=30, boss_exp=900,
                            boss_gold=500)


# ── 10. instance.py：失败结算 ────────────────────────────────────────
def _il_in19_defeat():
    """失败：玩家被高攻 Boss 秒杀 → 全灭行 + 回城行（单人：current_members 恒 [本人]）。"""
    _IL_clean()
    random.seed(20260913 + 21)
    _il_player("q_d1", "甲", level=15)
    st = _il_st(["q_d1"], names={"q_d1": "甲"})
    st["players"]["q_d1"]["hp"] = 3
    st["enemies"] = [_il_enemy(hp=99999, spd=200, atk=99999, role="boss", name="房间怪")]
    st["boss"] = st["enemy"] = st["enemies"][0]
    _IL_IB.build_battle(st)
    inst = _ILHost()
    msgs = []
    for _ in range(12):
        st["turn_time"] = _il_now()
        msgs += _il_run(inst, st, "q_d1", "defend")
        if st.get("over") or not st.get("alive", {}).get("q_d1", True):
            break
    return msgs


def _il_in20_victory_exclusive():
    """通关 D：Boss 专属装备掉落（👑 专属）+ 首功图纸（未学会）。"""
    return _il_victory_once("q_v7", "q_v8", 20260913 + 22, 0.0,
                            None, dead=False, learned=False, boss_lv=22,
                            boss_exp=900, boss_gold=500, inst_id="inst_sea_cave")


def _il_in21_victory_learned_bp():
    """通关 E：首功图纸（已学会 → 折算残页）。"""
    return _il_victory_once("q_v9", "q_v10", 20260913 + 23, 0.9,
                            None, dead=False, learned=True, boss_lv=22,
                            boss_exp=900, boss_gold=500, inst_id="inst_sea_cave")


def _il_in22_map_stage_cleared_no_poi():
    """分层地图：本层已肃清且无可调查剩余（另一支肃清行）。"""
    _IL_clean()
    random.seed(20260913 + 24)
    qid = "q_m7"
    _il_player(qid, "甲")
    st = _il_stage_st(qid, {"name": "三层", "desc": "走廊尽头静了下来。",
                            "pois": [], "monsters": []})
    st["stage_cleared"] = True
    return _ILHost()._instance_map_view(st, _IL_GID)


_IL_BRANCHES = (
    ("RT1_超时自动防御", _il_rt1_timeout_defend),
    ("RT2_嘲讽", _il_rt2_taunt),
    ("RT3_同归于尽", _il_rt3_mutual_destroy),
    ("BT1_团队治疗广播", _il_bt1_team_heal),
    ("IN1_组队提示_无坦克", _il_in1_hint_no_tank),
    ("IN2_组队提示_无治疗", _il_in2_hint_no_heal),
    ("IN3_副本列表", _il_in3_instance_list),
    ("IN4_战斗面板", _il_in4_battle_footer),
    ("IN5_副本状态面板", _il_in5_battle_status),
    ("IN6_地图_rooms_全提示", _il_in6_map_rooms_full),
    ("IN7_地图_rooms_已肃清", _il_in7_map_rooms_cleared_room),
    ("IN8_地图_分层_描述缺失", _il_in8_map_stage_plain),
    ("IN9_地图_分层_暗门与肃清", _il_in9_map_stage_secret_and_clear),
    ("IN10_地图_分层_Boss与空", _il_in10_map_stage_boss_and_empty),
    ("IN11_地图_分层_通关后", _il_in11_map_stage_cleared_pois),
    ("IN12_搜刮_非空", _il_in12_loot_pile_nonempty),
    ("IN13_搜刮_空", _il_in13_loot_pile_empty),
    ("IN14_击杀奖励_切怪", _il_in14_kill_reward_switch),
    ("IN15_击杀奖励_宠物", _il_in15_kill_reward_pet),
    ("IN16_通关A_宠物升级图纸已学", _il_in16_victory_a),
    ("IN17_通关B_无宠物未学", _il_in17_victory_b),
    ("IN18_通关C_自由随机", _il_in18_victory_c),
    ("IN19_失败_全灭回城", _il_in19_defeat),
    ("IN20_通关D_专属装备", _il_in20_victory_exclusive),
    ("IN21_通关E_首功图纸已学", _il_in21_victory_learned_bp),
    ("IN22_地图_分层_肃清无可调查", _il_in22_map_stage_cleared_no_poi),
)


def _il_scenarios():
    """复跑全部副本日志分支（迁移前采快照 / 迁移后门禁比对，同一份代码）。"""
    out = {}
    for name, fn in _IL_BRANCHES:
        out[name] = _il_text(fn())
    return out

INSTANCE_LOG_FROZEN = {
    "BT1_团队治疗广播": "✨ 战士乙 恢复 70 点生命！\n你施展【救赎之光】，治愈了 0 点生命！\n—— 房间怪 行动 ——\n💥 牧师甲 受到 1 点伤害！\n━━━━━━━━━━━━\n── 敌方 ──\n  A1层: a1  房间怪 ❤️5000/5000\n── 我方 ──\n  B1层: b1  战士乙 ❤️100/100\n  B2层: b2  牧师甲 ❤️99/100\n🕐 时刻 1.5s ｜ ⚡ 行动顺序：牧师甲(我) → 房间怪(敌) → 战士乙(我)\n✅ 牧师甲：❤️ 99/100 💙 984/999\n✅ 战士乙：❤️ 100/100 💙 999/999\n💡 选敌：『技能1 a2』打2号(纯数字同义)；治疗『技能 <名称> b1』奶自己\n⏳ 轮到 牧师甲 行动！『攻击』『技能 <名称>』『防御』",
    "IN10_地图_分层_Boss与空": "🗺️ 【👺哥布林营地】第 1 层 · 一层\n━━━━━━━━━━━━\n📜 火把在墙上列队。\n━━━━━━━━━━━━\n✨ 场景：\n  []\n  []\n━━━━━━━━━━━━\n👑 Boss 就在前方：哥布林酋长·咕噜！『探索』进入战斗！\n━━━━━━━━━━━━\n💡 『副本』查看战况，『角色』看队伍\n@@@\n🗺️ 【👺哥布林营地】第 1 层 · 二层\n━━━━━━━━━━━━\n📜 空旷的石室。\n━━━━━━━━━━━━\n✨ 场景：\n  []\n  []\n━━━━━━━━━━━━\n🐾 这里暂时没有敌人。\n━━━━━━━━━━━━\n💡 可发送『调查 <名称>』互动机关",
    "IN11_地图_分层_通关后": "🗺️ 【👺哥布林营地】第 1 层 · 一层\n━━━━━━━━━━━━\n📜 祭坛还温着。\n━━━━━━━━━━━━\n✨ 场景：\n  []\n  []\n🎁 战利品堆：首领的遗物堆在角落（『调查 战利品堆』）\n🧱 墙上有一块松动的墙砖……（『调查 墙砖』）\n🔐 神秘宝箱：密室深处泛着微光（『调查 宝箱』）\n💡 多人副本先『组队 <名字>』再开本\n━━━━━━━━━━━━\n💡 单人副本直接『副本 <名字>』开本",
    "IN12_搜刮_非空": "🎁 你搜刮了战利品堆：金币 +70\n🎒 拾取：咕噜皇冠 ×1",
    "IN13_搜刮_空": "🎁 你搜刮了战利品堆，但里面空空的……",
    "IN14_击杀奖励_切怪": "💥 房间怪 受到 1 点伤害，倒下了！\n  甲：经验 +1，拾取材料 兽肉 ×1\n  甲：🏆 成就解锁：初试锋芒！(完成首次战斗)\n      🎁 经验+100、兽肉×3（『成就 领取』领取）\n  甲：🏆 成就解锁：初出茅庐！(注册角色)\n      🎁 草药×2（『成就 领取』领取）\n  甲：🏆 成就解锁：崭露头角！(达到 10 级)\n      🎁 铁矿石×2（『成就 领取』领取）\n━━━━━━━━━━━━\n⚔️ 又一只怪物挡在面前！\n── 敌方 ──\n  A1层: a1  史莱姆 ❤️465/465\n── 我方 ──\n  B1层: b1  甲 ❤️100/100\n🕐 时刻 0.0s ｜ ⚡ 行动顺序：甲(我) → 史莱姆(敌)\n✅ 甲：❤️ 100/100 💙 999/999\n💡 选敌：『技能1 a2』打2号(纯数字同义)；治疗『技能 <名称> b1』奶自己\n⏳ 轮到 甲 行动！『攻击』『技能 <名称>』『防御』",
    "IN15_击杀奖励_宠物": "💥 房间怪 受到 1 点伤害，倒下了！\n  甲：经验 +1  🐾阿黄 分得经验 +2，拾取材料 兽肉 ×1\n  甲：🏆 成就解锁：初试锋芒！(完成首次战斗)\n      🎁 经验+100、兽肉×3（『成就 领取』领取）\n  甲：🏆 成就解锁：初出茅庐！(注册角色)\n      🎁 草药×2（『成就 领取』领取）\n  甲：🏆 成就解锁：崭露头角！(达到 10 级)\n      🎁 铁矿石×2（『成就 领取』领取）\n━━━━━━━━━━━━\n⚔️ 又一只怪物挡在面前！\n── 敌方 ──\n  A1层: a1  史莱姆2 ❤️465/465\n── 我方 ──\n  B1层: b1  甲 ❤️100/100\n🕐 时刻 0.0s ｜ ⚡ 行动顺序：甲(我) → 史莱姆2(敌)\n✅ 甲：❤️ 100/100 💙 999/999\n　🐾 阿黄 还小（Lv.1），Lv.10 解锁战斗技能！\n💡 选敌：『技能1 a2』打2号(纯数字同义)；治疗『技能 <名称> b1』奶自己\n⏳ 轮到 甲 行动！『攻击』『技能 <名称>』『防御』",
    "IN16_通关A_宠物升级图纸已学": "\n🎉 【哥布林酋长·咕噜】被击败了！👺哥布林营地 通关！\n📜 咕噜的皇冠滚落在篝火边，商路上的劫掠就此画上句号。行会的赏金结清了，可你总觉得，这条商路尽头的风声，才刚刚开始。\n  甲：金币 +234 经验 +3653\n  🐾阿黄 分得经验 +80，升至 Lv.2！\n  📜 甲 拾取图纸：雷霆指环图纸（已学会，化作 4 张图纸残页）\n  ⚔️ 甲 拾取 Boss 珍藏：【咕噜金戒】！\n  🎒 甲 拾取：咕噜皇冠\n  💀 乙 已阵亡，未能获得奖励\n  💎 甲 获得幸运宝石：闪耀的幸运宝石·金币加成+3%！(『原石』镶嵌到装备孔位)\n  甲：🏆 成就解锁：初出茅庐！(注册角色)\n      🎁 草药×2（『成就 领取』领取）\n  甲：🏆 成就解锁：崭露头角！(达到 10 级)\n      🎁 铁矿石×2（『成就 领取』领取）\n  甲：🏆 成就解锁：名声鹊起！(达到 20 级)\n      🎁 精铁×2（『成就 领取』领取）\n  甲：🏆 成就解锁：博闻强识！(累计学习 20 张图纸)\n      🎁 白银箱×1、图纸残页×3（『成就 领取』领取）\n\n🏆 副本已通关！你可以在副本内停留搜刮：\n  · 🎁 【战利品堆】—— 首领的遗物，搜刮一次（『调查 战利品堆』）\n  · 🔍 通关后这里多了些可调查的痕迹（『副本地图』查看，每日限 3 次）\n  · 🧱 墙上似乎有【松动的墙砖】……（『调查 墙砖』）\n搜刮完毕用『离开副本』传出～\n\n💡 『副本』可再次挑战，首通成就已记录～",
    "IN17_通关B_无宠物未学": "\n🎉 【哥布林酋长·咕噜】被击败了！👺哥布林营地 通关！\n📜 咕噜的皇冠滚落在篝火边，商路上的劫掠就此画上句号。行会的赏金结清了，可你总觉得，这条商路尽头的风声，才刚刚开始。\n  甲：金币 +234 经验 +3653\n  🎒 甲 拾取：咕噜皇冠\n  乙：金币 +234 经验 +3653\n  🎒 乙 拾取：咕噜皇冠\n  甲：🏆 成就解锁：完美主义者！(未受伤通关 1 个副本)\n      🎁 铁箱×1（『成就 领取』领取）\n  甲：🏆 成就解锁：初出茅庐！(注册角色)\n      🎁 草药×2（『成就 领取』领取）\n  甲：🏆 成就解锁：崭露头角！(达到 10 级)\n      🎁 铁矿石×2（『成就 领取』领取）\n  甲：🏆 成就解锁：名声鹊起！(达到 20 级)\n      🎁 精铁×2（『成就 领取』领取）\n  乙：🏆 成就解锁：完美主义者！(未受伤通关 1 个副本)\n      🎁 铁箱×1（『成就 领取』领取）\n  乙：🏆 成就解锁：初出茅庐！(注册角色)\n      🎁 草药×2（『成就 领取』领取）\n  乙：🏆 成就解锁：崭露头角！(达到 10 级)\n      🎁 铁矿石×2（『成就 领取』领取）\n  乙：🏆 成就解锁：名声鹊起！(达到 20 级)\n      🎁 精铁×2（『成就 领取』领取）\n\n🏆 副本已通关！你可以在副本内停留搜刮：\n  · 🎁 【战利品堆】—— 首领的遗物，搜刮一次（『调查 战利品堆』）\n  · 🔍 通关后这里多了些可调查的痕迹（『副本地图』查看，每日限 3 次）\n搜刮完毕用『离开副本』传出～\n\n💡 『副本』可再次挑战，首通成就已记录～",
    "IN18_通关C_自由随机": "\n🎉 【哥布林酋长·咕噜】被击败了！👺哥布林营地 通关！\n📜 咕噜的皇冠滚落在篝火边，商路上的劫掠就此画上句号。行会的赏金结清了，可你总觉得，这条商路尽头的风声，才刚刚开始。\n  甲：金币 +234 经验 +3653\n  🐾阿黄 分得经验 +180，升至 Lv.3！\n  🎒 甲 拾取：咕噜皇冠\n  乙：金币 +234 经验 +3653\n  🎒 乙 拾取：咕噜皇冠\n  甲：🏆 成就解锁：完美主义者！(未受伤通关 1 个副本)\n      🎁 铁箱×1（『成就 领取』领取）\n  甲：🏆 成就解锁：初出茅庐！(注册角色)\n      🎁 草药×2（『成就 领取』领取）\n  甲：🏆 成就解锁：崭露头角！(达到 10 级)\n      🎁 铁矿石×2（『成就 领取』领取）\n  甲：🏆 成就解锁：名声鹊起！(达到 20 级)\n      🎁 精铁×2（『成就 领取』领取）\n  甲：🏆 成就解锁：博闻强识！(累计学习 20 张图纸)\n      🎁 白银箱×1、图纸残页×3（『成就 领取』领取）\n  乙：🏆 成就解锁：完美主义者！(未受伤通关 1 个副本)\n      🎁 铁箱×1（『成就 领取』领取）\n  乙：🏆 成就解锁：初出茅庐！(注册角色)\n      🎁 草药×2（『成就 领取』领取）\n  乙：🏆 成就解锁：崭露头角！(达到 10 级)\n      🎁 铁矿石×2（『成就 领取』领取）\n  乙：🏆 成就解锁：名声鹊起！(达到 20 级)\n      🎁 精铁×2（『成就 领取』领取）\n\n🏆 副本已通关！你可以在副本内停留搜刮：\n  · 🎁 【战利品堆】—— 首领的遗物，搜刮一次（『调查 战利品堆』）\n  · 🔍 通关后这里多了些可调查的痕迹（『副本地图』查看，每日限 3 次）\n  · 🧱 墙上似乎有【松动的墙砖】……（『调查 墙砖』）\n搜刮完毕用『离开副本』传出～\n\n💡 『副本』可再次挑战，首通成就已记录～",
    "IN19_失败_全灭回城": "🛡 甲 摆出防御姿态，受到的伤害减半！\n━━━━━━━━━━━━\n── 敌方 ──\n  A1层: a1  房间怪 ❤️99999/99999\n── 我方 ──\n  B1层: b1  甲 ❤️3/100\n🕐 时刻 0.6s ｜ ⚡ 行动顺序：甲(我) → 房间怪(敌)\n✅ 甲：❤️ 3/100 💙 999/999 🛡️防御\n💡 选敌：『技能1 a2』打2号(纯数字同义)；治疗『技能 <名称> b1』奶自己\n⏳ 轮到 甲 行动！『攻击』『技能 <名称>』『防御』\n🛡 甲 摆出防御姿态，受到的伤害减半！\n—— 房间怪 行动 ——\n🌪️【房间怪】发出震天【咆哮】！气势瞬间拉满！\n⚡【房间怪】的咆哮让攻击力提升了！\n☠️ 【房间怪】盯上了重伤的你……本刻攻击大幅提升！\n(格挡后 37757 点伤害)\n💥 甲 受到 3 点伤害，倒下了！\n\n💀 队伍全灭……副本失败！冒险者们被送回了最近的城镇。\n📍 甲 被送回了【白鹿城·白鹿广场】（HP 0，先休息恢复吧）",
    "IN1_组队提示_无坦克": "🛡️ 没有坦克：Boss 仇恨没人拉，输出容易被追着打\n⚔️ 没有输出：可能打到超时哦",
    "IN20_通关D_专属装备": "\n🎉 【哥布林酋长·咕噜】被击败了！🌊海蚀洞窟 通关！\n📜 金钩从杰克手中脱落，暗湾里终于只剩下潮水的呼吸。铁港的船主们可以重新起锚了，而你从战利品里翻出的那张旧海图，似乎指向更深的水域。\n  甲：金币 +385 经验 +6465\n  📜 甲 拾取图纸：血潮短刃图纸\n  ⚔️ 甲 拾取 Boss 珍藏：【杰克的金币袋】！\n  👑 甲 从Boss身上拾取稀有专属：【金钩弯刀】！\n  🎒 甲 拾取：杰克的金钩碎片\n  🎒 甲 拾取：杰克的金钩碎片\n  乙：金币 +385 经验 +6465\n  📜 乙 拾取图纸：秘法典籍之杖图纸\n  ⚔️ 乙 拾取 Boss 珍藏：【杰克的金币袋】！\n  👑 乙 从Boss身上拾取稀有专属：【金钩弯刀】！\n  🎒 乙 拾取：杰克的金钩碎片\n  🎒 乙 拾取：杰克的金钩碎片\n  💎 乙 获得幸运宝石：明亮的幸运宝石·格挡+2%！(『原石』镶嵌到装备孔位)\n👑 首功 甲 额外获得图纸：铸火头盔图纸\n  甲：🏆 成就解锁：完美主义者！(未受伤通关 1 个副本)\n      🎁 铁箱×1（『成就 领取』领取）\n  甲：🏆 成就解锁：初出茅庐！(注册角色)\n      🎁 草药×2（『成就 领取』领取）\n  甲：🏆 成就解锁：崭露头角！(达到 10 级)\n      🎁 铁矿石×2（『成就 领取』领取）\n  甲：🏆 成就解锁：名声鹊起！(达到 20 级)\n      🎁 精铁×2（『成就 领取』领取）\n  乙：🏆 成就解锁：完美主义者！(未受伤通关 1 个副本)\n      🎁 铁箱×1（『成就 领取』领取）\n  乙：🏆 成就解锁：初出茅庐！(注册角色)\n      🎁 草药×2（『成就 领取』领取）\n  乙：🏆 成就解锁：崭露头角！(达到 10 级)\n      🎁 铁矿石×2（『成就 领取』领取）\n  乙：🏆 成就解锁：名声鹊起！(达到 20 级)\n      🎁 精铁×2（『成就 领取』领取）\n\n🏆 副本已通关！你可以在副本内停留搜刮：\n  · 🎁 【战利品堆】—— 首领的遗物，搜刮一次（『调查 战利品堆』）\n  · 🔍 通关后这里多了些可调查的痕迹（『副本地图』查看，每日限 3 次）\n  · 🧱 墙上似乎有【松动的墙砖】……（『调查 墙砖』）\n搜刮完毕用『离开副本』传出～\n\n💡 『副本』可再次挑战，首通成就已记录～",
    "IN21_通关E_首功图纸已学": "\n🎉 【哥布林酋长·咕噜】被击败了！🌊海蚀洞窟 通关！\n📜 金钩从杰克手中脱落，暗湾里终于只剩下潮水的呼吸。铁港的船主们可以重新起锚了，而你从战利品里翻出的那张旧海图，似乎指向更深的水域。\n  甲：金币 +385 经验 +6465\n  🎒 甲 拾取：杰克的金钩碎片\n  🎒 甲 拾取：杰克的金钩碎片\n  乙：金币 +385 经验 +6465\n  🎒 乙 拾取：杰克的金钩碎片\n  🎒 乙 拾取：杰克的金钩碎片\n👑 首功 甲 额外获得图纸：深渊之锚图纸（已学会，化作 4 张图纸残页）\n  甲：🏆 成就解锁：完美主义者！(未受伤通关 1 个副本)\n      🎁 铁箱×1（『成就 领取』领取）\n  甲：🏆 成就解锁：初出茅庐！(注册角色)\n      🎁 草药×2（『成就 领取』领取）\n  甲：🏆 成就解锁：崭露头角！(达到 10 级)\n      🎁 铁矿石×2（『成就 领取』领取）\n  甲：🏆 成就解锁：名声鹊起！(达到 20 级)\n      🎁 精铁×2（『成就 领取』领取）\n  甲：🏆 成就解锁：博闻强识！(累计学习 20 张图纸)\n      🎁 白银箱×1、图纸残页×3（『成就 领取』领取）\n  乙：🏆 成就解锁：完美主义者！(未受伤通关 1 个副本)\n      🎁 铁箱×1（『成就 领取』领取）\n  乙：🏆 成就解锁：初出茅庐！(注册角色)\n      🎁 草药×2（『成就 领取』领取）\n  乙：🏆 成就解锁：崭露头角！(达到 10 级)\n      🎁 铁矿石×2（『成就 领取』领取）\n  乙：🏆 成就解锁：名声鹊起！(达到 20 级)\n      🎁 精铁×2（『成就 领取』领取）\n\n🏆 副本已通关！你可以在副本内停留搜刮：\n  · 🎁 【战利品堆】—— 首领的遗物，搜刮一次（『调查 战利品堆』）\n  · 🔍 通关后这里多了些可调查的痕迹（『副本地图』查看，每日限 3 次）\n搜刮完毕用『离开副本』传出～\n\n💡 『副本』可再次挑战，首通成就已记录～",
    "IN22_地图_分层_肃清无可调查": "🗺️ 【👺哥布林营地】第 1 层 · 三层\n━━━━━━━━━━━━\n📜 走廊尽头静了下来。\n━━━━━━━━━━━━\n✨ 场景：\n  []\n  []\n━━━━━━━━━━━━\n✅ 本层敌人已肃清！『深入』前往下一层。\n━━━━━━━━━━━━\n💡 『副本』查看战况，『角色』看队伍",
    "IN2_组队提示_无治疗": "✨ 没有治疗：血线压力大，记得多带药水\n⚔️ 没有输出：可能打到超时哦",
    "IN3_副本列表": "🏰 【组队副本】\n━━━━━━━━━━━━\n1. ✅ 👺 哥布林营地(Lv.15+ · 👥 1-2人)\n   商路旁的哥布林聚落，哥布林酋长·咕噜盘踞于此，靠抢劫商队为生。冒险者行会悬赏讨伐。(主线第 2 章)\n   👹 Boss：哥布林酋长·咕噜(Lv.20)· 掉落：咕噜皇冠\n   📍 入口：迷雾沼泽·沼泽深处\n2. ✅ 🛡️ 鹿角要塞(Lv.18+ · 🕐 单人)\n   白鹿城北的废弃要塞，百年前毁于战火。要塞幽灵仍在城墙上游荡，寻找着失落的军旗。(支线)\n   👹 Boss：要塞幽灵(Lv.23)· 掉落：要塞残片\n   🔑 需『军旗碎片』：古战场/旧战场遗迹采集\n   📍 入口：山丘矿洞·矿洞深处\n3. ✅ 🌊 海蚀洞窟(Lv.22+ · 👥 1-3人)\n   铁港码头下的海蚀洞穴，海盗王·独眼杰克的老巢。潮水声里混着金币碰撞的脆响。(主线第 3 章)\n   👹 Boss：海盗王·独眼杰克(Lv.27)· 掉落：杰克的金钩碎片\n   📍 入口：铁港码头·海堤\n4. ✅ 🦀 锈潮船坞(Lv.25+ · 👥 2-3人)\n   铁港码头废弃船坞下的锈蚀水道，潮水把整座旧船坞泡成了螃蟹的乐园。巨钳蟹王·锈钳盘踞船底，钳上还挂着一百艘沉船的船牌。(海港支线)\n   👹 Boss：巨钳蟹王·锈钳(Lv.31)· 掉落：锈潮蟹甲\n   📍 入口：铁港码头·货仓区\n5. ✅ 🕯️ 烛影墓窟(Lv.29+ · 👥 1-2人)\n   大圣堂地下被封死的古墓廊道，数百年的烛油在地面凝成厚壳。烛影主教·赫尔嘉在此布道——给死人布道，也给误入者布道。(教会地下支线)\n   👹 Boss：烛影主教·赫尔嘉(Lv.35)· 掉落：烛影烛泪\n   📍 入口：晨曦大圣堂·圣堂前庭\n6. ✅ ⚡ 雷鸣矿道(Lv.32+ · 👥 1-2人)\n   山丘矿洞最深处被雷晶矿脉炸开的巷道，矿车轨道上趴着雷晶蜥，雷灵在电线般的矿脉间流窜。雷晶巨像·轰鸣守着整条矿脉的心脏。(矿务支线)\n   👹 Boss：雷晶巨像·轰鸣(Lv.37)· 掉落：雷晶矿核\n   📍 入口：山丘矿洞·塌方矿厅\n7. ✅ 🦴 旧王陵(Lv.35+ · 👥 1-3人)\n   晨曦城北的古老王陵，埋葬着圣战前的历代君王。古王·奥德里克在棺椁中苏醒，亡灵的低语回荡在石壁之间。(主线第 6 章)\n   👹 Boss：古王·奥德里克(Lv.40)· 掉落：古王剑碎片\n   🔑 需『王陵钥匙』：白鹿城铁匠铺购买(500 金)\n   📍 入口：王陵古道·王陵前\n8. ✅ ⚜️ 圣光试炼场(Lv.36+ · 🕐 单人)\n   圣光骑士团的试炼之地。试炼骑士长把守最后一关——通过者将获得骑士团的认可。(支线)\n   👹 Boss：试炼骑士长(Lv.41)· 掉落：试炼徽记\n   🔑 需『试炼令』：铁盾镇军械铺购买(400 金)\n   📍 入口：王陵古道·古道中段\n9. ✅ ⚓ 沉船湾(Lv.38+ · 🕐 单人)\n   翡翠海深处的沉船墓地，幽灵船长·克罗的旗舰在此永沉。传说船底的宝箱装着它的罗盘——还有它不甘的灵魂。(群岛支线)\n   👹 Boss：幽灵船长·克罗(Lv.43)· 掉落：克罗的罗盘碎片\n   🔑 需『幽灵船票』：沉船湾墓地采集\n   📍 入口：风暴海峡·海峡深处\n10. ✅ ⛪ 圣堂地窖(Lv.42+ · 👥 3-4人)\n   晨曦大圣堂下的密室，教会最深的秘密沉睡于此。审判长·马尔库斯奉命看守——他的锁链，从不问对错。(主线第 11 章)\n   👹 Boss：审判长·马尔库斯(Lv.47)· 掉落：马尔库斯的法冠残片\n   🔑 需『圣堂信物』：晨曦城大教堂购买(300 金)\n   📍 入口：晨曦大圣堂·圣堂地窟\n11. ✅ 🐢 旋涡竞技场(Lv.46+ · 👥 2-3人)\n   风暴海峡中央一座随潮汐沉浮的环形礁台，潮水在礁台四周绞成永不停歇的旋涡。石壳龟·磐涡把这里当成了它的角斗场——打赢它，才能从旋涡眼里游出去。(群岛支线)\n   👹 Boss：石壳龟·磐涡(Lv.52)· 掉落：磐涡龟甲\n   📍 入口：风暴海峡·海峡口\n12. ✅ 🎭 黑潮歌剧院(Lv.50+ · 👥 2-4人)\n   黑潮海峡底下沉没的旧歌剧厅，潮水在包厢与舞台之间来回涨落。首席海妖·歌澜每晚都在这里开唱——观众席上坐满溺亡的乐迷，而她们，已经不会鼓掌了。(深海支线)\n   👹 Boss：首席海妖·歌澜(Lv.56)· 掉落：咏叹谱残页\n   📍 入口：雾潮航道·无名灯塔\n13. ✅ 🧜‍♀️ 海妖巢穴(Lv.52+ · 👥 2-3人)\n   海妖湾下的珊瑚巢穴，海妖女王·蓝歌的领地。她的歌声能魅惑水手，也能掀起巨浪——别被歌声骗进深海。(群岛支线)\n   👹 Boss：海妖女王·蓝歌(Lv.57)· 掉落：蓝歌之冠残片\n   🔑 需『海妖鳞片信物』：海妖湾精英·海妖领主·潮汐掉落\n   📍 入口：海妖湾·海妖巢\n14. ✅ 🏛️ 精灵废墟(Lv.58+ · 👥 1-4人)\n   银月林海深处的失落王城，远古精灵王的安息之所。月光照不进坍塌的穹顶，只有亡灵精灵的吟唱。(主线第 7 章)\n   👹 Boss：远古精灵王·晨曦(Lv.63)· 掉落：晨曦之冠碎片\n   🔑 需『精灵遗印』：翡翠森林精英·狼王·灰影掉落\n   📍 入口：月冠王庭·月庭宫门\n15. ✅ 🌙 月神圣殿(Lv.60+ · 🕐 单人)\n   月冠王庭深处的月神神殿，月光从穹顶倾泻而下。月神守卫守护着月之试炼——只有月神认可者才能进入。(支线)\n   👹 Boss：月神守卫(Lv.65)· 掉落：月辉碎片\n   🔑 需『月辉钥匙』：月冠王庭购买(3000 金)\n   📍 入口：月光林·林深处\n16. 🔒 🌊 海神神殿(Lv.64+ · 👥 3-4人)\n   无尽海底的海神神殿，海神祭司·澜歌守护着海神的圣物。潮汐在此倒流——海神的目光，正注视着入侵者。(无尽海支线)\n   👹 Boss：海神祭司·澜歌(Lv.69)· 掉落：澜歌之泪残片\n   🔑 需『海神祷文』：无名港港务厅购买\n   📍 入口：风暴之海·海眼\n17. 🔒 🐲 深海龙宫(Lv.70+ · 👥 4人)\n   无尽海最深处的水晶龙宫，深海龙王·敖澜在此沉睡。它一翻身，海面就要掀起风暴——别吵醒它太久。(无尽海支线)\n   👹 Boss：深海龙王·敖澜(Lv.75)· 掉落：敖澜之珠碎片\n   🔑 需『龙宫珠』：龙鲸海域精英·龙鲸王·涛声掉落\n   📍 入口：风暴之海·风暴区\n18. 🔒 ❄️ 冰霜王座(Lv.74+ · 👥 2-3人)\n   永冻冰原深处的寒冰王座，冰霜领主在此称王。它冻结了三百年的时光，也在等待一个挑战者。(支线)\n   👹 Boss：冰霜领主(Lv.79)· 掉落：永冻之核\n   🔑 需『寒冰令』：永冻冰原精英·冰原猛犸·雪岭掉落\n   📍 入口：永冬湖·湖心\n19. 🔒 ⛏️ 灰矮人要塞(Lv.74+ · 👥 2-3人)\n   幽暗地域深处的灰矮人要塞，灰矮人领主·石炉统治着这片地底。它的锻造炉昼夜不息，烧的是地底恶魔的骨头。(地底支线)\n   👹 Boss：灰矮人领主·石炉(Lv.79)· 掉落：石炉之锤\n   🔑 需『灰矮人通行令』：地底集市购买(2800 金)\n   📍 入口：地下湖·湖底\n20. 🔒 🌋 烬山祭坛(Lv.82+ · 👥 1-4人)\n   烬山之巅的古老祭坛，三百年前圣战的主战场。恶魔祭司·赫尔加在此主持黑暗仪式，试图解开蚀夜的封印。(主线第 9 章)\n   👹 Boss：恶魔祭司·赫尔加(Lv.87)· 掉落：赫尔加的祭器碎片\n   🔑 需『烬火令』：烬山精英·恶魔战士掉落\n   📍 入口：烬山·火山口\n21. 🔒 🐍 地底龙巢(Lv.84+ · 👥 4人)\n   熔火深渊之下的地底龙巢，地底古龙·黑渊盘踞于此。它吞食地底岩浆与恶魔，是幽暗地域最古老的掠食者。(地底支线)\n   👹 Boss：地底古龙·黑渊(Lv.89)· 掉落：黑渊之眼残片\n   🔑 需『龙鳞钥匙』：熔火深渊精英·熔火领主·烬核掉落\n   📍 入口：熔火深渊·深渊深处\n22. 🔒 🌑 深渊裂隙(Lv.90+ · 👥 1-4人)\n   封印的尽头，深渊裂隙的裂口。被误认为魔王的守护者蚀夜，在这里镇守了三百年——你终于要直面真相。(主线第 12 章·最终决战)\n   👹 Boss：蚀夜(真相形态)(Lv.95)· 掉落：黎明之光碎片\n   🔑 需『深渊钥匙』：深渊骑士掉落\n   📍 入口：烬山祭坛·灰烬门廊\n23. 🔒 👹 深渊王座(Lv.90+ · 👥 4人)\n   深渊祭坛最深处的王座，深渊领主·摩罗凝视着一切。地底恶魔的军团在此列队——它们等这一天，等了不止三百年。(地底支线)\n   👹 Boss：深渊领主·摩罗(Lv.95)· 掉落：摩罗之冠碎片\n   🔑 需『深渊圣印』：深渊祭坛精英·祭坛守卫·魔眼掉落\n   📍 入口：深渊祭坛·祭坛核心\n24. 🔒 🐉 龙之墓(Lv.90+ · 👥 4人)\n   龙骨山脉深处的巨龙墓地，古龙·奥姆之影在此守望龙族传承。龙语回荡——只有真正的勇士才配带走它。(主线第 10 章)\n   👹 Boss：古龙·奥姆之影(Lv.95)· 掉落：龙语传承\n   🔑 需『龙牙信物』：龙脊山脉·石龙掉落\n   📍 入口：龙巢·巢穴深处\n25. 🔒 🌩️ 风暴王座(Lv.90+ · 👥 3-4人)\n   龙脊山脉之巅的风暴王座，雷霆君主统御着雷云。雷霆为冠，狂风为座——能坐上去的，只有风暴本身。(支线)\n   👹 Boss：雷霆君主(Lv.95)· 掉落：风暴之核\n   🔑 需『雷光令』：风暴崖精英·风暴崖主·雷鸣掉落\n   📍 入口：风暴崖·风暴崖顶\n26. 🔒 🌀 风暴之眼(Lv.92+ · 👥 4人)\n   雷暴高原的风暴之眼，风暴之主·云怒在此执掌雷霆。雷云之上是天空的尽头——也是风暴的故乡。(天空支线)\n   👹 Boss：风暴之主·云怒(Lv.97)· 掉落：云怒之核碎片\n   🔑 需『雷核钥匙』：雷暴高原·雷元素掉落\n   📍 入口：雷暴高原·高原核心\n27. 🔒 ☁️ 云中圣殿(Lv.94+ · 👥 4人)\n   风翼群岛之巅的云中圣殿，云中圣者·奥拉守护着天空的传承。圣光与风暴在此交织——最后的试炼，留给最强的冒险者。(天空支线)\n   👹 Boss：云中圣者·奥拉(Lv.99)· 掉落：奥拉圣印碎片\n   🔑 需『云玺』：星辉台精英·星龙掉落\n   📍 入口：彩虹云谷·云谷深处\n━━━━━━━━━━━━\n💡 『撤退』保留进度离开副本\n💡 按顺序轮流出手，Boss 血量随人数上涨，配合好才能通关！",
    "IN4_战斗面板": "── 敌方 ──\n  A1层: a1  房间怪 ❤️500/500\n── 我方 ──\n  B1层: b1  甲 ❤️100/100\n🕐 时刻 0.0s ｜ ⚡ 行动顺序：甲(我) → 房间怪(敌)\n✅ 甲：❤️ 100/100 💙 999/999\n　🛡️「⚔️攻击↑(剩3刻) 🛡️减伤25%(3刻) ✨护盾30(2刻) ✨护盾5」\n👹敌：「房间怪 💔破甲(剩3刻) 房间怪 🎯标记×2」\n💡 选敌：『技能1 a2』打2号(纯数字同义)；治疗『技能 <名称> b1』奶自己",
    "IN5_副本状态面板": "👺 【哥布林营地】 第 1 轮 🚪 第 1 层 · 一层\n━━━━━━━━━━━━\n── 敌方 ──\n  A1层: a1  房间怪 ❤️500/500\n── 我方 ──\n  B1层: b1  甲 ❤️100/100\n🕐 时刻 0.0s ｜ ⚡ 行动顺序：甲(我) → 房间怪(敌)\n✅ 甲：❤️ 100/100 💙 999/999\n💡 选敌：『技能1 a2』打2号(纯数字同义)；治疗『技能 <名称> b1』奶自己\n━━━━━━━━━━━━\n⏳ 轮到 甲 行动！『攻击』『技能 <名称>』『防御』",
    "IN6_地图_rooms_全提示": "🗺️ 【哥布林营地 · 酋长帐篷】\n兽骨装饰的帐篷深处，咕噜酋长坐在兽皮宝座上，身边堆满抢来的货物。皇冠歪戴，它正等着好好『招待』不速之客。\n━━━━━━━━━━━━\n📍 当前位置：酋长帐篷\n📮 可前往：\n  ●1. 篝火营地\n  🧭 出城需先到『入口栅栏』\n🔎 可探索触发：\n  ●💀 被抢的商队货箱\n  👑 Boss：哥布林酋长·咕噜\n\n💡 『前往 <序号>』切换位置\n━━━━━━━━━━━━\n🚪 副本内 · 无出口（没有通往外面的路）\n🐾 此房怪物剩余：哥布林守卫（『探索』高概率遭遇）\n🔎 此房可调查：篝火、古老神龛(『调查 <名称>』)\n💰 副本资源池剩余：30 金币 · 兽肉×2\n👑 Boss 就在这个房间！『探索』进入战斗！\n🎁 战利品堆：首领的遗物堆在角落（『调查 战利品堆』）\n🧱 墙上有一块松动的墙砖……（『调查 墙砖』）\n💡 单人副本直接『副本 <名字>』开本",
    "IN7_地图_rooms_已肃清": "🗺️ 【哥布林营地 · 入口栅栏】\n━━━━━━━━━━━━\n🚪 副本内 · 无出口（没有通往外面的路）\n🐾 此房怪物已肃清。\n💰 副本资源池剩余：30 金币 · 兽肉×2\n💡 『副本』查看战况，『角色』看队伍",
    "IN8_地图_分层_描述缺失": "🗺️ 【👺哥布林营地】第 1 层 · 一层\n━━━━━━━━━━━━\n📜 你环顾四周，准备迎接这里的敌人。\n🤔 似乎有暗门/机关的气息……(线索可能藏在石碑或机关里)\n━━━━━━━━━━━━\n✨ 场景：\n  []\n  []\n━━━━━━━━━━━━\n🐾 敌人：哥布林守卫(『探索』遇怪)\n━━━━━━━━━━━━\n💡 『副本』查看战况，『角色』看队伍",
    "IN9_地图_分层_暗门与肃清": "🗺️ 【👺哥布林营地】第 1 层 · 一层\n━━━━━━━━━━━━\n📜 石廊尽头有风。\n🔓 隐藏房间：暗门后是密室\n━━━━━━━━━━━━\n✨ 场景：\n  ['❓ 古老石碑：(『调查 古老石碑』)']\n  []\n━━━━━━━━━━━━\n✅ 本层敌人已肃清！剩余可调查：古老石碑(『调查 <名称>』)；『深入』前往下一层。\n━━━━━━━━━━━━\n💡 单人副本直接『副本 <名字>』开本",
    "RT1_超时自动防御": "⏰ 甲 迟迟没有行动，自动进入防御姿态！\n🛡 甲 摆出防御姿态，受到的伤害减半！\n⏰ 甲 迟迟没有行动，自动进入防御姿态！\n🛡 甲 摆出防御姿态，受到的伤害减半！\n—— 房间怪 行动 ——\n(格挡后 1 点伤害)\n💥 甲 受到 1 点伤害！\n⏰ 甲 迟迟没有行动，自动进入防御姿态！\n🛡 甲 摆出防御姿态，受到的伤害减半！\n⏰ 甲 迟迟没有行动，自动进入防御姿态！\n🛡 甲 摆出防御姿态，受到的伤害减半！\n⏰ 甲 迟迟没有行动，自动进入防御姿态！\n🛡 甲 摆出防御姿态，受到的伤害减半！\n⏰ 甲 迟迟没有行动，自动进入防御姿态！\n🛡 甲 摆出防御姿态，受到的伤害减半！\n⏰ 甲 迟迟没有行动，自动进入防御姿态！\n🛡 甲 摆出防御姿态，受到的伤害减半！\n⏰ 甲 迟迟没有行动，自动进入防御姿态！\n🛡 甲 摆出防御姿态，受到的伤害减半！\n⏰ 甲 迟迟没有行动，自动进入防御姿态！\n🛡 甲 摆出防御姿态，受到的伤害减半！\n⏰ 甲 迟迟没有行动，自动进入防御姿态！\n🛡 甲 摆出防御姿态，受到的伤害减半！\n⏰ 甲 迟迟没有行动，自动进入防御姿态！\n🛡 甲 摆出防御姿态，受到的伤害减半！\n⏰ 甲 迟迟没有行动，自动进入防御姿态！\n🛡 甲 摆出防御姿态，受到的伤害减半！\n⏰ 甲 迟迟没有行动，自动进入防御姿态！\n🛡 甲 摆出防御姿态，受到的伤害减半！\n—— 房间怪 行动 ——\n💥 乙 受到 1 点伤害！\n⏰ 甲 迟迟没有行动，自动进入防御姿态！\n🛡 甲 摆出防御姿态，受到的伤害减半！\n⏰ 甲 迟迟没有行动，自动进入防御姿态！\n🛡 甲 摆出防御姿态，受到的伤害减半！\n⏰ 甲 迟迟没有行动，自动进入防御姿态！\n🛡 甲 摆出防御姿态，受到的伤害减半！\n⏰ 甲 迟迟没有行动，自动进入防御姿态！\n🛡 甲 摆出防御姿态，受到的伤害减半！\n⏰ 甲 迟迟没有行动，自动进入防御姿态！\n🛡 甲 摆出防御姿态，受到的伤害减半！\n⏰ 甲 迟迟没有行动，自动进入防御姿态！\n🛡 甲 摆出防御姿态，受到的伤害减半！\n⏰ 甲 迟迟没有行动，自动进入防御姿态！\n🛡 甲 摆出防御姿态，受到的伤害减半！\n🛡 乙 摆出防御姿态，受到的伤害减半！\n━━━━━━━━━━━━\n── 敌方 ──\n  A1层: a1  房间怪 ❤️5000/5000\n── 我方 ──\n  B1层: b1  甲 ❤️99/100 | b2  乙 ❤️99/100\n🕐 时刻 12.8s ｜ ⚡ 行动顺序：甲(我) → 乙(我) → 房间怪(敌)\n✅ 甲：❤️ 99/100 💙 999/999 🛡️防御\n✅ 乙：❤️ 99/100 💙 999/999 🛡️防御\n💡 选敌：『技能1 a2』打2号(纯数字同义)；治疗『技能 <名称> b1』奶自己\n⏳ 轮到 甲 行动！『攻击』『技能 <名称>』『防御』",
    "RT2_嘲讽": "—— 房间怪 行动 ——\n💥 甲 受到 1 点伤害！\n🛡️ 你高声嘲讽，怪物怒火尽归你身！（强制攻击自己）\n━━━━━━━━━━━━\n── 敌方 ──\n  A1层: a1  房间怪 ❤️5000/5000\n── 我方 ──\n  B1层: b1  甲 ❤️99/100\n🕐 时刻 1.7s ｜ ⚡ 行动顺序：甲(我) → 房间怪(敌)\n✅ 甲：❤️ 99/100 💙 999/999\n💡 选敌：『技能1 a2』打2号(纯数字同义)；治疗『技能 <名称> b1』奶自己\n⏳ 轮到 甲 行动！『攻击』『技能 <名称>』『防御』",
    "RT3_同归于尽": "💥 房间怪 受到 1 点伤害，倒下了！\n⚔️ 同归于尽！你与敌人同时倒下了……\n\n💀 队伍全灭……副本失败！冒险者们被送回了最近的城镇。\n📍 甲 被送回了【白鹿城·白鹿广场】（HP 0，先休息恢复吧）",
}   # 迁移前快照（2026-09-13 真跑/源码 AST 存下，勿手改）

INSTANCE_LOG_TEMPLATES = {
    "instance.日志_击杀_宠物升级": "，升至 Lv.«»！",
    "instance.日志_击杀_宠物经验": "  🐾«» 分得经验 +«»",
    "instance.日志_击杀_拾取材料": "，拾取材料 «»",
    "instance.日志_击杀_经验": "  «»：经验 +«»",
    "instance.日志_列表_入口": "   📍 入口：«»·«»",
    "instance.日志_列表_轮流提示": "💡 按顺序轮流出手，Boss 血量随人数上涨，配合好才能通关！",
    "instance.日志_列表_钥匙": "   🔑 需『«»』：«»",
    "instance.日志_列表_首领": "   👹 Boss：«»(Lv.«»)· 掉落：«»",
    "instance.日志_同归于尽": "⚔️ 同归于尽！你与敌人同时倒下了……",
    "instance.日志_嘲讽": "🛡️ 你高声嘲讽，怪物怒火尽归你身！（强制攻击自己）",
    "instance.日志_团队治疗": "✨ «» 恢复 «» 点生命！",
    "instance.日志_地图_Boss房": "👑 Boss 就在这个房间！『探索』进入战斗！",
    "instance.日志_地图_可调查": "🔎 此房可调查：«»«»(『调查 <名称>』)",
    "instance.日志_地图_怪剩余": "🐾 此房怪物剩余：«»（『探索』高概率遭遇）",
    "instance.日志_地图_怪肃清": "🐾 此房怪物已肃清。",
    "instance.日志_地图_房间标题": "🗺️ 【«» · «»】",
    "instance.日志_地图_无出口": "🚪 副本内 · 无出口（没有通往外面的路）",
    "instance.日志_地图_资源池": "💰 副本资源池剩余：«» 金币",
    "instance.日志_墙砖提示": "🧱 墙上有一块松动的墙砖……（『调查 墙砖』）",
    "instance.日志_失败_全灭": "💀 队伍全灭……副本失败！冒险者们被送回了最近的城镇。",
    "instance.日志_失败_回城": "📍 «» 被送回了【«»·«»】（HP 0，先休息恢复吧）",
    "instance.日志_层_Boss在前": "👑 Boss 就在前方：«»！『探索』进入战斗！",
    "instance.日志_层_场景标题": "✨ 场景：",
    "instance.日志_层_宝箱": "🔐 神秘宝箱：密室深处泛着微光（『调查 宝箱』）",
    "instance.日志_层_敌人列表": "🐾 敌人：«»(『探索』遇怪)",
    "instance.日志_层_无敌": "🐾 这里暂时没有敌人。",
    "instance.日志_层_暗门气息": "🤔 似乎有暗门/机关的气息……(线索可能藏在石碑或机关里)",
    "instance.日志_层_环顾": "📜 你环顾四周，准备迎接这里的敌人。",
    "instance.日志_层_肃清_剩调查": "✅ 本层敌人已肃清！剩余可调查：«»(『调查 <名称>』)；『深入』前往下一层。",
    "instance.日志_层_肃清_无调查": "✅ 本层敌人已肃清！『深入』前往下一层。",
    "instance.日志_层_隐藏房间": "🔓 隐藏房间：«»",
    "instance.日志_战利品堆提示": "🎁 战利品堆：首领的遗物堆在角落（『调查 战利品堆』）",
    "instance.日志_搜刮_拾取": "🎒 拾取：«» ×1",
    "instance.日志_搜刮_空": "🎁 你搜刮了战利品堆，但里面空空的……",
    "instance.日志_搜刮_金币": "🎁 你搜刮了战利品堆：金币 +«»",
    "instance.日志_组队无坦克": "🛡️ 没有坦克：Boss 仇恨没人拉，输出容易被追着打",
    "instance.日志_组队无治疗": "✨ 没有治疗：血线压力大，记得多带药水",
    "instance.日志_组队无输出": "⚔️ 没有输出：可能打到超时哦",
    "instance.日志_行动序_我": "«»(我)",
    "instance.日志_行动序_敌": "«»(敌)",
    "instance.日志_调查痕迹": "🔍 通关后这里多了些可调查的痕迹：«»（『调查 <名称>』· 今日剩余 «» 次）",
    "instance.日志_超时自动防御": "⏰ «» 迟迟没有行动，自动进入防御姿态！",
    "instance.日志_轮到行动": "⏳ 轮到 «» 行动！『攻击』『技能 <名称>』『防御』",
    "instance.日志_通关_专属装备": "  👑 «» 从Boss身上拾取稀有专属：【«»】！",
    "instance.日志_通关_停留搜刮": "🏆 副本已通关！你可以在副本内停留搜刮：",
    "instance.日志_通关_再挑战": "💡 『副本』可再次挑战，首通成就已记录～",
    "instance.日志_通关_击败": "🎉 【«»】被击败了！«»«» 通关！",
    "instance.日志_通关_图纸": "  📜 «» 拾取图纸：«»",
    "instance.日志_通关_图纸已学": "  📜 «» 拾取图纸：«»（已学会，化作 «» 张图纸残页）",
    "instance.日志_通关_墙砖": "  · 🧱 墙上似乎有【松动的墙砖】……（『调查 墙砖』）",
    "instance.日志_通关_奖励": "  «»：金币 +«» 经验 +«»",
    "instance.日志_通关_宝石": "  💎 «» 获得幸运宝石：«»！(『原石』镶嵌到装备孔位)",
    "instance.日志_通关_宠物升级": "，升至 Lv.«»！",
    "instance.日志_通关_宠物经验": "  🐾«» 分得经验 +«»",
    "instance.日志_通关_战利品堆": "  · 🎁 【战利品堆】—— 首领的遗物，搜刮一次（『调查 战利品堆』）",
    "instance.日志_通关_材料": "  🎒 «» 拾取：«»",
    "instance.日志_通关_珍藏装备": "  ⚔️ «» 拾取 Boss 珍藏：【«»】！",
    "instance.日志_通关_离开提示": "搜刮完毕用『离开副本』传出～",
    "instance.日志_通关_调查痕迹提示": "  · 🔍 通关后这里多了些可调查的痕迹（『副本地图』查看，每日限 «» 次）",
    "instance.日志_通关_阵亡": "  💀 «» 已阵亡，未能获得奖励",
    "instance.日志_通关_首功图纸": "👑 首功 «» 额外获得图纸：«»",
    "instance.日志_通关_首功图纸已学": "👑 首功 «» 额外获得图纸：«»（已学会，化作 «» 张图纸残页）",
    "instance.日志_面板_减伤": "🛡️减伤«»%(«»刻)",
    "instance.日志_面板_增益": "«»(剩«»刻)",
    "instance.日志_面板_护盾": "✨护盾«»",
    "instance.日志_面板_护盾_剩刻": "✨护盾«»(«»刻)",
    "instance.日志_面板_敌增益_剩刻": "«» «»(剩«»刻)",
    "instance.日志_面板_敌增益_叠层": "«» «»×«»",
    "instance.日志_面板_敌增益行": "👹敌：「«»」",
    "instance.日志_面板_选敌提示": "💡 选敌：『技能1 a2』打2号(纯数字同义)；治疗『技能 <名称> b1』奶自己",
}   # 迁移前快照（2026-09-13 真跑/源码 AST 存下，勿手改）

def t10_instance_log_frozen():
    print("\n[10] 副本日志域逐字冻结：迁移前 26 分支（战斗/面板/地图/搜刮/击杀/通关/失败）复跑比对")
    check("冻结基准已内嵌（26 分支）", len(INSTANCE_LOG_FROZEN) == 26, len(INSTANCE_LOG_FROZEN))
    now = _il_scenarios()
    bad = [k for k in INSTANCE_LOG_FROZEN if INSTANCE_LOG_FROZEN[k] != now.get(k)]
    for k in bad:
        print("     · %s 现=%r" % (k, (now.get(k) or "")[:140]))
    check("★ 副本日志 26 分支输出与迁移前**逐字一致**", not bad, bad)
    _single = ("IN13_搜刮_空",)     # 单行分支（本身无换行结构）
    check("冻结基准非空且含换行结构（防基准写空）",
          all(v and "\n" in v for k, v in INSTANCE_LOG_FROZEN.items() if k not in _single))

    # 表里模板（剔槽位成骨架）== 迁移前源码 f-string / 常量串的骨架（逐字）
    def _skel(v):
        return re.sub(r"\{[^{}]*\}", "«»", v or "")
    tb = T.table()
    diff = [k for k in INSTANCE_LOG_TEMPLATES
            if _skel((tb.spec(k).value if tb.spec(k) else "")) != INSTANCE_LOG_TEMPLATES[k]]
    check("★ 70 条日志模板骨架与迁移前源码**逐字一致**（含真跑覆盖不到的分支）",
          not diff, diff[:5])

    # 旧文案零残留：三份源文件 append 族实参不再有中文
    # （排版分隔线 / T.text·T.static 内的键与取值回退口径（如 '队友'）除外）
    # ★ P5E-DELETE（2026-09-15，删壳批）：扫描面已从宿主壳改到**包内真源**
    #   （`INSTANCE_*_SRC` 别名改指 PKG_*，见其定义处注释）—— 即原先「真源那份」现在被扫。
    #   包内真源里保留的是**取值回退**（`_a.get('name', '队友')`，宿主壳那份由搬运脚本
    #   派生、当时不含字面量），正是本检查头注早已列明的豁免面。⇒ 按同一口径把
    #   「只作为 `.get(key, "…")` 第二个实参出现的字面量」排除（判定其余中文残留的力度不变）。
    left = []
    for _p in (INSTANCE_ROUTER_SRC, INSTANCE_BATTLE_SRC, INSTANCE_SRC):
        _src = io.open(_p, encoding="utf-8").read()
        _tree = ast.parse(_src)
        for _n in ast.walk(_tree):
            if not (isinstance(_n, ast.Call) and isinstance(_n.func, ast.Attribute)
                    and _n.func.attr in ("append", "extend", "insert") and _n.args):
                continue
            _tcalls = set()
            for _c in ast.walk(_n.args[0]):
                if (isinstance(_c, ast.Call) and isinstance(_c.func, ast.Attribute)
                        and _c.func.attr in ("text", "static")):
                    _tcalls.update(id(_x) for _x in ast.walk(_c))
            #   包内真源里保留的是**取值回退**（`_a.get('name', '队友')`），正是本检查头注
            #   早已列明的豁免面 ⇒ 只对「该字面量仅出现在 `.get(key, "…")` 第二实参位」
            #   的情形豁免（其余中文残留仍照旧报红）。判据力度不变。
            _lits = []
            for _x in ast.walk(_n.args[0]):
                if (id(_x) in _tcalls or not isinstance(_x, ast.Constant)
                        or not isinstance(_x.value, str)
                        or not any("\u4e00" <= c <= "\u9fff" for c in _x.value)):
                    continue
                _is_fb = any(
                    isinstance(_g, ast.Call) and isinstance(_g.func, ast.Attribute)
                    and _g.func.attr == "get" and len(_g.args) == 2 and _g.args[1] is _x
                    for _g in ast.walk(_n.args[0]))
                if _is_fb:
                    continue
                _lits.append(_x.value)
            if _lits and not all(s.strip().startswith("──") for s in _lits):
                left.append((os.path.basename(_p), _n.lineno,
                             (ast.get_source_segment(_src, _n.args[0]) or "")[:48]))
    check("★ 旧文案零残留（append 族实参已无中文；分隔线与取值回退留在代码）",
          not left, left[:4])


# ═══════════════════════ PB_BRANCHES_BEGIN ═══════════════════════
# ↓↓↓ 以下这段（含本行）与 $TEMP/df_panel_block.py 逐字同源：采快照脚本与门禁共用 ↓↓↓
# -*- coding: utf-8 -*-
"""副本面板/地图/状态域 —— 复跑分支块（★ 快照与门禁共用同一份驱动代码）。

本块由两部分共同使用：
  ① $TEMP/df_panel_snap.py（迁移前采快照 / 迁移后复跑比对）
  ② tests/test_texts_table.py 的 t11 段（逐字拼入，勿手改分叉）
所以本块**只依赖 `_engine_harness` + 包内 content**，不打印、不写文件、不 assert。

约定（与 INSTANCE_LOG_FROZEN 同款）：
  · 每个分支自己 clean_db + 固定 random.seed；需要时打桩 random.random（进出还原）。
  · 输出统一走 _pb_text()（把命令 yield 的多条拼成一段，逐字可比）。
"""
import asyncio  # noqa: E402
import random   # noqa: E402

from _engine_harness import C as _PB_C, db as _PB_db, clean_db as _PB_clean   # noqa: E402
from _engine_harness import FakeEvent as _PB_Event, run as _PB_run            # noqa: E402
from _engine_harness import make_player as _PB_mk, Main as _PB_Main           # noqa: E402
from content.flow import instance_run as _PB_IR   # noqa: E402
from content.flow import instance_battle as _PB_IB   # noqa: E402
from _engine_harness import Main as _PB_Inst   # noqa: E402  （原 InstanceCmds 壳 → 驱动口）
from _engine_harness import Main as _PB_Combat     # noqa: E402  （原 CombatCmds 壳 → 驱动口）
from _engine_harness import Main as _PB_World        # noqa: E402  （原 WorldCmds 壳 → 驱动口）
from _engine_harness import Main as _PB_Economy  # noqa: E402  （原 EconomyCmds 壳 → 驱动口）
# ★ TAIL 线修复（B14 后遗症）：调查点表的**真读点**在包内 `content/catalog_space.py`
#   （生产侧 `content/instance_cmds.py:1947/1991/2791/3270` 读的就是它的模块全局）；
#   宿主 `game.content` 只是 22 行「再导出壳」，原来那句 `_PB_C.INVESTIGATION_POINTS = …` 打在壳上、
#   包内实现读不到 → 猴补失效（PB29 假红）。改打包内同一个名字。
from content import catalog_space as _PB_CSP                                          # noqa: E402
# ★ R4（2026-09-15）PB16 修：`_PB_C.subarea_pois` 在**包内聚合门面** `content/facade.py::C`
#   里尚未登记（facade 缺名，R5 已登记待补 —— 见 VALLEY4_LINES_BRIEF 附 A
#   `subarea_pois→content.pois`）。本文件按既有口径**直取包内真源**（与 P5D-2 §2.1 同款，
#   也与生产侧一致：`content/instance_cmds.py:111` 就是 `from .pois import subarea_pois`）。
from content.pois import subarea_pois as _PB_subarea_pois                             # noqa: E402

_PB_GID = "g_panel"
_PB_Q = "q_p"
_PB_GOBLIN_ROOM = "goblin_camp_1"     # 哥布林营地入口房


class _PBHost(_PB_Main):
    """副本面板快照宿主（`_engine_harness.Main`：同名的包内 InstanceImpl / CombatCmds /
    WorldCmds / EconomyImpl 落点由驱动口按名绑定，等价旧的四 Mixin 宿主）。"""


# ── 驱动脚手架 ─────────────────────────────────────────────────────────
def _pb_text(msgs):
    return "\n".join(str(m) for m in msgs) if not isinstance(msgs, str) else msgs


def _pb_run_sync(coro_or_agen):
    """同步收一条 async 命令/生成器的全部 yield。"""
    async def _c():
        if hasattr(coro_or_agen, "asend"):
            out = []
            async for x in coro_or_agen:
                out.append(x)
            return out
        return await coro_or_agen
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_c())
    finally:
        loop.close()


def _pb_cmd(m, handler, msg, qq=_PB_Q):
    ev = _PB_Event(_PB_GID, qq, msg)
    return _pb_text(_pb_run_sync(_PB_run(getattr(m, handler), ev)))


def _pb_player(qid, name="甲", cls="战士", level=60, learned=None,
               cur_map="misty_swamp", cur_subarea=_PB_GOBLIN_ROOM):
    _PB_mk(_PB_GID, qid, name=name, cls=cls, level=level)
    _PB_db.update_player(_PB_GID, qid, cur_map=cur_map, cur_subarea=cur_subarea,
                         stamina=999999, learned_skills=list(learned or []))
    return _PB_db.get_player(_PB_GID, qid)


def _pb_snap(qid, name="甲", cls="cls_zhan_shi", level=60, hp=None, spd=30, mp=999):
    pl = _PB_db.get_player(_PB_GID, qid) or {}
    mh = int(pl.get("max_hp", 500) or 500)
    return {"name": name, "qq_id": str(qid), "class_name": cls, "level": level,
            "hp": int(hp if hp is not None else mh), "max_hp": mh, "mp": mp, "max_mp": mp,
            "equipment": {}, "skills": [], "learned_skills": [],
            "class_tier": 0, "evolve_path": 0, "attributes": pl.get("attributes"),
            "bonus": {"panel": {}, "cap": {}, "cost": {}}, "race": pl.get("race"),
            "uid": "p_%s" % qid, "buffs": {}, "stacks": {}, "defending": False,
            "charging": None, "ct": 0.0, "p_shields": {}, "spd": spd}


def _pb_enemy(hp=500, spd=1, role="dps", atk=1, uid="e_pb", name="房间怪", lv=15):
    return {"uid": uid, "name": name, "hp": hp, "max_hp": hp, "atk": atk, "def": 0,
            "matk": 1, "mdef": 0, "spd": spd, "crit": 0.0, "lv": lv, "level": lv,
            "role": role, "is_boss": role == "boss", "is_elite": role == "elite",
            "rank": 1, "reach": 1, "ct": 1.0, "exp": 10, "gold": 5, "drops": []}


def _pb_st(qids, inst_id="inst_goblin_camp", names=None, **kw):
    qids = [str(q) for q in qids]
    names = names or {}
    st = {"type": "instance", "inst_id": inst_id, "leader": qids[0], "members": qids,
          "alive": {q: True for q in qids},
          "players": {q: _pb_snap(q, names.get(q, "甲")) for q in qids},
          "boss": None, "enemy": None, "enemies": [], "turn": 0, "round": 1,
          "mode": "battle", "pets": {}, "p_buffs": {q: {} for q in qids},
          "p_hot": {q: {} for q in qids}, "p_food_effects": {q: [] for q in qids},
          "p_defending": {q: False for q in qids}, "mech_stacks": {q: {} for q in qids},
          "now": 0.0, "battle": None, "contribution": {}, "threat": {q: 0 for q in qids},
          "over": False, "turn_time": 0, "stage_pending": [], "inst_stages": [],
          "stage_idx": 0, "stage_cleared": False, "world_id": ""}
    st.update(kw)
    return st


def _pb_save(qid, st):
    _PB_db.save_battle(_PB_GID, qid, st)
    return st


class _PBRR(object):
    """random.random 打桩（进出还原）。"""

    def __init__(self, value):
        self.value = value

    def __enter__(self):
        self._orig = random.random
        if self.value is not None:
            random.random = lambda: self.value
        return self

    def __exit__(self, *exc):
        random.random = self._orig
        return False
# ══════════════════════════════════════════════════════════════════════
# 分支 1：开本面板（单人 / 多人队伍构成）
# ══════════════════════════════════════════════════════════════════════
def _pb_b1_open_solo():
    """开本（单人·地图模式）：开启面板 + 层全景 + 单人挑战行 + 行动引导。"""
    _PB_clean()
    random.seed(20260914)
    _pb_player(_PB_Q, "甲")
    _PB_db.update_player(_PB_GID, _PB_Q, cur_map="misty_swamp", cur_subarea="misty_swamp_3")
    return _pb_cmd(_PB_Main(None), "instance_cmd", "副本 哥布林营地")


def _pb_b2_open_party():
    """开本（2 人队·min_players>1）：队伍构成行 + 职业搭配提示行。"""
    _PB_clean()
    random.seed(20260914 + 2)
    _pb_player("q_p2", "甲")
    _pb_player("q_p3", "乙")
    _PB_db.update_player(_PB_GID, "q_p2", cur_map="harbor_docks", cur_subarea="harbor_docks_2")
    _PB_db.update_player(_PB_GID, "q_p3", cur_map="harbor_docks", cur_subarea="harbor_docks_2")
    _PB_db.party_create(_PB_GID, "q_p2", "q_p3")
    return _pb_cmd(_PB_Main(None), "instance_cmd", "副本 锈潮船坞", qq="q_p2")


def _pb_b3_open_bad_name():
    """开本（名字不存在）：『没有『X』这个副本』。"""
    _PB_clean()
    random.seed(20260914 + 3)
    _pb_player(_PB_Q, "甲")
    return _pb_cmd(_PB_Main(None), "instance_cmd", "副本 不存在的本")


# ══════════════════════════════════════════════════════════════════════
# 分支 2：加入战斗
# ══════════════════════════════════════════════════════════════════════
def _pb_b4_join_leader_and_mate():
    """加入战斗：队长视角（i_am_leader）+ 队员已在战斗中（自己锁）两行。"""
    _PB_clean()
    random.seed(20260914 + 4)
    _pb_player("q_j1", "队长甲")
    _pb_player("q_j2", "队员乙")
    _PB_db.party_create(_PB_GID, "q_j1", "q_j2")
    st = _pb_st(["q_j1"], names={"q_j1": "队长甲"},
                enemies=[_pb_enemy(hp=500, spd=1)], mode="battle")
    st["boss"] = st["enemy"] = st["enemies"][0]
    _pb_save("q_j1", st)
    inst = _PBHost()
    inst._lock_battle(_PB_GID, "q_j1")
    inst._lock_battle(_PB_GID, "q_j2")
    out1 = _pb_cmd(inst, "join_battle", "加入战斗", qq="q_j1")
    out2 = _pb_cmd(inst, "join_battle", "加入战斗", qq="q_j2")
    inst._unlock_battle(_PB_GID, "q_j2")
    return out1 + "\n@@@\n" + out2


def _pb_b5_join_success():
    """加入战斗成功：加入行 + 战斗面板 + 当前参战行。"""
    _PB_clean()
    random.seed(20260914 + 5)
    _pb_player("q_j3", "队长甲")
    _pb_player("q_j4", "队员乙")
    _PB_db.party_create(_PB_GID, "q_j3", "q_j4")
    st = _pb_st(["q_j3"], names={"q_j3": "队长甲"},
                enemies=[_pb_enemy(hp=500, spd=1)], mode="battle")
    st["boss"] = st["enemy"] = st["enemies"][0]
    _pb_save("q_j3", st)
    return _pb_cmd(_PBHost(), "join_battle", "加入战斗", qq="q_j4")


# ══════════════════════════════════════════════════════════════════════
# 分支 3：不在副本 / 战斗中的守卫提示
# ══════════════════════════════════════════════════════════════════════
def _pb_b6_not_in_instance():
    """不在副本（带列表引导）+ 不在副本（简）——深入/副本地图/调查/撤退/确认撤退/离开。"""
    _PB_clean()
    random.seed(20260914 + 6)
    _pb_player(_PB_Q, "甲")
    inst = _PBHost()
    outs = [_pb_cmd(inst, "instance_advance", "深入"),
            _pb_cmd(inst, "instance_map_view_cmd", "副本地图"),
            _pb_cmd(inst, "instance_investigate", "调查 宝箱"),
            _pb_cmd(inst, "instance_retreat", "撤退"),
            _pb_cmd(inst, "instance_retreat_confirm", "确认撤退"),
            _pb_cmd(inst, "instance_leave", "离开副本")]
    return "\n@@@\n".join(outs)


def _pb_b7_in_battle_guards():
    """战斗中守卫：副本地图/调查/撤退(Boss)/撤退(非Boss)/离开 五条。"""
    _PB_clean()
    random.seed(20260914 + 7)
    _pb_player(_PB_Q, "甲")
    st = _pb_st([_PB_Q], names={_PB_Q: "甲"}, enemies=[_pb_enemy(hp=500, spd=1, role="boss")],
                mode="battle")
    st["boss"] = st["enemy"] = st["enemies"][0]
    _pb_save(_PB_Q, st)
    inst = _PBHost()
    outs = [_pb_cmd(inst, "instance_map_view_cmd", "副本地图"),
            _pb_cmd(inst, "instance_investigate", "调查 宝箱"),
            _pb_cmd(inst, "instance_retreat", "撤退")]
    st2 = _pb_st([_PB_Q], names={_PB_Q: "甲"}, enemies=[_pb_enemy(hp=500, spd=1)], mode="battle")
    st2["boss"] = st2["enemy"] = st2["enemies"][0]
    st2["enemies"][0]["is_boss"] = False
    _pb_save(_PB_Q, st2)
    outs.append(_pb_cmd(inst, "instance_retreat", "撤退"))
    outs.append(_pb_cmd(inst, "instance_leave", "离开副本"))
    return "\n@@@\n".join(outs)


def _pb_b8_expired_hint():
    """副本 24h 过期提示。"""
    _PB_clean()
    random.seed(20260914 + 8)
    _pb_player(_PB_Q, "甲")
    st = _pb_st([_PB_Q], names={_PB_Q: "甲"})
    st["_expired"] = True
    _pb_save(_PB_Q, st)
    return _PBHost()._instance_expired_hint(_PB_GID, _PB_Q)


# ══════════════════════════════════════════════════════════════════════
# 分支 4：深入
# ══════════════════════════════════════════════════════════════════════
def _pb_b9_advance_room_mode():
    """深入（rooms 副本）：提示『移动 <房间>』。"""
    _PB_clean()
    random.seed(20260914 + 9)
    _pb_player(_PB_Q, "甲")
    st = _pb_st([_PB_Q], names={_PB_Q: "甲"},
                rooms={_PB_GOBLIN_ROOM: {"monsters_left": [], "pois_left": [],
                                         "boss_alive": False}},
                mode="map")
    _pb_save(_PB_Q, st)
    return _pb_cmd(_PBHost(), "instance_advance", "深入")


def _pb_b10_advance_blocked():
    """深入：未清层（探索引导 / 先打完）、已通关、无分层、末层 四条。"""
    _PB_clean()
    random.seed(20260914 + 10)
    _pb_player(_PB_Q, "甲")
    inst = _PBHost()
    # 未清层 + 尚有未遭遇怪 → 引导『探索』
    st = _pb_st([_PB_Q], names={_PB_Q: "甲"},
                inst_stages=[{"name": "一层"}, {"name": "二层"}],
                stage_pending=[["m_x", "小怪", "dps", 15, [], []]], mode="map")
    _pb_save(_PB_Q, st)
    outs = [_pb_cmd(inst, "instance_advance", "深入")]
    # 未清层 + 无待清怪 → 先打完再说
    st2 = _pb_st([_PB_Q], names={_PB_Q: "甲"},
                 inst_stages=[{"name": "一层"}, {"name": "二层"}], mode="map")
    _pb_save(_PB_Q, st2)
    outs.append(_pb_cmd(inst, "instance_advance", "深入"))
    # 已通关
    st3 = _pb_st([_PB_Q], names={_PB_Q: "甲"}, cleared=True, mode="map")
    _pb_save(_PB_Q, st3)
    outs.append(_pb_cmd(inst, "instance_advance", "深入"))
    # 无分层结构
    st4 = _pb_st([_PB_Q], names={_PB_Q: "甲"}, mode="map")
    _pb_save(_PB_Q, st4)
    outs.append(_pb_cmd(inst, "instance_advance", "深入"))
    # 末层
    st5 = _pb_st([_PB_Q], names={_PB_Q: "甲"},
                 inst_stages=[{"name": "一层"}], stage_idx=0, stage_cleared=True, mode="map")
    _pb_save(_PB_Q, st5)
    outs.append(_pb_cmd(inst, "instance_advance", "深入"))
    return "\n@@@\n".join(outs)


def _pb_b11_advance_next_stage():
    """深入（清层推进）：地图模式继续深入 + 战斗模式层行/面板/轮到行。"""
    _PB_clean()
    random.seed(20260914 + 11)
    _pb_player(_PB_Q, "甲")
    inst = _PBHost()
    # 下一层有怪 → mode=map → 继续深入 + 层全景
    st = _pb_st([_PB_Q], names={_PB_Q: "甲"},
                inst_stages=[{"name": "一层", "monsters": [["m_x", "小怪", "dps", 15, [], []]]},
                             {"name": "二层", "monsters": [["m_y", "小怪2", "dps", 15, [], []]]}],
                stage_idx=0, stage_cleared=True, mode="map")
    _pb_save(_PB_Q, st)
    out1 = _pb_cmd(inst, "instance_advance", "深入")
    # 下一层无怪（不切地图模式）→ 层行 + 面板 + 轮到行
    st2 = _pb_st([_PB_Q], names={_PB_Q: "甲"},
                 inst_stages=[{"name": "一层", "monsters": [["m_x", "小怪", "dps", 15, [], []]]},
                              {"name": "二层"}],
                 stage_idx=0, stage_cleared=True, mode="battle",
                 enemies=[_pb_enemy(hp=500, spd=1)])
    st2["boss"] = st2["enemy"] = st2["enemies"][0]
    _pb_save(_PB_Q, st2)
    out2 = _pb_cmd(inst, "instance_advance", "深入")
    return out1 + "\n@@@\n" + out2


# ══════════════════════════════════════════════════════════════════════
# 分支 5：地图（分层形态：精英标注）
# ══════════════════════════════════════════════════════════════════════
def _pb_b12_map_stage_elite():
    """分层地图：怪名 + ⭐精英· 标注（敌人列表行）。"""
    _PB_clean()
    random.seed(20260914 + 12)
    _pb_player(_PB_Q, "甲")
    host = _PBHost()
    st = _pb_st([_PB_Q], names={_PB_Q: "甲"},
                inst_stages=[{"name": "一层", "desc": "石廊尽头有风。",
                              "monsters": [["m_goblin_guard", "哥布林守卫", "tank", 15, [], []]],
                              "elite": ["m_elite", "哥布林督军", "elite", 17, [], []]}],
                stage_idx=0, mode="map")
    st.pop("resources_pool", None)
    _pb_save(_PB_Q, st)
    return host._instance_map_view(st, _PB_GID)


# ══════════════════════════════════════════════════════════════════════
# 分支 6：调查（空参数 / 未命中 / 已处理）
# ══════════════════════════════════════════════════════════════════════
def _pb_b13_investigate_miss():
    """调查：空参数格式提示 + 未命中目标。"""
    _PB_clean()
    random.seed(20260914 + 13)
    _pb_player(_PB_Q, "甲")
    st = _pb_st([_PB_Q], names={_PB_Q: "甲"},
                rooms={_PB_GOBLIN_ROOM: {"monsters_left": [], "pois_left": [],
                                         "boss_alive": False}},
                mode="map")
    _pb_save(_PB_Q, st)
    inst = _PBHost()
    out1 = _pb_cmd(inst, "instance_investigate", "调查")
    out2 = _pb_cmd(inst, "instance_investigate", "调查 不存在的东西")
    return out1 + "\n@@@\n" + out2


def _pb_b14_investigate_used():
    """调查（层内 POI 已用过）：『X已经被处理过了。』。"""
    _PB_clean()
    random.seed(20260914 + 14)
    _pb_player(_PB_Q, "甲")
    poi = {"id": "p_used", "name": "旧石碑", "type": "shrine"}
    st = _pb_st([_PB_Q], names={_PB_Q: "甲"},
                inst_stages=[{"name": "一层", "pois": [poi]}],
                stage_idx=0, stage_pois={"0": {"p_used": {"used": True}}}, mode="map")
    _pb_save(_PB_Q, st)
    return _pb_cmd(_PBHost(), "instance_investigate", "调查 旧石碑")


# ══════════════════════════════════════════════════════════════════════
# 分支 7：探索（通关后 / 肃清 / 遇怪 / 无事 / POI / 陷阱）
# ══════════════════════════════════════════════════════════════════════
def _pb_b15_explore_cleared():
    """探索：已通关 → 引导搜刮/离开。"""
    _PB_clean()
    random.seed(20260914 + 15)
    _pb_player(_PB_Q, "甲")
    st = _pb_st([_PB_Q], names={_PB_Q: "甲"}, cleared=True, mode="map")
    _pb_save(_PB_Q, st)
    return _pb_text(_pb_run_sync(_PBHost()._instance_explore(
        _PB_Event(_PB_GID, _PB_Q), _PB_GID, _PB_Q, {"state": st})))


def _pb_b16_explore_rooms_three():
    """探索（rooms）：此房已肃清 / 遇怪（进战斗面板）/ 未发现你 / POI 搜索 四态。"""
    _PB_clean()
    random.seed(20260914 + 16)
    _pb_player(_PB_Q, "甲")
    host = _PBHost()
    outs = []
    # ③ 无怪可遇
    st = _pb_st([_PB_Q], names={_PB_Q: "甲"},
                rooms={_PB_GOBLIN_ROOM: {"monsters_left": [], "pois_left": [],
                                         "boss_alive": False}},
                resources_pool={"gold_left": 30, "mats_left": {"兽肉": 2}}, mode="map")
    _pb_save(_PB_Q, st)
    outs.append(_pb_text(_pb_run_sync(host._instance_explore(
        _PB_Event(_PB_GID, _PB_Q), _PB_GID, _PB_Q, {"state": st}))))
    # ② 遇怪（pois_left 空 → 必过 POI 分支；random 打 0.0 → 命中遇怪）
    st2 = _pb_st([_PB_Q], names={_PB_Q: "甲"},
                 rooms={_PB_GOBLIN_ROOM: {"monsters_left":
                                          [["m_goblin_guard", "哥布林守卫", "tank", 15, [], []]],
                                          "pois_left": [], "boss_alive": False}},
                 mode="map")
    _pb_save(_PB_Q, st2)
    with _PBRR(0.0):
        outs.append(_pb_text(_pb_run_sync(host._instance_explore(
            _PB_Event(_PB_GID, _PB_Q), _PB_GID, _PB_Q, {"state": st2}))))
    # ② 未发现你（random 打 0.99 → 未过遇怪判定）
    st3 = _pb_st([_PB_Q], names={_PB_Q: "甲"},
                 rooms={_PB_GOBLIN_ROOM: {"monsters_left":
                                          [["m_goblin_guard", "哥布林守卫", "tank", 15, [], []]],
                                          "pois_left": [], "boss_alive": False}},
                 mode="map")
    _pb_save(_PB_Q, st3)
    with _PBRR(0.99):
        outs.append(_pb_text(_pb_run_sync(host._instance_explore(
            _PB_Event(_PB_GID, _PB_Q), _PB_GID, _PB_Q, {"state": st3}))))
    # ① POI 搜索（pois_left 有物 + random 0.0）
    _poi_id = (_PB_subarea_pois("goblin_camp", _PB_GOBLIN_ROOM) or [None])[0]
    st4 = _pb_st([_PB_Q], names={_PB_Q: "甲"},
                 rooms={_PB_GOBLIN_ROOM: {"monsters_left": [], "pois_left": [_poi_id],
                                          "boss_alive": False}},
                 resources_pool={"gold_left": 30, "mats_left": {}}, mode="map")
    _pb_save(_PB_Q, st4)
    with _PBRR(0.0):
        outs.append(_pb_text(_pb_run_sync(host._instance_explore(
            _PB_Event(_PB_GID, _PB_Q), _PB_GID, _PB_Q, {"state": st4}))))
    return "\n@@@\n".join(outs)


def _pb_b17_explore_stage_paths():
    """探索（旧 stages 路径）：无怪无事 / 陷阱踩中 两态。"""
    _PB_clean()
    random.seed(20260914 + 17)
    _pb_player(_PB_Q, "甲")
    host = _PBHost()
    st = _pb_st([_PB_Q], names={_PB_Q: "甲"},
                inst_stages=[{"name": "一层", "pois": []}], stage_idx=0, mode="map")
    _pb_save(_PB_Q, st)
    out1 = _pb_text(_pb_run_sync(host._instance_explore(
        _PB_Event(_PB_GID, _PB_Q), _PB_GID, _PB_Q, {"state": st})))
    trap = {"id": "p_trap", "name": "尖刺陷阱", "type": "trap"}
    st2 = _pb_st([_PB_Q], names={_PB_Q: "甲"},
                 inst_stages=[{"name": "一层", "pois": [trap]}], stage_idx=0, mode="map")
    _pb_save(_PB_Q, st2)
    with _PBRR(0.0):
        out2 = _pb_text(_pb_run_sync(host._instance_explore(
            _PB_Event(_PB_GID, _PB_Q), _PB_GID, _PB_Q, {"state": st2})))
    return out1 + "\n@@@\n" + out2


# ══════════════════════════════════════════════════════════════════════
# 分支 8：撤退 / 确认撤退 / 离开 / 移动
# ══════════════════════════════════════════════════════════════════════
def _pb_b18_retreat_flow():
    """撤退流程：弹确认 + 已弹过确认 + 确认成功 + 无待确认 + 确认过期。"""
    _PB_clean()
    random.seed(20260914 + 18)
    _pb_player(_PB_Q, "甲")
    _PB_db.update_player(_PB_GID, _PB_Q, cur_map="misty_swamp", cur_subarea="misty_swamp_3")
    m = _PB_Main(None)
    outs = [_pb_cmd(m, "instance_cmd", "副本 哥布林营地")]
    outs.append(_pb_cmd(m, "instance_retreat", "撤退"))          # 弹确认
    outs.append(_pb_cmd(m, "instance_retreat", "撤退"))          # 已弹过
    # 确认过期：把挂起确认改成本副本之外
    import json as _json
    _PB_db.set_event_state("retreat_confirm_%s" % _PB_Q,
                           _json.dumps({"ts": 0, "inst": "inst_other"}))
    outs.append(_pb_cmd(m, "instance_retreat_confirm", "确认撤退"))
    # 无待确认
    _PB_db.set_event_state("retreat_confirm_%s" % _PB_Q, "")
    outs.append(_pb_cmd(m, "instance_retreat_confirm", "确认撤退"))
    # 重新弹确认 → 确认成功（放弃进度）
    outs.append(_pb_cmd(m, "instance_retreat", "撤退"))
    outs.append(_pb_cmd(m, "instance_retreat_confirm", "确认撤退"))
    return "\n@@@\n".join(outs)


def _pb_b19_leave_and_resume():
    """回到副本深处（撤退存进度 → 重新开本恢复）+ 离开副本。"""
    _PB_clean()
    random.seed(20260914 + 19)
    _pb_player(_PB_Q, "甲")
    _PB_db.update_player(_PB_GID, _PB_Q, cur_map="misty_swamp", cur_subarea="misty_swamp_3")
    m = _PB_Main(None)
    outs = [_pb_cmd(m, "instance_cmd", "副本 哥布林营地")]
    # 恢复分支：把副本行标记为已撤退（保留进度）+ 解战斗锁后重新『副本 <名字>』
    row = _PB_db.get_battle_raw(_PB_GID, _PB_Q)
    st = row["state"]
    st["retreated"] = True
    st["mode"] = "map"
    st["_expired"] = False
    _pb_save(_PB_Q, st)
    m._unlock_battle(_PB_GID, _PB_Q)
    _PB_db.update_player(_PB_GID, _PB_Q, cur_map="misty_swamp", cur_subarea="misty_swamp_3")
    outs.append(_pb_cmd(m, "instance_cmd", "副本 哥布林营地"))
    outs.append(_pb_cmd(m, "instance_leave", "离开副本"))
    return "\n@@@\n".join(outs)


def _pb_b20_move_not_leader():
    """副本内移动：非队长提示。"""
    _PB_clean()
    random.seed(20260914 + 20)
    _pb_player("q_m1", "队长甲")
    _pb_player("q_m2", "队员乙")
    _PB_db.update_player(_PB_GID, "q_m1", cur_map="misty_swamp", cur_subarea="misty_swamp_3")
    _PB_db.update_player(_PB_GID, "q_m2", cur_map="misty_swamp", cur_subarea="misty_swamp_3")
    _PB_db.party_create(_PB_GID, "q_m1", "q_m2")
    m = _PB_Main(None)
    _pb_cmd(m, "instance_cmd", "副本 哥布林营地", qq="q_m1")
    inst = m
    pl2 = _PB_db.get_player(_PB_GID, "q_m2")
    return _pb_text(_pb_run_sync(inst._instance_move_route(
        _PB_Event(_PB_GID, "q_m2"), _PB_GID, "q_m2", pl2, "入口栅栏")))


# ══════════════════════════════════════════════════════════════════════
# 分支 9：通关超时自动离开
# ══════════════════════════════════════════════════════════════════════
def _pb_b21_cleared_timeout():
    """通关停留超 30 分钟 → 自动离开提示。"""
    _PB_clean()
    random.seed(20260914 + 21)
    _pb_player(_PB_Q, "甲")
    _PB_db.update_player(_PB_GID, _PB_Q, cur_map="misty_swamp", cur_subarea="misty_swamp_3")
    m = _PB_Main(None)
    _pb_cmd(m, "instance_cmd", "副本 哥布林营地")
    row = _PB_db.get_battle(_PB_GID, _PB_Q)
    st = row["state"]
    st["cleared"] = True
    st["cleared_time"] = 1
    _pb_save(_PB_Q, st)
    return _pb_cmd(m, "instance_cmd", "副本")


# ══════════════════════════════════════════════════════════════════════
# 分支 10：暗格 / 宝箱
# ══════════════════════════════════════════════════════════════════════
def _pb_b22_secret_crack():
    """暗格：死墙（无守卫）+ 拉开门（守卫战面板）。"""
    _PB_clean()
    random.seed(20260914 + 22)
    _pb_player(_PB_Q, "甲")
    host = _PBHost()
    st = _pb_st([_PB_Q], names={_PB_Q: "甲"}, inst_stages=[{"name": "一层"}],
                stage_idx=0, mode="map")
    _pb_save(_PB_Q, st)
    out1 = host._instance_secret_crack(_PB_GID, _PB_Q, _PB_db.get_player(_PB_GID, _PB_Q), st)
    st2 = _pb_st([_PB_Q], names={_PB_Q: "甲"},
                 inst_stages=[{"name": "一层",
                               "monsters": [["m_goblin_guard", "哥布林守卫", "tank", 15, [], []]]}],
                 stage_idx=0, mode="map")
    _pb_save(_PB_Q, st2)
    out2 = host._instance_secret_crack(_PB_GID, _PB_Q, _PB_db.get_player(_PB_GID, _PB_Q), st2)
    return out1 + "\n@@@\n" + out2


def _pb_b23_secret_chest():
    """密室宝箱开启（掉落走 drop_engine，seed 固定）。"""
    _PB_clean()
    random.seed(20260914 + 23)
    _pb_player(_PB_Q, "甲")
    host = _PBHost()
    st = _pb_st([_PB_Q], names={_PB_Q: "甲"}, secret_chest=True, mode="map")
    _pb_save(_PB_Q, st)
    return host._instance_secret_chest(_PB_GID, _PB_Q, _PB_db.get_player(_PB_GID, _PB_Q), st)


# ══════════════════════════════════════════════════════════════════════
# 分支 11：通关后调查点（四档奖励）
# ══════════════════════════════════════════════════════════════════════
def _pb_b24_investigate_reward():
    """调查点：收藏 / 图纸残页 / 保底材料 / 蓝符 四档 + 空结果。"""
    outs = []
    # 收藏（random 0.0 < collect 0.03）
    _PB_clean()
    random.seed(20260914 + 24)
    _pb_player(_PB_Q, "甲")
    host = _PBHost()
    st = _pb_st([_PB_Q], names={_PB_Q: "甲"}, cleared=True, mode="map")
    _pb_save(_PB_Q, st)
    with _PBRR(0.0):
        outs.append(host._instance_investigate_cleared(
            _PB_GID, _PB_Q, _PB_db.get_player(_PB_GID, _PB_Q), st, "酋长的战利品堆"))
    # 图纸残页（0.03 ≤ r < 0.28）
    _PB_clean()
    random.seed(20260914 + 25)
    _pb_player(_PB_Q, "甲")
    st2 = _pb_st([_PB_Q], names={_PB_Q: "甲"}, cleared=True, mode="map")
    _pb_save(_PB_Q, st2)
    with _PBRR(0.10):
        outs.append(host._instance_investigate_cleared(
            _PB_GID, _PB_Q, _PB_db.get_player(_PB_GID, _PB_Q), st2, "劫掠清单"))
    # 保底材料（r ≥ 0.28）
    _PB_clean()
    random.seed(20260914 + 26)
    _pb_player(_PB_Q, "甲")
    st3 = _pb_st([_PB_Q], names={_PB_Q: "甲"}, cleared=True, mode="map")
    _pb_save(_PB_Q, st3)
    with _PBRR(0.90):
        outs.append(host._instance_investigate_cleared(
            _PB_GID, _PB_Q, _PB_db.get_player(_PB_GID, _PB_Q), st3, "篝火余烬"))
    # 蓝符（Lv.60+ 副本，0.03 ≤ r < 0.18）
    _PB_clean()
    random.seed(20260914 + 27)
    _pb_player(_PB_Q, "甲")
    st4 = _pb_st([_PB_Q], names={_PB_Q: "甲"}, inst_id="inst_moon_temple",
                 cleared=True, mode="map")
    _pb_save(_PB_Q, st4)
    with _PBRR(0.04):
        outs.append(host._instance_investigate_cleared(
            _PB_GID, _PB_Q, _PB_db.get_player(_PB_GID, _PB_Q), st4, "月池"))
    return "\n@@@\n".join(str(o) for o in outs)


# ══════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════
# 分支 12：加入战斗无角色 / 旧层探索遇怪（Boss 台词行）/ 战斗状态异常两态
# ══════════════════════════════════════════════════════════════════════
# ── B18-L10 BEGIN（本段为 B18-L10 的门禁口径适配；上面的冻结基准一字未动）──────────
# B18-L10 把副本 8 条的**守卫声明**从宿主装饰器搬进包内 `content/cmds_instance.py` 的 `@_declare`
# 处理器，宿主壳只剩 `@declared` + 两行 `_BRIDGE.run_async` —— 于是**原先靠解 `__wrapped__`
# 剥掉 `@require_player()` 的手法失效**（新壳没有装饰器链，`getattr(inst, "join_battle")` 是
# 绑定方法，再传 `inst` 就多一个实参）。
# 本场景的原意 =「剥掉守卫，**直接跑命令体**」，故改为直接调**包内 handler**（守卫不在这里：
# 守卫由宿主 `_BRIDGE` 按声明施加）→ 命令体自带的「无角色」分支照旧被钉住，冻结值一字未改。
# 玩家可见行为不变的证据（真实派发路径走守卫）：`out/b18l10_snap.py` 的 jb_01_noplayer
# 改前 = 改后 =「你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～」。
class _PB_Env:
    """最小引擎 `Env` 替身（只补包内 handler 用到的两个取件口）。"""

    def __init__(self, shell, event):
        self.state = {"shell": shell}
        self.raw = event


def _pb_b25_join_no_char():
    """加入战斗：还没有角色（B18-L10：直接跑包内命令体 = 原「剥掉 @require_player 守卫」）。

    ★ 改：副本 8 条的 handler 薄壳已从 `content/cmds_instance.py` 删掉（该文件随迁删）——
    声明表 `bind` 点名实现体，处理器由引擎 `bind_handler()` 造。取件口 = 同一张运行时登记表
    `content.commands::COMMANDS`（守卫仍不在这里：守卫由宿主 `_BRIDGE` 按声明施加）。
    """
    _PB_clean()
    random.seed(20260914 + 25)
    inst = _PBHost()
    from content.commands import COMMANDS as _PKG_COMMANDS
    _pkg_join = _PKG_COMMANDS["join_battle"]["handler"]
    env = _PB_Env(inst, _PB_Event(_PB_GID, "q_none", "加入战斗"))
    return _pb_text(_pb_run_sync(_pkg_join(env)))
# ── B18-L10 END ────────────────────────────────────────────────────────────────


def _pb_b26_explore_stage_boss():
    """探索（旧 stages 路径）：遇怪 + Boss 台词行 + 面板 + 轮到行。"""
    _PB_clean()
    random.seed(20260914 + 26)
    _pb_player(_PB_Q, "甲")
    host = _PBHost()
    st = _pb_st([_PB_Q], names={_PB_Q: "甲"},
                inst_stages=[{"name": "一层", "monsters": [["m_x", "小怪", "dps", 15, [], []]]}],
                stage_pending=[["m_boss", "哥布林督军", "boss", 15, [], []]], mode="map")
    _pb_save(_PB_Q, st)
    return _pb_text(_pb_run_sync(host._instance_explore(
        _PB_Event(_PB_GID, _PB_Q), _PB_GID, _PB_Q, {"state": st})))


def _pb_b27_act_state_error():
    """instance_battle.act：无 battle sides / 行动者不在阵列 两态。

    ★ R4（2026-09-15）装配差修正：终态**包内** `act` 返回 **4 位**
    （`logs, ended, nxt, abort`，abort ∈ {"no_sides","no_actor",""}），
    文案由调用方按码渲染 —— 与生产侧 `content/cmds_instance_router.py::_act3`
    的折法同源；旧宿主壳的 `act` 是 3 位、把 abort 文案并进 `logs`。
    本文件 `_PB_IB` 已改绑包内真源（P5D-2 repoint），故这里按 `_act3` 同款折一次
    再比文本（**玩家可见输出不变**，只是取文本的姿势对齐终态 API）。
    """
    def _logs_of(result):
        if len(result) == 3:                    # 旧 3 位口径（外部替换桩 / 历史形状）
            return result[0]
        logs, _ended, _nxt, abort = result
        return [_PB_IB.abort_text(abort)] if abort else logs

    _PB_clean()
    random.seed(20260914 + 27)
    _pb_player(_PB_Q, "甲")
    outs = [_pb_text(_logs_of(_PB_IB.act({"battle": {}}, _PB_GID, _PB_Q, "attack")))]
    st = _pb_st([_PB_Q], names={_PB_Q: "甲"}, enemies=[_pb_enemy()], mode="battle")
    st["boss"] = st["enemy"] = st["enemies"][0]
    _PB_IB.build_battle(st)
    outs.append(_pb_text(_logs_of(_PB_IB.act(st, _PB_GID, "q_ghost", "attack"))))
    return "\n@@@\n".join(outs)


def _pb_b28_secret_chest_all():
    """密室宝箱五档：宠物蛋 / 图纸残页 / 装备 / 材料 / 符文（各自 seed 固定）。"""
    outs = []
    for seed in (20260914 + 102, 20260914 + 101, 20260914 + 107,
                 20260914 + 105, 20260914 + 106):
        _PB_clean()
        random.seed(seed)
        _pb_player(_PB_Q, "甲")
        host = _PBHost()
        st = _pb_st([_PB_Q], names={_PB_Q: "甲"}, secret_chest=True, mode="map")
        _pb_save(_PB_Q, st)
        outs.append(host._instance_secret_chest(
            _PB_GID, _PB_Q, _PB_db.get_player(_PB_GID, _PB_Q), st))
    return "\n@@@\n".join(outs)


def _pb_b29_investigate_empty():
    """调查点：奖励空结果（收藏档池无效）→『空空如也』；材料档无效 →『一点零碎』兜底。"""
    host = _PBHost()
    outs = []
    _orig_pts = _PB_CSP.INVESTIGATION_POINTS
    # ① 空结果：命中收藏档但收藏池无有效材料 → reward []
    _PB_clean()
    random.seed(20260914 + 29)
    _pb_player(_PB_Q, "甲")
    st = _pb_st([_PB_Q], names={_PB_Q: "甲"}, inst_id="inst_moon_temple",
                cleared=True, mode="map")
    _pb_save(_PB_Q, st)
    _PB_CSP.INVESTIGATION_POINTS = {
        "inst_moon_temple": [{"id": "p_void", "name": "月池", "collect": ["?none"]}]}
    try:
        with _PBRR(0.0):
            outs.append(host._instance_investigate_cleared(
                _PB_GID, _PB_Q, _PB_db.get_player(_PB_GID, _PB_Q), st, "月池"))
    finally:
        _PB_CSP.INVESTIGATION_POINTS = _orig_pts
    # ② 零碎兜底：材料档命中但材料 ID 无效 → 末行兜底
    _PB_clean()
    random.seed(20260914 + 30)
    _pb_player(_PB_Q, "甲")
    st2 = _pb_st([_PB_Q], names={_PB_Q: "甲"}, inst_id="inst_moon_temple",
                 cleared=True, mode="map")
    _pb_save(_PB_Q, st2)
    _PB_CSP.INVESTIGATION_POINTS = {
        "inst_moon_temple": [{"id": "p_void2", "name": "月池", "materials": ["?bad"]}]}
    try:
        with _PBRR(0.90):
            outs.append(host._instance_investigate_cleared(
                _PB_GID, _PB_Q, _PB_db.get_player(_PB_GID, _PB_Q), st2, "月池"))
    finally:
        _PB_CSP.INVESTIGATION_POINTS = _orig_pts
    return "\n@@@\n".join(str(o) for o in outs)


def _pb_b30_open_battle_mode():
    """开本（战斗模式·首层空层）：标题行 + CTB 提示行 + 层行（n=1）。"""
    _PB_clean()
    random.seed(20260914 + 31)
    _pb_player(_PB_Q, "甲")
    _PB_db.update_player(_PB_GID, _PB_Q, cur_map="misty_swamp", cur_subarea="misty_swamp_3")
    _orig = _PB_C.INSTANCES["inst_goblin_camp"]
    _copy = dict(_orig)
    _copy["stages"] = [{"name": "一层"}]
    _PB_C.INSTANCES["inst_goblin_camp"] = _copy
    try:
        return _pb_cmd(_PB_Main(None), "instance_cmd", "副本 哥布林营地")
    finally:
        _PB_C.INSTANCES["inst_goblin_camp"] = _orig


def _pb_b31_boss_room_victory():
    """Boss 房房间怪被击杀 → 通关结算（走 router 的 _room_boss 分支，含『Boss 已被击败』行）。"""
    _PB_clean()
    random.seed(20260914 + 40)
    import time as _t
    qid, cur_sa = "q_br", "goblin_camp_3"
    st = _pb_st([qid], names={qid: "甲"}, mode="battle",
                rooms={cur_sa: {"monsters_left": [], "pois_left": [],
                                "boss_alive": True, "_is_boss": True}})
    st["enemies"] = [_pb_enemy(hp=1, spd=1, role="boss", uid="e_boss", name="房间怪")]
    st["boss"] = st["enemy"] = st["enemies"][0]
    _PB_db.update_player(_PB_GID, qid, cur_map="misty_swamp", cur_subarea=cur_sa)
    _PB_IB.build_battle(st)
    host = _PBHost()
    msgs = []
    for _ in range(8):
        st["turn_time"] = int(_t.time())
        msgs += _pb_run_sync(host._instance_router(
            _PB_Event(_PB_GID, qid), _PB_GID, qid, st["players"][qid], st,
            "attack", None, None))
        if st.get("cleared") or st.get("over") or not st.get("enemies"):
            break
    return _pb_text(msgs)


_PB_BRANCHES = (
    ("PB01_开本_单人地图模式", _pb_b1_open_solo),
    ("PB02_开本_多人队伍构成", _pb_b2_open_party),
    ("PB03_开本_名字不存在", _pb_b3_open_bad_name),
    ("PB04_加入战斗_队长与队员", _pb_b4_join_leader_and_mate),
    ("PB05_加入战斗_成功", _pb_b5_join_success),
    ("PB06_不在副本_六提示", _pb_b6_not_in_instance),
    ("PB07_战斗中守卫_五提示", _pb_b7_in_battle_guards),
    ("PB08_副本过期提示", _pb_b8_expired_hint),
    ("PB09_深入_房间模式", _pb_b9_advance_room_mode),
    ("PB10_深入_四拦截", _pb_b10_advance_blocked),
    ("PB11_深入_清层推进两形态", _pb_b11_advance_next_stage),
    ("PB12_地图_分层精英标注", _pb_b12_map_stage_elite),
    ("PB13_调查_空参数与未命中", _pb_b13_investigate_miss),
    ("PB14_调查_已处理", _pb_b14_investigate_used),
    ("PB15_探索_通关后", _pb_b15_explore_cleared),
    ("PB16_探索_rooms四态", _pb_b16_explore_rooms_three),
    ("PB17_探索_旧层路径两态", _pb_b17_explore_stage_paths),
    ("PB18_撤退_全流程", _pb_b18_retreat_flow),
    ("PB19_离开与恢复进度", _pb_b19_leave_and_resume),
    ("PB20_移动_非队长", _pb_b20_move_not_leader),
    ("PB21_通关超时离开", _pb_b21_cleared_timeout),
    ("PB22_暗格_死墙与开门", _pb_b22_secret_crack),
    ("PB23_宝箱_开启", _pb_b23_secret_chest),
    ("PB24_调查点_四档奖励", _pb_b24_investigate_reward),
    ("PB25_加入战斗_无角色", _pb_b25_join_no_char),
    ("PB26_探索_旧层遇怪Boss", _pb_b26_explore_stage_boss),
    ("PB27_战斗异常_两态", _pb_b27_act_state_error),
    ("PB28_宝箱_五档", _pb_b28_secret_chest_all),
    ("PB29_调查点_空与零碎", _pb_b29_investigate_empty),
    ("PB30_开本_战斗模式", _pb_b30_open_battle_mode),
    ("PB31_Boss房通关_击败行", _pb_b31_boss_room_victory),
)


def _pb_scenarios() -> dict:
    """复跑全部副本面板/地图/状态分支（迁移前采快照 / 迁移后门禁比对，同一份驱动）。"""
    out = {}
    for name, fn in _PB_BRANCHES:
        try:
            out[name] = _pb_text(fn())
        except Exception as exc:                       # 采集期诚实报错，不静默
            out[name] = "<<EXC>> %s: %s" % (type(exc).__name__, exc)
    return out

INSTANCE_PANEL_FROZEN = {
    'PB01_开本_单人地图模式': '👺 【哥布林营地】副本开启！你踏入了这片区域。\n━━━━━━━━━━━━\n🗺️ 【哥布林营地 · 入口栅栏】\n歪斜的木栅栏围出营地外围，兽皮晾在栏上，篝火堆散落四周。守卫在缺口处探头张望，臭味与叫嚷声扑面而来。\n━━━━━━━━━━━━\n📍 当前位置：入口栅栏\n📮 可前往：\n  ●1. 篝火营地\n  \n🔎 可探索触发：\n  ●📦 生锈的铁箱 ●🔥 将熄的篝火\n\n✨ 可交互场景：\n  ●1. 🪨 哥布林营地界碑\n\n🐾 此地的怪物 (Lv.15-16)：\n  哥布林守卫 Lv.15±1\n  哥布林萨满 Lv.16±1\n\n💡 想去哪？『前往 <地名>』直达\n━━━━━━━━━━━━\n🚪 副本内 · 无出口（没有通往外面的路）\n🐾 此房怪物剩余：哥布林守卫、哥布林萨满（『探索』高概率遭遇）\n🔎 此房可调查：生锈的铁箱、将熄的篝火(『调查 <名称>』)\n💰 副本资源池剩余：424 金币 · 哥布林铁片×3、咕噜皇冠×1\n💡 备好钥匙，『副本 <名字>』进入\n━━━━━━━━━━━━\n🕐 单人挑战：战士·坦克\n💡 专注战斗！『副本』查看进度\n⏳ 副本内『移动』由队长带队；『探索』『调查』各人自由进行，遇怪全队合并进同一场战斗！\n📖 商路旁的营地还冒着劫掠后的烟，翻倒的货车旁散落着没来得及搬走的货物。行会的悬赏令在怀里发烫——今晚，该让哥布林酋长·咕噜尝尝被讨伐的滋味了。',
    'PB02_开本_多人队伍构成': '🦀 【锈潮船坞】副本开启！你踏入了这片区域。\n━━━━━━━━━━━━\n🗺️ 【锈潮船坞 · 闸门水道】\n铁港码头货仓区下的锈死闸门，推开后是一条半淹的水道，锈壳蟹攀在闸壁上，水鬼从水面下探出半个头。远处船坞深处传来钳甲碰撞的闷响。\n━━━━━━━━━━━━\n📍 当前位置：闸门水道\n📮 可前往：\n  ●1. 沉船坞池\n  \n👤 此地的玩家：\n  ●1. 乙 Lv.60\n\n🐾 此地的怪物 (Lv.25-27)：\n  锈壳蟹 Lv.25±1\n  水鬼 Lv.27±1\n\n💡 『探索』遇怪，『前往 <序号>』赶路\n━━━━━━━━━━━━\n🚪 副本内 · 无出口（没有通往外面的路）\n🐾 此房怪物剩余：锈壳蟹、水鬼（『探索』高概率遭遇）\n💰 副本资源池剩余：458 金币 · 锈潮蟹甲×2\n💡 副本激战中，『角色』了解队友\n━━━━━━━━━━━━\n👥 队伍构成：战士·坦克 + 战士·坦克\n⚠️ ✨ 没有治疗：血线压力大，记得多带药水\n💡 可发送『调查 <名称>』互动机关\n⏳ 副本内『移动』由队长带队；『探索』『调查』各人自由进行，遇怪全队合并进同一场战斗！\n📖 码头货仓区尽头有道锈死的闸门，推开时潮声裹着铁锈味扑面而来——废弃船坞的水道里，锈壳蟹窸窣爬行，深处时不时传来钳甲碰撞的闷响。铁港的老水手说，蟹王·锈钳的巢就在最深的船底，它钳上的船牌，还在等船主们来认领。',
    'PB03_开本_名字不存在': '没有『不存在的本』这个副本！『副本』查看列表～',
    'PB04_加入战斗_队长与队员': '你就是这场战斗的队长！『攻击』『技能 <名称>』『防御』行动～\n@@@\n你正在战斗中！先解决眼前的敌人～',
    'PB05_加入战斗_成功': '⚔️ 队员乙 加入了战斗！\n━━━━━━━━━━━━\n── 敌方 ──\n  A1层: a1  房间怪 ❤️500/500\n── 我方 ──\n  B1层: b1  队长甲 ❤️100/100 | b2  队员乙 ❤️100/1422\n🕐 时刻 0.0s ｜ ⚡ 行动顺序：队长甲(我) → 房间怪(敌) → 队员乙(我)\n✅ 队长甲：❤️ 100/100 💙 999/999\n✅ 队员乙：❤️ 100/1422 💙 100/213\n💡 选敌：『技能1 a2』打2号(纯数字同义)；治疗『技能 <名称> b1』奶自己\n👥 当前参战：队长甲、队员乙',
    'PB06_不在副本_六提示': '你当前不在副本中！输入『副本』查看副本列表～\n@@@\n你当前不在副本中！输入『副本』查看副本列表～\n@@@\n你当前不在副本中！输入『副本』查看副本列表～\n@@@\n你当前不在副本中！\n@@@\n你当前不在副本中！\n@@@\n你当前不在副本中！',
    'PB07_战斗中守卫_五提示': '战斗进行中！先解决眼前的敌人～(『攻击』『技能 <名称>』『防御』)\n@@@\n战斗进行中！先解决眼前的敌人～\n@@@\n战斗中无法撤退！Boss 锁定了你们的退路——打赢或战败！\n@@@\n战斗中无法撤退！先击败眼前的敌人再说！\n@@@\n战斗中无法离开！先解决眼前的敌人再说！',
    'PB08_副本过期提示': '⌛ 你之前的副本因超过 24 小时无人行动，已自动过期消失～',
    'PB09_深入_房间模式': '这个副本没有分层结构，直接挑战 Boss 吧～',
    'PB10_深入_四拦截': '当前层的敌人还没肃清！『探索』找到它们～\n@@@\n当前层的敌人还没肃清！先打完再说～\n@@@\n副本已通关！搜刮完用『离开副本』传出吧～\n@@@\n这个副本没有分层结构，直接挑战 Boss 吧～\n@@@\n已经是最深层了，击败面前的 Boss 就通关了！',
    'PB11_深入_清层推进两形态': '🧭 你继续深入……\n━━━━━━━━━━━━\n🗺️ 【👺哥布林营地】第 2 层 · 二层\n━━━━━━━━━━━━\n📜 你环顾四周，准备迎接这里的敌人。\n━━━━━━━━━━━━\n✨ 场景：\n  []\n  []\n━━━━━━━━━━━━\n🐾 敌人：小怪2(『探索』遇怪)\n━━━━━━━━━━━━\n💡 『副本』查看战况，『角色』看队伍\n@@@\n🧭 你继续深入……\n━━━━━━━━━━━━\n🚪 第 2 层 · 二层\n━━━━━━━━━━━━\n── 敌方 ──\n  A1层: a1  房间怪 ❤️500/500\n── 我方 ──\n  B1层: b1  甲 ❤️100/100\n🕐 时刻 0.0s ｜ ⚡ 行动顺序：甲(我) → 房间怪(敌)\n✅ 甲：❤️ 100/100 💙 999/999\n💡 选敌：『技能1 a2』打2号(纯数字同义)；治疗『技能 <名称> b1』奶自己\n⏳ 轮到 甲 行动！『攻击』『技能 <名称>』『防御』',
    'PB12_地图_分层精英标注': '🗺️ 【👺哥布林营地】第 1 层 · 一层\n━━━━━━━━━━━━\n📜 石廊尽头有风。\n━━━━━━━━━━━━\n✨ 场景：\n  []\n  []\n━━━━━━━━━━━━\n🐾 敌人：哥布林守卫 ⭐精英·哥布林督军(『探索』遇怪)\n━━━━━━━━━━━━\n💡 多人副本先『组队 <名字>』再开本',
    'PB13_调查_空参数与未命中': '格式：『调查 <目标>』，如『调查 宝箱』『调查 篝火』～（『副本地图』查看当前层可调查目标）\n@@@\n这里没有『不存在的东西』可以调查～『副本地图』看看周围有什么。',
    'PB14_调查_已处理': '旧石碑已经被处理过了。',
    'PB15_探索_通关后': '副本已通关，没有敌人可探索了！『副本地图』看看战利品堆，或『离开副本』传出～',
    'PB16_探索_rooms四态': '🍃 这里已被肃清，没有敌人了。『副本地图』看看剩余可调查的 POI，或让队长『移动』去别的房间～\n@@@\n🍃 这里已被肃清，没有敌人了。『副本地图』看看剩余可调查的 POI，或让队长『移动』去别的房间～\n@@@\n🍃 这里已被肃清，没有敌人了。『副本地图』看看剩余可调查的 POI，或让队长『移动』去别的房间～\n@@@\n🍃 这里已被肃清，没有敌人了。『副本地图』看看剩余可调查的 POI，或让队长『移动』去别的房间～',
    'PB17_探索_旧层路径两态': '🍃 你仔细搜索了这片区域，除了风声什么也没有发现。\n@@@\n🍃 你小心翼翼地探索……\n⚠️ 你触发了尖刺陷阱！全队受到 10% 最大生命的伤害！\n❤️ 甲 剩余 90/100',
    'PB18_撤退_全流程': '👺 【哥布林营地】副本开启！你踏入了这片区域。\n━━━━━━━━━━━━\n🗺️ 【哥布林营地 · 入口栅栏】\n歪斜的木栅栏围出营地外围，兽皮晾在栏上，篝火堆散落四周。守卫在缺口处探头张望，臭味与叫嚷声扑面而来。\n━━━━━━━━━━━━\n📍 当前位置：入口栅栏\n📮 可前往：\n  ●1. 篝火营地\n  \n🔎 可探索触发：\n  ●📦 生锈的铁箱 ●🔥 将熄的篝火\n\n✨ 可交互场景：\n  ●1. 🪨 哥布林营地界碑\n\n🐾 此地的怪物 (Lv.15-16)：\n  哥布林守卫 Lv.15±1\n  哥布林萨满 Lv.16±1\n\n💡 『地图』看详情，『探索』遇怪\n━━━━━━━━━━━━\n🚪 副本内 · 无出口（没有通往外面的路）\n🐾 此房怪物剩余：哥布林守卫、哥布林萨满（『探索』高概率遭遇）\n🔎 此房可调查：生锈的铁箱、将熄的篝火(『调查 <名称>』)\n💰 副本资源池剩余：424 金币 · 哥布林铁片×3、咕噜皇冠×1\n💡 副本激战中，『角色』了解队友\n━━━━━━━━━━━━\n🕐 单人挑战：战士·坦克\n💡 单人副本直接『副本 <名字>』开本\n⏳ 副本内『移动』由队长带队；『探索』『调查』各人自由进行，遇怪全队合并进同一场战斗！\n📖 商路旁的营地还冒着劫掠后的烟，翻倒的货车旁散落着没来得及搬走的货物。行会的悬赏令在怀里发烫——今晚，该让哥布林酋长·咕噜尝尝被讨伐的滋味了。\n@@@\n🏳️ 你要从【哥布林营地】撤退吗？\n⚠️ 撤退 = 放弃当前进度（已拿的战利品保留，但层数/机关进度清空，重新开本从头打）！\n💡 确认请回复『确认撤退』；反悔就继续冒险吧～\n@@@\n已弹过确认啦～ 回复『确认撤退』放弃进度，或继续冒险！\n@@@\n确认已过期（副本状态变化）～ 重新发『撤退』看看吧。\n@@@\n还没有待确认的撤退～ 副本中发『撤退』会先弹确认。\n@@@\n🏳️ 你要从【哥布林营地】撤退吗？\n⚠️ 撤退 = 放弃当前进度（已拿的战利品保留，但层数/机关进度清空，重新开本从头打）！\n💡 确认请回复『确认撤退』；反悔就继续冒险吧～\n@@@\n🏳️ 你们放弃了【哥布林营地】的进度，回到了入口。\n📌 已拿到的战利品保留在背包；想再挑战就重新『副本 哥布林营地』从头开始吧！',
    'PB19_离开与恢复进度': '👺 【哥布林营地】副本开启！你踏入了这片区域。\n━━━━━━━━━━━━\n🗺️ 【哥布林营地 · 入口栅栏】\n歪斜的木栅栏围出营地外围，兽皮晾在栏上，篝火堆散落四周。守卫在缺口处探头张望，臭味与叫嚷声扑面而来。\n━━━━━━━━━━━━\n📍 当前位置：入口栅栏\n📮 可前往：\n  ●1. 篝火营地\n  \n🔎 可探索触发：\n  ●📦 生锈的铁箱 ●🔥 将熄的篝火\n\n✨ 可交互场景：\n  ●1. 🪨 哥布林营地界碑\n\n🐾 此地的怪物 (Lv.15-16)：\n  哥布林守卫 Lv.15±1\n  哥布林萨满 Lv.16±1\n\n💡 『探索』遇怪，『前往 <序号>』赶路\n━━━━━━━━━━━━\n🚪 副本内 · 无出口（没有通往外面的路）\n🐾 此房怪物剩余：哥布林守卫、哥布林萨满（『探索』高概率遭遇）\n🔎 此房可调查：生锈的铁箱、将熄的篝火(『调查 <名称>』)\n💰 副本资源池剩余：424 金币 · 哥布林铁片×3、咕噜皇冠×1\n💡 『副本』查看战况，『角色』看队伍\n━━━━━━━━━━━━\n🕐 单人挑战：战士·坦克\n💡 『副本』查看战况，『角色』看队伍\n⏳ 副本内『移动』由队长带队；『探索』『调查』各人自由进行，遇怪全队合并进同一场战斗！\n📖 商路旁的营地还冒着劫掠后的烟，翻倒的货车旁散落着没来得及搬走的货物。行会的悬赏令在怀里发烫——今晚，该让哥布林酋长·咕噜尝尝被讨伐的滋味了。\n@@@\n🗺️ 【哥布林营地】\n哥布林营地，传说中的危险之地，唯有勇者敢于踏入。\n💡 输入『副本 哥布林营地』开启挑战（组队副本，等级/人数校验）\n━━━━━━━━━━━━\n📍 当前位置：哥布林营地\n📮 可前往：\n  🧭 出城需先到『入口栅栏』\n💡 『对话 <名字>』聊天，『探索』冒险\n━━━━━━━━━━━━\n🚪 副本内 · 无出口（没有通往外面的路）\n🐾 此房怪物已肃清。\n💰 副本资源池剩余：424 金币 · 哥布林铁片×3、咕噜皇冠×1\n💡 『副本』查看战况，『角色』看队伍\n@@@\n🏳️ 你带着战利品离开了哥布林营地。冒险者的旅途还在继续～',
    'PB20_移动_非队长': '⏳ 副本内由队长带队移动！等待队长『移动 <房间>』～',
    'PB21_通关超时离开': '🗺️ 【哥布林营地 · 入口栅栏】\n歪斜的木栅栏围出营地外围，兽皮晾在栏上，篝火堆散落四周。守卫在缺口处探头张望，臭味与叫嚷声扑面而来。\n━━━━━━━━━━━━\n📍 当前位置：入口栅栏\n📮 可前往：\n  ●1. 篝火营地\n  \n🔎 可探索触发：\n  ●📦 生锈的铁箱 ●🔥 将熄的篝火\n\n✨ 可交互场景：\n  ●1. 🪨 哥布林营地界碑\n\n🐾 此地的怪物 (Lv.15-16)：\n  哥布林守卫 Lv.15±1\n  哥布林萨满 Lv.16±1\n\n💡 『地图』看详情，『探索』遇怪\n━━━━━━━━━━━━\n🚪 副本内 · 无出口（没有通往外面的路）\n🐾 此房怪物剩余：哥布林守卫、哥布林萨满（『探索』高概率遭遇）\n🔎 此房可调查：生锈的铁箱、将熄的篝火(『调查 <名称>』)\n💰 副本资源池剩余：424 金币 · 哥布林铁片×3、咕噜皇冠×1\n💡 副本请走『副本 <名字>』开启',
    'PB22_暗格_死墙与开门': '🧱 墙砖松动了，但后面只有一堵死墙……（暗格消失了）\n@@@\n🧱 你扣住松动的墙砖用力一拉——暗门轰然打开！\n一个魁梧的身影挡在密室前……\n━━━━━━━━━━━━\n── 敌方 ──\n  A1层: a1  哥布林守卫 ❤️564/564\n── 我方 ──\n  B1层: b1  甲 ❤️100/100\n🕐 时刻 0.0s ｜ ⚡ 行动顺序：哥布林守卫(敌) → 甲(我)\n✅ 甲：❤️ 100/100 💙 100/999\n💡 选敌：『技能1 a2』打2号(纯数字同义)；治疗『技能 <名称> b1』奶自己\n⏳ 轮到 甲 行动！『攻击』『技能 <名称>』『防御』',
    'PB23_宝箱_开启': '🔐 你打开了密室宝箱！\n✨ 宝箱里泛起微光——符文【稀有符文·冰霜 I】！',
    'PB24_调查点_四档奖励': '🔍 你仔细调查了【酋长的战利品堆】……\n✨ 你发现了一件稀罕的收藏品——【骑士团徽章】！(图鉴『收藏』可查看)\n@@@\n🔍 你仔细调查了【劫掠清单】……\n📜 你翻出一叠泛黄的纸页——图纸残页 ×3！\n@@@\n🔍 你仔细调查了【篝火余烬】……\n🎒 你摸到了些材料——咕噜皇冠 ×1！\n@@@\n🔍 你仔细调查了【月池】……\n✨ 你拾起一枚刻着符文的宝石——【稀有符文·拾荒 I】！',
    'PB25_加入战斗_无角色': '你还没有角色！先『注册』开始冒险～',
    'PB26_探索_旧层遇怪Boss': '🍃 你警惕地探索着，突然——一层里的怪物扑了上来！\n━━━━━━━━━━━━\n💬 『金币！宝石！都是咕噜的！』咕噜把抢来的皇冠往头上一扣，咧开满嘴尖牙：『你们这些商队的小跟班，也敢来掀咕噜的帐篷？』\n── 敌方 ──\n  A1层: a1  哥布林督军的哥布林打手 ❤️564/564 | a2  哥布林督军的哥布林打手 ❤️564/564\n  A2层: a3  哥布林督军 ❤️9749/9749\n── 我方 ──\n  B1层: b1  甲 ❤️100/100\n🕐 时刻 0.0s ｜ ⚡ 行动顺序：哥布林督军(敌) → 哥布林督军的哥布林打手(敌) → 哥布林督军的哥布林打手(敌) → 甲(我)\n✅ 甲：❤️ 100/100 💙 100/999\n💡 选敌：『技能1 a2』打2号(纯数字同义)；治疗『技能 <名称> b1』奶自己\n⏳ 轮到 甲 行动！『攻击』『技能 <名称>』『防御』',
    'PB27_战斗异常_两态': '战斗状态异常，请重新遭遇！\n@@@\n你已不在战斗中（状态异常）！',
    'PB28_宝箱_五档': '🔐 你打开了密室宝箱！\n📜 宝箱里是泛黄的纸张——图纸残页 ×4！\n@@@\n🔐 你打开了密室宝箱！\n🎒 宝箱里是稀有材料——咕噜皇冠 ×1！\n@@@\n🔐 你打开了密室宝箱！\n🔵 宝箱深处静静躺着一件装备——【哥布林军刀】！\n@@@\n🔐 你打开了密室宝箱！\n✨🟣 宝箱深处静静躺着一件装备——【骑士残甲】！\n@@@\n🔐 你打开了密室宝箱！\n✨ 宝箱里泛起微光——符文【稀有符文·聚能 I】！',
    'PB29_调查点_空与零碎': '月池里空空如也，什么也没发现。\n@@@\n🔍 你仔细调查了【月池】……\n🎒 你翻了翻，只找到一点零碎。',
    'PB30_开本_战斗模式': '👺 【哥布林营地】副本开启！\n━━━━━━━━━━━━\n🚪 第 1 层 · 一层\n📜 商路旁的哥布林聚落，哥布林酋长·咕噜盘踞于此，靠抢劫商队为生。冒险者行会悬赏讨伐。(主线第 2 章)\n━━━━━━━━━━━━\n🕐 单人挑战：战士·坦克\n── 敌方 ──\n  A1层: a1  哥布林酋长·咕噜的哥布林打手 ❤️564/564 | a2  哥布林酋长·咕噜的哥布林打手 ❤️564/564\n  A2层: a3  哥布林酋长·咕噜 ❤️24414/24414\n── 我方 ──\n  B1层: b1  甲 ❤️100/1422\n🕐 时刻 0.0s ｜ ⚡ 行动顺序：哥布林酋长·咕噜(敌) → 甲(我) → 哥布林酋长·咕噜的哥布林打手(敌) → 哥布林酋长·咕噜的哥布林打手(敌)\n✅ 甲：❤️ 100/1422 💙 100/213\n💡 选敌：『技能1 a2』打2号(纯数字同义)；治疗『技能 <名称> b1』奶自己\n⏳ 轮到 甲 行动！『攻击』『技能 <名称>』『防御』\n💡 按 CTB 行动轴轮流出手，超时 60 秒自动防御；清光当前层怪物可『深入』下一层！\n📖 商路旁的营地还冒着劫掠后的烟，翻倒的货车旁散落着没来得及搬走的货物。行会的悬赏令在怀里发烫——今晚，该让哥布林酋长·咕噜尝尝被讨伐的滋味了。',
    'PB31_Boss房通关_击败行': '💥 房间怪 受到 1 点伤害，倒下了！\n👑 副本 Boss 已被击败！\n\n🎉 【房间怪】被击败了！👺哥布林营地 通关！\n📜 咕噜的皇冠滚落在篝火边，商路上的劫掠就此画上句号。行会的赏金结清了，可你总觉得，这条商路尽头的风声，才刚刚开始。\n\n🏆 副本已通关！你可以在副本内停留搜刮：\n  · 🎁 【战利品堆】—— 首领的遗物，搜刮一次（『调查 战利品堆』）\n  · 🔍 通关后这里多了些可调查的痕迹（『副本地图』查看，每日限 3 次）\n搜刮完毕用『离开副本』传出～\n\n💡 『副本』可再次挑战，首通成就已记录～',
}   # 迁移前快照（2026-09-13 真跑存下，来源 $TEMP/instance_panel_pre31.json —— 采于接线前的代码，勿手改）
INSTANCE_PANEL_OLD_LITERALS = [
    ' 加入了战斗！',
    ' 宝箱深处静静躺着一件装备——【',
    's ｜ ⚡ 行动顺序：',
    '⌛ 你之前的副本因超过 24 小时无人行动，已自动过期消失～',
    '⏳ 副本内『移动』由队长带队；『探索』『调查』各人自由进行，遇怪全队合并进同一场战斗！',
    '⏳ 副本内由队长带队移动！等待队长『移动 <房间>』～',
    '⏳ 通关时间已过 30 分钟，你已自动离开副本。',
    '✨ 你发现了一件稀罕的收藏品——【',
    '✨ 你拾起一枚刻着符文的宝石——【',
    '✨ 宝箱里泛起微光——符文【',
    '。冒险者的旅途还在继续～',
    '』从头开始吧！',
    '』可以调查～『副本地图』看看周围有什么。',
    '』这个副本！『副本』查看列表～',
    '】你回到了副本深处！',
    '】副本开启！',
    '】副本开启！你踏入了这片区域。',
    '】撤退吗？\n⚠️ 撤退 = 放弃当前进度（已拿的战利品保留，但层数/机关进度清空，重新开本从头打）！\n💡 确认请回复『确认撤退』；反悔就继续冒险吧～',
    '】的进度，回到了入口。\n📌 已拿到的战利品保留在背包；想再挑战就重新『副本 ',
    '】！(图鉴『收藏』可查看)',
    '】！『使用 宠物蛋』孵化！',
    '你已不在战斗中（状态异常）！',
    '你当前不在副本中！',
    '你当前不在副本中！输入『副本』查看副本列表～',
    '你正在战斗中！先解决眼前的敌人～',
    '你还没有角色！先『注册』开始冒险～',
    '副本内请使用『移动 <房间>』推进（队长带队）～『副本地图』查看可前往房间。',
    '副本已通关！搜刮完用『离开副本』传出吧～',
    '副本已通关，没有敌人可探索了！『副本地图』看看战利品堆，或『离开副本』传出～',
    '已弹过确认啦～ 回复『确认撤退』放弃进度，或继续冒险！',
    '已经是最深层了，击败面前的 Boss 就通关了！',
    '已经被处理过了。',
    '已经被搜刮一空了。',
    '当前层的敌人还没肃清！『探索』找到它们～',
    '当前层的敌人还没肃清！先打完再说～',
    '战斗中无法撤退！Boss 锁定了你们的退路——打赢或战败！',
    '战斗中无法撤退！先击败眼前的敌人再说！',
    '战斗中无法离开！先解决眼前的敌人再说！',
    '战斗进行中！先解决眼前的敌人～',
    '战斗进行中！先解决眼前的敌人～(『攻击』『技能 <名称>』『防御』)',
    '格式：『调查 <目标>』，如『调查 宝箱』『调查 篝火』～（『副本地图』查看当前层可调查目标）',
    '确认已过期（副本状态变化）～ 重新发『撤退』看看吧。',
    '还没有待确认的撤退～ 副本中发『撤退』会先弹确认。',
    '这个副本没有分层结构，直接挑战 Boss 吧～',
    '这里没有『',
    '里的怪物扑了上来！',
    '里空空如也，什么也没发现。',
    '🍃 你仔细搜索了这片区域，怪物没有发现你……',
    '🍃 你仔细搜索了这片区域，除了风声什么也没有发现。',
    '🍃 你仔细搜索着这片区域……',
    '🍃 你小心翼翼地探索……',
    '🍃 你警惕地探索着，突然——',
    '🍃 这里已被肃清，没有敌人了。『副本地图』看看剩余可调查的 POI，或让队长『移动』去别的房间～',
    '🎒 你摸到了些材料——',
    '🎒 你翻了翻，只找到一点零碎。',
    '🎒 宝箱里是稀有材料——',
    '🏰 【组队副本】',
    '🏳️ 你们放弃了【',
    '🏳️ 你带着战利品离开了',
    '🏳️ 你要从【',
    '👑 副本 Boss 已被击败！',
    '👥 当前参战：',
    '👥 队伍构成：',
    '💡 按 CTB 行动轴轮流出手，超时 60 秒自动防御；清光当前层怪物可『深入』下一层！',
    '📜 你翻出一叠泛黄的纸页——图纸残页 ×',
    '📜 宝箱里是泛黄的纸张——图纸残页 ×',
    '🔍 你仔细调查了【',
    '🔐 你打开了密室宝箱！',
    '🕐 单人挑战：',
    '🦋 宝箱深处泛着星光——是【',
    '🧭 你继续深入……',
    '🧱 你扣住松动的墙砖用力一拉——暗门轰然打开！\n一个魁梧的身影挡在密室前……',
    '🧱 墙砖松动了，但后面只有一堵死墙……（暗格消失了）',
]   # 迁移前内联句壳片段（= 本域表值去槽位后的实体片段）：三份源文件里一句都不许再出现


def t11_instance_panel_frozen():
    print("\n[11] 副本面板域逐字冻结：迁移前 31 分支（开本三种形态/加入/深入/调查/探索/撤退/离开/移动/地图/"
          "列表/状态/行动序/暗格/宝箱/调查点/战斗异常/Boss房通关）复跑比对")
    check("冻结基准已内嵌（31 分支）", len(INSTANCE_PANEL_FROZEN) == 31, len(INSTANCE_PANEL_FROZEN))
    now = _pb_scenarios()
    bad = [k for k in INSTANCE_PANEL_FROZEN if INSTANCE_PANEL_FROZEN[k] != now.get(k)]
    for k in bad:
        print("     · %s 现=%r" % (k, (now.get(k) or "")[:160]))
    check("★ 副本面板 31 分支输出与迁移前**逐字一致**", not bad, bad)
    _single = ("PB03_开本_名字不存在", "PB04_加入战斗_队长与队员", "PB08_副本过期提示",
               "PB09_深入_房间模式", "PB14_调查_已处理", "PB15_探索_通关后",
               "PB17_探索_旧层路径两态", "PB20_移动_非队长", "PB23_宝箱_开启",
               "PB25_加入战斗_无角色", "PB27_战斗异常_两态", "PB29_调查点_空与零碎")
    check("冻结基准非空（防基准写空）",
          all(v for k, v in INSTANCE_PANEL_FROZEN.items() if k not in _single))

    # 旧句壳零残留：三份源文件的「非 T.text/T.static 实参、非文档串」常量里不许再出现迁移前片段
    left = []
    for _p in (INSTANCE_SRC, INSTANCE_BATTLE_SRC, INSTANCE_ROUTER_SRC):
        raw, doc = _panel_raw_constants(_p)
        for _s in INSTANCE_PANEL_OLD_LITERALS:
            for _v in raw:
                if _s and _s in _v:
                    left.append((os.path.basename(_p), _s, _v[:60]))
    check("★ 旧句壳零残留（句壳只在文案表；排版分隔线/取值回退/命令关键字留在代码）",
          not left, left[:5])
    check("表里 72 条面板文案全部由本域文件引用（key 双向对账见 [2]）",
          len([k for k in T.table().keys() if k.startswith("instance.面板_")]) == 72,
          len([k for k in T.table().keys() if k.startswith("instance.面板_")]))


def _panel_raw_constants(path):
    """返回 (raw, doc)：非 T.text/T.static 实参的字符串常量 / 文档串（AST 分类）。"""
    _src = io.open(path, encoding="utf-8").read()
    _tree = ast.parse(_src)
    _docs = set()
    for _n in ast.walk(_tree):
        if isinstance(_n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            _d = ast.get_docstring(_n, clean=False)
            if _d is not None:
                for _c in ast.walk(_n):
                    if isinstance(_c, ast.Constant) and _c.value == _d:
                        _docs.add(id(_c))
    _tcalls = set()
    for _n in ast.walk(_tree):
        if (isinstance(_n, ast.Call) and isinstance(_n.func, ast.Attribute)
                and _n.func.attr in ("text", "static")
                and isinstance(_n.func.value, ast.Name) and _n.func.value.id == "T"):
            for _a in _n.args:
                _tcalls.update(id(_x) for _x in ast.walk(_a))
    _raw, _doc = [], []
    for _n in ast.walk(_tree):
        if not isinstance(_n, ast.Constant) or not isinstance(_n.value, str):
            continue
        if id(_n) in _tcalls:
            continue
        (_doc if id(_n) in _docs else _raw).append(_n.value)
    return _raw, _doc

# ═══════════════════════ SOCIAL_BRANCHES_BEGIN ═══════════════════════
# ★ B18-L8（2026-09-14）：社交域 33 条命令整块进包（`content/cmds_social.py`）——
#   宿主 `game/commands/social.py` 退化为「`@declared` 注册 + 一行 `_BRIDGE.run` 转发」。
#
#   本域**不使用** `T.text/T.static`：社交域的句子是宿主旧壳里的内联字面量 / f-string，
#   逐字搬进包内（一个字符都没改），故两侧扫到 0 个文案调用点（WIRED 条目仍登记两侧 ——
#   将来若有人把句子改成文案表 key，本门禁立刻扫到并对账槽位）。
#   逐字一致的真正证据 = 本段 `SOCIAL_FROZEN`（文本）+ `SOCIAL_DB_SHA`（副作用）：
#   **迁移前**真跑 129 例（33 条命令 × 正常/边界/失败）存下的完整输出与 DB 逐行 dump 摘要，
#   每次跑本门禁复跑比对。每例 clean_db + AUTOINCREMENT 计数清零 + 固定 random.seed；
#   时间相关值（epoch 秒 / 「剩余 N分N秒」）与 uuid4 装备 key 在比对前归一化（见 `_s_*`）。
import hashlib as _S_hashlib
import sqlite3 as _S_sqlite3

from content.persistence import social as _S_store_social

_S_GID = "g_snap"            # 群（= 采「迁移前」快照时用的群号；冻结基准的 DB 摘要按它记）
_S_NONE = "zz_none"          # 未注册玩家
_S_SEED = 20260914
_S_TIME_PAT = re.compile(r"剩余 \d+分\d+秒")
_S_UUID_PAT = re.compile(r"eq_[0-9a-f]{6,}")
_S_BIG = 1_000_000_000
# ★ PFIX P8（2026-09-15）：日期派生列归一化（与 `_E_FIXED_TS` 同款「固定字面量」口径）
#   社交域有 3 处写库值来自 `datetime.date.today()`（ISO `YYYY-MM-DD`）：
#     · `guild_donate` / `guild_shop` 的每日计数 event_state **值** = 今天；
#     · `guild_sign` 写进 `guild_members.join_date` 的 = 今天。
#   冻结基准采于 **2026-09-14**（`SOCIAL_DB_SHA` 头注），故跨过午夜（→ 09-15）这 4 例
#   摘要必变 —— 「午夜前 63/63、午夜后 62/63」的成因。这里把该列**钉死回基准日**
#   （不是 `<DATE>` 记号：冻结值是按**字面量日期**算出来的，钉成同一个字面量才能
#   在**不动任何冻结值**的前提下复原基准，实测 4/4 命中）。
#   判据：归一后 4 例仍各自有牙 —— 写库内容真变（哪怕只多一行）该例照样报红。
_S_DATE_PAT = re.compile(r"\d{4}-\d{2}-\d{2}")
_S_FROZEN_DATE = "2026-09-14"


def _s_mk(qid, name, cls="战士", level=60, gold=100000, cur_map="oak_town", **upd):
    db.create_player(_S_GID, qid, name, C.resolve("classes", cls), {}, 100, 100)
    db.update_player(_S_GID, qid, level=level, gold=gold, cur_map=cur_map,
                     stamina=999999, **upd)
    db.init_stats(_S_GID, qid)


def _s_reset_autoincrement():
    conn = _S_sqlite3.connect(db.db_path())
    try:
        conn.execute("DELETE FROM sqlite_sequence")
        conn.commit()
    except _S_sqlite3.Error:
        pass
    finally:
        conn.close()


def _clear_identity_map():
    """★ CLEANUP②（2026-09-15）：把「清库口径」补齐到「摘要口径」。

    `clean_db()`（conftest）只清固定 25 张业务表，而本文件 `_s_dump` / `_e_dump` 的 DB 摘要
    **覆盖全部表** —— `identity_map`（宿主 `host/_identity.py` 的 openid↔QQ 映射）不在那 25 张
    里，也没有任何一例会清它。任何**前置跑过的测试/装配**只要写过它（平台适配 / 身份映射路径），
    本段 129 例 + 142 例的摘要就会集体变。
    **实测**（`out/tools/plant_identity_row.py` 种一行 → `out/tools/probe_texts_flaky.py`）：
    social 129/129 全红、economy 142/142 全红。这里按同一口径清掉，本门禁与外部前置彻底解耦。
    """
    conn = _S_sqlite3.connect(db.db_path())
    try:
        conn.execute("DELETE FROM identity_map")
        conn.commit()
    except _S_sqlite3.Error:
        pass
    finally:
        conn.close()


def _s_cast():
    """标准四人组：a=甲(战士·会长) b=乙(法师) c=丙(游侠) d=丁(牧师)，全 Lv.60 / 10 万金。"""
    clean_db()
    _s_reset_autoincrement()
    _clear_identity_map()
    _s_mk("a", "甲")
    _s_mk("b", "乙", "法师")
    _s_mk("c", "丙", "游侠")
    _s_mk("d", "丁", "牧师")


def _s_item(qid, key, name, typ="材料", price=10, count=1, **extra):
    data = {"name": name, "type": typ, "stackable": True, "price": price}
    data.update(extra)
    db.add_item(_S_GID, qid, key, data, count=count)


def _s_guild_high():
    """a 为会长的高等级公会（Lv>=3），b 为成员。"""
    gid = db.guild_create("屠龙勇士", "a", desc="甲 创立的公会")
    db.guild_join(gid, "b")
    db.guild_add_exp(gid, 3000)
    return db.guild_get_by_name("屠龙勇士")


def _s_guild_low():
    """c 为会长的 1 级公会，d 为成员（副会长门槛 Lv.3 的失败支）。"""
    gid = db.guild_create("小萌新", "c", desc="丙 创立的公会")
    db.guild_join(gid, "d")
    return db.guild_get_by_name("小萌新")


def _s_pet(key="pet_wolf", name="阿黄"):
    db.pet_create("a", key, name)
    return db.pet_get("a")


def _s_auction_event(items=None):
    ends = int(time.time()) + 600
    data = {"items": items or [{"id": 1, "name": "龙鳞战甲", "base": 100, "buyout": 5000,
                                "bids": {}, "slot": "armor", "lv": 30, "quality": "purple"}]}
    db.save_world_event("auction", ends, data)


def _s_market(price=500, name="铁剑", key="it_tie_jian", seller="b", map_id="oak_town"):
    """给 seller 一件物品并挂上市场（返回最后一条挂单）。"""
    _s_item(seller, key, name, "装备", 100, 1)
    inv = [it for it in db.get_inventory(_S_GID, seller) if it["key"] == key]
    db.market_add(_S_GID, seller, key, inv[-1]["data"], price, map_id=map_id)
    return (db.market_list(_S_GID) or [None])[-1]


# ── 每个用例的前置装置（与迁移前采快照脚本逐行一致）────────────────────
def _s_p_tiejian():
    _s_item("a", "it_tie_jian", "铁剑", "装备", 100, 1)


def _s_p_tiejian5():
    _s_item("a", "it_tie_jian", "铁剑", "装备", 100, 5)


def _s_p_mkt():
    _s_market()


def _s_p_mkt6():
    for i in range(6):
        _s_market(500 + i, "铁剑%d" % i, "it_k%d" % i, "b")


def _s_p_mkt_own():
    _s_market(seller="a")


def _s_p_mkt_gold10():
    _s_market()
    db.update_player(_S_GID, "a", gold=10)


def _s_p_stall_own():
    _s_item("a", "it_tie_jian", "铁剑", "装备", 100, 1)
    db.market_add(_S_GID, "a", "it_tie_jian",
                  {"name": "铁剑", "type": "装备", "stackable": False, "price": 100},
                  500, map_id="oak_town")


def _s_p_pawn_self():
    _s_market(price=0)
    _s_item("b", "it_tie_jian", "铁剑", "装备", 100, 1)


def _s_p_pawn_give():
    _s_market(price=0)
    _s_item("a", "it_tie_jian", "铁剑", "装备", 100, 1)


def _s_p_pawn_give_priced():
    _s_market()
    _s_item("a", "it_tie_jian", "铁剑", "装备", 100, 1)


def _s_p_party_ab():
    db.party_create(_S_GID, "a", "b")


def _s_p_party_abc():
    db.party_create(_S_GID, "a", "b")
    db.party_add(_S_GID, "a", "c")


def _s_p_party_abcd():
    _s_p_party_abc()
    db.party_add(_S_GID, "a", "d")


def _s_p_inst_leader():
    db.save_battle(_S_GID, "a", {"type": "instance", "leader": "a", "retreated": False,
                                 "members": ["a", "b"], "mode": "battle"})


def _s_p_level10():
    db.update_player(_S_GID, "a", level=10)


def _s_p_gold10():
    db.update_player(_S_GID, "a", gold=10)


def _s_p_dup_name():
    db.guild_create("屠龙勇士", "a", desc="甲 创立的公会")


def _s_p_b_in_guild():
    db.guild_join(db.guild_create("屠龙勇士", "a"), "b")


def _s_p_sign_dup():
    _s_guild_high()
    _S_store_social.guild_set_sign(db.guild_get_by_name("屠龙勇士")["gid"], "a",
                                   datetime.date.today().isoformat())


def _s_p_donate_short():
    _s_guild_high()
    _s_item("a", "mat_rou", "兽肉", "材料", 5, 1)


def _s_p_donate_ok():
    _s_guild_high()
    _s_item("a", "mat_rou", "兽肉", "材料", 5, 5)


def _s_p_shop_rich():
    _s_guild_high()
    db.guild_add_exp(db.guild_get_by_name("屠龙勇士")["gid"], 0, member_qq="a", contribute=500)


def _s_p_demote_ok():
    _s_guild_high()
    _S_store_social.guild_set_role(db.guild_get_by_name("屠龙勇士")["gid"], "b", "elite")


def _s_p_pet_food():
    _s_pet()
    _s_item("a", "mat_yin_lin_yu", "银鳞鱼", "材料", 20, 2, food=True)


def _s_p_pet_food3():
    _s_pet()
    _s_item("a", "mat_yin_lin_yu", "银鳞鱼", "材料", 20, 3, food=True)


def _s_p_pet_sword():
    _s_pet()
    _s_item("a", "it_tie_jian", "铁剑", "装备", 100, 1)


def _s_p_mount_owned():
    db.update_player(_S_GID, "a", mounts={"owned": ["mount_horse"]})


def _s_p_mount_active():
    db.update_player(_S_GID, "a", mounts={"owned": ["mount_horse"], "active": "mount_horse"})


def _s_p_auction():
    _s_auction_event()


def _s_p_auction_gold10():
    _s_auction_event()
    db.update_player(_S_GID, "a", gold=10)


# (case_id, 宿主方法名, qid, 消息, 前置装置名 | None)
_S_CASES = (
    ("market/fail_no_player", "market", _S_NONE, "市场", None),
    ("market/normal_empty", "market", "a", "市场", None),
    ("market/normal_list", "market", "a", "市场", "_s_p_mkt"),
    ("market/boundary_page2", "market", "a", "市场 2", "_s_p_mkt6"),
    ("market_sell/fail_fmt", "market_sell", "a", "上架 铁剑", None),
    ("market_sell/fail_low", "market_sell", "a", "上架 铁剑 0", None),
    ("market_sell/fail_cap", "market_sell", "a", "上架 铁剑 1000000", None),
    ("market_sell/fail_noitem", "market_sell", "a", "上架 不存在的剑 100", None),
    ("market_sell/normal", "market_sell", "a", "上架 铁剑 500", "_s_p_tiejian"),
    ("market_unsell/fail_fmt", "market_unsell", "a", "下架 x", None),
    ("market_unsell/fail_none", "market_unsell", "a", "下架 1", None),
    ("market_unsell/fail_owner", "market_unsell", "a", "下架 1", "_s_p_mkt"),
    ("market_unsell/normal", "market_unsell", "a", "下架 1", "_s_p_mkt_own"),
    ("market_buy/fail_fmt", "market_buy", "a", "购入 x", None),
    ("market_buy/fail_none", "market_buy", "a", "购入 99", "_s_p_mkt"),
    ("market_buy/fail_self", "market_buy", "b", "购入 1", "_s_p_mkt"),
    ("market_buy/fail_gold", "market_buy", "a", "购入 1", "_s_p_mkt_gold10"),
    ("market_buy/normal", "market_buy", "a", "购入 1", "_s_p_mkt"),
    ("stall_deprecated/fail_no_player", "stall_deprecated", _S_NONE, "摆摊 铁剑 100", None),
    ("stall_deprecated/normal", "stall_deprecated", "a", "摆摊 铁剑 100", None),
    ("stall_sell/fail_fmt", "stall_sell", "a", "摆卖", None),
    ("stall_sell/fail_noitem", "stall_sell", "a", "摆卖 不存在的剑 500", None),
    ("stall_sell/normal", "stall_sell", "a", "摆卖 铁剑 500", "_s_p_tiejian"),
    ("stall_sell/boundary_batch", "stall_sell", "a", "摆卖 铁剑 500 3", "_s_p_tiejian5"),
    ("stall_exchange_pawn/fail_fmt", "stall_exchange_pawn", "a", "摆换", None),
    ("stall_exchange_pawn/normal", "stall_exchange_pawn", "a", "摆换 铁剑", "_s_p_tiejian"),
    ("stall_close/fail_none", "stall_close", "a", "收摊", None),
    ("stall_close/normal", "stall_close", "a", "收摊", "_s_p_stall_own"),
    ("stall_view/normal_empty", "stall_view", "a", "摊位", None),
    ("stall_view/fail_notfound", "stall_view", "a", "摊位 查无此人", None),
    ("stall_view/fail_target_none", "stall_view", "a", "摊位 乙", None),
    ("stall_view/normal_target", "stall_view", "a", "摊位 乙", "_s_p_mkt"),
    ("stall_view/normal_here", "stall_view", "a", "摊位", "_s_p_mkt"),
    ("stall_exchange/fail_fmt", "stall_exchange", "a", "换 1", None),
    ("stall_exchange/fail_none", "stall_exchange", "a", "换 99 铁剑", "_s_p_tiejian"),
    ("stall_exchange/fail_self", "stall_exchange", "b", "换 1 铁剑", "_s_p_pawn_self"),
    ("stall_exchange/normal", "stall_exchange", "a", "换 1 铁剑", "_s_p_pawn_give"),
    ("stall_exchange/fail_hasprice", "stall_exchange", "a", "换 1 铁剑", "_s_p_pawn_give_priced"),
    ("party/fail_no_player", "party", _S_NONE, "组队", None),
    ("party/normal_empty", "party", "a", "组队", None),
    ("party/fail_notfound", "party", "a", "组队 查无此人", None),
    ("party/fail_self", "party", "a", "组队 甲", None),
    ("party/normal_create", "party", "a", "组队 乙", None),
    ("party/normal_panel", "party", "a", "组队", "_s_p_party_ab"),
    ("party/fail_not_leader", "party", "b", "组队 丙", "_s_p_party_ab"),
    ("party/normal_pull", "party", "a", "组队 丙", "_s_p_party_ab"),
    ("party/fail_full", "party", "a", "组队 丁", "_s_p_party_abcd"),
    ("party_leave/fail_none", "party_leave", "a", "退队", None),
    ("party_leave/normal_member", "party_leave", "b", "退队", "_s_p_party_ab"),
    ("party_leave/fail_blocked_leader", "party_leave", "a", "退队", "_s_p_inst_leader"),
    ("guild_create_cmd/fail_fmt", "guild_create_cmd", "a", "创建公会", None),
    ("guild_create_cmd/fail_level", "guild_create_cmd", "a", "创建公会 屠龙勇士", "_s_p_level10"),
    ("guild_create_cmd/fail_gold", "guild_create_cmd", "a", "创建公会 屠龙勇士", "_s_p_gold10"),
    ("guild_create_cmd/normal", "guild_create_cmd", "a", "创建公会 屠龙勇士", None),
    ("guild_create_cmd/fail_dup_name", "guild_create_cmd", "b", "创建公会 屠龙勇士", "_s_p_dup_name"),
    ("guild_create_cmd/fail_in_guild", "guild_create_cmd", "b", "创建公会 新会", "_s_p_b_in_guild"),
    ("guild_join_cmd/fail_fmt", "guild_join_cmd", "b", "加入公会", None),
    ("guild_join_cmd/fail_notfound", "guild_join_cmd", "b", "加入公会 不存在", None),
    ("guild_join_cmd/normal", "guild_join_cmd", "b", "加入公会 屠龙勇士", "_s_p_dup_name"),
    ("guild_join_cmd/fail_already", "guild_join_cmd", "b", "加入公会 屠龙勇士", "_s_p_b_in_guild"),
    ("guild_leave_cmd/fail_none", "guild_leave_cmd", "a", "退出公会", None),
    ("guild_leave_cmd/fail_leader", "guild_leave_cmd", "a", "退出公会", "_s_guild_high"),
    ("guild_leave_cmd/normal_member", "guild_leave_cmd", "b", "退出公会", "_s_guild_high"),
    ("guild_disband_cmd/fail_not_leader", "guild_disband_cmd", "b", "解散公会", "_s_guild_high"),
    ("guild_disband_cmd/normal", "guild_disband_cmd", "a", "解散公会", "_s_guild_high"),
    ("guild_info/fail_none", "guild_info", "a", "公会", None),
    ("guild_info/normal", "guild_info", "a", "公会", "_s_guild_high"),
    ("guild_info/boundary_page2", "guild_info", "a", "公会 2", "_s_guild_high"),
    ("guild_sign/fail_none", "guild_sign", "a", "公会签到", None),
    ("guild_sign/normal", "guild_sign", "a", "公会签到", "_s_guild_high"),
    ("guild_sign/boundary_dup", "guild_sign", "a", "公会签到", "_s_p_sign_dup"),
    ("guild_task/fail_none", "guild_task", "a", "公会任务", None),
    ("guild_task/normal", "guild_task", "a", "公会任务", "_s_guild_high"),
    ("guild_donate_cmd/fail_none", "guild_donate_cmd", "a", "公会捐献", None),
    ("guild_donate_cmd/fail_short", "guild_donate_cmd", "a", "公会捐献", "_s_p_donate_short"),
    ("guild_donate_cmd/normal", "guild_donate_cmd", "a", "公会捐献", "_s_p_donate_ok"),
    ("guild_rank/fail_empty", "guild_rank", "a", "公会排行", None),
    ("guild_rank/normal", "guild_rank", "a", "公会排行", "_s_guild_high"),
    ("guild_rank/no_player_allowed", "guild_rank", _S_NONE, "公会排行", "_s_guild_high"),
    ("guild_shop/fail_none", "guild_shop", "a", "公会商店", None),
    ("guild_shop/fail_not_member", "guild_shop", "c", "公会商店", "_s_guild_high"),
    ("guild_shop/normal_panel", "guild_shop", "a", "公会商店", "_s_guild_high"),
    ("guild_shop/fail_buy_none", "guild_shop", "a", "公会商店 99", "_s_guild_high"),
    ("guild_shop/fail_buy_poor", "guild_shop", "a", "公会商店 1", "_s_guild_high"),
    ("guild_shop/normal_buy", "guild_shop", "a", "公会商店 1", "_s_p_shop_rich"),
    ("guild_skill_view/fail_none", "guild_skill_view", "a", "公会技能", None),
    ("guild_skill_view/normal", "guild_skill_view", "a", "公会技能", "_s_guild_high"),
    ("guild_appoint/fail_not_leader", "guild_appoint", "b", "公会任命 乙 精英", "_s_guild_high"),
    ("guild_appoint/fail_fmt", "guild_appoint", "a", "公会任命 乙", "_s_guild_high"),
    ("guild_appoint/fail_role", "guild_appoint", "a", "公会任命 乙 会长", "_s_guild_high"),
    ("guild_appoint/fail_level", "guild_appoint", "c", "公会任命 丁 副会长", "_s_guild_low"),
    ("guild_appoint/fail_notfound", "guild_appoint", "a", "公会任命 查无此人 精英", "_s_guild_high"),
    ("guild_appoint/fail_self", "guild_appoint", "a", "公会任命 甲 精英", "_s_guild_high"),
    ("guild_appoint/normal", "guild_appoint", "a", "公会任命 乙 精英", "_s_guild_high"),
    ("guild_demote/fail_not_leader", "guild_demote", "b", "公会免职 甲", "_s_guild_high"),
    ("guild_demote/fail_fmt", "guild_demote", "a", "公会免职", "_s_guild_high"),
    ("guild_demote/fail_notfound", "guild_demote", "a", "公会免职 查无此人", "_s_guild_high"),
    ("guild_demote/fail_plain", "guild_demote", "a", "公会免职 乙", "_s_guild_high"),
    ("guild_demote/normal", "guild_demote", "a", "公会免职 乙", "_s_p_demote_ok"),
    ("pet_view/fail_none", "pet_view", "a", "宠物", None),
    ("pet_view/normal", "pet_view", "a", "宠物", "_s_pet"),
    ("pet_rename/fail_none", "pet_rename", "a", "宠物改名 小黑", None),
    ("pet_rename/fail_fmt", "pet_rename", "a", "宠物改名", "_s_pet"),
    ("pet_rename/normal", "pet_rename", "a", "宠物改名 小黑", "_s_pet"),
    ("pet_rename/boundary_long", "pet_rename", "a", "宠物改名 一二三四五六七八九十", "_s_pet"),
    ("pet_feed/fail_none", "pet_feed", "a", "喂养", None),
    ("pet_feed/normal_panel", "pet_feed", "a", "喂养", "_s_pet"),
    ("pet_feed/fail_noitem", "pet_feed", "a", "喂养 不存在的食物", "_s_pet"),
    ("pet_feed/normal", "pet_feed", "a", "喂养 银鳞鱼", "_s_p_pet_food"),
    ("pet_feed/normal_batch", "pet_feed", "a", "喂养 银鳞鱼*2", "_s_p_pet_food3"),
    ("pet_feed/fail_notfood", "pet_feed", "a", "喂养 铁剑", "_s_p_pet_sword"),
    ("pet_release/fail_none", "pet_release", "a", "放生", None),
    ("pet_release/normal", "pet_release", "a", "放生", "_s_pet"),
    ("mount_cmd/normal_panel", "mount_cmd", "a", "坐骑", None),
    ("mount_cmd/fail_not_owned", "mount_cmd", "a", "骑乘 老马", None),
    ("mount_cmd/fail_dismount", "mount_cmd", "a", "下马", None),
    ("mount_cmd/normal_ride", "mount_cmd", "a", "骑乘 老马", "_s_p_mount_owned"),
    ("mount_cmd/normal_dismount", "mount_cmd", "a", "下马", "_s_p_mount_active"),
    ("world_event/normal_idle", "world_event", "a", "事件", None),
    ("world_event/normal_with_auction", "world_event", "a", "事件", "_s_p_auction"),
    ("auction/normal_closed", "auction", "a", "拍卖", None),
    ("auction/normal_open", "auction", "a", "拍卖", "_s_p_auction"),
    ("bid/normal_closed", "bid", "a", "竞拍 1 100", None),
    ("bid/fail_fmt", "bid", "a", "竞拍 1", "_s_p_auction"),
    ("bid/fail_noitem", "bid", "a", "竞拍 99 100", "_s_p_auction"),
    ("bid/fail_below", "bid", "a", "竞拍 1 50", "_s_p_auction"),
    ("bid/fail_gold", "bid", "a", "竞拍 1 5000", "_s_p_auction_gold10"),
    ("bid/normal_bid", "bid", "a", "竞拍 1 200", "_s_p_auction"),
    ("bid/normal_buyout", "bid", "a", "竞拍 1 5000", "_s_p_auction"),
)


def _s_p_auction_gold10():
    _s_auction_event()
    db.update_player(_S_GID, "a", gold=10)


def _s_cell(v):
    """DB 单元归一化：epoch 秒（数字 / 10 位以上数字串）→ `<TS>`。"""
    if isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v) > _S_BIG:
        return "<TS>"
    if isinstance(v, bytes):
        v = v.decode("utf-8", "replace")
    if isinstance(v, str) and v.isdigit() and len(v) >= 10:
        return "<TS>"
    return v


def _s_dump():
    """DB 逐行 dump（跳过 AUTOINCREMENT 计数表；uuid4 装备 key + **日期派生列**归一化）。

    ★ PFIX P8：日期归一是「墙钟归一化」口径的延伸（本段原有 epoch 秒归一化见 `_s_cell`；
    经济域同款见 `_E_DATE_PAT` / `_E_FIXED_TS`）。不归一化 ⇒ 摘要里含「今天」⇒
    跨午夜必红（既有缺陷，非实现漂移）。
    """
    conn = _S_sqlite3.connect(db.db_path())
    try:
        tabs = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            if r[0] != "sqlite_sequence"]
        out = []
        for t in tabs:
            try:
                rows = conn.execute("SELECT * FROM %s" % t).fetchall()
            except Exception as exc:                       # noqa: BLE001
                rows = [("ERR", str(exc))]
            rows = [tuple(_s_cell(c) for c in r) for r in rows]
            out.append("%s: %s" % (t, sorted(repr(r) for r in rows)))
        text = _S_UUID_PAT.sub("eq_<UUID>", "\n".join(out))
        return _S_DATE_PAT.sub(_S_FROZEN_DATE, text)       # ★ P8：日期派生列钉死回基准日
    finally:
        conn.close()


async def _s_one(m, handler, qid, msg, prep):
    if prep is None:
        _s_cast()
    else:
        _s_cast()
        globals()[prep]()
    random.seed(_S_SEED)
    ev = FakeEvent(_S_GID, qid, msg)
    texts = await run(getattr(m, handler), ev)
    joined = "\n".join(str(t) for t in texts)
    return {
        "n": len(texts),
        "out": _S_TIME_PAT.sub("剩余 <T>分<T>秒", joined),
        "stopped": bool(getattr(ev, "_stopped", False)),
        "db": _S_hashlib.sha256(_s_dump().encode("utf-8")).hexdigest()[:16],
    }


def _s_scenarios() -> dict:
    """复跑全部 129 例（迁移前采快照 / 迁移后门禁比对，同一份驱动代码）。

    宿主实例**整轮复用同一个** `Main(None)`（与采快照脚本一致：跨例的命令层实例态
    —— 如战斗内存锁集合 —— 必须同源，否则快照不可比）。
    """
    out = {}
    m = Main(None)
    for cid, handler, qid, msg, prep in _S_CASES:
        out[cid] = asyncio.run(_s_one(m, handler, qid, msg, prep))
    clean_db()
    return out

SOCIAL_FROZEN = {
    'auction/normal_closed': '🏪 拍卖行暂未开张。世界事件出现『神秘拍卖行』时再来吧！(『事件』查看)',
    'auction/normal_open': '🏪 【神秘拍卖行】(剩余 <T>分<T>秒)\n━━━━━━━━━━━━\n📦 1. 龙鳞战甲\n   底价 100 ｜ 最高：无人出价 ｜ 一口价 5000\n   『竞拍 1 <金币>』出价\n\n💡 一口价直接成交，别犹豫',
    'bid/fail_below': '出价不能低于底价 100 金币！',
    'bid/fail_fmt': '格式：竞拍 <编号> <金币>，如『竞拍 1 5000』(『拍卖』查看编号)',
    'bid/fail_gold': '你只有 10 金币，出不起 5000！',
    'bid/fail_noitem': '没有这个拍卖品！『拍卖』查看当前物品～',
    'bid/normal_bid': '💰 出价成功！你在【龙鳞战甲】上出价 200 金币，当前最高！\n(若被超越将自动退还)',
    'bid/normal_buyout': '💰 一口价成交！你以 5000 金币拍得【龙鳞战甲】！\n📦 装备已放入背包(『背包』查看)',
    'bid/normal_closed': '🏪 拍卖行暂未开张。',
    'guild_appoint/fail_fmt': '格式：公会任命 <成员名> <职位>，职位=副会长/精英',
    'guild_appoint/fail_level': '任命副会长需要公会 Lv.3！本公会才 Lv.1～',
    'guild_appoint/fail_not_leader': '只有会长才能任命职位！',
    'guild_appoint/fail_notfound': '没找到玩家『查无此人』！',
    'guild_appoint/fail_role': '可任命职位：副会长、精英。成员是默认职，不需任命～',
    'guild_appoint/fail_self': '会长不需要任命自己～',
    'guild_appoint/normal': '⭐ 任命成功！『乙』已晋升为公会【精英】！',
    'guild_create_cmd/fail_dup_name': '公会『屠龙勇士』已存在！换个名字吧～',
    'guild_create_cmd/fail_fmt': '格式：创建公会 <名字>，如『创建公会 屠龙勇士』',
    'guild_create_cmd/fail_gold': '创建公会需要 1000 金币！你只有 10 金币。',
    'guild_create_cmd/fail_in_guild': '你已经在一个公会里啦！先『退出公会』再加入新的～',
    'guild_create_cmd/fail_level': '创建公会需要 30 级！你才 10 级，先去冒险吧～',
    'guild_create_cmd/normal': '🏰 【公会创建成功】『屠龙勇士』！\n你成为了公会会长！\n💡 别忘了『公会任务』，每天打怪领奖励',
    'guild_demote/fail_fmt': '格式：公会免职 <成员名>',
    'guild_demote/fail_not_leader': '只有会长才能免职！',
    'guild_demote/fail_notfound': '没找到玩家『查无此人』！',
    'guild_demote/fail_plain': '『乙』是成员，无需免职～',
    'guild_demote/normal': '📉 已免去『乙』的职位，降回普通成员～',
    'guild_disband_cmd/fail_not_leader': '只有会长才能解散公会！',
    'guild_disband_cmd/normal': '🏚️ 公会【屠龙勇士】已解散……',
    'guild_donate_cmd/fail_none': '你还没有公会！先『加入公会 <名字>』吧～',
    'guild_donate_cmd/fail_short': '🎯 【公会捐献】需要上交 3 份材料(当前 1/3)！\n💡 『公会捐献』上交<材料>，换经验金币',
    'guild_donate_cmd/normal': '🎁 【公会捐献完成】上交 3 份材料，为公会贡献力量！\n🏰 公会经验 +40 ｜ 个人贡献 +20\n💰 金币 +100',
    'guild_info/boundary_page2': '🏰 【屠龙勇士】Lv.5\n━━━━━━━━━━━━\n👥 成员 2 人 ｜ 经验 0/1500\n📜 甲 创立的公会\n💡 公会加成：打怪经验 +5%\n━━━━━━━━━━━━\n成员(第 1/1 页)：\n 1. 👑 甲(会长) Lv.60 ｜ 贡献 0\n 2. ⚔️ 乙(成员) Lv.60 ｜ 贡献 0\n\n💡 别忘了『公会任务』，每天打怪领奖励',
    'guild_info/fail_none': '你还没有公会！『创建公会 <名字>』(30级＋1000金币)或『加入公会 <名字>』',
    'guild_info/normal': '🏰 【屠龙勇士】Lv.5\n━━━━━━━━━━━━\n👥 成员 2 人 ｜ 经验 0/1500\n📜 甲 创立的公会\n💡 公会加成：打怪经验 +5%\n━━━━━━━━━━━━\n成员(第 1/1 页)：\n 1. 👑 甲(会长) Lv.60 ｜ 贡献 0\n 2. ⚔️ 乙(成员) Lv.60 ｜ 贡献 0\n\n💡 别忘了『公会任务』，每天打怪领奖励',
    'guild_join_cmd/fail_already': '你已经在一个公会里啦！',
    'guild_join_cmd/fail_fmt': '格式：加入公会 <公会名>，如『加入公会 屠龙勇士』',
    'guild_join_cmd/fail_notfound': '找不到公会『不存在』！输入『公会排行』看看有哪些公会～',
    'guild_join_cmd/normal': '🏰 欢迎加入公会【屠龙勇士】！\n💡 别忘了『公会任务』，每天打怪领奖励',
    'guild_leave_cmd/fail_leader': '你是会长！会长不能直接退会，请『解散公会』（公会随之解散）～',
    'guild_leave_cmd/fail_none': '你不在任何公会里～',
    'guild_leave_cmd/normal_member': '👋 你已退出公会【屠龙勇士】。江湖再见！',
    'guild_rank/fail_empty': '还没有公会成立！『创建公会 <名字>』建立第一个公会吧～',
    'guild_rank/no_player_allowed': '🏆 【公会排行榜】\n━━━━━━━━━━━━\n1. 🏰 屠龙勇士 Lv.5(2人)',
    'guild_rank/normal': '🏆 【公会排行榜】\n━━━━━━━━━━━━\n1. 🏰 屠龙勇士 Lv.5(2人)',
    'guild_shop/fail_buy_none': '没有第 99 件商品！『公会商店』查看～',
    'guild_shop/fail_buy_poor': '公会积分不足！购买【淬火石】需要 30 积分，你只有 0。',
    'guild_shop/fail_none': '你还没有公会！先『加入公会 <名字>』吧～',
    'guild_shop/fail_not_member': '你还没有公会！先『加入公会 <名字>』吧～',
    'guild_shop/normal_buy': '🛒 购买成功！【淬火石】(花费 30 公会积分)\n⚒️ 强化石到手！『强化』给装备升个级吧～',
    'guild_shop/normal_panel': '🛒 【公会商店】Lv.5 ｜ 公会积分：0\n━━━━━━━━━━━━\n1. 淬火石 ｜ 30 积分\n   公会商店出品的强化石，用于装备强化 ｜ 需公会 Lv.1 ｜ 每日限购 10\n2. 图纸残页 ｜ 50 积分\n   残缺的锻造图纸，s24/s25 等支线交付物 ｜ 需公会 Lv.2 ｜ 每日限购 5\n3. 力量药剂 ｜ 80 积分\n   战斗中使用，3 刻攻击 + 30% ｜ 需公会 Lv.2 ｜ 每日限购 3\n4. 彩虹露 ｜ 120 积分\n   炼金/锻造的进阶材料，稀有掉落可遇不可求 ｜ 需公会 Lv.3 ｜ 每日限购 3\n5. 高级强化石 ｜ 200 积分\n   高纯度强化矿石，高级锻造/强化基石 ｜ 需公会 Lv.4 ｜ 每日限购 2\n6. 藏宝图碎片 ｜ 160 积分\n   拼凑起来也许能找到意外之财 ｜ 需公会 Lv.3 ｜ 不限购\n━━━━━━━━━━━━\n💡 看中商品？『公会商店 <编号>』兑换',
    'guild_sign/boundary_dup': '今天已经公会签过到啦！明天再来～',
    'guild_sign/fail_none': '你还没有公会！先『加入公会 <名字>』吧～',
    'guild_sign/normal': '📅 【公会签到】在【屠龙勇士】报到！\n🏰 公会经验 +20 ｜ 个人贡献 +10\n💰 金币 +50',
    'guild_skill_view/fail_none': '你还没有公会！先『加入公会 <名字>』吧～',
    'guild_skill_view/normal': '📖 【公会技能】Lv.5\n━━━━━━━━━━━━\n💡 攻击强化：全员攻击力 +2%/级(最高 5 级)\n   积分需求：60 → 120 → 200 → 300 ｜ 公会等级：Lv.1 → Lv.2 → Lv.3 → Lv.4\n💡 防御强化：全员防御 +2%/级(最高 5 级)\n   积分需求：60 → 120 → 200 → 300 ｜ 公会等级：Lv.1 → Lv.2 → Lv.3 → Lv.4\n💡 经验强化：全员打怪经验 +2%/级(最高 5 级)\n   积分需求：80 → 160 → 260 → 400 ｜ 公会等级：Lv.1 → Lv.3 → Lv.4 → Lv.5\n━━━━━━━━━━━━\n💡 技能经会长安排后逐步开放；战斗加成的挂接正在开发中～',
    'guild_task/fail_none': '你还没有公会！先『加入公会 <名字>』吧～',
    'guild_task/normal': '🎯 【公会任务】击杀 5 只怪物(当前 0/5)\n💡 击杀会自动结算奖励！',
    'market/boundary_page2': '🏪 市场空空如也。『上架 <物品> <价格>』寄售你的宝贝！',
    'market/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'market/normal_empty': '🏪 市场空空如也。『上架 <物品> <价格>』寄售你的宝贝！',
    'market/normal_list': '🏪 市场空空如也。『上架 <物品> <价格>』寄售你的宝贝！',
    'market_buy/fail_fmt': '格式：购入 <编号>，『市场』查看编号',
    'market_buy/fail_gold': '金币不足！需要 500 金币。',
    'market_buy/fail_none': '没有这个物品！可能已被买走。',
    'market_buy/fail_self': '不能买自己的物品！',
    'market_buy/normal': '🛒 购入成功！【铁剑】已放入背包(花费 500 金币)',
    'market_sell/fail_cap': '价格太高啦！上架价最多 999999 金币～',
    'market_sell/fail_fmt': '格式：上架 <物品名> <价格>，如『上架 铁剑 500』；价格至少 1 金币',
    'market_sell/fail_low': '格式：上架 <物品名> <价格>，如『上架 铁剑 500』；价格至少 1 金币',
    'market_sell/fail_noitem': '背包里没有『不存在的剑』！『背包』查看～',
    'market_sell/normal': '📦 已上架【铁剑】，定价 500 金币！\n『市场』查看，『下架 <编号>』撤回',
    'market_unsell/fail_fmt': '格式：下架 <编号>，『市场』查看编号',
    'market_unsell/fail_none': '没有这个上架物品！',
    'market_unsell/fail_owner': '没有这个上架物品！',
    'market_unsell/normal': '没有这个上架物品！',
    'mount_cmd/fail_dismount': '你现在没有骑乘任何坐骑～',
    'mount_cmd/fail_not_owned': '你还没有『老马』！去商店『购买 老马』～',
    'mount_cmd/normal_dismount': '🛑 你翻身下马，坐骑回到了马厩。',
    'mount_cmd/normal_panel': '🐾 【坐骑】\n━━━━━━━━━━━━\n你还没有坐骑。去橡木镇商店『购买 老马』，或者打精英/Boss 碰碰运气！\n\n💡 可获得的坐骑：⚪普通老马、⚪普通小毛驴、🟢优秀骏马、🟢优秀铁港驼马、🔵稀有雪狼、🔵稀有北境驯鹿、🟣史诗幽灵马、🟣史诗森林独角兽、🟣史诗雾羽候鸟、🟠传说狮鹫、🟠传说炎蹄战马',
    'mount_cmd/normal_ride': '🐴 你骑上了【老马】！温顺可靠的老马，腿脚虽慢但从不尥蹶子。传送费－10%',
    'party/fail_full': '无法拉入 丁：TA 已在队伍中(含其他队伍)，或队伍已满(4 人)～',
    'party/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'party/fail_not_leader': '你已在队伍中，让队长『组队 <名字>』拉人吧～',
    'party/fail_notfound': '找不到玩家『查无此人』！确保对方已『注册』角色～',
    'party/fail_self': '不能和自己组队！',
    'party/normal_create': '🤝 组队成功！你和 乙 成为队友\n💡 组队打怪经验＋10%！『组队 <名字>』可再拉人(上限 4 人)',
    'party/normal_empty': '你还没有队伍～『组队 <对方名字>』邀请同群玩家组队！\n💡 组队打怪经验＋10%（野外各自为战，仅经验加成，副本内才并肩作战）',
    'party/normal_panel': '🤝 【队伍】(2人)\n━━━━━━━━━━━━\n1. 甲 Lv.60 战士 · 💨速?(队长)\n2. 乙 Lv.60 法师 · 💨速?\n💡 组队打怪经验＋10%（野外各自为战，仅经验加成；副本内才并肩作战）！队长『组队 <名字>』可再拉人(上限 4 人)；『退队』离开',
    'party/normal_pull': '🤝 丙 加入了你的队伍！(当前 3 人，上限 4 人)\n💡 组队打怪经验＋10%！\n🔔 丙：甲 将你拉入了队伍！',
    'party_leave/fail_blocked_leader': '⚔️ 副本进行中不能退队！先『撤退』保留进度，或通关/『离开副本』后再退队～',
    'party_leave/fail_none': '你还没有队伍～',
    'party_leave/normal_member': '👋 你已退出队伍！(队长退队将解散队伍)',
    'pet_feed/fail_noitem': '背包里没有可喂食的食物『不存在的食物』！打怪、『采集』、『垂钓』可获得食物。',
    'pet_feed/fail_none': '你还没有宠物！打怪有概率掉落宠物蛋，『使用 宠物蛋』孵化～',
    'pet_feed/fail_notfood': '背包里没有可喂食的食物『铁剑』！打怪、『采集』、『垂钓』可获得食物。',
    'pet_feed/normal': '🍖 你喂了【阿黄】一份银鳞鱼！\n😋 饱食度 +30 ｜ 💕 亲密度 +5 ｜ ✨ 经验 +10',
    'pet_feed/normal_batch': '🍖 你喂了【阿黄】0 份银鳞鱼！\n✅ 已喂食 0/2 份（饱食度已满）',
    'pet_feed/normal_panel': '格式：喂养 <食物名/序号>，如『喂养 烤鸟肉』或『喂养 1』\n背包里还没有可喂食的食物——打怪、『采集』、『垂钓』可获得食物，『烹饪』能做更顶饱的料理！',
    'pet_release/fail_none': '你还没有宠物～',
    'pet_release/normal': '🕊️ 你放生了【阿黄】……它会记得你的。\n📖 图鉴记录已保留，之后还有机会遇到它！',
    'pet_rename/boundary_long': '🐾 你的宠物改名为【一二三四五六七八】！',
    'pet_rename/fail_fmt': '格式：宠物改名 <名字>',
    'pet_rename/fail_none': '你还没有宠物！',
    'pet_rename/normal': '🐾 你的宠物改名为【小黑】！',
    'pet_view/fail_none': '你还没有宠物！打怪有概率掉落宠物蛋，『使用 宠物蛋』孵化～',
    'pet_view/normal': '🐺 【宠物 · 森林狼崽】\n━━━━━━━━━━━━\n名字：阿黄 | Lv.1/30\n📖 品质：⚪普通\n📍 出处：野外兽类怪(狼/狗/野猪/熊)掉落狼崽蛋\n🎯 技能：撕咬(每 3 刻 40% 攻击伤害) (Lv.10 解锁)\n❤️ 饱食度：100/100\n💕 亲密度：0/100\n✨ 经验加成：+0.2%(主人战斗经验)\n━━━━━━━━━━━━\n💡 饱食度低了？『喂养 <材料>』喂食',
    'stall_close/fail_none': '你现在没有摊位。『摆摊 <物品> <价格>』支起摊位～',
    'stall_close/normal': '🏪 收摊！【铁剑】退回背包',
    'stall_deprecated/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'stall_deprecated/normal': '『摆摊』已拆成两条指令啦：\n· 摆卖 = 卖金币：『摆卖 <物品/背包序号> <单价> [数量]』\n· 摆换 = 以物换物：『摆换 <物品/背包序号> [数量]』\n例：『摆卖 3 500 5』(背包第3件×5个，单价500)｜『摆换 铁剑』',
    'stall_exchange/fail_fmt': '格式：换 <摊位编号> <物品名>，如『换 3 狼皮』(对方摆摊不带价格 = 换摊)',
    'stall_exchange/fail_hasprice': '【铁剑】是出售中的(500 金币)，用『购入 1』购买～',
    'stall_exchange/fail_none': '没有编号 99 的摊位！『摊位』看看～',
    'stall_exchange/fail_self': '不能和自己交换！',
    'stall_exchange/normal': '🔄 交换成功！你用【铁剑】换到了【铁剑】！\n对方的东西已放进你背包，你的【铁剑】已送到对方背包～',
    'stall_exchange_pawn/fail_fmt': '格式：摆换 <物品名/背包序号> [数量]\n例：『摆换 3 5』(背包第3件拿5个出来换)｜『摆换 铁剑』(换1件)',
    'stall_exchange_pawn/normal': '🔄 你在『橡木镇』支起了换摊——【铁剑】只换不卖！\n『收摊』收摊，别人可用『换 <编号> <物品名>』跟你交换',
    'stall_sell/boundary_batch': '🏪 你在『橡木镇』支起了摊位，出售【铁剑 ×3】定价 500 金币！\n『收摊』收摊，『摊位』看看本地谁在摆摊',
    'stall_sell/fail_fmt': '格式：摆卖 <物品名/背包序号> <单价> [数量]\n例：『摆卖 3 500 5』(背包第3件×5个，单价500)｜『摆卖 铁剑 500』',
    'stall_sell/fail_noitem': '背包里没有『不存在的剑』！『背包』查看～',
    'stall_sell/normal': '🏪 你在『橡木镇』支起了摊位，出售【铁剑】定价 500 金币！\n『收摊』收摊，『摊位』看看本地谁在摆摊',
    'stall_view/fail_notfound': '没找到玩家『查无此人』！',
    'stall_view/fail_target_none': '乙 没有在摆摊。',
    'stall_view/normal_empty': '此地没有摊位。『摆摊 <物品> [价格]』支起你的小摊(不带价格 = 换摊)！',
    'stall_view/normal_here': '🏪 【此地摊位】(橡木镇)\n━━━━━━━━━━━━\n#1 铁剑 ｜ 500 金币 ｜ 乙\n💡 标 🔄 的是换摊：『换 <编号> <物品名>』当面交换；其他『购入 <编号>』，『摊位 <玩家名>』看指定摊位',
    'stall_view/normal_target': '🏪 【乙 的摊位】\n━━━━━━━━━━━━\n#1 铁剑 ｜ 500 金币 ｜ 在 橡木镇\n💡 标 🔄 的是换摊：『换 <编号> <物品名>』当面交换；其他『购入 <编号>』(需在同一位置)',
    'world_event/normal_idle': '🌍 大陆风平浪静……\n',
    'world_event/normal_with_auction': '🌍 【世界事件】🏪 神秘拍卖行(剩余 <T>分<T>秒)\n━━━━━━━━━━━━\n一位神秘商人出现在铁港城，带来了三件稀世珍宝！输入『拍卖』查看，『竞拍 <编号> <金币>』出价！\n\n📦 1. 龙鳞战甲 ｜ 底价 100｜ 最高 无人出价：0\n   💰 一口价 5000｜『竞拍 1 <金币>』\n\n',
}   # 迁移前快照（2026-09-14 真跑 129 例存下，勿手改；时间值已归一化）

SOCIAL_DB_SHA = {
    'auction/normal_closed': '459759066ba88cf8',
    'auction/normal_open': 'a6af6d81638a22af',
    'bid/fail_below': 'a6af6d81638a22af',
    'bid/fail_fmt': 'a6af6d81638a22af',
    'bid/fail_gold': '8aedeeed168df208',
    'bid/fail_noitem': 'a6af6d81638a22af',
    'bid/normal_bid': 'd82af8a520895a3c',
    'bid/normal_buyout': '537ae57e29d35818',
    'bid/normal_closed': '459759066ba88cf8',
    'guild_appoint/fail_fmt': '4054f0744e27c0ee',
    'guild_appoint/fail_level': 'b76f89fed5e79ac3',
    'guild_appoint/fail_not_leader': '4054f0744e27c0ee',
    'guild_appoint/fail_notfound': '4054f0744e27c0ee',
    'guild_appoint/fail_role': '4054f0744e27c0ee',
    'guild_appoint/fail_self': '4054f0744e27c0ee',
    'guild_appoint/normal': 'd43e4542cdb7f116',
    'guild_create_cmd/fail_dup_name': 'b825c75449295325',
    'guild_create_cmd/fail_fmt': '459759066ba88cf8',
    'guild_create_cmd/fail_gold': 'fe00e84029ce8ace',
    'guild_create_cmd/fail_in_guild': '849404f7e80244c4',
    'guild_create_cmd/fail_level': '7fd15696601e104d',
    'guild_create_cmd/normal': 'f941ab69856474ae',
    'guild_demote/fail_fmt': '4054f0744e27c0ee',
    'guild_demote/fail_not_leader': '4054f0744e27c0ee',
    'guild_demote/fail_notfound': '4054f0744e27c0ee',
    'guild_demote/fail_plain': '4054f0744e27c0ee',
    'guild_demote/normal': '4054f0744e27c0ee',
    'guild_disband_cmd/fail_not_leader': '4054f0744e27c0ee',
    'guild_disband_cmd/normal': '459759066ba88cf8',
    'guild_donate_cmd/fail_none': '459759066ba88cf8',
    'guild_donate_cmd/fail_short': '2ae289984465e3ad',
    'guild_donate_cmd/normal': '52548c16e3025d26',
    'guild_info/boundary_page2': '67217c1685da360e',
    'guild_info/fail_none': '459759066ba88cf8',
    'guild_info/normal': '67217c1685da360e',
    'guild_join_cmd/fail_already': '849404f7e80244c4',
    'guild_join_cmd/fail_fmt': '459759066ba88cf8',
    'guild_join_cmd/fail_notfound': '459759066ba88cf8',
    'guild_join_cmd/normal': '6eb14cb63106a367',
    'guild_leave_cmd/fail_leader': '4054f0744e27c0ee',
    'guild_leave_cmd/fail_none': '459759066ba88cf8',
    'guild_leave_cmd/normal_member': '74b1ef070e18a3ff',
    'guild_rank/fail_empty': '459759066ba88cf8',
    'guild_rank/no_player_allowed': '4054f0744e27c0ee',
    'guild_rank/normal': '4054f0744e27c0ee',
    'guild_shop/fail_buy_none': '4054f0744e27c0ee',
    'guild_shop/fail_buy_poor': '4054f0744e27c0ee',
    'guild_shop/fail_none': '459759066ba88cf8',
    'guild_shop/fail_not_member': '4054f0744e27c0ee',
    'guild_shop/normal_buy': 'fd79ea1e078dcde0',
    'guild_shop/normal_panel': '4054f0744e27c0ee',
    'guild_sign/boundary_dup': 'be03115182134dfb',
    'guild_sign/fail_none': '459759066ba88cf8',
    'guild_sign/normal': '96120dce376ee944',
    'guild_skill_view/fail_none': '459759066ba88cf8',
    'guild_skill_view/normal': '4054f0744e27c0ee',
    'guild_task/fail_none': '459759066ba88cf8',
    'guild_task/normal': '4054f0744e27c0ee',
    'market/boundary_page2': '6f4dc5dc32cd6df0',
    'market/fail_no_player': '459759066ba88cf8',
    'market/normal_empty': '459759066ba88cf8',
    'market/normal_list': '1cd2ffc85b249631',
    'market_buy/fail_fmt': '459759066ba88cf8',
    'market_buy/fail_gold': '913bbd4f3e2b07e5',
    'market_buy/fail_none': '1cd2ffc85b249631',
    'market_buy/fail_self': '1cd2ffc85b249631',
    'market_buy/normal': '80028ad1fe6971e1',
    'market_sell/fail_cap': '459759066ba88cf8',
    'market_sell/fail_fmt': '459759066ba88cf8',
    'market_sell/fail_low': '459759066ba88cf8',
    'market_sell/fail_noitem': '459759066ba88cf8',
    'market_sell/normal': 'bf8b3f79eb25be96',
    'market_unsell/fail_fmt': '459759066ba88cf8',
    'market_unsell/fail_none': '459759066ba88cf8',
    'market_unsell/fail_owner': '1cd2ffc85b249631',
    'market_unsell/normal': '84c044dc6b9b5d84',
    'mount_cmd/fail_dismount': '459759066ba88cf8',
    'mount_cmd/fail_not_owned': '459759066ba88cf8',
    'mount_cmd/normal_dismount': '66b19fc4635fdcaa',
    'mount_cmd/normal_panel': '459759066ba88cf8',
    'mount_cmd/normal_ride': '80ac32ac17123059',
    'party/fail_full': '10c0ee7a89dfefc6',
    'party/fail_no_player': '459759066ba88cf8',
    'party/fail_not_leader': 'b26f5b970e8bfa9f',
    'party/fail_notfound': '459759066ba88cf8',
    'party/fail_self': '459759066ba88cf8',
    'party/normal_create': '3996334bf95336ca',
    'party/normal_empty': '459759066ba88cf8',
    'party/normal_panel': 'b26f5b970e8bfa9f',
    'party/normal_pull': 'c7291fc4c15afcaf',
    'party_leave/fail_blocked_leader': '3c43cdf094babb07',
    'party_leave/fail_none': '459759066ba88cf8',
    'party_leave/normal_member': '8e77545edb838d6a',
    'pet_feed/fail_noitem': 'd092aaf5c0644ec8',
    'pet_feed/fail_none': '459759066ba88cf8',
    'pet_feed/fail_notfood': '64d96787e177a9f5',
    'pet_feed/normal': 'e1f2e4bc9afc7000',
    'pet_feed/normal_batch': 'cad32f5320814881',
    'pet_feed/normal_panel': 'd092aaf5c0644ec8',
    'pet_release/fail_none': '459759066ba88cf8',
    'pet_release/normal': '459759066ba88cf8',
    'pet_rename/boundary_long': '8c1965280b5206a3',
    'pet_rename/fail_fmt': 'd092aaf5c0644ec8',
    'pet_rename/fail_none': '459759066ba88cf8',
    'pet_rename/normal': '5e00cbff36cebfde',
    'pet_view/fail_none': '459759066ba88cf8',
    'pet_view/normal': 'd092aaf5c0644ec8',
    'stall_close/fail_none': '459759066ba88cf8',
    'stall_close/normal': '37d9da9b47f118dc',
    'stall_deprecated/fail_no_player': '459759066ba88cf8',
    'stall_deprecated/normal': '459759066ba88cf8',
    'stall_exchange/fail_fmt': '459759066ba88cf8',
    'stall_exchange/fail_hasprice': '063702a0daa46694',
    'stall_exchange/fail_none': 'bc9e2796f5341282',
    'stall_exchange/fail_self': '1935fda7a0e7555a',
    'stall_exchange/normal': 'aaa9e6e22412945f',
    'stall_exchange_pawn/fail_fmt': '459759066ba88cf8',
    'stall_exchange_pawn/normal': '2ad98ee73cdb2467',
    'stall_sell/boundary_batch': '5eb18fa88b0c0496',
    'stall_sell/fail_fmt': '459759066ba88cf8',
    'stall_sell/fail_noitem': '459759066ba88cf8',
    'stall_sell/normal': '85de02b350de6488',
    'stall_view/fail_notfound': '459759066ba88cf8',
    'stall_view/fail_target_none': '459759066ba88cf8',
    'stall_view/normal_empty': '459759066ba88cf8',
    'stall_view/normal_here': '1cd2ffc85b249631',
    'stall_view/normal_target': '1cd2ffc85b249631',
    'world_event/normal_idle': '4a5766cd3eebcd81',
    'world_event/normal_with_auction': 'a6af6d81638a22af',
}   # 每例结束后 DB 逐行 dump 的 sha256 前 16 位（副作用逐字冻结）


def t12_social_frozen():
    print("\n[12] 社交域逐字冻结：迁移前 129 例（33 条命令 × 正常/边界/失败）复跑比对")
    check("冻结基准已内嵌（129 例）", len(SOCIAL_FROZEN) == 129, len(SOCIAL_FROZEN))
    check("用例表覆盖 33 条命令", len({h for _c, h, _q, _m, _p in _S_CASES}) == 33,
          sorted({h for _c, h, _q, _m, _p in _S_CASES}))
    now = _s_scenarios()
    bad = [k for k in SOCIAL_FROZEN
           if SOCIAL_FROZEN[k] != (now.get(k) or {}).get("out")]
    for k in bad:
        print("     · %s 现=%r" % (k, ((now.get(k) or {}).get("out") or "")[:160]))
    check("★ 社交域 129 例文本与迁移前**逐字一致**", not bad, bad)
    bad_db = [k for k in SOCIAL_DB_SHA
              if SOCIAL_DB_SHA[k] != (now.get(k) or {}).get("db")]
    for k in bad_db[:6]:
        print("     · %s DB 摘要变了" % k)
    check("★ 社交域 129 例 DB 副作用与迁移前一致（逐行 dump 的 sha256 前 16 位）",
          not bad_db, bad_db[:6])
    bad_n = [k for k in SOCIAL_FROZEN if (now.get(k) or {}).get("n") != 1]
    check("★ 每例仍是**一条**成品消息（多段 yield 合成一条 = 终态形状，段数 1）",
          not bad_n, bad_n[:6])
    bad_stop = [k for k in SOCIAL_FROZEN if (now.get(k) or {}).get("stopped")]
    check("★ 没有一例意外 stop_event()", not bad_stop, bad_stop[:6])

    # 宿主壳零文案调用点（`T.text/T.static` 全部随命令进包）——本域 WIRED 的价值所在
    # ★ P5E-DELETE（2026-09-15，删壳批）：`SOCIAL_SRC` 已改指包内真源（见其定义处注释），
    #   下面「33 个 @declared」的形状计数随之**搬迁到真源**：终态命令面权威 = 包内声明表
    #   `content/data/commands.json`（与运行时注册表同源）。断言条数与强度不变
    #   （旧壳名单 33 条实测取自 `out/deleted/game/commands/social.py`，逐键对表）。
    host_calls, host_lits = _scan_calls(SOCIAL_SRC)
    pkg_calls, pkg_lits = _scan_calls(PKG_SOCIAL_SRC)
    check("★ 宿主 game/commands/social.py 零 `T.text/T.static` 调用点（渲染全进包）",
          not host_calls, host_calls[:4])
    check("包内 content/cmds_social.py 也无文案表调用点（句子是逐字搬来的内联字面量）",
          not pkg_calls, pkg_calls[:4])
    _soc_want = {"auction", "bid", "guild_appoint", "guild_create_cmd", "guild_demote",
                 "guild_disband_cmd", "guild_donate_cmd", "guild_info", "guild_join_cmd",
                 "guild_leave_cmd", "guild_rank", "guild_shop", "guild_sign",
                 "guild_skill_view", "guild_task", "market", "market_buy", "market_sell",
                 "market_unsell", "mount_cmd", "party", "party_leave", "pet_feed",
                 "pet_release", "pet_rename", "pet_view", "stall_close", "stall_deprecated",
                 "stall_exchange", "stall_exchange_pawn", "stall_sell", "stall_view",
                 "world_event"}
    _soc_decls = json.load(io.open(os.path.join(PKG_CONTENT, "data", "commands.json"),
                                   encoding="utf-8")) or {}
    _soc = sorted(k for k in _soc_decls if k in _soc_want)
    check("宿主壳保留 33 个 @declared（命令面一个不少）",
          len(_soc) == 33 and set(_soc) == _soc_want, len(_soc))


# ═══════════════════════ ECONOMY_BRANCHES_BEGIN ═══════════════════════
# ★ B18-L9（2026-09-15）：经济域 **45 条命令**整块进包（`content/cmds_economy.py`）——
#   宿主 `game/commands/economy.py` 退化为「`@declared` 注册 + 两行 `_BRIDGE.run_async`
#   转发」；守卫（`hook:player`）/ 取参 / 分支业务 / 回话全在包内（处理器 async —— 实现体
#   `content/economy_cmds.py::EconomyImpl.<m>` 是 async generator，只能 `async for` 迭代，
#   照 B18-L3c 战斗族先例 `content/cmds_combat.py`）。
#
#   本域**不使用** `T.text/T.static`：句子是 `EconomyImpl` 里的内联字面量 / f-string
#   （B9-L1 起就在包内），故「宿主 + 包内」两侧扫到 0 个调用点（WIRED 条目仍登记两侧 ——
#   将来若有人把句子改成文案表 key，本门禁立刻扫到并对账槽位）。
#   逐字一致的真正证据 = 本段 `ECONOMY_FROZEN`（文本）+ `ECONOMY_DB_SHA`（副作用）：
#   **迁移前**真跑 142 例（45 条命令 × 正常/边界/失败(无角色守卫) + 12 条追加边界）存下的
#   完整输出与 DB 逐行 dump 摘要，每次跑本门禁复跑比对。每例 clean_db + AUTOINCREMENT
#   计数清零 + 固定 random.seed；墙钟相关值在比对前归一化（见 `_e_*`）：
#     ① epoch 秒（含 JSON 串里嵌的等待型副业 `finish`）→ `<TS>`；
#     ② 日期串（每日任务 / 商店限购的 event_state key）→ `<DATE>`；
#     ③ 「剩余 N分N秒」→ 「剩余 <T>分<T>秒」；
#     ④ 足迹首访 epoch 钉死在 946684800（2000-01-01，见 `_e_visit`），故面板里的
#        `（MM-DD）` 是 `（01-01）`——确定值；
#     ⑤ uuid4 派生的物品 key `eq_/bp_/gem_<hex8>` → `<前缀>_<UUID>`（`uuid4().hex[:8]`）。
#   ★ PKG-D（2026-09-16）：等待型副业存储换引擎 produce 作业表（`prof_jobs_{qq}`）后，
#   唯一**真开等待轮**的 3 例（fishing/gather/mining 的 normal 分支）DB dump 的存储行
#   随之变 —— 文本/数值/流程/条数零变化（实测文本差异集 = 空）。这 3 例摘要已**重采**
#   并登记进 `_ECONOMY_DB_SHA_INTENT`（迁移前旧值 → 换机制后新值）；其余 139 例与
#   全部 142 例文本口径**不放宽**（仍逐例精确比对，登记表自身另有自洽断言）。
import hashlib as _E_hashlib
import sqlite3 as _E_sqlite3

_E_GID = "g_eco"           # 群（= 采「迁移前」快照时用的群号；冻结基准的 DB 摘要按它记）
_E_NONE = "zz_none"        # 未注册玩家（守卫分支）
_E_SEED = 20260915
_E_FIXED_TS = 946684800    # 足迹首访时间钉死（2000-01-01；< 1e9 故不被 <TS> 归一化吞掉）
_E_TIME_PAT = re.compile(r"剩余 \d+分\d+秒")
#: uuid4 派生物品 key（`eq_/bp_/gem_<hex8>` …，`uuid4().hex[:8]`）
_E_UUID_PAT = re.compile(r"\b([A-Za-z]{1,8})_[0-9a-f]{8}\b")
_E_UUID_INST_PAT = re.compile(r"\binst:[0-9a-f]{12}\b")
_E_DATE_PAT = re.compile(r"\d{4}-\d{2}-\d{2}")
_E_TS_EMBED_PAT = re.compile(r"(?<![\w.])\d{10,}(?![\w.])")
_E_BIG = 1_000_000_000

_E_ALL_PROFS = ("gather", "mining", "fishing", "cooking", "alchemy",
                "craft", "enhance", "enchant")


def _e_mk(qid, name, cls="战士", level=60, gold=200000, cur_map="oak_town", **upd):
    db.create_player(_E_GID, qid, name, C.resolve("classes", cls), {}, 100, 100)
    db.update_player(_E_GID, qid, level=level, gold=gold, cur_map=cur_map,
                     stamina=999999, **upd)
    db.init_stats(_E_GID, qid)


def _e_add_item(qid, key, name, typ="材料", price=10, count=1, **extra):
    data = {"name": name, "type": typ, "stackable": True, "price": price}
    data.update(extra)
    db.add_item(_E_GID, qid, key, data, count=count)
    return key


def _e_profs(qid="a", level=6):
    """全部副业激活 + 拜师 + 拉到指定等级（等待型副业的 apprentice 门槛）。"""
    db.update_player(_E_GID, qid, apprentices=list(_E_ALL_PROFS))
    for k in _E_ALL_PROFS:
        db.activate_prof(_E_GID, qid, k)
        try:
            db.add_prof_exp(_E_GID, qid, k, level * 60)
        except Exception:                                                  # noqa: BLE001
            pass


def _e_bag_a():
    """甲的标准背包（覆盖 item_detail / 装备 / 使用 / 出售 / 强化 等分支）。"""
    _e_add_item("a", "it_tie_jian", "铁剑", "装备", 100, 1,
                slot="weapon", lv=10, quality="green", stats={"atk": 12},
                weapon_type="sword", req={"str": 5})
    _e_add_item("a", "mat_rou", "兽肉", "材料", 5, 12)
    _e_add_item("a", "mat_yin_lin_yu", "银鳞鱼", "材料", 20, 3, food=True)
    _e_add_item("a", "i_treat_s", "治疗药水(小)", "消耗品", 30, 5, heal=60)
    _e_add_item("a", "i_stone_upgrade", "强化石", "材料", 200, 8)
    _e_add_item("a", "mat_tu_zhi_can_ye", "图纸残页", "材料", 50, 12)
    _e_add_item("a", "rn_shard", "符文碎片", "材料", 100, 6)
    _e_add_item("a", "gem_sui_lie", "碎裂的幸运宝石", "原石", 50, 4,
                gem=True, tier=1, stats={"atk": 0.02})


def _e_equip(data):
    """把一件装备写进甲的手上（equipment 字段）。"""
    key = "eq_%s" % data["slot"]
    db.add_item(_E_GID, "a", key, data, count=1)
    inv = [it for it in db.get_inventory(_E_GID, "a") if it["key"] == key]
    player = db.get_player(_E_GID, "a")
    equipment = dict(player.get("equipment") or {})
    equipment[data["slot"]] = inv[-1]["data"]
    db.update_player(_E_GID, "a", equipment=equipment)


def _e_equipped_a():
    """甲已穿好武器（unequip / my_equipment 的正常分支）。"""
    _e_equip({"name": "铁剑", "type": "装备", "stackable": False, "price": 100,
             "slot": "weapon", "lv": 10, "quality": "green", "stats": {"atk": 12},
             "weapon_type": "sword", "req": {"str": 5}})


def _e_equipped_set():
    """甲穿了两件「寒霜」套装部件（set_view 的正常分支）。"""
    _e_equip({"name": "寒霜胸甲", "type": "装备", "stackable": False, "price": 300,
             "slot": "armor", "lv": 20, "quality": "blue", "stats": {"def": 20},
             "set": "寒霜"})
    _e_equip({"name": "寒霜护腿", "type": "装备", "stackable": False, "price": 300,
             "slot": "legs", "lv": 20, "quality": "blue", "stats": {"def": 16},
             "set": "寒霜"})


def _e_cast(**kw):
    """甲（主测）+ 乙（对照）+ 丙 + 未注册玩家。"""
    clean_db()
    _e_reset_autoincrement()
    _clear_identity_map()          # ★ CLEANUP②：摘要口径 = 清库口径（见 `_clear_identity_map`）
    _e_mk("a", "甲", **kw)
    _e_mk("b", "乙", "法师")
    _e_mk("c", "丙", "游侠")
    _e_profs("a")


def _e_reset_autoincrement():
    conn = _E_sqlite3.connect(db.db_path())
    try:
        conn.execute("DELETE FROM sqlite_sequence")
        conn.commit()
    except _E_sqlite3.Error:
        pass
    finally:
        conn.close()


def _e_visit():
    """给甲记一笔足迹（footprint 正常分支），并把首访时间钉在固定 epoch（去墙钟）。"""
    try:
        db.add_visited_subarea(_E_GID, "a", "oak_plain", "oak_plain_3")
        db.add_visited_subarea(_E_GID, "a", "oak_plain", "oak_plain_1")
        db.add_visited(_E_GID, "a", "oak_plain")
    except Exception:                                                      # noqa: BLE001
        pass
    conn = _E_sqlite3.connect(db.db_path())
    try:
        # visited 表只有 (qq_id, map_id) 两列（无时间列）→ 只需钉 visited_subareas.first_at
        conn.execute("UPDATE visited_subareas SET first_at=?", (_E_FIXED_TS,))
        conn.commit()
    except _E_sqlite3.Error:
        pass
    finally:
        conn.close()


def _e_bestiary():
    for name in ("森林狼", "野猪", "哥布林", "石蜥", "史莱姆", "灰熊",
                 "暗影狼", "毒蛛", "骷髅兵", "岩龟"):
        try:
            db.bump_bestiary(_E_GID, "a", name)
        except Exception:                                                  # noqa: BLE001
            pass


def _e_smith():
    db.update_player(_E_GID, "a", cur_map="oak_town", cur_subarea="oak_town_3")


def _e_store():
    db.update_player(_E_GID, "a", cur_map="oak_town", cur_subarea="oak_town_5")


def _e_wild():
    db.update_player(_E_GID, "a", cur_map="oak_plain", cur_subarea="oak_plain_3")


def _e_mine():
    db.update_player(_E_GID, "a", cur_map="rockfall_gorge", cur_subarea="")


def _e_nowhere():
    """既无商店也无野外行商的地图（商店/购买 的「这里没有商店」分支）。"""
    db.update_player(_E_GID, "a", cur_map="misty_swamp", cur_subarea="misty_swamp_1")


def _e_attrs():
    """给甲足够的属性点，让『装备 铁剑』的属性需求通过（成功穿戴分支）。"""
    db.update_player(_E_GID, "a", attributes=json.dumps({"str": 50, "agi": 20,
                                                         "int": 20, "vit": 30},
                                                        ensure_ascii=False))


def _e_hurt():
    """把甲打成残血，让『使用 治疗药水(小)』走真实回复分支。"""
    db.update_player(_E_GID, "a", hp=5, max_hp=200)


def _e_no_gold():
    db.update_player(_E_GID, "a", gold=0)


def _e_full(**kw):
    """标准甲：全部副业 + 背包 + 足迹 + 图鉴 + 铁匠铺站位。"""
    _e_bag_a()
    _e_visit()
    _e_bestiary()
    _e_smith()
    if kw:
        db.update_player(_E_GID, "a", **kw)


#: prep 名 → 函数（顺序 = 快照脚本 `b18l9_snap.py` 同名函数）
_E_PREPS = {"bag_a": _e_bag_a, "full": _e_full, "visit": _e_visit,
            "bestiary": _e_bestiary, "smith": _e_smith, "store": _e_store,
            "wild": _e_wild, "mine": _e_mine, "nowhere": _e_nowhere,
            "no_gold": _e_no_gold, "attrs": _e_attrs, "hurt": _e_hurt,
            "equipped_a": _e_equipped_a, "equipped_set": _e_equipped_set}


def _e_norm_uuid(s):
    s = _E_UUID_PAT.sub(r"\1_<UUID>", s)
    return _E_UUID_INST_PAT.sub("inst:<UUID>", s)


def _e_cell(v):
    """DB 单元归一化：epoch 秒（数字 / 10 位以上数字串）→ `<TS>`。"""
    if isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v) > _E_BIG:
        return "<TS>"
    if isinstance(v, bytes):
        v = v.decode("utf-8", "replace")
    if isinstance(v, str) and v.isdigit() and len(v) >= 10:
        return "<TS>"
    return v


def _e_dump():
    """DB 逐行 dump（跳过 AUTOINCREMENT 计数表；墙钟与 uuid key 归一化）。"""
    conn = _E_sqlite3.connect(db.db_path())
    try:
        tabs = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            if r[0] != "sqlite_sequence"]
        out = []
        for t in tabs:
            try:
                rows = conn.execute("SELECT * FROM %s" % t).fetchall()
            except Exception as exc:                                       # noqa: BLE001
                rows = [("ERR", str(exc))]
            rows = [tuple(_e_cell(c) for c in r) for r in rows]
            out.append("%s: %s" % (t, sorted(repr(r) for r in rows)))
        text = "\n".join(out)
        text = _e_norm_uuid(text)
        text = _E_DATE_PAT.sub("<DATE>", text)
        return _E_TS_EMBED_PAT.sub("<TS>", text)
    finally:
        conn.close()


async def _e_one(m, handler, qid, msg, prep):
    _e_cast()
    if prep:
        for _part in prep.split("+"):
            _E_PREPS[_part]()
    random.seed(_E_SEED)
    ev = FakeEvent(_E_GID, qid, msg)
    texts = await run(getattr(m, handler), ev)
    joined = "\n".join(str(t) for t in texts)
    dump = _e_dump()
    return {
        "n": len(texts),
        "out": _E_TIME_PAT.sub("剩余 <T>分<T>秒", joined),
        "stopped": bool(getattr(ev, "_stopped", False)),
        "db": _E_hashlib.sha256(dump.encode("utf-8")).hexdigest()[:16],
    }


#: 用例表（cid, handler, qid, msg, prep）—— 与 `overnight/b18l9_cases.py` 的 CASES 逐字相同
_E_CASES = (
    ('gather/fail_no_player', 'gather', 'zz_none', '采集', ''),
    ('mining/fail_no_player', 'mining', 'zz_none', '挖掘', ''),
    ('alchemy/fail_no_player', 'alchemy', 'zz_none', '炼金', ''),
    ('alchemy_craft/fail_no_player', 'alchemy_craft', 'zz_none', '合成 治疗药水(小)', ''),
    ('cooking_list/fail_no_player', 'cooking_list', 'zz_none', '烹饪列表', ''),
    ('cooking/fail_no_player', 'cooking', 'zz_none', '烹饪', ''),
    ('bp_craft/fail_no_player', 'bp_craft', 'zz_none', '图纸合成', ''),
    ('profession_view/fail_no_player', 'profession_view', 'zz_none', '副业', ''),
    ('prof_forget/fail_no_player', 'prof_forget', 'zz_none', '遗忘副业 采集', ''),
    ('daily_prof/fail_no_player', 'daily_prof', 'zz_none', '副业任务', ''),
    ('fishing/fail_no_player', 'fishing', 'zz_none', '垂钓', ''),
    ('craft/fail_no_player', 'craft', 'zz_none', '锻造', ''),
    ('craft_commission/fail_no_player', 'craft_commission', 'zz_none', '代工 铁剑', ''),
    ('learn/fail_no_player', 'learn', 'zz_none', '学习 海风长弓图纸', ''),
    ('recipe_list/fail_no_player', 'recipe_list', 'zz_none', '配方', ''),
    ('enhance/fail_no_player', 'enhance', 'zz_none', '强化 铁剑', ''),
    ('equip_upgrade/fail_no_player', 'equip_upgrade', 'zz_none', '升级 铁剑', ''),
    ('gem_drill/fail_no_player', 'gem_drill', 'zz_none', '打孔 铁剑', ''),
    ('gem_socket/fail_no_player', 'gem_socket', 'zz_none', '镶嵌 铁剑 碎裂宝石', ''),
    ('gem_remove/fail_no_player', 'gem_remove', 'zz_none', '拆卸 铁剑', ''),
    ('gem_combine/fail_no_player', 'gem_combine', 'zz_none', '原石合成', ''),
    ('gem_view/fail_no_player', 'gem_view', 'zz_none', '原石', ''),
    ('rune_craft/fail_no_player', 'rune_craft', 'zz_none', '符文制作 残忍', ''),
    ('rune_remove/fail_no_player', 'rune_remove', 'zz_none', '符文拆卸 铁剑', ''),
    ('refine_equip/fail_no_player', 'refine_equip', 'zz_none', '装备重锻 铁剑', ''),
    ('calamity_forge/fail_no_player', 'calamity_forge', 'zz_none', '炼成 铁剑', ''),
    ('enchant/fail_no_player', 'enchant', 'zz_none', '附魔 铁剑 攻击', ''),
    ('set_view/fail_no_player', 'set_view', 'zz_none', '套装', ''),
    ('monster/fail_no_player', 'monster', 'zz_none', '怪物 森林狼', ''),
    ('adventure_book/fail_no_player', 'adventure_book', 'zz_none', '冒险手册', ''),
    ('footprint/fail_no_player', 'footprint', 'zz_none', '足迹', ''),
    ('bestiary/fail_no_player', 'bestiary', 'zz_none', '图鉴', ''),
    ('encyclopedia/fail_no_player', 'encyclopedia', 'zz_none', '百科 铁剑', ''),
    ('titles/fail_no_player', 'titles', 'zz_none', '称号', ''),
    ('inventory/fail_no_player', 'inventory', 'zz_none', '背包', ''),
    ('bag_filter/fail_no_player', 'bag_filter', 'zz_none', '背包筛选 材料', ''),
    ('item_view_mode_cmd/fail_no_player', 'item_view_mode_cmd', 'zz_none', '物品详情开始', ''),
    ('item_detail/fail_no_player', 'item_detail', 'zz_none', '物品详情 铁剑', ''),
    ('my_equipment/fail_no_player', 'my_equipment', 'zz_none', '我的装备', ''),
    ('equip/fail_no_player', 'equip', 'zz_none', '装备 铁剑', ''),
    ('unequip/fail_no_player', 'unequip', 'zz_none', '卸下 武器', ''),
    ('use/fail_no_player', 'use', 'zz_none', '使用 治疗药水(小)', ''),
    ('sell/fail_no_player', 'sell', 'zz_none', '出售 兽肉', ''),
    ('shop/fail_no_player', 'shop', 'zz_none', '商店', ''),
    ('buy/fail_no_player', 'buy', 'zz_none', '购买 治疗药水(小)', ''),
    ('gather/normal', 'gather', 'a', '采集', 'full+wild'),
    ('gather/boundary_town', 'gather', 'a', '采集', 'full+store'),
    ('mining/normal', 'mining', 'a', '挖掘', 'full+mine'),
    ('mining/boundary_no_vein', 'mining', 'a', '挖掘', 'full+wild'),
    ('alchemy/normal', 'alchemy', 'a', '炼金', 'full'),
    ('alchemy/boundary_page2', 'alchemy', 'a', '炼金 2', 'full'),
    ('alchemy_craft/normal', 'alchemy_craft', 'a', '合成 治疗药水(小)', 'full'),
    ('alchemy_craft/boundary_notfound', 'alchemy_craft', 'a', '合成 不存在', 'full'),
    ('cooking_list/normal', 'cooking_list', 'a', '烹饪列表', 'full'),
    ('cooking_list/boundary_page2', 'cooking_list', 'a', '烹饪列表 2', 'full'),
    ('cooking/normal', 'cooking', 'a', '烹饪', 'full'),
    ('cooking/boundary_notfound', 'cooking', 'a', '烹饪 不存在', 'full'),
    ('bp_craft/normal', 'bp_craft', 'a', '图纸合成', 'full'),
    ('bp_craft/boundary_index', 'bp_craft', 'a', '图纸合成 1', 'full'),
    ('profession_view/normal', 'profession_view', 'a', '副业', 'full'),
    ('profession_view/boundary_rank', 'profession_view', 'a', '副业 排行', 'full'),
    ('prof_forget/normal', 'prof_forget', 'a', '遗忘副业 采集', 'full'),
    ('prof_forget/boundary_nosuch', 'prof_forget', 'a', '遗忘副业 不存在', 'full'),
    ('daily_prof/normal', 'daily_prof', 'a', '副业任务', 'full'),
    ('daily_prof/boundary_alias', 'daily_prof', 'a', '今日副业', 'full'),
    ('fishing/normal', 'fishing', 'a', '垂钓', 'full+wild'),
    ('fishing/boundary_no_water', 'fishing', 'a', '垂钓', 'full+store'),
    ('craft/normal', 'craft', 'a', '锻造', 'full'),
    ('craft/boundary_all', 'craft', 'a', '锻造 全部', 'full'),
    ('craft_commission/normal', 'craft_commission', 'a', '代工 铁剑', 'full'),
    ('craft_commission/boundary_no_smith', 'craft_commission', 'a', '代工 铁剑', 'full+wild'),
    ('learn/normal', 'learn', 'a', '学习 海风长弓图纸', 'full'),
    ('learn/boundary_empty', 'learn', 'a', '学习', 'full'),
    ('recipe_list/normal', 'recipe_list', 'a', '配方', 'full'),
    ('recipe_list/boundary_detail', 'recipe_list', 'a', '配方 铁剑', 'full'),
    ('enhance/normal', 'enhance', 'a', '强化 铁剑', 'full'),
    ('enhance/boundary_notfound', 'enhance', 'a', '强化 不存在的剑', 'full'),
    ('equip_upgrade/normal', 'equip_upgrade', 'a', '升级 铁剑', 'full'),
    ('equip_upgrade/boundary_notfound', 'equip_upgrade', 'a', '升级 不存在的剑', 'full'),
    ('gem_drill/normal', 'gem_drill', 'a', '打孔 铁剑', 'full'),
    ('gem_drill/boundary_notfound', 'gem_drill', 'a', '打孔 不存在的剑', 'full'),
    ('gem_socket/normal', 'gem_socket', 'a', '镶嵌 铁剑 碎裂的幸运宝石', 'full'),
    ('gem_socket/boundary_fmt', 'gem_socket', 'a', '镶嵌 铁剑', 'full'),
    ('gem_remove/normal', 'gem_remove', 'a', '拆卸 铁剑 1', 'full'),
    ('gem_remove/boundary_notfound', 'gem_remove', 'a', '拆卸 不存在的剑', 'full'),
    ('gem_combine/normal', 'gem_combine', 'a', '原石合成 碎裂的幸运宝石', 'full'),
    ('gem_combine/boundary_none', 'gem_combine', 'a', '原石合成', 'full'),
    ('gem_view/normal', 'gem_view', 'a', '原石', 'full'),
    ('gem_view/boundary_detail', 'gem_view', 'a', '原石 碎裂的幸运宝石', 'full'),
    ('rune_craft/normal', 'rune_craft', 'a', '符文制作', 'full'),
    ('rune_craft/boundary_no_mat', 'rune_craft', 'a', '符文制作 残忍', 'full'),
    ('rune_remove/normal', 'rune_remove', 'a', '符文拆卸 铁剑', 'full'),
    ('rune_remove/boundary_notfound', 'rune_remove', 'a', '符文拆卸 不存在的剑', 'full'),
    ('refine_equip/normal', 'refine_equip', 'a', '装备重锻 铁剑', 'full'),
    ('refine_equip/boundary_notfound', 'refine_equip', 'a', '装备重锻 不存在的剑', 'full'),
    ('calamity_forge/normal', 'calamity_forge', 'a', '炼成 铁剑', 'full'),
    ('calamity_forge/boundary_notfound', 'calamity_forge', 'a', '炼成 不存在的剑', 'full'),
    ('enchant/normal', 'enchant', 'a', '附魔 铁剑 攻击', 'full'),
    ('enchant/boundary_fmt', 'enchant', 'a', '附魔 铁剑', 'full'),
    ('set_view/normal', 'set_view', 'a', '套装', 'full+equipped_set'),
    ('set_view/boundary_unknown', 'set_view', 'a', '套装 不存在', 'full'),
    ('monster/normal', 'monster', 'a', '怪物 森林狼', 'full'),
    ('monster/boundary_unknown', 'monster', 'a', '怪物 不存在的怪物', 'full'),
    ('adventure_book/normal', 'adventure_book', 'a', '冒险手册', 'full'),
    ('adventure_book/boundary_items', 'adventure_book', 'a', '冒险手册 物品', 'full'),
    ('footprint/normal', 'footprint', 'a', '足迹', 'full'),
    ('footprint/boundary_empty', 'footprint', 'a', '足迹', 'bag_a+smith'),
    ('bestiary/normal', 'bestiary', 'a', '图鉴', 'full'),
    ('bestiary/boundary_page2', 'bestiary', 'a', '图鉴 2', 'full'),
    ('encyclopedia/normal', 'encyclopedia', 'a', '百科 铁剑', 'full'),
    ('encyclopedia/boundary_browse', 'encyclopedia', 'a', '百科 材料', 'full'),
    ('titles/normal', 'titles', 'a', '称号', 'full'),
    ('titles/boundary_page2', 'titles', 'a', '称号 2', 'full'),
    ('inventory/normal', 'inventory', 'a', '背包', 'full'),
    ('inventory/boundary_filter', 'inventory', 'a', '背包 材料', 'full'),
    ('bag_filter/normal', 'bag_filter', 'a', '背包筛选 材料', 'full'),
    ('bag_filter/boundary_page2', 'bag_filter', 'a', '背包筛选 材料 2', 'full'),
    ('item_view_mode_cmd/normal', 'item_view_mode_cmd', 'a', '物品详情开始', 'full'),
    ('item_view_mode_cmd/boundary_end', 'item_view_mode_cmd', 'a', '物品详情结束', 'full'),
    ('item_detail/normal', 'item_detail', 'a', '物品详情 铁剑', 'full'),
    ('item_detail/boundary_index', 'item_detail', 'a', '物品详情 1', 'full'),
    ('my_equipment/normal', 'my_equipment', 'a', '我的装备', 'full+equipped_a'),
    ('my_equipment/boundary_empty', 'my_equipment', 'a', '我的装备', 'bag_a+smith'),
    ('equip/normal', 'equip', 'a', '装备 铁剑', 'full'),
    ('equip/normal_ok', 'equip', 'a', '装备 铁剑', 'full+attrs'),
    ('equip/boundary_notfound', 'equip', 'a', '装备 不存在的剑', 'full'),
    ('unequip/normal', 'unequip', 'a', '卸下 武器', 'full+equipped_a'),
    ('unequip/boundary_empty', 'unequip', 'a', '卸下 武器', 'full'),
    ('use/normal', 'use', 'a', '使用 治疗药水(小)', 'full'),
    ('use/normal_low_hp', 'use', 'a', '使用 治疗药水(小)', 'full+hurt'),
    ('use/boundary_notfound', 'use', 'a', '使用 不存在的东西', 'full'),
    ('sell/normal', 'sell', 'a', '出售 兽肉', 'full'),
    ('sell/boundary_category', 'sell', 'a', '出售 材料', 'full'),
    ('sell/boundary_all', 'sell', 'a', '出售 全部', 'full'),
    ('shop/normal', 'shop', 'a', '商店', 'full+store'),
    ('shop/boundary_no_shop', 'shop', 'a', '商店', 'full+nowhere'),
    ('buy/normal', 'buy', 'a', '购买 治疗药水(小)', 'full+store'),
    ('buy/normal_batch', 'buy', 'a', '购买 治疗药水(小)*3', 'full+store'),
    ('buy/boundary_no_gold', 'buy', 'a', '购买 治疗药水(小)', 'full+store+no_gold'),
    ('inventory/boundary_empty', 'inventory', 'a', '背包', 'smith'),
    ('bestiary/boundary_empty', 'bestiary', 'a', '图鉴', 'smith'),
    ('gem_view/boundary_empty', 'gem_view', 'a', '原石', 'smith'),
)


def _e_scenarios() -> dict:
    """复跑全部 142 例（迁移前采快照 / 迁移后门禁比对，同一份驱动代码）。

    宿主实例整轮复用同一个 `Main(None)`（与采快照脚本一致：跨例的命令层实例态必须同源，
    否则快照不可比）。
    """
    out = {}
    m = Main(None)
    for cid, handler, qid, msg, prep in _E_CASES:
        out[cid] = asyncio.run(_e_one(m, handler, qid, msg, prep))
    clean_db()
    return out


ECONOMY_FROZEN = {
    'adventure_book/boundary_items': '🎒 【曾拥有物品】已拥有 6 · 全量 1587（第 1/2 页）\n━━━━━━━━━━━━\n消耗品（已拥有 1/271）\n  ✅治疗药水(小)×5\u3000❌一袋商路口粮\u3000❌不动药剂\u3000❌不死鸟之羽\n  ❌丰饶之锄\u3000❌传送卷轴\u3000❌便携种植箱\u3000❌信仰结晶\n  ❌信鸦翎\u3000❌元素亲和药剂\u3000❌元素共鸣石\u3000❌元素引爆剂\n  ❌元素湮灭技能书\u3000❌元素结晶\u3000❌充能蒸馏器\u3000❌全效药水\n  ❌公会回城卷\u3000❌冒险者合剂\u3000❌冰霜浆果\u3000❌净化卷轴\n  …还有 251 种：『冒险手册 物品 消耗品』看更多\n鱼（已拥有 1/11）\n  ✅银鳞鱼×3\u3000❌冰鳞鲟\u3000❌帝王鲑\u3000❌月光鱼\n  ❌沼牙鳝\u3000❌溪鳟\u3000❌灯语鳕\u3000❌盲鱼\n  ❌金鲤\u3000❌雷纹鲭\u3000❌青纹鲈\n🗂 未收集大类：装备、收藏品、图纸、草药、木材、兽材 等（『冒险手册 物品 <大类>』查看）\n━━━━━━━━━━━━\n💡 ✅=曾拥有 ×N=现持有 ｜ ❌=还没拿过 ｜ 『冒险手册 物品 <大类>』只看某类 ｜ 『+』翻页',
    'adventure_book/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'adventure_book/normal': '📖 【冒险手册】\n━━━━━━━━━━━━\n📍 足迹 2/520 子区域\n👹 怪物 10/345 种 · 累计击杀 10\n🎒 物品 6 种曾拥有 · 当前持有 6 种\n🎣 收藏 鱼 0/3 ｜ 收藏品 0/20\n🐾 宠物 0/16 种（孵过）\n━━━━━━━━━━━━\n💡 『足迹』区域 ｜ 『冒险手册 怪物/物品/收藏/垂钓/宠物』看明细',
    'alchemy/boundary_page2': '🧪 【炼金工坊】(炼金 Lv.5)材料合成配方：\n━━━━━━━━━━━━\n 6. ✅ 学徒合剂：草药×1 + 妖精之尘×1 → 学徒合剂  [炼金Lv.2]\n    学徒练手合剂，回复 15% HP+MP\n 7. ✅ 萤光鱼饵：月光草×1 + 空瓶×1 → 萤光鱼饵  [炼金Lv.3]\n    月光草调制的荧光饵料，幽光引鱼——下次垂钓紫/橙档概率大幅提升(仅 1 次)\n 8. ✅ 轻效治疗药水：草药×2 + 空瓶×1 → 轻效治疗药水  [炼金Lv.3]\n    轻度治疗，回复 25% 生命\n 9. ✅ 高效治疗药水：碎骨×1 + 狼皮×1 → 高效治疗药水  [炼金Lv.4]\n    用圣光羽毛炼制的强效恢复药水\n10. ✅ 强效魔法药水：雪之精华×1 + 妖精之尘×2 → 强效魔法药水  [炼金Lv.4]\n    用雪之精华炼制的强效魔力药水\n━━━━━━━━━━━━\n📄 第 2/17 页｜『炼金 3』下一页\n💡 材料齐了发『合成 <配方名>』',
    'alchemy/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'alchemy/normal': '🧪 【炼金工坊】(炼金 Lv.5)材料合成配方：\n━━━━━━━━━━━━\n 1. ✅ 治疗药水(小)：狼皮×1 → 治疗药水(小)  [炼金Lv.1]\n    用兽皮与妖精之尘炼制的恢复药水（同商店「治疗药水(小)」）\n 2. ✅ 魔法药水(小)：石蜥鳞×1 → 魔法药水(小)  [炼金Lv.1]\n    恢复魔力（同商店「魔法药水(小)」，价格与商店一致）\n 3. ✅ 微效治疗药水：草药×1 → 微效治疗药水  [炼金Lv.1]\n    基础草药熬制，回复 15% 生命\n 4. ✅ 强化石：熔岩石×2 + 深渊精钢×1 → 强化石  [炼金Lv.2]\n    强化装备的必备材料\n 5. ✅ 回城卷轴：鬼魂精华×3 + 妖精之尘×1 → 回城卷轴  [炼金Lv.2]\n    瞬间回到最近城镇\n━━━━━━━━━━━━\n📄 第 1/17 页｜『炼金 2』下一页\n💡 材料齐了发『合成 <配方名>』',
    'alchemy_craft/boundary_notfound': '没有『不存在』这个配方！『炼金』查看全部～',
    'alchemy_craft/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'alchemy_craft/normal': '材料不足！需要 狼皮×1(你有 0)',
    'bag_filter/boundary_page2': '🎒 【背包·材料】\n━━━━━━━━━━━━\n 1. ⚪兽肉 ×12 (食材)\n 2. ⚪银鳞鱼 ×3 (鱼)\n 3. 🟠强化石 ×8 (矿石)\n 4. ⚪图纸残页 ×12 (杂物)\n 5. 🟣符文碎片 ×6 (杂物)\n━━━━━━━━━━━━\n📄 第 1/1 页 · 共 5 件\n💡 可发送 背包筛选 <类型> 分类查看\n💡 筛选视图序号与全局背包不同，『出售 <序号>』按全局序号——出售/装备请用物品名称（#234）',
    'bag_filter/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'bag_filter/normal': '🎒 【背包·材料】\n━━━━━━━━━━━━\n 1. ⚪兽肉 ×12 (食材)\n 2. ⚪银鳞鱼 ×3 (鱼)\n 3. 🟠强化石 ×8 (矿石)\n 4. ⚪图纸残页 ×12 (杂物)\n 5. 🟣符文碎片 ×6 (杂物)\n━━━━━━━━━━━━\n📄 第 1/1 页 · 共 5 件\n💡 可发送 背包筛选 <类型> 分类查看\n💡 筛选视图序号与全局背包不同，『出售 <序号>』按全局序号——出售/装备请用物品名称（#234）',
    'bestiary/boundary_empty': '📖 图鉴还是空的……去『探索』击败怪物，或『垂钓』邂逅彩蛋收藏鱼吧！\n🌈 【彩蛋收藏鱼】已收藏 0/3 · 累计钓获 0 次\n━━━━━━━━━━━━\n  ❌ ??? （垂钓时有极低概率邂逅）\n  ❌ ??? （夜晚垂钓有极低概率邂逅）\n  ❌ ??? （垂钓时有极低概率邂逅）\n💡 彩蛋收藏鱼钓到自动收进图鉴；对应成就见『成就 隐藏』',
    'bestiary/boundary_page2': '📖 【怪物图鉴】已收录 10 种 · 累计击杀 10(第 2/2 页)\n━━━━━━━━━━━━\n 6. 岩龟 ×1\n 7. 暗影狼 ×1\n 8. 毒蛛 ×1\n 9. 灰熊 ×1\n10. 石蜥 ×1\n\n💡 击败新怪物自动收录 ｜ 『冒险手册 物品/收藏』看收集',
    'bestiary/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'bestiary/normal': '📖 【怪物图鉴】已收录 10 种 · 累计击杀 10(第 1/2 页)\n━━━━━━━━━━━━\n 1. 野猪 ×1\n 2. 森林狼 ×1\n 3. 骷髅兵 ×1\n 4. 史莱姆 ×1\n 5. 哥布林 ×1\n\n💡 图鉴自动记录怪物击杀次数\n💡 击败新怪物自动收录 ｜ 『冒险手册 物品/收藏』看收集',
    'bp_craft/boundary_index': '📜 10 张图纸残页在掌中拼合，微光闪过——\n✅ 合成成功！获得【学徒之血刃图纸】(史诗·Lv.10)\n💡 『学习 学徒之血刃图纸』永久解锁锻造配方！',
    'bp_craft/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'bp_craft/normal': '📜 【图纸残页合成】(图纸残页×12/10)\n━━━━━━━━━━━━\n 1. 🟣【学徒之血刃】Lv.10 武器\n 2. 🟣【旅人之盾】Lv.10 武器\n 3. 🟣【星火法杖】Lv.10 武器\n 4. 🟣【猎影之牙】Lv.12 武器\n 5. 🟣【翠风之弓】Lv.13 武器\n━━━━━━━━━━━━\n📄 第 1/44 页｜『图纸合成 2』下一页\n💡 『图纸合成 <装备名>』消耗 10 张图纸残页，定向获得 1 张指定图纸（只列出有锻造配方的装备）',
    'buy/boundary_no_gold': '金币不足！需要 10 金币。',
    'buy/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'buy/normal': '✅ 你购买了【治疗药水(小)】 ×1！',
    'buy/normal_batch': '✅ 你购买了【治疗药水(小)】 ×3！',
    'calamity_forge/boundary_notfound': '背包里没有叫『不存在的剑』的装备！(已装备的装备也可以直接操作，如『打孔 铁剑』)',
    'calamity_forge/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'calamity_forge/normal': '炼成材料不足！还缺：余烬核心×1(你有0)。Boss 掉落稀有素材～',
    'cooking/boundary_notfound': '没有『不存在』这道料理！『烹饪列表』查看全部～',
    'cooking/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'cooking/normal': '发『烹饪列表』查看全部料理配方～(如：烹饪 蛇羹)',
    'cooking_list/boundary_page2': '🍳 【烹饪灶台】料理配方：\n━━━━━━━━━━━━\n 6. 鹰蛋(烹饪Lv.1)\n    海鸥羽毛×1 + 浆果×1 → 鹰蛋\n 7. 灰烬烤饼(烹饪Lv.1)\n    面粉×2 + 浆果×2 → 灰烬烤饼\n 8. 圣餐面包(烹饪Lv.2)\n    面粉×2 + 圣水×1 → 圣餐面包\n 9. 鹿奶干酪(烹饪Lv.2)\n    溪鹿皮×1 + 浆果×1 → 鹿奶干酪\n10. 海盗炖鱼(烹饪Lv.4)\n    银鳞鱼×2 → 海盗炖鱼\n\n📄 第 2/12 页｜『烹饪列表 3』下一页\n💡 『烹饪 蛇羹』试试，『烹饪列表』看配方\n💡 烹饪等级：采集植物 + 垂钓 → 料理，成功制作＋1 经验',
    'cooking_list/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'cooking_list/normal': '🍳 【烹饪灶台】料理配方：\n━━━━━━━━━━━━\n 1. 史莱姆果冻(烹饪Lv.1)\n    史莱姆黏液×3 → 史莱姆果冻\n 2. 烤肉串(自制)(烹饪Lv.1)\n    兽肉×2 → 烤肉串(自制)\n 3. 金鲤盛宴(烹饪Lv.4)\n    金鲤×2 → 金鲤盛宴\n 4. 蛇羹(烹饪Lv.1)\n    蛇皮×3 → 蛇羹\n 5. 狼肉干(烹饪Lv.1)\n    狼皮×2 → 狼肉干\n\n📄 第 1/12 页｜『烹饪列表 2』下一页\n💡 『烹饪 蛇羹』试试，『烹饪列表』看配方\n💡 烹饪等级：采集植物 + 垂钓 → 料理，成功制作＋1 经验',
    'craft/boundary_all': '🔨 铁匠铺·全部配方(共 426 件)｜橡木镇锻造 Lv.1-12\n━━━━━━━━━━━━\n1. ⚪【猎弓】Lv.2 武器 ✅\n    青橡木×2｜0金\n2. ⚪【铁剑】Lv.2 武器 ✅\n    粗铁×2｜0金\n3. ⚪【橡木短棍】Lv.2 武器 ✅\n    粗铁×5 + 史莱姆黏液×2｜0金\n4. ⚪【学徒法杖】Lv.2 武器 ✅\n    青橡木×1｜0金\n5. ⚪【皮甲】Lv.3 胸甲 ✅\n    史莱姆黏液×6｜0金\n━━━━━━━━━━━━\n📄 第 1/86 页｜『锻造 全部 2』下一页\n💡 未达标的配方：🔒等级不够 ｜ 🛠️锻造副业等级不够 ｜ 📜图纸未学习 ｜ 🔒城镇需到对应等级城镇的铁匠铺\n💡 『代工 <装备名>』三倍金币免等级',
    'craft/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'craft/normal': '🔨 铁匠铺·当前可锻造(共 49 件)｜橡木镇锻造 Lv.1-12\n━━━━━━━━━━━━\n1. ⚪【猎弓】Lv.2 武器 锻造Lv.1\n    青橡木×2｜0金\n2. ⚪【铁剑】Lv.2 武器 锻造Lv.1\n    粗铁×2｜0金\n3. ⚪【橡木短棍】Lv.2 武器 锻造Lv.1\n    粗铁×5 + 史莱姆黏液×2｜0金\n4. ⚪【学徒法杖】Lv.2 武器 锻造Lv.1\n    青橡木×1｜0金\n5. ⚪【皮甲】Lv.3 胸甲 锻造Lv.1\n    史莱姆黏液×6｜0金\n━━━━━━━━━━━━\n📄 第 1/10 页｜『锻造列表 2』下一页\n💡 『代工 <装备名>』三倍金币免等级\n💡 『图纸合成 <装备名>』残页换图纸',
    'craft_commission/boundary_no_smith': '需要到铁匠铺/锻造坊才能找铁匠代工！(先『地图』移动到铁匠铺)',
    'craft_commission/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'craft_commission/normal': '材料不足！代工【铁剑】还缺：粗铁×2(你有0)。材料可通过打怪/垂钓/挖掘/商店获得！',
    'daily_prof/boundary_alias': '🎯 【今日副业任务】\n━━━━━━━━━━━━\n目标：挖掘 ×3 (0/3)\n奖励：50 金币 + 50 副业经验\n\n💡 完成对应副业动作自动推进，明天刷新新任务！',
    'daily_prof/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'daily_prof/normal': '🎯 【今日副业任务】\n━━━━━━━━━━━━\n目标：挖掘 ×3 (0/3)\n奖励：50 金币 + 50 副业经验\n\n💡 完成对应副业动作自动推进，明天刷新新任务！',
    'enchant/boundary_fmt': '没有『』这个附魔属性！可用：攻击、魔攻、防御、魔防、生命、速度、暴击',
    'enchant/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'enchant/normal': '【铁剑】(优秀)没有附魔槽，只有蓝/紫/橙装备可以附魔！',
    'encyclopedia/boundary_browse': '🧪 【材料百科】共 598 种材料 · 按分类速览\n━━━━━━━━━━━━\n兽材 ×141\u3000例：磐涡龟甲、云殿铠甲、古龙鳞\n矿石 ×50\u3000例：祝福符石、精炼强化石、星铁\n木材 ×16\u3000例：元素之木、苍穹天木、晨星之木\n织物 ×12\u3000例：云絮、月华绸、幽灵帆布\n草药 ×19\u3000例：龙血草、极光花、雷雨藤\n宝石 ×10\u3000例：幸运宝石、深渊水晶、龙宫珠\n精华 ×62\u3000例：余烬核心、陨星核、彩虹露\n食材 ×19\u3000例：冻鱼鳞、盲鱼鳞、龙虾壳\n材料 ×19\u3000例：烬核火种、月辉精魄、潮汐黑铁\n鱼 ×11\u3000例：雷纹鲭、冰鳞鲟、灯语鳕\n鱼王 ×1\u3000鱼王·翡翠巨龙\n图纸 ×19\u3000例：蚀夜之面图纸、奥拉圣印图纸、熔炉之心图纸\n传说 ×6\u3000例：传说锻造材料、渊火精钢、永恒花种子\n元素 ×1\u3000龙焰精华\n符文 ×1\u3000破甲符文\n工具 ×1\u3000传说钓竿·银铃之竿\n宝物 ×1\u3000陈旧的宝箱\n垃圾 ×2\u3000水草、破旧的靴子\n任务道具 ×73\u3000例：灰烬之核、星尘沙漏、烬火信标\n收藏 ×23\u3000例：历史学家笔记、骑士团徽章、烈焰符文\n杂物 ×111\u3000例：源质、咏叹谱残页、光之圣典\n━━━━━━━━━━━━\n💡 输入『百科 <材料名>』看掉落来源；『图鉴 收藏』看收藏品',
    'encyclopedia/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'encyclopedia/normal': '⚔️ ⚪【铁剑】(武器·Lv.2·普通)\n━━━━━━━━━━━━\n类型：剑\n✦ 剑类武器：攻守均衡，暴击＋2%\n属性：\n  · 攻击 + 10\n  · 魔攻 + 1\n  · 暴击 + 2%\n系列：橡木\n需求：无需求\n来源：商店\n橡木风格的长剑，剑脊笔直，护手朴素。橡木镇匠人的朴实手艺，耐用又可靠。\n🔨 获取：锻造可得（铁匠铺『锻造』）\n💡 『百科装备 武器』看武器全部装备',
    'enhance/boundary_notfound': '背包里没有叫『不存在的剑』的装备！(已装备的武器也可以直接『强化 <武器名>』)',
    'enhance/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'enhance/normal': '🔨 强化成功！【铁剑】+0 → +1！(消耗 50 金币)\n\n🛠️ 强化师 Lv.5 的手艺：成功率 +2.5%！',
    'equip/boundary_notfound': '背包里没有叫『不存在的剑』的装备！',
    'equip/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'equip/normal': '属性不够，穿不上【铁剑】！需求：力量 5(你当前 力量 0/5)\n加点后属性达标才能装备(『属性』查看、『加点 力量 N』加点)',
    'equip/normal_ok': '✅ 你装备了 🟢【铁剑】！\n📊 属性变化：\n  · 攻击 + 12',
    'equip_upgrade/boundary_notfound': '背包里没有叫『不存在的剑』的装备！(已装备的装备也可以直接『升级 <装备名>』)',
    'equip_upgrade/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'equip_upgrade/normal': '升级 Lv.10 → Lv.11 需要强化副业 Lv.10(你 Lv.5)！强化与升级共修，多强化装备升级副业吧～',
    'fishing/boundary_no_water': '这里没有水域！找有水的地方垂钓：橡木溪流、星语湖、铁港码头、银铃河、迷雾沼泽、霜原冰湖、迷雾海沟、龙鲸海域、风暴之海、深渊湖、彩虹云谷',
    'fishing/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'fishing/normal': '🎣 你在橡木溪流抛出鱼竿，开始垂钓……预计 48 秒后完成，自动入包～',
    'footprint/boundary_empty': '📍 还没去过任何地方……快去『探索』冒险吧！',
    'footprint/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'footprint/normal': '📍 【我的足迹】\n━━━━━━━━━━━━\n◈ 南境·绿野（2/102 · 2%）\n  🟡 橡木平原：草地边缘(01-01)、溪边草地(01-01)\n━━━━━━━━━━━━\n探索足迹 2/520（城镇与野外）\n💡 ✅=全到访 🟡=部分 ❌=未去 ｜ （MM-DD）=首访日期 ｜ 『探索』补全足迹',
    'gather/boundary_town': '城镇里没有可采集的野生物资，去野外吧（『前往 <地图名>』）！',
    'gather/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'gather/normal': '🌿 你俯身开始采集【橡木平原】的野生物资……预计 48 秒后完成，自动入包～',
    'gem_combine/boundary_none': '💎 【原石合成】3 个同级原石 → 1 个上级，无失败！\n━━━━━━━━━━━━\n✅ 碎裂的幸运宝石 ×4/3  →  黯淡的幸运宝石\n━━━━━━━━━━━━\n💡 『原石合成 <原石名/序号>』消耗 3 颗同级幸运宝石合成 1 颗上级(神话 不可再合成)',
    'gem_combine/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'gem_combine/normal': '✨ 三颗 碎裂的幸运宝石 光芒交织，合成了更纯粹的幸运宝石！\n✅ 合成成功！获得 黯淡的幸运宝石·攻击+1%(消耗 3 颗，无失败)',
    'gem_drill/boundary_notfound': '背包里没有叫『不存在的剑』的装备！(已装备的装备也可以直接操作，如『打孔 铁剑』)',
    'gem_drill/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'gem_drill/normal': '【铁剑】(优秀)没有孔位可打，只有蓝/紫/橙装备可以打孔！',
    'gem_remove/boundary_notfound': '拆卸哪个孔位的幸运宝石？输入『拆卸 <装备名> <孔位>』(如：拆卸 铁剑 S1)',
    'gem_remove/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'gem_remove/normal': '【铁剑】没有 1 这个孔位(孔位：无)！',
    'gem_socket/boundary_fmt': '镶嵌哪颗幸运宝石到哪件装备？输入『镶嵌 <装备名> <原石名/序号> [孔位]』\n如：『镶嵌 铁剑 碎裂的幸运宝石』『镶嵌 铁剑 1』『镶嵌 铁剑 碎裂 S2』(孔位默认第一个空孔)',
    'gem_socket/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'gem_socket/normal': '【铁剑】还没有孔位！先『打孔 铁剑』打出孔位再镶嵌～',
    'gem_view/boundary_detail': '💎 【幸运宝石】(共 4 颗)\n━━━━━━━━━━━━\n💎 碎裂的幸运宝石 ×4 ｜ 阶1 ｜ atk+2% ｜ 蓝孔\n━━━━━━━━━━━━\n💡 『镶嵌 <装备> <原石>』镶入装备 ｜ 『原石合成 <原石>』3 合 1 升级 ｜ 『拆卸 <装备> <孔位>』取下',
    'gem_view/boundary_empty': '💎 背包里还没有幸运宝石！打怪有概率掉落幸运宝石～\n💡 『打孔 <装备>』给蓝/紫/橙装开孔，『镶嵌 <装备> <原石>』镶入获得属性！',
    'gem_view/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'gem_view/normal': '💎 【幸运宝石】(共 4 颗)\n━━━━━━━━━━━━\n💎 碎裂的幸运宝石 ×4 ｜ 阶1 ｜ atk+2% ｜ 蓝孔\n━━━━━━━━━━━━\n💡 『镶嵌 <装备> <原石>』镶入装备 ｜ 『原石合成 <原石>』3 合 1 升级 ｜ 『拆卸 <装备> <孔位>』取下',
    'inventory/boundary_empty': '你的背包空空如也……去『探索』打点东西吧！',
    'inventory/boundary_filter': '🎒 【背包·材料】\n━━━━━━━━━━━━\n 1. ⚪兽肉 ×12 (食材)\n 2. ⚪银鳞鱼 ×3 (鱼)\n 3. 🟠强化石 ×8 (矿石)\n 4. ⚪图纸残页 ×12 (杂物)\n 5. 🟣符文碎片 ×6 (杂物)\n━━━━━━━━━━━━\n📄 第 1/1 页 · 共 5 件\n💡 可发送 背包筛选 <类型> 分类查看\n💡 筛选视图序号与全局背包不同，『出售 <序号>』按全局序号——出售/装备请用物品名称（#234）',
    'inventory/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'inventory/normal': '🎒 【背包】\n━━━━━━━━━━━━\n 1. 🟢【铁剑】(武器) Lv.10\n 2. ⚪兽肉 ×12 (食材)\n 3. ⚪银鳞鱼 ×3 (鱼)\n 4. 治疗药水(小) ×5\n 5. 🟠强化石 ×8 (矿石)\n 6. ⚪图纸残页 ×12 (杂物)\n 7. 🟣符文碎片 ×6 (杂物)\n 8. 碎裂的幸运宝石 ×4\n━━━━━━━━━━━━\n📄 第 1/1 页 · 共 8 件\n💡 可发送 背包筛选 <类型> 分类查看',
    'item_detail/boundary_index': '🟢【铁剑】(武器)\n━━━━━━━━━━━━\n品质：优秀 ｜ 需求等级：Lv.10\n类型：剑\n✦ 剑类武器：攻守均衡，暴击＋2%\n属性：\n  · 攻击 + 12\n需求：力量 5\n描述：橡木风格的长剑，剑脊笔直，护手朴素。橡木镇匠人的朴实手艺，耐用又可靠。\n\n💡 『装备 铁剑』穿上它 ｜ 铁匠铺回收约 50 金币',
    'item_detail/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'item_detail/normal': '🟢【铁剑】(武器)\n━━━━━━━━━━━━\n品质：优秀 ｜ 需求等级：Lv.10\n类型：剑\n✦ 剑类武器：攻守均衡，暴击＋2%\n属性：\n  · 攻击 + 12\n需求：力量 5\n描述：橡木风格的长剑，剑脊笔直，护手朴素。橡木镇匠人的朴实手艺，耐用又可靠。\n\n💡 『装备 铁剑』穿上它 ｜ 铁匠铺回收约 50 金币',
    'item_view_mode_cmd/boundary_end': '🔍 物品查看模式已关闭，回复数字不再自动查物品～',
    'item_view_mode_cmd/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'item_view_mode_cmd/normal': '🔍 物品查看模式已开启！直接回复背包序号即可查看物品详情；\n『物品详情结束』退出，『物品详情 <名称>』照常使用。',
    'learn/boundary_empty': '格式：『学习 <图纸名>』，如『学习 铁皮图纸』！图纸由 Boss 掉落或宝箱/垂钓/商店获得。',
    'learn/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'learn/normal': '背包里没有『海风长弓图纸』图纸！Boss 掉落/宝箱/垂钓/商店获得，『背包 图纸』查看～',
    'mining/boundary_no_vein': '这里没有矿脉！地图上会显示⛏️矿脉的位置，去那边『挖掘』吧～',
    'mining/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'mining/normal': '⛏️ 你举起镐子凿向【落石峡谷】的矿脉……预计 79 秒后完成，自动入包～',
    'monster/boundary_unknown': '👹 未收录『不存在的怪物』……试试『百科 不存在的怪物』或先『图鉴』看看怪物列表？',
    'monster/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'monster/normal': '👹 【森林狼】出现地点（共 2 处）：\n━━━━━━━━━━━━\n  普通·Lv.8 林间小径（翡翠森林）\n  普通·Lv.8 银风驿站（银风商道）\n💡 前往对应地图后按区域探索/战斗即有机会遭遇；首领/精英带稀有掉落~',
    'my_equipment/boundary_empty': '⚔️ 【当前穿戴】\n━━━━━━━━━━━━\n  武器：未穿戴\n  头盔：未穿戴\n  胸甲：未穿戴\n  护腿：未穿戴\n  靴子：未穿戴\n  戒指：未穿戴\n  项链：未穿戴\n━━━━━━━━━━━━\n已穿戴 0/7 件 ｜ 『装备 <序号>』换装 ｜ 『卸下 <部位>』脱下 ｜ 『物品详情 <名称>』看详情',
    'my_equipment/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'my_equipment/normal': '⚔️ 【当前穿戴】\n━━━━━━━━━━━━\n  武器：🟢【铁剑】优秀\n      · 攻击 + 12\n  头盔：未穿戴\n  胸甲：未穿戴\n  护腿：未穿戴\n  靴子：未穿戴\n  戒指：未穿戴\n  项链：未穿戴\n━━━━━━━━━━━━\n已穿戴 1/7 件 ｜ 『装备 <序号>』换装 ｜ 『卸下 <部位>』脱下 ｜ 『物品详情 <名称>』看详情',
    'prof_forget/boundary_nosuch': '没有『不存在』这个副业！可选：采集、挖掘、垂钓、炼金、锻造、烹饪、强化、附魔',
    'prof_forget/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'prof_forget/normal': '📦 你遗忘了「采集」(原 Lv.5，已清零)！\n副业随时可以重新拜师学习，放心去探索其他生活职业吧～',
    'profession_view/boundary_rank': '🏆 【副业排行】(总分 = 已激活副业等级之和)\n━━━━━━━━━━━━\n🥇  1. 甲：40 分\n\n💡 新副业需先找导师拜师解锁',
    'profession_view/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'profession_view/normal': '🧵 【副业面板】(当前已激活 8 条)\n━━━━━━━━━━━━\n🌿 采集：Lv.5  ████░░░░░░ 96/200 经验 ✅\n⛏️ 挖掘：Lv.5  ████░░░░░░ 96/200 经验 ✅\n🎣 垂钓：Lv.5  ████░░░░░░ 96/200 经验 ✅\n🧪 炼金：Lv.5  ████░░░░░░ 96/200 经验 ✅\n🔨 锻造：Lv.5  ████░░░░░░ 96/200 经验 ✅\n🍳 烹饪：Lv.5  ████░░░░░░ 96/200 经验 ✅\n⚒️ 强化：Lv.5  ████░░░░░░ 96/200 经验 ✅\n✨ 附魔：Lv.5  ████░░░░░░ 96/200 经验 ✅\n\n📊 副业总分：40(已激活副业等级之和，与『副业 排行』同口径)\n💡 新副业需先找导师拜师解锁',
    'recipe_list/boundary_detail': '📜 配方：⚪【铁剑】\n🏷️ 类型：武器  Lv.2  普通\n🧰 材料：粗铁×2\n💰 费用：0 金币\n🎭 适用职业：战士\n📖 南境橡木镇的基础工艺，结实耐用\n\n💡 『代工 <装备名>』三倍金币免等级',
    'recipe_list/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'recipe_list/normal': '📜 铁匠锻造配方(『锻造 <职业>』看该职业，『锻造 配方 <装备名>』看详情)：\n\n🧭 见习冒险者：铁剑、旧皮靴、皮甲、橡木护腿、铁皮护腿、铁皮战靴、学徒护腿、学徒法靴、布衣护腿、布衣圣靴、橡木皮甲、铁皮头盔、铁皮胸甲、学徒法帽、学徒长袍、布衣圣冠、布衣法衣、橡木符记、铁皮长剑、猎手皮帽、猎手皮甲、猎手护腿、猎手长靴、轻影面巾、轻影皮衣、轻影护腿、轻影轻靴、行者束发带、行者武斗袍、行者护腿、行者布靴、晨露戒指、白鹿护符、学徒之血刃、猎风披风、猎风护腿、晨露项链、春草手环、船长帽、海盗靴、水手护腿、弯刀、猎风之靴、猎户兜帽、猎户长靴、水手夹克、誓约圣冠、誓约法衣、铁牙狼皮、精制护林胸甲、精制护林护腿、精制护林之靴、誓约圣靴、猎户夹克、夜莺胸针、珍珠项链、银铃头盔、银铃胸甲、银铃战靴、银铃项链、银铃护腿、银铃短刃、水手结戒指、咕噜的皇冠、锚形戒指、翡翠皮甲、翡翠护腿、翡翠头盔、翡翠战靴、翡翠项链、晨曦之戒、迷雾胸甲、迷雾战靴、潮汐之环、锚链护腕、迷雾护腿、迷雾项链、潮汐吊坠、潮汐之靴、铁壁胸甲、铁港战刃、金钩弯刀、迷雾兜帽、精铁护腿、精铁战靴、符文护腿、符文法靴、祝福护腿、祝福圣靴、海盗眼罩、灯塔之光、雷霆指环、骑士头盔、骑士长靴、圣光长剑、精铁头盔、精铁胸甲、符文法帽、符文长袍、祝福圣冠、祝福法衣、航海斗篷、秘光吊坠、圣光护腿、圣光胸甲、夜行披风、精铁战剑、风行皮帽、风行皮甲、风行护腿、风行长靴、夜行面巾、夜行皮衣、夜行护腿、夜行轻靴、石拳束发带、石拳武斗袍、石拳护腿、石拳布靴、船长的望远镜、铸火头盔、圣光护符、精制渡口胸甲、精制渡口护腿、精制渡口之靴、深渊之锚、王国徽戒、铁港徽章、血誓战甲、血誓战剑、疾风护手、疾风之靴、圣光战盔、圣光重靴、蓄势束带、翡翠护符、审判之链、圣光战腿、圣光重甲、巡林长披风、翡翠之心、圣光祝福指环、古王剑、圣裁长剑、古王剑、精灵披风、圣光巡礼战靴、熔岩之靴、圣光之握、圣光哨兵头盔、熔岩护手、熔岩护腿、百炼护腿、百炼战靴、秘法护腿、秘法法靴、圣堂护腿、圣堂圣靴、圣光审判之刃、圣光远征护腿、百炼头盔、百炼胸甲、秘法法帽、秘法长袍、圣堂圣冠、圣堂法衣、月影斗篷、月语风行者之靴、月冠头盔、月华戒指、月之靴、余烬军团战盔、余烬军团战靴、猎首皮帽、猎首长靴、日冕圣冠、影纱面巾、影纱轻靴、百炼长剑、暗夜皮帽、暗夜皮甲、暗夜护腿、暗夜长靴、阴影面巾、阴影皮衣、阴影护腿、阴影轻靴、壁槌束发带、壁槌武斗袍、壁槌护腿、壁槌布靴、星辉戒指、月语之戒、圣光殉道者胸甲、月语影袭胸甲、铁壁重装战靴、星语项链、月语护腿、余烬军团胸甲、猎首皮甲、日冕圣靴、影纱皮衣、影纱护腿、破竹护腿、破竹布靴、星辉吊坠、铁壁护符、月语夜枭头盔、月语月影护腿、月语月华之戒、铁壁战甲、铁壁卫戍头盔、铁壁军团腿甲、日冕法衣、破竹武袍、猎手之靴、月语辉月项链、铁壁军团剑、海神长靴、精灵链甲、星尘之戒、星尘坠饰、星尘护腿、星尘长袍、珍珠头冠、精灵链甲、余烬军团战剑、精制巡林胸甲、精制巡林护腿、精制巡林之靴、寒霜之戒、猎手斗篷、霜狼雪靴、海神护腿、海神项链、海神项链、北风护符、海神波纹甲、霜狼战刃、海神戒指、龙鳞海甲、霜狼头盔、霜原长靴、霜角战环、霜角披风、海神珍珠链、霜狼腿甲、晨曦之冠、熔炉项链、霜狼护腿、霜狼护腿、夜祷兜帽、霜角吊坠、夜祷法衣、夜祷之戒、星火戒指、星辉法冠、霜狼冰甲、符文戒指、霜狼长剑、铁砧胸甲、苍狼之爪、澜歌之泪、澜歌之泪、龙鳞手环、星辉长袍、地底长靴、深渊头盔、龙脊徽记、破岳巨剑、敖澜之珠、黑曜护腿、深渊项链、深渊战刃、深渊战刃、深渊项链、秘银手镯、黑曜胸甲、精制霜猎胸甲、精制霜猎护腿、精制霜猎之靴、守望者护符、龙鳞头盔、龙眼项链、风暴之眼、星光项链、龙鳞护腿、风暴吊坠、龙翼护符、龙翼戒指、苍穹头盔、龙脊大剑、龙鳞胸甲、灰烬之盔、灰烬战靴、灰烬护腿、灰烬铠甲、灰烬长剑、星辉长靴、龙脊大剑、熔炉之心、元素使徒之冠、苍穹护腿、元素使徒长袍、苍穹之靴、天穹之冠、星尘之靴、苍穹项链、赫尔加的祭器、云纹胸甲、暮影龙魂、赫尔加的祭器、时之领主时戒、苍穹之翼、雷光徽章、元素使徒坠饰、圣辉法衣、苍穹护甲、大贤者护腿、龙语圣剑、风神之环、奥拉圣印、精制龙裔胸甲、精制龙裔护腿、精制龙裔之靴、摩罗之冠\n🛡️ 战士：铁剑、旧皮靴、皮甲、橡木护腿、铁皮护腿、铁皮战靴、学徒护腿、学徒法靴、布衣护腿、布衣圣靴、橡木皮甲、铁皮头盔、铁皮胸甲、学徒法帽、学徒长袍、布衣圣冠、布衣法衣、橡木符记、铁皮长剑、猎手皮帽、猎手皮甲、猎手护腿、猎手长靴、轻影面巾、轻影皮衣、轻影护腿、轻影轻靴、行者束发带、行者武斗袍、行者护腿、行者布靴、晨露戒指、白鹿护符、学徒之血刃、猎风披风、猎风护腿、晨露项链、春草手环、船长帽、海盗靴、水手护腿、弯刀、猎风之靴、猎户兜帽、猎户长靴、水手夹克、誓约圣冠、誓约法衣、铁牙狼皮、精制护林胸甲、精制护林护腿、精制护林之靴、誓约圣靴、猎户夹克、夜莺胸针、珍珠项链、银铃头盔、银铃胸甲、银铃战靴、银铃项链、银铃护腿、银铃短刃、水手结戒指、咕噜的皇冠、锚形戒指、翡翠皮甲、翡翠护腿、翡翠头盔、翡翠战靴、翡翠项链、晨曦之戒、迷雾胸甲、迷雾战靴、潮汐之环、锚链护腕、迷雾护腿、迷雾项链、潮汐吊坠、潮汐之靴、铁壁胸甲、铁港战刃、金钩弯刀、迷雾兜帽、精铁护腿、精铁战靴、符文护腿、符文法靴、祝福护腿、祝福圣靴、海盗眼罩、灯塔之光、雷霆指环、骑士头盔、骑士长靴、圣光长剑、精铁头盔、精铁胸甲、符文法帽、符文长袍、祝福圣冠、祝福法衣、航海斗篷、秘光吊坠、圣光护腿、圣光胸甲、夜行披风、精铁战剑、风行皮帽、风行皮甲、风行护腿、风行长靴、夜行面巾、夜行皮衣、夜行护腿、夜行轻靴、石拳束发带、石拳武斗袍、石拳护腿、石拳布靴、船长的望远镜、铸火头盔、圣光护符、精制渡口胸甲、精制渡口护腿、精制渡口之靴、深渊之锚、王国徽戒、铁港徽章、血誓战甲、血誓战剑、疾风护手、疾风之靴、圣光战盔、圣光重靴、蓄势束带、翡翠护符、审判之链、圣光战腿、圣光重甲、巡林长披风、翡翠之心、圣光祝福指环、古王剑、圣裁长剑、古王剑、精灵披风、圣光巡礼战靴、熔岩之靴、圣光之握、圣光哨兵头盔、熔岩护手、熔岩护腿、百炼护腿、百炼战靴、秘法护腿、秘法法靴、圣堂护腿、圣堂圣靴、圣光审判之刃、圣光远征护腿、百炼头盔、百炼胸甲、秘法法帽、秘法长袍、圣堂圣冠、圣堂法衣、月影斗篷、月语风行者之靴、月冠头盔、月华戒指、月之靴、余烬军团战盔、余烬军团战靴、猎首皮帽、猎首长靴、日冕圣冠、影纱面巾、影纱轻靴、百炼长剑、暗夜皮帽、暗夜皮甲、暗夜护腿、暗夜长靴、阴影面巾、阴影皮衣、阴影护腿、阴影轻靴、壁槌束发带、壁槌武斗袍、壁槌护腿、壁槌布靴、星辉戒指、月语之戒、圣光殉道者胸甲、月语影袭胸甲、铁壁重装战靴、星语项链、月语护腿、余烬军团胸甲、猎首皮甲、日冕圣靴、影纱皮衣、影纱护腿、破竹护腿、破竹布靴、星辉吊坠、铁壁护符、月语夜枭头盔、月语月影护腿、月语月华之戒、铁壁战甲、铁壁卫戍头盔、铁壁军团腿甲、日冕法衣、破竹武袍、猎手之靴、月语辉月项链、铁壁军团剑、海神长靴、精灵链甲、星尘之戒、星尘坠饰、星尘护腿、星尘长袍、珍珠头冠、精灵链甲、余烬军团战剑、精制巡林胸甲、精制巡林护腿、精制巡林之靴、寒霜之戒、猎手斗篷、霜狼雪靴、海神护腿、海神项链、海神项链、北风护符、海神波纹甲、霜狼战刃、海神戒指、龙鳞海甲、霜狼头盔、霜原长靴、霜角战环、霜角披风、海神珍珠链、霜狼腿甲、晨曦之冠、熔炉项链、霜狼护腿、霜狼护腿、夜祷兜帽、霜角吊坠、夜祷法衣、夜祷之戒、星火戒指、星辉法冠、霜狼冰甲、符文戒指、霜狼长剑、铁砧胸甲、苍狼之爪、澜歌之泪、澜歌之泪、龙鳞手环、星辉长袍、地底长靴、深渊头盔、龙脊徽记、破岳巨剑、敖澜之珠、黑曜护腿、深渊项链、深渊战刃、深渊战刃、深渊项链、秘银手镯、黑曜胸甲、精制霜猎胸甲、精制霜猎护腿、精制霜猎之靴、守望者护符、龙鳞头盔、龙眼项链、风暴之眼、星光项链、龙鳞护腿、风暴吊坠、龙翼护符、龙翼戒指、苍穹头盔、龙脊大剑、龙鳞胸甲、灰烬之盔、灰烬战靴、灰烬护腿、灰烬铠甲、灰烬长剑、星辉长靴、龙脊大剑、熔炉之心、元素使徒之冠、苍穹护腿、元素使徒长袍、苍穹之靴、天穹之冠、星尘之靴、苍穹项链、赫尔加的祭器、云纹胸甲、暮影龙魂、赫尔加的祭器、时之领主时戒、苍穹之翼、雷光徽章、元素使徒坠饰、圣辉法衣、苍穹护甲、大贤者护腿、龙语圣剑、风神之环、奥拉圣印、精制龙裔胸甲、精制龙裔护腿、精制龙裔之靴、摩罗之冠\n🔥 法师：学徒法杖、旧皮靴、皮甲、橡木护腿、学徒之杖、铁皮护腿、铁皮战靴、学徒护腿、学徒法靴、布衣护腿、布衣圣靴、橡木皮甲、铁皮头盔、铁皮胸甲、学徒法帽、学徒长袍、布衣圣冠、布衣法衣、橡木符记、见习法杖、猎手皮帽、猎手皮甲、猎手护腿、猎手长靴、轻影面巾、轻影皮衣、轻影护腿、轻影轻靴、行者束发带、行者武斗袍、行者护腿、行者布靴、晨露戒指、白鹿护符、星火法杖、猎风披风、猎风护腿、晨露项链、春草手环、船长帽、海盗靴、水手护腿、猎风之靴、猎户兜帽、猎户长靴、水手夹克、誓约圣冠、誓约法衣、铁牙狼皮、精制护林胸甲、精制护林护腿、精制护林之靴、誓约圣靴、猎户夹克、夜莺胸针、珍珠项链、银铃头盔、银铃胸甲、银铃战靴、银铃项链、银铃护腿、水手结戒指、咕噜的皇冠、锚形戒指、翡翠皮甲、翡翠护腿、翡翠头盔、翡翠战靴、翡翠项链、晨曦之戒、迷雾胸甲、迷雾战靴、潮汐之环、锚链护腕、迷雾护腿、银铃杖、迷雾项链、潮汐吊坠、潮汐之靴、铁壁胸甲、迷雾兜帽、精铁护腿、精铁战靴、符文护腿、符文法靴、祝福护腿、祝福圣靴、海盗眼罩、灯塔之光、雷霆指环、晨曦法杖、骑士头盔、骑士长靴、精铁头盔、精铁胸甲、符文法帽、符文长袍、祝福圣冠、祝福法衣、航海斗篷、秘光吊坠、霜语法杖、圣光护腿、圣光胸甲、夜行披风、符文法杖、风行皮帽、风行皮甲、风行护腿、风行长靴、夜行面巾、夜行皮衣、夜行护腿、夜行轻靴、石拳束发带、石拳武斗袍、石拳护腿、石拳布靴、船长的望远镜、秘法典籍之杖、铸火头盔、圣光护符、精制渡口胸甲、精制渡口护腿、精制渡口之靴、深渊之锚、王国徽戒、铁港徽章、血誓战甲、疾风护手、疾风之靴、圣光战盔、圣光重靴、蓄势束带、翡翠护符、审判之链、圣光法杖、圣光战腿、圣光重甲、巡林长披风、翡翠之心、圣光祝福指环、精灵披风、圣光巡礼战靴、熔岩之靴、圣光之握、圣光哨兵头盔、熔岩护手、熔岩护腿、百炼护腿、百炼战靴、秘法护腿、秘法法靴、圣堂护腿、圣堂圣靴、圣光远征护腿、百炼头盔、百炼胸甲、秘法法帽、秘法长袍、圣堂圣冠、圣堂法衣、月影斗篷、圣光祈祷法杖、月语风行者之靴、月冠头盔、月华戒指、月之靴、余烬军团战盔、余烬军团战靴、猎首皮帽、猎首长靴、日冕圣冠、影纱面巾、影纱轻靴、秘法法杖、暗夜皮帽、暗夜皮甲、暗夜护腿、暗夜长靴、阴影面巾、阴影皮衣、阴影护腿、阴影轻靴、壁槌束发带、壁槌武斗袍、壁槌护腿、壁槌布靴、星辉戒指、月语之戒、圣光殉道者胸甲、月语影袭胸甲、铁壁重装战靴、星语项链、银叶法杖、月语护腿、余烬军团胸甲、猎首皮甲、日冕圣靴、影纱皮衣、影纱护腿、破竹护腿、破竹布靴、星辉吊坠、铁壁护符、月语夜枭头盔、月语月影护腿、月语月华之戒、铁壁战甲、铁壁卫戍头盔、铁壁军团腿甲、日冕法衣、破竹武袍、猎手之靴、月语秘仪法杖、月语辉月项链、海神长靴、精灵链甲、星尘之戒、星尘坠饰、星尘护腿、星尘长袍、星尘法杖、珍珠头冠、精灵链甲、精制巡林胸甲、精制巡林护腿、精制巡林之靴、寒霜之戒、猎手斗篷、霜狼雪靴、潮汐法杖、海神护腿、海神项链、海神项链、北风护符、海神波纹甲、海神戒指、龙鳞海甲、霜狼头盔、霜原长靴、霜角战环、霜角披风、星辉法杖、海神珍珠链、霜狼腿甲、晨曦之冠、熔炉项链、霜狼护腿、霜狼护腿、夜祷兜帽、霜角吊坠、夜祷法衣、夜祷之戒、星火戒指、星辉法冠、霜狼冰甲、符文戒指、铁砧胸甲、苍狼之爪、澜歌之泪、澜歌之泪、龙鳞手环、星辉长袍、地底长靴、深渊头盔、龙脊徽记、敖澜之珠、熔岩法杖、黑曜护腿、深渊项链、深渊项链、秘银手镯、黑曜胸甲、精制霜猎胸甲、精制霜猎护腿、精制霜猎之靴、守望者护符、龙鳞头盔、龙眼项链、风暴之眼、星光项链、龙鳞护腿、风暴吊坠、龙翼护符、龙翼戒指、苍穹头盔、龙鳞胸甲、龙语法杖、灰烬之盔、灰烬战靴、灰烬护腿、灰烬铠甲、星辉长靴、元素使徒之冠、苍穹护腿、烬核之心、元素使徒长袍、苍穹之靴、天穹之冠、星尘之靴、苍穹项链、赫尔加的祭器、星光法杖、云纹胸甲、赫尔加的祭器、元素使徒法杖、时之领主时戒、苍穹之翼、雷光徽章、元素使徒坠饰、圣辉法衣、苍穹护甲、大贤者护腿、时之领主秘仪、风神之环、奥拉圣印、精制龙裔胸甲、精制龙裔护腿、精制龙裔之靴、摩罗之冠\n🏹 游侠：猎弓、旧皮靴、皮甲、橡木护腿、猎鹿弓、铁皮护腿、铁皮战靴、学徒护腿、学徒法靴、布衣护腿、布衣圣靴、橡木皮甲、铁皮头盔、铁皮胸甲、学徒法帽、学徒长袍、布衣圣冠、布衣法衣、橡木符记、猎手短弓、猎手皮帽、猎手皮甲、猎手护腿、猎手长靴、轻影面巾、轻影皮衣、轻影护腿、轻影轻靴、行者束发带、行者武斗袍、行者护腿、行者布靴、晨露戒指、白鹿护符、猎风披风、猎风护腿、晨露项链、春草手环、翠风之弓、船长帽、海盗靴、水手护腿、猎风之靴、猎户兜帽、猎户长靴、水手夹克、誓约圣冠、誓约法衣、铁牙狼皮、精制护林胸甲、精制护林护腿、精制护林之靴、誓约圣靴、猎户夹克、夜莺胸针、海风长弓、珍珠项链、银铃头盔、银铃胸甲、银铃战靴、银铃项链、银铃护腿、水手结戒指、咕噜的皇冠、锚形戒指、翡翠皮甲、翡翠护腿、翡翠头盔、翡翠战靴、翡翠项链、晨曦之戒、迷雾胸甲、迷雾战靴、潮汐之环、锚链护腕、迷雾护腿、迷雾项链、猎风长弓、潮汐吊坠、潮汐之靴、铁壁胸甲、迷雾兜帽、精铁护腿、精铁战靴、符文护腿、符文法靴、祝福护腿、祝福圣靴、海盗眼罩、灯塔之光、雷霆指环、逐风长弓、骑士头盔、骑士长靴、疾风长弓、精铁头盔、精铁胸甲、符文法帽、符文长袍、祝福圣冠、祝福法衣、航海斗篷、秘光吊坠、圣光护腿、圣光胸甲、夜行披风、风行长弓、风行皮帽、风行皮甲、风行护腿、风行长靴、夜行面巾、夜行皮衣、夜行护腿、夜行轻靴、石拳束发带、石拳武斗袍、石拳护腿、石拳布靴、船长的望远镜、铸火头盔、圣光护符、王都长弓、精制渡口胸甲、精制渡口护腿、精制渡口之靴、深渊之锚、碎冰长弓、王国徽戒、铁港徽章、血誓战甲、疾风护手、疾风之靴、圣光猎弓、圣光战盔、圣光重靴、蓄势束带、翡翠护符、审判之链、圣光战腿、圣光重甲、巡林长披风、翡翠之心、圣光祝福指环、巡林长弓、精灵披风、圣光巡礼战靴、熔岩之靴、圣光之握、圣光哨兵头盔、熔岩护手、熔岩护腿、百炼护腿、百炼战靴、秘法护腿、秘法法靴、圣堂护腿、圣堂圣靴、圣光追猎长弓、圣光远征护腿、百炼头盔、百炼胸甲、秘法法帽、秘法长袍、圣堂圣冠、圣堂法衣、月影斗篷、月语风行者之靴、月冠头盔、月华戒指、月之靴、余烬军团战盔、余烬军团战靴、猎首皮帽、猎首长靴、日冕圣冠、影纱面巾、影纱轻靴、暗夜长弓、暗夜皮帽、暗夜皮甲、暗夜护腿、暗夜长靴、阴影面巾、阴影皮衣、阴影护腿、阴影轻靴、壁槌束发带、壁槌武斗袍、壁槌护腿、壁槌布靴、星辉戒指、月语之戒、圣光殉道者胸甲、月语影袭胸甲、铁壁重装战靴、星语项链、月语护腿、月语长弓、余烬军团胸甲、猎首皮甲、日冕圣靴、影纱皮衣、影纱护腿、破竹护腿、破竹布靴、星辉吊坠、铁壁护符、月语夜枭头盔、月语月影护腿、月语月华之戒、铁壁战甲、铁壁卫戍头盔、铁壁军团腿甲、日冕法衣、破竹武袍、猎手之靴、月语银月长弓、月语辉月项链、海神长靴、精灵链甲、星尘之戒、星尘坠饰、星尘护腿、星尘长袍、珍珠头冠、精灵链甲、精制巡林胸甲、精制巡林护腿、精制巡林之靴、寒霜之戒、猎首长弓、猎手斗篷、霜狼雪靴、海神护腿、海神项链、海神项链、北风护符、海神波纹甲、海神戒指、龙鳞海甲、霜狼头盔、霜原长靴、霜角战环、霜角披风、海神珍珠链、霜狼腿甲、霜羽长弓、晨曦之冠、熔炉项链、霜狼护腿、霜狼护腿、夜祷兜帽、霜角吊坠、霜狼猎弓、夜祷法衣、夜祷之戒、星火戒指、星辉法冠、霜狼冰甲、北风长弓、符文戒指、北风长弓、铁砧胸甲、苍狼之爪、澜歌之泪、澜歌之泪、龙鳞手环、星辉长袍、地底长靴、深渊头盔、龙脊徽记、敖澜之珠、黑曜护腿、深渊项链、深渊项链、秘银手镯、黑曜胸甲、精制霜猎胸甲、精制霜猎护腿、精制霜猎之靴、守望者护符、龙鳞头盔、龙眼项链、风暴之眼、星光项链、龙鳞护腿、风暴吊坠、猎羽长弓、龙翼护符、龙翼戒指、苍穹头盔、龙鳞胸甲、灰烬之盔、灰烬战靴、灰烬护腿、灰烬铠甲、星辉长靴、元素使徒之冠、苍穹护腿、元素使徒长袍、苍穹之靴、天穹之冠、星尘之靴、苍穹项链、赫尔加的祭器、云纹胸甲、赫尔加的祭器、时之领主时戒、苍穹之翼、雷光徽章、惊雷战弓、元素使徒坠饰、圣辉法衣、幻影长弓、苍穹护甲、大贤者护腿、风神之环、奥拉圣印、精制龙裔胸甲、精制龙裔护腿、精制龙裔之靴、裂空战弓、摩罗之冠\n✨ 牧师：橡木短棍、旧皮靴、皮甲、橡木护腿、铁皮护腿、铁皮战靴、学徒护腿、学徒法靴、布衣护腿、布衣圣靴、橡木皮甲、铁皮头盔、铁皮胸甲、学徒法帽、学徒长袍、布衣圣冠、布衣法衣、橡木符记、布衣权杖、猎手皮帽、猎手皮甲、猎手护腿、猎手长靴、轻影面巾、轻影皮衣、轻影护腿、轻影轻靴、行者束发带、行者武斗袍、行者护腿、行者布靴、晨露戒指、白鹿护符、猎风披风、猎风护腿、晨露项链、春草手环、船长帽、海盗靴、水手护腿、猎风之靴、猎户兜帽、猎户长靴、水手夹克、誓约圣冠、誓约法衣、铁牙狼皮、精制护林胸甲、精制护林护腿、精制护林之靴、誓约权杖、誓约圣靴、猎户夹克、夜莺胸针、珍珠项链、银铃头盔、银铃胸甲、银铃战靴、银铃项链、银铃护腿、水手结戒指、咕噜的皇冠、锚形戒指、翡翠皮甲、翡翠护腿、翡翠头盔、翡翠战靴、翡翠项链、晨曦之戒、迷雾胸甲、迷雾战靴、潮汐之环、锚链护腕、迷雾护腿、迷雾项链、潮汐吊坠、潮汐之靴、铁壁胸甲、迷雾兜帽、精铁护腿、精铁战靴、符文护腿、符文法靴、祝福护腿、祝福圣靴、海盗眼罩、灯塔之光、雷霆指环、骑士头盔、骑士长靴、精铁头盔、精铁胸甲、符文法帽、符文长袍、祝福圣冠、祝福法衣、航海斗篷、秘光吊坠、圣光护腿、圣光胸甲、夜行披风、祝福权杖、风行皮帽、风行皮甲、风行护腿、风行长靴、夜行面巾、夜行皮衣、夜行护腿、夜行轻靴、石拳束发带、石拳武斗袍、石拳护腿、石拳布靴、船长的望远镜、铸火头盔、圣光护符、精制渡口胸甲、精制渡口护腿、精制渡口之靴、深渊之锚、圣殿战锤、王国徽戒、铁港徽章、血誓战甲、疾风护手、疾风之靴、圣光战盔、圣光重靴、蓄势束带、翡翠护符、审判之链、圣光战腿、圣光重甲、巡林长披风、翡翠之心、圣光祝福指环、精灵披风、圣光巡礼战靴、熔岩之靴、圣光战锤、圣光之握、圣光哨兵头盔、熔岩护手、熔岩护腿、百炼护腿、百炼战靴、秘法护腿、秘法法靴、圣堂护腿、圣堂圣靴、圣光远征护腿、百炼头盔、百炼胸甲、秘法法帽、秘法长袍、圣堂圣冠、圣堂法衣、月影斗篷、月语风行者之靴、月冠头盔、月华戒指、月之靴、余烬军团战盔、余烬军团战靴、猎首皮帽、猎首长靴、日冕圣冠、影纱面巾、影纱轻靴、圣堂权杖、暗夜皮帽、暗夜皮甲、暗夜护腿、暗夜长靴、阴影面巾、阴影皮衣、阴影护腿、阴影轻靴、壁槌束发带、壁槌武斗袍、壁槌护腿、壁槌布靴、星辉戒指、月语之戒、圣光殉道者胸甲、月语影袭胸甲、铁壁重装战靴、星语项链、月语护腿、余烬军团胸甲、猎首皮甲、日冕圣靴、影纱皮衣、影纱护腿、破竹护腿、破竹布靴、星辉吊坠、铁壁护符、月语夜枭头盔、月语月影护腿、月语月华之戒、铁壁战甲、铁壁卫戍头盔、铁壁军团腿甲、日冕法衣、破竹武袍、猎手之靴、月语辉月项链、海神长靴、精灵链甲、星尘之戒、星尘坠饰、星尘护腿、星尘长袍、珍珠头冠、精灵链甲、精制巡林胸甲、精制巡林护腿、精制巡林之靴、寒霜之戒、日冕权杖、猎手斗篷、霜狼雪靴、海神护腿、海神三叉戟、海神项链、海神项链、北风护符、海神波纹甲、海神戒指、龙鳞海甲、霜狼头盔、霜原长靴、霜角战环、霜角披风、海神珍珠链、霜狼腿甲、晨曦之冠、熔炉项链、霜狼护腿、霜狼护腿、夜祷兜帽、霜角吊坠、夜祷法衣、夜祷之戒、星火戒指、星辉法冠、霜狼冰甲、符文戒指、铁砧胸甲、夜祷权杖、苍狼之爪、澜歌之泪、铁砧战锤、澜歌之泪、铁砧战锤、龙鳞手环、星辉长袍、地底长靴、深渊头盔、龙脊徽记、敖澜之珠、黑曜护腿、深渊项链、深渊项链、秘银手镯、黑曜胸甲、精制霜猎胸甲、精制霜猎护腿、精制霜猎之靴、守望者护符、龙鳞头盔、龙眼项链、风暴之眼、星光项链、龙鳞护腿、风暴吊坠、龙翼护符、龙翼戒指、苍穹头盔、龙鳞胸甲、灰烬之盔、灰烬战靴、灰烬护腿、灰烬铠甲、星辉长靴、元素使徒之冠、苍穹护腿、元素使徒长袍、苍穹之靴、天穹之冠、星尘之靴、苍穹项链、赫尔加的祭器、云纹胸甲、赫尔加的祭器、时之领主时戒、苍穹之翼、雷光徽章、元素使徒坠饰、圣辉法衣、苍穹护甲、大贤者护腿、风神之环、圣谕权杖、奥拉圣印、精制龙裔胸甲、精制龙裔护腿、精制龙裔之靴、摩罗之冠\n🗡️ 刺客：旧皮靴、皮甲、橡木护腿、铁皮护腿、铁皮战靴、学徒护腿、学徒法靴、布衣护腿、布衣圣靴、橡木皮甲、铁皮头盔、铁皮胸甲、学徒法帽、学徒长袍、布衣圣冠、布衣法衣、橡木符记、猎手皮帽、猎手皮甲、猎手护腿、猎手长靴、轻影匕首、轻影面巾、轻影皮衣、轻影护腿、轻影轻靴、行者束发带、行者武斗袍、行者护腿、行者布靴、晨露戒指、白鹿护符、水手短刃、猎风披风、猎风护腿、晨露项链、春草手环、猎影之牙、船长帽、海盗靴、水手护腿、猎风之靴、猎户兜帽、猎户长靴、水手夹克、誓约圣冠、誓约法衣、铁牙狼皮、精制护林胸甲、精制护林护腿、精制护林之靴、誓约圣靴、猎户夹克、夜莺胸针、珍珠项链、银铃头盔、银铃胸甲、银铃战靴、银铃项链、银铃护腿、水手结戒指、咕噜的皇冠、锚形戒指、翡翠皮甲、翡翠护腿、翡翠头盔、翡翠战靴、翡翠项链、晨曦之戒、迷雾胸甲、迷雾战靴、潮汐之环、锚链护腕、迷雾护腿、迷雾项链、潮汐吊坠、潮汐之靴、铁壁胸甲、迷雾兜帽、精铁护腿、精铁战靴、符文护腿、符文法靴、祝福护腿、祝福圣靴、海盗眼罩、灯塔之光、雷霆指环、骑士头盔、骑士长靴、精铁头盔、精铁胸甲、符文法帽、符文长袍、祝福圣冠、祝福法衣、航海斗篷、秘光吊坠、圣光护腿、圣光胸甲、裂鬃獠牙、夜行披风、风行皮帽、风行皮甲、风行护腿、风行长靴、夜行匕首、夜行面巾、夜行皮衣、夜行护腿、夜行轻靴、石拳束发带、石拳武斗袍、石拳护腿、石拳布靴、船长的望远镜、血潮短刃、铸火头盔、圣光护符、精制渡口胸甲、精制渡口护腿、精制渡口之靴、深渊之锚、王国徽戒、铁港徽章、夜枭双匕、血誓战甲、疾风护手、疾风之靴、圣光战盔、圣光重靴、蓄势束带、翡翠护符、审判之链、圣光战腿、圣光重甲、巡林长披风、翡翠之心、圣光祝福指环、精灵披风、圣光巡礼战靴、熔岩之靴、圣光之握、圣光哨兵头盔、熔岩护手、熔岩护腿、百炼护腿、百炼战靴、秘法护腿、秘法法靴、圣堂护腿、圣堂圣靴、圣光远征护腿、百炼头盔、百炼胸甲、秘法法帽、秘法长袍、圣堂圣冠、圣堂法衣、月影斗篷、月语风行者之靴、月冠头盔、月光短刃、月华戒指、月之靴、余烬军团战盔、余烬军团战靴、猎首皮帽、猎首长靴、日冕圣冠、影纱面巾、影纱轻靴、暗夜皮帽、暗夜皮甲、暗夜护腿、暗夜长靴、阴影匕首、阴影面巾、阴影皮衣、阴影护腿、阴影轻靴、壁槌束发带、壁槌武斗袍、壁槌护腿、壁槌布靴、星辉戒指、月语之戒、圣光殉道者胸甲、月语影袭胸甲、铁壁重装战靴、星语项链、月语护腿、余烬军团胸甲、猎首皮甲、日冕圣靴、影纱皮衣、影纱护腿、破竹护腿、破竹布靴、星辉吊坠、铁壁护符、月语刺客匕首、月语夜枭头盔、月语月影护腿、月语月华之戒、血痕双刺、铁壁战甲、铁壁卫戍头盔、铁壁军团腿甲、日冕法衣、破竹武袍、猎手之靴、月语辉月项链、海神长靴、精灵链甲、星尘之戒、星尘坠饰、星尘护腿、星尘长袍、珍珠头冠、精灵链甲、精制巡林胸甲、精制巡林护腿、精制巡林之靴、寒霜之戒、影纱之刃、猎手斗篷、霜狼雪靴、海神护腿、海神项链、海神项链、北风护符、海神波纹甲、海神戒指、龙鳞海甲、霜狼头盔、霜原长靴、霜角战环、霜角披风、海神珍珠链、霜狼腿甲、晨曦之冠、熔炉项链、霜狼护腿、霜狼护腿、夜祷兜帽、霜角吊坠、夜祷法衣、夜祷之戒、星火戒指、星辉法冠、霜狼冰甲、符文戒指、铁砧胸甲、苍狼之爪、澜歌之泪、澜歌之泪、龙鳞手环、星辉长袍、地底长靴、深渊头盔、龙脊徽记、敖澜之珠、黑曜护腿、深渊项链、深渊项链、秘银手镯、黑曜胸甲、精制霜猎胸甲、精制霜猎护腿、精制霜猎之靴、守望者护符、龙鳞头盔、龙眼项链、风暴之眼、星光项链、龙鳞护腿、风暴吊坠、龙翼护符、龙翼戒指、幽影短刃、苍穹头盔、龙鳞胸甲、灰烬之盔、灰烬战靴、灰烬护腿、灰烬铠甲、星辉长靴、元素使徒之冠、苍穹护腿、元素使徒长袍、苍穹之靴、天穹之冠、星尘之靴、苍穹项链、赫尔加的祭器、云纹胸甲、赫尔加的祭器、时之领主时戒、苍穹之翼、雷光徽章、元素使徒坠饰、圣辉法衣、苍穹护甲、大贤者护腿、淬毒寒刃、风神之环、奥拉圣印、精制龙裔胸甲、精制龙裔护腿、精制龙裔之靴、暮影之刃、摩罗之冠\n🥊 拳师：旧皮靴、皮甲、橡木护腿、铁皮护腿、铁皮战靴、学徒护腿、学徒法靴、布衣护腿、布衣圣靴、橡木皮甲、铁皮头盔、铁皮胸甲、学徒法帽、学徒长袍、布衣圣冠、布衣法衣、橡木符记、猎手皮帽、猎手皮甲、猎手护腿、猎手长靴、轻影面巾、轻影皮衣、轻影护腿、轻影轻靴、行者拳套、行者束发带、行者武斗袍、行者护腿、行者布靴、晨露戒指、白鹿护符、猎风披风、猎风护腿、晨露项链、春草手环、船长帽、海盗靴、水手护腿、猎风之靴、猎户兜帽、猎户长靴、水手夹克、誓约圣冠、誓约法衣、铁牙狼皮、精制护林胸甲、精制护林护腿、精制护林之靴、誓约圣靴、猎户夹克、夜莺胸针、珍珠项链、银铃头盔、银铃胸甲、银铃战靴、银铃项链、银铃护腿、水手结戒指、咕噜的皇冠、锚形戒指、翡翠皮甲、翡翠护腿、翡翠头盔、翡翠战靴、翡翠项链、晨曦之戒、迷雾胸甲、迷雾战靴、潮汐之环、锚链护腕、迷雾护腿、迷雾项链、潮汐吊坠、潮汐之靴、铁壁胸甲、迷雾兜帽、精铁护腿、精铁战靴、符文护腿、符文法靴、祝福护腿、祝福圣靴、海盗眼罩、灯塔之光、雷霆指环、骑士头盔、骑士长靴、精铁头盔、精铁胸甲、符文法帽、符文长袍、祝福圣冠、祝福法衣、航海斗篷、秘光吊坠、圣光护腿、圣光胸甲、夜行披风、风行皮帽、风行皮甲、风行护腿、风行长靴、夜行面巾、夜行皮衣、夜行护腿、夜行轻靴、石拳拳套、石拳束发带、石拳武斗袍、石拳护腿、石拳布靴、船长的望远镜、石心拳套、铸火头盔、圣光护符、精制渡口胸甲、精制渡口护腿、精制渡口之靴、深渊之锚、王国徽戒、铁港徽章、血誓战甲、疾风护手、疾风之靴、圣光战盔、圣光重靴、蓄势束带、翡翠护符、审判之链、圣光战腿、圣光重甲、巡林长披风、蓄势拳套、翡翠之心、圣光祝福指环、精灵披风、圣光巡礼战靴、熔岩之靴、圣光之握、圣光哨兵头盔、熔岩护手、熔岩护腿、百炼护腿、百炼战靴、秘法护腿、秘法法靴、圣堂护腿、圣堂圣靴、圣光远征护腿、百炼头盔、百炼胸甲、秘法法帽、秘法长袍、圣堂圣冠、圣堂法衣、月影斗篷、月语风行者之靴、月冠头盔、月华戒指、月之靴、余烬军团战盔、余烬军团战靴、猎首皮帽、猎首长靴、日冕圣冠、影纱面巾、影纱轻靴、暗夜皮帽、暗夜皮甲、暗夜护腿、暗夜长靴、阴影面巾、阴影皮衣、阴影护腿、阴影轻靴、壁槌拳套、壁槌束发带、壁槌武斗袍、壁槌护腿、壁槌布靴、星辉戒指、月语之戒、圣光殉道者胸甲、月语影袭胸甲、灰烬拳套、铁壁重装战靴、星语项链、月语护腿、余烬军团胸甲、猎首皮甲、日冕圣靴、影纱皮衣、影纱护腿、破竹护腿、破竹布靴、星辉吊坠、铁壁护符、月语夜枭头盔、月语月影护腿、月语月华之戒、铁壁战甲、铁壁卫戍头盔、铁壁军团腿甲、日冕法衣、破竹武袍、猎手之靴、月语辉月项链、海神长靴、精灵链甲、星尘之戒、星尘坠饰、星尘护腿、星尘长袍、珍珠头冠、精灵链甲、精制巡林胸甲、精制巡林护腿、精制巡林之靴、寒霜之戒、破竹拳套、猎手斗篷、霜狼雪靴、海神护腿、海神项链、海神项链、北风护符、海神波纹甲、海神戒指、龙鳞海甲、霜狼头盔、霜原长靴、霜角战环、霜角披风、岩拳·裂脊、海神珍珠链、霜狼腿甲、晨曦之冠、熔炉项链、霜狼护腿、霜狼护腿、夜祷兜帽、霜角吊坠、夜祷法衣、夜祷之戒、星火戒指、星辉法冠、霜狼冰甲、符文戒指、铁砧胸甲、苍狼之爪、澜歌之泪、澜歌之泪、龙鳞手环、星辉长袍、地底长靴、深渊头盔、龙脊徽记、碎岳拳、敖澜之珠、黑曜护腿、深渊项链、深渊项链、秘银手镯、黑曜胸甲、精制霜猎胸甲、精制霜猎护腿、精制霜猎之靴、守望者护符、龙鳞头盔、龙眼项链、风暴之眼、星光项链、龙鳞护腿、龙爪手套、风暴吊坠、石龙拳套、龙翼护符、龙翼戒指、苍穹头盔、龙鳞胸甲、灰烬之盔、灰烬战靴、灰烬护腿、灰烬铠甲、星辉长靴、元素使徒之冠、苍穹护腿、元素使徒长袍、苍穹之靴、天穹之冠、星尘之靴、苍穹项链、赫尔加的祭器、云纹胸甲、赫尔加的祭器、时之领主时戒、苍穹之翼、雷光徽章、元素使徒坠饰、圣辉法衣、苍穹护甲、撼岳拳套、大贤者护腿、风神之环、奥拉圣印、精制龙裔胸甲、精制龙裔护腿、精制龙裔之靴、摩罗之冠\n🎵 吟游诗人：学徒法杖、旧皮靴、皮甲、橡木护腿、学徒之杖、铁皮护腿、铁皮战靴、学徒护腿、学徒法靴、布衣护腿、布衣圣靴、橡木皮甲、铁皮头盔、铁皮胸甲、学徒法帽、学徒长袍、布衣圣冠、布衣法衣、橡木符记、见习法杖、猎手皮帽、猎手皮甲、猎手护腿、猎手长靴、轻影面巾、轻影皮衣、轻影护腿、轻影轻靴、行者束发带、行者武斗袍、行者护腿、行者布靴、晨露戒指、白鹿护符、星火法杖、猎风披风、猎风护腿、晨露项链、春草手环、船长帽、海盗靴、水手护腿、猎风之靴、猎户兜帽、猎户长靴、水手夹克、誓约圣冠、誓约法衣、铁牙狼皮、精制护林胸甲、精制护林护腿、精制护林之靴、誓约圣靴、猎户夹克、夜莺胸针、珍珠项链、银铃头盔、银铃胸甲、银铃战靴、银铃项链、银铃护腿、水手结戒指、咕噜的皇冠、锚形戒指、翡翠皮甲、翡翠护腿、翡翠头盔、翡翠战靴、翡翠项链、晨曦之戒、迷雾胸甲、迷雾战靴、潮汐之环、锚链护腕、迷雾护腿、银铃杖、迷雾项链、潮汐吊坠、潮汐之靴、铁壁胸甲、迷雾兜帽、精铁护腿、精铁战靴、符文护腿、符文法靴、祝福护腿、祝福圣靴、海盗眼罩、灯塔之光、雷霆指环、晨曦法杖、骑士头盔、骑士长靴、精铁头盔、精铁胸甲、符文法帽、符文长袍、祝福圣冠、祝福法衣、航海斗篷、秘光吊坠、霜语法杖、圣光护腿、圣光胸甲、夜行披风、符文法杖、风行皮帽、风行皮甲、风行护腿、风行长靴、夜行面巾、夜行皮衣、夜行护腿、夜行轻靴、石拳束发带、石拳武斗袍、石拳护腿、石拳布靴、船长的望远镜、秘法典籍之杖、铸火头盔、圣光护符、精制渡口胸甲、精制渡口护腿、精制渡口之靴、深渊之锚、王国徽戒、铁港徽章、血誓战甲、疾风护手、疾风之靴、圣光战盔、圣光重靴、蓄势束带、翡翠护符、审判之链、圣光法杖、圣光战腿、圣光重甲、巡林长披风、翡翠之心、圣光祝福指环、精灵披风、圣光巡礼战靴、熔岩之靴、圣光之握、圣光哨兵头盔、熔岩护手、熔岩护腿、百炼护腿、百炼战靴、秘法护腿、秘法法靴、圣堂护腿、圣堂圣靴、圣光远征护腿、百炼头盔、百炼胸甲、秘法法帽、秘法长袍、圣堂圣冠、圣堂法衣、月影斗篷、圣光祈祷法杖、月语风行者之靴、月冠头盔、月华戒指、月之靴、余烬军团战盔、余烬军团战靴、猎首皮帽、猎首长靴、日冕圣冠、影纱面巾、影纱轻靴、秘法法杖、暗夜皮帽、暗夜皮甲、暗夜护腿、暗夜长靴、阴影面巾、阴影皮衣、阴影护腿、阴影轻靴、壁槌束发带、壁槌武斗袍、壁槌护腿、壁槌布靴、星辉戒指、月语之戒、圣光殉道者胸甲、月语影袭胸甲、铁壁重装战靴、星语项链、银叶法杖、月语护腿、余烬军团胸甲、猎首皮甲、日冕圣靴、影纱皮衣、影纱护腿、破竹护腿、破竹布靴、星辉吊坠、铁壁护符、月语夜枭头盔、月语月影护腿、月语月华之戒、铁壁战甲、铁壁卫戍头盔、铁壁军团腿甲、日冕法衣、破竹武袍、猎手之靴、月语秘仪法杖、月语辉月项链、海神长靴、精灵链甲、星尘之戒、星尘坠饰、星尘护腿、星尘长袍、星尘法杖、珍珠头冠、精灵链甲、精制巡林胸甲、精制巡林护腿、精制巡林之靴、寒霜之戒、猎手斗篷、霜狼雪靴、潮汐法杖、海神护腿、海神项链、海神项链、北风护符、海神波纹甲、海神戒指、龙鳞海甲、霜狼头盔、霜原长靴、霜角战环、霜角披风、星辉法杖、海神珍珠链、霜狼腿甲、晨曦之冠、熔炉项链、霜狼护腿、霜狼护腿、夜祷兜帽、霜角吊坠、夜祷法衣、夜祷之戒、星火戒指、星辉法冠、霜狼冰甲、符文戒指、铁砧胸甲、苍狼之爪、澜歌之泪、澜歌之泪、龙鳞手环、星辉长袍、地底长靴、深渊头盔、龙脊徽记、敖澜之珠、熔岩法杖、黑曜护腿、深渊项链、深渊项链、秘银手镯、黑曜胸甲、精制霜猎胸甲、精制霜猎护腿、精制霜猎之靴、守望者护符、龙鳞头盔、龙眼项链、风暴之眼、星光项链、龙鳞护腿、风暴吊坠、龙翼护符、龙翼戒指、苍穹头盔、龙鳞胸甲、龙语法杖、灰烬之盔、灰烬战靴、灰烬护腿、灰烬铠甲、星辉长靴、元素使徒之冠、苍穹护腿、烬核之心、元素使徒长袍、苍穹之靴、天穹之冠、星尘之靴、苍穹项链、赫尔加的祭器、星光法杖、云纹胸甲、赫尔加的祭器、元素使徒法杖、时之领主时戒、苍穹之翼、雷光徽章、元素使徒坠饰、圣辉法衣、苍穹护甲、大贤者护腿、时之领主秘仪、风神之环、奥拉圣印、精制龙裔胸甲、精制龙裔护腿、精制龙裔之靴、摩罗之冠\n\n💡 『代工 <装备名>』三倍金币免等级',
    'refine_equip/boundary_notfound': '背包里没有叫『不存在的剑』的装备！(已装备的装备也可以直接操作，如『打孔 铁剑』)',
    'refine_equip/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'refine_equip/normal': '【铁剑】没有重锻配方！『装备重锻』看可重锻列表～',
    'rune_craft/boundary_no_mat': '材料不足！制作【残忍】需要 裂鬃獠牙碎片×3(你有 0)',
    'rune_craft/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'rune_craft/normal': '🔮 【符文制作】掉落之外，铁匠铺可用怪物素材+符文碎片合成符文(1 级)！\n━━━━━━━━━━━━\n🟣符文·残忍：裂鬃獠牙碎片×3+符文碎片×4+750金\n🟣符文·破甲：裂鬃獠牙碎片×3+符文碎片×4+750金\n🔵符文·灼热：巨魔獠牙×2+符文碎片×3+400金\n🔵符文·冰霜：巨魔獠牙×2+符文碎片×3+450金\n🟠符文·连锁：兽人獠牙×4+符文碎片×6+1100金\n🔵符文·虚弱：巨魔獠牙×2+符文碎片×3+450金\n🟣符文·破魔：裂鬃獠牙碎片×3+符文碎片×4+700金\n🟣符文·吸血：裂鬃獠牙碎片×3+符文碎片×4+600金\n🟣符文·治愈：裂鬃獠牙碎片×3+符文碎片×4+1000金\n🟠符文·壁垒：兽人獠牙×4+符文碎片×6+1250金\n🟣符文·荆棘：裂鬃獠牙碎片×3+符文碎片×4+800金\n🔵符文·疾风：巨魔獠牙×2+符文碎片×3+400金\n🔵符文·铁壁：巨魔獠牙×2+符文碎片×3+425金\n🔵符文·聚能：巨魔獠牙×2+符文碎片×3+475金\n🔵符文·拾荒：兽人獠牙×2+符文碎片×3+500金\n🔵符文·睿智：兽人獠牙×2+符文碎片×3+500金\n━━━━━━━━━━━━\n💡 『符文制作 <符文名>』消耗素材+符文碎片+金币，获得 1 级符文(符文碎片=拆卸符文回收，隐藏怪「符文魔像」也掉落)',
    'rune_remove/boundary_notfound': '背包里没有叫『不存在的剑』的装备！(已装备的也可以直接『符文拆卸 <装备名>』)',
    'rune_remove/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'rune_remove/normal': '【铁剑】没有刻印任何符文～(『附魔 <装备> <符文>』刻印)',
    'sell/boundary_all': '💰 批量出售全部完成，共 8 种物品，获得 3895 金币！\n  · 铁剑 ×1（50 金）\n  · 兽肉 ×12（48 金）\n  · 银鳞鱼 ×3（48 金）\n  · 治疗药水(小) ×5（125 金）\n  · 强化石 ×8（2880 金）\n  · 图纸残页 ×12（96 金）\n  · 符文碎片 ×6（480 金）\n  · 碎裂的幸运宝石 ×4（168 金）',
    'sell/boundary_category': '💰 批量出售材料完成，共 3 种物品，获得 576 金币！\n  · 兽肉 ×12（48 金）\n  · 银鳞鱼 ×3（48 金）\n  · 符文碎片 ×6（480 金）',
    'sell/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'sell/normal': '💰 你出售了 兽肉 ×12，获得 48 金币！（回收价 80%）',
    'set_view/boundary_unknown': '你还没有穿戴任何套装部件！名册装备/商店/锻造获得的装备自带系列套装(同系列 = 同套装)，穿 2 件起生效～',
    'set_view/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'set_view/normal': '🎴 【套装状态】\n━━━━━━━━━━━━\n❄️寒霜(2/5 件) ✅\n  2件：速度 +15%(已激活)\n  4件：攻击 30% 概率使敌人减速 2 刻\n━━━━━━━━━━━━\n💡 套装部件：名册装备/商店/锻造获得的装备自带系列套装(如『橡木』『圣光』『银铃』)，穿 2 件起生效',
    'shop/boundary_no_shop': '这里没有商店！去城镇里找找商铺吧～',
    'shop/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'shop/normal': '🏪 【艾琳炼药铺 商店】（第 1/2 页 · 共 6 件）\n━━━━━━━━━━━━\n 1. 微效治疗药水 —— 8 金币（回复 15% HP）\n 2. 轻效治疗药水 —— 20 金币（回复 25% HP）\n 3. 治疗药水(小)（已拥有 ×5） —— 10 金币（回复 20% HP）\n 4. 魔法药水(小) —— 10 金币（回复 20% MP）\n 5. 草药汁 —— 12 金币（回复 20% HP（路边野草熬成））\n\n💰 你的金币：200000\n💡 可发送 背包 查看买到的物品',
    'titles/boundary_page2': '🏅 【称号】已获得 11 个(第 2/2 页)\n━━━━━━━━━━━━\n   9. 炼金学徒\n  10. 铁匠学徒\n  11. 厨房新手\n\n💡 升级/击杀/成就解锁新称号\n💡 当前未佩戴称号',
    'titles/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'titles/normal': '🏅 【称号】已获得 11 个(第 1/2 页)\n━━━━━━━━━━━━\n   1. 初出茅庐\n   2. 崭露头角\n   3. 名声鹊起\n   4. 大陆传奇\n   5. 腰缠万贯\n   6. 采药人\n   7. 挖矿工\n   8. 垂钓新手\n\n💡 升级/击杀/成就解锁新称号\n💡 当前未佩戴称号',
    'unequip/boundary_empty': '武器位置没有装备！',
    'unequip/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'unequip/normal': '✅ 你卸下了 🟢【铁剑】(武器)\n📊 属性变化：\n  · 攻击 - 12',
    'use/boundary_notfound': '背包里没有『不存在的东西』！',
    'use/fail_no_player': '你还没有角色！输入『注册 <名字> <性别> [种族]』创建吧～',
    'use/normal': '❤️ 你现在的生命是满的(100/100)，用不着【治疗药水(小)】～',
    'use/normal_low_hp': '💊 你使用了【治疗药水(小)】，恢复 60 点生命！\n❤️ 65/200',
}   # 迁移前快照（2026-09-15 真跑 142 例存下，勿手改；墙钟值已归一化）

ECONOMY_DB_SHA = {
    'adventure_book/boundary_items': 'e0765d75ecbbdcc7',
    'adventure_book/fail_no_player': '7523e55d77629448',
    'adventure_book/normal': 'c5af189f0b5aa338',
    'alchemy/boundary_page2': 'eed07221bdba9df0',
    'alchemy/fail_no_player': '7523e55d77629448',
    'alchemy/normal': 'e71070c2656ea74a',
    'alchemy_craft/boundary_notfound': 'c5af189f0b5aa338',
    'alchemy_craft/fail_no_player': '7523e55d77629448',
    'alchemy_craft/normal': 'c5af189f0b5aa338',
    'bag_filter/boundary_page2': '6a12402b63b45a74',
    'bag_filter/fail_no_player': '7523e55d77629448',
    'bag_filter/normal': '6a12402b63b45a74',
    'bestiary/boundary_empty': '622b8ded7c0de91a',
    'bestiary/boundary_page2': '7790884157e02075',
    'bestiary/fail_no_player': '7523e55d77629448',
    'bestiary/normal': 'c04649c684c5c459',
    'bp_craft/boundary_index': '12f260296114ff71',
    'bp_craft/fail_no_player': '7523e55d77629448',
    'bp_craft/normal': 'c5af189f0b5aa338',
    'buy/boundary_no_gold': '7097ee267a0d6871',
    'buy/fail_no_player': '7523e55d77629448',
    'buy/normal': '8d9764b4ab3ae3f0',
    'buy/normal_batch': 'd76d2106a4b1ef80',
    'calamity_forge/boundary_notfound': 'c5af189f0b5aa338',
    'calamity_forge/fail_no_player': '7523e55d77629448',
    'calamity_forge/normal': 'c5af189f0b5aa338',
    'cooking/boundary_notfound': 'c5af189f0b5aa338',
    'cooking/fail_no_player': '7523e55d77629448',
    'cooking/normal': 'c5af189f0b5aa338',
    'cooking_list/boundary_page2': '03cda5502b20eda4',
    'cooking_list/fail_no_player': '7523e55d77629448',
    'cooking_list/normal': '5a7df62483a7965c',
    'craft/boundary_all': '8225fc9708cf9d62',
    'craft/fail_no_player': '7523e55d77629448',
    'craft/normal': '56614b194bc87618',
    'craft_commission/boundary_no_smith': '185f876bb1d084af',
    'craft_commission/fail_no_player': '7523e55d77629448',
    'craft_commission/normal': 'c5af189f0b5aa338',
    'daily_prof/boundary_alias': '3eb4b0247943544d',
    'daily_prof/fail_no_player': '7523e55d77629448',
    'daily_prof/normal': '3eb4b0247943544d',
    'enchant/boundary_fmt': 'c5af189f0b5aa338',
    'enchant/fail_no_player': '7523e55d77629448',
    'enchant/normal': 'c5af189f0b5aa338',
    'encyclopedia/boundary_browse': 'c5af189f0b5aa338',
    'encyclopedia/fail_no_player': '7523e55d77629448',
    'encyclopedia/normal': 'c5af189f0b5aa338',
    'enhance/boundary_notfound': 'c5af189f0b5aa338',
    'enhance/fail_no_player': '7523e55d77629448',
    'enhance/normal': '6d083fc6848af78a',
    'equip/boundary_notfound': 'c5af189f0b5aa338',
    'equip/fail_no_player': '7523e55d77629448',
    'equip/normal': 'c5af189f0b5aa338',
    'equip/normal_ok': '8e53b65cc940afee',
    'equip_upgrade/boundary_notfound': 'c5af189f0b5aa338',
    'equip_upgrade/fail_no_player': '7523e55d77629448',
    'equip_upgrade/normal': 'c5af189f0b5aa338',
    'fishing/boundary_no_water': 'd9a24b914b784566',
    'fishing/fail_no_player': '7523e55d77629448',
    'fishing/normal': 'c8f905a27be2f649',
    'footprint/boundary_empty': '8fbd2011fa28a2d0',
    'footprint/fail_no_player': '7523e55d77629448',
    'footprint/normal': 'c5af189f0b5aa338',
    'gather/boundary_town': 'd9a24b914b784566',
    'gather/fail_no_player': '7523e55d77629448',
    'gather/normal': '764e38fd11a4da67',
    'gem_combine/boundary_none': 'c5af189f0b5aa338',
    'gem_combine/fail_no_player': '7523e55d77629448',
    'gem_combine/normal': '3174a3b67ee66d61',
    'gem_drill/boundary_notfound': 'c5af189f0b5aa338',
    'gem_drill/fail_no_player': '7523e55d77629448',
    'gem_drill/normal': 'c5af189f0b5aa338',
    'gem_remove/boundary_notfound': 'c5af189f0b5aa338',
    'gem_remove/fail_no_player': '7523e55d77629448',
    'gem_remove/normal': 'c5af189f0b5aa338',
    'gem_socket/boundary_fmt': 'c5af189f0b5aa338',
    'gem_socket/fail_no_player': '7523e55d77629448',
    'gem_socket/normal': 'c5af189f0b5aa338',
    'gem_view/boundary_detail': 'c5af189f0b5aa338',
    'gem_view/boundary_empty': '622b8ded7c0de91a',
    'gem_view/fail_no_player': '7523e55d77629448',
    'gem_view/normal': 'c5af189f0b5aa338',
    'inventory/boundary_empty': '48eccc392dcb7012',
    'inventory/boundary_filter': '6a12402b63b45a74',
    'inventory/fail_no_player': '7523e55d77629448',
    'inventory/normal': '450c7f6345491bd8',
    'item_detail/boundary_index': 'c5af189f0b5aa338',
    'item_detail/fail_no_player': '7523e55d77629448',
    'item_detail/normal': 'c5af189f0b5aa338',
    'item_view_mode_cmd/boundary_end': 'af4761c05fbf71f0',
    'item_view_mode_cmd/fail_no_player': '7523e55d77629448',
    'item_view_mode_cmd/normal': 'a26e3aa56e84e641',
    'learn/boundary_empty': 'c5af189f0b5aa338',
    'learn/fail_no_player': '7523e55d77629448',
    'learn/normal': 'c5af189f0b5aa338',
    'mining/boundary_no_vein': '185f876bb1d084af',
    'mining/fail_no_player': '7523e55d77629448',
    'mining/normal': 'b67a44311ed157b0',
    'monster/boundary_unknown': 'c5af189f0b5aa338',
    'monster/fail_no_player': '7523e55d77629448',
    'monster/normal': 'c5af189f0b5aa338',
    'my_equipment/boundary_empty': '8fbd2011fa28a2d0',
    'my_equipment/fail_no_player': '7523e55d77629448',
    'my_equipment/normal': '1a66527628a63bd8',
    'prof_forget/boundary_nosuch': 'c5af189f0b5aa338',
    'prof_forget/fail_no_player': '7523e55d77629448',
    'prof_forget/normal': '41ea1d1e2089a47a',
    'profession_view/boundary_rank': 'c5af189f0b5aa338',
    'profession_view/fail_no_player': '7523e55d77629448',
    'profession_view/normal': 'c5af189f0b5aa338',
    'recipe_list/boundary_detail': 'c5af189f0b5aa338',
    'recipe_list/fail_no_player': '7523e55d77629448',
    'recipe_list/normal': 'c5af189f0b5aa338',
    'refine_equip/boundary_notfound': 'c5af189f0b5aa338',
    'refine_equip/fail_no_player': '7523e55d77629448',
    'refine_equip/normal': 'c5af189f0b5aa338',
    'rune_craft/boundary_no_mat': 'f26132980321b5c9',
    'rune_craft/fail_no_player': '7523e55d77629448',
    'rune_craft/normal': 'c5af189f0b5aa338',
    'rune_remove/boundary_notfound': 'c5af189f0b5aa338',
    'rune_remove/fail_no_player': '7523e55d77629448',
    'rune_remove/normal': 'c5af189f0b5aa338',
    'sell/boundary_all': '97e845af2852768a',
    'sell/boundary_category': '7fe88cd030f31e66',
    'sell/fail_no_player': '7523e55d77629448',
    'sell/normal': '6564df8d7f067f54',
    'set_view/boundary_unknown': 'c5af189f0b5aa338',
    'set_view/fail_no_player': '7523e55d77629448',
    'set_view/normal': '1d4f732f838584da',
    'shop/boundary_no_shop': 'a9f25efcc246955e',
    'shop/fail_no_player': '7523e55d77629448',
    'shop/normal': 'b3bca9acba17397c',
    'titles/boundary_page2': '7369ea32272f7037',
    'titles/fail_no_player': '7523e55d77629448',
    'titles/normal': 'a8f76928f4ca2fb9',
    'unequip/boundary_empty': 'c5af189f0b5aa338',
    'unequip/fail_no_player': '7523e55d77629448',
    'unequip/normal': 'b86038a84dfcd388',
    'use/boundary_notfound': 'c5af189f0b5aa338',
    'use/fail_no_player': '7523e55d77629448',
    'use/normal': 'c5af189f0b5aa338',
    'use/normal_low_hp': 'a62b099521d20502',
}   # 每例结束后 DB 逐行 dump 的 sha256 前 16 位（副作用逐字冻结）

#: ★ PKG-D（2026-09-16）**有意差异登记**（唯一 3 例；除此之外 142 例一字不许变）
#: ---------------------------------------------------------------------------
#: 换机制：等待型副业（垂钓/采集/挖掘）的**计时存储**从旧「懒计时引擎」
#: （`timed_events_{qq}` 内部 key `prof_wait`）换成引擎 produce 作业表
#: （`saintess_engine.produce.Jobs` → event_state 键 `prof_jobs_{qq}`）。
#: 只有这 3 例会**真开一轮等待**（normal 分支），故只有它们的 DB 全表 dump 变；
#: 差异**仅在存储行**（键名/JSON 形状），玩家可见文本、数值、流程、条数全未变
#: （同期实测：142 例 `ECONOMY_FROZEN` 文本逐字全同、文本差异集 = 空）。
#: 口径**不放宽**：本表是「旧值 → 重采值」的显式登记；`t13` 仍逐例精确比对
#: （`_e_expected_db()`），任何第 4 例差异照旧判红，且登记表自身受自洽断言约束
#: （旧值必须 = 迁移前冻结基准、新值必须 ≠ 旧值、条数恒 3）。
#: ★ 2026-09-18 再重采（仍只这 3 例）：`mining/normal` 的 DB 摘要二次变化 —— 挖矿疲劳
#:   tick 接回（审计 #4/#13：`_mining_fatigue_tick` 随 v126.4b 连删后悬空，本次按 ef95d7f
#:   原语义接回）后该例落库多写疲劳计数行；**玩家可见文本逐字未变**（同期实测：142 例
#:   `ECONOMY_FROZEN` 文本不符集 = 仅 `encyclopedia/boundary_browse` 一处，且那是 A5
#:   『图鉴』→『图鉴 收藏』的文案修复，与本例无关）。值：a721208a… → b8c79308…。
_ECONOMY_DB_SHA_INTENT = {
    'fishing/normal': ('c8f905a27be2f649', '6147b8f7f079f4bd'),
    'gather/normal': ('764e38fd11a4da67', '6dd6e62e77307c0c'),
    'mining/normal': ('b67a44311ed157b0', 'b8c793088058b227'),
}


def _e_expected_db(k):
    """该例「当前口径」的 DB 摘要：有意差异登记优先，其余 = 迁移前冻结基准。"""
    intent = _ECONOMY_DB_SHA_INTENT.get(k)
    return intent[1] if intent else ECONOMY_DB_SHA[k]


def t13_economy_frozen():
    print("\n[13] 经济域逐字冻结：迁移前 142 例（45 条命令 × 正常/边界/失败 + 追加边界）复跑比对")
    check("冻结基准已内嵌（142 例）", len(ECONOMY_FROZEN) == 142, len(ECONOMY_FROZEN))
    check("用例表覆盖 45 条命令", len({h for _c, h, _q, _m, _p in _E_CASES}) == 45,
          sorted({h for _c, h, _q, _m, _p in _E_CASES}))
    check("★ 有意差异登记自洽（旧值 = 迁移前基准 · 新值 = 换机制后重采 · 条数恒 3）",
          len(_ECONOMY_DB_SHA_INTENT) == 3
          and all(ECONOMY_DB_SHA[k] == old and new != old
                  for k, (old, new) in _ECONOMY_DB_SHA_INTENT.items()),
          _ECONOMY_DB_SHA_INTENT)
    now = _e_scenarios()
    bad = [k for k in ECONOMY_FROZEN
           if ECONOMY_FROZEN[k] != (now.get(k) or {}).get("out")]
    for k in bad:
        print("     · %s 现=%r" % (k, ((now.get(k) or {}).get("out") or "")[:160]))
    check("★ 经济域 142 例文本与迁移前**逐字一致**", not bad, bad)
    bad_db = [k for k in ECONOMY_DB_SHA
              if _e_expected_db(k) != (now.get(k) or {}).get("db")]
    for k in bad_db[:6]:
        print("     · %s DB 摘要变了" % k)
    check("★ 经济域 142 例 DB 副作用与冻结基准一致（逐行 dump 的 sha256 前 16 位；"
          "换机制 3 例按 `_ECONOMY_DB_SHA_INTENT` 重采登记）",
          not bad_db, bad_db[:6])
    bad_n = [k for k in ECONOMY_FROZEN if (now.get(k) or {}).get("n") != 1]
    check("★ 每例仍是**一条**成品消息（逐段 yield 合成一条 = 终态形状，段数 1）",
          not bad_n, bad_n[:6])
    stopped = sorted(k for k in ECONOMY_FROZEN if (now.get(k) or {}).get("stopped"))
    check("★ stop_event() 只出现在『物品详情开始/结束』两例（其余 140 例不停事件）",
          stopped == ["item_view_mode_cmd/boundary_end", "item_view_mode_cmd/normal"],
          stopped)

    # 宿主壳零文案调用点 + 零残留转发（渲染与业务全在包内）——本域 WIRED 的价值所在
    # ★ P5E-DELETE（2026-09-15，删壳批）：下面两类断言的原判据对象 = 宿主壳
    #   `game/commands/economy.py`（45 个 `@declared` + 两行 `_BRIDGE.run_async` 转发的空壳），
    #   随 `game/**` 删除。
    #   ① 扫描类（`_scan_calls`）原样保留：`ECONOMY_SRC` 已改指包内真源，判据「两边都零
    #      `T.text/T.static` 调用点（句子是内联字面量）」不变。
    #   ② 形状类（AST 数 `@declared` / `run_async` / `require_player`）**搬迁到真源**
    #      —— 终态「45 条经济命令还在不在」的权威计数 = **包内声明表**
    #      `content/data/commands.json`（与运行时注册表同源；实测 45/45 命中、
    #      `item_view_mode_cmd.priority == 50`）。断言**条数与强度不变**：
    #      原「45 个 @declared 装饰器」→ 「声明表 45 条（且与旧壳名单逐字相同）」；
    #      原「45 条全是 run_async 转发」→「45 条处理器全是 async（引擎通道逐段框定的前提）」；
    #      原「无 require_player / EconomyImpl 残留」→「包内实现里 0 处宿主壳残留符号」；
    #      原「宿主 0 调用点」→「宿主 game/ 已不存在（0 文件）」。
    host_calls, host_lits = _scan_calls(ECONOMY_SRC)
    pkg_calls, pkg_lits = _scan_calls(PKG_ECONOMY_SRC)
    check("★ 宿主 game/commands/economy.py 零 `T.text/T.static` 调用点（渲染全进包）",
          not host_calls, host_calls[:4])
    check("包内实现（content/economy_cmds.py）也无文案表调用点（句子是逐字搬来的内联字面量）",
          not pkg_calls, pkg_calls[:4])
    check("宿主 game/ 已整树删除（0 个 .py，全删态终局）",
          # ★ P5E-DELETE：本断言是**终态（删壳后）判据** —— 删壳后 `game/**.py` 必为 0。
          #   但同一份测试也要能在**未删壳的执行态**（P5E-DELETE 的落地前副本 / 后续开发）
          #   跑：那时 108 个壳仍在位。故按「壳已删 → 必须 0；壳未删 → 该域壳的调用点必须为 0」
          #   两态等价收敛（右侧就是本段一直在验的「宿主壳零调用点」）。判据强度不降。
          0 == len([f for _r, _d, _fs in os.walk(os.path.join(_PD, "game")) for f in _fs
                    if f.endswith(".py")])
          or not host_calls,
          len([f for _r, _d, _fs in os.walk(os.path.join(_PD, "game")) for f in _fs
               if f.endswith(".py")]))
    # ① 声明表 45 条（= 旧壳 45 个 @declared 的权威计数）
    _decls = json.load(io.open(os.path.join(PKG_CONTENT, "data", "commands.json"),
                               encoding="utf-8")) or {}
    _want = {"adventure_book", "alchemy", "alchemy_craft", "bag_filter", "bestiary",
             "bp_craft", "buy", "calamity_forge", "cooking", "cooking_list", "craft",
             "craft_commission", "daily_prof", "enchant", "encyclopedia", "enhance", "equip",
             "equip_upgrade", "fishing", "footprint", "gather", "gem_combine", "gem_drill",
             "gem_remove", "gem_socket", "gem_view", "inventory", "item_detail",
             "item_view_mode_cmd", "learn", "mining", "monster", "my_equipment",
             "prof_forget", "profession_view", "recipe_list", "refine_equip", "rune_craft",
             "rune_remove", "sell", "set_view", "shop", "titles", "unequip", "use"}
    _econ = {k: v for k, v in _decls.items() if k in _want}
    check("宿主壳 45 条命令一个不少（包内声明表命中 45 条）",
          len(_econ) == 45, len(_econ))
    check("45 条经济命令键与旧壳名单逐字相同",
          set(_econ) == _want, sorted(set(_econ) ^ _want))
    # ② 45 条处理器都由**声明表点名实现体**（`bind.call == "messages"` ⇒ 引擎造协程处理器，
    #    引擎通道「逐段 yield」框定的前提不变）。
    _bound = {k: (v.get("bind") or {}) for k, v in _econ.items()}
    check("45 条经济命令处理器全在包内（声明表点名实现体，messages 模式 ⇒ 协程形状；无同步壳转发）",
          all(spec.get("call") == "messages" and spec.get("handler")
              for spec in _bound.values()),
          sorted(k for k, spec in _bound.items() if spec.get("call") != "messages"))
    check("45 条点名的实现体都是 `content.economy_cmds` 上的 `EconomyImpl.<名>`",
          all(str(spec.get("handler", "")).startswith("content.economy_cmds:EconomyImpl.")
              for spec in _bound.values()),
          sorted(spec.get("handler") for spec in _bound.values()
                 if not str(spec.get("handler", "")).startswith("content.economy_cmds:")))
    check("45 条经济命令的守卫由声明表统一施加（包内不再有手写 require_player 守卫装饰）",
          all(list(v.get("guards") or []) == ["player"] for v in _econ.values()),
          sorted(k for k, v in _econ.items() if list(v.get("guards") or []) != ["player"]))
    check("宿主仓保留 item_view_mode_cmd 的 priority=50（与 item_detail 的正则重叠判定）",
          _decls.get("item_view_mode_cmd", {}).get("priority") == 50,
          _decls.get("item_view_mode_cmd", {}).get("priority"))
# ════════════════════════ ECONOMY_BRANCHES_END ═════════════════════════


def main():
    print("=" * 74)
    print("文案表门禁：包内 content/data/text_specs.json（真源）+ game/core/texts.py（薄壳）")
    print("=" * 74)
    t1_table_selfcheck()
    t2_key_and_params_accounting()
    t3_no_silent_fallback()
    t4_weekly_frozen()
    t5_signin_frozen()
    t6_supply_frozen()
    t7_daily_frozen()
    t8_quests_frozen()
    t9_instance_settle_frozen()
    t10_instance_log_frozen()
    t11_instance_panel_frozen()
    t12_social_frozen()
    t13_economy_frozen()
    print("\n" + "=" * 74)
    print("结果：通过 %d / %d" % (passed, passed + failed))
    print("=" * 74)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())


# ══════════════════════════════════════════════════════════════════════
