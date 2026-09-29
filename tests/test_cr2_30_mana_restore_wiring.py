# -*- coding: utf-8 -*-
"""C-R2.30 gate -- mana_restore wiring = family #5 (mana restore + cost discount).

Two things this gate pins that earlier gates could not:

1. Family #5 does BOTH halves in one use: mp restore (through the engine's
   only write port ATTR.set_current) + cost discount (bonus.cost.mp_pct,
   same container as family #4).
2. ★ THE REAL DEFECT: family #5 is a SECOND mp_pct writer. C-R2.29B's expire
   hook did `_cost["mp_pct"] = 0.0`, whose documented premise was "this family
   is the only writer". That premise died with this unit, so zeroing now wipes
   a still-running discount from the OTHER family. Fixed by a per-family
   ledger (item_use._add_ledger_pct / _pop_ledger_pct), engine untouched.
3. ★ C-R2.29B never wired install_cost_discount_expire into content/apply.py
   (only its own gate called it) => in a real battle the discount never expired.
   This gate asserts the assembly chain calls it, by static read of apply.py.
"""
import io
import json
import os
import sys

PKG = r"C:/Users/yuyu/framework-engine/games/orlandia"
ENG = r"C:/Users/yuyu/framework-engine"

sys.path.insert(0, PKG)
sys.path.insert(0, os.path.join(ENG, "extends"))
sys.path.insert(0, ENG)
os.environ.setdefault("GWEN_TEST_MODE", "1")

FAILS = []


def check(name, ok, extra=""):
    print(("  ok   " if ok else "  FAIL ") + name + (("  | " + str(extra)) if extra else ""))
    if not ok:
        FAILS.append(name)


import content.mech.item_use as IU                          # noqa: E402

_D = json.load(io.open(os.path.join(PKG, "content/data/potion_effects.json"), encoding="utf-8"))
_MR = _D["mana_restore"]
_MCD = _D["mana_cost_down"]
TTL_KEY = IU._COST_DISCOUNT_TTL_KEY
MR_SFX = IU._MANA_RESTORE_KINDS["mana_restore"][3]
MCD_SFX = IU._COST_DISCOUNT_KINDS["mana_cost_down"][2]
MR_TTL = "%s_%s" % (TTL_KEY, MR_SFX)
MCD_TTL = "%s_%s" % (TTL_KEY, MCD_SFX)


def _fresh_actor(mp=20):
    return {"name": "t", "hp": 100, "max_hp": 100, "mp": mp, "max_mp": 100,
            "effects": {}, "triggers": {},
            "bonus": {"panel": {}, "cap": {}, "cost": {}}}


def _B():
    from ext_combat.battle.battle import Battle
    b = Battle()
    b._now = 1000.0
    return b


def _mp(a):
    return int(a.get("mp", 0) or 0)


def _pct(a):
    return float(((a.get("bonus") or {}).get("cost") or {}).get("mp_pct") or 0.0)


def _led(a):
    return dict(((a.get("bonus") or {}).get("cost") or {}).get(IU._COST_LEDGER_KEY) or {})


def _use(kind, value, actor=None, battle=None):
    b = battle if battle is not None else _B()
    a = actor if actor is not None else _fresh_actor()
    logs = []
    r = IU._translate_special(b, a, kind, value, logs, 0.0, 0.0)
    return b, a, logs, r

# ---------- 1 wiring: both halves land ----------
_b, a, logs, r = _use("mana_restore", dict(_MR))
check("1.1 branch returns logs (not None) => item is consumable",
      r is not None and logs, r)
check("1.2 mp restored by mana_pct of max_mp (20 + 25% of 100 = 45)",
      _mp(a) == 45, _mp(a))
check("1.3 cost half: mp_pct == cost_reduce",
      abs(_pct(a) - float(_MR["cost_reduce"])) < 1e-9, _pct(a))
check("1.4 ledger records ONLY this family",
      list(_led(a)) == [MR_SFX], _led(a))
check("1.5 TTL entry mounted under family key",
      MR_TTL in (a.get("effects") or {}), sorted((a.get("effects") or {})))
check("1.6 receipts are rendered text, never a raw key",
      (not any("iu." in str(x) for x in logs)), logs)
print("      receipts:", logs)

# ---------- 2 can_translate agrees with the dispatcher ----------
check("2.1 can_translate('special:mana_restore') True (no dual source)",
      IU.can_translate("special:mana_restore"))
check("2.2 can_translate with json payload True",
      IU.can_translate("special:mana_restore:" + json.dumps(_MR)))
check("2.3 unknown special kind still False (fail-closed)",
      not IU.can_translate("special:no_such_kind_xyz"))

