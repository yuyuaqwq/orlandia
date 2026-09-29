# -*- coding: utf-8 -*-
"""台账 C-R2.24 门禁 —— **战斗中「战斗药水」有 44 件在真跑路径上被拦下**
（玩家吃到 `use.not_migrated` = 「⚠️ 该道具的战斗内效果尚未迁移」）。

★ 本件把上一轮 C-R2.23 的结论**往前推了一层**（不是推翻，是把「死在哪一环」定位准了）
------------------------------------------------------------------------------------
C-R2.23 说「熔核之心写进 `buffs` 的减伤零消费者」。本轮实测发现：**它根本走不到那行**。
真实顺序（`content/economy_cmds.py::use` 的战斗内分支，逐字读过）：

    ① `meta["battle_ok"]`   → 模板允许战斗中用吗？`restore_resource_full` = **True**（放行）
    ② `IT.TEMPLATES[tpl](ctx)` → 产 payload = `special:restore_resource_full:{...}`
    ③ `can_translate(payload)` → **False**（`special:` 家族只认 `_EFFECT_ACTION_KEYS`(21)
       与 `_SHIELD_KINDS`(3)，`restore_resource_full` 两边都不在）
    ④ ⇒ 直接 `yield use.not_migrated` + **return**（不扣道具、不占刻、机制一个字没跑）

★ 所以「熔核之心减伤是死机制」是**第二层**的病；**第一层**是这 44 件连机制都没被调用。
而 `content/effects/potion_effects.py` 的 36 个 handler（含 `eff_restore_resource_full`）
**全仓零调用方**——`POTION_EFFECTS` 这个字典被导出，但没有任何 `.get(...)` 消费点。

**它守什么**
--------
把「战斗中 44 件药水被 `can_translate` 拦下」变成**常驻可判定**的断言。
一旦有人往白名单里接线（或把这些 effect 从 `_V130_ITEM_EFFECTS` 摘掉），
本门禁**会红**并要求同步改判据 ⇒ 杜绝「机制悄悄接上、没人知道这道闸还在」。

**断言组**
  (一) 正证档：**同一判据下确实会命中**（`buff:atk_up;cast:1.4` ⇒ True）
      ⇒ 证明 `can_translate` 不是恒 False，判据有牙。
  (二) 范围档：`battle_ok=True` 的物品里，被拦下的**逐条**列出（数量 + 代表样本）。
  (三) 死机制档：`POTION_EFFECTS` 字典**零消费方**（全仓 `.get(` 扫描）。
  (四) ★ 反证档（假门禁保险）：往白名单塞一个键 ⇒ 命中数**立刻变小**
      ⇒ 本门禁**不是恒绿档**。
"""

import io
import json
import os
import re
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


# ============================================================
# 0. 取件（与运行时**同一条路**：`economy_cmds` 用的就是这两个符号）
# ============================================================
import content.item_templates as IT                       # noqa: E402
import content.mech.item_use as IU                        # noqa: E402

_ITEMS = os.path.join(PKG, "content", "data", "items.json")


class _Ctx:
    """只给被测模板用到的口子（`battle` 非 None = 战斗内；`hook` 是模板的副作用钩）。"""

    def __init__(self, d):
        self.data = d
        self.battle = object()
        self.group_id = "g"
        self.qq_id = "q"
        self.player = {}

    def hook(self, *a, **k):
        return None


def _payload_of(v):
    """复刻 `economy_cmds::use` 战斗内分支的 payload 拼法（逐字同款）。"""
    tpl = IT.infer_template(v)
    if tpl is None or tpl not in IT.TEMPLATES:
        return None
    r = IT.TEMPLATES[tpl](_Ctx(v))
    p = r.payload if getattr(r, "payload", None) is not None else "0"
    it = v.get("cast")
    if it:
        p = (p + ";cast:%s" % it) if p else ("cast:%s" % it)
    return p


