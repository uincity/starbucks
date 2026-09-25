"""
임의의 좌표(예: 아파트 단지, 개발 사업지 등)를 기준으로
주변 스타벅스 인프라 및 시계열 변화 모멘텀을 계산하는 공간 피처 엔지니어링 모듈.
"""

from datetime import datetime
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd

from src.processing.entity_resolution import haversine_distance_meters


def compute_starbucks_features_for_location(
    target_lat: float,
    target_lon: float,
    history_df: pd.DataFrame,
    ref_date: str = "2026-09-25",
) -> Dict[str, Any]:
    """
    특정 위경도 좌표에 대해 스타벅스 공간 접근성 및 최근 12개월 변화율 피처를 계산합니다.

    반환 필드:
    - nearest_starbucks_distance: 가장 가까운 영업 중 매장까지의 거리 (m)
    - nearest_store_name: 가장 가까운 매장명
    - starbucks_count_500m: 500m 반경 내 영업 매장 수
    - starbucks_count_1km: 1km 반경 내 영업 매장 수
    - starbucks_count_2km: 2km 반경 내 영업 매장 수
    - new_starbucks_1km_12m: 1km 반경 내 최근 12개월 신규 개점 매장 수
    - closed_starbucks_1km_12m: 1km 반경 내 최근 12개월 폐점 매장 수
    - local_sb_net_change_12m: 1km 반경 내 최근 12개월 순증감
    - local_sb_momentum: 국소 상권 모멘텀 상태 (ACCELERATING / EXPANDING / STABLE / CONTRACTING)
    """
    ref_dt = pd.to_datetime(ref_date)
    dt_12m_ago = ref_dt - pd.DateOffset(months=12)

    # 거리 계산을 위해 위경도가 유효한 매장 필터링
    valid_stores = history_df[history_df["latitude"].notna() & history_df["longitude"].notna()].copy()
    if len(valid_stores) == 0:
        return {}

    distances = []
    for _, row in valid_stores.iterrows():
        dist = haversine_distance_meters(target_lat, target_lon, row["latitude"], row["longitude"])
        distances.append(dist)
    valid_stores["distance_m"] = distances

    # 현재 영업 중 매장 기준
    operating = valid_stores[valid_stores["current_status"] == "OPERATING"]

    if len(operating) > 0:
        min_idx = operating["distance_m"].idxmin()
        nearest_dist = round(operating.loc[min_idx, "distance_m"], 1)
        nearest_name = operating.loc[min_idx, "store_name"]
    else:
        nearest_dist = 99999.0
        nearest_name = ""

    count_500m = int((operating["distance_m"] <= 500.0).sum())
    count_1km = int((operating["distance_m"] <= 1000.0).sum())
    count_2km = int((operating["distance_m"] <= 2000.0).sum())

    # 1km 반경 내 최근 12개월 신규 개점 매장
    within_1km = valid_stores[valid_stores["distance_m"] <= 1000.0]
    opened_dates = pd.to_datetime(within_1km["opened_date_best"])
    new_1km_12m = int(((opened_dates >= dt_12m_ago) & (opened_dates <= ref_dt)).sum())

    # 1km 반경 내 최근 12개월 폐점 매장
    closed_dates = pd.to_datetime(within_1km["closed_date_best"])
    closed_1km_12m = int(((closed_dates >= dt_12m_ago) & (closed_dates <= ref_dt)).sum())

    net_change_1km_12m = new_1km_12m - closed_1km_12m

    # 국소 모멘텀 판정
    if net_change_1km_12m > 0 and count_1km > 1:
        local_momentum = "EXPANDING"
    elif net_change_1km_12m > 0 and count_1km == 1:
        local_momentum = "FIRST_ENTRY"
    elif net_change_1km_12m < 0:
        local_momentum = "CONTRACTING"
    else:
        local_momentum = "STABLE"

    return {
        "nearest_starbucks_distance": nearest_dist,
        "nearest_store_name": nearest_name,
        "starbucks_count_500m": count_500m,
        "starbucks_count_1km": count_1km,
        "starbucks_count_2km": count_2km,
        "new_starbucks_1km_12m": new_1km_12m,
        "closed_starbucks_1km_12m": closed_1km_12m,
        "local_sb_net_change_12m": net_change_1km_12m,
        "local_sb_momentum": local_momentum,
    }


def batch_compute_starbucks_features(
    locations_df: pd.DataFrame,
    lat_col: str,
    lon_col: str,
    history_df: pd.DataFrame,
    ref_date: str = "2026-09-25",
) -> pd.DataFrame:
    """
    여러 좌표가 포함된 DataFrame에 대해 일괄적으로 스타벅스 피처를 결합합니다.
    """
    feature_rows = []
    for _, row in locations_df.iterrows():
        feats = compute_starbucks_features_for_location(
            row[lat_col], row[lon_col], history_df, ref_date=ref_date
        )
        feature_rows.append(feats)

    feats_df = pd.DataFrame(feature_rows)
    return pd.concat([locations_df.reset_index(drop=True), feats_df], axis=1)
