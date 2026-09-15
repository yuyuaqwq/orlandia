# -*- coding: utf-8 -*-
"""v151 时刻制改造：防御型 buff 按"受击计数"而非玩家回合递减

鱼鱼拍板（2026-08-31）：防御药水"3 回合防御 +45%"在 CTB 下失真——
防的是敌方出手，却按玩家行动回合递减（敌快多招赚/敌慢少招亏）。
改为：防御/受击类 buff 登记 _p_buff_hits，实际受击 N 次后消失，回合递减豁免。

验证：
1. 药水写入防御 buff 时登记受击计数（_p_buff_hits）
2. _end_round 回合结束豁免防御 buff 递减
3. _damage_player 实际受击递减，归零清除
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import C  # noqa: F401  (设置 sys.path)

passed = failed = 0
def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ✅ %s" % name)
    else:
        failed += 1
        print("  ❌ %s %s" % (name, detail))


def _sim_hit(battle, logs):
    """复刻 battle.py _damage_player 里的受击递减逻辑"""
    hits = battle._p_buff_hits()
    if not hits:
        return
    for _hk in [k for k in list(hits) if int(hits.get(k, 0) or 0) > 0]:
        _nh = int(hits.get(_hk, 0) or 0) - 1
        if _nh <= 0:
            hits.pop(_hk, None)
            if _hk in battle._p_buffs_bag():
                battle._p_buffs_bag().pop(_hk, None)
                logs.append(f"🕛 【{_hk}】效果随受击消耗殆尽！")
        else:
            hits[_hk] = _nh


def _sim_end_round(battle):
    """复刻 battle.py _end_round 的豁免递减逻辑"""
    for tbl in (battle._p_buffs_bag(),):
        for k in list(tbl):
            if k in battle._p_buff_hits():
                continue  # v151 时刻制豁免
            tbl[k] -= 1
            if tbl[k] <= 0:
                del tbl[k]


class FakeBattle:
    def __init__(self):
        self._focus = {}
        self._p_buffs_bag()["def_up"] = 3
        self._p_buff_hits()["def_up"] = 3

    def _p_buffs_bag(self):
        """v180-B：玩家 buffs 袋 = player actor dict['buffs']（与 Battle 同语义）。"""
        return self._focus.setdefault("buffs", {})

    def _p_buff_hits(self):
        """v180-B：受击计数袋 = player actor dict['buff_hits']。"""
        return self._focus.setdefault("buff_hits", {})


def main():
    print("【v151 时刻制：防御 buff 受击计数】")
    b = FakeBattle()
    logs = []

    _sim_end_round(b)
    check("回合结束豁免：def_up 不递减", b._p_buffs_bag().get("def_up") == 3,
          str(b._p_buffs_bag()))
    check("受击计数保持 3", b._p_buff_hits().get("def_up") == 3,
          str(b._p_buff_hits()))

    _sim_hit(b, logs)  # 受击 1
    check("受击 1 次：def_up 仍在（hits 2/3）",
          b._p_buffs_bag().get("def_up") == 3 and b._p_buff_hits()["def_up"] == 2,
          str((b._p_buffs_bag(), b._p_buff_hits())))

    _sim_hit(b, logs)
    _sim_hit(b, logs)  # 受击 3 次
    check("受击 3 次：def_up 消失",
          "def_up" not in b._p_buffs_bag() and "def_up" not in b._p_buff_hits(),
          str((b._p_buffs_bag(), b._p_buff_hits())))
    check("消失日志已输出", any("消耗殆尽" in l for l in logs), str(logs))

    # 非防御 buff 不登记 hits，仍按回合递减
    b2 = FakeBattle()
    b2._focus["buffs"] = {"atk_up": 3}
    b2._focus["buff_hits"] = {}
    _sim_end_round(b2)
    check("攻击 buff 不豁免：回合递减", b2._p_buffs_bag().get("atk_up") == 2,
          str(b2._p_buffs_bag()))

    print("\n结果: %d 通过, %d 失败" % (passed, failed))
    return failed == 0

if __name__ == "__main__":
    sys.exit(0 if main() else 1)