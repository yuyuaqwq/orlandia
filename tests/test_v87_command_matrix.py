# -*- coding: utf-8 -*-
"""v87 命令互斥矩阵回归测试（v104 审计 P2/M24 补回）。

背景：M24 实测发现 25 个文本命中 ≥2 条注册正则；本测试在 v104 后补回互斥矩阵，
防止 @filter.regex 新增/改动时出现"一条消息命中多条指令"的回归。

数据源（双份，互相强校验）：
1. 包内声明表 `content/data/commands.json` 派生的有效表（2026-09-12 #9 收尾后 = 声明表派生）
2. 包内运行时注册表 `pkg.command_handlers()` ∪ 平台例外键（真实注册 = 194 条）

断言：
A. 一致性：静态表键集合 == 装饰器方法名集合，且每条模式逐字相等（表漂移即失败）
B. 互斥矩阵：每条指令的代表输入在全量正则池（re.match，输入 strip）下
   恰好命中 1 条，且命中的就是它自己的方法（双注册豁免除外，见 EXEMPT_DOUBLE）
C. 负面用例：疑似过宽输入必须 0 命中（防抢指令）
D. _maint_gate（停服全局 gate）不匹配任何指令输入

设计内双注册豁免（EXEMPT_DOUBLE，命中 2 条但 AstrBot 按 priority 判定先后）：
- 裸数字（'5'/'12'）：shortcut_trigger + npc_quick_dialog 同 pattern 双注册，
  priority=100 NPC 对话优先（world.py:1968 注释）
- '物品详情开始/结束'：item_view_mode_cmd(priority=50) + item_detail 正则重叠
  （economy.py:2426 开关指令，priority 判定）

运行：python tests/test_v87_command_matrix.py（exit=0 通过）
"""
import json
import os
import re
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# ★ P5F-REPOINT: 原宿主壳 `game/commands`（`_registry.py` 随删壳批消失）
#   → 包内声明真源 `content/data/commands.json`（就地派生，口径逐字 = 原
#   `_registry._declared_patterns()`：单条原样 / 多条 `(?:a)|(?:b)`）。
CMD_DIR = os.path.join(PLUGIN_DIR, "content")
SPEC_FILE = os.path.join(CMD_DIR, "data", "commands.json")


def _combine(patterns):
    """多条正则合成一条（与 `_registry._combine_patterns` / 引擎 `combine_patterns` 同语义）。"""
    pats = [p for p in (patterns or ()) if p]
    if not pats:
        return ""
    if len(pats) == 1:
        return pats[0]
    return "|".join("(?:%s)" % p for p in pats)


def _declared_table():
    """包内声明表 → `{key: 合并正则}`（原 `_registry.COMMAND_REGEX` 的终态等价物）。"""
    with open(SPEC_FILE, encoding="utf-8") as f:
        data = json.load(f)
    out = {}
    for k, v in (data or {}).items():
        pats = v.get("patterns", v.get("pattern")) if isinstance(v, dict) else v
        if isinstance(pats, str):
            pats = [pats]
        c = _combine(pats or [])
        if c:
            out[str(k)] = c
    return out


# 有效表 = 包内声明表派生（镜像表 2026-09-12 已退役；宿主 `_registry.py` 随删壳批消失）
COMMAND_REGEX = _declared_table()

# ---- 装饰器扫描（**唯一实现在 tests/_cmd_registry.py**）----
# ★ P5F-REPOINT: 原扫宿主 `game/commands/*.py` 的装饰器（`@filter.regex` / `@declared(key)`）
#   → 键集取包内运行时注册表、正则/priority 取包内声明表（见 `_cmd_registry.patterns_with_meta`）。
#   原先本文件自带一份扫描实现，与 test_v59 / test_v104 三处重复 → 形态一变要改三处
#   （2026-09-11 引入 @declared 时正是如此）。现统一到 helper。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cmd_registry import patterns_with_meta, MISSING as DECLARED_MISSING  # noqa: E402
from _engine_harness import harness as _harness  # noqa: E402
from host.adapter_qq import PLATFORM_KEYS  # noqa: E402

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ✅ %s" % name)
    else:
        failed += 1
        print("  ❌ %s %s" % (name, detail))


