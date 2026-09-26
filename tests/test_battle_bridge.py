# -*- coding: utf-8 -*-
"""N5b 数据桥测试：真实怪物数据 → saintess_engine actor → 完整战斗闭环。

验证 game/services/battle_bridge.py：
1. monster_to_actor：lv→level、字段透传、auto_act
2. player_to_actor：玩家面板字段透传
3. build_sides：组 sides
4. 端到端：真实 build_monster_group 产物 + 假玩家 → saintess_engine.Battle → 攻击/胜利

跑法（w1 内）：python tests/test_battle_bridge.py
"""
import ast
import os
import sys
import tempfile

# 独立临时 GWEN_GAME_DB（HANDOFF 约定：测试独立临时库）
# ★ 2026-09-19 卫生修复（本文件原先**从不清理**该临时目录 ⇒ 实测累积 824 目录 / 92MB；
#   审计线一度误登记为「文案批 B-2 的产物 gwen_b2bridge_*」，实为本文件的 mkdtemp 泄漏）。
#   双保险，缺一不可：
#   ① **跑前**清掉超过 1 小时的**历史遗留** —— Windows 上 sqlite 连接在解释器退出时往往还持有
#      文件锁 ⇒ `rmtree` 静默失败（实测确认：单靠 atexit 堵不住）；1 小时阈值避免误删并发兄弟进程。
#   ② **atexit** 尽力清自己那个（锁解开时能删成功）。
#   实测（2026-09-19）：跑前清理把 4 个历史目录清成 0；本次那个因 sqlite 文件锁残留 1 个
#   ⇒ **稳态 ≤1 个**（原先是「每跑一次涨一个」，累积到 824）✓
import atexit as _atexit            # noqa: E402
import glob as _glob                # noqa: E402
import shutil as _shutil            # noqa: E402
import time as _time                # noqa: E402

for _d in _glob.glob(os.path.join(tempfile.gettempdir(), "gwen_b2bridge_*")):
    try:
        if _time.time() - os.path.getmtime(_d) > 3600:
            _shutil.rmtree(_d, ignore_errors=True)
    except OSError:
        pass

_tmp_db = tempfile.mkdtemp(prefix="gwen_b2bridge_")
os.environ["GWEN_GAME_DB"] = os.path.join(_tmp_db, "game.db")
_atexit.register(_shutil.rmtree, _tmp_db, ignore_errors=True)
os.environ["GWEN_TEST_MODE"] = "1"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）

# 挂载 saintess_engine 游戏规则（HANDOFF 测试铁律）——测试侧引擎通道驱动口（幂等）
from _engine_harness import boot as _eng_cfg; _eng_cfg()

from _engine_harness import db
db.init_db()
from ext_combat import Battle as B2Battle
from ext_combat.battle import actors as B2A
from content import bridge as BR

PASS = 0
FAIL = 0

from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL")

def section(name):
    print("\n== %s ==" % name)

def make_player(cls="战士", level=10, hp=100, mp=30, equip=None):
    return {
        "qq_id": 10001, "group_id": "g1", "name": "测试勇者", "class_name": cls,
        "level": level, "hp": hp, "mp": mp, "max_hp": 200, "max_mp": 60,
        "equipment": equip or {},
        "class_tier": 1, "attributes": {"力量": 10, "体质": 5},
        "evolve_path": 0, "race": "人族",
        "learned_skills": ["猛击", "治愈术"],
        "cur_map": "test_map",
    }

section("monster_to_actor 字段翻译")
mon = {
    "id": "test_slime", "uid": "e_test_slime-5", "name": "史莱姆", "lv": 5,
    "role": "dps", "rank": 1, "reach": 1, "buffs": {}, "stacks": {},
    "defending": False, "charging": None,
    "hp": 80, "max_hp": 80, "atk": 12, "def": 5, "matk": 0, "mdef": 3, "spd": 6,
    "exp": 20, "gold": 15, "skills": [], "drops": [], "map": "测试平原",
    "map_area": "field", "is_boss": False, "is_elite": False,
    "mech": "", "mod": "", "ai": None,
}
a = BR.monster_to_actor(mon)
check("lv→level 翻译", a.get("level") == 5, a.get("level"))
check("hp/max_hp 直读", a.get("hp") == 80 and a.get("max_hp") == 80)
check("side=enemy", a.get("side") == "enemy")
check("uid/name 保留", a.get("uid") == "e_test_slime-5" and a.get("name") == "史莱姆")
check("rank/reach/role 透传", a.get("rank") == 1 and a.get("reach") == 1 and a.get("role") == "dps")
check("exp/gold/drops 透传", a.get("exp") == 20 and a.get("gold") == 15)
check("is_boss/is_elite 透传", a.get("is_boss") is False and a.get("is_elite") is False)
check("atk/def/spd 字段", a.get("atk") == 12 and a.get("def") == 5 and a.get("spd") == 6)
check("effects 播种（V 系列，buffs 不透传）", a.get("effects") == {} and "buffs" not in a)
check("kind=monster（无 class_name）", a.get("kind") == "monster")
check("make_actor 播种 ct", "ct" in a and a.get("ct") == 0.0)
check("make_actor 播种 effects", isinstance(a.get("effects"), dict))
check("make_actor 播种 shields/cooldown", isinstance(a.get("shields"), dict) and isinstance(a.get("cooldown"), dict))
check("auto_act 缺省 attack", (a.get("auto_act") or {}).get("act", {}).get("type") == "attack")

