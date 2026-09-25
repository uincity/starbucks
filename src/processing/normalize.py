"""
과거 스타벅스 스냅샷 엑셀/CSV 데이터를 자동 탐색하고 표준 스키마로 정규화하여
data/interim/legacy_snapshots.parquet 파일로 병합하는 모듈.
"""

import glob
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# 대한민국 17개 광역 시도 표준 정규화 사전
SIDO_MAP = {
    "서울": "서울특별시",
    "서울특별시": "서울특별시",
    "경기": "경기도",
    "경기도": "경기도",
    "인천": "인천광역시",
    "인천광역시": "인천광역시",
    "부산": "부산광역시",
    "부산광역시": "부산광역시",
    "대구": "대구광역시",
    "대구광역시": "대구광역시",
    "광주": "광주광역시",
    "광주광역시": "광주광역시",
    "대전": "대전광역시",
    "대전광역시": "대전광역시",
    "울산": "울산광역시",
    "울산광역시": "울산광역시",
    "세종": "세종특별자치시",
    "세종특별자치시": "세종특별자치시",
    "강원": "강원특별자치도",
    "강원도": "강원특별자치도",
    "강원특별자치도": "강원특별자치도",
    "충북": "충청북도",
    "충청북도": "충청북도",
    "충남": "충청남도",
    "충청남도": "충청남도",
    "전북": "전북특별자치도",
    "전라북도": "전북특별자치도",
    "전북특별자치도": "전북특별자치도",
    "전남": "전라남도",
    "전라남도": "전라남도",
    "경북": "경상북도",
    "경상북도": "경상북도",
    "경남": "경상남도",
    "경상남도": "경상남도",
    "제주": "제주특별자치도",
    "제주도": "제주특별자치도",
    "제주특별자치도": "제주특별자치도",
}


def extract_snapshot_date(file_path: str) -> Optional[str]:
    """
    파일명에서 YYYYMMDD 또는 YYYYMDD 형태의 날짜를 추출하여 YYYY-MM-DD로 변환합니다.
    """
    filename = Path(file_path).name

    # 1. 8자리 YYYYMMDD (2021~2026)
    m8 = re.search(r"(202[1-6])([01]\d)([0-3]\d)", filename)
    if m8:
        y, m, d = m8.group(1), m8.group(2), m8.group(3)
        return f"{y}-{m}-{d}"

    # 2. 7자리 YYYYMDD (예: 2024303 -> 2024-03-03, 2024324 -> 2024-03-24, 2024608 -> 2024-06-08)
    m7 = re.search(r"(202[1-6])([1-9])([0-3]\d)", filename)
    if m7:
        y = m7.group(1)
        m = m7.group(2).zfill(2)
        d = m7.group(3)
        return f"{y}-{m}-{d}"

    return None


def parse_address_sido_sigungu(addr: str) -> Tuple[str, str]:
    """
    주소 문자열에서 시도와 시군구를 분리 및 표준화합니다.
    """
    if not isinstance(addr, str) or not addr.strip():
        return "", ""

    tokens = addr.strip().split()
    if not tokens:
        return "", ""

    raw_sido = tokens[0]
    sido = SIDO_MAP.get(raw_sido, raw_sido)

    sigungu = ""
    if len(tokens) > 1:
        sigungu = tokens[1]
        # 구가 붙은 경우 (예: 경기도 수원시 팔달구 -> 수원시 팔달구)
        if len(tokens) > 2 and tokens[1].endswith("시") and (tokens[2].endswith("구") or tokens[2].endswith("군")):
            sigungu = f"{tokens[1]} {tokens[2]}"

    return sido, sigungu


