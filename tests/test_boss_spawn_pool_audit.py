# -*- coding: utf-8 -*-
"""审计回归：Boss 的 AI 权重 / 连招链引用的技能必须真能解析（不许静默空放）。

背景（2026-09-11 修）：v180 boss 设计的技能/阶段/AI 权重都合进了生产数据，唯独漏了
设计稿明示的「合表要求」——各 Boss 的身份技/常态循环技必须写进 instances.py 的 boss
6 元组技能数组（引擎常态技能池 = spawn 值，phases.add_skills 只在血量阈值后追加）。
漏写的后果是运行期 _skill_index 查不到 → ActCtx.info={} → do_skill 直接 return []：
Boss 静默白耗一回合（AI 权重 17 处 / 连招链 4 处，共 12+3 只怪）。

本测试把 tools/audit_ai_moves_resolvable.py 的三分类口径固化为回归门禁：
  OK-base   开战即持有（spawn 6 元组 skills）
  OK-phase  阶段 add_skills 里（MONSTER_MODS ∪ INSTANCES 副本内联 ＋ 阶段模板）
  DEAD      两处都没有 → 引用不存在的技能（fail）
引用通道 = ai.weights ∪ chains[].seq（两者都经 ActCtx 解析技能 dict）。

跑法：python tests/test_boss_spawn_pool_audit.py
"""
import os
import sys
import importlib.util

# 包仓布局：本文件在 `pkg/tests/`，`dirname(dirname(__file__))` 是**包根**（不是插件根）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

PLUGIN_DIR = _paths.HOST_ROOT      # 宿主插件根（旧语义；`tools/` 在宿主侧）
PKG_ROOT = _paths.PKG_ROOT         # 包根（内容真源）
sys.path.insert(0, PLUGIN_DIR)
sys.path.insert(0, _paths.TESTS_DIR)


def _alias_host_deploy_tree():
    """审计工具按**真仓部署树名**取宿主注入面：`<qqbot>/data/plugins/dragonfall` = 插件根。

    `tools/audit_ai_moves_resolvable.py::_host_inject()` 里 `from data.plugins.dragonfall.host
    import store_factory` 用的是**部署树**名；包仓布局里插件根 = `_paths.HOST_ROOT`，
    故把该名字挂到宿主的 `host` 包上（同源同值；不读真仓、不改审计工具、不动任何断言）。
    """
    import types
    host_pkg = importlib.import_module("host")               # _paths.HOST_ROOT/host
    importlib.import_module("host.store_factory")
    for name in ("data", "data.plugins"):
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules.setdefault(name, mod)
    pkg_alias = types.ModuleType("data.plugins.dragonfall")
    pkg_alias.__path__ = [PLUGIN_DIR]
    sys.modules.setdefault("data.plugins.dragonfall", pkg_alias)
    sys.modules.setdefault("data.plugins.dragonfall.host", host_pkg)
    return host_pkg


_alias_host_deploy_tree()

PASS = 0
FAIL = 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        FAILURES.append(f"{name} {detail}")
        print(f"  ❌ {name} {detail}")


def _load_audit():
    """按路径加载审计工具模块（tools/ 非包）。"""
    p = os.path.join(PLUGIN_DIR, "tools", "audit_ai_moves_resolvable.py")
    spec = importlib.util.spec_from_file_location("_audit_ai_moves", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    A = _load_audit()
    spawns = A.collect_spawns()
    from content.catalog_quests import MONSTER_MODS
    from content.catalog_quests import MONSTER_SKILLS

    # ---- 1. 全量三分类：无 DEAD ----
    dead = []
    n_ai = n_chain = n_refs = 0
    for mid, mod in sorted(MONSTER_MODS.items()):
        refs = A.ai_skill_refs(mod)
        chains = A.chain_refs_of(mid, mod)
        if refs:
            n_ai += 1
        if chains:
            n_chain += 1
        if not refs and not chains:
            continue
        base = spawns.get(mid) or set()
        phs = A.held_skills_of(mid, mod)
        for sk in dict.fromkeys(refs + chains):
            n_refs += 1
            if sk not in MONSTER_SKILLS:
                dead.append((mid, sk, "怪技能表无此 key"))
            elif sk not in base and sk not in phs:
                dead.append((mid, sk, "spawn/阶段均无"))
    check(f"AI/链引用技能全可解析（{n_ai} 只 AI / {n_chain} 只链 / {n_refs} 处）",
          not dead, f"DEAD={dead}")

    # ---- 2. 12 只 v180 boss 的常态身份技确已入池（防回退到旧命名） ----
    EXPECT = [
        ("b_goblin_chief", "ms_lve_duo_h_ling"),
        ("b_fort_ghost", "ms_you_hui_hui_chang"),
        ("b_fort_ghost", "ms_you_xiang_ji"),
        ("b_jack_pirate", "ms_ha_huo_qiang_qi"),
        ("b_king_odric", "ms_zhao_ku_lou_mi"),
        ("b_marcus", "ms_suo_lian_ding_zui"),
        ("b_marcus", "ms_chu_xing_xuan_du"),
        ("b_trial_knight", "ms_dun_ji_shi_lian"),
        ("b_dawn_elf", "ms_yue_guang_xin"),
        ("b_dawn_elf", "ms_yue_hua_lian_shan"),
        ("b_dawn_elf", "ms_gen_xu_chan_rao_x"),
        ("b_frost_lord", "ms_bing_xi_lord"),
        ("b_siren_queen", "ms_mei_huo_ge_blue"),
        ("b_siren_queen", "ms_ju_lang_blue"),
        ("b_siren_queen", "ms_zhao_chu_shou_blue"),
        ("b_aolan", "ms_shui_xi_aolan"),
        ("b_gray_lord", "ms_zhan_chui_lord"),
        ("b_under_dragon", "ms_shi_lin_suan_shi"),
        ("b_under_dragon", "ms_shi_gu_shen_tun"),
        ("b_storm_master", "ms_f6_lei_bao_feng_yan"),
        ("b_storm_master", "ms_f6_feng_bao_feng_yan"),
    ]
    for mid, sk in EXPECT:
        got = spawns.get(mid) or set()
        check(f"{mid} 常态池含 {sk}", sk in got, f"实际={sorted(got)}")

    # ---- 3. 旧命名不再出现在这些 boss 的常态池（一次性换名，禁留兼容壳） ----
    LEGACY = {
        "b_aolan": "ms_shui_xi",
        "b_frost_lord": "ms_bing_xi",
        "b_gray_lord": "ms_zhan_chui",
        "b_marcus": "ms_suo_lian",
        "b_king_odric": "ms_zhao_huan_ku_lou",
        "b_fort_ghost": "ms_ai_hao",
        "b_jack_pirate": "ms_huo_qiang",
        "b_siren_queen": "ms_mei_huo_zhi_ge",
    }
    for mid, old in LEGACY.items():
        got = spawns.get(mid) or set()
        check(f"{mid} 常态池已无旧命名 {old}", old not in got, f"实际={sorted(got)}")

    print(f"\n{'-' * 46}\n通过 {PASS} / 失败 {FAIL}")
    if FAILURES:
        for f in FAILURES:
            print(f"  ❌ {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
