#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""门禁：奥兰迪亚**包内数据冻结门禁**（★ 2026-09-14 B14 开关后）

跑法（系统 python 即可）：
    cd dragonfall && python tests/test_export_package_sync.py
退出码：0 = 全绿；1 = 有红（红行点名具体域 / 文件 / key）。

框架仓路径：默认 `C:/Users/yuyu/framework-engine`，可用 `$GWEN_FRAMEWORK_DIR` 覆盖。

═══════════════════════════════════════════════════════════════════════════
语义变更（2026-09-14，本文件头必须读完再改判据）
═══════════════════════════════════════════════════════════════════════════
旧版 = 「宿主真源 `game/data/*.py` → 包 JSON」的**同步门禁**：现场重新派生，再与仓库里已生成的
`content/data/*.json` 逐字节比对。

2026-09-14 **B14 开关**删掉了宿主 `game/data/*.py`（74,707 行 / 87 文件），单向导出器
`scripts/export_game_package.py` 与域插件 `scripts/export_domains/` **随之退役**
（归档 `scripts/_retired/`，语义账见其 `README.md`）→ **包内 `content/data|rules/*.json`
就是数据真源**，「现场重新派生」这件事不再存在。

于是本门禁改为**冻结门禁**：把必须恒定的事实写成断言（规模 / 形状 / 落盘规范 / 清单一致），
任何一条变了立刻红。**判据只加强不削弱** —— 旧版能抓的（少 key、字段丢失、条数漂移、
清单漂移、未声明域文件）现在照样抓，只是依据从「与真源对拍」变成「与冻结账对拍」。

═══════════════════════════════════════════════════════════════════════════
锁什么
═══════════════════════════════════════════════════════════════════════════
【1】items 域**冻结规模** = 900（合表后唯一物品数，**不是** 1704 = 900+598+206 —— 语义账见
     `scripts/_retired/README.md`）；key 匹配 `^[a-z][a-z0-9_]*$`。
【2】items 每条必填 `name`/`price`/`desc`（对齐 `schemas/item.schema.json` required）；
     price 非负；`quality` 有则必须 ∈ enum。
【3】逐条过**包内 schema**（`editor.packages.domain_status`；jsonschema 缺失时用框架校验器兜底）。
【4】清单 ↔ 文件：`game.json:domains` 声明的每个域都有数据文件（落点由域 `kind` 决定）；
     反向：`content/data|rules/` 下不存在未声明的孤儿文件。
【5】各域**冻结规模账**（值 = B14 收纳当刻实测：72 域 / 9125 条的那份账里的代表项）。
【6】**落盘规范**（编辑器保存自动满足；手改必须照此，否则每次保存都产生 diff 噪音）：
     UTF-8 无 BOM · LF 行尾 · `indent=2` · 末尾换行 · 外层键**升序**。
【7】包清单规范：`id`/`name`/`engine`/`entry`/`created`/`domains` 齐备；`id == "orlandia"`；
     `domains` 与包声明域、实际数据文件三方一致。
