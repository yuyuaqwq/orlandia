# -*- coding: utf-8 -*-
"""《奥兰迪亚》包内**组队域**（`content/party.py`）—— 逐字搬自游戏仓 `game/services/party.py`（225 行）。

★ B12-L4（2026-09-14）：宿主 `game/services/party.py` 薄壳化 =「加载包 + 注入宿主替身 + 同名 re-export」，
调用点与调用签名**一字不变**：
    命令层   `game/commands/social.py:301/366`（`party` 命令 5 名 + `party_leave` 命令 3 名）
    聚合导出 `game/services/__init__.py:40`（8 个名字，逐字沿用）
    测试     `tests/test_services_party_guild.py:24`（`resolve_party_target`/`party_join`/`party_leave_execute`）

只改两类东西（与 `content/quests_flow.py` / `content/world_cmds.py` 同款）
----------------------------------------------------------------------
| 真源写法 | 包内写法 | 说明 |
|---|---|---|
| 函数体内 `from .. import db` | **删行**（模块级 `db` = 惰性宿主代理） | 正文里 `db.xxx(...)` 一行未改 |
| 函数体内 `from .. import content as C` | **删行**（模块级 `C` = 宿主聚合层代理） | `C.display` / `C.CLASS_NOVICE` / `C.check_achievements` 一字未改 |
| 函数体内 `from ..content_rules.panel import player_final_stats` | `final_stats = _panel_stats()` | 同一函数对象（注入优先），正文其余不动 |
| 真源「队员 list + `members[0]` 当队长」的隐含约定（散在 3 处） | `_roster(members)` = 引擎 `saintess_engine.run.Roster` | ★ PKG-G：**成员集合形状**（保序 / 队长 / 在册过滤）；不造第二个名单，顺序与判据都不变 |

※ B14-2 L8（2026-09-14）：`C.CLASS_NOVICE` 已切包内读口（`content/tables.py:45`，逐值相等实测 True），
  正文该行取值口改写为本地名 `CLASS_NOVICE`；`C` 仍有残余（`C.display` / `C.check_achievements`）→ 替身保留。

⚠️ 缺口（报告同步登记，**不建第二份读口**）：
  · `C.display`（展示名索引，宿主 `game/core/index.py`）**无同名域/读口** ⇒ 保留 `C.display`
    （`CLASS_NOVICE` 原也走注入，B14-2 L8 已切包内读口，不再走注入以免双源）。
  · `C.check_achievements`（成就判定）= 宿主 `game/core/achievements.py`，本线不搬。
  · `db.party_*` / `db.bump_stats` / `db.get_group_players` / `db.update_player` / `db.clear_battle` /
    `db.get_battle` 全部是**存档层原语**（`game/store/social.py`）——接人层铁律 ⇒ 留宿主。

真源模块 docstring（逐字保留）
------------------------------
'''
奥兰迪亚·余烬纪年服务层 - party（组队域，v181 P4-6）

组队/退队的编排逻辑（v104 M04 P1/P2、v141 大陆隔离规则原样随迁）：
由 social.py 『组队/队伍』『退队』命令层消费——命令层只留解析 + 文案壳，
业务判定与落库调用收敛到本文件（store/social.py 已备 party_* 原语）。

- v104 M04 P1：战斗/副本中禁止组队/拉人——防把副本队长/队员拉走（原队伍解散→副本僵尸化）、
  战斗中拉新人。队员的副本 battle 行存队长名下；retreated（撤退保留进度）不算战斗中。
- v49：已有队伍时队长用『组队 <名字>』拉新人（上限 4 人）。
- v104 M04 P2：拉人/组队成功双方各记 party_count（成就进度）。
- v104 P1：副本进行中队长禁止退队（battle 只存队长名下）；队员退队后同步清战斗锁；
  队长退队=队伍解散，其名下撤退保留的副本进度行一并清理。
- v141 大陆隔离：队员退队时若正挂在副本大陆（world_id=inst:），回滚到主大陆。

依赖红线：可 import data/core/store/db/engine/battle/reward；禁止 import commands/*。
db 等依赖一律函数体内惰性 import（防 data/_assembly 加载期循环，core 样板同款铁律）。

'''
"""

from __future__ import annotations

