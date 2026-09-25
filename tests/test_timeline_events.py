"""
스타벅스 매장 변화 타임라인 이벤트 데이터 정합성 및 생애주기 무결성 테스트.
"""

from pathlib import Path
import pandas as pd
import pytest

from src.visualization.timeline_map import build_timeline_payload


@pytest.fixture(scope="module")
def history_df():
    fpath = Path("data/processed/store_history.parquet")
    assert fpath.exists(), f"데이터 파일 누락: {fpath}"
    return pd.read_parquet(fpath)


@pytest.fixture(scope="module")
def busan_payload(history_df):
    return build_timeline_payload(history_df, sido="부산광역시", sigungu=None, period="전체")


def test_event_date_ordering(busan_payload):
    """1. 이벤트 날짜 정렬 검사: 시간순 오름차순 정렬 여부"""
    events = busan_payload["events"]
    assert len(events) > 0, "부산 이벤트가 비어있음"

    dates = [e["event_date"] for e in events]
    assert dates == sorted(dates), "이벤트 날짜가 시간순으로 정렬되지 않았습니다."


def test_no_close_before_open(busan_payload):
    """2. OPEN(또는 baseline) 이전 CLOSE 불가 검사"""
    events = busan_payload["events"]
    initial_ids = {s["store_id"] for s in busan_payload["initial_stores"]}

    opened_ids = set(initial_ids)
    for ev in events:
        sid = ev["store_id"]
        etype = ev["event_type"]
        if etype in ("OPEN", "BASELINE"):
            opened_ids.add(sid)
        elif etype == "CLOSE":
            assert sid in opened_ids, f"매장 ID {sid} ({ev['store_name']})가 OPEN 전에 CLOSE되었습니다."


def test_no_duplicate_open(busan_payload):
    """3. 동일 매장 중복 OPEN 검사"""
    events = busan_payload["events"]
    initial_ids = {s["store_id"] for s in busan_payload["initial_stores"]}

    seen_open = set(initial_ids)
    for ev in events:
        sid = ev["store_id"]
        etype = ev["event_type"]
        if etype == "OPEN":
            assert sid not in seen_open, f"매장 ID {sid} ({ev['store_name']})가 중복 OPEN되었습니다."
            seen_open.add(sid)


def test_final_active_matches_operating(history_df, busan_payload):
    """4. 최종 active store count = 현재 영업점 수 (148개) 일치 검증"""
    events = busan_payload["events"]
    active_stores = {s["store_id"] for s in busan_payload["initial_stores"]}

    for ev in events:
        sid = ev["store_id"]
        etype = ev["event_type"]
        if etype in ("OPEN", "BASELINE"):
            active_stores.add(sid)
        elif etype == "CLOSE":
            active_stores.discard(sid)

    actual_operating = (
        (history_df["sido"] == "부산광역시") & (history_df["current_status"] == "OPERATING")
    ).sum()

    assert len(active_stores) == actual_operating, (
        f"타임라인 최종 active 매장수({len(active_stores)})가 실제 운영 매장수({actual_operating})와 불일치합니다."
    )


def test_sigungu_sum_equals_sido_total(history_df):
    """5. 각 구·군별 active 합계 = 부산 전체 일치 검증"""
    busan_df = history_df[history_df["sido"] == "부산광역시"]
    sigungus = busan_df["sigungu"].unique()

    total_sum = 0
    for sgg in sigungus:
        payload = build_timeline_payload(history_df, sido="부산광역시", sigungu=sgg, period="전체")
        # 구별 최종 active 매장 수 계산
        active = {s["store_id"] for s in payload["initial_stores"]}
        for ev in payload["events"]:
            sid = ev["store_id"]
            if ev["event_type"] in ("OPEN", "BASELINE"):
                active.add(sid)
            elif ev["event_type"] == "CLOSE":
                active.discard(sid)
        total_sum += len(active)

    actual_operating = (
        (history_df["sido"] == "부산광역시") & (history_df["current_status"] == "OPERATING")
    ).sum()

    assert total_sum == actual_operating, (
        f"구별 합계({total_sum})가 부산 전체 운영 매장수({actual_operating})와 다릅니다."
    )


def test_no_missing_coordinates(busan_payload):
    """6. 좌표 누락 검사: 모든 초기 매장 및 이벤트에 위도/경도가 존재하는가"""
    for s in busan_payload["initial_stores"]:
        assert s["latitude"] is not None and s["longitude"] is not None
        assert not pd.isna(s["latitude"]) and not pd.isna(s["longitude"])

    for ev in busan_payload["events"]:
        assert ev["latitude"] is not None and ev["longitude"] is not None
        assert not pd.isna(ev["latitude"]) and not pd.isna(ev["longitude"])


def test_coordinates_in_busan_bbox(busan_payload):
    """7. 위도/경도 부산 영역(Bounding Box) 검사"""
    for ev in busan_payload["events"]:
        lat = ev["latitude"]
        lon = ev["longitude"]
        assert 34.8 <= lat <= 35.6, f"위도 범위 벗어남: {lat} ({ev['store_name']})"
        assert 128.7 <= lon <= 129.5, f"경도 범위 벗어남: {lon} ({ev['store_name']})"


def test_timeline_period_filters(history_df):
    """8. 최근 5년, 최근 3년 필터 적용 시에도 최종 상태의 active 수가 정상 일치하는지 검증"""
    actual_operating = (
        (history_df["sido"] == "부산광역시") & (history_df["current_status"] == "OPERATING")
    ).sum()

    for period in ["최근 10년", "최근 5년", "최근 3년"]:
        payload = build_timeline_payload(history_df, sido="부산광역시", sigungu=None, period=period)
        active = {s["store_id"] for s in payload["initial_stores"]}
        for ev in payload["events"]:
            sid = ev["store_id"]
            if ev["event_type"] in ("OPEN", "BASELINE"):
                active.add(sid)
            elif ev["event_type"] == "CLOSE":
                active.discard(sid)

        assert len(active) == actual_operating, (
            f"{period} 필터 재생 후 active 매장수({len(active)})가 실제 운영 매장수({actual_operating})와 불일치합니다."
        )
