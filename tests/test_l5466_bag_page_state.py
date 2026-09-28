# -*- coding: utf-8 -*-
"""审计 L5466：背包分页状态写库**不再静默失败**（行为门禁，钉住真修法）

台账判据（`AUDIT_台账.md` L5466，准则 3/4）：
  `content/economy_cmds.py::_bag_view` 里 `try: db.set_event_state("bag_page_…") / except
  Exception: pass` —— 写库型静默：写失败时玩家「上一页/下一页」静默回第 1 页，
  而紧接其后的 `_record_list_state` 照写不误 ⇒ 面板照常渲染、零提示，谎称状态已记录。

本门禁钉**行为**（不是「某行不存在」那种恒真断言）：
  ① 正常写：`_bag_view` 真把 {cat,page} 落进 event_state（读口 :5451 能取回）；
  ② 翻页语义：先看第 1 页 → 『背包 下一页』相对翻到第 2 页（依赖 ① 写进去了）；
  ③ ★ fail-closed：写口抛异常时**必须上抛**，不得静默（这是本批的核心修复）；
  ④ 同族读口仍容错（`except (ValueError, TypeError)` 回落空 dict）——旧档容错是**读**侧的
     正当兜底，本门禁明确它**不该**被顺手改成 fail-hard（防止"收口收过头"）。
"""
import sys, os, json, sqlite3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import C, db, clean_db, Main, FakeEvent, run  # noqa: E402

passed = failed = 0
from _check import bind_check  # noqa: E402  断言助手单源：tests/_check.py

check = bind_check(globals(), "passed", "failed")


def _bag_key(g="g1", u="i1"):
    return f"bag_page_{g}_{u}"


async def _mk_player():
    m = Main(None)
    await run(m.register, FakeEvent("g1", "i1", "注册 战士 格温 男"))
    return m


async def main():
    clean_db()

    # ── ① 正常写：_bag_view 真落 event_state ────────────────────────────────
    m = await _mk_player()
    db.add_item("g1", "i1", "misc_x", {"name": "破旧布条", "type": "材料", "quality": "white", "price": 5}, 1)
    # ★ 夹具要点（v101.27：每页 10 件）：造够 12 件才有第 2 页，否则 `_page_items` 会把
    #   page clamp 回 1，断言②永远测不到「相对翻页」这条路径（首版就是踩了这个坑）。
    for _i in range(11):
        db.add_item("g1", "i1", f"filler_{_i}",
                    {"name": f"填充布条{_i}", "type": "材料", "quality": "white", "price": 1}, 1)
    out = m._bag_view("g1", "i1", "")
    raw = db.get_event_state(_bag_key())
    check("① _bag_view 真把分页状态写进 event_state", raw is not None, f"raw={raw!r}")
    if raw:
        st = json.loads(raw)
        check("① 写入内容 = {cat:'', page:1}", st.get("cat") == "" and st.get("page") == 1, st)
    check("① 面板仍正常渲染（未因去 try 而变空）", "🎒" in out, out[:200])

    # ── ② 相对翻页语义（读口 :5451 依赖 ① 写进去的值）────────────────────
    out2 = m._bag_view("g1", "i1", "下一页")
    st2 = json.loads(db.get_event_state(_bag_key()) or "{}")
    check("② 『背包 下一页』相对翻页后 page 递增", st2.get("page") == 2, st2)

    # ── ③ ★ fail-closed：写口抛异常必须上抛（原为 except Exception: pass）──
    m2 = await _mk_player()
    _orig = db.set_event_state

    def _boom(key, value):
        raise RuntimeError("模拟写库失败")

    db.set_event_state = _boom
    raised = False
    try:
        m2._bag_view("g1", "i1", "")
    except RuntimeError as e:
        raised = ("模拟写库失败" in str(e))
    finally:
        db.set_event_state = _orig
    check("③ 写库失败时异常上抛，不再静默 pass", raised,
          "静默吞掉了 —— L5466 未真正修好")

    # ── ④ 同族读口仍容错：旧档脏值不炸（旧档容错是正当兜底，别收过头）────
    m3 = await _mk_player()
    _o2 = db.set_event_state
    db.set_event_state = lambda k, v: _o2(k, "{ 这不是合法 JSON")
    try:
        out4 = m3._bag_view("g1", "i1", "下一页")   # 读侧 (ValueError, TypeError) 应兜住
        read_ok = isinstance(out4, str) and "🎒" in out4
    except Exception as e:                          # noqa: BLE001
        read_ok = False
        print("读侧未兜住:", type(e).__name__, e)
    finally:
        db.set_event_state = _o2
    check("④ 读口对脏存档仍容错（读侧兜底保留）", read_ok, "读侧被误改成 fail-hard")

    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)


import asyncio
asyncio.run(main())