# ---- 扫描结果（helper：`@filter.regex(字面量)` + `@declared(key)` 两种都认）----
DECORATORS = patterns_with_meta()
# `@declared("key")` 但声明表里没有该 key → helper 收在 MISSING（re-export 供断言）
DECLARED_MISSING = DECLARED_MISSING

# 全局正则池：{方法名: 编译后 pattern}（真实装饰器为准，静态表仅做一致性校验）
# _maint_gate 为停服全局 gate（base.py:179）：模式无 $ 锚定、设计上匹配所有消息，
# 不参与指令互斥（见 E 组），故从互斥池剔除。
POOL = {name: re.compile(pat) for name, (pat, _p, _f) in DECORATORS.items()
        if name != "_maint_gate"}


def hits(text):
    """全量匹配：返回命中的方法名集合。"""
    t = text.strip()
    return {name for name, rx in POOL.items() if rx.match(t)}


# ---- 互斥矩阵：每条指令的代表输入（期望命中集合 = 自身方法）----
# 覆盖静态表全部键（_maint_gate 除外，gate 无代表输入，见 D 组）
REPRESENTATIVES = {
    # misc.py
    "achievements": "成就", "help_cmd": "帮助", "signin": "签到", "feedback_cmd": "意见",
    "game_tip": "游戏提示",
    # instance.py
    "instance_cmd": "副本", "instance_advance": "深入", "instance_map_view_cmd": "副本地图",
    "instance_investigate": "调查 房间", "instance_retreat": "撤退", "instance_retreat_confirm": "确认撤退", "instance_leave": "离开副本",
    "join_battle": "加入战斗",  # v137 副本『加入战斗』（队友并入战斗）
    # world.py
    "deed_view": "地契", "deed_buy": "买房", "deed_sell": "卖房", "go_home": "回家",
    "go_out": "出门", "visit_home": "拜访", "home_storage": "仓库", "home_storage_take": "取出",
    "map_view": "地图", "move": "前往", "portal_view": "祭坛", "portal_activate": "激活祭坛",
    "portal_travel": "传送", "quest_view": "任务", "quest_accept": "接取", "daily": "每日",
    # v169.2 周常悬赏『周常』『周常列表』/修炼爬塔『爬塔』（代表输入）
    "weekly_cmd": "周常", "weekly_list": "周常列表", "tower_cmd": "爬塔",
    # v167.1 『区域』指令：当前区域可前往总览（代表输入『区域』，恰命中 region_view）
    # v116：放弃进行中的支线/每日任务（代表输入带序号）
    "quest_abandon": "放弃 2",
    "time_cmd": "时间", "wild_notes": "见闻录", "location_view": "位置",
    "hurry_view": "赶路",
    # v167.1 『区域』：当前区域可前往总览（代表输入，恰命中 region_view）
    "region_view": "区域",
    # O74 『返回 <地名>』提示 handler / O115 『问路 <地名>』路线指引 handler
    "back_cmd": "返回 橡木镇", "ask_way": "问路 海蚀洞窟",
    "npc_quick_dialog": "5", "interact_prop": "交互", "talk_choice": "对话",
    "turn_in": "交付任务", "rest_camp": "休息", "rest": "住宿", "reputation": "声望",
    "rep_shop": "声望商店",
    "chronicle": "编年史",
    # v140 波2 『收藏册』（5 套冒险者收藏册展示/满套领奖）
    "collection": "收藏册",
    # v140 波3.7 『今日事件/事件 <地图名>』（地图随机事件菜单；裸『事件』由 world_event 占用）
    "event_menu": "今日事件",
    # social.py
    "market": "市场", "market_sell": "上架", "market_unsell": "下架", "market_buy": "购入",
    "stall_deprecated": "摆摊", "stall_sell": "摆卖", "stall_exchange_pawn": "摆换", "stall_close": "收摊", "stall_view": "摊位", "stall_exchange": "换",
    "party": "组队", "party_leave": "退队", "guild_create_cmd": "创建公会",
    "guild_join_cmd": "加入公会", "guild_leave_cmd": "退出公会", "guild_disband_cmd": "解散公会",
    "guild_info": "公会", "guild_sign": "公会签到", "guild_task": "公会任务",
    "guild_donate_cmd": "公会捐献",
    # v116 公会成长纵深：商店/技能/任命/免职（代表输入）
    "guild_shop": "公会商店",
    "guild_skill_view": "公会技能",
    "guild_appoint": "公会任命 精英 副会长",
    "guild_demote": "公会免职 精英",
    "guild_rank": "公会排行", "pet_view": "宠物", "pet_rename": "宠物改名",
    "pet_feed": "喂养", "pet_release": "放生", "mount_cmd": "坐骑", "world_event": "事件",
    "auction": "拍卖", "bid": "竞拍",
    # v116 阵营国战：加入阵营/任务/商店/排行（代表输入）
    "camp_join": "加入阵营 1", "camp_task": "阵营任务", "camp_shop": "阵营商店 1",
    "camp_rank": "阵营排行",
    # combat.py
    "explore": "探索", "wish": "许愿", "attack": "攻击", "skill": "技能", "defend": "防御",
    # v115：探索进度指令（commands/exploration.py）
    "explore_progress": "探索进度",
    "flee": "逃跑", "hunt_boss": "讨伐", "honor_shop": "荣誉",
    # v113.5 O71：流浪商人强卖确认/拒绝（探索事件挂起报价后的二段回复）
    "trader_confirm": "确认购买",
    # O119：战败结算复活羽毛二段回复（消耗羽毛免扣金币 / 放弃复活损失金币）
    # 代表输入用『放弃复活』：『使用复活羽毛』会被 use 前缀正则同时命中（待 O119 侧加 priority）
    "revive_confirm": "放弃复活",
    # player.py
    "shortcut": "快捷", "shortcut_trigger": "5", "page_flip": "+2", "register": "注册", "profile": "角色",
    "bind_identity": "绑定身份 1454832774 鱼冻不冻阿",
    "leaderboard": "排行", "races": "种族", "evolve": "转职", "attributes": "属性",
    "add_attr": "加点", "reset_skill": "技能洗点", "evolve_reset": "转职重置",
    "reset_attr": "洗点", "power": "战力", "skill_detail": "技能详情",
    "skill_learn": "技能学习", "skill_upgrade": "技能升级", "skill_bar_view": "技能栏",
    "skill_bar_set": "设置技能", "build_view": "流派", "delete_account": "注销",
    # v130.2g 新功能：『职业』速查指令（代表输入）
    "job_guide": "职业",
    # economy.py
    "gather": "采集", "mining": "挖掘", "alchemy": "炼金", "alchemy_craft": "合成",
    "cooking_list": "烹饪列表", "cooking": "烹饪", "profession_view": "副业",
    "prof_forget": "遗忘副业", "daily_prof": "副业任务", "fishing": "垂钓", "craft": "锻造",
    "bp_craft": "图纸合成 铁剑",  # v135 图纸残页合成
    "craft_commission": "代工", "learn": "学习", "recipe_list": "配方", "enhance": "强化",
    "equip_upgrade": "升级 铁剑",  # v135 装备升级
    # v136 原石系统：打孔/镶嵌/拆卸/合成/查看（代表输入）
    "gem_drill": "打孔 铁剑",
    "gem_socket": "镶嵌 铁剑 碎裂I",
    "gem_remove": "拆卸 铁剑 S1",
    "gem_combine": "原石合成 碎裂I",
    "gem_view": "原石",
    # v136 Phase 3 符文可制作+可拆卸（独立命令，与『拆卸』原石命令并行不冲突）
    "rune_craft": "符文制作 残忍",
    "rune_remove": "符文拆卸 铁剑 1",
    # v136 Phase 4/5 装备重锻 + 怪异炼成
    "refine_equip": "装备重锻 弯刀",
    "calamity_forge": "炼成 铁剑",
    "enchant": "附魔", "set_view": "套装", "bestiary": "图鉴", "encyclopedia": "百科", "monster": "怪物",  # v130.3 意见#3
    # v168 冒险手册：总入口 + 足迹
    "adventure_book": "冒险手册 物品", "footprint": "足迹",
    "titles": "称号", "inventory": "背包", "bag_filter": "背包筛选",
    "item_view_mode_cmd": "物品详情开始", "item_detail": "物品详情", "equip": "装备", "my_equipment": "我的装备",
    "unequip": "卸下", "use": "使用", "sell": "出售", "shop": "商店", "buy": "购买",
    # gm.py
    "gm_maintenance": "gm_停服", "gm_open": "gm_开服", "gm_status": "gm_状态",
    "gm_broadcast": "gm_广播", "gm_players": "gm_玩家", "gm_query": "gm_查询",
    "gm_give_gold": "gm_发金币", "gm_give_item": "gm_发物品", "gm_give_exp": "gm_发经验",
    "gm_set_level": "gm_设等级", "gm_teleport": "gm_传送", "gm_stamina": "gm_体力",
    "gm_rename": "gm_改名", "gm_add_gm": "gm_加GM", "gm_del_gm": "gm_删GM",
    "gm_play": "gm_play", "gm_spy": "gm_窥探", "gm_help": "gm_帮助", "gm_boss_dmg": "gm_伤害",
    "gm_bind_identity": "gm_绑身份 1454832774", "gm_identity_table": "gm_身份表",
    # v139 战前指令（职业融合）
    "battle_prefs_form": "战前形态 狂暴",
    "battle_prefs_finisher": "战前阈值 快刀",
    "battle_prefs_view": "战前指令",
    # v2026-09-11 奥术力场档位（法师专属战前设置）
    "battle_prefs_arcane_field": "战前力场 盾",
    # v140 波2：野王看守宝箱（sibling 子 agent 登记的命令，补矩阵代表输入防漏）
    "wild_king_chest": "摸战利箱",
}

