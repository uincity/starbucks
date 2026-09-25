#라이브러리 불러오기
import requests
import json
import pandas as pd
# !pip install -U finance-datareader #코랩 사용시 설치 필요요
import FinanceDataReader as fdr


# 스타벅스 서울 매장 가져오는 함수 
def get_star() :
    data = {
    'ins_lat':'37.56682',
    'ins_lng':'126.97865',
    'p_sido_cd':'01',
    'p_gugun_cd':'',
    'in_biz_cd':'',
    'set_date':'',
    'iend':'1000'}
    url = "<https://www.starbucks.co.kr/store/getStore.do>"
    response = requests.post(url, data = data)
    star_list = response.json()['list']
    df_star = pd.DataFrame(star_list)
    df = df_star[['open_dt','s_name', 'sido_name','gugun_name','doro_address', 'tel', 'lat', 'lot','sido_code']]
    cols = ['오픈일', '매장명', '시/도', '구/군', '주소', '전화번호', '위도', '경도', '코드']  
    df.columns = cols
    df['위도'] = df['위도'].astype(float)
    df['경도'] = df['경도'].astype(float)
    df = df.sort_values('오픈일').reset_index(drop = True)
    
    return df

df_seoul = get_star()
file_name_1 = 'starbucks_seoul'
df_seoul.to_csv(file_name_1, index=False)