def normalize_legacy_file(file_path: str) -> Optional[pd.DataFrame]:
    """
    개별 과거 엑셀/CSV 파일을 표준 포맷으로 변환합니다.
    매장 목록 데이터가 아니거나 요약 통계인 경우 None을 반환합니다.
    """
    snap_date = extract_snapshot_date(file_path)
    if not snap_date:
        return None

    try:
        if file_path.endswith(".csv"):
            try:
                df = pd.read_csv(file_path, encoding="utf-8-sig")
            except UnicodeDecodeError:
                df = pd.read_csv(file_path, encoding="cp949")
        else:
            df = pd.read_excel(file_path)
    except Exception as e:
        logger.warning(f"파일 로드 실패 {file_path}: {e}")
        return None

    cols = list(df.columns)

    # 매장명 컬럼 찾기
    name_col = None
    for c in cols:
        if "매장" in str(c) and "명" in str(c):
            name_col = c
            break
        elif str(c).strip() in ["s_name", "store_name", "이름", "상호명"]:
            name_col = c
            break

    if not name_col:
        return None  # 매장 목록이 아닌 집계표는 제외

    # 위도 / 경도 컬럼 찾기
    lat_col = next((c for c in cols if "위도" in str(c) or "lat" in str(c).lower()), None)
    lon_col = next((c for c in cols if "경도" in str(c) or "long" in str(c).lower() or "lot" in str(c).lower()), None)

    # 주소 컬럼 찾기
    addr_col = next((c for c in cols if "주소" in str(c) or "address" in str(c).lower() or "addr" in str(c).lower()), None)

    # 전화번호 컬럼
    phone_col = next((c for c in cols if "전화" in str(c) or "tel" in str(c).lower()), None)

    # 매장타입 컬럼
    type_col = next((c for c in cols if "타입" in str(c) or "type" in str(c).lower()), None)

    # 시도 / 시군 컬럼이 이미 존재하는 경우
    sido_col = next((c for c in cols if str(c).strip() in ["시도", "sido"]), None)
    sigungu_col = next((c for c in cols if str(c).strip() in ["시군", "시군구", "sigungu", "gugun"]), None)

    # 정규화 DataFrame 구성
    records = []
    for _, row in df.iterrows():
        store_name = str(row[name_col]).strip() if pd.notna(row[name_col]) else ""
        if not store_name or store_name == "nan":
            continue

        raw_addr = str(row[addr_col]).strip() if addr_col and pd.notna(row[addr_col]) else ""

        # 시도/시군구 결정
        if sido_col and pd.notna(row[sido_col]):
            sido_val = SIDO_MAP.get(str(row[sido_col]).strip(), str(row[sido_col]).strip())
        else:
            sido_val, _ = parse_address_sido_sigungu(raw_addr)

        if sigungu_col and pd.notna(row[sigungu_col]):
            sigungu_val = str(row[sigungu_col]).strip()
        else:
            _, sigungu_val = parse_address_sido_sigungu(raw_addr)

        # 위경도 변환
        try:
            lat = float(row[lat_col]) if lat_col and pd.notna(row[lat_col]) else None
        except (ValueError, TypeError):
            lat = None

        try:
            lon = float(row[lon_col]) if lon_col and pd.notna(row[lon_col]) else None
        except (ValueError, TypeError):
            lon = None

        # 매장 유형 결정
        raw_type = str(row[type_col]).strip() if type_col and pd.notna(row[type_col]) else ""
        is_dt = bool("DT" in store_name or "generalDT" in raw_type or "드라이브스루" in store_name)
        is_reserve = bool(store_name.endswith("R") or "리저브" in store_name or "reserve" in raw_type.lower())
        is_community = bool("커뮤니티" in store_name)

        if is_dt:
            stype = "DT"
        elif is_reserve:
            stype = "Reserve"
        elif is_community:
            stype = "Community"
        else:
            stype = "General"

        phone = str(row[phone_col]).strip() if phone_col and pd.notna(row[phone_col]) else ""

        records.append({
            "snapshot_date": snap_date,
            "store_name": store_name,
            "sido": sido_val,
            "sigungu": sigungu_val,
            "address_road": raw_addr,
            "address_jibun": "",
            "latitude": lat,
            "longitude": lon,
            "phone": phone,
            "store_type": stype,
            "is_dt": is_dt,
            "is_reserve": is_reserve,
            "is_community": is_community,
            "source_file": Path(file_path).name,
        })

    if not records:
        return None

    res_df = pd.DataFrame(records)
    # 매장명 중복 제거 (단일 스냅샷 내)
    res_df = res_df.drop_duplicates(subset=["store_name"]).reset_index(drop=True)
    return res_df


def build_legacy_snapshots(base_dir: str = ".") -> pd.DataFrame:
    """
    모든 과거 스냅샷 파일을 탐색하여 data/interim/legacy_snapshots.parquet을 구축합니다.
    """
    base_path = Path(base_dir)
    pattern1 = str(base_path / "data" / "**" / "*.xlsx")
    pattern2 = str(base_path / "data" / "**" / "*.csv")
    pattern3 = str(base_path / "old" / "**" / "*.xlsx")
    pattern4 = str(base_path / "old" / "**" / "*.csv")
    pattern5 = str(base_path / "*.xlsx")

    candidate_files = (
        glob.glob(pattern1, recursive=True)
        + glob.glob(pattern2, recursive=True)
        + glob.glob(pattern3, recursive=True)
        + glob.glob(pattern4, recursive=True)
        + glob.glob(pattern5)
    )
    candidate_files = sorted(list(set(candidate_files)))

    # 불필요 파일 제외
    exclude_keywords = ["stores_current", "legacy_snapshots", "~$", "비교", "분석.xlsx", "OLD\\startbucks_store_list_1_", "20220410\\startbucks_store_list_"]
    # 단, 시도별 분할 파일 중 전국 통합본이 있는 경우 통합본을 우선 사용

    snapshot_dfs: Dict[str, pd.DataFrame] = {}

    for f in candidate_files:
        fname = Path(f).name
        # 임시파일이나 비교 엑셀 제외
        if any(ex in f for ex in ["~$", "stores_current", "legacy_snapshots", "시도비교"]):
            continue

        # 단일 시도별 파일(예: startbucks_store_list_1_서울.xlsx)은 nationwide 파일이 없는 경우에만 사용
        # nationwide 파일 우선 탐색
        df = normalize_legacy_file(f)
        if df is None or len(df) < 50:  # 전국 단위 매장은 최소 수백 개 이상이어야 함
            continue

        snap_date = df["snapshot_date"].iloc[0]
        logger.info(f"스냅샷 로드 완료: {snap_date} | 매장수: {len(df)}개 | 파일: {fname}")

        # 동일 날짜가 여러 번 나오는 경우 더 매장 수가 많은(완전한) 파일 선택
        if snap_date not in snapshot_dfs or len(df) > len(snapshot_dfs[snap_date]):
            snapshot_dfs[snap_date] = df

    all_dfs = [snapshot_dfs[d] for d in sorted(snapshot_dfs.keys())]
    if not all_dfs:
        raise RuntimeError("유효한 과거 스냅샷 데이터를 찾지 못했습니다.")

    combined_df = pd.concat(all_dfs, ignore_index=True)

    # 출력 디렉토리 보장
    out_dir = base_path / "data" / "interim"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "legacy_snapshots.parquet"

    combined_df.to_parquet(out_file, index=False)
    logger.info(f"Legacy 스냅샷 통합 완료: {out_file}")
    logger.info(f"총 {len(combined_df)}건 레코드, 고유 날짜 {combined_df['snapshot_date'].nunique()}개:")
    for dt, group in combined_df.groupby("snapshot_date"):
        logger.info(f"  - {dt}: {len(group)}개 매장")

    return combined_df


if __name__ == "__main__":
    df = build_legacy_snapshots()
    print("완료!")
