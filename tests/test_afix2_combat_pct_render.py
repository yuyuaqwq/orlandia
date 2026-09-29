# -*- coding: utf-8 -*-
"""审计 B2 自开口（族：玩家可见比率被向零截断）的**第三个命令模块**那一面。

前两轮收口：
  · 8b2d6cb  content/economy_cmds.py 文件内 12 处
  · 8265c82  升成包级单源 catalog_core.pct_str + world_cmds 7 处 + economy 再 7 处
本轮（combat_cmds）：同一渲染口径在**战斗面**仍是裸写法，共 15 处 ——
  技能面板 power 维度（列表 + 曲线）/ 吸血（列表 + 曲线）/ 敌人 DOT 抗性 /
  5 处血条 pct / 2 处祝福 pct（银行家舍入 round）/ Boss 贡献黄金占比。
★ 这一个面是玩家**天天点**的：技能列表、战斗开始/回合血条、Boss 结算。
实测（真调生产 _skill_list_gains，304 行）：改前 70 行屏显少 1
（sk_bing_zhui 印「伤害 115%」而真值 116%，因 1.16*100 = 115.99999999999999），
改后 MISMATCH=0；血条 7/9 由 77% 改 78%。

本判据钉住的是这一类（数据驱动，不写死是哪几条）：
  1. 单源：15 处走 catalog_core.pct_str（按**源码行形状**取真实调用点，不靠行号）
  2. 活代码零裸截断：combat_cmds.py 里 int(...*100) / round(...*100) 形状归零
  3. 端到端：真调生产渲染口，玩家看到的那一行 == half-up 真值（覆盖面自检）
  4. 整数量级零改动：0.02->2% / 0.5->50% / 1.0->100%
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402,F401

from _check import bind_check  # noqa: E402

passed = failed = 0
check = bind_check(globals(), "passed", "failed")

_CC_SRC = os.path.join(str(_paths.PKG_ROOT), "content", "catalog_core.py")
_CB = os.path.join(str(_paths.PKG_ROOT), "content", "combat_cmds.py")
_skills = os.path.join(str(_paths.PKG_ROOT), "content", "data", "skills.json")
_cb_src = open(_CB, encoding="utf-8").read()
_cb_lines = _cb_src.split("\n")

# ---------------------------------------------------------------- 1 单源
_sites = [(i, ln) for i, ln in enumerate(_cb_lines, 1) if "_cc.pct_str(" in ln]
check("15 处战斗面比率走包级单源 _cc.pct_str（技能面板/吸血/抗性/血条/祝福/Boss贡献）",
      len(_sites) == 15,
      "combat_cmds.py 上 _cc.pct_str 调用点 %d 处（应 15）—— 调用点被回退或改写" % len(_sites))
check("combat_cmds 已 import catalog_core（_cc）—— 单源可寻址",
      re.search(r"^from \. import catalog_core as _cc\b", _cb_src, re.M) is not None,
      "combat_cmds.py 上没有 `from . import catalog_core as _cc`")
check("包级单源 pct_str 仍在 catalog_core（未被搬走）",
      "def pct_str(v)" in open(_CC_SRC, encoding="utf-8").read(),
      "catalog_core 上没有 pct_str —— 包级出口缺失")

# ------------------------------------------------------- 2 活代码零裸截断
_trunc = re.compile(r"\bint\(\s*[^()]*\*\s*100\s*\)")
_bare = [(i, ln.strip()[:80]) for i, ln in enumerate(_cb_lines, 1) if _trunc.search(ln)]
check("战斗面活代码零裸 int(...*100) 截断", not _bare,
      "combat_cmds.py 仍有 %d 处裸截断：%s" % (len(_bare), _bare[:3]))
_bank = [(i, ln.strip()[:80]) for i, ln in enumerate(_cb_lines, 1)
         if re.search(r"\bround\([^()]*\*\s*100\s*\)", ln)]
check("战斗面活代码零裸 round(...*100)（银行家舍入会让平局印 0%）", not _bank,
      "combat_cmds.py 仍有 %d 处裸 round(...*100)：%s" % (len(_bank), _bank[:3]))

# ------------------------------------------------------- 3 端到端（真跑）
sys.path[:0] = [str(_paths.ENGINE_ROOT), str(_paths.ENGINE_ROOT) + "/extends",
                str(_paths.PKG_ROOT), str(_paths.PKG_ROOT) + "/tests"]
os.environ.setdefault("GWEN_TEST_MODE", "1")
os.environ.setdefault("GWEN_GAME_DB", os.path.join(
    os.environ.get("LOCALAPPDATA", "."), "Temp", "_afix2_combat_pct_probe.db"))
try:
    from content import combat_cmds as C          # noqa: E402
    from content import catalog_core as _cc       # noqa: E402
    from ext_combat.battle.formulas import skill_power_mult   # noqa: E402
    _data = json.load(open(_skills, encoding="utf-8"))
    _mismatch = []
    _n = 0
    for _sid, _info in _data.items():
        if not isinstance(_info, dict) or not _info.get("power"):
            continue
        _line = " ".join(C._skill_list_gains(None, _info, 1))
        _n += 1
        _m = re.search(r"(?:伤害|治疗)\s*(\d+)%", _line)
        if not _m:
            continue
        _truth = _cc.pct_str(_info["power"] * skill_power_mult(1, _info))
        if _m.group(1) != _truth:
            _mismatch.append((_sid, _m.group(1), _truth))
    check("技能面板覆盖面自检（域里确有带 power 的技能）", _n > 100, "只找到 %d 个带 power 的技能 —— 判据覆盖面不足" % _n)
    check("技能面板 %d 行屏显 == half-up 真值（改前 70 行少 1）" % _n, not _mismatch,
          "屏显与真值不符 %d 行：%s" % (len(_mismatch), _mismatch[:4]))
    # 逐格核对：真调生产渲染口
    _power_probe = _data.get("sk_bing_zhui")
    if _power_probe:
        _line = " ".join(C._skill_list_gains(None, _power_probe, 1))
        check("已知截断格 sk_bing_zhui 印 116%（改前 115%，float 误差 115.9999…）",
              "116%" in _line, "屏显是 %r —— 截断复发" % _line[:50])
    check("血条 7/9 印 78%（改前 77%）", int(_cc.pct_str(7 / 9)) == 78,
          "7/9 印 %d，应 78" % int(_cc.pct_str(7 / 9)))
    # ------------------------------------------------ 4 整数量级零改动
    for _v, _want in ((0.02, "2"), (0.5, "50"), (1.0, "100"), (0.0, "0"), (0.145, "14"), (0.015, "2")):
        check("整数量级 %s -> %s%%" % (_v, _want), _cc.pct_str(_v) == _want,
              "pct_str(%s)=%s，应 %s" % (_v, _cc.pct_str(_v), _want))
except Exception as _e:                      # 修正被撤 / 装载失败 ⇒ 报红，不静默
    check("生产渲染口可调（import content.combat_cmds + 真调 _skill_list_gains）", False,
          "装载或调用失败：%s: %s" % (type(_e).__name__, _e))

print("afix2_combat_pct: %d/%d" % (passed, failed))
raise SystemExit(1 if failed else 0)