# ============================================================
# ① 宿主替身口（注入优先 → sys.modules → importlib；**绝不静默空跑**）
# ============================================================
from ._hostref import make_wire_module  # 取件工厂单源（P0-3；常量本身不再被本文件引用）
from saintess_engine.wire import slot as _slot
_WIRE, bind_host = _slot()


_wire_module = make_wire_module(_WIRE, "party")


def _wire_attr(mod: str, attr: str):
    """宿主模块属性 —— 真源「函数内 `from ..<mod> import <attr>`」的同义替身（调用时解析）。"""
    return getattr(_wire_module(mod), attr)


class _HostMod:
    """宿主模块替身（`C` / `db`）——`C.xxx` / `db.xxx` 正文一字未改，属性访问时解析。"""

    def __init__(self, name):
        self._name = name

    def __getattr__(self, attr):
        return _wire_attr(self._name, attr)


from ._pkgref import DB as db, PkgModule
# ★ P4′-W1 A 组：`C.display`→content.index · `C.check_achievements`→content.achievements（探针实测）
_C_INDEX = PkgModule("content.index")
_C_ACH = PkgModule("content.achievements")
C = _HostMod("content")     # 残留：历史句柄，无调用点（P5C 随壳一起清）


def _panel_stats():
    """真源函数体内 `from ..content_rules.panel import player_final_stats` 的同义替身（注入优先）。"""
    if "panel_stats" in _WIRE.handles():
        return _WIRE.handle("panel_stats")
    from .panel import player_final_stats
    return player_final_stats


# ============================================================
# ② 真源正文（逐字；仅上表三类取件行改动）
# ============================================================
import re

# B14-2 L8（2026-09-14）：`C.CLASS_NOVICE`（宿主聚合层）→ 包内读口（`content/tables.py:45`，逐值相等）
from .tables import CLASS_NOVICE      # noqa: E402
from . import texts as _T            # C 档 20b（2026-09-19）：文案表读口（本文件首次接入）

# ★ PKG-G：成员集合形状（引擎 `saintess_engine.run.Roster`）——「谁在里面」只有这一个来源
from saintess_engine.run import Roster   # noqa: E402


def _roster(members) -> Roster:
    """队伍成员集合形状（引擎 `run.Roster`）：**保序** + **队长 = 首成员**。

    真源把队伍成员当普通 list 用，队长靠 `members[0]` 的隐含约定，散在
    面板队长标记 / 拉人权限 / 副本成员判定三处各写一遍。引擎已有名单形状 ⇒
    收口到 `Roster`，包内不再复制这套约定（**不造第二个成员集合**）。
    顺序 = `db.party_members` 给的顺序（队长自指行第一）——本形状**不重排**。

    `members` 是**调用方给的当前队伍**：`None` / `[]` = 无队（与真源 `if members:` 同义）。
    """
    return Roster(members or ())


def _state_roster(state) -> Roster:
    """从战斗态读成员集合（引擎 `run.Roster`）。

    - `members` **键缺失** = 老存档的空名单（真源 `.get("members", [])` 同义）；
    - `members` **键在但读到 None** = 形状读不到 → **醒目报错**（fail-closed：不静默
      降级成「空名单」；真源那句 `for m in None` 的 TypeError 同样是响亮失败）。
    """
    if "members" not in state:
        return _roster(())
    members = state["members"]
    if members is None:
        raise ValueError("party：战斗态成员集合读不到（state['members'] 是 None）—— 拒绝静默当空名单")
    return _roster(members)


# ---- 组队（『组队/队伍』）----


def resolve_party_target(group_id, qq_id, raw_target):
    """解析『组队/队伍』参数 → (target_qq, err) 或 (None, None)（无目标=看面板，由调用方处理）。

    - v104 M04 P2：『队伍甲』免空格拉人——『队伍』前缀剥掉（『队伍』=查看面板，空参同义）。
    - v173.3 意见#157：『组队 @某人』At 标记剥离（At 在指令后不在开头）。
    纯解析，无 db 读写。命令层对 (target_qq=None 且 err=None) 走面板分支。
    """
    target = (raw_target or "").strip()
    if target.startswith("队伍"):
        target = target[2:].strip()
    _at_m = re.search(r"\[At:(\d+)\]", target)
    if _at_m:
        target = _at_m.group(1)
    if not target:
        return None, None
    # 找目标玩家
    all_players = db.get_group_players(group_id)
    target_qq = None
    for q, p in all_players.items():
        if p.get("name") == target or q == target:
            target_qq = q
            break
    if not target_qq:
        return None, _T.text("party.target_missing", name=target)
    return target_qq, None