# ---------- 3 mp write port is the engine's, and it clamps ----------
check("3.1 engine really exposes ATTR.set_current for mp",
      "set_current" in io.open(os.path.join(ENG, "extends/ext_combat/battle/attributes.py"),
                               encoding="utf-8").read())
_b2, a2, l2, _ = _use("mana_restore", {"mana_pct": 0.25, "cost_reduce": 0.0}, _fresh_actor(mp=95))
check("3.2 clamp to max_mp (95 + 25 -> 100, never 120)",
      _mp(a2) == 100, _mp(a2))
_b3, a3, l3, _ = _use("mana_restore", {"mana_pct": 0.25, "cost_reduce": 0.0}, _fresh_actor(mp=100))
check("3.3 already full => mp unchanged", _mp(a3) == 100, _mp(a3))
check("3.4 already full => 'already full' receipt, not 'restored 0'",
      any("已满" in str(x) for x in l3) and not any("恢复 0" in str(x) for x in l3), l3)

# ---------- 4 fail-closed ----------
_b4, a4, l4, r4 = _use("mana_restore", {"mana_pct": 0.0, "cost_reduce": 0.0})
check("4.1 both halves zero => None (no dead potion)",
      r4 is None, r4)
check("4.2 ...and nothing was written", _mp(a4) == 20 and _pct(a4) == 0.0,
      (_mp(a4), _pct(a4)))

# ---------- 5 ★ THE REAL DEFECT: one family expiring must not zero the other ----------
from ext_combat.battle.effects import ACTION_HANDLERS, missing_actions   # noqa: E402
import content.mech.we_procs as _WE        # noqa: E402,F401  trigger registration

_H = ACTION_HANDLERS.get("we_cost_discount_expire")
check("5.1 expire action registered", _H is not None)
check("5.2 missing_actions does not report it",
      not missing_actions(["we_cost_discount_expire"]))

# both families live on the same actor, different windows
_b5, a5, l5, _ = _use("mana_cost_down", dict(_MCD), _fresh_actor())
check("5.3 setup: family #4 discount live", _pct(a5) > 0, _pct(a5))
_use("mana_restore", dict(_MR), a5, _b5)
_both = _pct(a5)
check("5.4 setup: two families coexist (ledger has both)",
      sorted(_led(a5)) == sorted([MCD_SFX, MR_SFX]), _led(a5))
check("5.5 setup: total is the sum of both",
      abs(_both - (float(_MCD["pct"]) + float(_MR["cost_reduce"]))) < 1e-9, _both)

# family #4 window expires now
_b5._fire_ctx = {"actor": a5, "target": a5, "key": MCD_TTL}
_H(_b5, a5, a5, {}, [])
check("5.6 ★ after family #4 expires, family #5 SURVIVES",
      abs(_pct(a5) - float(_MR["cost_reduce"])) < 1e-9, _pct(a5))
check("5.7 ...ledger dropped only the expired family",
      list(_led(a5)) == [MR_SFX], _led(a5))

# counter-evidence: the OLD code would have zeroed it
_a_old = {"bonus": {"cost": {"mp_pct": _both}}}
_a_old["bonus"]["cost"]["mp_pct"] = 0.0
check("5.8 counter-evidence: zeroing really would have wiped BOTH (old behaviour)",
      _a_old["bonus"]["cost"]["mp_pct"] == 0.0)

# and the reverse direction
_b6, a6, _l6, _ = _use("mana_restore", dict(_MR), _fresh_actor())
_use("mana_cost_down", dict(_MCD), a6, _b6)
_b6._fire_ctx = {"actor": a6, "target": a6, "key": MR_TTL}
_H(_b6, a6, a6, {}, [])
check("5.9 reverse: family #5 expires => family #4 SURVIVES",
      abs(_pct(a6) - float(_MCD["pct"])) < 1e-9, _pct(a6))
check("5.10 ...ledger dropped only family #5", list(_led(a6)) == [MCD_SFX], _led(a6))

# both expired => exactly zero, ledger empty
_b7, a7, _l7, _ = _use("mana_cost_down", dict(_MCD), _fresh_actor())
_use("mana_restore", dict(_MR), a7, _b7)
for _k in (MCD_TTL, MR_TTL):
    _b7._fire_ctx = {"actor": a7, "target": a7, "key": _k}
    _H(_b7, a7, a7, {}, [])
check("5.11 both expired => mp_pct exactly 0 (no float dust)", _pct(a7) == 0.0, _pct(a7))
check("5.12 ...ledger emptied", not _led(a7), _led(a7))

