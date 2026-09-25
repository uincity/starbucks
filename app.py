"""
스타벅스 전국 매장 시계열 데이터 및 상권 모멘텀 분석 Streamlit 대시보드.
실행 방법: streamlit run app.py
"""

import math
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# 페이지 기본 설정
st.set_page_config(
    page_title="스타벅스 상권 모멘텀 대시보드",
    page_icon="☕",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA_DIR = Path("data/processed")
REPORTS_DIR = Path("reports")


@st.cache_data
def load_all_data():
    hist_file = DATA_DIR / "store_history.parquet"
    monthly_file = DATA_DIR / "area_monthly_metrics.parquet"
    rank_file = DATA_DIR / "area_momentum_rank.parquet"
    audit_file = REPORTS_DIR / "match_audit.csv"

    history_df = pd.read_parquet(hist_file) if hist_file.exists() else pd.DataFrame()
    monthly_df = pd.read_parquet(monthly_file) if monthly_file.exists() else pd.DataFrame()
    rank_df = pd.read_parquet(rank_file) if rank_file.exists() else pd.DataFrame()
    audit_df = pd.read_csv(audit_file) if audit_file.exists() else pd.DataFrame()

    return history_df, monthly_df, rank_df, audit_df


history_df, monthly_df, rank_df, audit_df = load_all_data()

# 사이드바 네비게이션
st.sidebar.title("☕ 스타벅스 상권 분석")
st.sidebar.caption("시계열 데이터 기반 지역 상권 모멘텀 추적 시스템")

menu = st.sidebar.radio(
    "메뉴 선택",
    [
        "1. 전국 Overview",
        "2. 상권 Momentum 순위 & 4분면",
        "3. 지역 심층 분석 (Drill-down)",
        "4. 신규·폐점 공간 지도",
        "5. 개별 매장 History 검색",
        "6. 데이터 품질 및 Audit",
    ],
)

st.sidebar.markdown("---")
st.sidebar.info(
    "💡 **분석 원칙**\n"
    "스타벅스 출점을 상권 성장의 직접적 인과로 단정하지 않고, "
    "상권 규모·소비력·유동인구 변화를 보여주는 **보조 모멘텀 신호**로 활용합니다."
)

if history_df.empty or rank_df.empty:
    st.error("데이터 파일이 준비되지 않았습니다. 파이프라인을 먼저 실행하세요.")
    st.stop()

# -------------------------------------------------------------
# 메뉴 1: 전국 Overview
# -------------------------------------------------------------
if menu == "1. 전국 Overview":
    st.title("📊 전국 스타벅스 인프라 현황 & 종합 KPI")
    st.markdown("전국 스타벅스 매장의 현재 분포와 최근 12개월간의 개폐점 순변화를 조망합니다.")

    # KPI 지표 카드
    curr_stores = (history_df["current_status"] == "OPERATING").sum()
    dt_stores = (history_df["is_dt"] & (history_df["current_status"] == "OPERATING")).sum()
    res_stores = (history_df["is_reserve"] & (history_df["current_status"] == "OPERATING")).sum()

    tot_12m_opened = rank_df["opened_12m"].sum()
    tot_12m_closed = rank_df["closed_12m"].sum()
    tot_12m_net = tot_12m_opened - tot_12m_closed

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("전국 운영 매장 수", f"{curr_stores:,}개")
    col2.metric("최근 12개월 신규", f"+{tot_12m_opened:,}개")
    col3.metric("최근 12개월 폐점", f"-{tot_12m_closed:,}개")
    col4.metric("최근 12개월 순증가", f"{tot_12m_net:+,}개", delta=f"{tot_12m_net} net")
    col5.metric("DT (드라이브스루)", f"{dt_stores}개", f"{dt_stores/curr_stores*100:.1f}%")
    col6.metric("Reserve (리저브)", f"{res_stores}개", f"{res_stores/curr_stores*100:.1f}%")

    # 부산광역시 하이라이트 배너
    busan_op = ((history_df["sido"] == "부산광역시") & (history_df["current_status"] == "OPERATING")).sum()
    busan_dt_cnt = ((history_df["sido"] == "부산광역시") & (history_df["current_status"] == "OPERATING") & history_df["is_dt"]).sum()
    busan_res_cnt = ((history_df["sido"] == "부산광역시") & (history_df["current_status"] == "OPERATING") & history_df["is_reserve"]).sum()
    busan_rank = rank_df[rank_df["sido"] == "부산광역시"]
    busan_net_12m = busan_rank["net_change_12m"].sum() if not busan_rank.empty else 0
    st.info(
        f"📍 **[핵심 거점 바로보기: 부산광역시]** 현재 총 **{busan_op}개** 매장 운영 중 "
        f"(최근 12개월 순증감 **{busan_net_12m:+d}개** · DT 매장 **{busan_dt_cnt}개** · 리저브 **{busan_res_cnt}개**)"
    )

    st.markdown("---")

    col_chart1, col_chart2 = st.columns([3, 2])

    with col_chart1:
        st.subheader("📈 전국 월별 누적 매장 수 추이 (2021 ~ 현재)")
        monthly_nat = monthly_df.groupby("year_month").agg(
            stores_end=("stores_end", "sum"),
            opened=("opened", "sum"),
            closed=("closed", "sum"),
            net_change=("net_change", "sum"),
        ).reset_index()

        fig_line = px.line(
            monthly_nat,
            x="year_month",
            y="stores_end",
            markers=True,
            title="전국 스타벅스 운영 매장 수 시계열 추이",
            labels={"year_month": "연월", "stores_end": "총 매장 수"},
            template="plotly_white",
        )
        fig_line.update_traces(line_color="#006241", line_width=3)
        st.plotly_chart(fig_line, use_container_width=True)

    with col_chart2:
        st.subheader("🗺️ 시도별 매장 수 분포")
        sido_counts = history_df[history_df["current_status"] == "OPERATING"]["sido"].value_counts().reset_index()
        sido_counts.columns = ["시도", "매장수"]
        fig_bar = px.bar(
            sido_counts.head(10),
            x="매장수",
            y="시도",
            orientation="h",
            color="매장수",
            color_continuous_scale="Greens",
            template="plotly_white",
        )
        fig_bar.update_layout(yaxis={"autorange": "reversed"})
        st.plotly_chart(fig_bar, use_container_width=True)

# -------------------------------------------------------------
# 메뉴 2: 상권 Momentum 순위 & 4분면
# -------------------------------------------------------------
elif menu == "2. 상권 Momentum 순위 & 4분면":
    st.title("🚀 지역별 상권 모멘텀 순위 및 4분면 분석")
    st.markdown(
        "단순 현재 매장 수가 아니라 **최근 12개월 순증가폭**과 **직전 12개월 대비 가속도**를 결합한 "
        "**SB Commercial Momentum Score**를 기반으로 지역 상권의 확장 속도를 비교합니다."
    )

    # 필터
    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
    with col_f1:
        sido_opts = sorted(rank_df["sido"].unique())
        default_sidos = ["부산광역시"] if "부산광역시" in sido_opts else []
        sido_filter = st.multiselect("시도 필터", options=sido_opts, default=default_sidos)
    with col_f2:
        status_filter = st.multiselect("모멘텀 상태 필터", options=sorted(rank_df["momentum_status"].unique()), default=[])
    with col_f3:
        type_filter = st.selectbox("매장 유형/특성 필터", options=["전체", "리저브(Reserve) 보유 지역", "DT(드라이브스루) 50% 이상"])
    with col_f4:
        min_stores = st.slider("최소 매장 수 필터", min_value=1, max_value=50, value=2)

    filtered_rank = rank_df[rank_df["store_count_current"] >= min_stores].copy()
    if sido_filter:
        filtered_rank = filtered_rank[filtered_rank["sido"].isin(sido_filter)]
    if status_filter:
        filtered_rank = filtered_rank[filtered_rank["momentum_status"].isin(status_filter)]
    if type_filter == "리저브(Reserve) 보유 지역":
        filtered_rank = filtered_rank[filtered_rank["reserve_count"] > 0]
    elif type_filter == "DT(드라이브스루) 50% 이상":
        filtered_rank = filtered_rank[filtered_rank["dt_share"] >= 50.0]

    # 4분면 매트릭스 산점도
    st.subheader("🎯 상권 변화 4분면 매트릭스 (직전 12M vs 최근 12M 순증감)")
    st.caption("1사분면(우상단): 가속 성장 | 2사분면(좌상단): 신규 반등/급가속 | 4사분면(우하단): 성장 둔화")

    fig_quad = px.scatter(
        filtered_rank,
        x="net_change_prev_12m",
        y="net_change_12m",
        color="momentum_status",
        size="store_count_current",
        hover_name="area_name",
        hover_data=["store_count_current", "opening_acceleration", "sb_momentum_score"],
        labels={
            "net_change_prev_12m": "직전 12개월 순증감 (Net Change Prev 12M)",
            "net_change_12m": "최근 12개월 순증감 (Net Change Recent 12M)",
            "momentum_status": "모멘텀 상태",
        },
        template="plotly_white",
    )
    # 기준선 (0,0) 및 대각선(y=x: 가속/감속 분기)
    fig_quad.add_hline(y=0, line_dash="dash", line_color="gray")
    fig_quad.add_vline(x=0, line_dash="dash", line_color="gray")
    st.plotly_chart(fig_quad, use_container_width=True)

    # 랭킹 테이블
    st.subheader("📋 상권 모멘텀 종합 랭킹 테이블")
    display_cols = [
        "momentum_rank", "area_name", "store_count_current", "opened_12m", "closed_12m",
        "net_change_12m", "net_change_prev_12m", "opening_acceleration", "growth_12m",
        "dt_share", "sb_momentum_score", "momentum_status"
    ]
    st.dataframe(
        filtered_rank[display_cols].rename(columns={
            "momentum_rank": "순위",
            "area_name": "지역명",
            "store_count_current": "현재매장",
            "opened_12m": "12M신규",
            "closed_12m": "12M폐점",
            "net_change_12m": "12M순증감",
            "net_change_prev_12m": "직전12M순증감",
            "opening_acceleration": "출점가속도",
            "growth_12m": "증가율(%)",
            "dt_share": "DT비율(%)",
            "sb_momentum_score": "SB모멘텀스코어",
            "momentum_status": "모멘텀상태",
        }),
        use_container_width=True,
    )

# -------------------------------------------------------------
# 메뉴 3: 지역 심층 분석 (Drill-down)
# -------------------------------------------------------------
elif menu == "3. 지역 심층 분석 (Drill-down)":
    st.title("🔍 지역 심층 드릴다운 (Drill-down)")
    st.markdown("선택한 시도의 시군구별 매장 수 순위를 확인하고, **막대를 클릭하여 하단 상세 분석을 실시간 연동**할 수 있습니다.")

    # 1. 시도 선택 (기본값: 부산광역시)
    sido_list = sorted(rank_df["sido"].unique())
    default_sido_idx = sido_list.index("부산광역시") if "부산광역시" in sido_list else 0
    selected_sido = st.selectbox("시도 선택", options=sido_list, index=default_sido_idx)

    # 2. 해당 시도의 시군구 데이터 필터링 (매장수 0 초과만 포함, 매장수 상위 순 정렬)
    sido_rank_df = rank_df[(rank_df["sido"] == selected_sido) & (rank_df["store_count_current"] > 0)].copy()
    sido_rank_df = sido_rank_df.sort_values("store_count_current", ascending=False).reset_index(drop=True)

    if sido_rank_df.empty:
        st.warning(f"선택하신 {selected_sido}에는 현재 운영 중인 스타벅스 매장이 없습니다.")
    else:
        ALL_OPTION = f"전체 ({selected_sido} 전체)"
        sigungu_raw_options = sido_rank_df["sigungu"].tolist()
        sigungu_options = [ALL_OPTION] + sigungu_raw_options

        # 세션 상태로 현재 선택된 시군구 추적 (기본값: 시도 전체)
        state_key = f"drill_sigungu_{selected_sido}"
        if state_key not in st.session_state or st.session_state[state_key] not in sigungu_options:
            st.session_state[state_key] = ALL_OPTION

        current_selected = st.session_state[state_key]

        # 3. 상단 시군구별 매장 수 막대그래프 (특정 시군구 선택 시 강조 색상 부여)
        sido_rank_df["bar_color"] = sido_rank_df["sigungu"].apply(
            lambda x: "#e67e22" if x == current_selected else "#006241"
        )

        fig_bar = px.bar(
            sido_rank_df,
            x="sigungu",
            y="store_count_current",
            text="store_count_current",
            title=f"📊 {selected_sido} 시군구별 스타벅스 매장 수 (상위 정렬 · 막대 클릭 시 하단 개별 연동)",
            labels={"sigungu": "시군구", "store_count_current": "현재 매장 수 (개)"},
            template="plotly_white",
        )
        fig_bar.update_traces(
            marker_color=sido_rank_df["bar_color"],
            textposition="outside",
            textfont_size=12,
            cliponaxis=False,
        )
        fig_bar.update_layout(
            xaxis_tickangle=-45 if len(sigungu_raw_options) > 10 else 0,
            xaxis_title="시군구 (막대 클릭 시 개별 시군구로 전환)",
            yaxis_title="매장 수",
            hovermode="closest",
            margin=dict(t=50, b=80, l=40, r=40),
        )

        # 막대 클릭 이벤트 감지
        chart_event = st.plotly_chart(
            fig_bar,
            on_select="rerun",
            selection_mode="points",
            key=f"sigungu_click_chart_{selected_sido}",
        )

        # 클릭 시 세션 상태 갱신 (막대 클릭 시 해당 개별 시군구로 전환)
        if chart_event and "selection" in chart_event and chart_event["selection"].get("points"):
            clicked_points = chart_event["selection"]["points"]
            if clicked_points:
                clicked_sigungu = clicked_points[0].get("x")
                if clicked_sigungu and clicked_sigungu in sigungu_raw_options and clicked_sigungu != current_selected:
                    st.session_state[state_key] = clicked_sigungu
                    st.rerun()

        # 4. 시군구 선택 셀렉트박스 ('전체' 포함 및 양방향 동기화)
        sel_idx = sigungu_options.index(st.session_state[state_key]) if st.session_state[state_key] in sigungu_options else 0
        chosen_sigungu = st.selectbox(
            "선택된 시군구 (그래프의 막대를 클릭하거나 아래 목록에서 '전체' 또는 특정 시군구 선택)",
            options=sigungu_options,
            index=sel_idx,
            key=f"selectbox_sigungu_{selected_sido}",
        )

        if chosen_sigungu != st.session_state[state_key]:
            st.session_state[state_key] = chosen_sigungu
            st.rerun()

        selected_sigungu = st.session_state[state_key]

        # 5. 하단 상세 프로파일 및 시계열 분석 연동
        st.markdown("---")

        if selected_sigungu == ALL_OPTION:
            # 5-A. [시도 전체] 선택 시
            total_curr = int(sido_rank_df["store_count_current"].sum())
            total_net_12m = int(sido_rank_df["net_change_12m"].sum())
            total_accel = int(sido_rank_df["opening_acceleration"].sum())
            total_dt = int(sido_rank_df["dt_count"].sum())
            total_reserve = int(sido_rank_df["reserve_count"].sum())
            dt_share_pct = round(total_dt / total_curr * 100, 1) if total_curr > 0 else 0.0
            reserve_share_pct = round(total_reserve / total_curr * 100, 1) if total_curr > 0 else 0.0

            st.subheader(f"📍 {selected_sido} 전체 종합 상권 프로파일")

            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("시도 전체 운영 매장", f"{total_curr:,}개")
            m2.metric("최근 12M 순증감", f"{total_net_12m:+d}개")
            m3.metric("시도 출점 가속도", f"{total_accel:+d}개")
            m4.metric("DT 점유율", f"{dt_share_pct}% ({total_dt}개)")
            m5.metric("Reserve 점유율", f"{reserve_share_pct}% ({total_reserve}개)")

            # 시도 전체 월별 시계열 라인 차트
            sido_monthly = monthly_df[monthly_df["sido"] == selected_sido].groupby("year_month").agg(
                stores_end=("stores_end", "sum")
            ).reset_index().sort_values("year_month")

            if not sido_monthly.empty:
                fig_sub = px.line(
                    sido_monthly,
                    x="year_month",
                    y="stores_end",
                    markers=True,
                    title=f"📈 {selected_sido} 전체 매장 수 월별 시계열 변화 (2021 ~ 현재)",
                    labels={"year_month": "연월", "stores_end": "매장 수"},
                    template="plotly_white",
                )
                fig_sub.update_traces(line_color="#006241", line_width=2.5)
                st.plotly_chart(fig_sub, use_container_width=True)

            # 시도 전체 매장 상세 목록 테이블
            all_sido_stores = history_df[history_df["sido"] == selected_sido].copy()
            # 운영 매장 우선, 그 다음 개점일 역순 정렬
            all_sido_stores = all_sido_stores.sort_values(
                by=["current_status", "opened_date_best"],
                ascending=[True, False]
            ).reset_index(drop=True)

            operating_count = (all_sido_stores["current_status"] == "OPERATING").sum()
            closed_count = (all_sido_stores["current_status"] == "CLOSED").sum()

            st.subheader(f"🏪 {selected_sido} 전체 매장 목록 (운영 {operating_count:,}개 / 과거 폐점 {closed_count:,}개)")
            st.dataframe(
                all_sido_stores[[
                    "sigungu", "store_name", "store_type", "opened_date_best", "current_status",
                    "closed_date_best", "address_road", "is_dt", "is_reserve"
                ]].rename(columns={
                    "sigungu": "시군구",
                    "store_name": "매장명",
                    "store_type": "유형",
                    "opened_date_best": "개점일(추정)",
                    "current_status": "운영상태",
                    "closed_date_best": "폐점일",
                    "address_road": "도로명주소",
                    "is_dt": "DT여부",
                    "is_reserve": "리저브",
                }),
                use_container_width=True,
                height=450,
            )
        else:
            # 5-B. [개별 시군구] 선택 시
            area_key = f"{selected_sido} {selected_sigungu}"
            area_info = sido_rank_df[sido_rank_df["area_name"] == area_key]

            if not area_info.empty:
                info = area_info.iloc[0]
                st.subheader(f"📍 {area_key} 상세 상권 프로파일")

                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("현재 매장 수", f"{info['store_count_current']}개")
                m2.metric("최근 12M 순증감", f"{info['net_change_12m']:+d}개")
                m3.metric("출점 가속도", f"{info['opening_acceleration']:+d}개")
                m4.metric("DT 점유율", f"{info['dt_share']}% ({info['dt_count']}개)")
                m5.metric("SB 모멘텀 스코어", f"{info['sb_momentum_score']}점", f"상태: {info['momentum_status']}")

                # 월별 시계열 라인 차트
                sub_monthly = monthly_df[monthly_df["area_name"] == area_key].sort_values("year_month")
                if not sub_monthly.empty:
                    fig_sub = px.line(
                        sub_monthly,
                        x="year_month",
                        y="stores_end",
                        markers=True,
                        title=f"📈 {area_key} 매장 수 월별 시계열 변화 (2021 ~ 현재)",
                        labels={"year_month": "연월", "stores_end": "매장 수"},
                        template="plotly_white",
                    )
                    fig_sub.update_traces(line_color="#006241", line_width=2.5)
                    st.plotly_chart(fig_sub, use_container_width=True)

                # 해당 지역 매장 목록 테이블
                area_stores = history_df[(history_df["sido"] == selected_sido) & (history_df["sigungu"] == selected_sigungu)].copy()
                area_stores = area_stores.sort_values(
                    by=["current_status", "opened_date_best"],
                    ascending=[True, False]
                ).reset_index(drop=True)

                st.subheader(f"🏪 {area_key} 매장 상세 목록 (총 {len(area_stores)}건)")
                st.dataframe(
                    area_stores[[
                        "store_name", "store_type", "opened_date_best", "current_status",
                        "closed_date_best", "address_road", "is_dt", "is_reserve"
                    ]].rename(columns={
                        "store_name": "매장명",
                        "store_type": "유형",
                        "opened_date_best": "개점일(추정)",
                        "current_status": "운영상태",
                        "closed_date_best": "폐점일",
                        "address_road": "도로명주소",
                        "is_dt": "DT여부",
                        "is_reserve": "리저브",
                    }),
                    use_container_width=True,
                    height=350,
                )

# -------------------------------------------------------------
# 메뉴 4: 신규·폐점 공간 지도
# -------------------------------------------------------------
elif menu == "4. 신규·폐점 공간 지도":
    st.title("🗺️ 전국 신규·기존·폐점 매장 공간 인터랙티브 맵")
    st.markdown("마우스 휠 스크롤로 자유롭게 확대·축소할 수 있으며, 광역시도를 선택하면 해당 지역으로 지도가 자동 포커싱됩니다.")

    # 17개 광역시도 중심 좌표 및 최적 줌 레벨 사전
    SIDO_GEO_PRESETS = {
        "전국 (전체)": {"lat": 36.3, "lon": 127.8, "zoom": 6.8},
        "서울특별시": {"lat": 37.5665, "lon": 126.9780, "zoom": 11.2},
        "부산광역시": {"lat": 35.1796, "lon": 129.0756, "zoom": 11.0},
        "대구광역시": {"lat": 35.8714, "lon": 128.6014, "zoom": 11.0},
        "인천광역시": {"lat": 37.4563, "lon": 126.7052, "zoom": 10.5},
        "광주광역시": {"lat": 35.1595, "lon": 126.8526, "zoom": 11.5},
        "대전광역시": {"lat": 36.3504, "lon": 127.3845, "zoom": 11.5},
        "울산광역시": {"lat": 35.5384, "lon": 129.3114, "zoom": 11.2},
        "세종특별자치시": {"lat": 36.4800, "lon": 127.2890, "zoom": 11.8},
        "경기도": {"lat": 37.4138, "lon": 127.5183, "zoom": 9.2},
        "강원특별자치도": {"lat": 37.8228, "lon": 128.1555, "zoom": 8.6},
        "충청북도": {"lat": 36.8000, "lon": 127.7000, "zoom": 8.8},
        "충청남도": {"lat": 36.5184, "lon": 126.8000, "zoom": 8.8},
        "전북특별자치도": {"lat": 35.7175, "lon": 127.1530, "zoom": 8.8},
        "전라남도": {"lat": 34.8679, "lon": 126.9910, "zoom": 8.6},
        "경상북도": {"lat": 36.4919, "lon": 128.8889, "zoom": 8.5},
        "경상남도": {"lat": 35.4606, "lon": 128.2132, "zoom": 8.8},
        "제주특별자치도": {"lat": 33.3846, "lon": 126.5535, "zoom": 9.8},
    }

    # 상단 컨트롤 필터 (광역시도 포커싱 + 신규 관측 기간 + 필터 옵션)
    col_map1, col_map2, col_map3 = st.columns([2, 2, 2])
    with col_map1:
        sido_choices = list(SIDO_GEO_PRESETS.keys())
        default_map_idx = sido_choices.index("부산광역시") if "부산광역시" in sido_choices else 0
        selected_focus_sido = st.selectbox("🎯 광역시도 선택 (지도 포커싱)", options=sido_choices, index=default_map_idx)
    with col_map2:
        period_filter = st.selectbox(
            "⏱️ 신규 매장 관측 기간",
            ["최근 12개월 (2025-10 ~ 현재)", "최근 24개월 (2024-10 ~ 현재)", "전체 기간"],
            index=0,
        )
    with col_map3:
        only_selected_sido = st.checkbox("선택한 시도 매장만 보기", value=True)

    now_dt = pd.to_datetime("2026-09-25")
    if "12개월" in period_filter:
        cutoff_dt = now_dt - pd.DateOffset(months=12)
    elif "24개월" in period_filter:
        cutoff_dt = now_dt - pd.DateOffset(months=24)
    else:
        cutoff_dt = pd.to_datetime("1990-01-01")

    map_df = history_df[history_df["latitude"].notna() & history_df["longitude"].notna()].copy()
    map_df["opened_dt"] = pd.to_datetime(map_df["opened_date_best"])

    # 시도 필터링 적용 (토글 체크 시)
    if only_selected_sido and selected_focus_sido != "전국 (전체)":
        map_df = map_df[map_df["sido"] == selected_focus_sido].copy()

    # 매장 상태 태그 및 마커 크기 정의 (시각적 구분 강화)
    def assign_display_props(row):
        if row["current_status"] == "CLOSED":
            return "폐점 매장 (Closed)", 12
        elif row["opened_dt"] >= cutoff_dt:
            return "최근 신규 개점 (New Open)", 15
        elif row["is_reserve"] and row["is_dt"]:
            return "리저브 DT (Reserve DT)", 16
        elif row["is_reserve"]:
            return "리저브 (Reserve)", 15
        elif row["is_dt"]:
            return "드라이브스루 (DT)", 13
        else:
            return "일반 매장 (General)", 11

    props = map_df.apply(assign_display_props, axis=1)
    map_df["display_type"] = [p[0] for p in props]
    map_df["marker_size"] = [p[1] for p in props]

    # 매장 표시 유형 (display_type) 다중 선택 필터
    ALL_DISPLAY_TYPES = [
        "최근 신규 개점 (New Open)",
        "리저브 (Reserve)",
        "리저브 DT (Reserve DT)",
        "드라이브스루 (DT)",
        "일반 매장 (General)",
        "폐점 매장 (Closed)",
    ]

    selected_display_types = st.multiselect(
        "🏷️ 매장 표시 유형 선택 (중복 선택 가능 · 최근 신규매장만 선택 시 신규점만 표시)",
        options=ALL_DISPLAY_TYPES,
        default=ALL_DISPLAY_TYPES,
    )

    # 선택된 유형으로 필터링 (미선택 시 전체 유지)
    if selected_display_types:
        map_df = map_df[map_df["display_type"].isin(selected_display_types)].copy()

    # 표시 매장 수 현황 요약
    if not map_df.empty:
        summary_tags = [
            f"**{t}**: {(map_df['display_type'] == t).sum()}개"
            for t in ALL_DISPLAY_TYPES
            if (map_df["display_type"] == t).sum() > 0
        ]
        st.markdown(f"📌 **지도 표시 매장 총 {len(map_df):,}개** ({' · '.join(summary_tags)})")
    else:
        st.warning("선택하신 매장 유형 조건에 해당하는 매장이 없습니다.")

    # 중심 좌표 및 줌 레벨 결정
    geo_target = SIDO_GEO_PRESETS.get(selected_focus_sido, SIDO_GEO_PRESETS["전국 (전체)"])
    center_lat = geo_target["lat"]
    center_lon = geo_target["lon"]
    map_zoom = geo_target["zoom"]

    if not map_df.empty:
        fig_map = px.scatter_mapbox(
            map_df,
            lat="latitude",
            lon="longitude",
            color="display_type",
            size="marker_size",
            size_max=16,
            hover_name="store_name",
            hover_data={
                "sido": True,
                "sigungu": True,
                "store_type": True,
                "opened_date_best": True,
                "current_status": True,
                "address_road": True,
                "marker_size": False,
                "latitude": False,
                "longitude": False,
            },
            color_discrete_map={
                "최근 신규 개점 (New Open)": "#ff4d4f",
                "리저브 (Reserve)": "#d4af37",
                "리저브 DT (Reserve DT)": "#722ed1",
                "드라이브스루 (DT)": "#1890ff",
                "일반 매장 (General)": "#2d6a4f",
                "폐점 매장 (Closed)": "#666666",
            },
            zoom=map_zoom,
            center={"lat": center_lat, "lon": center_lon},
            mapbox_style="open-street-map",
            height=750,
        )

        # 마커 테두리(White outline) 및 시각적 대비 극대화
        fig_map.update_traces(
            marker=dict(
                opacity=0.9,
                allowoverlap=True,
            )
        )
        fig_map.update_layout(
            margin=dict(t=10, b=10, l=10, r=10),
            legend=dict(
                yanchor="top",
                y=0.98,
                xanchor="left",
                x=0.02,
                bgcolor="rgba(255, 255, 255, 0.9)",
                bordercolor="gray",
                borderwidth=1,
                font=dict(size=12, color="black"),
            ),
        )

        # 마우스 휠 스크롤 줌 활성화 config 적용
        st.plotly_chart(
            fig_map,
            config={
                "scrollZoom": True,
                "displayModeBar": True,
                "modeBarButtonsToRemove": ["lasso2d", "select2d"],
            },
        )

    st.caption("💡 **지도 조작 팁:** 마우스 휠을 스크롤하여 확대/축소할 수 있으며, 마커 위에 마우스를 올리면 상세 주소와 개점일을 확인할 수 있습니다.")

# -------------------------------------------------------------
# 메뉴 5: 개별 매장 History 검색
# -------------------------------------------------------------
elif menu == "5. 개별 매장 History 검색":
    st.title("🔎 개별 스타벅스 매장 생애주기 검색기")
    st.markdown("전국 2,417개 매장(현재 운영 + 과거 폐점)의 개점일, 폐점일, 출처, 신뢰도를 조회합니다.")

    search_kw = st.text_input("매장명 검색 (예: 해운대, 서면, 센텀, 광화문)", value="해운대")

    if search_kw.strip():
        searched = history_df[history_df["store_name"].str.contains(search_kw.strip(), case=False, na=False)]
        st.write(f"검색 결과: 총 **{len(searched)}개** 매장")

        for _, r in searched.head(10).iterrows():
            with st.expander(f"📍 {r['store_name']} ({r['current_status']}) - {r['sido']} {r['sigungu']}"):
                c1, c2 = st.columns(2)
                with c1:
                    st.write(f"**매장 ID:** `{r['store_id']}`")
                    st.write(f"**매장 유형:** {r['store_type']} (DT: {r['is_dt']}, Reserve: {r['is_reserve']})")
                    st.write(f"**개점일(Best):** `{r['opened_date_best']}` (신뢰도: **{r['opened_date_confidence']}**, 출처: {r['opened_date_source']})")
                    if r["current_status"] == "CLOSED":
                        st.write(f"**폐점일(Best):** `{r['closed_date_best']}` (출처: {r['closed_date_source']})")
                with c2:
                    st.write(f"**도로명주소:** {r['address_road']}")
                    st.write(f"**최초 관측일:** `{r['first_seen_date']}`")
                    st.write(f"**최종 관측일:** `{r['last_seen_date']}`")
                    st.write(f"**좌표 (WGS84):** ({r['latitude']}, {r['longitude']})")

# -------------------------------------------------------------
# 메뉴 6: 데이터 품질 및 Audit
# -------------------------------------------------------------
elif menu == "6. 데이터 품질 및 Audit":
    st.title("🛡️ 데이터 정합성 검증 및 매칭 Audit")

    if not audit_df.empty:
        col_q1, col_q2, col_q3 = st.columns(3)
        col_q1.metric("HIGH 신뢰도 매칭", f"{(audit_df['match_grade'] == 'MATCH_HIGH').sum():,}건")
        col_q2.metric("MEDIUM 신뢰도 매칭", f"{(audit_df['match_grade'] == 'MATCH_MEDIUM').sum():,}건")
        col_q3.metric("신규 매칭 후보 (UNMATCHED)", f"{(audit_df['match_grade'] == 'UNMATCHED').sum():,}건")

        st.subheader("매칭 감사 로그 (Match Audit)")
        grade_filter = st.multiselect("매칭 등급 필터", options=audit_df["match_grade"].unique(), default=[])
        if grade_filter:
            st.dataframe(audit_df[audit_df["match_grade"].isin(grade_filter)], use_container_width=True)
        else:
            st.dataframe(audit_df.head(50), use_container_width=True)

    dq_file = REPORTS_DIR / "data_quality_report.md"
    if dq_file.exists():
        st.markdown("---")
        st.subheader("📄 Data Quality Report 전문")
        st.markdown(dq_file.read_text(encoding="utf-8"))
