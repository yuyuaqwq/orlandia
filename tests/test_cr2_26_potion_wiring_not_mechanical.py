# -*- coding: utf-8 -*-
"""台账 C-R2.26 门禁 —— **44 件战斗药水的接线不是「白名单加键」能解决的**
（上一轮台账给本车道开的施工单据此被实测推翻，本件把结论钉成可判定断言）。

**它守什么**
------------
台账 §1 剩余清单登记「C-R2.26 = 44 件战斗药水接线」，并建议
「先做可机械判定的一族（能映射进 `_EFFECT_ACTION_KEYS` 的纯属性别名）」。

★ **本轮实测：那一族是空的。** 逐条核 29 个被拦下的 `special:` 族：

    ① `_EFFECT_ACTION_KEYS`(21) ∪ `_SHIELD_KINDS`(3) 与 29 个被拦族名的**交集 = 0**
       —— 一个都不在白名单里，**没有「加个键就通」的机械族**。
    ② 36 个 `POTION_EFFECTS` handler 全在，但**它们要的 battle 回调在引擎侧不存在**：
       `_hit_tgt` / `_res_gain` / `_add_shield` / `_branch_keys` / `_is_branch_of` /
       `_elem_mark_apply` / `_elem_reaction_boost` / `_elem_marks` /
       `_reaction_table_resolve` / `_player_stats` / `_deal_damage` 共 **10 个**逐个
       `grep 'def <名>'` 全仓 = 0 命中。**唯一例外是 `action_def_down`**，它已由包内
       `content/effect_actions.py:84` 提供（这一条我第一版写「11 个全无」是错的，已更正）。
    ③ ★★ 最要紧的一条：handler 的落点是**旧容器**，不是引擎现行形状。
       19/29 写 `player.setdefault('buffs', {})[…]`、5/29 写 `player['eff'][…]`；
       而 `content/bridge.py::player_to_actor` 明确**剔除 buffs/debuffs/hot/state
       四个旧键**（注释：同构键已废弃，透传只会造成脏残留），引擎侧对
       `buffs` / `debuffs` 的读口**全仓 = 0**。

⇒ **只往 `can_translate` 白名单里加键 = 玩家从「提示未迁移」变成「吃下去什么都不发生」**
—— 把一个显式拒绝换成一个静默空放，比现状更坏。

**断言组**
  (一) 正证档：`can_translate` 判据**确实有牙**（已通的白名单样本返 True）。
  (二) 交集档：**白名单 ∩ 29 个被拦族名 = 0**（本件的结论，可复算）。
  (三) 接缝档：handler 需要的 battle 回调**在引擎侧零存在**（逐个点名）。
  (四) 落点档：handler 写的旧容器里的药效键**在引擎侧零读口**
      ⇒ 证明「接线 = 换落点形状」，不是「接线 = 加白名单键」。
  (五) ★ 反证档（假门禁保险）：往白名单塞一个被拦族名 ⇒ 档 (二) 的 0 立刻变 1
      ⇒ 本门禁**不是恒绿档**，且证明「加键就能通」这条路确实是空的。
"""

import inspect
import io
import os
import sys

PKG = r"C:/Users/yuyu/framework-engine/games/orlandia"
ENG = r"C:/Users/yuyu/framework-engine"

sys.path.insert(0, PKG)
sys.path.insert(0, os.path.join(ENG, "extends"))
os.environ.setdefault("GWEN_TEST_MODE", "1")

FAILS = []


def check(name, ok, extra=""):
    print(("  ok   " if ok else "  FAIL ") + name + (("  | " + str(extra)) if extra else ""))
    if not ok:
        FAILS.append(name)


import content.effects.potion_effects as PE            # noqa: E402
import content.item_templates as IT                     # noqa: E402
import content.mech.item_use as IU                      # noqa: E402

# 文件头 ③ 替身回调清单（本件把「零存在」逐条钉住）
BATTLE_CBS = [
    "_hit_tgt", "_res_gain", "_add_shield", "_branch_keys", "_is_branch_of",
    "_elem_mark_apply", "_elem_reaction_boost", "_elem_marks",
    "_reaction_table_resolve", "_player_stats", "_deal_damage", "action_def_down",
]
# 44 件战斗内道具的 29 个被拦族名（C-R2.24 实测基线）
BLOCKED_KINDS = [
    "restore_resource", "resource_amp", "trap", "summon", "magic_resist", "mana_cost_down",
    "armor_break_pot", "block_pot", "phoenix", "resource_charge", "invuln", "crit_dmg_pot",
    "execute_pot", "full_tension", "heal_up", "steal_buff", "dot_amp", "lifesteal_pot",
    "morph", "restore_resource_full", "pene_magi_pot", "pene_pot", "vuln", "dodge_pot",
    "mana_restore", "buff_extend", "thorns_pot", "reaction", "apply_mark",
]

