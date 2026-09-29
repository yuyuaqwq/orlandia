# -*- coding: utf-8 -*-
"""台账 C-R2.23 门禁 —— 熔核之心的「战损代价」是**死机制**（写进 `buffs`，零消费者）。

**它守什么**
----------
`content/effects/potion_effects.py::eff_restore_resource_full` 的 penalty 分支写两处：

```python
player.setdefault('buffs', {})["reduce_all"] = -penalty      # ← 死键
player['reduce_all_left'] = turns                             # ← 死键
```

而**引擎全仓（`extends/` + `saintess_engine/`）对字符串 `"buffs"` 零命中** ——
战斗减伤的活路是 `content/mech/team_procs.py::team_taken_reduce`：
它写 `effects["team:reduce:<标签>"]` 并挂 **`taken_calc`** 触发器，由 `_damage_actor` 消费。
⇒ 本 potion 写的 `buffs` 容器**没有任何消费者**。

**症状 = 玩家可见错值（不是「不报错」）**：屏上仍印
「🔥 熔核之心爆发！… 代价：3 刻内 全减伤 -30%（受损加重）」
（`potion.nucleus_full_cost`）⇒ 玩家为一个**从未生效**的代价付了资源，机制是假的。

**★ 为什么本门禁是「不许它继续是死的」而不是「不许它死」**
本批**只加门禁、不改机制**（把减伤接到容器是设计决定 = 内容侧口径，且要动机制消费链）。
门禁的作用 = 把「写了没人读」这件事实变成**常驻可判定**的断言：
一旦有人把 `buffs` 接到消费面（或把它删干净），本门禁会**红**并要求同步改判据
—— 杜绝「机制悄悄接上、但没人知道 dead 键已经活了」。

**断言组**
  (一) 正证档：真跑 `eff_restore_resource_full` ⇒ 屏上话**确实承诺**减伤 + 确实写进 `buffs`
      （证明「承诺存在」与「写入存在」两件事都是真的，不是幻觉）
  (二) 死机制档：引擎两棵树对 `"buffs"` 零命中（消费面为空）
  (三) 活路反证：`team_taken_reduce` 写的是 `effects` + `taken_calc`（**对照证明机制有活形态**）
  (四) 反证档（★ 假门禁保险）：若 `buffs` 真的被接上消费面 ⇒ 档 (二) 立刻红
      ⇒ 本门禁**不是恒绿档**。
"""

import inspect
import io
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
# 0. 取件
# ============================================================
from content.effects import potion_effects as PE                     # noqa: E402
import content.mech.team_procs as TP                                 # noqa: E402

PE._res_mine = lambda b, p, k: True
PE._item_res_def = lambda k: {"max": 100, "name": "星核"}


class _P(dict):
    def setdefault(self, k, d=None):
        return dict.setdefault(self, k, d)


class _B:
    """只给被测函数真正用到的那一个口子（_res_gain）—— 别做万能替身。"""
    def _res_gain(self, player, key, cap):
        player.setdefault("res", {})[key] = cap
        return cap


print("【档 一】正证：屏上确实承诺 + 确实写进 buffs（两件事都得是真的）")
p = _P({"uid": "p1", "level": 30})
msg = PE.eff_restore_resource_full(_B(), p,
                                   {"key": "xinghe", "penalty_pct": 0.30, "penalty_turns": 3})
print("   屏上话：", msg)
buffs = p.get("buffs") or {}
check("屏上话含『减伤 -30%』的承诺", "减伤" in msg and "-30%" in msg, msg)
check("写进 buffs['reduce_all'] = -0.30",
      abs(float(buffs.get("reduce_all", 0)) + 0.30) < 1e-9, buffs.get("reduce_all"))
check("写进 reduce_all_left = 3", p.get("reduce_all_left") == 3, p.get("reduce_all_left"))

print("【档 二】死机制：引擎两棵树对 \"buffs\" 零命中（= 消费面为空）")
# ★ 本档改用**纯 Python 扫描**：第一版写的是 subprocess 调 `grep`，
#    而本机 msys grep 不识 `C:/` 路径（对纯 Python 读到的文件直接返回 rc=1，
#    即成功命中也报「零命中」）⇒ **连反证都抱不住它**（已实测确认）。
#    真遇到的表现就是「档二在打印的时候全绿」。
# ★ 口径要紧：只认**引擎对 `buffs` 容器的读口**，不误报别人的局部变量。
#   实测教训（本档第二版自踩）：纯扫描拿「字符串含 buffs」当规则 →
#   会把 `_consume_hit_buffs` 里的**局部变量** `hit_buffs` 也算成 21 处 → 真实事实被否定。
#   正确规则 = 引擎容器为 `actor["buffs"]`，即**引号引号的字面量**（不是 `hit_buffs` 这种标识符前缀）。
_CONTAINER = re.compile(r"""["']buffs["']""")


def _scan_tree(root, skip_dirs=()):
    """返回**引号引号的 buffs 容器**读口的位置（非本地变量 `hit_buffs`）。"""
    hits = []
    for dp, dirs, fs in os.walk(root):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for f in fs:
            if not f.endswith(".py"):
                continue
            fp = os.path.join(dp, f)
            try:
                with io.open(fp, "r", encoding="utf-8", errors="replace") as fh:
                    txt = fh.read()
            except Exception:
                continue
            for i, ln in enumerate(txt.splitlines(), 1):
                if _CONTAINER.search(ln):
                    hits.append((os.path.relpath(fp, root).replace("\\", "/"), i, ln.strip()[:100]))
    return hits


for sub in ("extends", "saintess_engine"):
    lines = _scan_tree(os.path.join(ENG, sub))
    print("   扫 %s/ \"buffs\" 容器 ⇒ %d 行" % (sub, len(lines)))
    check("引擎 %s 对 \"buffs\" 容器零读口（本件要修的那一族）" % sub, not lines,
          lines[:2])

print("【档 三】活路反证：减伤确有活形态（effects + taken_calc）")
tsrc = inspect.getsource(TP.team_taken_reduce)
check("活路写 effects 条目", 'a.setdefault("effects", {})[state_key]' in tsrc)
check("活路挂 taken_calc 触发器", '"taken_calc"' in tsrc)
check("活路不读 buffs（两者是**不相连**的两条路）", "buffs" not in tsrc)

print("【档 四】★ 假门禁保险：本门禁不是恒绿档")
# 若有人把 buffs 接上消费面，本档会红 ⇒ 证明判据仍把把关
alive = len(_scan_tree(ENG, skip_dirs=("games", ".git")))
print("   引擎树（不含 games/）内 \"buffs\" **容器** 读口共 %d 处" % alive)
check("★ 引擎树内 \"buffs\" 仍为 0 处（一旦被接上，本门禁必红 ⇒ 不是恒绿）", alive == 0, alive)

print()
if FAILS:
    print("★ 失败 %d 项：%s" % (len(FAILS), " / ".join(FAILS)))
else:
    print("全绿。")
    print("  ⇒ 熔核之心『战损代价』的减伤写进 buffs 容器，引擎零消费者 ⇒ 机制为死。")
    print("  ⇒ 本批**只加门禁**：把减伤接到 effects 容器 = 内容侧设计决定，需单独立项。")
sys.exit(1 if FAILS else 0)
