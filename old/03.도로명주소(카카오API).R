
library(httr) # GET()
library(jsonlite) # fromJSON()
library(dplyr)

# 검색할 주소 목록 : 참고 : https://hoontaeklee.github.io/en/posts/20200217_using_api_in_r/


# Web API key
KAKAO_MAP_API_KEY = "eeef2a60013e6941cf9918810f40fe63"

# 결과 저장용 데이터프레임
bowl = data.frame()

# 주소별 반복 : 1826개 length(st_data3$주소)
#i=10

for(i in 1:length(st_data3$주소)) {
  
# GET함수: GET 프로토콜 형식으로 API 호출
  
  addr2coord_res <- 
    GET(
      # 카카오 주소검색API
      
      url = 'https://dapi.kakao.com/v2/local/search/address.json', 
      # 검색어
      
      query = list(query = st_data3$주소[i]),
      # 헤더(API마다 다를 수 있다)
      
      add_headers(Authorization = paste0("KakaoAK ", KAKAO_MAP_API_KEY)))
  

  
  kpmg_list <- addr2coord_res %>% 
    content(as = 'text') %>% 
    fromJSON()
  
  # 검색 결과 중 원하는 인자  추출
  
  row_temp = 
    cbind(
      ## 매장명
      st_data3[i,1] , 
      ## 지번주소
      kpmg_list$documents$address %>% 
        select(address_name,region_3depth_h_name,region_3depth_name),
      ## 도로명주소
      kpmg_list$documents$road_address %>% 
        select(address_name, building_name, x, y))
  
  # 데이터프레임에 저장

  bowl = rbind(bowl, row_temp)
  }

i

