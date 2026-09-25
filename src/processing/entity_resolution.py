"""
Starbucks 매장 간 및 외부 데이터와의 Entity Resolution 모듈.
매장명 정규화, RapidFuzz 유사도, 도로명주소 정규화, 공간 거리(Haversine)를 결합하여
종합 일치도(Overall Match Score)를 산출하고 등급을 분류합니다.
"""

import math
import re
from typing import Dict, Any, Tuple, Optional
import pandas as pd
from rapidfuzz import fuzz

STOPWORDS = [
    r"스타벅스커피코리아",
    r"스타벅스코리아",
    r"스타벅스",
    r"STARBUCKS",
    r"주식회사",
    r"\(주\)",
    r"㈜",
    r"점$",
    r"점\b",
    r"\bDT\b",
    r"\bR\b",
    r"리저브",
    r"드라이브스루",
    r"커뮤니티",
]


def normalize_store_name(name: str) -> str:
    """
    매장명 비교를 위한 정규화 함수.
    접두어, 법인명, 특수문자, 지점 접미사 등을 제거하여 핵심 고유 지명/상호만 추출합니다.
    """
    if not isinstance(name, str):
        return ""

    cleaned = name.strip()
    for pattern in STOPWORDS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.I)

    # 특수문자 및 공백 제거
    cleaned = re.sub(r"[\s\-_.,/()~#\[\]]+", "", cleaned)
    return cleaned.lower()


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    위경도 좌표(WGS84) 간의 대원거리(Haversine 거리, 미터 단위)를 계산합니다.
    """
    if any(v is None or math.isnan(v) for v in [lat1, lon1, lat2, lon2]):
        return 999999.0

    R = 6371000.0  # 지구 반지름 (미터)
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    return R * c


def normalize_road_address(addr: str) -> str:
    """
    도로명 주소 정규화 (공백 정리 및 층수/호수 제거).
    """
    if not isinstance(addr, str):
        return ""
    # 괄호 및 층/호수 정보 제거
    cleaned = re.sub(r"\([^)]*\)", "", addr)
    cleaned = re.sub(r"\d+층|\d+호|지하\d+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def calculate_match_score(
    name1: str,
    addr1: str,
    lat1: Optional[float],
    lon1: Optional[float],
    name2: str,
    addr2: str,
    lat2: Optional[float],
    lon2: Optional[float],
) -> Dict[str, Any]:
    """
    두 매장 레코드 간의 이름, 주소, 공간거리를 종합하여 매칭 점수와 등급을 산출합니다.
    """
    # 1. 이름 유사도 (정규화 후 RapidFuzz 토큰 정렬 및 부분 일치)
    norm1 = normalize_store_name(name1)
    norm2 = normalize_store_name(name2)

    if norm1 == norm2 and len(norm1) > 0:
        name_score = 1.0
    elif norm1 in norm2 or norm2 in norm1:
        name_score = 0.9
    else:
        name_score = fuzz.token_sort_ratio(norm1, norm2) / 100.0

    # 2. 주소 유사도
    road1 = normalize_road_address(addr1)
    road2 = normalize_road_address(addr2)
    if road1 and road2:
        addr_score = fuzz.token_set_ratio(road1, road2) / 100.0
    else:
        addr_score = 0.5  # 주소 결측 시 중립값

    # 3. 공간 거리 (미터)
    dist = haversine_distance_meters(lat1, lon1, lat2, lon2)
    if dist <= 50.0:
        geo_score = 1.0
    elif dist <= 150.0:
        geo_score = 0.85
    elif dist <= 300.0:
        geo_score = 0.65
    elif dist <= 500.0:
        geo_score = 0.40
    else:
        geo_score = 0.0

    # 4. 종합 점수 가중치 (공간정보가 유효하면 거리 비중을 높임)
    if dist < 999990.0:
        overall = 0.45 * name_score + 0.35 * geo_score + 0.20 * addr_score
    else:
        overall = 0.65 * name_score + 0.35 * addr_score

    # 등급 부여
    if overall >= 0.85 or (name_score >= 0.95 and dist <= 100.0):
        grade = "MATCH_HIGH"
    elif overall >= 0.70 or (name_score >= 0.80 and dist <= 300.0):
        grade = "MATCH_MEDIUM"
    elif overall >= 0.50:
        grade = "MATCH_LOW"
    else:
        grade = "UNMATCHED"

    return {
        "name_score": round(name_score, 4),
        "addr_score": round(addr_score, 4),
        "geo_score": round(geo_score, 4),
        "distance_meters": round(dist, 1) if dist < 999990.0 else None,
        "overall_match_score": round(overall, 4),
        "match_grade": grade,
    }
