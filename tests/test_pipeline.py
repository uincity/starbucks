"""
스타벅스 시계열 파이프라인 정합성 및 무결성 검증 pytest 테스트 스위트.
"""

from pathlib import Path
import pytest
import pandas as pd
import numpy as np

DATA_DIR = Path("data/processed")


@pytest.fixture(scope="module")
def current_stores():
    f = DATA_DIR / "stores_current.parquet"
    assert f.exists(), "stores_current.parquet 파일이 존재해야 합니다."
    return pd.read_parquet(f)


@pytest.fixture(scope="module")
def store_history():
    f = DATA_DIR / "store_history.parquet"
    assert f.exists(), "store_history.parquet 파일이 존재해야 합니다."
    return pd.read_parquet(f)


@pytest.fixture(scope="module")
def area_monthly():
    f = DATA_DIR / "area_monthly_metrics.parquet"
    assert f.exists(), "area_monthly_metrics.parquet 파일이 존재해야 합니다."
    return pd.read_parquet(f)


@pytest.fixture(scope="module")
def area_rank():
    f = DATA_DIR / "area_momentum_rank.parquet"
    assert f.exists(), "area_momentum_rank.parquet 파일이 존재해야 합니다."
    return pd.read_parquet(f)


def test_current_stores_no_duplicate_store_id(current_stores):
    """현재 운영 매장에 중복된 store_id가 없어야 함"""
    dup = current_stores["store_id"].duplicated().sum()
    assert dup == 0, f"중복 store_id 발견: {dup}건"


def test_coordinates_korea_bounding_box(current_stores):
    """모든 매장 좌표가 대한민국 위경도 범위 내에 존재해야 함 (위도 33~39, 경도 124~132)"""
    valid = current_stores[current_stores["latitude"].notna() & current_stores["longitude"].notna()]
    assert len(valid) > 2000, "유효 좌표 매장 수가 2000개 이상이어야 합니다."

    assert (valid["latitude"] >= 33.0).all() and (valid["latitude"] <= 39.5).all(), "위도 범위 이탈"
    assert (valid["longitude"] >= 124.0).all() and (valid["longitude"] <= 132.5).all(), "경도 범위 이탈"


def test_snapshot_date_format(current_stores):
    """스냅샷 날짜가 YYYY-MM-DD 형식이어야 함"""
    sample_dt = current_stores["snapshot_date"].iloc[0]
    parsed = pd.to_datetime(sample_dt, format="%Y-%m-%d")
    assert parsed.year >= 2024, "최신 스냅샷 연도가 2024 이상이어야 합니다."


def test_opened_before_closed(store_history):
    """폐점일이 있는 경우 opened_date <= closed_date 여야 함"""
    closed = store_history[store_history["closed_date_best"].notna()].copy()
    assert len(closed) > 0, "폐점 매장이 존재해야 합니다."

    o_dt = pd.to_datetime(closed["opened_date_best"])
    c_dt = pd.to_datetime(closed["closed_date_best"])

    valid_seq = o_dt <= c_dt
    invalid_count = (~valid_seq).sum()
    assert invalid_count == 0, f"개점일보다 폐점일이 앞선 매장 발견: {invalid_count}건"


def test_operating_store_status(store_history):
    """현재 영업 매장은 current_status가 OPERATING 이어야 함"""
    operating = store_history[store_history["current_status"] == "OPERATING"]
    assert len(operating) >= 2000, "운영 매장 수가 2000개 이상이어야 합니다."
    assert operating["closed_date_best"].isna().all(), "운영 매장에 폐점일이 존재할 수 없습니다."


def test_monthly_metrics_net_consistency(area_monthly):
    """월별 메트릭스에서 net_change == opened - closed 일치 검사"""
    calc_net = area_monthly["opened"] - area_monthly["closed"]
    diff = (calc_net != area_monthly["net_change"]).sum()
    assert diff == 0, f"net_change 계산 불일치: {diff}건"


def test_area_rank_net_and_acceleration(area_rank):
    """상권 모멘텀에서 opening_acceleration == net_change_12m - net_change_prev_12m 검사"""
    calc_acc = area_rank["net_change_12m"] - area_rank["net_change_prev_12m"]
    diff = (calc_acc != area_rank["opening_acceleration"]).sum()
    assert diff == 0, f"opening_acceleration 계산 불일치: {diff}건"


def test_sb_momentum_score_range(area_rank):
    """SB 모멘텀 스코어가 0에서 100 사이여야 함"""
    scores = area_rank["sb_momentum_score"]
    assert (scores >= 0.0).all() and (scores <= 100.0).all(), "스코어 범위 이탈"