section("monster_to_actor 怪扮职业")
mon2 = dict(mon, lv=8, class_name="cls_mu_shi", equipment={"weapon": "x"},
            learned_skills=["治疗术"], ai={"skill_chance": 0.5})
a2 = BR.monster_to_actor(mon2)
check("class_name 透传", a2.get("class_name") == "cls_mu_shi")
check("equipment 透传", a2.get("equipment") == {"weapon": "x"})
check("learned_skills 透传", a2.get("learned_skills") == ["治疗术"])
check("kind 随 class_name→player", a2.get("kind") == "player")
check("lv→level 翻译", a2.get("level") == 8)
check("带 ai 不强制 auto_act", a2.get("auto_act") is None)

section("player_to_actor 字段翻译")
p = make_player()
pa = BR.player_to_actor(p)
check("uid=p_qq", pa.get("uid") == "p_10001")
check("side=player", pa.get("side") == "player")
check("kind=player", pa.get("kind") == "player")
check("human_controlled", pa.get("human_controlled") is True)
check("class_name", pa.get("class_name") == "战士")
check("level", pa.get("level") == 10)
check("hp/mp 当前值", pa.get("hp") == 100 and pa.get("mp") == 30)
check("equipment 透传", pa.get("equipment") == {})
check("class_tier 透传", pa.get("class_tier") == 1)
check("attributes 透传", pa.get("attributes") == {"力量": 10, "体质": 5})
check("evolve_path 透传", pa.get("evolve_path") == 0)
check("race 透传", pa.get("race") == "人族")
check("qq_id 透传", pa.get("qq_id") == 10001)
check("skills=learned_skills", pa.get("skills") == ["猛击", "治愈术"])
check("name", pa.get("name") == "测试勇者")

section("build_sides")
sides = BR.build_sides(player=p, enemies=[mon])
check("player side 1 actor", len(sides.get("player", [])) == 1)
check("enemy side 1 actor", len(sides.get("enemy", [])) == 1)
check("player actor human_controlled", sides["player"][0].get("human_controlled") is True)
check("enemy actor side=enemy", sides["enemy"][0].get("side") == "enemy")

section("端到端：saintess_engine 真实怪组完整战斗")
# 用真实数据管线：build_monster → build_monster_group（缩放后多怪）
from content import drops as D
# content 是 game/content.py（`from .. import content as C` 在命令层）
# 真实地图（用第一张野外图）
import json
# 直接手工构造 map_obj（避免依赖真实地图数据）
map_obj = {"id": "test_plain", "name": "测试平原", "area": "field", "type": "field", "lv": 5}
monster_def = ("test_slime", "史莱姆", "dps", 5, [], [])
mon_real = D.build_monster(monster_def, map_obj)
group = D.build_monster_group(mon_real, map_obj, player=p)
check("build_monster_group 返回阵列", isinstance(group, list) and len(group) >= 1)
# 数据桥翻译
sides = BR.build_sides(player=p, enemies=group)
check("sides player/enemy 非空", len(sides["player"]) == 1 and len(sides["enemy"]) >= 1)
# 开战
b = B2Battle("monster", sides=sides)
check("battle 构造成功", b is not None)
check("btype", b.btype == "monster")
check("result None", b.result is None)
# 普攻：玩家打第一个怪
focus = b.focus()
check("focus 是玩家", focus is not None and focus.get("kind") == "player")
enemy = b.sides_of("enemy")[0]
logs, ended = b.act(B2A.ActCtx(caster=focus, action="attack", skill_name=None, target=enemy))
check("普攻执行不报错", isinstance(logs, list))
check("攻击后敌方 hp 减少或死亡", enemy.get("hp", 0) <= mon_real["hp"] if not ended else True)
# 自动跑完整战斗（auto_run——全自动直到结束）
logs2 = []
b2 = B2Battle("monster", sides=BR.build_sides(player=p, enemies=group))
b2.auto_run(logs2)
check("auto_run 战斗有结果", b2.result in ("victory", "defeat", "fled"))
check("auto_run 日志非空", len(logs2) > 0)

