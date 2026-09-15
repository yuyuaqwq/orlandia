# -*- coding: utf-8 -*-
"""B1 切读点：**包内**惰性模块句柄（`content/_pkgref.py`）。

为什么要它（实测，不是推测）
--------------------------
B1 要把「包 → 宿主薄壳 → 包」拍平成「包 → 包」。但**取件时机本身是行为的一部分**：
旧宿主惰性句柄是**属性访问时**才解析（才 import `game.db`），
而 `from . import persistence as db` 是 **import 期**解析。二者不等价 —— 实测直接炸：

    import game.content
      → game/core/__init__.py:61      from . import smith_stock
      → content/smith_stock.py        from . import persistence as db          ← EAGER
      → content/persistence/__init__.py:11  from .schema import C_MAP_IDS
      → content/persistence/schema.py:30    C_MAP_IDS = _map_ids()
      → content/persistence/schema.py:25    set(C.MAP_BY_ID.keys())            ← C = 宿主 game.content
      → AttributeError: partially initialized module
                        'data.plugins.dragonfall.game.content' has no attribute 'MAP_BY_ID'

根因：`content/persistence/__init__.py` 在 import 期要读宿主 `game.content`
（`C_MAP_IDS = _map_ids()`），所以它是 EAGER 装配窗口里的**危险目标**；凡在窗口内
被 import 的包内文件（`game/core/__init__.py` 那条链上的）都**只能惰性**取它。

本模块把「惰性取包内模块」做成**引擎 wire 形状**（`Wire.lazy` → `LazyRef`）：
取件时机与旧宿主惰性句柄**逐字相同**（首次属性访问才解析）⇒ 行为面不变，
同时不再往返宿主。`saintess_engine.wire` 自身只依赖标准库（`types` / `typing`），
可以安全地出现在任何 EAGER 窗口里。
"""
from __future__ import annotations

import importlib
import sys

from saintess_engine.wire import Wire

#: 宿主存档层**部署适配件**（唯一装配点：读 `GWEN_GAME_DB`/插件目录 → `handles.bind(db_path=…)`）。
#: 不在本批 35 个纯薄壳里；包内文档明写「库路径是部署信息，由宿主 store_factory 注入」。
#:
#: ★ REPOINT-PKG（2026-09-15，B4R B 组第 5/6 项）口径裁定 —— **「宿主薄壳已删」对本项不适用**：
#:   `game/store/store_factory.py`（37 行）**不是薄壳**，是宿主对包内 `content.persistence` 的
#:   **唯一装配点**（零 SQL / 零业务分支，只算 `DB_PATH = $GWEN_GAME_DB | <插件目录>/game_data.db`
#:   并 `handles.bind(db_path=…, clock=…, flush_log=…)`）。库路径是**部署信息**，包内算不出
#:   （包侧 `__file__` 在框架仓，默认路径会变成另一个文件），故**不可包内化**。
#:   实测证据：把本块改成不 import 宿主 → 只 `import game.content` 的入口拿不到 db_path 注入
#:   → `handles.db_path()` 抛 → 数值门禁红 1/18（原因写在 `_warm_host_store` docstring）。
#:   ⇒ B 组第 5 项（`game.store`）：包内真正的 code 级消费者只有 `store.social` 取件两处，
#:     本批已改包内直取（`content/social_guild.py` / `content/social_stall.py`）；
#:     第 6 项（`game.store.store_factory`）**归宿主侧线**（部署适配件迁移/改名时同步本元组）。
#:   ★ 本条 import 是**已加载优先**（在册即返回）⇒ 宿主侧删壳后此处自动静默降级，不炸。
_HOST_FACTORY = (
    "data.plugins.dragonfall.game.store.store_factory",
    "game.store.store_factory",
)
_warmed = False


def _warm_host_store():
    """**一次性**确保宿主工厂已把 `db_path` 句柄注入 `content/persistence/handles`。

    为什么必须有这一步（实测，不是推测）
    ----------------------------------
    旧宿主惰性句柄在**首次属性访问**时 `import game.db` → `game.store`
    → `store_factory`，顺带完成注入；只 `import game.content` 的入口
    （`tests/test_numeric_drop_unify.py`）也靠这个副作用拿到库路径。惰性包内句柄不再触发它
    → `handles.db_path()` 抛「句柄未注入」→ 实测 numeric 门禁红 1/18。
    本步把这条**本来就存在**的依赖从「隐式」变「显式」：仅当宿主工厂尚未在 `sys.modules`
    时才 import 一次（已在册 → 直接返回，绝不覆盖宿主已注入/已重绑的句柄）。
    纯包场景（无宿主）import 失败 → 静默返回，交给 `db_path()` 自己按原样抛。

    ★ 本函数是**业务**（部署适配副作用），不是取件样板：wire 形状里没有它的对应物，
    按铁律 4「换不动的原样留着」。它作为 `DB` 那个惰性 loader 的**前置步骤**原样保留。
    """
    global _warmed
    if _warmed:
        return
    _warmed = True
    for name in _HOST_FACTORY:
        if name in sys.modules:
            return
    for name in _HOST_FACTORY:
        try:
            importlib.import_module(name)
            return
        except Exception:                       # noqa: BLE001  纯包场景：无宿主可注入
            continue


def PkgModule(name, warm=None):
    """包内模块惰性句柄工厂 —— 返回引擎 wire 形状 `LazyRef`。

    * **登记不加载**：首次 `ref.<属性>` / `ref.get()` 才调 loader ⇒ 取件时机 = 旧样板的
      「属性访问时解析」逐字相同（EAGER 窗口安全）。
    * `warm` 给定时是 loader 的**前置副作用**（先 warm 再 import），逐字保留 `DB` 的既有行为。
    * 每个句柄**各自**登记一份 `Wire`：`Wire.lazy` 是「一个名字一种来源」，而同名句柄会被
      多个消费文件各自持有（`content.index` / `content.drops` 各 5 处），共用一个 `Wire`
      会当场 `ValueError` —— 独立登记 = 各句柄互不干扰，且都走同一条 wire 取件语义。
    """
    def _load():
        if warm is not None:
            warm()
        return importlib.import_module(name)
    return Wire().lazy(name, _load)


#: 包内 `db` 句柄（旧宿主 `db` 模块句柄的包内等价物）
DB = PkgModule("content.persistence", warm=_warm_host_store)
#: 存档层注入面（旧宿主 `store.connection` 属性口的包内等价物）
HANDLES = PkgModule("content.persistence.handles")
#: 存档层 world 域（旧宿主 `store.world` 属性口的包内等价物）
WORLD = PkgModule("content.persistence.world")
#: 存档层 inventory 域（旧宿主 `store.inventory` 属性口的包内等价物）
INVENTORY = PkgModule("content.persistence.inventory")
#: 存档层 social 域（旧宿主 `store.social` 属性口的包内等价物）
SOCIAL = PkgModule("content.persistence.social")