# an unrelated effect expiring must touch nothing
_b8, a8, _l8, _ = _use("mana_cost_down", dict(_MCD), _fresh_actor())
_b8._fire_ctx = {"actor": a8, "target": a8, "key": "some_other_effect"}
_H(_b8, a8, a8, {}, [])
check("5.13 other key expiring => mp_pct UNTOUCHED", _pct(a8) > 0, _pct(a8))
# unknown suffix of our own prefix must not clear anything
_b9, a9, _l9, _ = _use("mana_cost_down", dict(_MCD), _fresh_actor())
_b9._fire_ctx = {"actor": a9, "target": a9, "key": TTL_KEY + "_not_a_family"}
_H(_b9, a9, a9, {}, [])
check("5.14 unknown family suffix => UNTOUCHED (no over-clear)", _pct(a9) > 0, _pct(a9))

# ---------- 6 ★ C-R2.29B never wired the expire hook into assembly ----------
_apply = io.open(os.path.join(PKG, "content/apply.py"), encoding="utf-8").read()
check("6.1 ★ apply.py now calls install_cost_discount_expire",
      "install_cost_discount_expire" in _apply, "not wired => never expires in prod")
check("6.2 ...as a real _step (runs per assembly, not a comment)",
      '_step("item_use_expire"' in _apply)

# ---------- 7 the premise the pop() relies on: single writer ----------
import re                                                        # noqa: E402
_iu = io.open(os.path.join(PKG, "content/mech/item_use.py"), encoding="utf-8").read()
def _code_only(text):
    NL = chr(10)
    """strip comments + docstrings so the audit reads CODE, not my own prose.

    (First version of this gate matched the explanatory comment that QUOTES
    the old line -- a false red proving the assertion was testing itself.)
    """
    out = []
    for ln in text.split(NL):
        stripped = ln.lstrip()
        if stripped.startswith(chr(34) * 3) or stripped.startswith(chr(39) * 3):
            out.append("")
            continue
        out.append(ln.split("#", 1)[0])
    joined = NL.join(out)
    return joined


_we = io.open(os.path.join(PKG, "content/mech/we_procs.py"), encoding="utf-8").read()
_iu_code = _code_only(_iu)
_writers = re.findall(r'cost\["mp_pct"\]\s*=', _iu_code)
check("7.1 ★ only the two ledger helpers write mp_pct in item_use",
      len(_writers) == 2, _writers)
check("7.2 ...and the hook pops through the helper, not a bare zero",
      '_cost["mp_pct"] = 0.0' not in _iu_code)
_we_code = _code_only(io.open(os.path.join(PKG, "content/mech/we_procs.py"),
                              encoding="utf-8").read())
check("7.3 we_procs no longer assigns mp_pct directly",
      '["mp_pct"] = 0.0' not in _we_code)
check("7.4 hook calls _pop_ledger_pct", "_pop_ledger_pct" in _we)

# ---------- 8 dual-table sync ----------
_t1 = json.load(io.open(os.path.join(PKG, "content/data/texts.json"), encoding="utf-8"))
_t2 = json.load(io.open(os.path.join(PKG, "content/data/text_specs.json"), encoding="utf-8"))
for _k in ("iu.mana_full", "iu.mana_restore_cost"):
    check("8.1 texts.json has %s" % _k, _k in _t1)
    check("8.2 text_specs.json has %s" % _k, _k in _t2)
    check("8.3 both tables %s identical" % _k,
          _t1[_k]["value"] == _t2[_k]["value"] and _t1[_k]["params"] == _t2[_k]["params"], _k)
_k1 = [k for k in _t1 if k.startswith("iu.")]
check("8.4 iu.* outer key order ascending", _k1 == sorted(_k1), _k1)
check("8.5 counts 3283 / 3285", (len(_t1), len(_t2)) == (3283, 3285), (len(_t1), len(_t2)))

# ---------- 9 idempotence while window live ----------
_b9, a9b, l9b, _ = _use("mana_restore", dict(_MR), _fresh_actor())
_p9 = _pct(a9b)
_use("mana_restore", dict(_MR), a9b, _b9)
check("9.1 re-use while window live => discount NOT doubled",
      abs(_pct(a9b) - _p9) < 1e-9, (_p9, _pct(a9b)))
check("9.2 ...ledger not doubled either", list(_led(a9b)) == [MR_SFX], _led(a9b))

print("")
if FAILS:
    print("FAILED %d: %s" % (len(FAILS), " / ".join(FAILS)))
    sys.exit(1)
print("all green.")
print("  => mana_restore does BOTH halves: real mp write (engine port) + cost discount.")
print("  => ★ one family expiring no longer wipes the other (per-family ledger).")
print("  => ★ C-R2.29B's unwired expire hook is now on the assembly chain.")
