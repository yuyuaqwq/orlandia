# -*- coding: utf-8 -*-
"""C-R2.29B gate -- mana_cost_down wiring = cost-discount family (shape #4).

The first three families (C-R2.27 panel-snapshot / C-R2.28 expire-extend /
C-R2.29A multiplier-trigger) all land state on the actor. This family lands
NEITHER: it writes the engine ALREADY-EXISTING discount container
actor["bonus"]["cost"]["mp_pct"], which actions._skill_pay_of really reads.

Why expiry needs no engine change (this overturns ledger 0.40):
  engine EVENTS already contains effect_expire, and
  schedule._settle_time_effects fires it WITH the expiring entry key.
  => clear mp_pct on that event. Content-side only, engine untouched.
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
_MCD = _D["mana_cost_down"]
TTL_KEY = IU._COST_DISCOUNT_TTL_KEY


class _B:
    def __init__(self):
        self.triggers = {}
        self.sides = {"A": [], "B": []}
        self._fire_ctx = None
        self._now = 1000.0


def _fresh_actor():
    return {"name": "t", "hp": 100, "max_hp": 100, "mp": 100, "max_mp": 100,
            "effects": {}, "triggers": {},
            "bonus": {"panel": {}, "cap": {}, "cost": {}}}


def _act(value=None, actor=None):
    b = _B()
    a = actor if actor is not None else _fresh_actor()
    logs = []
    r = IU._translate_special(b, a, "mana_cost_down",
                              value if value is not None else dict(_MCD),
                              logs, 0.0, 0.0)
    b._now = 1000.0
    return b, a, logs, r


def _mp_pct(a):
    return float(((a.get("bonus") or {}).get("cost") or {}).get("mp_pct") or 0.0)

# ---------- 1 positive ----------
b, a, logs, r = _act()
check("1.1 translate really returns (not None)", r is not None, r)
check("1.2 bonus.cost.mp_pct got a value", _mp_pct(a) > 0, _mp_pct(a))
check("1.3 value verbatim from domain potion_effects.mana_cost_down.pct",
      abs(_mp_pct(a) - float(_MCD["pct"])) < 1e-9, (_mp_pct(a), _MCD["pct"]))
check("1.4 player-visible receipt rendered (via text table)", bool(logs), logs)

# ---------- 2 gating ----------
check("2.1 can_translate(special:mana_cost_down) passes",
      IU.can_translate("special:mana_cost_down;cast:1.0") is True)
check("2.2 unregistered mech special still blocked (gate has teeth)",
      IU.can_translate("special:phoenix:{};cast:1.0") is False)

# ---------- 3 read point ----------
_src = io.open(os.path.join(ENG, "extends/ext_combat/battle/actions.py"), encoding="utf-8").read()
check("3.1 engine actions.py really reads bonus.cost / mp_pct",
      ("mp_pct" in _src) and ("bonus" in _src))

# ---------- 4 expiry ----------
ttl = (a.get("effects") or {}).get(TTL_KEY + "_mana_cost")
check("4.1 TTL entry landed (window source of truth)", bool(ttl), list((a.get("effects") or {})))
check("4.2 TTL entry carries no stat (pure state, not a panel row)",
      bool(ttl) and "stat" not in (ttl or {}), ttl)
_before = _mp_pct(a)
b2, a2, logs2, r2 = _act(actor=a)
check("4.3 idempotent while window live: mp_pct NOT doubled",
      abs(_mp_pct(a2) - _before) < 1e-9, (_before, _mp_pct(a2)))
check("4.4 idempotent path emits extend receipt", bool(logs2), logs2)

# ---------- 5 counter-evidence ----------
r0 = IU._translate_special(_B(), _fresh_actor(), "mana_cost_down",
                           {"pct": 0.0, "turns": 3}, [], 0.0, 0.0)
check("5.1 pct=0 => None (fail-closed, no always-on dead discount)", r0 is None, r0)

from ext_combat.battle import actions as _ACT                  # noqa: E402
info100 = {"name": "s", "mp": 100, "res_cost": {}}


def _pay(actor, info=info100):
    return _ACT._skill_pay_of(actor, info)["mp"]


_aclean = _fresh_actor()
check("5.2 no discount => pay == declared cost (baseline)", _pay(_aclean) == 100, _pay(_aclean))
_a25 = {"name": "d", "bonus": {"panel": {}, "cap": {}, "cost": {"mp_pct": 0.25}}}
check("5.3 REAL engine fold: declared 100 / 25% => pay 75", _pay(_a25) == 75, _pay(_a25))
_a10 = {"name": "d", "bonus": {"panel": {}, "cap": {}, "cost": {"mp_pct": 0.10}}}
check("5.4 REAL engine fold: 10% => pay 90 (value source = passed)", _pay(_a10) == 90, _pay(_a10))

from ext_combat.battle.effects import ACTION_HANDLERS, missing_actions   # noqa: E402
import content.mech.we_procs as _WE        # noqa: F401  trigger registration
_H = ACTION_HANDLERS.get("we_cost_discount_expire")
check("5.5 we_cost_discount_expire registered in ACTION_HANDLERS", _H is not None)
check("5.6 missing_actions does not report our action name",
      not missing_actions(["we_cost_discount_expire"]), missing_actions(["we_cost_discount_expire"]))
check("5.7 counter-evidence: unregistered name IS reported",
      missing_actions(["we_definitely_not_registered_xyz"]) != [])

if _H is not None:
    b3, a3, _l3, _ = _act()
    IU.install_cost_discount_expire(a3)
    rows = (a3.get("triggers") or {}).get("effect_expire") or []
    # ★ C-R2.30：本钩子现按**族**各挂一行（第 5 族 mana_restore 加入同一容器）
    #   ⇒ 精确等值锚点 1 -> 2（未放宽：仍不许 >2，也不改成 'any'）。
    _keys = [r.get("key") for r in rows]
    check("5.8 install mounted one effect_expire row per cost family",
          len(rows) == 2, rows)
    check("5.8b this family's row is among them",
          (TTL_KEY + "_mana_cost") in _keys, _keys)
    b3._fire_ctx = {"actor": a3, "target": a3, "key": TTL_KEY + "_mana_cost"}
    _out = []
    _H(b3, a3, a3, dict(rows[0]) if rows else {}, _out)
    check("5.9 REAL expire hook: window ends => mp_pct back to 0", _mp_pct(a3) == 0.0, _mp_pct(a3))
    b4, a4, _l4, _ = _act()
    b4._fire_ctx = {"actor": a4, "target": a4, "key": "some_other_effect"}
    _H(b4, a4, a4, {}, [])
    check("5.10 other key expiring => mp_pct UNTOUCHED (no over-clear)", _mp_pct(a4) > 0, _mp_pct(a4))

# ---------- 6 dual-table sync ----------
_t1 = json.load(io.open(os.path.join(PKG, "content/data/texts.json"), encoding="utf-8"))
_t2 = json.load(io.open(os.path.join(PKG, "content/data/text_specs.json"), encoding="utf-8"))
for _k in ("iu.cost_window", "iu.cost_expired"):
    check("6.1 texts.json has %s" % _k, _k in _t1)
    check("6.2 text_specs.json has %s" % _k, _k in _t2)
    check("6.3 both tables %s identical" % _k,
          _t1[_k]["value"] == _t2[_k]["value"] and _t1[_k]["params"] == _t2[_k]["params"], _k)
_k1 = [k for k in _t1 if k.startswith("iu.")]
check("6.4 iu.* outer key order still ascending", _k1 == sorted(_k1), _k1)

print("")
if FAILS:
    print("FAILED %d: %s" % (len(FAILS), " / ".join(FAILS)))
    sys.exit(1)
print("all green.")
print("  => mana-cost potion folded by the real engine point (100->75 / 100->90).")
print("  => cleared on expiry via effect_expire (really run); engine UNTOUCHED.")