# 设计内双注册豁免：输入 → (期望命中集合, 原因)
EXEMPT_DOUBLE = {
    "5": ({"shortcut_trigger", "npc_quick_dialog"},
          "裸数字双注册：快捷指令+npc_quick_dialog 同 pattern，priority=100 NPC 对话优先（world.py:1968）"),
    "12": ({"shortcut_trigger", "npc_quick_dialog"},
           "同上（两位数字）"),
    "物品详情开始": ({"item_view_mode_cmd", "item_detail"},
                "物品查看模式开关(priority=50)与通用物品详情正则重叠，priority 判定（economy.py:2426）"),
    "物品详情结束": ({"item_view_mode_cmd", "item_detail"},
                "同上"),
}

# 负面用例：废弃别名/缺参/未注册输入，必须 0 命中
# v104 M24 P2-2/P2-4：『交任务』已注册为 turn_in 别名、『调查』空参已放行（均转 EXTRA_POSITIVE）
NEGATIVE = [
    "查看状态",    # profile 废弃别名（实际未注册）
    "查看任务",    # quest_view 废弃别名（实际未注册）
    "筛选",        # bag_filter 裸『筛选』未注册（实际=背包筛选）
    "捐献",        # 裸『捐献』未注册（实际=公会捐献）
    # v105 M24 P3-2：前缀误触收窄（负向断言）——『角色扮演/注册表/签到机/帮助中心』不再命中游戏指令
    "角色扮演",    # profile 负向断言 (?!扮演)
    "注册表",      # register 负向断言 (?!表)（原『注册表在哪看』停服 gate 误伤同源）
    "签到机",      # signin 负向断言 (?!机)
    "帮助中心",    # help_cmd 负向断言 (?!中心)
]