print("【档 一】正证：同一判据下**确实会命中** ⇒ can_translate 不是恒 False")
_ok = IU.can_translate("buff:atk_up;cast:1.4")
print("   can_translate('buff:atk_up;cast:1.4') = %s" % _ok)
check("正证样本判 True（本判据有牙）", _ok is True, _ok)
check("正证样本的 effect 名在白名单里",
      "buff_atk" in IU._EFFECT_ACTION_KEYS, sorted(IU._EFFECT_ACTION_KEYS)[:3])

print("【档 二】范围：battle_ok=True 的物品里，被 can_translate 拦下的逐条")
_items = json.load(io.open(_ITEMS, encoding="utf-8"))
blocked, live = [], 0
for k, v in _items.items():
    if not isinstance(v, dict) or not v.get("effect"):
        continue
    try:
        tpl = IT.infer_template(v)
    except Exception:
        continue
    if tpl is None or tpl not in IT.TEMPLATES:
        continue
    if not (IT.META.get(tpl) or {}).get("battle_ok"):
        continue
    try:
        p = _payload_of(v)
    except Exception:
        continue
    if p is None:
        continue
    if IU.can_translate(p):
        live += 1
    else:
        blocked.append((k, tpl, p))

print("   战斗内可翻译 %d 件 · **被拦下 %d 件**" % (live, len(blocked)))
# ★ C-R2.27（2026-09-29）：面板快照型 8 族接线 ⇒ 被拦下的件数 **44 → 35**（-9）。
# ★ C-R2.28A（2026-09-29）：`heal_up` 接入面板快照型（第 9 族）⇒ **35 → 34**（-1）。
# ★ C-R2.28B（2026-09-29）：`buff_extend` 接入**到期顺延族**（新形状）⇒ **34 → 33**（-1）。
# ★ C-R2.29A（2026-09-29）：`execute_pot` 接入**乘区触发族**（第三种形状）⇒ **33 → 32**（-1）。
#   实跑 = 战斗内可翻译 63 / 被拦下 32（正是本件接的那 1 件）。
#   不是判据放松：本条针对**当前真实缺口清单**，
#   接线使缺口变小是**事实推进**，不是判据失效。
#   判据只跟着事实走，**断言强度未变**（仍是精确等值，不是「≤ 35」那种允许集合）。
# ★ C-R2.29B（2026-09-29）：`mana_cost_down` 接入**消耗折扣族**（第四种形状，
#   落 `bonus.cost.mp_pct` + `effect_expire` 到期归零）⇒ **32 → 31**（-1）。
#   实跑 = 战斗内可翻译 64 / 被拦下 31（正是本件接的那 1 件）。
# ★ C-R2.30（2026-09-29）：`mana_restore` 接入**第 5 族**（回蓝 + 消耗折扣）⇒ **31 → 30**（-1）。
#   实跑 = 战斗内可翻译 65 / 被拦下 30（正是本件接的那 1 件）。
#   仍是**精确等值**断言，不是「≤ 31」那种允许集合：接线使缺口变小是**事实推进**。
check("被拦下的件数 = 30（C-R2.30 mana_restore 接线后基线）", len(blocked) == 30, len(blocked))
_molten = [b for b in blocked if b[0] == "i_molten_core"]
check("熔核之心在名单内（承 C-R2.23）", len(_molten) == 1, _molten)
check("熔核之心的 payload = special:restore_resource_full:{...}",
      bool(_molten) and _molten[0][2].startswith("special:restore_resource_full:"), _molten[:1])
# 机制型 special 是最大的一族（_V130_ITEM_EFFECTS 声明了它，翻译器却没有）
_mech = [b for b in blocked if b[2].startswith("special:")]
check("机制型 special 占多数（%d/%d）" % (len(_mech), len(blocked)),
      len(_mech) * 2 > len(blocked), len(_mech))
