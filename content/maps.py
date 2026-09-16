# -*- coding: utf-8 -*-
"""包内空间域（`content/maps.py`）—— 地图 / 子区域的**形状查询适配层**。

职责边界（**形状在引擎，内容在本模块**）
----------------------------------------
* 数据来源 = 包内域 `content/data/maps.json`（`nodes` / `roles` / `topology` / `links`）
  与 `content/data/subareas.json`（房间行：`hidden` / `reveal` / `monsters` …）。
* 全部**拓扑派生**（邻接 / 深度 / 出入口 / 必经路径 / 结构审计）由引擎
  `saintess_engine.space.Space` 完成；本模块只做这件事：把内容字段翻成引擎的**角色名**
  （`_ROLES` = hub/through/exit 的**取值**，引擎不认具体取值），并保留本游戏的
  「老数据兜底」策略（v87 时期城里没有出口类型节点时，回退出入口 = id 以 `_gate` 结尾者）。
* 游戏专属判定（`hidden` / `reveal` 字段、探索计数落库）留本模块 —— 引擎侧无对应形状。
"""
from __future__ import annotations

import os

from saintess_engine.records import RecordsSet

_HERE = os.path.dirname(os.path.abspath(__file__))          # <pkg>/content
_PKG_ROOT = os.path.dirname(_HERE)                          # <pkg>

# 读表口 = 引擎 records 形状：读域文件 / 缺表留痕（`missing`）收成一处（零默认值、零改写）
_R = RecordsSet(_PKG_ROOT, {
    "maps":     {"sub": "content/data"},
    "subareas": {"sub": "content/data"},
})


# maps 域（图内形状）：{map_id: {name, roles, nodes:[{id,name,role}], topology, links?}}
_MAPS: dict = _R.maps.all()
# subareas 域（房间内容）：{subarea_id: 源行原样 + 注入 map}
_SUBS: dict = _R.subareas.all()

# `roles` 兜底（域里每张图都带 `roles`，实测 121/121 同值 —— 取第一个非空的当兜底，防单图缺键）
_DOM_ROLES: dict = next((e.get("roles") for e in _MAPS.values() if e.get("roles")), {})


# ============================================================
# 存储口（`db`）—— 只给探索计数（`reveal_*` event_state）用
# ============================================================
from saintess_engine.wire import Wire
_WIRE = Wire()


def bind_host(**objs):
    """宿主替身注入（幂等）。引擎装配期（`content/facade.py` 扇出表）调用。

    本模块在终态只认存档半边（`db` = `content.persistence`）；其余键由 `Wire` 收下不解释。
    """
    _WIRE.bind(**objs)


from ._pkgref import DB as db            # B1：包内存储层（引擎 wire 形状的惰性句柄）


# ============================================================
# 包内域读口（maps / subareas 域）—— 图条目 / 房间行 / 显式连通表（import 期各读一次）
# ============================================================
def _map_entry(map_id: str) -> dict:
    """该图的形状条目（未知图 → 空 dict，与宿主 `SUBAREAS.get(map_id) or []` 同义）。"""
    ent = _MAPS.get(map_id)
    return ent if isinstance(ent, dict) else {}


def _role_by_type(ent: dict) -> dict:
    """子区域 type（域 `nodes[].role` 原样）→ 引擎角色名（= 宿主 `_ROLE_BY_TYPE` 的**逆映射**，
    取值来自域 `roles`，不新增第二处定义）。"""
    return {v: k for k, v in ((ent.get("roles") or _DOM_ROLES) or {}).items()}


def _sa_rows(map_id: str) -> list:
    """该图子区域行（**声明序** = `maps.nodes` 序；行 = `subareas` 域原样）。
    与宿主 `SUBAREAS.get(map_id, [])` 逐字段等价（实测 628 条 0 差异）。"""
    return [row for row in (_SUBS.get(n.get("id")) for n in (_map_entry(map_id).get("nodes") or []))
            if isinstance(row, dict)]


def _subarea_links_index(map_id: str):
    """该图的显式网状连通表（无显式定义 → None，与宿主 `SUBAREA_LINKS_INDEX.get` 同义）。"""
    return _map_entry(map_id).get("links")


# ---- v183 引擎形状适配：本游戏的「角色映射」----------------------------------
# 引擎只认角色名（hub/through/exit），**取值**由内容侧给 —— 这三条映射就是全部内容。
_ROLES = {"hub": "hub", "through": "through", "exit": "exit"}


