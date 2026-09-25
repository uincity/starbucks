
# #### https://www.starbucks.co.kr/store/store_map.do?disp=locale

from bs4 import BeautifulSoup 
from selenium import webdriver 
import time
import pandas as pd


# 스타벅스코리아 홈페이지 접속
browser = webdriver.Chrome('C:\\r_selenium\chromedriver')
url = 'https://www.starbucks.co.kr/store/store_map.do?disp=locale'
browser.get(url)
time.sleep(4)

# 도시별 xpath값 저장
city_xpath = []
for i in range(17):
    text = f'//*[@id="container"]/div/form/fieldset/div/section/article[1]/article/article[2]/div[1]/div[2]/ul/li[{i+1}]/a'
    city_xpath.append(text)

#열려있는 페이지의 소스를 가져오기
html = browser.page_source
soup = BeautifulSoup(html,'html.parser')

# 도시별 이름 저장
city  = soup.select('ul.sido_arae_box')[0].text
city_name = []
leng = 2
for i in range(0,34,2):
    city_name_temp = city[i:leng]
    city_name.append(city_name_temp)
    leng+=2

#전체 버튼 정보 저장
#browser.find_element_by_xpath(city_xpath[0]).click() #지역검색 서울 클릭후 
total_btn ='/html/body/div[4]/div[7]/div/form/fieldset/div/section/article[1]/article/article[2]/div[2]/div[3]/div/div/div[1]/ul/li[1]/a'
#browser.find_element_by_xpath(total_btn).click()

# 지역검색
# /html/body/div[4]/div[7]/div/form/fieldset/div/section/article[1]/article/header[2]/h3/a
# browser.find_element_by_xpath('//*[@id="container"]/div/form/fieldset/div/section/article[1]/article/header[2]/h3/a').click()

tot_cnt = 0 #전국 매장건수 

for i in range(len(city_name)):
    time.sleep(4)
    # 해당 지역 클릭
    browser.find_element_by_xpath(city_xpath[i]).click()
    time.sleep(2)
    # 세종시 부분 처리를 위한 if문
    if(i<16):
        # 전체 버튼 클릭
        browser.find_element_by_xpath(total_btn).click()
        time.sleep(5)    
    # 스타벅스 서울시 매장 리스트 HTML 파싱
    html = browser.page_source
    soup = BeautifulSoup(html, 'html.parser')
   
    starbucks_soup_list = soup.select('li.quickResultLstCon')
    startbucks_list = []

    area_cnt = 0 #지역별 건수 

    for item in starbucks_soup_list:
        name = item.select('strong')[0].text.strip() # 매장명
        lat = item['data-lat'].strip()
        long = item['data-long'].strip()
        store_type = item.select('i')[0].text.strip() 
        adress = str(item.select('p')[0]).split('<br/>')[0].split('>')[1]
        tel = str(item.select('p')[0]).split('<br/>')[1].split('<')[0]
        startbucks_list.append([name,lat,long,store_type,adress,tel])
        area_cnt = area_cnt + 1
    columns = ['매장명', '위도', '경도','매장타입','주소','전화번호']
    startbucks_df =pd.DataFrame(startbucks_list,columns=columns)
    
    tot_cnt = tot_cnt + 1
    startbucks_df.to_excel(f'./startbucks_store_list_{i+1}_{city_name[i]}.xlsx', index = False)
    if(i<16):
        #지역 검색 클릭
        browser.find_element_by_xpath('//*[@id="container"]/div/form/fieldset/div/section/article[1]/article/header[2]/h3/a').click()
    
    print(f'{i+1}번째 {city_name[i]} 지역 매장수 : {area_cnt} 크롤링 종료')
print(f'스타벅스 전국매장수 : {tot_cnt} 크롤링을 종료합니다.')

#browser.close()
