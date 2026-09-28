# -*- coding: utf-8 -*-
"""尺（先加尺后修）：表达式技能预览的等级代入是否真进到表达式里。

★ 这条尺是 R2.2 之后**独立挖出的另一处玩家可见错值**（不是 R2.2 的同源问题）：
  包侧 `player_cmds._skill_detail_message` 把玩家等级塞进 `_player_lv`，
  而引擎 `formulas.py:448/579` 取的是 `stats["level"]`（build_vars(player_lv=…)）
  ⇒ 引擎从没读到过那个键，表达式里的 `player_lv` 恒按 0 算。

**刻意不进全量门禁**（文件名 `_probe_*`，跑器只枚举 `test_*.py`）：
  修好之后 2.1 会转绿；进闸时机由下一批决定。名字沿用 R2.2 那把尺的约定。

判据（两侧同时钉住 ⇒ 不可能恒绿）：
  ① 正证：等级越高，预览值越高，且**逐级递增**
  ② 反证：把等级抹成同一个值 ⇒ 预览值**逐档相同**（证明确实在读等级，
     而不是碰巧算出一个常数）
  ③ 键名守卫：`player_final_stats` 的返回里**不得**再出现 `_player_lv`
     （那是已被引擎淘汰的旧名；留着的唯一后果就是没人读）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import Main  # noqa: E402,F401  装好包内依赖（content.* 全链）
from _check import bind_check  # noqa: E402

from ext_combat.battle.formulas import skill_expr_preview  # noqa: E402
from content.panel import player_final_stats  # noqa: E402
from content.player_cmds import _expr_preview_stats, _is_expr_skill  # noqa: E402

passed = failed = 0
check = bind_check(globals(), "passed", "failed")

F = "atk*1.5 + 12 + player_lv*4.5 + skill_lv*12.0"
INFO = {"exprs": [F], "kind": "物理", "name": "尺用斩", "lv": 1}

# ★ 隔离变量用的公式：**只含 player_lv / skill_lv，不含任何随等级自动涨的属性**
#   （atk/matk/max_hp 本身随等级增长 ⇒ 用上面那条公式时，等级涨 → 预览值照样涨，
#    于是「等级驱动预览」在坏代码上也是绿的 —— 这正是本尺第一版的漏判，
#    由反证（把键名改回 _player_lv 后 ① 仍绿）当场照出来。）
#   隔离后：坏代码下取值恒定（player_lv 恒 0），好代码下逐级递增。
F_ONLY_LV = "player_lv*4.5 + skill_lv*12.0"
INFO_ONLY_LV = {"exprs": [F_ONLY_LV], "kind": "物理", "name": "尺用斩2", "lv": 1}


def _preview(lv, info=None):
    return skill_expr_preview(info or INFO, 1, _expr_preview_stats(
        {"class_name": "战士", "level": lv, "equipment": {}}))


def test_positive_levels_drive_value():
    """① 正证：等级 → 预览值，逐级递增且严格由等级驱动。"""
    vals = [_preview(lv) for lv in (1, 30, 60)]
    print("【1. 等级驱动预览值】", vals)
    check("三级取值非零", all(v > 0 for v in vals), str(vals))
    check("等级越高预览越高", vals[0] < vals[1] < vals[2], str(vals))
    # 系数 4.5 × 等级差：Lv1→Lv30 至少涨 100（Lv30-1=29 × 4.5 = 130.5）
    check("Lv1→Lv30 涨幅 ≥ 100（等级确实进去了）", (vals[1] - vals[0]) >= 100.0,
          f"实际涨 {vals[1] - vals[0]:.1f}")
    check("Lv30→Lv60 涨幅 ≥ 100", (vals[2] - vals[1]) >= 100.0,
          f"实际涨 {vals[2] - vals[1]:.1f}")


def test_isolated_player_lv_only():
    """①b 隔离判据：只留 player_lv/skill_lv 的公式 —— 坏代码下取值恒定，好代码下递增。

    ★ 这条是本尺的**承重判据**：上面 ① 用的公式含 atk，而 atk 本身随等级涨，
      于是在「等级根本没进表达式」的坏代码上 ① 也会绿 ⇒ 恒绿档。
      这条把等级之外的变量全部隔离掉，才照得出真因。
    """
    vals = [_preview(lv, INFO_ONLY_LV) for lv in (1, 30, 60)]
    print("【1b. 隔离判据（只有 player_lv/skill_lv）】", vals)
    check("隔离口径下三级取值互不相同", len(set(vals)) == 3, str(vals))
    check("隔离口径下逐级递增", vals[0] < vals[1] < vals[2], str(vals))
    # player_lv*4.5：Lv1→Lv30 应涨 29*4.5 = 130.5（坏代码下这里恰好是 0）
    check("Lv1→Lv60 涨幅 ≥ 200（坏代码下为 0）", (vals[2] - vals[0]) >= 200.0,
          f"实际涨 {vals[2] - vals[0]:.1f}")


def test_control_same_level_same_value():
    """② 反证：同等级必同值（恒绿探针的铁证档）。"""
    a, b = _preview(30), _preview(30)
    print("【2. 同级反证】", a, b)
    check("同等级逐字相同", a == b, f"{a} vs {b}")


def test_no_legacy_key():
    """③ 键名守卫：旧名 `_player_lv` 不得再出现在属性快照里。"""
    st = player_final_stats("战士", 30, {}, 0, None, 0, None, None, None)
    print("【3. 键名守卫】level in st =", "level" in st,
          "| _player_lv in st =", "_player_lv" in st)
    check("属性快照不含旧名 _player_lv", "_player_lv" not in st, str(sorted(st)))
    snap = _expr_preview_stats({"class_name": "战士", "level": 30, "equipment": {}})
    check("预览快照带的是 level", snap.get("level") == 30, str(snap.get("level")))
    check("预览快照无旧名", "_player_lv" not in snap, str(sorted(snap)))
    check("_is_expr_skill 认得表达式技能", _is_expr_skill(INFO) is True)
    check("_is_expr_skill 认得非表达式技能", _is_expr_skill({"power": 1.5}) is False)


if __name__ == "__main__":
    test_positive_levels_drive_value()
    test_isolated_player_lv_only()
    test_control_same_level_same_value()
    test_no_legacy_key()
    print(f"\n通过 {passed} / 失败 {failed}")
    sys.exit(0 if failed == 0 else 1)