"""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ID = "orlandia"
sys.path.insert(0, HERE)   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402  ← 包根/引擎根发现（GWEN_FRAMEWORK_DIR 优先）
FW_ROOT = _paths.ENGINE_ROOT
PKG_DIR = _paths.PKG_ROOT
#: 「不是域表」的已登记辅助文件（`content/data|rules/` 下）：跳过孤儿扫描，**明示打印**，
#: 且不要求落盘规范（它们由各自机制维护）。第一条 = 文案规格表（P4′-B 后在包内，
#: 与 `texts` 域的数据文件 `texts.json`（导出投影）配对；真源/投影关系由
#: `tests/test_texts_specs_sync.py` 钉住）。
AUX_FILES = {"text_specs.json": "文案规格表（非域表；真源=包内，宿主那份是构建期镜像）",
             "tables.json": "存档表结构声明（非域表；包内真源，由引擎 `saintess_engine.store` 装载建表）",
             "cond_specs.json": "声明式条件表（非域表；S4 起为包内真源 —— 由 `content/cond_specs.py` "
                                "读口供给，引擎 `saintess_engine.conditions.declarative` 通用装配）"}

DATA_DIR = os.path.join(PKG_DIR, "content", "data")
RULES_DIR = os.path.join(PKG_DIR, "content", "rules")
MAN_PATH = os.path.join(PKG_DIR, "game.json")
ITEM_SCHEMA = os.path.join(PKG_DIR, "schemas", "item.schema.json")

MAX_REPORT = 20                  # 每类差异最多打印多少行

# ---- 冻结账（B14 收纳当刻实测；改这里 = 改口径，必须同时改 scripts/_retired/README.md）----
EXPECT_ITEMS = 900               # 合表后唯一物品数（不是 1704）
EXPECT_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
FROZEN_COUNTS = {
    "items": 900, "equip_roster": 687, "subareas": 628, "exploration": 628,
    "drop_pools": 596, "pois": 457, "npcs": 431, "craft": 426, "monster_roster": 380,
    "monsters": 330, "skills": 305, "skill_up": 305, "quests": 238,
    # ★ D2（数据进表）：`texts` = 文案真源的导出投影 —— 武器特效域（`weapon_effects`）的 51 条
    #   玩家可见文案随域迁移进 `text_specs.json`，投影同步 + 51 ⇒ 233 → 284。
    #   口径变更（有意）：文案条目仍只由 `text_specs.json` 一个真源驱动，本账只反映条目数。
    #   ★ 2026-09-17 B 批 B-1：效果名 47 + 战斗名词 130（机制/增益/减益/叠层/资源）⇒ 284 → 461。
    #   ★ 2026-09-18 C 档 13（B-2 第一片）：economy_cmds「面板尾货」—— 物品详情 `_render_*` 10 函数
    #     59 键 + `_possessed_view.order` / `_ency_browse_materials._order` 类目表 25 键（12 词共用）
    #     ⇒ 1006 → 1090（净增 84 键）。
    #   ★ 2026-09-18 C 档 14（B-2 第 2 片）：player_cmds「散落/尾巴」—— 14 函数 97 处替换 / 93 新键
    #     （4 处幂等复用 skill.only_n ×2 / skill.no_skill ×2）⇒ 1090 → 1183。
    #   ★ 2026-09-18 C 档 15（B-2 第 6 片）：item_templates「道具模板文案族」—— 44 个模板函数
    #     111 处替换 / 105 新键（6 条 occ='all' 共键各覆盖 2 处）⇒ 1183 → 1288。
    #   ★ 2026-09-18 C 档 16（B-2 第 3 片）：economy 散落「采集/生活」—— 10 个函数
    #     77 处替换 / 75 新键（' 📜未学' 与 '📄 第 N/M 页' 各幂等复用一次）⇒ 1288 → 1363。
    #   ★ 2026-09-18 C 档 17a（B-2 第 3 片第 2 小片）：economy 散落「锻造族」——
    #     craft / craft_commission / learn / _learned_blueprint_list / _craft_line /
    #     _craft_town_hint / _craft_list_{available,all,class} / _recipe_detail / recipe_list
    #     78 处替换 / 71 新键（craft.removed×3、not_found×2、lack_detail×2、page_no×3 幂等复用）⇒ 1363 → 1434。
    #   ★ 2026-09-18 C 档 17b（B-2 第 3 片第 3 小片）：economy 散落「强化·宝石·符文·重锻·炼成·附魔」——
    #     enhance / equip_upgrade / gem_drill / gem_socket / gem_remove / gem_combine / gem_view /
    #     _gem_find_equip / _gem_find_gem / _gem_tier_detail / _rune_craft_panel / rune_craft /
    #     rune_remove / refine_equip / calamity_forge / enchant
    #     120 处替换 / 115 新键（common.bag_no_idx×4、common.prof_lv_up×2、craft.lack_detail×3 幂等复用）⇒ 1434 → 1549。
    #   ★ 2026-09-18 C 档 18a（B-2 第 4 片第 1 小片）：world 散落「地图面板族」——
    #     _map_facilities / _map_scene / map_view / region_view / _map_nav_body /
    #     location_view / _hurry_type / _hurry_panel / hurry_view / back_cmd / ask_way
    #     42 处替换 / 34 新键（world.inst_battle×4、world.hurry_tip×3、world.hidden×3、
    #     nav.cur_pos×2 幂等复用）⇒ 1549 → 1583。
    #   ★ 2026-09-18 C 档 18c（B-2 第 4 片第 2 小片）：world 散落「任务委托族」——
    #     quest_accept（接取）· quest_abandon（放弃）· daily（悬赏板红名）
    #     30 处替换 / 25 新键（main_ready×2、side_head×2、reward×2、objective×2、abandon.done×2 幂等复用）⇒ 1583 → 1608。
    #   ★ 2026-09-18 C 档 18d-1（B-2 第 4 片第 3 小片）：world 散落「家园·地契」——
    #     deed_view / deed_buy / deed_sell / _deed_upgrade / go_home / go_out / visit_home /
    #     home_storage / home_storage_take / _home_view
    #     52 处替换 / 48 新键（storage_full×2、storage_not_home×2 幂等复用；
    #     prof.fish_battle×2 跨片复用既有键）⇒ 1608 → 1656。
    #   ★ 2026-09-18 C 档 18d-2（B-2 第 4 片第 4 小片）：world 散落「营地·休息·声望·阵营」——
    #     rest_camp / rest / reputation / rep_shop / camp_join / _camp_line / camp_task /
    #     camp_shop / camp_rank
    #     64 处替换 / 64 新键（无复用）⇒ 1656 → 1720。
    #   ★ 2026-09-19 C 档 18d-3（B-2 第 4 片第 5 小片）：world 散落「传送·方碑·场景交互」——
    #     portal_view / portal_activate / portal_travel / interact_prop
    #     38 处替换 / 35 新键（井水同值 ×2、翻找同值 ×3 幂等复用）⇒ 1720 → 1755。
    #   ★ 2026-09-19 C 档 19a（B-2 第 5 片第 1 小片）：combat 战斗域「探索·战斗主循环」——
    #     explore / attack / defend / flee / wild_king_chest / _status_line / _buff_left_ticks /
    #     _battle_formation_panel / _battle_footer / _handle_victory
    #     65 处替换 / 49 新键（explore 内多片段同值 + 跨函数复用）⇒ 1755 → 1804。
    #   ★ 2026-09-19 C 档 19b（B-2 第 5 片第 2 小片）：combat 技能族 ——
    #     skill / _skill_list_page / _skill_tag / _skill_range_label /
    #     _skill_list_gains / _skill_gains_curve
    #     44 处替换 / 34 新键（技能面板分类已存在；PVP/旧存档/Boss 不可逃/食物提示跨片复用）
    #     ⇒ 1804 → 1838。
    #   ★ 2026-09-19 C 档 19c（B-2 第 5 片第 3 小片）：combat「PvP·荣誉」——
    #     honor_shop / _honor_buy / _pvp_start / _pvp_act / _pvp_finish
    #     40 处替换 / 40 新键（新分类 PvP荣誉）⇒ 1838 → 1878。
    #     一条不迁：荣誉商店普通物品兑换行（elif 分支单段 f-string，工具 needle 命中 0）
    #   ★ 2026-09-19 C 档 19d（B-2 第 5 片第 4 小片）：combat「世界 Boss 讨伐」——
    #     hunt_boss / _worldboss_act　16 处替换 / 12 新键（新分类 世界Boss）⇒ 1878 → 1890。
    #   ★ 2026-09-19 C 档 19e-1（B-2 第 5 片第 5 小片）：combat「许愿·流浪商人·复活确认」——
    #     wish / trader_confirm / revive_confirm　18 处替换 / 18 新键（新分类 许愿商人）⇒ 1890 → 1908。
    #   ★ 2026-09-19 C 档 19e-2（B-2 第 5 片第 6 小片）：combat「battle_prefs 战前设置」——
    #     battle_prefs_form / _finisher / _arcane_field / _view　23 处替换 / 22 新键
    #     （新分类 战前设置）⇒ 1908 → 1930。
    #   ★ 2026-09-19 C 档 20a（B-2 第 6 片第 1 小片）：社交散落「市场·摊位」——
    #     content/social_stall.py 全函数 + cmds_social 市场/摆摊段（12 函数）60 处替换 / 57 新键
    #     （新分类 社交市场）⇒ 1939 → 1996。
    #   ★ 2026-09-19 C 档 20b（B-2 第 6 片第 2 小片）：社交「组队·公会」——
    #     cmds_social 组队/公会段（15 函数）+ content/party.py（5 函数）+ content/social_guild.py（14 函数）
    #     81 处替换 / 77 新键（新分类 社交队伍 / 社交公会）⇒ 1996 → 2073。
    #   ★ 2026-09-19 C 档 20c（B-2 第 6 片第 3 小片）：社交「世界事件 · 拍卖竞拍」——
    #     content/social_cmds.py 全 4 函数（maybe_roll_event / world_event_run / auction_run / bid_run）
    #     23 处替换 / 19 新键（新分类 世界事件 / 社交拍卖）⇒ 2073 → 2092。
    # ★ C 档 22c（B-2 第 8 片：world「NPC 对话族」43 处替换 / 37 新键，6 处幂等复用）⇒ 2270 → 2307
    # ★ C 档 23a（B-2 第 9 片：world「移动 · 赶路族」30 处替换 / 26 新键，1 处幂等复用
    #   npclist.head；新分类 移动赶路）——content/world_cmds.py 的 move（前往/移动全守卫链）
    #   + _hurry_section（赶路各类型过滤区）⇒ 2307 → 2333
    # ★ C 档 24a（B-2 第 10 片：world「副本内移动 · 落点模式提示」9 处替换 / 8 新键，1 处幂等复用
    #   move.same_sa；新分类 副本移动）——content/world_cmds.py 的 _instance_dungeon_move
    #   （副本内移动全守卫链 + 遇怪/Boss 房开场）+ _subarea_arrive（落点赶路模式提示行）
    #   ⇒ 2333 → 2341
    # ★ C 档 25a（B-2 第 11 片：world「NPC 支线/进化教学族」28 处替换 / 28 新键）⇒ 2341 → 2369
    # ★ C 档 26a（B-2 第 12 片：world 收尾「见闻录 / 时间面板 / 地图尾块 / 指路」
    #   42 处替换 / 36 新键，6 处同值幂等复用（hurry.fac_head/poi_head/prop_head/
    #   monster_head/elite + npclist.head）；新分类 见闻录 / 时间面板 / 时段名，
    #   季节名 / 天气名 为既有分类）⇒ 2369 → 2405
    #   ★ C 档 27a（B-2 第 13 片：world 余量「交付目标行 / 武器自选礼包」
    #     15 新键 = objline.* 9（含手改拆出的 find_ready / find_ready_map）+ wpick.* 6）⇒ 2405 → 2420
    #   ★ C 档 28a（B-2 第 14 片：settlement「战斗结算：经验/金币加成 + 掉落播报」
    #     37 新键 = 战斗结算 25 + 掉落播报 12）⇒ 2420 → 2457
    #   ★ C 档 28b（B-2 第 15 片：settlement「胜利面板 / 战败结算」两个大编排
    #     9 新键 = victory_settle 3 + defeat_settle 6）⇒ 2457 → 2466
    #   ★ C 档 29a（B-2 第 16 片：quests_flow 全文件「任务列表/接取/交付/进度」
    #     42 新键，6 处与 27a 的 objline.* 同值幂等复用）⇒ 2466 → 2508
    #   ★ C 档 30a（B-2 第 17 片：player_cmds 余量「注册欢迎面板 / 转职面板 /
    #     转职重置 / 战力 / 注销确认」，5 函数 8 处替换 / 8 新键；注册 / 转职 /
    #     注销 沿用既有分类，战力面板 为新分类）⇒ 2508 → 2516
    #   ★ C 档 31a（B-2 第 18 片：world_cmds 余量「野外来客未出现提示 / 对话支线菜单 /
    #     编年史」，3 函数 3 处替换 / 3 新键；NPC查找 / NPC对话 沿用既有，编年史 为新分类）
    #     ⇒ 2516 → 2519
    #   ★ C 档 33a（B-2 第 21 片：profession「副业结算：等待流/垂钓/惊喜/采集/挖掘」
    #     6 函数 40 处替换 / 39 新键；副业等待 / 垂钓结算 / 垂钓惊喜 / 采集结算 /
    #     挖掘结算 五个新分类；fish.lv_up ×4、fish.sv_legend ×2 同键同值复用，
    #     gather.rare_hint 跨 settle_gather / settle_mining 共键）⇒ 2586 → 2625
    #   ★ C 档 33b（B-2 第 22 片：cmds_job「职业速查」+ cmds_collection「收藏册」
    #     36 处替换 / 36 新键；职业速查 / 收藏册 两个新分类；零同值复用）⇒ 2625 → 2661
    #   ★ C 档 33c（B-2 第 23 片：wild_king「野王 / 野王宝箱」+ travel「出行提示」
    #     33 处替换 / 33 新键；野王 / 野王宝箱 / 出行提示 三个新分类）⇒ 2661 → 2694
    # ★ C 档 34a（B-2 第 24 片）：`content/talk_actions.py`「对话动作」19 处替换 +
    #     `content/race_talent_display.py`「种族天赋」24 处替换（两新分类）⇒ 2694 → 2737
    # ★ C 档 34b（B-2 第 25 片）：`content/cmds_event.py`「今日事件」30 处替换 +
    #     `content/reward.py`「奖励发放」9 处替换（两新分类）⇒ 2737 → 2774
    # ★ C 档 34c（B-2 第 26 片）：`content/misc_cmds.py`「帮助兜底/成就面板/意见反馈」
    #     8 处替换 + `content/achievements.py`「成就」11 处替换（两新分类）⇒ 2774 → 2792
    #   ★ C 档 37a（B-2 第 31 片 · C 档收口片：economy 货架行/孤品行/体力恢复 hook + combat 荣誉行/双形态可用行 + pets 宠物蛋 desc + instance_gate 人数措辞；10 处替换 / 10 新键，零同值复用）⇒ 3136 → 3146
    # ★ C 档 38a（收尾慢磨）：`content/cmds_gm.py`「gm_窥探 平台例外族」（8 处替换 / 8 新键，
    #     归既有 GM指令）+ `content/player_events.py`「成就解锁播报」（2 处替换 / 2 新键，
    #     归既有 成就面板；本文件首次接入 `_T`）⇒ 3172 → 3182
    # ★ C 档 38b（收尾慢磨）：`content/mech/we_procs.py` 四张模块级文案表 → `_T.names`
    #     （12 槽位 / 10 同值复用键 + 2 新键）+ 破败之吻内联串 ⇒ 3182 → 3184
    "texts": 3184,
    #     · EconomyImpl.titles 4 新键（新分类 称号面板：卸下回执 / 无称号整段 / 分页头 /
    #       未佩戴底栏）· _equip_title 3 新键（用法行 / 未获得 / 佩戴成功）
    #     · item_view_mode_cmd 2 新键（itemview.on / off —— 归既有 背包面板）
    # ★ C 档 22a（物品详情·我的装备·卸下，14 新键 / 22 处替换，8 处同值幂等复用）⇒ 2247 → 2261
    #     · item_detail 『物品详情/查看』7 新键（经济面板；百科装备序号详情块与
    #       _render_encyclopedia_equip 同值复用 item.series_line / req_line / src_line /
    #       set_line / special_line 5 键）
    #     · _my_equipment_view 『我的装备』3 新键（装备面板：标题/空槽行/底栏）
    #     · unequip 『卸下』3 新键（装备面板；复用 equip.in_battle / diff_head / diff_none）
    #     · _req_check 需求行 1 新键（经济面板 item.req_check）
    # ★ C 档 21c（使用·背包·装备，39 新键 / 48 处替换，5 处同值幂等复用）⇒ 2208 → 2247
    #     · _bag_view 背包/筛选/翻页 11 新键（新分类 背包面板）
    #     · equip 穿戴与守卫 10 新键（新分类 装备面板；序号越界复用 enhance.idx_missing）
    #     · use 道具使用 18 新键（新分类 道具使用；复用 sell.no_item / instance.结算_等待行动 /
    #       bt.stale_explore / enhance.idx_missing）
    # ★ C 档 21b（商店·买卖，35 新键 / 52 处替换，17 处同值幂等复用）⇒ 2173 → 2208
    #     · buy 名称路径 8 新键（shop.gold_short / buy_ok / equip_one … 共 17 处同值复用 21a 键）
    #     · sell 全分支 27 新键（新分类 商店出售）
    "commands": 196, "events": 146, "monster_mods": 140, "maps": 121, "worlds": 121,
    "achievements": 119, "item_templates": 99, "effect_rules": 85, "affixes": 76,
    "gather_pools": 68, "guild": 4, "instances": 27, "classes": 8, "races": 6,
    "pets": 16, "runes": 16, "passive_proc": 42, "dialogues": 39, "titles": 68,
}
# npcs 三表合表构成（旧版【12】的等价断言）
EXPECT_NPCS_SOURCES = {"town": 362, "wild": 47, "hidden": 22}
# items 的 quality 允许值**不在这里硬编**：从 `schemas/item.schema.json` 的 enum 读（单一真源）。
# 实测（2026-09-14）= ['blue', 'green', 'orange', 'purple', 'white']（品质色标，非英文品质名）。

PASS = 0
FAIL = 0
FAILURES: list = []


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


def _read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _pkg_module():
    """框架侧 `editor.packages`（域声明 / 落点 / 校验的唯一入口）。"""
    if os.path.abspath(FW_ROOT) not in sys.path:
        sys.path.insert(0, os.path.abspath(FW_ROOT))
    from editor import packages as PK      # noqa: PLC0415
    return PK


def main() -> int:
    print(f"框架仓 = {FW_ROOT}\n包     = {PKG_DIR}")
    print("（★ B14 开关后：包内 content/data|rules/*.json 即真源；导出器已退役 → 本门禁 = 冻结门禁）")
    if not os.path.isdir(PKG_DIR):
        print(f"❌ 包目录不存在：{PKG_DIR}")
        return 1
    PK = _pkg_module()

    # ---------------- 【7】包清单规范 ----------------
    print("\n【7】包清单（game.json）规范")
    man = PK.load_manifest(PKG_DIR)
    check("manifest 可读且为 dict", isinstance(man, dict) and bool(man), str(type(man)))
    for k in ("id", "name", "engine", "entry", "created", "domains"):
        check(f"manifest 有 {k} 字段", k in man, f"实际键={sorted(man)}")
    check(f"manifest.id == {PKG_ID!r}", man.get("id") == PKG_ID, repr(man.get("id")))
    declared = sorted(PK.declared_domain_ids(PKG_DIR))
    man_doms = sorted(man.get("domains") or [])
    check(f"manifest.domains == 包声明域（{len(declared)} 个）", declared == man_doms,
          f"清单独有 {sorted(set(man_doms) - set(declared))[:5]} / 声明独有 {sorted(set(declared) - set(man_doms))[:5]}")

    # ---------------- 【4】清单 ↔ 文件（双向） ----------------
    print("\n【4】清单 ↔ 数据文件（正反双向）")
    missing = []
    for d in declared:
        try:
            p = PK.domain_path(PKG_DIR, d)
        except KeyError as e:
            missing.append(f"{d}:{e}")
            continue
        if not os.path.isfile(p):
            missing.append(d)
    check(f"{len(declared)} 个声明域都有数据文件（落点由域 kind 决定）", not missing,
          f"缺 {missing[:MAX_REPORT]}")
    orphans = []
    aux_seen = []
    for sub, root in (("data", DATA_DIR), ("rules", RULES_DIR)):
        if not os.path.isdir(root):
            continue
        for fn in sorted(os.listdir(root)):
            if not fn.endswith(".json") or fn[:-5] in set(declared):
                continue
            if fn in AUX_FILES:
                aux_seen.append(f"content/{sub}/{fn}（{AUX_FILES[fn]}）")
                continue
            orphans.append(f"content/{sub}/{fn}")
    check("无孤儿域文件（data/rules 下每个 json 都已声明）", not orphans, f"孤儿 {orphans[:MAX_REPORT]}")
    print(f"  已登记辅助文件（非域表，跳过孤儿扫描）= {len(aux_seen)}：{aux_seen}")

    # ---------------- 【3】逐条过 schema + 非空 ----------------
    print("\n【3】逐域：条数 > 0 且逐条过 schema")
    empty, invalid = [], []
    counts = {}
    for d in declared:
        st = PK.domain_status(PKG_DIR, d)
        counts[d] = int(st.get("count", 0) or 0)
        if counts[d] == 0:
            empty.append(d)
        bad = list(st.get("invalid") or [])
        if bad or not st.get("ok"):
            invalid.append(f"{d}:{bad[:2]}")
    check(f"{len(declared)} 个域条数均 > 0（无静默空表）", not empty, f"空表 {empty[:MAX_REPORT]}")
    check(f"{len(declared)} 个域逐条校验 0 无效", not invalid, f"{invalid[:MAX_REPORT]}")
    print(f"  条目合计 = {sum(counts.values())}")

    # ---------------- 【5】冻结规模账 ----------------
    print("\n【5】冻结规模账（B14 收纳当刻实测）")
    for d, want in sorted(FROZEN_COUNTS.items()):
        got = counts.get(d, _read_json(os.path.join(DATA_DIR if os.path.isfile(
            os.path.join(DATA_DIR, d + ".json")) else RULES_DIR, d + ".json"), {}) or {})
        n = got if isinstance(got, int) else len(got)
        check(f"{d:<16} == {want}", n == want, f"实测 {n}")

    # ---------------- 【1】+【2】items 域专项 ----------------
    print("\n【1】items 域冻结规模 / key 形状")
    items = _read_json(os.path.join(DATA_DIR, "items.json"), {}) or {}
    check(f"items 条数 == {EXPECT_ITEMS}（合表后唯一物品，不是 1704）",
          len(items) == EXPECT_ITEMS, f"实测 {len(items)}")
    bad_keys = [k for k in items if not EXPECT_KEY_RE.match(k)]
    check("items 全部 key 匹配 ^[a-z][a-z0-9_]*$", not bad_keys, f"{bad_keys[:MAX_REPORT]}")

    print("\n【2】items 逐条字段（name/price/desc/quality）")
    q_enum = set(((((_read_json(ITEM_SCHEMA, {}) or {}).get("$defs") or {})
                   .get("item") or {}).get("properties") or {}).get("quality", {}).get("enum") or [])
    check("从 schemas/item.schema.json 读到 quality enum（非空）", bool(q_enum), f"实际={sorted(q_enum)}")
    miss_fields, bad_price, bad_q = [], [], []
    for k, v in items.items():
        if not isinstance(v, dict):
            miss_fields.append(f"{k}:非 dict")
            continue
        for f in ("name", "price", "desc"):
            if f not in v or v[f] in (None, ""):
                miss_fields.append(f"{k}:{f}")
        pr = v.get("price")
        if not isinstance(pr, (int, float)) or isinstance(pr, bool) or pr < 0:
            bad_price.append(f"{k}={pr!r}")
        q = v.get("quality")
        if q is not None and q not in q_enum:
            bad_q.append(f"{k}={q!r}")
    check("每条都有 name/price/desc", not miss_fields, f"{miss_fields[:MAX_REPORT]}")
    check("price 均为非负数", not bad_price, f"{bad_price[:MAX_REPORT]}")
    check("quality（有则）∈ schema enum", not bad_q, f"{bad_q[:MAX_REPORT]}")
    # schema 文件自身可用（缺了 → 上面【3】的校验就是空转）
    check("schemas/item.schema.json 存在", os.path.isfile(ITEM_SCHEMA), ITEM_SCHEMA)

    # ---------------- npcs 三表合表构成 ----------------
    print("\n【5b】npcs 域三表合表构成（town 362 + wild 47 + hidden 22 = 431）")
    npcs = _read_json(os.path.join(DATA_DIR, "npcs.json"), {}) or {}
    got_src: dict = {}
    for v in npcs.values():
        if isinstance(v, dict):
            got_src[str(v.get("source"))] = got_src.get(str(v.get("source")), 0) + 1
    check(f"npcs 条数 == {sum(EXPECT_NPCS_SOURCES.values())}", len(npcs) == sum(EXPECT_NPCS_SOURCES.values()),
          f"实测 {len(npcs)}")
    check("npcs source 分布 == 冻结账", {k: got_src.get(k, 0) for k in EXPECT_NPCS_SOURCES} == EXPECT_NPCS_SOURCES,
          f"实测 {got_src}")

    # ---------------- 【6】落盘规范 ----------------
    print("\n【6】落盘规范（UTF-8 无 BOM / LF / indent=2 / 末尾换行 / 外层键升序）")
    fmt_bad = []
    for sub in ("data", "rules"):
        root = os.path.join(PKG_DIR, "content", sub)
        if not os.path.isdir(root):
            continue
        for fn in sorted(os.listdir(root)):
            if not fn.endswith(".json"):
                continue
            p = os.path.join(root, fn)
            raw = open(p, "rb").read()
            probs = []
            if raw[:3] == b"\xef\xbb\xbf":
                probs.append("BOM")
            if b"\r\n" in raw:
                probs.append("CRLF")
            if not raw.endswith(b"\n"):
                probs.append("无末尾换行")
            try:
                obj = json.loads(raw.decode("utf-8-sig"))
            except ValueError:
                probs.append("JSON 坏")
                obj = None
            if isinstance(obj, dict):
                if list(obj) != sorted(obj):
                    probs.append("外层键非升序")
                if json.dumps(obj, ensure_ascii=False, indent=2) + "\n" != raw.decode("utf-8-sig"):
                    probs.append("非 indent=2 规范形")
            if probs:
                fmt_bad.append(f"content/{sub}/{fn}:{probs}")
    check("全部域文件满足落盘规范", not fmt_bad, f"{fmt_bad[:MAX_REPORT]}")

    # ---------------- 汇总 ----------------
    print(f"\n{'=' * 60}\n汇总：{PASS} 通过 / {FAIL} 失败")
    if FAILURES:
        print("红行：")
        for f in FAILURES:
            print("  ❌", f)
        print("\n修法：包内数据即真源 —— 改 `games/orlandia/content/<data|rules>/<域>.json`"
              "（或用编辑器 UI），别去改宿主 `game/data`（该目录已删）。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
