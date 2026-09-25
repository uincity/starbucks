# 크롤링 모듈 임포트
from bs4 import BeautifulSoup 
from selenium import webdriver 
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

import time
from datetime import datetime
import pandas as pd

# Get today's date in 'YYYYMMDD' format
now = datetime.now()
today_date = now.today().strftime('%Y%m%d')

print(today_date)
# Open a text file for logging
log_file = open('starbucks_crawl_log.txt', 'w')

# 스타벅스코리아 홈페이지 접속
chrome_options = Options()
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')
driver = webdriver.Chrome(options=chrome_options)
url = 'https://www.starbucks.co.kr/store/store_map.do?disp=locale'
driver.get(url)
time.sleep(3)

# 도시별 xpath값 저장
city_xpath = []
for i in range(17):
    text = f'//*[@id="container"]/div/form/fieldset/div/section/article[1]/article/article[2]/div[1]/div[2]/ul/li[{i+1}]/a'
    city_xpath.append(text)

#열려있는 페이지의 소스를 가져오기
html = driver.page_source
soup = BeautifulSoup(html,'html.parser')

# 도시별 이름 저장
city  = soup.select('ul.sido_arae_box')[0].text
city_name = []
leng = 2
for i in range(0,34,2):
    city_name_temp = city[i:leng]
    city_name.append(city_name_temp)
    leng+=2

#전체 버튼 정의
total_btn ='/html/body/div[4]/div[7]/div/form/fieldset/div/section/article[1]/article/article[2]/div[2]/div[3]/div/div/div[1]/ul/li[1]/a'

columns = ['매장명', '위도', '경도','매장타입','주소','전화번호']
startbucks_df_all = pd.DataFrame(columns = columns)  #strabuck전국매장 담을 df
st_cnt =1

for i in range(len(city_name)):

    time.sleep(3)
    # 해당 지역 클릭
    driver.find_element(By.XPATH, city_xpath[i]).click()
    time.sleep(3)
    # 세종시 부분 처리를 위한 if문
    if(i<16):
        # 전체 버튼 클릭
        driver.find_element(By.XPATH, total_btn).click()
        time.sleep(5)    
    # 스타벅스 서울시 매장 리스트 HTML 파싱
    html = driver.page_source
    soup = BeautifulSoup(html, 'html.parser')

    starbucks_soup_list = soup.select('li.quickResultLstCon')
    startbucks_list = []
    area_cnt = 0
    for item in starbucks_soup_list:
        name = item.select('strong')[0].text.strip() # 매장명
        lat = item['data-lat'].strip()
        long = item['data-long'].strip()
        # store_type = item.select('i')[0].text.strip() 
        store_type = item.select('i')[0].attrs.get('class')[0][4::]  #class이름 pin_다음이 매장의 type을 나타내는 아이콘임 
        adress = str(item.select('p')[0]).split('<br/>')[0].split('>')[1]
        tel = str(item.select('p')[0]).split('<br/>')[1].split('<')[0]
        startbucks_list.append([name,lat,long,store_type,adress,tel])
        area_cnt = area_cnt + 1
        st_cnt = st_cnt + 1 #매장총건수 카운트
    startbucks_df =pd.DataFrame(startbucks_list,columns=columns) #현재 지역 매장 담을 df
    # startbucks_df.to_excel(f'./startbucks_store_list_{i+1}_{city_name[i]}.xlsx', index = False)
    startbucks_df_all = pd.concat([startbucks_df_all, startbucks_df], ignore_index=True) #전국 df 결합 
    if(i<16):
        #지역 검색 클릭
        driver.find_element(By.XPATH, '//*[@id="container"]/div/form/fieldset/div/section/article[1]/article/header[2]/h3/a').click()

    print(f'{i+1}번째   {city_name[i]} 지역 매장수 : {area_cnt} 크롤링 종료')
    log_file.write(f'{i+1}번째 {city_name[i]} 지역 매장수 : {area_cnt} 크롤링 종료\n')

log_file.write(f'크롤링을 종료합니다. {today_date}일자 총매장수 : {st_cnt}\n')

print(f'크롤링을 종료합니다. 총매장수 : {st_cnt}')

# Close the log file
log_file.close()

# Save the DataFrame to an Excel file with today's date in the file name
startbucks_df_all.to_excel(f'./startbucks_store_list_{today_date}.xlsx', index=False)

# Close the browser
driver.quit()