print("【档 一】正证：同一判据下确实会命中 ⇒ can_translate 不是恒 False")
_ok = IU.can_translate("special:shield_small;cast:1.4")
print("   can_translate('special:shield_small;cast:1.4') = %s" % _ok)
check("正证样本判 True（本判据有牙）", _ok is True, _ok)

print("【档 二】★ 交集：白名单 ∩ 29 个被拦族名 = 0 ⇒ 没有「加键就通」的机械族")
_white = set(IU._EFFECT_ACTION_KEYS).union(set(IU._SHIELD_KINDS))
_inter = sorted(_white.intersection(set(BLOCKED_KINDS)))
print("   白名单 %d 项（effect %d + shield %d）· 被拦族 %d 个"
      % (len(_white), len(IU._EFFECT_ACTION_KEYS), len(IU._SHIELD_KINDS), len(BLOCKED_KINDS)))
check("★ 白名单与被拦族名交集 = 0（台账建议的「机械族」不存在）", not _inter, _inter)

print("【档 三】接缝：handler 要的 battle 回调在引擎侧零存在")
_missing, _present = [], []
_src_cache = {}
for _root, _dirs, _fs in os.walk(ENG):
    _dirs[:] = [d for d in _dirs if d not in ("__pycache__", ".git", "_archive_unused")]
    for _f in _fs:
        if not _f.endswith(".py"):
            continue
        _fp = os.path.join(_root, _f)
        # 只扫**生产码**：`tests/` 里的假 battle（test_cr2_23 就自带一个
        # `def _res_gain(self, player, key, cap)`）不算「回调已存在」，
        # 否则会把自己门禁的结论算错（第一版就踩了这个，已更正）。
        _rel0 = os.path.relpath(_fp, ENG).replace("\\", "/")
        if "/tests/" in _rel0 or _rel0.startswith("tests/") or "/_archive_unused/" in _rel0:
            continue
        try:
            with io.open(_fp, encoding="utf-8", errors="replace") as _fh:
                _src_cache[_fp] = _fh.read()
        except Exception:
            continue
for _cb in BATTLE_CBS:
    _hit = sum(1 for _t in _src_cache.values() if ("def " + _cb + "(") in _t)
    if _hit:
        _present.append("%s(%d)" % (_cb, _hit))
    else:
        _missing.append(_cb)
print("   零存在 %d / %d：%s" % (len(_missing), len(BATTLE_CBS), ", ".join(_missing)))
print("   已有定义：%s" % (", ".join(_present) or "（无）"))
check("★ 除已存在的 action_def_down 外，10 个替身回调在引擎侧全部不存在（接线须先造形状）",
      len(_missing) == len(BATTLE_CBS) - 1, _present)

print("【档 四】落点：handler 写的旧容器在引擎侧零读口 ⇒ 接线 = 换形状")
_NEEDLES = ["phoenix_revive", "phoenix_used", "invuln_used"]
_readers = []
for _fp, _txt in _src_cache.items():
    _rel = os.path.relpath(_fp, ENG).replace("\\", "/")
    if "potion_effects.py" in _rel or "/tests/" in _rel:
        continue
    if _rel.startswith("editor/") or "glossary" in _rel:
        continue          # 编辑器词表 = 开发者文档，不是运行期读口
    for _n in _NEEDLES:
        if ('"%s"' % _n) in _txt or ("'%s'" % _n) in _txt:
            _readers.append((_rel, _n))
print("   引擎+包内容侧（去 potion_effects 定义处/测试/编辑器词表）内药效键出现 %d 处" % len(_readers))
for _r in _readers[:8]:
    print("     %-58s %s" % _r)
check("★ phoenix/invuln 三键在引擎侧零读口（写进旧容器 = 无人消费）", not _readers, _readers[:3])

print("【档 五】★ 反证：往白名单塞一个被拦族名 ⇒ 档 (二) 的 0 立刻变 1")
IU._EFFECT_ACTION_KEYS.add("phoenix")
_inter2 = sorted(set(IU._EFFECT_ACTION_KEYS).union(set(IU._SHIELD_KINDS))
                 .intersection(set(BLOCKED_KINDS)))
_got = IU.can_translate('special:phoenix:{"revive_hp":0.3}')
IU._EFFECT_ACTION_KEYS.discard("phoenix")
_back = IU.can_translate('special:phoenix:{"revive_hp":0.3}')
print("   加键后交集 = %s（原本 0）· can_translate = %s（原本 False）· 撤回后 = %s"
      % (_inter2, _got, _back))
check("★ 反证档：加键后交集非空且判 True ⇒ 档 (二)(三) 会红（不是恒绿档）",
      bool(_inter2) and _got is True and _back is False, (_inter2, _got, _back))

print()
if FAILS:
    print("★ 失败 %d 项：%s" % (len(FAILS), " / ".join(FAILS)))
    sys.exit(1)
print("全绿 %d 项" % 5)
