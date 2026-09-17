# -*- coding: utf-8 -*-
"""《奥兰迪亚》武器/词条特效族（we_procs）参数表 —— 逐字搬运物（P4-D2）。

真源：游戏仓 `C:/Users/yuyu/qqbot/data/plugins/dragonfall/game/data/weapon_effect_data.py:27`
      → `WEAPON_EFFECT_DATA`（82 条 = 79 + D3 增量 3；本文件用 `python -c` import 真源模块后 dump 成字面量，
      键序/数值/文案**逐字未改**，未经人手誊抄）。
      D3 增量 3 条（divine_execution / dragon_annihilation / star_destruction）为 2026-09-13
      手工加在真源与本文件**尾部同一位置、逐字相同**（对拍见 `overnight/d3_gap_fix_verify.py` A5）。

另：`ACT_TICK` 逐字抄自 `game/core/constants.py:156`
    （`ACT_TICK = 1.0        # 1 刻 = 1.0 时刻 = 1 游戏秒（鱼鱼拍板对齐秒）`；
    真源 `battle_we_procs.py:251/341/517/692/730` 的 `from ..core.constants import ACT_TICK`
    → 本包 `from .we_data import ACT_TICK`。引擎侧 `schedule.py` 同口径：1 刻 = 1 时刻 = 1 游戏秒。）

接线状态（诚实标注，勿静默）：本批 27 个动作**没有**任何一处直接 import `WEAPON_EFFECT_DATA`
（真源 `battle_we_procs.py` 同样不 import 它——动作全部参数化，数值由装配层
`battle_equip_proc` 从数据表翻译后写进 params）。本表按 P4-D2 要求先逐字入库，供装配层接线。


────────────────────────────────────────────────────────────────────────────
D2（数据进表）迁移说明 —— 本文件的「数据 / 文案」两面已分离
────────────────────────────────────────────────────────────────────────────
* **数据真源** = `content/data/weapon_effects.json`（域 id `weapon_effects`，登记在
  `editor/domains.json`；落点由声明的 `kind=data` 派生）。表里只剩数值/结构/键名。
* **文案真源** = `content/data/text_specs.json`（域内显示文案字段存 `<字段>_key`，条目的
  模板串**只在文案表里**）—— 玩家可见文案不再有第二份真源。
* **本模块 = 唯一读口**：import 期由「域 + 文案表」拼出 `WEAPON_EFFECT_DATA`，键序 / 值 /
  类型与搬前逐名相等（对拍 `out/raw/00_before.json` ↔ `01_after.json`，diff 为空）。
* fail-closed：域未声明 / 文件缺 / 落点与声明不符 / 键序不符 / 文案 key 缺 → **当场报错点名**，
  绝不静默给空表（读口 = 引擎 `records` 声明驱动口 + `content/texts.py` 渲染表）。
* 例外 2 条（`death_dance.log` / `firmament_crown.log`）：模板含嵌套 `{}`，`str.format`
  语法非法 ⇒ `TextTable.validate()` 判非法 ⇒ 不能作为文案表条目，暂留数据域原样；
  见 `out/LANDING.md`「未做与不确定」。
"""


from __future__ import annotations

import os

_HERE = os.path.dirname(os.path.abspath(__file__))              # <pkg>/content/mech
_PKG_ROOT = os.path.dirname(os.path.dirname(_HERE))             # <pkg>

#: 本表数据域（域元数据唯一源 = `editor/domains.json`；落点由 kind 派生）
_DOMAIN = "weapon_effects"

#: 真源插入序（域文件按键升序落盘 ⇒ 序必须显式声明；与域键集不符 = 报错，不静默改序）
_ORDER = (
    "starlight_bulwark",
    "gale_step",
    "swift_boots",
    "deadman_stride",
    "temple_stride",
    "void_stride",
    "abyss_barrier",
    "eclipse_crown",
    "arcane_firmament",
    "undying_will",
    "wind_mark",
    "hunter_open",
    "smith_blaze_wound",
    "rong_lu_yu_wen",
    "frost_ring",
    "blood_trace",
    "wind_split",
    "holy_judgment_field",
    "thunder_weave",
    "phantom_barrage",
    "siren_fang",
    "soul_eater",
    "star_pierce",
    "combo_end",
    "novice_lifesteal",
    "novice_hunt_combo",
    "novice_wind_spd",
    "afterglow_splash",
    "spellblade_echo",
    "annihilation_echo",
    "ember_burn",
    "everfrost_domain",
    "everfrost_scepter",
    "trinity_rhythm",
    "mountain_break",
    "oath_blade",
    "endless_radiance",
    "endless_blade",
    "rune_amp",
    "sage_amp",
    "eternal_codex",
    "sentinel_aegis",
    "iron_echo",
    "frost_crown",
    "thorn_armor",
    "guardian_will",
    "deeprock_aegis",
    "gargoyle_retort",
    "titan_retort",
    "ranger_retort",
    "dragon_spine_mail",
    "retribution_ring",
    "ember_bulwark",
    "vital_band",
    "holy_radiance_mail",
    "echo_band",
    "echo_bless",
    "atonement_shield",
    "holy_word_bind",
    "novice_regen_heal",
    "guard_regen",
    "dawn_regen",
    "undying_band",
    "death_dance",
    "time_staff",
    "randuin_weary",
    "ice_vein",
    "time_freeze",
    "bedrock_crown",
    "firmament_crown",
    "gargoyle_heart",
    "dusk_blade",
    "twilight_execute",
    "star_slayer_edge",
    "death_dance_armor",
    "novice_first_turn_guard",
    "novice_spark_followup",
    "novice_first_turn_dodge",
    "novice_dawn_mana",
    "divine_execution",
    "dragon_annihilation",
    "star_destruction",
)

