import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import folium
from folium import plugins
import warnings
warnings.filterwarnings('ignore')

# 한글 폰트 설정
plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False

print("=== 스타벅스 매장 데이터 EDA 시작 ===\n")

# 1. 데이터 로드
try:
    df = pd.read_excel('./data/스타벅스_20250827_분석.xlsx')
    print(f"✅ 데이터 로드 완료: {len(df)}개 매장")
except FileNotFoundError:
    print("❌ 파일을 찾을 수 없습니다: ./data/스타벅스_20250827_분석.xlsx")
    print("현재 디렉토리의 파일들:")
    for file in os.listdir('.'):
        if file.endswith('.xlsx'):
            print(f"  - {file}")
    exit()

# 2. 기본 데이터 정보
print("\n=== 기본 데이터 정보 ===")
print(f"데이터 크기: {df.shape}")
print(f"컬럼: {list(df.columns)}")
print(f"데이터 타입:\n{df.dtypes}")

# 3. 결측치 확인
print("\n=== 결측치 확인 ===")
missing_data = df.isnull().sum()
missing_percent = (missing_data / len(df)) * 100
missing_df = pd.DataFrame({
    '결측치 수': missing_data,
    '결측치 비율(%)': missing_percent.round(2)
})
print(missing_df[missing_df['결측치 수'] > 0])

# 4. 기본 통계 요약
print("\n=== 기본 통계 요약 ===")
print(df.describe())

# 5. 지역별 분석
print("\n=== 지역별 분석 ===")

# 시도별 매장 수
print("시도별 매장 수 (상위 10개):")
sido_counts = df['시도'].value_counts()
print(sido_counts.head(10))

# 시군별 매장 수
print("\n시군별 매장 수 (상위 15개):")
sigungu_counts = df['시군'].value_counts()
print(sigungu_counts.head(15))

# 동명별 매장 수
print("\n동명별 매장 수 (상위 15개):")
dong_counts = df['동명'].value_counts()
print(dong_counts.head(15))

# 6. 시각화
print("\n=== 시각화 생성 중... ===")

# 그래프 크기 설정
plt.figure(figsize=(15, 12))

# 6-1. 시도별 매장 수 막대그래프
plt.subplot(2, 2, 1)
sido_counts.plot(kind='bar', color='skyblue', edgecolor='black')
plt.title('시도별 스타벅스 매장 수', fontsize=14, fontweight='bold')
plt.xlabel('시도')
plt.ylabel('매장 수')
plt.xticks(rotation=45, ha='right')
plt.tight_layout()

# 6-2. 시군별 매장 수 (상위 20개)
plt.subplot(2, 2, 2)
top_sigungu = sigungu_counts.head(20)
top_sigungu.plot(kind='bar', color='lightcoral', edgecolor='black')
plt.title('시군별 매장 수 (상위 20개)', fontsize=14, fontweight='bold')
plt.xlabel('시군')
plt.ylabel('매장 수')
plt.xticks(rotation=45, ha='right')
plt.tight_layout()

# 6-3. 동명별 매장 수 (상위 20개)
plt.subplot(2, 2, 3)
top_dong = dong_counts.head(20)
top_dong.plot(kind='bar', color='lightgreen', edgecolor='black')
plt.title('동명별 매장 수 (상위 20개)', fontsize=14, fontweight='bold')
plt.xlabel('동명')
plt.ylabel('매장 수')
plt.xticks(rotation=45, ha='right')
plt.tight_layout()

# 6-4. 매장 타입별 분포
plt.subplot(2, 2, 4)
store_type_counts = df['매장타입'].value_counts()
store_type_counts.plot(kind='pie', autopct='%1.1f%%', startangle=90)
plt.title('매장 타입별 분포', fontsize=14, fontweight='bold')
plt.ylabel('')

plt.tight_layout()
plt.savefig('./data/스타벅스_지역별_분석.png', dpi=300, bbox_inches='tight')
plt.show()

# 7. 지리적 분석
print("\n=== 지리적 분석 ===")

# 위도/경도 통계
print("위도 통계:")
print(f"  최소: {df['위도'].min():.4f} (남쪽)")
print(f"  최대: {df['위도'].max():.4f} (북쪽)")
print(f"  평균: {df['위도'].mean():.4f}")
print(f"  표준편차: {df['위도'].std():.4f}")

print("\n경도 통계:")
print(f"  최소: {df['경도'].min():.4f} (서쪽)")
print(f"  최대: {df['경도'].max():.4f} (동쪽)")
print(f"  평균: {df['경도'].mean():.4f}")
print(f"  표준편차: {df['경도'].std():.4f}")

# 8. 지역별 밀도 분석
print("\n=== 지역별 밀도 분석 ===")