section("开战仪式 prepare_player_for_battle")
# 玩家：DB max_hp 给旧值 100（战士 Lv10 实时面板应 > 100——v95.19 面板实时化）
_p2 = make_player(level=10, hp=80, mp=20)
_p2["max_hp"], _p2["max_mp"] = 100, 30  # 模拟 DB 注册/升级快照旧值
# 预置 event_state：echo_bless（一次性）+ poi_buff（left=2）
import json as _json
db.set_event_state("bless_10001", "1")
db.set_event_state("poi_buff_10001", _json.dumps(
    {"stat": "atk", "mult": 1.10, "name": "攻击", "left": 2}, ensure_ascii=False))
BR.prepare_player_for_battle(_p2, title_bonus={}, event_state=BR._as_event_state(db))
check("播种 shields/cooldown/resources/stacks（player dict 协议；buffs 容器已随 V 系列合并删除）",
      all(isinstance(_p2.get(k), dict) for k in
          ("shields", "cooldown", "resources", "stacks"))
      and "buffs" not in _p2)
check("echo_bless 消费进 _battle_boons（V6 面板快照标记）",
      (_p2.get("_battle_boons") or {}).get("echo_bless", {}).get("mult") == 1.05)
check("echo_bless event_state 清空", not db.get_event_state("bless_10001"))
# V6：boons → player_to_actor 翻译成 actor.effects 面板快照（整场生效）
_boon_actor = BR.player_to_actor(dict(_p2))
check("echo_bless 翻译进 actor.effects",
      (_boon_actor.get("effects") or {}).get("echo_bless", {}).get("mult") == 1.05)
check("poi_buff 翻译进 actor.effects",
      (_boon_actor.get("effects") or {}).get("poi_buff", {}).get("stat") == "atk")
check("神龛 poi_buff 挂上", (_p2.get("poi_buff") or {}).get("stat") == "atk")
check("poi_buff left 2→1", _json.loads(db.get_event_state("poi_buff_10001"))["left"] == 1)
check("max_hp 实时化 > 100", int(_p2.get("max_hp", 0)) > 100, "max_hp=%s" % _p2.get("max_hp"))
# 第二次开战：echo 不再重复；poi left 1→0 删 key
_p3 = make_player(level=10, hp=80, mp=20)
_p3["max_hp"], _p3["max_mp"] = 100, 30
BR.prepare_player_for_battle(_p3, title_bonus={}, event_state=BR._as_event_state(db))
check("二次开战 echo 不重复", not (_p3.get("_battle_boons") or {}).get("echo_bless"))
check("poi left 耗尽删 key", not db.get_event_state("poi_buff_10001"))
check("二次开战 poi_buff 仍挂上", (_p3.get("poi_buff") or {}).get("stat") == "atk")

section("战斗回写 sync_player_from_actor")
_p4 = make_player(level=10, hp=200, mp=50)
_sides = BR.build_sides(player=_p4, enemies=group)
_b3 = B2Battle("monster", sides=_sides)
_focus = _b3.focus()
_focus["hp"] = 77          # 引擎改 actor（副本）
_focus["mp"] = 12
_focus.setdefault("effects", {})["atk_up"] = {"stacks": 2}
BR.sync_player_from_actor(_p4, _focus)
check("回写 hp", _p4.get("hp") == 77)
check("回写 mp", _p4.get("mp") == 12)
check("回写 effects", (_p4.get("effects") or {}).get("atk_up", {}).get("stacks") == 2)
check("空 actor 安全", BR.sync_player_from_actor(_p4, {}) is _p4)

# ============================================================
# 🔒 T6⑨（2026-09-20）：引擎 Battle「构造 / 恢复」出口唯一性（防复发门禁）
#
# 背景（T6 第 1 轮实测教训）：`content/world_cmds.py::move` 的撞怪兜底分支经
# `from ext_combat import Battle as B2` **裸造 Battle**（不带 `text=`）⇒ 绕过
# 「玩家可见文案唯一真源」。★ 该分支按字面量 grep `Battle(` 扫不出来（走的别名）⇒
# 本门禁按 **import 绑定**扫：别名（`Battle as B2`）与模块别名（`import saintess_engine as SE`
# → `SE.Battle(...)`）两条绕行路都盯。
#
# 判据：`content/**` 里除 `content/bridge.py::{make_battle,restore_battle}`（唯一出口本身）
#       外零处构造 / 恢复；白名单两处必须**确实被扫到**（防「扫描器整体失灵」的假绿）；
#       三条反证：改前段（别名裸造）必命中 · 模块别名裸造必命中 · 正路（`BR.make_battle`）必不命中。
# ============================================================
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ALLOWED_OUTLETS = {
    ("content/bridge.py", "make_battle", "construct"),
    ("content/bridge.py", "restore_battle", "restore"),
}