def map_space(map_id: str):
    """本图的引擎 `Space`（节点 = 子区域，角色 = type 映射；显式连通表优先）。

    不缓存：每张图现读现建（构造很便宜，每图 ≤ 十余节点，移动路径上的调用量级可接受）。
    读的是包内域快照（`_MAPS` / `_SUBS`，import 期各读一次）—— 运行期不再有第二份来源，故不存在「读到半成品」问题。
    """
    from saintess_engine.space import MESH, Space
    ent = _map_entry(map_id)
    role_of_type = _role_by_type(ent)
    nodes = [{"id": n["id"], "name": n.get("name"), "role": role_of_type.get(n.get("role"))}
             for n in (ent.get("nodes") or [])]
    mesh = _subarea_links_index(map_id)
    # 旧数据兜底（v87 时期的老图）：城里没有「城镇出口」类型节点时，出入口退回
    # id 以 `_gate` 结尾者。属**内容策略**（引擎不认识 id 命名习惯），故在适配层算好传进去。
    gate_override = None
    if (nodes and nodes[0]["role"] == _ROLES["hub"]
            and not any(n["role"] == _ROLES["exit"] for n in nodes)):
        gate_override = next((n["id"] for n in nodes if str(n["id"]).endswith("_gate")), None)
    if mesh is not None:
        return Space(nodes=nodes, topology=MESH, roles=_ROLES, links=mesh,
                     label_key="name", gate=gate_override)
    topo = "star" if (nodes and nodes[0]["role"] == _ROLES["hub"]) else "chain"
    return Space(nodes=nodes, topology=topo, roles=_ROLES, label_key="name", gate=gate_override)


def map_center(map_id: str) -> str:
    """枢纽节点 id（星形图的中心）；链状/网状图无枢纽 → ""。"""
    sp = map_space(map_id)
    return sp.root if sp.role_of(sp.root) == _ROLES["hub"] else ""


def map_route(map_id: str, src: str, dst: str) -> list:
    """同图必经路径（**含两端**）；同点 → 单元素；任一端未知或不可达 → []。

    用途：把「不能直达，需要先经过 X、Y」这类提示从手算改成问引擎
    （v183 之前该判断在 travel / world 各抄了一份星形链首逻辑）。
    """
    return map_space(map_id).route(src, dst)


# ============================================================
# 装配期派生表（`MONSTER_LOCS` / `ENCY_*`）—— **已收归 `content/catalog_space.py` 一处**
# ============================================================
# S3（本批）删除：本模块曾自带一份 `build_ency()` / `build_monster_locs()` + 装配输入适配
# + 4 只模块级 dict，与 `content/catalog_space.py:⑦` 的同名实现**逐条等价**（探针实测 4 表全等），
# 且**本模块那份从未被调用**（4 只 dict 恒为空）—— 消费者读的是 `content.catalog_space.<名>`
# （`content/economy_cmds.py:4707` 走 `_cspace.ENCY_MAP_MONSTERS`；`C.MONSTER_LOCS` 由门面
# `AGGREGATE_MODULES` 里 `content.catalog_space` 先落者胜 ⇒ 同一只对象）。等价与删除依据见
# `out/raw/space_snapshot_before.json::residue` 与 `out/LANDING.md`。


def subarea_links(map_id: str, subarea_id: str) -> list:
    """同图内可直达的子区域 id 列表（v183：派生搬进引擎 `saintess_engine.space`）。

    显式网状连通表（`maps` 域的 `links`）优先；否则按拓扑派生：**城镇星形
    （枢纽 ↔ 场所、通道 ↔ 出口，含无通道时枢纽直连出口的防断链分支）/ 野外线性**。
    结果**包含隐藏房间，不过滤** —— 隐藏房间的可见性由命令层过滤（历史契约不变）。

    注（v141 审计）：副本大陆克隆的 subareas 无命令层消费本函数 —— 保留待动态化；
    命令层副本移动走 SUBAREA_LINKS_INDEX（instance.py _subarea_arrive 直读数据表）。
    """
    return map_space(map_id).links(subarea_id)


def map_exit_subarea(map_id: str) -> str:
    """离开该图必须所在的子区域（v183：= 引擎 `Space.gate()`）。

    城镇：城镇出口子区域；非城镇：首个子区域（入口）。
    ★ 与 `map_entry_subarea` **同义** —— v183 之前这两份实现逐字重复，现已合一
    （两者都问引擎同一个 gate，名字保留只为调用方零改动）。
    """
    return map_space(map_id).gate()