#: 显示文案字段：域内存 `<字段>_key`，装载期从文案表回填模板串
_TEXT_FIELDS = ("log", "source", "tag")

#: 本表消费的文案 key（`content/data/text_specs.json`）——装载期与域内 `<字段>_key`
#: **双向对账**：域里多/少一个 key 都报错（不静默漏文案、不静默多挂）。
_TEXT_KEYS = (
    "we.starlight_bulwark.log",
    "we.gale_step.log",
    "we.swift_boots.log",
    "we.deadman_stride.log",
    "we.temple_stride.log",
    "we.void_stride.log",
    "we.abyss_barrier.log",
    "we.eclipse_crown.log",
    "we.arcane_firmament.log",
    "we.undying_will.log",
    "we.wind_mark.log",
    "we.frost_ring.source",
    "we.blood_trace.log",
    "we.holy_judgment_field.log",
    "we.holy_judgment_field.source",
    "we.thunder_weave.log",
    "we.phantom_barrage.log",
    "we.soul_eater.log",
    "we.novice_hunt_combo.log",
    "we.novice_wind_spd.log",
    "we.everfrost_domain.source",
    "we.everfrost_scepter.source",
    "we.endless_radiance.log",
    "we.rune_amp.log",
    "we.eternal_codex.log",
    "we.sentinel_aegis.log",
    "we.frost_crown.source",
    "we.thorn_armor.log",
    "we.guardian_will.log",
    "we.deeprock_aegis.log",
    "we.dragon_spine_mail.log",
    "we.retribution_ring.log",
    "we.ember_bulwark.log",
    "we.echo_bless.log",
    "we.atonement_shield.log",
    "we.holy_word_bind.source",
    "we.time_staff.log",
    "we.randuin_weary.log",
    "we.ice_vein.log",
    "we.time_freeze.log",
    "we.time_freeze.source",
    "we.bedrock_crown.log",
    "we.gargoyle_heart.log",
    "we.dusk_blade.log",
    "we.novice_first_turn_guard.log",
    "we.novice_spark_followup.log",
    "we.novice_first_turn_dodge.log",
    "we.novice_dawn_mana.log",
    "we.divine_execution.tag",
    "we.dragon_annihilation.tag",
    "we.star_destruction.tag",
)

# 1 刻 = 1.0 时刻 = 1 游戏秒（真源 game/core/constants.py:156，逐字）
ACT_TICK = 1.0


def _text_templates() -> dict:
    """文案 key → 模板串（真源 = 包内 `content/data/text_specs.json`）。

    缺 key **不静默**：`TextTable.render` 的缺 key 兜底是「把 key 本身返回给玩家」——
    那对 `WEAPON_EFFECT_DATA` 就是**静默错值**，所以这里先点名报错。
    """
    from ..texts import table as _text_table
    tb = _text_table()
    miss = [k for k in _TEXT_KEYS if k not in tb]
    if miss:
        raise RuntimeError(
            "武器特效文案缺 %d 个 key（content/data/text_specs.json）：%s"
            % (len(miss), miss[:5]))
    return {k: tb.get(k) for k in _TEXT_KEYS}


def _load_weapon_effects() -> dict:
    """域 + 文案表 → `WEAPON_EFFECT_DATA`（保真：键序/值/类型与搬前逐名相等）。"""
    from saintess_engine.records import records_from_domain
    rec = records_from_domain(_PKG_ROOT, _DOMAIN, order=_ORDER)
    raw = rec.all()                       # load()：缺声明/缺文件/键序不符 → 当场报错
    if rec.missing:
        raise RuntimeError("武器特效域读不到：%s（%r）" % (_DOMAIN, rec.problems[:3]))
    tpl = _text_templates()
    used: set = set()
    out: dict = {}
    for key, entry in raw.items():
        if not isinstance(entry, dict):
            raise RuntimeError("武器特效域条目 %r 不是映射（键型不符）" % (key,))
        item: dict = {}
        for field, value in entry.items():
            if field.endswith("_key") and field[:-4] in _TEXT_FIELDS:
                base = field[:-4]
                if not isinstance(value, str) or value not in tpl:
                    raise RuntimeError(
                        "武器特效域 %r.%s 的文案 key 无效：%r" % (key, field, value))
                used.add(value)
                item[base] = tpl[value]
            else:
                item[field] = value
        out[key] = item
    drift = sorted(used ^ set(_TEXT_KEYS))
    if drift:
        raise RuntimeError(
            "文案 key 清单与域不一致（双向对账，多/少都报）：%r" % (drift[:5],))
    return out


WEAPON_EFFECT_DATA = _load_weapon_effects()