print("   --- 前 6 条 ---")
for b in blocked[:6]:
    print("     %-24s %-22s %s" % (b[0], b[1], b[2][:56]))

print("【档 三】死机制：POTION_EFFECTS 字典零消费方（handler 全仓没人调）")
_hits = []
for dp, dirs, fs in os.walk(PKG):
    dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "tests")]
    for f in fs:
        if not f.endswith(".py"):
            continue
        fp = os.path.join(dp, f)
        rel = os.path.relpath(fp, PKG).replace("\\", "/")
        if rel.endswith("effects/potion_effects.py") or rel.endswith("effects/__init__.py"):
            continue          # 定义处与导出处不算「消费方」
        try:
            with io.open(fp, "r", encoding="utf-8", errors="replace") as fh:
                for i, ln in enumerate(fh.read().splitlines(), 1):
                    if "POTION_EFFECTS" in ln and ".get(" in ln:
                        _hits.append((rel, i, ln.strip()[:90]))
        except Exception:
            continue
print("   全包（去定义/导出/测试）内 `POTION_EFFECTS...get(` 命中 %d 处" % len(_hits))
check("★ POTION_EFFECTS 零消费方 ⇒ 36 个 handler 永不执行", not _hits, _hits[:2])

print("【档 四】★ 反证：往白名单塞一个键 ⇒ 命中数立刻变小（不是恒绿档）")
_before = len(blocked)
# ★ C-R2.27：原版用 magic_resist，但它已被 C-R2.27 接亿（面板快照型）
#   ⇒ 旧反证档失效了（加键与不加键都是 True）。
#   改用一个**仍未接线**的族名 phoenix（机制型，属 R2.2 引擎立项）。
_PROBE = "phoenix"
IU._EFFECT_ACTION_KEYS.add(_PROBE)
_try = IU.can_translate("special:%s;cast:2.0" % _PROBE)
IU._EFFECT_ACTION_KEYS.discard(_PROBE)
_after_ok = IU.can_translate("special:%s;cast:2.0" % _PROBE)
print("   加键后 can_translate = %s（原本 False）· 撤回后 = %s" % (_try, _after_ok))
check("★ 反证档：加键后判 True ⇒ 本门禁会红（不是恒绿）", _try is True and _after_ok is False,
      (_try, _after_ok))
# 逐条重算：接上之后这份名单应当**变短**
_new = []
for k, v in _items.items():
    if not isinstance(v, dict) or not v.get("effect"):
        continue
    try:
        tpl = IT.infer_template(v)
    except Exception:
        continue
    if tpl is None or tpl not in IT.TEMPLATES:
        continue
    if not (IT.META.get(tpl) or {}).get("battle_ok"):
        continue
    try:
        p = _payload_of(v)
    except Exception:
        continue
    if p is None:
        continue
    IU._EFFECT_ACTION_KEYS.add(_PROBE)
    r2 = IU.can_translate(p)
    IU._EFFECT_ACTION_KEYS.discard(_PROBE)
    if not r2:
        _new.append((k, tpl, p))
print("   接线后被拦件数 = %d（原 %d）" % (len(_new), _before))
check("接线后名单确实变短（%d < %d）⇒ 判据跟着事实走" % (len(_new), _before),
      len(_new) < _before, (len(_new), _before))

print()
if FAILS:
    print("★ 失败 %d 项：%s" % (len(FAILS), " / ".join(FAILS)))
else:
    print("全绿。")
    print("  ⇒ 战斗中 %d 件战斗药水仍被 can_translate 拦下 ⇒ 玩家吃到 use.not_migrated。" % len(blocked))
    print("  ⇒ 熔核之心的减伤是**第二层**病（第一层：机制压根没被调用）。")
    print("  ⇒ 本批**只加门禁**：接线是内容侧设计决定（走哪条路 / 数值口径），需单独立项。")
sys.exit(1 if FAILS else 0)
