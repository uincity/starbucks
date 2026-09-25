"""
시도, 시군구, H3 그리드 단위의 월별 시계열 집계 및 상권 모멘텀(Commercial Momentum) 지표 생성 모듈.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple

import h3
import numpy as np
import pandas as pd

from src.processing.sido_utils import standardize_sido, ALL_17_SIDOS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def generate_area_monthly_metrics(history_df: pd.DataFrame) -> pd.DataFrame:
    """
    모든 매장의 개점일과 폐점일을 바탕으로 시군구 및 시도 단위의 월별 시계열을 생성합니다.
    """
    # 2021년 1월부터 현재(2026년 9월)까지의 월 목록 생성
    start_date = pd.to_datetime("2021-01-01")
    end_date = pd.to_datetime("2026-09-30")
    months = pd.date_range(start_date, end_date, freq="MS").strftime("%Y-%m").tolist()

    # 분석 대상 지역 목록 (시군구)
    valid_stores = history_df.copy()
    valid_stores["sido"] = valid_stores.apply(
        lambda r: standardize_sido(r["sido"], sigungu_input=r["sigungu"], address_input=r.get("address_road", "")),
        axis=1,
    )
    valid_stores["sigungu"] = valid_stores["sigungu"].fillna("기타")
    valid_stores.loc[valid_stores["sigungu"] == "", "sigungu"] = "기타"
    valid_stores["area_name"] = valid_stores["sido"] + " " + valid_stores["sigungu"]

    # 개점월, 폐점월 계산
    valid_stores["open_ym"] = pd.to_datetime(valid_stores["opened_date_best"]).dt.strftime("%Y-%m")
    valid_stores["close_ym"] = pd.to_datetime(valid_stores["closed_date_best"]).dt.strftime("%Y-%m")

    area_list = valid_stores["area_name"].unique().tolist()
    records = []

    for area in area_list:
        area_df = valid_stores[valid_stores["area_name"] == area]
        running_stores = 0

        # 해당 지역의 첫 개점 이전 매장 수 계산
        pre_existing = area_df[area_df["open_ym"] < months[0]]
        pre_closed = area_df[area_df["close_ym"].notna() & (area_df["close_ym"] < months[0])]
        running_stores = len(pre_existing) - len(pre_closed)
        if running_stores < 0:
            running_stores = 0

        sido_val = area_df["sido"].iloc[0]
        sigungu_val = area_df["sigungu"].iloc[0]

        for ym in months:
            stores_start = running_stores

            # 이번 달 신규 개점 매장 수
            opened = len(area_df[area_df["open_ym"] == ym])
            # 이번 달 폐점 매장 수
            closed = len(area_df[area_df["close_ym"] == ym])
            net_change = opened - closed
            stores_end = stores_start + net_change
            if stores_end < 0:
                stores_end = 0

            records.append({
                "year_month": ym,
                "area_type": "sigungu",
                "area_id": area,
                "area_name": area,
                "sido": sido_val,
                "sigungu": sigungu_val,
                "stores_start": stores_start,
                "opened": opened,
                "closed": closed,
                "net_change": net_change,
                "stores_end": stores_end,
            })
            running_stores = stores_end

    metrics_df = pd.DataFrame(records)
    return metrics_df


def calculate_momentum_scores(monthly_df: pd.DataFrame, history_df: pd.DataFrame, ref_ym: str = "2026-09") -> pd.DataFrame:
    """
    기준월(ref_ym)을 중심으로 최근 12개월(1~12개월 전)과 직전 12개월(13~24개월 전)의
    순증감, 가속도, 폐점압력, 턴오버, SB 모멘텀 스코어를 계산합니다.
    """
    # 월 목록 및 기준 인덱스
    all_months = sorted(monthly_df["year_month"].unique().tolist())
    if ref_ym not in all_months:
        ref_ym = all_months[-1]

    ref_idx = all_months.index(ref_ym)

    # 최근 12개월 (예: 2025-10 ~ 2026-09)
    recent_12m = all_months[max(0, ref_idx - 11) : ref_idx + 1]
    # 직전 12개월 (예: 2024-10 ~ 2025-09)
    prev_12m = all_months[max(0, ref_idx - 23) : max(0, ref_idx - 11)]

    # 12개월 전, 24개월 전 시점
    ym_12m_ago = all_months[max(0, ref_idx - 12)]
    ym_24m_ago = all_months[max(0, ref_idx - 24)]

    logger.info(f"모멘텀 산출 기준월: {ref_ym} (최근 12M: {recent_12m[0]}~{recent_12m[-1]}, 직전 12M: {prev_12m[0]}~{prev_12m[-1]})")

    results = []
    for area_id, group in monthly_df.groupby("area_id"):
        group_indexed = group.set_index("year_month")

        # 매장수 추이
        store_count_current = group_indexed.loc[ref_ym, "stores_end"] if ref_ym in group_indexed.index else 0
        store_count_12m_ago = group_indexed.loc[ym_12m_ago, "stores_end"] if ym_12m_ago in group_indexed.index else 0
        store_count_24m_ago = group_indexed.loc[ym_24m_ago, "stores_end"] if ym_24m_ago in group_indexed.index else 0

        # 최근 12개월 집계
        sub_rec = group[group["year_month"].isin(recent_12m)]
        opened_12m = sub_rec["opened"].sum()
        closed_12m = sub_rec["closed"].sum()
        net_change_12m = opened_12m - closed_12m

        # 직전 12개월 집계
        sub_prev = group[group["year_month"].isin(prev_12m)]
        opened_prev_12m = sub_prev["opened"].sum()
        closed_prev_12m = sub_prev["closed"].sum()
        net_change_prev_12m = opened_prev_12m - closed_prev_12m

        # 출점 가속도 (Acceleration)
        opening_acceleration = net_change_12m - net_change_prev_12m

        # 증가율 계산 및 SMALL_BASE 플래그
        is_small_base = store_count_12m_ago < 3
        if store_count_12m_ago > 0:
            growth_12m = round(net_change_12m / store_count_12m_ago * 100, 2)
            closure_pressure = round(closed_12m / store_count_12m_ago, 4)
            turnover = round((opened_12m + closed_12m) / store_count_12m_ago, 4)
        else:
            growth_12m = 100.0 if net_change_12m > 0 else 0.0
            closure_pressure = 0.0
            turnover = 0.0

        # DT 및 Reserve 비율 (현재 운영 매장 기준)
        sido_val = group["sido"].iloc[0]
        sigungu_val = group["sigungu"].iloc[0]
        area_stores = history_df[(history_df["sido"] == sido_val) & (history_df["sigungu"] == sigungu_val) & (history_df["current_status"] == "OPERATING")]

        tot_curr = len(area_stores)
        dt_count = area_stores["is_dt"].sum()
        reserve_count = area_stores["is_reserve"].sum()
        dt_share = round(dt_count / tot_curr * 100, 1) if tot_curr > 0 else 0.0
        reserve_share = round(reserve_count / tot_curr * 100, 1) if tot_curr > 0 else 0.0

        # 신규 진입 여부 (12개월 전에 0개였으나 현재 1개 이상)
        is_first_entry = bool(store_count_12m_ago == 0 and store_count_current > 0)
        is_dt_expansion = bool(dt_share >= 50.0 and net_change_12m > 0)

        # 상권 모멘텀 상태 분류
        if net_change_12m > 0 and opening_acceleration > 0:
            status = "ACCELERATING"
        elif net_change_12m > 0:
            status = "EXPANDING"
        elif net_change_12m < 0:
            status = "CONTRACTING"
        elif opened_12m >= 2 and closed_12m >= 2:
            status = "HIGH_TURNOVER"
        else:
            status = "STABLE"

        results.append({
            "area_id": area_id,
            "area_name": area_id,
            "sido": sido_val,
            "sigungu": sigungu_val,
            "store_count_current": store_count_current,
            "store_count_12m_ago": store_count_12m_ago,
            "store_count_24m_ago": store_count_24m_ago,
            "opened_12m": opened_12m,
            "closed_12m": closed_12m,
            "net_change_12m": net_change_12m,
            "growth_12m": growth_12m,
            "net_change_prev_12m": net_change_prev_12m,
            "opening_acceleration": opening_acceleration,
            "closure_pressure": closure_pressure,
            "turnover": turnover,
            "dt_count": dt_count,
            "dt_share": dt_share,
            "reserve_count": reserve_count,
            "reserve_share": reserve_share,
            "is_small_base": is_small_base,
            "is_first_entry": is_first_entry,
            "is_dt_expansion": is_dt_expansion,
            "momentum_status": status,
        })

    rank_df = pd.DataFrame(results)

    # -------------------------------------------------------------
    # SB Commercial Momentum Score (0 ~ 100) 산출
    # 35% 최근 12개월 순증감 (percentile rank)
    # 25% 출점 가속도 (percentile rank)
    # 15% 신규 상권 진입 가산점
    # 15% 최근 24개월 지속 성장성
    # 10% 폐점압력 역점수 (1 - percentile rank)
    # -------------------------------------------------------------
    p_net = rank_df["net_change_12m"].rank(pct=True) * 100
    p_acc = rank_df["opening_acceleration"].rank(pct=True) * 100
    p_close_inv = (1.0 - rank_df["closure_pressure"].rank(pct=True)) * 100

    # 24개월 지속성 (24M 대비 순증감 기준)
    net_24m = rank_df["store_count_current"] - rank_df["store_count_24m_ago"]
    p_24m = net_24m.rank(pct=True) * 100

    first_entry_bonus = rank_df["is_first_entry"].astype(float) * 100

    score = (
        0.35 * p_net
        + 0.25 * p_acc
        + 0.15 * first_entry_bonus
        + 0.15 * p_24m
        + 0.10 * p_close_inv
    )

    rank_df["sb_momentum_score"] = score.round(1)
    rank_df = rank_df.sort_values("sb_momentum_score", ascending=False).reset_index(drop=True)
    rank_df["momentum_rank"] = rank_df.index + 1

    return rank_df


def build_and_save_momentum_features(base_dir: str = ".") -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    월별 메트릭스와 상권 모멘텀 순위 테이블을 생성하여 Parquet로 저장합니다.
    """
    base_path = Path(base_dir)
    hist_file = base_path / "data" / "processed" / "store_history.parquet"
    if not hist_file.exists():
        raise FileNotFoundError(f"{hist_file} 파일이 없습니다.")

    history_df = pd.read_parquet(hist_file)

    # 0. 시도 명칭 대한민국 표준 17개 광역시도로 일원화
    history_df["sido"] = history_df.apply(
        lambda r: standardize_sido(r["sido"], sigungu_input=r["sigungu"], address_input=r.get("address_road", "")),
        axis=1,
    )

    # 1. H3 인덱스 추가 (Resolution 8 & 9)
    valid_coords = history_df["latitude"].notna() & history_df["longitude"].notna()
    history_df.loc[valid_coords, "h3_res8"] = history_df.loc[valid_coords].apply(
        lambda r: h3.latlng_to_cell(r["latitude"], r["longitude"], 8), axis=1
    )
    history_df.loc[valid_coords, "h3_res9"] = history_df.loc[valid_coords].apply(
        lambda r: h3.latlng_to_cell(r["latitude"], r["longitude"], 9), axis=1
    )
    # H3가 추가된 history 저장
    history_df.to_parquet(hist_file, index=False)

    # 2. 월별 메트릭스 생성
    monthly_df = generate_area_monthly_metrics(history_df)
    monthly_file = base_path / "data" / "processed" / "area_monthly_metrics.parquet"
    monthly_df.to_parquet(monthly_file, index=False)
    logger.info(f"월별 메트릭스 저장 완료: {monthly_file} (총 {len(monthly_df)}건)")

    # 3. 모멘텀 랭킹 생성
    rank_df = calculate_momentum_scores(monthly_df, history_df, ref_ym="2026-09")
    rank_file = base_path / "data" / "processed" / "area_momentum_rank.parquet"
    rank_df.to_parquet(rank_file, index=False)
    logger.info(f"상권 모멘텀 랭킹 저장 완료: {rank_file} (총 {len(rank_df)}개 지역)")

    return monthly_df, rank_df


if __name__ == "__main__":
    m, r = build_and_save_momentum_features()
    print("Top 10 Commercial Momentum Areas:")
    print(r[["momentum_rank", "area_name", "store_count_current", "net_change_12m", "opening_acceleration", "sb_momentum_score", "momentum_status"]].head(10))