def map_entry_subarea(map_id: str) -> str:
    """跨图进入该图的落点子区域（v183：= 引擎 `Space.gate()`，与 map_exit_subarea 同义）。

    城镇：出口子区域（从野外进城先到镇郊，再经东大街进广场）；非城镇：首个子区域。
    注：注册/传送/回家等「城内直达」场景用 subareas[0]（广场），不走城门。
    """
    return map_space(map_id).gate()


# ---- v115 网状子区域核心 ----

def _explore_count(group_id: str, qq_id: str, map_id: str) -> int:
    """当前探索计数：event_state key = reveal_{map_id}_{qq_id}。"""
    raw = db.get_event_state("reveal_{}_{}".format(map_id, qq_id))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def subarea_depth(map_id: str, sa_id: str) -> int:
    """从该图首个子区域（入口）算的深度（v183：口径由引擎定）。

    - 显式连通表 → 从入口 BFS（网状图没有天然顺序）
    - 否则 → 声明序（子区域列表位置：链状/星形图里顺序本身就是作者给的由近及远）
    """
    return map_space(map_id).depth(sa_id)


def _is_hidden_in_row(map_id: str, sa_id: str) -> bool:
    """查 subareas 域中该子区域条目的 hidden 字段（默认 False）。"""
    for s in _sa_rows(map_id):
        if s.get("id") == sa_id:
            return bool(s.get("hidden"))
    return False


def is_hidden_room(map_id: str, sa_id: str) -> bool:
    """查 subareas 域中该子区域条目的 hidden 字段（默认 False）—— **公开口，必须在**。

    ★ S3 独立复核（本函数曾被降为私有 `_is_hidden_in_row`，已回退）：
    静态引用核查会得出「零调用者」，但真正的消费者是**动态取件** ——
    `content/travel.py:139`（`visible_sas`）与 `:192`（`subarea_hidden_block`）走的是
    `getattr(C, "is_hidden_room", None)`：取不到 ⇒ `None` ⇒ 落进 travel 模块头注写明的
    「接口缺失 → **全部可见 / 放行**」兜底分支 ⇒ 隐藏房会被列进面板、未揭示也能直接前往。
    故本口属判定表里的 **(C) 留包**，不许从公开面移除。
    证据：`out/raw/S3_hidden_regression.txt`（移除态实测 `emerald_forest` 隐藏房
    `visible_leak=1`、`subarea_hidden_block` 返回 `None`；恢复后两者回零/回文案）。
    """
    return _is_hidden_in_row(map_id, sa_id)


def reveal_met(cond, group_id: str, qq_id: str, map_id: str) -> bool:
    """reveal 条件是否满足。cond 形如：
    - "explore:N"：event_state key=reveal_{map}_{qq} 的探索次数 ≥ N
    - "item:道具名"：db.count_item > 0
    无 cond / 未知格式化 → True（开放）。"""
    if not cond:
        return True
    if cond.startswith("explore:"):
        try:
            need = int(cond.split(":", 1)[1])
        except (TypeError, ValueError):
            return False
        return _explore_count(group_id, qq_id, map_id) >= need
    if cond.startswith("item:"):
        item = cond.split(":", 1)[1]
        return db.count_item(group_id, qq_id, item) > 0
    return True


def reveal_progress(group_id: str, qq_id: str, map_id: str):
    """返回 (cur, need)——当前探索计数 与 本图需探索次数的最大值。
    本图无 explore: 型 reveal 房间 → 返回 (0, 0)。"""
    needs = []
    for s in _sa_rows(map_id):
        cond = s.get("reveal")
        if cond and cond.startswith("explore:"):
            try:
                needs.append(int(cond.split(":", 1)[1]))
            except (TypeError, ValueError):
                pass
    if not needs:
        return (0, 0)
    return _explore_count(group_id, qq_id, map_id), max(needs)


def bump_explore_count(group_id: str, qq_id: str, map_id: str):
    """探索计数 +1（G agent 会在每次野外探索时调用）。
    event_state key = reveal_{map_id}_{qq_id}。"""
    key = "reveal_{}_{}".format(map_id, qq_id)
    db.set_event_state(key, _explore_count(group_id, qq_id, map_id) + 1)


__all__ = [
    "map_space", "map_center", "map_route",
    "subarea_links", "map_exit_subarea", "map_entry_subarea", "subarea_depth",
    "reveal_met", "reveal_progress", "bump_explore_count",
    "is_hidden_room",
    "bind_host",
]
# 注：装配期派生表（`MONSTER_LOCS` / `ENCY_*`）与 `build_ency` / `build_monster_locs`
# 不在本模块 —— 真源 = `content/catalog_space.py:⑦`（见上方同名小节）。
