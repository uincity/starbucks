"""
스타벅스 매장별 전체 생애주기(개점, 폐점, 이전, 유형변경)를 추적하는
store_history.parquet 및 store_events.parquet 생성 모듈.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import pandas as pd
import numpy as np

from src.processing.entity_resolution import (
    calculate_match_score,
    normalize_store_name,
    haversine_distance_meters,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def build_store_history_and_events(base_dir: str = ".") -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    현재 매장과 과거 16개 스냅샷 데이터를 결합하여
    store_history.parquet, store_events.parquet, reports/match_audit.csv를 구축합니다.
    """
    base_path = Path(base_dir)
    current_file = base_path / "data" / "processed" / "stores_current.parquet"
    legacy_file = base_path / "data" / "interim" / "legacy_snapshots.parquet"

    if not current_file.exists():
        raise FileNotFoundError(f"{current_file} 파일이 없습니다. 수집기를 먼저 실행하세요.")
    if not legacy_file.exists():
        raise FileNotFoundError(f"{legacy_file} 파일이 없습니다. 정규화기를 먼저 실행하세요.")

    current_df = pd.read_parquet(current_file)
    legacy_df = pd.read_parquet(legacy_file)

    logger.info(f"현재 공식 매장: {len(current_df)}개, 과거 스냅샷 레코드: {len(legacy_df)}개")

    # 1. 과거 스냅샷 집계: 매장명 기준 최초 관측일, 마지막 관측일, 관측 횟수, 대표 주소/좌표
    legacy_summary = legacy_df.groupby("store_name").agg(
        first_seen_date=("snapshot_date", "min"),
        last_seen_date=("snapshot_date", "max"),
        seen_count=("snapshot_date", "count"),
        sido=("sido", "first"),
        sigungu=("sigungu", "first"),
        address_road=("address_road", "first"),
        latitude=("latitude", "median"),
        longitude=("longitude", "median"),
        store_type=("store_type", "last"),
        is_dt=("is_dt", "max"),
        is_reserve=("is_reserve", "max"),
        is_community=("is_community", "max"),
    ).reset_index()

    # 2. 현재 매장과 과거 매장 간 Entity Resolution 매칭
    audit_records = []
    matched_legacy_names = set()

    # 현재 매장 사전 구축
    curr_lookup = {}
    for idx, row in current_df.iterrows():
        curr_lookup[row["store_name"]] = row

    history_records = []
    events_records = []

    # 전체 스냅샷 날짜 정렬 목록 (폐점 구간 판정용)
    all_snapshot_dates = sorted(legacy_df["snapshot_date"].unique().tolist() + [current_df["snapshot_date"].iloc[0]])

    # 2-1. 현재 운영 중인 매장 처리
    for _, curr in current_df.iterrows():
        c_name = curr["store_name"]
        store_id = curr["store_id"]
        lat = curr["latitude"]
        lon = curr["longitude"]
        addr = curr["address_road"] or curr["address_jibun"]

        # 과거 스냅샷에서 매칭 후보 찾기
        matched_legacy_row = None
        best_match_info = None

        if c_name in legacy_summary["store_name"].values:
            matched_legacy_row = legacy_summary[legacy_summary["store_name"] == c_name].iloc[0]
            matched_legacy_names.add(c_name)
            best_match_info = {
                "match_grade": "MATCH_HIGH",
                "overall_match_score": 1.0,
                "distance_meters": 0.0,
                "name_score": 1.0,
                "addr_score": 1.0,
            }
        else:
            # 이름 정규화 후 검색 (RapidFuzz 및 거리)
            norm_c = normalize_store_name(c_name)
            cand_pool = legacy_summary[legacy_summary["sido"] == curr["sido"]]
            best_score = 0.0

            for _, leg in cand_pool.iterrows():
                l_name = leg["store_name"]
                if l_name in matched_legacy_names:
                    continue
                score_dict = calculate_match_score(
                    c_name, addr, lat, lon,
                    l_name, leg["address_road"], leg["latitude"], leg["longitude"]
                )
                if score_dict["overall_match_score"] > best_score:
                    best_score = score_dict["overall_match_score"]
                    best_match_info = score_dict
                    matched_legacy_row = leg

            if best_match_info and best_match_info["overall_match_score"] >= 0.70:
                matched_legacy_names.add(matched_legacy_row["store_name"])
            else:
                matched_legacy_row = None

        # 감사 로그 기록
        audit_records.append({
            "store_id": store_id,
            "current_store_name": c_name,
            "matched_legacy_name": matched_legacy_row["store_name"] if matched_legacy_row is not None else None,
            "match_grade": best_match_info["match_grade"] if best_match_info else "UNMATCHED",
            "overall_match_score": best_match_info["overall_match_score"] if best_match_info else 0.0,
            "distance_meters": best_match_info["distance_meters"] if best_match_info else None,
        })

        # 개점일 결정 (공식 open_dt 1순위, HIGH 신뢰도)
        if pd.notna(curr["open_dt"]) and curr["open_dt"]:
            opened_date_best = curr["open_dt"]
            opened_date_source = "starbucks_official_api"
            opened_date_confidence = "HIGH"
        elif matched_legacy_row is not None:
            opened_date_best = matched_legacy_row["first_seen_date"]
            opened_date_source = "legacy_snapshot_first_seen"
            opened_date_confidence = "MEDIUM"
        else:
            opened_date_best = curr["snapshot_date"]
            opened_date_source = "current_snapshot_first_seen"
            opened_date_confidence = "LOW"

        first_seen = matched_legacy_row["first_seen_date"] if matched_legacy_row is not None else curr["snapshot_date"]
        # 만약 공식 개점일이 first_seen보다 앞서면 first_seen을 공식 개점일로 인정
        if opened_date_best and opened_date_best < first_seen:
            first_seen = opened_date_best

        history_records.append({
            "store_id": store_id,
            "store_name": c_name,
            "latitude": lat,
            "longitude": lon,
            "sido": curr["sido"],
            "sigungu": curr["sigungu"],
            "address_road": addr,
            "address_jibun": curr["address_jibun"],
            "first_seen_date": first_seen,
            "last_seen_date": curr["snapshot_date"],
            "opened_date_best": opened_date_best,
            "opened_date_source": opened_date_source,
            "opened_date_confidence": opened_date_confidence,
            "closed_date_best": None,
            "closed_date_source": None,
            "closed_date_confidence": None,
            "current_status": "OPERATING",
            "store_type": curr["store_type"],
            "is_dt": curr["is_dt"],
            "is_reserve": curr["is_reserve"],
            "is_community": curr["is_community"],
        })

        # OPEN 이벤트 기록
        events_records.append({
            "event_date": opened_date_best,
            "store_id": store_id,
            "store_name": c_name,
            "event_type": "OPEN",
            "old_value": None,
            "new_value": curr["store_type"],
            "source": opened_date_source,
            "confidence": opened_date_confidence,
        })

    # 2-2. 과거 스냅샷에만 있고 현재 운영 목록에 없는 매장 -> 폐점(CLOSED) 판정
    unmatched_legacy = legacy_summary[~legacy_summary["store_name"].isin(matched_legacy_names)]
    logger.info(f"현재 미운영(과거 폐점 추정) 매장 수: {len(unmatched_legacy)}개")

    closed_store_seq = 900000
    for _, leg in unmatched_legacy.iterrows():
        closed_store_seq += 1
        l_name = leg["store_name"]
        last_seen = leg["last_seen_date"]
        first_seen = leg["first_seen_date"]

        # 폐점 추정일: last_seen 바로 다음 스냅샷 날짜 또는 last_seen + 1개월
        idx_after = [d for d in all_snapshot_dates if d > last_seen]
        if idx_after:
            closed_date_best = idx_after[0]
            closed_date_source = f"snapshot_interval_{last_seen}_to_{idx_after[0]}"
        else:
            closed_date_best = (pd.to_datetime(last_seen) + pd.Timedelta(days=30)).strftime("%Y-%m-%d")
            closed_date_source = f"snapshot_after_{last_seen}"

        history_records.append({
            "store_id": f"LEGACY_{closed_store_seq}",
            "store_name": l_name,
            "latitude": leg["latitude"],
            "longitude": leg["longitude"],
            "sido": leg["sido"],
            "sigungu": leg["sigungu"],
            "address_road": leg["address_road"],
            "address_jibun": "",
            "first_seen_date": first_seen,
            "last_seen_date": last_seen,
            "opened_date_best": first_seen,
            "opened_date_source": "legacy_snapshot_first_seen",
            "opened_date_confidence": "MEDIUM",
            "closed_date_best": closed_date_best,
            "closed_date_source": closed_date_source,
            "closed_date_confidence": "HIGH" if leg["seen_count"] >= 2 else "MEDIUM",
            "current_status": "CLOSED",
            "store_type": leg["store_type"],
            "is_dt": leg["is_dt"],
            "is_reserve": leg["is_reserve"],
            "is_community": leg["is_community"],
        })

        # OPEN 이벤트
        events_records.append({
            "event_date": first_seen,
            "store_id": f"LEGACY_{closed_store_seq}",
            "store_name": l_name,
            "event_type": "OPEN",
            "old_value": None,
            "new_value": leg["store_type"],
            "source": "legacy_snapshot_first_seen",
            "confidence": "MEDIUM",
        })

        # CLOSE 이벤트
        events_records.append({
            "event_date": closed_date_best,
            "store_id": f"LEGACY_{closed_store_seq}",
            "store_name": l_name,
            "event_type": "CLOSE",
            "old_value": leg["store_type"],
            "new_value": "CLOSED",
            "source": closed_date_source,
            "confidence": "HIGH" if leg["seen_count"] >= 2 else "MEDIUM",
        })

    # 3. 이전 매장(RELOCATION) 판별 로직
    # 폐점 매장과 1년(365일) 이내, 500m 이내에 유사 매장명으로 신규 오픈한 경우
    history_df = pd.DataFrame(history_records)
    events_df = pd.DataFrame(events_records)
    audit_df = pd.DataFrame(audit_records)

    closed_subset = history_df[history_df["current_status"] == "CLOSED"]
    opened_subset = history_df[history_df["current_status"] == "OPERATING"]

    relocations_detected = 0
    for _, c_row in closed_subset.iterrows():
        c_lat, c_lon = c_row["latitude"], c_row["longitude"]
        c_close_dt = pd.to_datetime(c_row["closed_date_best"])
        c_norm = normalize_store_name(c_row["store_name"])

        # 같은 시도의 신규 오픈 매장 검색
        sido_matches = opened_subset[opened_subset["sido"] == c_row["sido"]]
        for _, o_row in sido_matches.iterrows():
            o_lat, o_lon = o_row["latitude"], o_row["longitude"]
            o_open_dt = pd.to_datetime(o_row["opened_date_best"])
            dist = haversine_distance_meters(c_lat, c_lon, o_lat, o_lon)

            # 500m 이내, 폐점일 기준 전후 1년 이내, 이름 유사도 0.5 이상
            time_diff_days = abs((o_open_dt - c_close_dt).days)
            if dist <= 500.0 and time_diff_days <= 365:
                o_norm = normalize_store_name(o_row["store_name"])
                if c_norm in o_norm or o_norm in c_norm or fuzz.token_sort_ratio(c_norm, o_norm) >= 60:
                    relocations_detected += 1
                    # RELOCATION 이벤트 추가
                    events_df = pd.concat([events_df, pd.DataFrame([{
                        "event_date": o_row["opened_date_best"],
                        "store_id": o_row["store_id"],
                        "store_name": o_row["store_name"],
                        "event_type": "RELOCATION",
                        "old_value": c_row["store_name"],
                        "new_value": o_row["store_name"],
                        "source": f"relocation_from_{c_row['store_name']}_{int(dist)}m",
                        "confidence": "HIGH",
                    }])], ignore_index=True)
                    break

    logger.info(f"이전(Relocation) 감지 매장 수: {relocations_detected}건")

    # 4. Parquet 및 CSV 파일 저장
    proc_dir = base_path / "data" / "processed"
    reports_dir = base_path / "reports"
    proc_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    hist_file = proc_dir / "store_history.parquet"
    event_file = proc_dir / "store_events.parquet"
    audit_file = reports_dir / "match_audit.csv"

    history_df.to_parquet(hist_file, index=False)
    events_df.to_parquet(event_file, index=False)
    audit_df.to_csv(audit_file, index=False, encoding="utf-8-sig")

    logger.info(f"저장 완료:\n - {hist_file} ({len(history_df)}개 매장)\n - {event_file} ({len(events_df)}개 이벤트)\n - {audit_file} ({len(audit_df)}개 감사로그)")

    return history_df, events_df, audit_df


if __name__ == "__main__":
    h, e, a = build_store_history_and_events()
    print("Store History Head:")
    print(h[["store_id", "store_name", "sido", "sigungu", "opened_date_best", "current_status"]].head(5))
    print(f"Total history stores: {len(h)}, Operating: {(h['current_status']=='OPERATING').sum()}, Closed: {(h['current_status']=='CLOSED').sum()}")
