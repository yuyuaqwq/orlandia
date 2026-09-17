# -*- coding: utf-8 -*-
"""《奥兰迪亚·余烬纪年》包内**条件显示文案表**（逐字搬自游戏仓 `game/core/battle_cond_labels.py`，59 行）。

真源 = 技能详情面板「条件转化」行的文案源（44 键）：**纯数据 + lambda**，
故本文件 = 原文件正文逐字（不动一行），只加本头注。宿主 `game/core/battle_cond_labels.py`
现在是薄壳（一行再导出 `COND_LABELS`）。

★ B 批 B-1 B 档（2026-09-17）：**句壳已搬进文案真源** —— `content/data/text_specs.json` 的
`cond_label.*`（44 条）。本文件此后只剩「槽位怎么算」这一层：lambda 按调用方给的配置 `c`
算出槽位值再交给文案表渲染（铁律 2：代码只传槽位）。加条件类型 = 判定加一行 + 文案表加一行
（本表仍要加一行 lambda 映射，槽位算不出时玩家会看到 key 本身，不静默）。
故原「零依赖、零 IO」的说法自本次起不再成立：本模块依赖包内文案读口 `content/texts.py`
（read-only，无 IO 副作用）。

分工（v181 拆分后的单源结构，照原注）：
* 判定在哪 → 游戏仓 `game/services/battle_cond_procs.py::COND_PREDICATES`（宿主）；
* 文案在哪 → `content/data/text_specs.json` 的 `cond_label.*`（本模块只换算槽位；
  消费方：宿主 `game/commands/player.py` 技能详情）。

缺口：无（本模块零宿主耦合）。
"""
# -*- coding: utf-8 -*-
"""条件显示文案表 battle_cond_labels（技能详情面板「条件转化」行的文案源）。

分工（v181 拆分后的单源结构）：
- **判定**在哪 → `game/services/battle_cond_procs.py` 的 `COND_PREDICATES`
  （在战走装配层 `skill_cond_mult` 乘区钩子，挂 dmg_calc / heal_calc；引擎零改动）
- **文案**在哪 → 文案真源 `cond_label.*`（本模块只保留「c → 槽位值」的换算）

历史：本表原与判定函数同处 `core/battle_conds.py`（v98.4 注册表）。v181 期间
判定侧整体迁往 battle_cond_procs（旧 `COND_CHECKS` 在 saintess_engine 零消费方、
且谓词读的是已删除的旧引擎 API），判定函数随之删除；**文案是本表唯一还活着的部分**，
故拆成独立模块。B 批 B-1 B 档再把句壳搬进文案真源，本模块退化为槽位换算表。
"""
from . import texts as _T                       # 文案表（B 批 B-1 B 档：条件文案）
COND_LABELS = {
    "enemy_hp_low": lambda c: _T.text("cond_label.enemy_hp_low", pct=int(c.get('hp_pct', 0.4) * 100)),
    "player_hp_low": lambda c: _T.text("cond_label.player_hp_low", pct=int(c.get('hp_pct', 0.3) * 100)),
    "enemy_hp_high": lambda c: _T.text("cond_label.enemy_hp_high", pct=int(c.get('hp_pct', 0.7) * 100)),
    "player_hp_high": lambda c: _T.text("cond_label.player_hp_high", pct=int(c.get('hp_pct', 0.8) * 100)),
    "enemy_full_hp": lambda c: _T.static("cond_label.enemy_full_hp"),
    "enemy_frozen": lambda c: _T.static("cond_label.enemy_frozen"),
    "enemy_stunned": lambda c: _T.static("cond_label.enemy_stunned"),
    "enemy_silenced": lambda c: _T.static("cond_label.enemy_silenced"),
    "enemy_poison_stacks": lambda c: _T.text("cond_label.enemy_poison_stacks", n=c.get('stacks', 0)),
    "enemy_shaken_gt": lambda c: _T.static("cond_label.enemy_shaken_gt"),
    "player_rage_form": lambda c: _T.static("cond_label.player_rage_form"),
    "player_stance": lambda c: _T.static("cond_label.player_stance"),
    "player_combo_stacks": lambda c: _T.text("cond_label.player_combo_stacks", n=c.get('stacks', 3)),
    "enemy_marked": lambda c: _T.static("cond_label.enemy_marked"),
    "enemy_debuff": lambda c: _T.static("cond_label.enemy_debuff"),
    "enemy_slowed": lambda c: _T.static("cond_label.enemy_slowed"),
    "enemy_mark_full": lambda c: _T.text("cond_label.enemy_mark_full", mech=c.get('mech', ''), n=c.get('stacks', 3)),
    "element_marks": lambda c: _T.text("cond_label.element_marks", element=c.get('element', ''), n=c.get('stacks', 0)),
    "player_shield": lambda c: _T.static("cond_label.player_shield"),
    "player_spd_up": lambda c: _T.static("cond_label.player_spd_up"),
    "player_chi_stacks": lambda c: _T.text("cond_label.player_chi_stacks", n=c.get('stacks', 0)),
    "player_res_stacks": lambda c: _T.text("cond_label.player_res_stacks", res=c.get('res_key', ''), n=c.get('stacks', 0)),
    "player_mech_stacks": lambda c: _T.text("cond_label.player_mech_stacks", mech=c.get('mech', ''), n=c.get('stacks', 0)),
    "player_buffed": lambda c: _T.static("cond_label.player_buffed"),
    "player_untouched": lambda c: _T.static("cond_label.player_untouched"),
    "player_combo": lambda c: _T.text("cond_label.player_combo", last=c.get('last', '连招中')),
    "player_first": lambda c: _T.static("cond_label.player_first"),
    "speed_ratio": lambda c: _T.text("cond_label.speed_ratio", ratio=c.get('ratio', 1.5)),
    "enemy_hunt_mark": lambda c: _T.static("cond_label.enemy_hunt_mark"),
    "enemy_hunt_full": lambda c: _T.text("cond_label.enemy_hunt_full", n=c.get('stacks', 3)),
    "enemy_cursed": lambda c: _T.static("cond_label.enemy_cursed"),
    "faith_full": lambda c: _T.text("cond_label.faith_full", n=c.get('stacks', 10)),
    "faith_lt": lambda c: _T.text("cond_label.faith_lt", n=c.get('stacks', 5)),
    "enemy_broken": lambda c: _T.static("cond_label.enemy_broken"),
    "enemy_shaken_ratio": lambda c: _T.text("cond_label.enemy_shaken_ratio", step=c.get('step', 50)),
    "enemy_shaken_scale": lambda c: _T.static("cond_label.enemy_shaken_scale"),
    "guard_core": lambda c: _T.static("cond_label.guard_core"),
    "enemy_def_high": lambda c: _T.static("cond_label.enemy_def_high"),
    "melody_buff": lambda c: _T.static("cond_label.melody_buff"),
    "melody_stacks": lambda c: _T.text("cond_label.melody_stacks", n=c.get('stacks', 4)),
    "enemy_low_hp": lambda c: _T.text("cond_label.enemy_low_hp", hp=int(c.get('hp_lt', c.get('hp_pct', 40)))),
    "enemy_marks": lambda c: _T.text("cond_label.enemy_marks", n=c.get('stacks', 4)),
    "revenge": lambda c: _T.static("cond_label.revenge"),
    "stealth": lambda c: _T.static("cond_label.stealth"),
}