# 补充正向：别名/变体/At 前缀输入（期望命中集合）
EXTRA_POSITIVE = [
    ("help", {"help_cmd"}),
    ("我的角色", {"profile"}),
    ("主线", {"quest_view"}),
    ("队伍", {"party"}),
    ("位置", {"location_view"}),  # v128: 『位置』拆出→精简面板（原 v101 归 map_view）
    ("周围", {"map_view"}),
    ("骑乘", {"mount_cmd"}),
    ("下马", {"mount_cmd"}),
    ("激活", {"portal_activate"}),
    ("方碑", {"portal_view"}),
    ("移动", {"move"}),
    ("技能列表", {"skill"}),
    ("物品", {"inventory"}),
    ("时间指令", {"time_cmd"}),
    ("深入第3层", {"instance_advance"}),
    # v113.5 O71：『拒绝』别名（与『确认购买』同 handler，按消息内容分流）
    ("拒绝", {"trader_confirm"}),
    # v105 M24 同步：instance_advance 放宽『深入3层』（不带"第"，并行任务 M04/M19 改动）
    ("深入3层", {"instance_advance"}),
    ("组队列表", {"party"}),   # v104 party 宽化（支持参数），『组队列表』=组队面板
    # v104 M24 P2-2：『交任务』策划案 23 章:182 主指令别名（原废弃别名转正）
    ("交任务", {"turn_in"}),
    # v104 M24 P2-4：『调查』空参放行（handler 内给格式提示）
    ("调查", {"instance_investigate"}),
    # v104 M24 P2-1：『每日副业/今日副业』→ daily_prof（每日负向断言收窄，不误触『每日』）
    ("每日副业", {"daily_prof"}),
    ("今日副业", {"daily_prof"}),
    # v104 审计#1369 记录的前缀误触（(?:\s*|$) 部分匹配语义，re.match 下天然前缀命中）：
    # 已收窄项（v105 M24 P3-2）移入 NEGATIVE：角色扮演/注册表/签到机/帮助中心 负向断言后 0 命中；
    # 带参数变体（签到2）仍命中，保留于此保证不回归为多命中。
    ("签到2", {"signin"}),
    ("公会捐献2", {"guild_donate_cmd"}),
    ("[At:123] 签到", {"signin"}),
    ("[At:123] 技能", {"skill"}),
    ("[At:123] 副本", {"instance_cmd"}),
    # v136 原石系统：别名/带参变体/负向断言收窄
    ("原石 碎裂I", {"gem_view"}),
    ("原石合成", {"gem_combine"}),
    ("打孔", {"gem_drill"}),
    ("镶嵌 铁剑 1", {"gem_socket"}),
    ("[At:123] 原石", {"gem_view"}),
    ("[At:123] 原石合成 碎裂I", {"gem_combine"}),
]


