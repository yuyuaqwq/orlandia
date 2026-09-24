#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""机制序列表**行为冻结**门禁（P2 试点 5 个动作 · 2026-09-24）。

对象：`we_death_pool_add` / `we_death_pool_pay`（武器域）· `mech_cash_dmg_mult` /
`passive_bar_extend` / `passive_low_hp_core`（职业域）—— 它们的实现载体已从 Python 函数体
换成声明表（`content/rules/mech_seq_*.json` + `content/mech/seq_verbs_*.py`，形状在引擎
`saintess_engine.acts`）。

判据三条（都能证伪）：

  ① **行为段逐字节相同**：60 条 case 的规范 JSON 与基线 `tests/_mech_seq_frozen.json` 逐字节一致。
     「换实现不换行为」是这批唯一的验收判据 —— **不许**改判据迁就实现。
  ② **源码指纹自洽**：3 个职业域动作体的 `inspect.getsource` sha256 == 仓内冻结门禁
     `test_u1d2_triggers_extra_frozen.py` 的 `_PIN["aux"]`（同一把尺，两处不许漂）。
  ③ **基线指纹已登记**：5 个动作体的指纹 == 基线 `source` 段 —— 若实现真的再改，必须
     `python tests/_mech_seq_frozen.py --emit` 重采 + 在提交消息里说明（行为段仍须逐字节相同）。

反证（本文件内做，不依赖改实现）：把基线里某条 case 的输出改一个字符 ⇒ ① 的逐字节比较必须变红；
若仍判「相同」，说明比较没牙。

跑法：python tests/test_mech_seq_frozen.py
退出码：0 = 全绿；1 = 有失败。
"""
import importlib.util
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from _check import bind_check  # noqa: E402

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")

_HERE = HERE
_MOD_PATH = os.path.join(_HERE, "_mech_seq_frozen.py")


def _load_checker():
    spec = importlib.util.spec_from_file_location("_mech_seq_frozen", _MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_mech_seq_frozen"] = mod
    spec.loader.exec_module(mod)          # 模块带 __main__ 守卫 ⇒ import 不跑 CLI
    return mod


def main():
    print("== 机制序列表行为冻结门禁（P2 试点 5 动作）==")
    mod = _load_checker()

    base_path = mod.BASELINE_PATH
    check("基线文件存在", os.path.isfile(base_path), base_path)
    if not os.path.isfile(base_path):
        return 1
    base = json.load(io.open(base_path, encoding="utf-8"))

    rep = mod.build_report()
    check("case 条数一致（基线 vs 现跑）",
          len(rep["cases"]) == len(base["cases"]) == 60,
          (len(rep["cases"]), len(base["cases"])))

    # ① 行为段逐字节
    same = mod._cases_bytes(rep) == mod._cases_bytes(base)
    check("★ 行为段逐字节相同（换实现不换行为）", same,
          "现跑与基线不一致 —— 先按点名 case 定位实现，**不许改基线/判据**")
    if not same:
        try:
            diffs = [rep["cases"][i].get("id", i) for i, (a, b) in
                     enumerate(zip(rep["cases"], base["cases"])) if mod.canon(a) != mod.canon(b)]
            check("行为段差异的 case（辅助定位）", True, diffs[:8])
        except Exception as exc:                                # noqa: BLE001
            check("行为段差异定位（辅助）", True, repr(exc)[:80])

    # ② 源码指纹自洽（与仓内冻结门禁同一把尺）
    rpm = rep["source"]["repo_pins_match"]
    check("源码指纹与仓内 _PIN 自洽（3 个职业域动作体）",
          all(rpm.values()), [k for k, ok in rpm.items() if not ok])

    # ③ 基线指纹已登记
    fps_now = rep["source"]["fingerprints_sha256"]
    fps_pin = base["source"]["fingerprints_sha256"]
    drifted = [k for k in sorted(fps_now) if fps_now[k] != fps_pin.get(k)]
    check("5 个动作体指纹 == 基线登记值", not drifted,
          drifted and "漂了就先 --emit 重采并在提交里说明：%s" % drifted)

    # 反证：比较必须有牙
    mut = json.loads(json.dumps(base))
    case0 = mut["cases"][0]
    out = case0.setdefault("output", {})
    key = sorted(out)[0] if out else "probe"
    out[key] = "MUTATED" if not isinstance(out.get(key), list) else out[key] + ["MUTATED"]
    check("反证：基线改一个字符 ⇒ 逐字节比较必红（有牙）",
          mod._cases_bytes(mut) != mod._cases_bytes(base))

    print("\n" + "=" * 56)
    _f = globals().get("FAILURES") or []
    print("===== 结果：通过 %d / 失败 %d =====" % (globals().get("PASS", 0), len(_f)))
    for x in _f[:6]:
        print("   ❌ " + str(x))
    return 0 if not _f else 1


if __name__ == "__main__":
    sys.exit(main())