def party_in_battle(group_id, qq_id):
    """qq_id 是否处于野外/副本战斗中（禁止组队/拉人/退队的战斗锁判定）。

    v104 M04 P1：队员的副本 battle 行存队长名下，须经 party 反查队长；
    retreated（撤退保留进度）不算战斗中。返回 "self"/"target"/None 供文案层区分。
    """
    _lb = db.get_battle(group_id, qq_id)
    if _lb and not (_lb["state"].get("type") == "instance" and _lb["state"].get("retreated")):
        return "self"
    return None


def target_in_battle(group_id, target_qq, inst_battle_hook=None):
    """目标玩家是否战斗/副本中（组队拉人前校验）。

    inst_battle_hook：命令层注入的 `_instance_battle_for`（读大陆实例权威源，
    是纯 db/内存只读判定，与 store 原语同层）；缺省时按 party 反查队长 battle 行兜底。
    返回 "battle"/"instance"/None。
    """
    _tb = db.get_battle(group_id, target_qq)
    if _tb and not (_tb["state"].get("type") == "instance" and _tb["state"].get("retreated")):
        return "battle"
    if inst_battle_hook is not None:
        try:
            if inst_battle_hook(group_id, target_qq):
                return "instance"
        except Exception:
            pass
    return None


def party_view_lines(group_id, members, get_player=None, final_stats=None, display=None):
    """组队面板行（v104 M04 P2：等级/职业/速度值展示；v121 改展示速度而非静态出手位）。

    返回行列表（不含空行结尾）。get_player/final_stats/display 由命令层注入
    （self._player / player_final_stats / C.display——后者为面板展示，命令层语义），
    缺省时内部用 db.get_player + game.engine/core 直读（等价实现）。
    """
    if get_player is None:
        get_player = lambda g, q: db.get_player(g, q)
    if final_stats is None:
        final_stats = _panel_stats()
    if display is None:
        display = _C_INDEX.display
    roster = _roster(members)
    lines = [_T.text("party.title", n=len(roster)), "━━━━━━━━━━━━"]
    _order = []
    for _m in roster.members:
        _p = get_player(group_id, _m)
        _spd = 0
        if _p:
            _spd = final_stats(
                _p["class_name"], _p["level"], _p.get("equipment", {}),
                _p.get("class_tier", 0), _p.get("attributes"),
                _p.get("evolve_path", 0), None, _p.get("race")
            ).get("spd", 0) or 0
        _order.append((_spd, str(_m)))
    _spdmap = dict(_order)
    for i, m in enumerate(roster.members, 1):
        p = get_player(group_id, m)
        cls_str = (
            _T.text("party.row_lv", lv=p.get('level', '?'),
                cls=display('classes', p.get('class_name') or CLASS_NOVICE))
            if p else ""
        )
        pos_str = _T.text("party.row_spd", spd=_spdmap.get(str(m), '?')) if len(roster) > 1 else ""
        lines.append(_T.text("party.row", i=i, name=p['name'] if p else m, cls=cls_str, pos=pos_str) + (_T.static("party.leader_mark") if m == roster.leader else ""))
    lines.append(_T.static("party.tip"))
    return lines