# 시도별 평균 위도/경도
sido_coords = df.groupby('시도').agg({
    '위도': ['mean', 'std'],
    '경도': ['mean', 'std'],
    '매장명': 'count'
}).round(4)

sido_coords.columns = ['평균위도', '위도표준편차', '평균경도', '경도표준편차', '매장수']
sido_coords = sido_coords.sort_values('매장수', ascending=False)

print("시도별 지리적 통계:")
print(sido_coords)

# 9. 상관관계 분석
print("\n=== 상관관계 분석 ===")

# 수치형 컬럼만 선택
numeric_cols = ['위도', '경도']
correlation_matrix = df[numeric_cols].corr()

print("위도-경도 상관계수:")
print(correlation_matrix)

# 10. 지도 시각화
print("\n=== 지도 시각화 생성 중... ===")

# 한국 중심 좌표
center_lat = df['위도'].mean()
center_lon = df['경도'].mean()

# Folium 지도 생성
m = folium.Map(location=[center_lat, center_lon], 
               zoom_start=7, 
               tiles='OpenStreetMap')

# 시도별로 다른 색상 사용
colors = ['red', 'blue', 'green', 'purple', 'orange', 'darkred', 'lightred', 
          'beige', 'darkblue', 'darkgreen', 'cadetblue', 'darkpurple', 'white', 
          'pink', 'lightblue', 'lightgreen', 'gray', 'black', 'lightgray']

# 시도별로 마커 추가
for idx, row in df.iterrows():
    if pd.notna(row['위도']) and pd.notna(row['경도']):
        # 시도별로 색상 선택
        sido_idx = list(sido_counts.index).index(row['시도']) if row['시도'] in sido_counts.index else 0
        color = colors[sido_idx % len(colors)]
        
        # 팝업 정보
        popup_text = f"""
        <b>{row['매장명']}</b><br>
        주소: {row['주소']}<br>
        시도: {row['시도']}<br>
        시군: {row['시군']}<br>
        동명: {row['동명']}<br>
        전화: {row['전화번호']}
        """
        
        folium.Marker(
            location=[row['위도'], row['경도']],
            popup=folium.Popup(popup_text, max_width=300),
            icon=folium.Icon(color=color, icon='info-sign')
        ).add_to(m)

# 범례 추가
legend_html = '''
<div style="position: fixed; 
            bottom: 50px; left: 50px; width: 200px; height: 200px; 
            background-color: white; border:2px solid grey; z-index:9999; 
            font-size:14px; padding: 10px">
            <p><b>시도별 색상</b></p>
'''
for i, sido in enumerate(sido_counts.index[:10]):  # 상위 10개만
    color = colors[i % len(colors)]
    legend_html += f'<p><span style="color:{color};">●</span> {sido}</p>'

legend_html += '</div>'
m.get_root().html.add_child(folium.Element(legend_html))

# 지도 저장
m.save('./data/스타벅스_매장_지도.html')
print("✅ 지도가 저장되었습니다: ./data/스타벅스_매장_지도.html")

# 11. 추가 분석
print("\n=== 추가 분석 ===")

# 동명이 없는 매장 분석
empty_dong_df = df[df['동명'] == '']
print(f"동명이 없는 매장 수: {len(empty_dong_df)} ({len(empty_dong_df)/len(df)*100:.1f}%)")

if len(empty_dong_df) > 0:
    print("\n동명이 없는 매장의 시도별 분포:")
    print(empty_dong_df['시도'].value_counts().head(10))

# 12. 요약 리포트
print("\n" + "="*50)
print("📊 스타벅스 매장 EDA 완료!")
print("="*50)
print(f"📁 총 매장 수: {len(df):,}개")
print(f"🗺️  시도 수: {df['시도'].nunique()}개")
print(f"🏘️  시군 수: {df['시군'].nunique()}개")
print(f"🏠  동명 수: {df['동명'].nunique()}개")
print(f"📱 매장 타입 수: {df['매장타입'].nunique()}개")
print(f"📍 동명 추출 성공률: {(len(df) - len(empty_dong_df))/len(df)*100:.1f}%")

print(f"\n📈 생성된 파일들:")
print(f"  - 지역별 분석 차트: ./data/스타벅스_지역별_분석.png")
print(f"  - 인터랙티브 지도: ./data/스타벅스_매장_지도.html")

print("\n🎯 주요 인사이트:")
print(f"  - 가장 많은 매장: {sido_counts.index[0]} ({sido_counts.iloc[0]}개)")
print(f"  - 가장 많은 시군: {sigungu_counts.index[0]} ({sigungu_counts.iloc[0]}개)")
print(f"  - 가장 많은 동명: {dong_counts.index[0]} ({dong_counts.iloc[0]}개)")

print("="*50)