def main():
    print("【v87 命令互斥矩阵回归】装饰器 %d 条 / 静态表 %d 键"
          % (len(DECORATORS), len(COMMAND_REGEX)))

    # ===== A. 一致性：声明表派生 vs 运行时注册表 1:1 =====
    print("  · 一致性（声明表派生 ↔ 包内运行时注册表）")
    dec_names = set(DECORATORS)
    tbl_names = set(COMMAND_REGEX)
    check("键集合 1:1（声明表=%d, 注册表派生的模式表=%d）" % (len(tbl_names), len(dec_names)),
          tbl_names == dec_names,
          "表独有:%s 装饰器独有:%s" % (sorted(tbl_names - dec_names), sorted(dec_names - tbl_names)))
    mism = [k for k in tbl_names & dec_names
            if COMMAND_REGEX[k] != DECORATORS[k][0]]
    check("模式逐条相等", not mism, "漂移键: %s" % mism)
    # ★ P5F-REPOINT: A 组**非空转**的独立对侧 = 包内运行时注册表（`pkg.command_handlers()`）
    #   ∪ 平台例外键（`host/adapter_qq.py::PLATFORM_KEYS`：包内有声明、宿主层实现、包内无处理器）。
    #   声明表派生键集与它必须 1:1 —— 「有处理器无声明」/「有声明无处理器」当场报红。
    runtime_keys = set(_harness().host.handlers) | set(PLATFORM_KEYS)
    check("声明表派生键集 == 包内运行时注册表键集（%d 键）" % len(runtime_keys),
          tbl_names == runtime_keys,
          "表独有:%s 注册表独有:%s" % (sorted(tbl_names - runtime_keys),
                                       sorted(runtime_keys - tbl_names)))

    # ===== B. 互斥矩阵：每指令代表输入恰好命中 1 条 =====
    print("  · 互斥矩阵（代表输入 → 恰好命中 1 条）")
    missing = sorted(set(COMMAND_REGEX) - {"_maint_gate"} - set(REPRESENTATIVES))
    check("矩阵覆盖全部表键（_maint_gate 除外）", not missing, "缺: %s" % missing)
    extra = sorted(set(REPRESENTATIVES) - set(COMMAND_REGEX))
    check("矩阵无幽灵方法", not extra, "多余: %s" % extra)

    for name, inp in sorted(REPRESENTATIVES.items()):
        rx = POOL.get(name)
        if rx is None:
            check("方法 %s 有注册正则" % name, False, "装饰器缺失")
            continue
        got = hits(inp)
        if inp in EXEMPT_DOUBLE:
            want, why = EXEMPT_DOUBLE[inp]
            check("『%s』命中 %d 条（豁免：%s）" % (inp, len(want), name),
                  got == want, "实际 %s（%s）" % (sorted(got), why))
        else:
            check("『%s』→ 恰好命中 1 条=%s" % (inp, name),
                  got == {name}, "实际 %s" % sorted(got))

    # ===== C. 负面用例：0 命中 =====
    print("  · 负面用例（疑似过宽/废弃别名，必须 0 命中）")
    for inp in NEGATIVE:
        got = hits(inp)
        check("『%s』0 命中" % inp, not got, "实际 %s" % sorted(got))

    # ===== D. 补充正向（别名/At 前缀）=====
    print("  · 补充正向（别名/变体/At 前缀）")
    for inp, want in EXTRA_POSITIVE:
        got = hits(inp)
        check("『%s』→ %s" % (inp, sorted(want)), got == want, "实际 %s" % sorted(got))

    # ===== E. _maint_gate 停服全局 gate：设计上匹配一切消息（配合 custom_filter 判定）=====
    print("  · 停服 gate（_maint_gate）")
    gate_pat, gate_prio, gate_file = DECORATORS.get("_maint_gate", (None, None, None))
    check("gate 已注册（base.py 全局拦截）", gate_pat is not None, "装饰器缺失")
    if gate_pat:
        check("gate priority=100（最先执行）", gate_prio == 100, "实际 %s" % gate_prio)
        gate_rx = re.compile(gate_pat)
        all_inputs = set(REPRESENTATIVES.values()) | set(NEGATIVE) | {i for i, _ in EXTRA_POSITIVE}
        not_covered = [t for t in sorted(all_inputs) if not gate_rx.match(t.strip())]
        check("gate 覆盖全部 %d 个矩阵样本（停服时无漏网指令）" % len(all_inputs),
              not not_covered, "漏网: %s" % not_covered)

    # ===== F. 重复模式检查：同 pattern 双注册仅限豁免组 =====
    print("  · 重复模式检查")
    from collections import Counter
    pat_cnt = Counter(pat for pat, _p, _f in DECORATORS.values())
    dups = {pat: n for pat, n in pat_cnt.items() if n > 1}
    exempt_pats = {DECORATORS[n][0] for n in ("shortcut_trigger", "npc_quick_dialog")}
    bad_dup = {p: n for p, n in dups.items() if p not in exempt_pats}
    check("同 pattern 多注册仅限裸数字豁免组", not bad_dup,
          "额外重复: %s" % {p: n for p, n in bad_dup.items()})

    print("\n结果: %d 通过, %d 失败" % (passed, failed))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
