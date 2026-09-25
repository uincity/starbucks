"""
대한민국 17개 광역시도 표준화 유틸리티 모듈.
'강원', '강원도', '강원특별자치도' -> '강원특별자치도'
'부산', '부산광역시' -> '부산광역시'
'전남광주' -> 구(광산구, 동구, 서구, 남구, 북구)는 '광주광역시', 그 외는 '전라남도' 로 완벽히 일원화합니다.
"""

GWANGJU_DISTRICTS = {"동구", "서구", "남구", "북구", "광산구"}

# 공식 17개 광역시도 정규화 사전
SIDO_CANONICAL_MAP = {
    # 서울
    "서울": "서울특별시",
    "서울특별시": "서울특별시",
    # 부산
    "부산": "부산광역시",
    "부산광역시": "부산광역시",
    # 대구
    "대구": "대구광역시",
    "대구광역시": "대구광역시",
    # 인천
    "인천": "인천광역시",
    "인천광역시": "인천광역시",
    # 광주
    "광주": "광주광역시",
    "광주광역시": "광주광역시",
    # 대전
    "대전": "대전광역시",
    "대전광역시": "대전광역시",
    # 울산
    "울산": "울산광역시",
    "울산광역시": "울산광역시",
    # 세종
    "세종": "세종특별자치시",
    "세종시": "세종특별자치시",
    "세종특별자치시": "세종특별자치시",
    # 경기
    "경기": "경기도",
    "경기도": "경기도",
    # 강원
    "강원": "강원특별자치도",
    "강원도": "강원특별자치도",
    "강원특별자치도": "강원특별자치도",
    # 충북
    "충북": "충청북도",
    "충청북도": "충청북도",
    # 충남
    "충남": "충청남도",
    "충청남도": "충청남도",
    # 전북
    "전북": "전북특별자치도",
    "전라북도": "전북특별자치도",
    "전북특별자치도": "전북특별자치도",
    # 전남
    "전남": "전라남도",
    "전라남도": "전라남도",
    # 경북
    "경북": "경상북도",
    "경상북도": "경상북도",
    # 경남
    "경남": "경상남도",
    "경상남도": "경상남도",
    # 제주
    "제주": "제주특별자치도",
    "제주도": "제주특별자치도",
    "제주특별자치도": "제주특별자치도",
}

ALL_17_SIDOS = [
    "서울특별시",
    "부산광역시",
    "대구광역시",
    "인천광역시",
    "광주광역시",
    "대전광역시",
    "울산광역시",
    "세종특별자치시",
    "경기도",
    "강원특별자치도",
    "충청북도",
    "충청남도",
    "전북특별자치도",
    "전라남도",
    "경상북도",
    "경상남도",
    "제주특별자치도",
]


def standardize_sido(
    sido_input: str,
    sigungu_input: str = "",
    address_input: str = "",
    sigungu: str = "",
    address: str = "",
) -> str:
    """
    모든 형태의 시도 명칭을 대한민국 표준 17개 광역시도로 통합 변환합니다.
    """
    sido = str(sido_input or "").strip()
    sigungu_val = str(sigungu or sigungu_input or "").strip()
    addr = str(address or address_input or "").strip()

    # 1. '전남광주' 또는 '전남광주통합특별시' 케이스 분리
    if "전남광주" in sido or "전남광주" in addr:
        # 광주 5대 자치구 여부 판별
        if sigungu_val in GWANGJU_DISTRICTS:
            return "광주광역시"
        # 주소에 동구, 서구, 남구, 북구, 광산구가 들어있는 경우
        for d in GWANGJU_DISTRICTS:
            if f" {d} " in f" {addr} ":
                return "광주광역시"
        return "전라남도"

    # 2. 사전 직접 매핑
    if sido in SIDO_CANONICAL_MAP:
        return SIDO_CANONICAL_MAP[sido]

    # 3. 주소 첫 토큰 기준 매핑
    if addr:
        first_token = addr.split()[0]
        if first_token in SIDO_CANONICAL_MAP:
            return SIDO_CANONICAL_MAP[first_token]

    # 4. 부분 문자열 매칭 fallback
    for k, canonical in SIDO_CANONICAL_MAP.items():
        if k in sido:
            return canonical

    return sido
