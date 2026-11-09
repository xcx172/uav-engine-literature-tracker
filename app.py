"""Streamlit dashboard for the aviation two-stroke engine literature tracker.

Demo mode is fully offline and needs no API key. Online mode calls OpenAlex and
DeepSeek through :func:`src.refresh.run_refresh`; keys are read only in the
backend from the local ``.env``.
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from src import store
from src.config import Settings
from src.refresh import run_refresh

ROOT = Path(__file__).resolve().parent
DEMO_FILE = ROOT / "data" / "demo_papers.json"

CATEGORY_LABELS = {
    "direct": "直接相关",
    "near_aircraft": "近邻·航空活塞",
    "near_two_stroke": "近邻·二冲程",
    "excluded": "排除",
    "unclassified": "未分类",
}
CODE_LABELS = {"Yes": "Yes", "No": "No", None: "未确认"}


@st.cache_data(show_spinner=False)
def load_demo() -> list[dict]:
    with DEMO_FILE.open(encoding="utf-8") as handle:
        return json.load(handle)


def row_to_item(row) -> dict:
    item = dict(row)
    for key, source in (("methods", "methods_json"), ("datasets", "datasets_json")):
        try:
            item[key] = json.loads(item.get(source) or "[]")
        except ValueError:
            item[key] = []
    item["synthetic"] = False
    return item


def matches(item: dict, keyword: str, code_filter: str) -> bool:
    if keyword:
        haystack = " ".join(
            str(item.get(key) or "")
            for key in ("title", "abstract", "contribution_zh", "code_evidence")
        )
        haystack += " " + " ".join(item.get("methods") or []) + " " + " ".join(item.get("datasets") or [])
        if keyword.lower() not in haystack.lower():
            return False
    if code_filter != "全部":
        current = item.get("code_open") or "未确认"
        if current != code_filter:
            return False
    return True


def render_card(item: dict) -> None:
    with st.container(border=True):
        st.markdown(f"**{item.get('title', '（无标题）')}**")
        published = item.get("publication_date") or "日期未知"
        label = CATEGORY_LABELS.get(item.get("category", ""), "未分类")
        st.caption(f"{published} · {label}")
        if item.get("contribution_zh"):
            st.write(item["contribution_zh"])
        if item.get("methods"):
            st.caption("方法：" + "、".join(item["methods"]))
        if item.get("datasets"):
            st.caption("数据集：" + "、".join(item["datasets"]))
        code = item.get("code_open")
        st.write(f"代码开源：**{CODE_LABELS.get(code, '未确认')}**")
        if item.get("code_evidence"):
            st.caption("证据：" + item["code_evidence"])
        link = item.get("doi_url") or item.get("landing_url") or item.get("openalex_url")
        if link:
            st.markdown(f"[原文链接]({link})")
        else:
            st.caption("无可用链接")


def metric_row(items: list[dict], missing: int = 0, date_unknown: int = 0) -> None:
    counts = {"direct": 0, "near_aircraft": 0, "near_two_stroke": 0}
    for item in items:
        if item.get("category") in counts:
            counts[item["category"]] += 1
    columns = st.columns(5)
    columns[0].metric("直接相关", counts["direct"])
    columns[1].metric("近邻·航空活塞", counts["near_aircraft"])
    columns[2].metric("近邻·二冲程", counts["near_two_stroke"])
    columns[3].metric("摘要缺失", missing)
    columns[4].metric("日期未知", date_unknown)


def main() -> None:
    st.set_page_config(page_title="航空发动机转速控制文献追踪", layout="wide")
    st.title("航空二冲程活塞发动机转速控制文献追踪看板")

    with st.sidebar:
        st.header("控制面板")
        mode = st.radio("模式", ["演示模式", "在线模式"], index=0)
        days = st.number_input("时间窗口 X（天）", min_value=1, max_value=3650, value=365, step=1)
        keyword = st.text_input("关键词", placeholder="标题 / 摘要 / 方法 / 数据集")
        code_filter = st.selectbox("代码开源状态", ["全部", "Yes", "No", "未确认"])
        if mode == "在线模式":
            update = st.button("在线更新", type="primary", use_container_width=True)
        else:
            update = False
        st.caption("真实 Key 只在本机 `.env` 配置；演示模式不发起任何请求。")

    if mode == "演示模式":
        st.info("当前为合成演示数据，非真实检索结果。")
        items = load_demo()
        metric_row(items)
        filtered = [item for item in items if matches(item, keyword, code_filter)]
        st.caption(f"共 {len(items)} 条合成示例，当前筛选 {len(filtered)} 条。")
        if not filtered:
            st.warning("当前筛选条件下没有记录，请调整关键词或开源状态。")
        for item in filtered:
            render_card(item)
        return

    settings = Settings.load(ROOT)
    missing = settings.validate(online=True)
    if missing:
        st.warning(
            "缺少配置："
            + "、".join(f"`{name}`" for name in missing)
            + "。请在本机项目根目录的 `.env` 中填写；当前不会发起任何在线请求。"
        )
        st.caption("可先切换到演示模式查看合成示例。")
        return

    result = st.session_state.get("last_result")
    if update:
        with st.spinner("正在检索与提取，请稍候…"):
            result = run_refresh(settings, days=int(days), max_summaries=20)
        st.session_state["last_result"] = result

    if result is None:
        st.info("在线模式已就绪。设置 X 后点击「在线更新」。")
        return

    if result.status == "ok":
        relevant = result.direct_count + result.near_aircraft_count + result.near_two_stroke_count
        if relevant == 0:
            st.info(
                f"本次检索无命中：{result.queries_ok}/3 组查询成功，"
                f"直接相关与两类近邻均为 0（区间 {result.window.start_iso} ~ {result.window.end_iso}）。"
            )
        else:
            st.success(
                f"更新完成：命中 {result.hit_count} 篇，队列 {result.queue_count} 篇，"
                f"提取 {result.extracted_count} 篇。"
            )
    elif result.status == "partial":
        st.warning(
            f"结果不完整：{result.queries_ok}/3 组查询成功，"
            f"失败 {result.failed_count} 篇。下方为已取得的结果。"
        )
    else:
        st.error("更新失败。下方展示历史缓存（如有）。")

    db_path = Path(settings.db_path)
    if db_path.exists():
        conn = store.init_db(db_path)
        latest, current, history = store.current_and_history(conn)
        last_success = store.get_meta(conn, "last_success_at")
        current_items = [row_to_item(row) for row in current]
        metric_row(current_items, result.missing_abstract_count, result.date_unknown_count)
        if last_success:
            st.caption(f"最后成功时间：{last_success}")
        st.subheader("本次结果")
        filtered = [item for item in current_items if matches(item, keyword, code_filter)]
        if not filtered:
            st.warning("当前筛选条件下没有本次结果。")
        for item in filtered:
            render_card(item)
        if history:
            with st.expander(f"历史缓存（{len(history)} 条，来自更早的成功运行）"):
                st.caption("以下为历史缓存，不计入本次命中与分类计数。")
                history_items = [row_to_item(row) for row in history]
                filtered_history = [item for item in history_items if matches(item, keyword, code_filter)]
                for item in filtered_history:
                    render_card(item)


main()