#: ★ 2026-09-23：`Battle` 从引擎搬进了扩展包 `ext_combat`（包栈重构第 2 批）——
#: 扫描器要认「战斗实现的提供方」，不再写死引擎包名（否则搬迁后整体失灵、假绿）。
_BATTLE_SOURCES = ("saintess_engine", "ext_combat")


def _scan_tree(rel, src):
    """返回 [(rel, 所在函数, 行号, 绑定全名, construct/restore)]。"""
    out = []
    tree = ast.parse(src)
    parents = {}
    for _node in ast.walk(tree):
        for _child in ast.iter_child_nodes(_node):
            parents[_child] = _node
    alias, mod_alias = {}, set()
    for _node in ast.walk(tree):
        if isinstance(_node, ast.ImportFrom) and any(
                _p in (_node.module or "") for _p in _BATTLE_SOURCES):
            for _a in _node.names:
                if _a.name == "Battle":
                    alias[_a.asname or _a.name] = "%s.Battle" % _node.module
        elif isinstance(_node, ast.Import):
            for _a in _node.names:
                if any(_a.name.startswith(_p) for _p in _BATTLE_SOURCES):
                    mod_alias.add(_a.asname or _a.name)

    def _enclosing(node):
        _cur = parents.get(node)
        while _cur is not None:
            if isinstance(_cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return _cur.name
            _cur = parents.get(_cur)
        return "<模块级>"

    for _node in ast.walk(tree):
        if not isinstance(_node, ast.Call):
            continue
        _f = _node.func
        _bound = _kind = None
        if isinstance(_f, ast.Name) and _f.id in alias:
            _bound, _kind = alias[_f.id], "construct"
        elif (isinstance(_f, ast.Attribute) and _f.attr == "Battle"
              and isinstance(_f.value, ast.Name) and _f.value.id in mod_alias):
            _bound, _kind = "%s.Battle" % _f.value.id, "construct"
        elif (isinstance(_f, ast.Attribute) and _f.attr == "from_state"
              and isinstance(_f.value, ast.Name) and _f.value.id in alias):
            _bound, _kind = alias[_f.value.id], "restore"
        if _bound:
            out.append((rel, _enclosing(_node), _node.lineno, _bound, _kind))
    return out


def _scan_battle_outlets(root):
    found = []
    for _dirpath, _dirs, _files in os.walk(root):
        for _name in sorted(_files):
            if not _name.endswith(".py"):
                continue
            _path = os.path.join(_dirpath, _name)
            _rel = os.path.relpath(_path, _PKG_ROOT).replace(os.sep, "/")
            found += _scan_tree(_rel, open(_path, encoding="utf-8").read())
    return found


section("T6⑨ 构造出口唯一性：content/** 禁绕过 content/bridge.py 出口")
_hits = _scan_battle_outlets(os.path.join(_PKG_ROOT, "content"))
_bad = [h for h in _hits if (h[0], h[1], h[4]) not in _ALLOWED_OUTLETS]
check("content/** 零处绕过 bridge 出口的 Battle 构造/恢复", not _bad, _bad[:4])
check("白名单两处（bridge.make_battle / bridge.restore_battle）确实被扫到",
      {(h[0], h[1], h[4]) for h in _hits} >= _ALLOWED_OUTLETS,
      sorted({(h[0], h[1], h[4]) for h in _hits}))
_neg1 = _scan_tree("<反证:改前段>", 'from ext_combat import Battle as B2\n'
                                      'def f(self):\n'
                                      '    return B2("monster", sides={})\n')
check("反证①：改前那段（别名 B2 裸造）必被扫到",
      len(_neg1) == 1 and _neg1[0][4] == "construct", _neg1)
_neg2 = _scan_tree("<反证:模块别名>", 'import saintess_engine as SE\n'
                                       'def f():\n'
                                       '    return SE.Battle("monster", sides={})\n')
check("反证②：模块别名（SE.Battle）裸造必被扫到",
      len(_neg2) == 1 and _neg2[0][4] == "construct", _neg2)
_neg3 = _scan_tree("<反证:正路>", 'from . import bridge as BR\n'
                                   'def f():\n'
                                   '    return BR.make_battle("monster", sides={})\n')
check("反证③：正路（BR.make_battle）必不命中", not _neg3, _neg3)

print("\n=== 结果 PASS=%d FAIL=%d ===" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
