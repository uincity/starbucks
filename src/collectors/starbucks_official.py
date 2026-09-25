"""
스타벅스 공식 홈페이지 REST API를 통한 전국 매장 수집 모듈.
Selenium 브라우저 대신 getStore.do 엔드포인트를 직접 호출하여 빠르고 안정적으로 수집합니다.
"""

import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

import pandas as pd
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

API_URL = "https://www.starbucks.co.kr/store/getStore.do?r=N833"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://www.starbucks.co.kr",
    "Referer": "https://www.starbucks.co.kr/store/store_map.do",
}


def fetch_official_stores_raw(timeout: int = 15, max_retries: int = 3) -> List[Dict[str, Any]]:
    """
    공식 스타벅스 엔드포인트에서 전국 매장 Raw JSON 데이터를 수집합니다.
    """
    payload = {
        "in_biz_cds": "0",
        "in_scodes": "0",
        "ins_lat": "37.56682",
        "ins_lng": "126.97865",
        "search_date": "",
        "sido": "",
        "gugun": "",
        "in_distance": "0",
        "in_biz_cd": "",
        "iend": "3500",  # 전국 매장(약 2,200개)을 1회 호출로 모두 수신
        "searchType": "C",
        "set_date": "",
        "rndCod": "1234",
    }

    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"공식 API 호출 시도 {attempt}/{max_retries}...")
            resp = requests.post(API_URL, data=payload, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            stores = data.get("list", [])
            if not stores:
                raise ValueError("API 응답 내 'list'가 비어 있습니다.")
            logger.info(f"총 {len(stores)}개 매장 원본 데이터 수신 성공.")
            return stores
        except Exception as e:
            logger.warning(f"시도 {attempt} 실패: {e}")
            last_exc = e
            time.sleep(2 * attempt)

    raise RuntimeError(f"공식 스타벅스 데이터 수집 실패: {last_exc}")


def normalize_store_record(raw: Dict[str, Any], snapshot_date: str) -> Dict[str, Any]:
    """
    공식 매장 레코드를 표준 스키마 형태로 변환합니다.
    """
    store_name = (raw.get("s_name") or "").strip()
    s_code = str(raw.get("s_code") or "").strip()
    biz_code = str(raw.get("s_biz_code") or "").strip()

    # 위도 / 경도 실수 변환
    lat_val = raw.get("lat")
    lot_val = raw.get("lot")
    try:
        latitude = float(lat_val) if lat_val else None
    except (ValueError, TypeError):
        latitude = None

    try:
        longitude = float(lot_val) if lot_val else None
    except (ValueError, TypeError):
        longitude = None

    # 매장 특성 분류 (공식 스타벅스 store_core.js 테마 코드 기준: T01=DT, T03=Reserve)
    theme_state = str(raw.get("theme_state") or "")
    
    # DT 판별 (공식 T01 코드 또는 매장명 DT)
    is_dt = bool("T01" in theme_state or re.search(r"\bDT\b|드라이브스루", store_name, re.I))

    # Reserve 판별 (공식 T03 코드, 또는 매장명 리저브/R 표기. 단 DSR/SDR 등 사내약어 제외)
    has_t03 = "T03" in theme_state
    has_r_name = bool(
        "리저브" in store_name or
        (re.search(r"R$|R\s|R점", store_name) and not re.search(r"DSR|SDR", store_name, re.I))
    )
    is_reserve = bool(has_t03 or has_r_name)

    is_community = bool("커뮤니티" in store_name)
    is_new = bool(raw.get("new_icon") == "Y" or raw.get("new_bool") == 1)

    if is_dt and is_reserve:
        store_type = "Reserve DT"
    elif is_reserve:
        store_type = "Reserve"
    elif is_dt:
        store_type = "DT"
    elif is_community:
        store_type = "Community"
    else:
        store_type = "General"

    # 개점일 (open_dt) 포맷팅: YYYYMMDD -> YYYY-MM-DD
    open_dt_raw = str(raw.get("open_dt") or "").strip()
    if len(open_dt_raw) == 8 and open_dt_raw.isdigit():
        open_dt = f"{open_dt_raw[:4]}-{open_dt_raw[4:6]}-{open_dt_raw[6:]}"
    else:
        open_dt = None

    # 시도 / 시군구 표준화
    from src.processing.sido_utils import standardize_sido
    raw_sido = (raw.get("sido_name") or "").strip()
    sigungu = (raw.get("gugun_name") or "").strip()
    doro = (raw.get("doro_address") or "").strip()
    jibun = (raw.get("addr") or "").strip()

    sido = standardize_sido(raw_sido, sigungu=sigungu, address_input=doro or jibun)

    return {
        "snapshot_date": snapshot_date,
        "store_id": s_code,
        "biz_code": biz_code,
        "store_name": store_name,
        "sido": sido,
        "sigungu": sigungu,
        "address_jibun": jibun,
        "address_road": doro,
        "latitude": latitude,
        "longitude": longitude,
        "phone": (raw.get("tel") or "").strip(),
        "store_type": store_type,
        "is_dt": is_dt,
        "is_reserve": is_reserve,
        "is_community": is_community,
        "is_new": is_new,
        "open_dt": open_dt,
        "service_codes": theme_state,
        "source": "starbucks_official",
        "collected_at": datetime.now().isoformat(),
    }


def collect_and_save_current(base_dir: str = ".") -> pd.DataFrame:
    """
    최신 전국 스타벅스 매장을 수집하여 raw, snapshot, processed 디렉토리에 저장합니다.
    """
    base_path = Path(base_dir)
    today_str = datetime.now().strftime("%Y-%m-%d")

    # 1. Raw JSON 저장
    raw_stores = fetch_official_stores_raw()
    raw_dir = base_path / "data" / "raw" / "starbucks_official" / today_str
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_file = raw_dir / "stores_raw.json"
    with open(raw_file, "w", encoding="utf-8") as f:
        json.dump(raw_stores, f, ensure_ascii=False, indent=2)
    logger.info(f"Raw 데이터 저장 완료: {raw_file}")

    # 2. DataFrame 표준화
    normalized = [normalize_store_record(r, today_str) for r in raw_stores]
    df = pd.DataFrame(normalized)

    # 중복 store_id 방지
    df = df.drop_duplicates(subset=["store_id"]).reset_index(drop=True)

    # 3. Snapshot 저장 (immutable)
    snap_dir = base_path / "data" / "snapshots" / today_str
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap_file = snap_dir / "stores.parquet"
    df.to_parquet(snap_file, index=False)
    logger.info(f"스냅샷 저장 완료: {snap_file} (총 {len(df)}개 매장)")

    # 4. Processed 마스터 파일 저장
    proc_dir = base_path / "data" / "processed"
    proc_dir.mkdir(parents=True, exist_ok=True)
    proc_parquet = proc_dir / "stores_current.parquet"
    proc_xlsx = proc_dir / "stores_current.xlsx"
    df.to_parquet(proc_parquet, index=False)
    df.to_excel(proc_xlsx, index=False)
    logger.info(f"Processed 마스터 저장 완료: {proc_parquet}, {proc_xlsx}")

    # 5. Snapshot Index 갱신 (Idempotent)
    index_file = base_path / "data" / "snapshots" / "snapshot_index.parquet"
    index_entry = {
        "snapshot_date": today_str,
        "store_count": len(df),
        "collector_version": "2.0_official_rest",
        "collection_status": "SUCCESS",
        "collected_at": datetime.now().isoformat(),
    }
    if index_file.exists():
        idx_df = pd.read_parquet(index_file)
        # 같은 날짜 존재시 대체
        idx_df = idx_df[idx_df["snapshot_date"] != today_str]
        idx_df = pd.concat([idx_df, pd.DataFrame([index_entry])], ignore_index=True)
    else:
        idx_df = pd.DataFrame([index_entry])

    idx_df = idx_df.sort_values("snapshot_date").reset_index(drop=True)
    idx_df.to_parquet(index_file, index=False)
    logger.info(f"스냅샷 인덱스 갱신 완료: {len(idx_df)}개 스냅샷 기록됨")

    return df


if __name__ == "__main__":
    df = collect_and_save_current()
    print(f"수집 완료: 총 {len(df)}개 매장")
    print(df[["store_name", "sido", "sigungu", "open_dt", "store_type"]].head(5))
