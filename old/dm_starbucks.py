import pandas as pd
import re
import os

# 파일 경로 확인 및 수정
excel_file = 'startbucks_store_list_20250827.xlsx'
if not os.path.exists(excel_file):
    print(f"파일을 찾을 수 없습니다: {excel_file}")
    print("현재 디렉토리의 파일들:")
    for file in os.listdir('.'):
        if file.endswith('.xlsx'):
            print(f"  - {file}")
    exit()

# 데이터 읽기
st_data = pd.read_excel(excel_file)
print(f"데이터 로드 완료: {len(st_data)}개 매장")

# 데이터 구조 확인
print("\n=== 데이터 구조 확인 ===")
print(st_data.head())       # R의 View()
print("\n=== 데이터 정보 ===")
print(st_data.info())       # R의 glimpse(), str()
print("\n=== 데이터 요약 ===")
print(st_data.describe())   # R의 summary()

# 1. 지역 구분 : 광역 17개 단위 / 시군구 / 도로명
st_data2 = st_data.copy()

# 주소를 공백 기준으로 분리 (더 안전한 방법)
def split_address(address):
    if pd.isna(address):
        return ["", "", ""]
    
    parts = str(address).split()
    if len(parts) >= 3:
        return [parts[0], parts[1], ' '.join(parts[2:])]
    elif len(parts) == 2:
        return [parts[0], parts[1], ""]
    elif len(parts) == 1:
        return [parts[0], "", ""]
    else:
        return ["", "", ""]

# 주소 분리 적용
address_parts = st_data2['주소'].apply(split_address)
st_data2['시도'] = [part[0] for part in address_parts]
st_data2['시군'] = [part[1] for part in address_parts]
st_data2['도로명'] = [part[2] for part in address_parts]

print("\n=== 주소 분리 결과 ===")
print(st_data2[['주소', '시도', '시군', '도로명']].head(10))

# 2. 동명 추출 (괄호 안의 내용 + 다른 형태도 고려)
def extract_dong(address):
    if pd.isna(address):
        return ""
    
    address_str = str(address)
    
    # 괄호 안의 내용 추출
    match = re.search(r'\((.*?)\)', address_str)
    if match:
        return match.group(1)
    
    # "동"으로 끝나는 패턴 찾기
    dong_match = re.search(r'([가-힣]+동)', address_str)
    if dong_match:
        return dong_match.group(1)
    
    # "리"로 끝나는 패턴 찾기 (농촌지역)
    ri_match = re.search(r'([가-힣]+리)', address_str)
    if ri_match:
        return ri_match.group(1)
    
    return ""

st_data2['동명'] = st_data2['주소'].apply(extract_dong)

print("\n=== 동명 추출 결과 ===")
print(st_data2[['주소', '동명']].head(10))

# 3. 지역별 분석
print("\n=== 지역별 매장 수 분석 ===")
print("시도별 매장 수:")
print(st_data2['시도'].value_counts().head(10))

print("\n\n시군별 매장 수 (상위 10개):")
print(st_data2['시군'].value_counts().head(10))

print("\n\n동명별 매장 수 (상위 10개):")
dong_counts = st_data2['동명'].value_counts()
print(dong_counts.head(10))

# 4. 결측치 확인
print("\n=== 결측치 확인 ===")
print(f"동명이 빈 값인 매장 수: {(st_data2['동명'] == '').sum()}")
print(f"동명이 빈 값인 비율: {((st_data2['동명'] == '').sum() / len(st_data2) * 100):.1f}%")

# 동명이 빈 값인 행 필터
empty_dong = st_data2[st_data2['동명'] == ""]
print(f"\n동명이 없는 매장들 (처음 5개):")
print(empty_dong[['매장명', '주소', '시도', '시군']].head())

# 5. 데이터 저장
output_file = "./data/스타벅스_20250827_분석.xlsx"
os.makedirs('./data', exist_ok=True)  # data 폴더가 없으면 생성

st_data2.to_excel(output_file, sheet_name="분석결과", index=False)
print(f"\n분석 결과가 저장되었습니다: {output_file}")

# 6. 추가 분석: 지역별 통계
print("\n=== 지역별 상세 분석 ===")
region_stats = st_data2.groupby(['시도', '시군']).agg({
    '매장명': 'count',
    '위도': ['mean', 'std'],
    '경도': ['mean', 'std']
}).round(4)

region_stats.columns = ['매장수', '평균위도', '위도표준편차', '평균경도', '경도표준편차']
print(region_stats.head(10))
