#backup 
#st_20230615 <- st_data3 
# 탐색 EDA ----------------------------------------------------------------------
glimpse(st_data3)

st_data3 %>% View()
st_data3 %>% group_by(시도) %>% tally()

st_data3 %>% group_by(시도) %>% summarise(n=n()) %>% arrange(desc(n)) %>% 
  write.xlsx2(file="./data/스타벅스23년_1.xlsx", sheetName = "시도별", 
              col.names = TRUE, row.names = TRUE, append = FALSE)

st_data3 %>% group_by(시도,시군) %>% summarise(n=n()) %>% arrange(desc(n)) %>% View()
st_data3 %>% group_by(시도,시군) %>% summarise(n=n()) %>% arrange(desc(n)) %>% write.csv(file = "./data/스타벅스23년_2.csv")

st_data3 %>% group_by(시도,시군) %>% summarise(n=n()) %>% arrange(desc(n)) %>% 
  write.xlsx2(file="./data/스타벅스22년_2.xlsx", sheetName = "구군별", 
              col.names = TRUE, row.names = TRUE, append = FALSE)


#Data Explore
introduce(st_data3)

#To visualize frequency distributions for all discrete features
plot_bar(st_data3)
plot_bar(st_data3$시도)


#To visualize correlation heatmap for all non-missing features:
plot_correlation(na.omit(st_data3), maxcat = 5L)

config <- list(
  "introduce" = list(),
  "plot_intro" = list(),
  "plot_str" = list(
    "type" = "diagonal",
    "fontSize" = 35,
    "width" = 1000,
    "margin" = list("left" = 350, "right" = 250)
  ),
  "plot_missing" = list(),
  "plot_histogram" = list(),
  "plot_density" = list(),
  "plot_qq" = list(sampled_rows = 1000L),
  "plot_bar" = list(),
  "plot_correlation" = list("cor_args" = list("use" = "pairwise.complete.obs")),
  "plot_prcomp" = list(),
  "plot_boxplot" = list(),
  "plot_scatterplot" = list(sampled_rows = 1000L)
)
create_report(st_data3, config = config)