def party_join(group_id, qq_id, target_qq, target_name, members, check_achievements=None):
    """已有队伍时队长拉人 / 无队伍时创建队伍 的统一编排。

    members：调用方已查的 db.party_members（空 = 新建 2 人队，非空 = 队长拉人）。
    check_achievements：命令层注入 C.check_achievements（可空，缺省内部直调 C 聚合）。
    返回 (ok, lines, my_name)：ok=False 时 lines=[拒绝文案]；ok=True 时 lines=成功面板行。
    组队次数 bump（v104 M04 P2 双方各记）与成就判定（v105 阶段九）在本函数内完成。
    """
    if check_achievements is None:
        check_achievements = _C_ACH.check_achievements
    roster = _roster(members)
    if roster.members:
        # 已有队伍：仅队长可拉人
        if roster.leader != str(qq_id):
            return False, [_T.static("party.in_party")], None
        if db.party_add(group_id, qq_id, target_qq):
            db.bump_stats(group_id, qq_id, party_count=1)
            db.bump_stats(group_id, target_qq, party_count=1)
            check_achievements(group_id, qq_id)
            check_achievements(group_id, target_qq)
            my_name = db.get_player(group_id, qq_id)
            return True, [
                _T.text("party.join_lead", name=target_name, n=len(db.party_members(group_id, qq_id)),
                    name2=target_name, leader=my_name['name'] if my_name else qq_id)
            ], my_name
        return False, [_T.text("party.join_fail", name=target_name)], None
    if not db.party_create(group_id, qq_id, target_qq):
        return False, [_T.text("party.join_fail2", name=target_name)], None
    db.bump_stats(group_id, qq_id, party_count=1)
    db.bump_stats(group_id, target_qq, party_count=1)
    check_achievements(group_id, qq_id)
    check_achievements(group_id, target_qq)
    return True, [_T.text("party.create_ok", name=target_name)], None


# ---- 退队（『退队』）----


def party_leave_check(group_id, qq_id):
    """退队前置守卫：副本进行中队长禁止退队（battle 只存队长名下，队长退队→副本僵尸化）。

    返回 (blocked, msg)：blocked=True 时命令层直接 yield msg。
    """
    b = db.get_battle(group_id, qq_id)
    if b and b["state"].get("type") == "instance" and not b["state"].get("retreated") \
            and str(b["state"].get("leader", qq_id)) == str(qq_id):
        return True, _T.static("party.inst_block")
    return False, None


def party_leave_inst_member(group_id, qq_id):
    """退队者是否正挂在副本队伍中（战斗记录存队长名下）→ 退队后需清其战斗锁。"""
    roster = _roster(db.party_members(group_id, qq_id))
    if roster.members and roster.leader != str(qq_id):
        lb = db.get_battle(group_id, roster.leader)
        if lb and lb["state"].get("type") == "instance" and not lb["state"].get("retreated") \
                and _state_roster(lb["state"]).is_member(qq_id):
            return True
    return False


def party_leave_execute(group_id, qq_id, inst_member, unlock_battle_hook=None, player_hook=None):
    """执行退队 + 退队后清理（v104 P1 战斗锁清理 / v141 大陆隔离回滚 / 队长解散清理）。

    返回 (left, ok_lines, err_lines)：left=True 且 ok_lines=[成功文案]；
    left=False 时 err_lines=[未入队文案]。unlock_battle_hook：命令层注入
    self._unlock_battle（内存锁集合，命令层实例态）；player_hook：self._player。
    """
    if unlock_battle_hook is None:
        def unlock_battle_hook(g, q):
            pass
    if player_hook is None:
        player_hook = db.get_player
    if db.party_leave(group_id, qq_id):
        if inst_member:
            unlock_battle_hook(group_id, qq_id)
            db.clear_battle(group_id, qq_id)
        # v141 大陆隔离：队员退队时若正挂在副本大陆（world_id=inst:），
        # 回滚 world_id 到主大陆 + 位置回副本入口图（防卡副本图出不去）。
        # 大陆实例的 members 快照保留（展示用），副本进度不受退队影响。
        try:
            _p2 = player_hook(group_id, qq_id)
            _wid2 = (_p2 or {}).get("world_id") or ""
            if _wid2.startswith("inst:"):
                db.update_player(group_id, qq_id, world_id="mainland")
        except Exception:
            pass
        # v104 M04 P2：队长退队=队伍解散，其名下撤退保留的副本进度行一并清理
        # （队伍已散，进度无法恢复；此前该行驻留到被新开本覆盖，长期占一行数据）
        if not db.party_members(group_id, qq_id):
            _lb = db.get_battle(group_id, qq_id)
            if _lb and _lb["state"].get("type") == "instance" and _lb["state"].get("retreated"):
                db.clear_battle(group_id, qq_id)
        return True, [_T.static("party.leave_ok")], None
    return False, None, [_T.static("party.leave_none")]
