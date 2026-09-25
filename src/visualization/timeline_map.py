"""
스타벅스 매장 개점·폐점 타임라인 지도 (Event-driven Timeline Map) 컴포넌트 모듈.
Leaflet.js 기반의 클라이언트 사이드 JavaScript 애니메이션으로,
Python Streamlit의 rerun 없이 매끄럽게 개점 펄스 및 폐점 쇼크웨이브/소멸 애니메이션을 렌더링합니다.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


def build_timeline_payload(
    history_df: pd.DataFrame,
    sido: str,
    sigungu: Optional[str] = None,
    period: str = "전체",
) -> Dict[str, Any]:
    """
    선택된 지역(시도 및 시군구)에 대해 시간순 Event 데이터와 초기 baseline 데이터를 구축합니다.
    """
    # 1. 지역 필터링
    df = history_df[history_df["sido"] == sido].copy()
    is_all_sigungu = (
        sigungu is None
        or sigungu.startswith("전체")
        or "전체" in str(sigungu)
    )

    if not is_all_sigungu:
        df = df[df["sigungu"] == sigungu].copy()

    if df.empty:
        return {
            "error": "선택된 지역에 매장 데이터가 없습니다.",
            "sido": sido,
            "sigungu": sigungu or "전체",
        }

    # 2. 유효 좌표 필터링
    df = df[df["latitude"].notna() & df["longitude"].notna()].copy()

    # 3. 기간 필터에 따른 start_date 결정 (기준일: 2026-09-25)
    now_str = "2026-09-25"
    now_dt = pd.to_datetime(now_str)

    if period == "최근 3년":
        cutoff_dt = now_dt - pd.DateOffset(years=3)
    elif period == "최근 5년":
        cutoff_dt = now_dt - pd.DateOffset(years=5)
    elif period == "최근 10년":
        cutoff_dt = now_dt - pd.DateOffset(years=10)
    else:  # 전체
        min_opened = df["opened_date_best"].min()
        cutoff_dt = pd.to_datetime(min_opened) if pd.notna(min_opened) else pd.to_datetime("2000-01-01")

    start_date_str = cutoff_dt.strftime("%Y-%m-%d")

    # 4. 초기 상태 (baseline stores): start_date 이전에 개점되어 start_date 시점에 운영 중이던 매장
    initial_stores: List[Dict[str, Any]] = []
    events: List[Dict[str, Any]] = []

    for _, row in df.iterrows():
        sid = str(row["store_id"])
        sname = str(row["store_name"])
        lat = float(row["latitude"])
        lon = float(row["longitude"])
        stype = str(row["store_type"])
        is_dt = bool(row["is_dt"])
        is_res = bool(row["is_reserve"])
        sgg = str(row["sigungu"])
        road = str(row.get("address_road", ""))

        open_best = str(row["opened_date_best"]) if pd.notna(row["opened_date_best"]) else ""
        open_conf = str(row["opened_date_confidence"]) if pd.notna(row["opened_date_confidence"]) else "UNKNOWN"
        open_src = str(row["opened_date_source"]) if pd.notna(row["opened_date_source"]) else ""

        close_best = str(row["closed_date_best"]) if pd.notna(row.get("closed_date_best")) and str(row["closed_date_best"]) != "NaT" else None
        curr_status = str(row["current_status"])

        store_meta = {
            "store_id": sid,
            "store_name": sname,
            "latitude": lat,
            "longitude": lon,
            "sido": sido,
            "sigungu": sgg,
            "store_type": stype,
            "is_dt": is_dt,
            "is_reserve": is_res,
            "address_road": road,
            "opened_date": open_best,
            "open_confidence": open_conf,
            "closed_date": close_best,
            "current_status": curr_status,
        }

        # start_date 시점에 이미 활성 상태인지 판별
        was_active_at_start = False
        if open_best and open_best <= start_date_str:
            if close_best is None or close_best > start_date_str:
                was_active_at_start = True

        if was_active_at_start:
            initial_stores.append(store_meta)
        else:
            # start_date 이후에 개점한 매장
            if open_best and open_best > start_date_str:
                # 품질 처리 (요구사항 7)
                # FIRST_SEEN / UNKNOWN 이면서 일괄 추정된 폐점 매장은 BASELINE(가짜 OPEN 방지)
                if open_src == "legacy_snapshot_first_seen" and open_conf != "HIGH":
                    event_type = "BASELINE"
                else:
                    event_type = "OPEN"

                events.append({
                    "event_date": open_best,
                    "event_type": event_type,
                    "open_quality": open_conf,
                    **store_meta,
                })

        # 폐점 이벤트: start_date 이후에 폐점한 경우
        if close_best and close_best >= start_date_str:
            events.append({
                "event_date": close_best,
                "event_type": "CLOSE",
                "open_quality": open_conf,
                **store_meta,
            })

    # 5. 이벤트 정렬: 날짜순 오름차순, 동일 날짜는 BASELINE -> OPEN -> CLOSE 순
    type_priority = {"BASELINE": 1, "OPEN": 2, "CLOSE": 3}
    events.sort(key=lambda x: (x["event_date"], type_priority.get(x["event_type"], 4), x["store_name"]))

    # 6. 마일스톤 생성
    milestones: Dict[str, str] = {}
    cum_open = len(initial_stores)
    first_store_found = bool(initial_stores)

    for ev in events:
        if ev["event_type"] in ("OPEN", "BASELINE"):
            cum_open += 1
            edate = ev["event_date"]
            if not first_store_found:
                milestones[edate] = f"🌟 {ev['sigungu']} 최초 스타벅스 진입 ({ev['store_name']})"
                first_store_found = True
            elif cum_open == 10:
                milestones[edate] = f"🎉 {sido} 10번째 매장 돌파 ({ev['store_name']})"
            elif cum_open == 30:
                milestones[edate] = f"🚀 {sido} 30번째 매장 돌파 ({ev['store_name']})"
            elif cum_open == 50:
                milestones[edate] = f"🏆 {sido} 50번째 매장 돌파 ({ev['store_name']})"
            elif cum_open == 100:
                milestones[edate] = f"👑 {sido} 100번째 매장 돌파 ({ev['store_name']})"

    # 7. 자동 Bounds 계산
    all_lats = df["latitude"].tolist()
    all_lons = df["longitude"].tolist()
    bounds = [
        [min(all_lats), min(all_lons)],
        [max(all_lats), max(all_lons)],
    ]
    center = [sum(all_lats) / len(all_lats), sum(all_lons) / len(all_lons)]

    # 8. 시군구 목록
    sigungu_list = sorted(df["sigungu"].unique().tolist())

    # 9. 데이터 분석 인사이트 자동 생성
    operating_now = (df["current_status"] == "OPERATING").sum()
    closed_now = (df["current_status"] == "CLOSED").sum()
    dt_now = (df["is_dt"] & (df["current_status"] == "OPERATING")).sum()
    res_now = (df["is_reserve"] & (df["current_status"] == "OPERATING")).sum()

    df_op = df[df["opened_date_best"].notna()].copy()
    df_op["open_year"] = df_op["opened_date_best"].str.slice(0, 4)
    peak_year = df_op["open_year"].value_counts().index[0] if not df_op.empty else "N/A"
    peak_count = df_op["open_year"].value_counts().iloc[0] if not df_op.empty else 0

    insight_text = (
        f"💡 **상권 변화 관측 요약 ({sido} {sigungu if not is_all_sigungu else '전체'}):** "
        f"가장 활발하게 출점이 일어난 피크 연도는 **{peak_year}년**({peak_count}개 개점)이었으며, "
        f"현재 운영 중인 {operating_now:,}개 매장 중 DT 매장은 {dt_now}개({dt_now/operating_now*100:.1f}%), "
        f"리저브 매장은 {res_now}개입니다. 과거 누적 폐점은 총 {closed_now}건이 관측되었습니다."
    )

    return {
        "sido": sido,
        "sigungu": sigungu if not is_all_sigungu else "전체",
        "is_all_sigungu": is_all_sigungu,
        "period": period,
        "start_date": start_date_str,
        "end_date": now_str,
        "bounds": bounds,
        "center": center,
        "initial_stores": initial_stores,
        "events": events,
        "milestones": milestones,
        "sigungu_list": sigungu_list,
        "total_stores_operating": int(operating_now),
        "total_stores_closed": int(closed_now),
        "insight_text": insight_text,
    }


def generate_timeline_html(payload: Dict[str, Any]) -> str:
    """
    Leaflet.js 기반의 인터랙티브 애니메이션 타임라인 지도 HTML 코드를 생성합니다.
    """
    payload_json = json.dumps(payload, ensure_ascii=False)

    html_code = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>스타벅스 매장 변화 타임라인</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  
  <!-- Leaflet CSS -->
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  
  <style>
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Pretendard", "Segoe UI", Roboto, sans-serif;
    }}
    body {{
      background: #0d1117;
      color: #e6edf3;
      overflow: hidden;
      padding: 4px;
    }}
    
    .timeline-container {{
      display: flex;
      flex-direction: column;
      gap: 8px;
      height: 770px;
      background: #161b22;
      border: 1px solid #30363d;
      border-radius: 12px;
      padding: 14px;
      box-shadow: 0 8px 24px rgba(0,0,0,0.4);
    }}
    
    /* 상단 헤더 & 컨트롤 바 */
    .header-bar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 8px;
      border-bottom: 1px solid #21262d;
    }}
    .header-title {{
      font-size: 15px;
      font-weight: 700;
      color: #2ea043;
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .header-subtitle {{
      font-size: 12px;
      color: #8b949e;
      margin-left: 6px;
    }}
    .header-controls {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .toggle-label {{
      font-size: 12px;
      color: #c9d1d9;
      display: flex;
      align-items: center;
      gap: 5px;
      cursor: pointer;
      user-select: none;
    }}
    .toggle-label input {{
      cursor: pointer;
      accent-color: #2ea043;
    }}
    
    /* 본문 레이아웃 (지도 + 우측 패널) */
    .main-view {{
      display: flex;
      flex: 1;
      gap: 12px;
      min-height: 0;
      position: relative;
    }}
    
    /* 지도 뷰 영역 */
    .map-wrapper {{
      flex: 1;
      position: relative;
      border-radius: 8px;
      overflow: hidden;
      border: 1px solid #30363d;
      background: #090d13;
    }}
    #timeline-map {{
      width: 100%;
      height: 100%;
    }}
    
    /* 지도 내부 HUD 오버레이 (날짜 & KPI) */
    .hud-overlay {{
      position: absolute;
      top: 12px;
      left: 12px;
      z-index: 1000;
      background: rgba(13, 17, 23, 0.90);
      backdrop-filter: blur(8px);
      border: 1px solid rgba(240, 246, 252, 0.15);
      border-radius: 8px;
      padding: 10px 14px;
      box-shadow: 0 4px 16px rgba(0,0,0,0.5);
      min-width: 250px;
      pointer-events: none;
    }}
    .hud-date {{
      font-size: 22px;
      font-weight: 800;
      color: #58a6ff;
      letter-spacing: -0.5px;
      margin-bottom: 6px;
      display: flex;
      align-items: baseline;
      gap: 8px;
    }}
    .hud-date .date-badge {{
      font-size: 11px;
      padding: 2px 6px;
      border-radius: 4px;
      background: rgba(56, 139, 253, 0.15);
      color: #58a6ff;
      font-weight: 600;
    }}
    .hud-kpi-row {{
      display: flex;
      gap: 12px;
      font-size: 12px;
      color: #8b949e;
    }}
    .kpi-item {{
      display: flex;
      flex-direction: column;
    }}
    .kpi-val {{
      font-size: 15px;
      font-weight: 700;
      color: #f0f6fc;
    }}
    .kpi-val.green {{ color: #3fb950; }}
    .kpi-val.red {{ color: #f85149; }}
    
    /* 현재 이벤트 실시간 알림 배너 */
    .hud-event-banner {{
      margin-top: 8px;
      padding: 5px 8px;
      border-radius: 4px;
      font-size: 12px;
      font-weight: 600;
      display: none;
      transition: all 0.3s ease;
    }}
    .hud-event-banner.open-banner {{
      display: block;
      background: rgba(46, 160, 67, 0.2);
      border: 1px solid #2ea043;
      color: #3fb950;
    }}
    .hud-event-banner.close-banner {{
      display: block;
      background: rgba(248, 81, 73, 0.2);
      border: 1px solid #f85149;
      color: #ff7b72;
    }}
    
    /* 마일스톤 토스트 */
    .milestone-toast {{
      margin-top: 6px;
      padding: 4px 8px;
      border-radius: 4px;
      background: rgba(210, 153, 34, 0.2);
      border: 1px solid #d29922;
      color: #e3b341;
      font-size: 11px;
      font-weight: 700;
      display: none;
    }}
    
    /* 지도 범례 */
    .map-legend {{
      position: absolute;
      bottom: 12px;
      right: 12px;
      z-index: 1000;
      background: rgba(13, 17, 23, 0.9);
      border: 1px solid #30363d;
      border-radius: 6px;
      padding: 6px 10px;
      font-size: 11px;
      color: #c9d1d9;
      display: flex;
      gap: 10px;
      pointer-events: none;
    }}
    .legend-item {{
      display: flex;
      align-items: center;
      gap: 4px;
    }}
    
    /* 우측 패널 (실시간 랭킹 또는 상세 KPI) */
    .side-panel {{
      width: 280px;
      background: #0d1117;
      border: 1px solid #30363d;
      border-radius: 8px;
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      overflow-y: auto;
    }}
    .side-title {{
      font-size: 13px;
      font-weight: 700;
      color: #f0f6fc;
      border-bottom: 1px solid #21262d;
      padding-bottom: 6px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .side-badge {{
      font-size: 11px;
      color: #8b949e;
      font-weight: normal;
    }}
    
    /* Bar Chart Race 스타일 */
    .rank-list {{
      display: flex;
      flex-direction: column;
      gap: 6px;
      flex: 1;
    }}
    .rank-item {{
      display: flex;
      flex-direction: column;
      gap: 2px;
    }}
    .rank-header {{
      display: flex;
      justify-content: space-between;
      font-size: 11px;
      color: #c9d1d9;
    }}
    .rank-bar-bg {{
      height: 7px;
      background: #21262d;
      border-radius: 4px;
      overflow: hidden;
    }}
    .rank-bar-fill {{
      height: 100%;
      background: linear-gradient(90deg, #2ea043, #56d364);
      border-radius: 4px;
      width: 0%;
      transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }}
    
    /* 단일 시군구 요약 카드 */
    .summary-card {{
      background: #161b22;
      border: 1px solid #21262d;
      border-radius: 6px;
      padding: 10px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}
    .summary-kpi-item {{
      display: flex;
      justify-content: space-between;
      font-size: 12px;
      color: #8b949e;
    }}
    .summary-kpi-item strong {{
      color: #f0f6fc;
    }}
    
    /* 하단 타임라인 슬라이더 & 컨트롤 */
    .timeline-footer {{
      display: flex;
      flex-direction: column;
      gap: 8px;
      background: #0d1117;
      border: 1px solid #30363d;
      border-radius: 8px;
      padding: 10px 14px;
    }}
    .slider-row {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .slider-year {{
      font-size: 12px;
      font-weight: 700;
      color: #8b949e;
      min-width: 40px;
    }}
    .timeline-slider {{
      flex: 1;
      height: 6px;
      -webkit-appearance: none;
      background: #21262d;
      border-radius: 3px;
      outline: none;
      cursor: pointer;
    }}
    .timeline-slider::-webkit-slider-thumb {{
      -webkit-appearance: none;
      width: 16px;
      height: 16px;
      border-radius: 50%;
      background: #2ea043;
      border: 2px solid #ffffff;
      cursor: pointer;
      box-shadow: 0 0 8px rgba(46, 160, 67, 0.8);
      transition: transform 0.1s ease;
    }}
    .timeline-slider::-webkit-slider-thumb:hover {{
      transform: scale(1.2);
    }}
    
    .playback-row {{
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .btn-group {{
      display: flex;
      gap: 6px;
    }}
    .ctrl-btn {{
      background: #21262d;
      color: #f0f6fc;
      border: 1px solid #30363d;
      border-radius: 6px;
      padding: 5px 12px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 4px;
      transition: all 0.2s ease;
    }}
    .ctrl-btn:hover {{
      background: #30363d;
      border-color: #8b949e;
    }}
    .ctrl-btn.primary {{
      background: #238636;
      border-color: #2ea043;
    }}
    .ctrl-btn.primary:hover {{
      background: #2ea043;
    }}
    
    .speed-group {{
      display: flex;
      gap: 4px;
    }}
    .speed-btn {{
      background: #161b22;
      color: #8b949e;
      border: 1px solid #30363d;
      border-radius: 4px;
      padding: 3px 8px;
      font-size: 11px;
      font-weight: 600;
      cursor: pointer;
    }}
    .speed-btn.active {{
      background: #388bfd;
      color: #ffffff;
      border-color: #388bfd;
    }}
    
    /* -------------------------------------------------------------
       CSS Keyframe 애니메이션 & Leaflet 마커 스타일
       ------------------------------------------------------------- */
    .store-marker-wrap {{
      position: relative;
      width: 32px;
      height: 32px;
      display: flex;
      align-items: center;
      justify-content: center;
      pointer-events: auto;
    }}
    
    /* 기본 마커 원형 */
    .store-dot {{
      width: 14px;
      height: 14px;
      border-radius: 50%;
      background: #006241;
      border: 2px solid #ffffff;
      box-shadow: 0 0 6px rgba(0,0,0,0.6);
      position: relative;
      z-index: 10;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 8px;
      font-weight: 900;
      color: #ffffff;
      transition: transform 0.2s ease, background 0.3s ease;
    }}
    .store-dot.dt {{
      border: 2.5px solid #ff9800;
    }}
    .store-dot.reserve {{
      border: 2.5px solid #ffd700;
      background: #1a1a1a;
      color: #ffd700;
    }}
    
    /* 1. OPEN 애니메이션 */
    .anim-open {{
      animation: openScale 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275) forwards;
    }}
    @keyframes openScale {{
      0% {{ transform: scale(0.1); opacity: 0; }}
      50% {{ transform: scale(1.8); opacity: 1; }}
      100% {{ transform: scale(1.0); opacity: 1; }}
    }}
    
    /* OPEN 리플 파동 */
    .open-ripple {{
      position: absolute;
      width: 14px;
      height: 14px;
      border-radius: 50%;
      border: 3px solid #2ea043;
      z-index: 5;
      animation: rippleSpread 0.75s ease-out forwards;
      pointer-events: none;
    }}
    @keyframes rippleSpread {{
      0% {{ transform: scale(1); opacity: 0.9; }}
      100% {{ transform: scale(4.5); opacity: 0; border-width: 1px; }}
    }}
    
    /* 2. CLOSE 애니메이션 (RED -> PULSE -> X -> SHRINK) */
    .anim-close-flash {{
      background: #e74c3c !important;
      border-color: #ffffff !important;
      animation: closeFlash 0.3s ease forwards;
    }}
    @keyframes closeFlash {{
      0% {{ transform: scale(1); }}
      50% {{ transform: scale(1.6); background: #ff3838; }}
      100% {{ transform: scale(1.2); background: #c0392b; }}
    }}
    
    /* CLOSE 쇼크웨이브 */
    .close-shockwave {{
      position: absolute;
      width: 14px;
      height: 14px;
      border-radius: 50%;
      border: 3px solid #ff4d4d;
      z-index: 5;
      animation: shockwaveSpread 0.65s ease-out forwards;
      pointer-events: none;
    }}
    @keyframes shockwaveSpread {{
      0% {{ transform: scale(1); opacity: 0.95; }}
      100% {{ transform: scale(5); opacity: 0; border-width: 1px; }}
    }}
    
    /* CLOSE Shrink & Fade Out */
    .anim-close-fade {{
      animation: closeFade 0.65s ease-in forwards;
    }}
    @keyframes closeFade {{
      0% {{ transform: scale(1.2); opacity: 1; }}
      60% {{ transform: scale(0.8); opacity: 0.6; }}
      100% {{ transform: scale(0); opacity: 0; }}
    }}
    
    /* 폐점 흔적 마커 (회색 X) */
    .closed-trace-marker {{
      width: 10px;
      height: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 10px;
      font-weight: 900;
      color: #8b949e;
      opacity: 0.45;
      pointer-events: auto;
    }}
    
    /* 미니 팝업 툴팁 */
    .leaflet-popup-content-wrapper {{
      background: #161b22;
      color: #e6edf3;
      border: 1px solid #30363d;
      border-radius: 6px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.5);
      font-size: 12px;
      padding: 0;
    }}
    .leaflet-popup-content {{
      margin: 8px 10px;
      line-height: 1.4;
    }}
    .leaflet-popup-tip {{
      background: #161b22;
    }}
    .popup-store-name {{
      font-weight: 700;
      color: #58a6ff;
      margin-bottom: 2px;
    }}
    .popup-meta {{
      font-size: 11px;
      color: #8b949e;
    }}
    .popup-tag {{
      display: inline-block;
      padding: 1px 4px;
      border-radius: 3px;
      font-size: 10px;
      font-weight: 600;
      margin-top: 3px;
    }}
    .tag-open {{ background: rgba(46,160,67,0.2); color: #3fb950; }}
    .tag-close {{ background: rgba(248,81,73,0.2); color: #ff7b72; }}
    .tag-dt {{ background: rgba(255,152,0,0.2); color: #ffa726; }}
    .tag-res {{ background: rgba(255,215,0,0.2); color: #ffd54f; }}
  </style>
</head>
<body>

<div class="timeline-container">
  <!-- 1. 상단 타이틀 & 컨트롤 바 -->
  <div class="header-bar">
    <div class="header-title">
      <span>⏱️ 스타벅스 매장 변화 타임라인</span>
      <span class="header-subtitle" id="subtitle-text">{payload.get('sido', '')} {payload.get('sigungu', '')} ({payload.get('start_date', '')[:4]} → {payload.get('end_date', '')[:4]})</span>
    </div>
    <div class="header-controls">
      <label class="toggle-label">
        <input type="checkbox" id="chk-trace">
        <span>폐점 매장 흔적 표시 (✕)</span>
      </label>
    </div>
  </div>

  <!-- 2. 본문 메인 뷰 (지도 + 우측 패널) -->
  <div class="main-view">
    <div class="map-wrapper">
      <div id="timeline-map"></div>
      
      <!-- 지도 HUD 오버레이 -->
      <div class="hud-overlay">
        <div class="hud-date">
          <span id="disp-date">----.--.--</span>
          <span class="date-badge" id="disp-pct">0%</span>
        </div>
        <div class="hud-kpi-row">
          <div class="kpi-item">
            <span>운영 매장</span>
            <span class="kpi-val green" id="disp-active">0</span>
          </div>
          <div class="kpi-item">
            <span>누적 개점</span>
            <span class="kpi-val" id="disp-opened">0</span>
          </div>
          <div class="kpi-item">
            <span>누적 폐점</span>
            <span class="kpi-val red" id="disp-closed">0</span>
          </div>
        </div>
        <!-- 실시간 이벤트 배너 -->
        <div class="hud-event-banner" id="hud-banner"></div>
        <!-- 마일스톤 배너 -->
        <div class="milestone-toast" id="hud-milestone"></div>
      </div>

      <!-- 지도 범례 -->
      <div class="map-legend">
        <div class="legend-item"><span style="color:#006241;font-weight:900;">●</span> 일반</div>
        <div class="legend-item"><span style="color:#ff9800;font-weight:900;">◉</span> DT</div>
        <div class="legend-item"><span style="color:#ffd700;font-weight:900;">★</span> Reserve</div>
        <div class="legend-item"><span style="color:#ff4d4d;font-weight:900;">✕</span> 폐점</div>
      </div>
    </div>

    <!-- 우측 실시간 랭킹 / KPI 요약 패널 -->
    <div class="side-panel" id="side-panel">
      <!-- JS로 동적 렌더링 -->
    </div>
  </div>

  <!-- 3. 하단 타임라인 슬라이더 & 재생 컨트롤 -->
  <div class="timeline-footer">
    <div class="slider-row">
      <span class="slider-year" id="start-year-lbl">2001</span>
      <input type="range" id="timeline-slider" class="timeline-slider" min="0" max="100" value="0">
      <span class="slider-year" id="end-year-lbl">2026</span>
    </div>
    
    <div class="playback-row">
      <div class="btn-group">
        <button class="ctrl-btn" id="btn-start" title="처음으로">|◀</button>
        <button class="ctrl-btn" id="btn-prev" title="이전 이벤트">◀</button>
        <button class="ctrl-btn primary" id="btn-play">▶ 재생</button>
        <button class="ctrl-btn" id="btn-next" title="다음 이벤트">▶</button>
        <button class="ctrl-btn" id="btn-end" title="끝으로">▶|</button>
      </div>
      
      <div class="speed-group">
        <button class="speed-btn" data-speed="1">1x</button>
        <button class="speed-btn active" data-speed="2">2x</button>
        <button class="speed-btn" data-speed="5">5x</button>
        <button class="speed-btn" data-speed="10">10x</button>
      </div>
    </div>
  </div>
</div>

<!-- Leaflet JS -->
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

<script>
  // Python에서 주입된 데이터
  const DATA = {payload_json};

  // 상태 관리 객체
  const state = {{
    map: null,
    events: DATA.events || [],
    initialStores: DATA.initial_stores || [],
    currentIndex: 0, // 지금까지 처리한 이벤트 수 (0 ~ events.length)
    isPlaying: false,
    speedMultiplier: 2, // 2x 기본
    showClosedTraces: false,
    timer: null,
    
    // 현재 지도에 활성화된 마커들 Map<store_id, {{ marker, data }}>
    activeMarkers: new Map(),
    // 폐점 흔적 마커들 Map<store_id, marker>
    traceMarkers: new Map(),
    
    // 구별 카운트 (실시간 랭킹용)
    sigunguCounts: {{}},
    
    // 누적 통계
    totalOpened: 0,
    totalClosed: 0,
  }};

  // 1. 지도 초기화
  function initMap() {{
    const center = DATA.center || [35.1796, 129.0756];
    state.map = L.map('timeline-map', {{
      center: center,
      zoom: 11,
      zoomControl: true,
      scrollWheelZoom: true,
      attributionControl: false,
    }});

    // 100% 무료 & API 키가 일체 필요 없는 OpenStreetMap 공식 타일 레이어
    L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors'
    }}).addTo(state.map);

    // 자동 Bounds 맞춤
    if (DATA.bounds && DATA.bounds.length === 2) {{
      state.map.fitBounds(DATA.bounds, {{ padding: [35, 35] }});
    }}
  }}

  // 마커 DivIcon 생성기
  function createStoreIcon(store, customClass = '') {{
    let typeClass = 'general';
    let symbol = '';
    if (store.is_reserve) {{
      typeClass = 'reserve';
      symbol = 'R';
    }} else if (store.is_dt) {{
      typeClass = 'dt';
      symbol = 'DT';
    }}

    const html = `
      <div class="store-marker-wrap">
        <div class="store-dot ${{typeClass}} ${{customClass}}">
          ${{symbol}}
        </div>
      </div>
    `;

    return L.divIcon({{
      html: html,
      className: '',
      iconSize: [32, 32],
      iconAnchor: [16, 16],
    }});
  }}

  // 팝업 HTML 생성기
  function getPopupContent(store, eventType = 'OPERATING', eventDate = '') {{
    const typeLabel = store.is_reserve ? '리저브 (Reserve)' : (store.is_dt ? '드라이브스루 (DT)' : '일반 매장');
    const tagClass = eventType === 'CLOSE' ? 'tag-close' : (eventType === 'OPEN' ? 'tag-open' : 'tag-open');
    const tagText = eventType === 'CLOSE' ? '폐점 완료' : (eventType === 'OPEN' ? '신규 오픈' : '운영 중');

    let extraNote = '';
    if (store.open_confidence === 'MEDIUM' || store.open_quality === 'MEDIUM') {{
      extraNote = '<div style="color:#d29922;font-size:10px;margin-top:2px;">* 개점일 추정 매장</div>';
    }}

    return `
      <div>
        <div class="popup-store-name">${{store.store_name}}</div>
        <div class="popup-meta">📍 ${{store.sigungu}} | ${{typeLabel}}</div>
        <div class="popup-meta">📅 개점: ${{store.opened_date || '-'}}</div>
        ${{store.closed_date ? `<div class="popup-meta">🛑 폐점: ${{store.closed_date}}</div>` : ''}}
        <div class="popup-meta" style="font-size:10px;color:#8b949e;margin-top:3px;">${{store.address_road || ''}}</div>
        <span class="popup-tag ${{tagClass}}">${{tagText}}</span>
        ${{extraNote}}
      </div>
    `;
  }}

  // 2. Baseline 초기 매장 로드
  function loadBaseline() {{
    clearAllMarkers();
    state.sigunguCounts = {{}};
    (DATA.sigungu_list || []).forEach(s => state.sigunguCounts[s] = 0);

    state.totalOpened = (DATA.initial_stores || []).length;
    state.totalClosed = 0;

    (DATA.initial_stores || []).forEach(store => {{
      const icon = createStoreIcon(store);
      const marker = L.marker([store.latitude, store.longitude], {{ icon: icon }}).addTo(state.map);
      marker.bindPopup(getPopupContent(store, 'OPERATING'));

      state.activeMarkers.set(store.store_id, {{ marker: marker, data: store }});
      state.sigunguCounts[store.sigungu] = (state.sigunguCounts[store.sigungu] || 0) + 1;
    }});

    updateHUD(DATA.start_date, '초기 상태');
    updateSidePanel();
  }}

  function clearAllMarkers() {{
    state.activeMarkers.forEach(item => state.map.removeLayer(item.marker));
    state.activeMarkers.clear();

    state.traceMarkers.forEach(m => state.map.removeLayer(m));
    state.traceMarkers.clear();
  }}

  // 3. 이벤트 실행 로직 (OPEN / CLOSE / BASELINE)
  function processEvent(event, isFastForward = false) {{
    const storeId = event.store_id;
    const eventType = event.event_type;
    const eventDate = event.event_date;

    if (eventType === 'OPEN' || eventType === 'BASELINE') {{
      state.totalOpened++;
      state.sigunguCounts[event.sigungu] = (state.sigunguCounts[event.sigungu] || 0) + 1;

      if (state.activeMarkers.has(storeId)) {{
        state.map.removeLayer(state.activeMarkers.get(storeId).marker);
      }}

      const animClass = isFastForward || eventType === 'BASELINE' ? '' : 'anim-open';
      const icon = createStoreIcon(event, animClass);
      const marker = L.marker([event.latitude, event.longitude], {{ icon: icon }}).addTo(state.map);
      marker.bindPopup(getPopupContent(event, 'OPEN', eventDate));

      state.activeMarkers.set(storeId, {{ marker: marker, data: event }});

      if (!isFastForward && eventType === 'OPEN') {{
        triggerRipple(event.latitude, event.longitude);
        showEventBanner(`+ ${{event.store_name}} OPEN (${{event.sigungu}})`, 'open');
        
        if (DATA.milestones && DATA.milestones[eventDate]) {{
          showMilestone(DATA.milestones[eventDate]);
        }}
      }}
    }}
    else if (eventType === 'CLOSE') {{
      state.totalClosed++;
      if (state.sigunguCounts[event.sigungu] > 0) {{
        state.sigunguCounts[event.sigungu]--;
      }}

      if (state.activeMarkers.has(storeId)) {{
        const item = state.activeMarkers.get(storeId);
        
        if (!isFastForward) {{
          triggerCloseAnimation(item.marker, event, () => {{
            state.map.removeLayer(item.marker);
            state.activeMarkers.delete(storeId);
            maybeAddClosedTrace(event);
          }});
          showEventBanner(`− ${{event.store_name}} CLOSED (${{event.sigungu}})`, 'close');
        }} else {{
          state.map.removeLayer(item.marker);
          state.activeMarkers.delete(storeId);
          maybeAddClosedTrace(event);
        }}
      }} else {{
        maybeAddClosedTrace(event);
      }}
    }}

    updateHUD(eventDate);
    updateSidePanel();
  }}

  // 리플 효과 (OPEN 시 녹색 파동)
  function triggerRipple(lat, lon) {{
    const rippleIcon = L.divIcon({{
      html: '<div class="open-ripple"></div>',
      className: '',
      iconSize: [14, 14],
      iconAnchor: [7, 7],
    }});
    const ripple = L.marker([lat, lon], {{ icon: rippleIcon, interactive: false }}).addTo(state.map);
    setTimeout(() => state.map.removeLayer(ripple), 800);
  }}

  // 폐점 시퀀스 애니메이션 (RED -> SHOCKWAVE -> X -> SHRINK)
  function triggerCloseAnimation(marker, event, onComplete) {{
    const el = marker.getElement();
    if (!el) {{
      onComplete();
      return;
    }}
    const dot = el.querySelector('.store-dot');
    if (dot) {{
      dot.classList.add('anim-close-flash');
      dot.innerText = '✕';
    }}

    triggerShockwave(event.latitude, event.longitude);
    setTimeout(() => triggerShockwave(event.latitude, event.longitude), 200);

    setTimeout(() => {{
      if (dot) dot.classList.add('anim-close-fade');
    }}, 400);

    setTimeout(() => {{
      onComplete();
    }}, 900);
  }}

  function triggerShockwave(lat, lon) {{
    const shockIcon = L.divIcon({{
      html: '<div class="close-shockwave"></div>',
      className: '',
      iconSize: [14, 14],
      iconAnchor: [7, 7],
    }});
    const shock = L.marker([lat, lon], {{ icon: shockIcon, interactive: false }}).addTo(state.map);
    setTimeout(() => state.map.removeLayer(shock), 700);
  }}

  function maybeAddClosedTrace(store) {{
    if (!state.traceMarkers.has(store.store_id)) {{
      const traceIcon = L.divIcon({{
        html: '<div class="closed-trace-marker">✕</div>',
        className: '',
        iconSize: [12, 12],
        iconAnchor: [6, 6],
      }});
      const traceMarker = L.marker([store.latitude, store.longitude], {{ icon: traceIcon }});
      traceMarker.bindPopup(getPopupContent(store, 'CLOSE'));
      state.traceMarkers.set(store.store_id, traceMarker);

      if (state.showClosedTraces) {{
        traceMarker.addTo(state.map);
      }}
    }}
  }}

  // 4. 임의 날짜 상태 즉시 복원 (state_at_date)
  function stateAtDate(targetCount) {{
    loadBaseline();
    for (let i = 0; i < targetCount && i < state.events.length; i++) {{
      processEvent(state.events[i], true); // fast-forward mode
    }}
    state.currentIndex = targetCount;
    updateSlider(targetCount);

    const currentDate = targetCount > 0 && targetCount <= state.events.length
      ? state.events[targetCount - 1].event_date
      : DATA.start_date;
    updateHUD(currentDate);
  }}

  // 5. HUD 및 패널 UI 업데이트
  function updateHUD(dateStr) {{
    document.getElementById('disp-date').innerText = (dateStr || DATA.start_date).replace(/-/g, '. ');
    document.getElementById('disp-active').innerText = state.activeMarkers.size.toLocaleString();
    document.getElementById('disp-opened').innerText = state.totalOpened.toLocaleString();
    document.getElementById('disp-closed').innerText = state.totalClosed.toLocaleString();

    const totalEvents = state.events.length;
    const pct = totalEvents > 0 ? Math.round((state.currentIndex / totalEvents) * 100) : 100;
    document.getElementById('disp-pct').innerText = `${{pct}}%`;
  }}

  function showEventBanner(text, type) {{
    const banner = document.getElementById('hud-banner');
    banner.innerText = text;
    banner.className = `hud-event-banner ${{type}}-banner`;
    setTimeout(() => {{
      banner.style.display = 'none';
    }}, 2000);
  }}

  function showMilestone(text) {{
    const toast = document.getElementById('hud-milestone');
    toast.innerText = text;
    toast.style.display = 'block';
    setTimeout(() => {{
      toast.style.display = 'none';
    }}, 3500);
  }}

  function updateSidePanel() {{
    const panel = document.getElementById('side-panel');
    if (!panel) return;

    if (DATA.is_all_sigungu) {{
      const sortedSgg = Object.entries(state.sigunguCounts)
        .sort((a, b) => b[1] - a[1]);
      
      const maxVal = Math.max(...sortedSgg.map(x => x[1]), 1);

      let html = `
        <div class="side-title">
          <span>📊 시군구별 운영 매장</span>
          <span class="side-badge">총 ${{state.activeMarkers.size}}개</span>
        </div>
        <div class="rank-list">
      `;

      sortedSgg.forEach(([sgg, count], idx) => {{
        if (count > 0 || idx < 10) {{
          const widthPct = Math.round((count / maxVal) * 100);
          html += `
            <div class="rank-item">
              <div class="rank-header">
                <span>${{idx + 1}}. ${{sgg}}</span>
                <strong>${{count}}개</strong>
              </div>
              <div class="rank-bar-bg">
                <div class="rank-bar-fill" style="width: ${{widthPct}}%;"></div>
              </div>
            </div>
          `;
        }}
      }});

      html += `</div>`;
      panel.innerHTML = html;
    }} else {{
      const sgg = DATA.sigungu;
      const activeCount = state.activeMarkers.size;
      
      let dtCount = 0;
      let resCount = 0;
      state.activeMarkers.forEach(item => {{
        if (item.data.is_dt) dtCount++;
        if (item.data.is_reserve) resCount++;
      }});

      panel.innerHTML = `
        <div class="side-title">
          <span>📍 ${{sgg}} 상권 프로파일</span>
          <span class="side-badge">실시간 현황</span>
        </div>
        <div class="summary-card">
          <div class="summary-kpi-item">
            <span>현재 운영 매장:</span>
            <strong style="color:#3fb950;font-size:14px;">${{activeCount}}개</strong>
          </div>
          <div class="summary-kpi-item">
            <span>누적 개점 매장:</span>
            <strong>${{state.totalOpened}}개</strong>
          </div>
          <div class="summary-kpi-item">
            <span>누적 폐점 매장:</span>
            <strong style="color:#f85149;">${{state.totalClosed}}개</strong>
          </div>
          <div class="summary-kpi-item">
            <span>DT (드라이브스루):</span>
            <strong style="color:#ffa726;">${{dtCount}}개</strong>
          </div>
          <div class="summary-kpi-item">
            <span>리저브 (Reserve):</span>
            <strong style="color:#ffd54f;">${{resCount}}개</strong>
          </div>
        </div>
        <div style="font-size:11px;color:#8b949e;line-height:1.5;padding:6px;">
          ⏱️ 타임라인 날짜가 이동할 때마다 ${{sgg}} 내 매장의 생애주기 지표가 실시간으로 재계산됩니다.
        </div>
      `;
    }}
  }}

  // 6. 슬라이더 및 재생 컨트롤
  function updateSlider(val) {{
    const slider = document.getElementById('timeline-slider');
    slider.value = val;
  }}

  function getStepDelay() {{
    const base = 1000;
    return Math.max(80, base / state.speedMultiplier);
  }}

  function playNext() {{
    if (!state.isPlaying) return;

    if (state.currentIndex < state.events.length) {{
      const ev = state.events[state.currentIndex];
      processEvent(ev, false);
      state.currentIndex++;
      updateSlider(state.currentIndex);

      const delay = getStepDelay();
      state.timer = setTimeout(playNext, delay);
    }} else {{
      pausePlayback();
      showEventBanner('🏁 타임라인 재생 완료 (현재 매장 상태)', 'open');
    }}
  }}

  function startPlayback() {{
    if (state.currentIndex >= state.events.length) {{
      stateAtDate(0);
    }}
    state.isPlaying = true;
    document.getElementById('btn-play').innerText = '❚❚ 일시정지';
    document.getElementById('btn-play').classList.remove('primary');
    playNext();
  }}

  function pausePlayback() {{
    state.isPlaying = false;
    if (state.timer) clearTimeout(state.timer);
    document.getElementById('btn-play').innerText = '▶ 재생';
    document.getElementById('btn-play').classList.add('primary');
  }}

  function togglePlayback() {{
    if (state.isPlaying) pausePlayback();
    else startPlayback();
  }}

  // 7. 이벤트 리스너 바인딩
  function bindControls() {{
    const slider = document.getElementById('timeline-slider');
    slider.max = state.events.length;
    slider.value = 0;

    slider.addEventListener('input', (e) => {{
      pausePlayback();
      const val = parseInt(e.target.value, 10);
      stateAtDate(val);
    }});

    document.getElementById('btn-play').addEventListener('click', togglePlayback);
    
    document.getElementById('btn-start').addEventListener('click', () => {{
      pausePlayback();
      stateAtDate(0);
    }});
    
    document.getElementById('btn-end').addEventListener('click', () => {{
      pausePlayback();
      stateAtDate(state.events.length);
    }});
    
    document.getElementById('btn-prev').addEventListener('click', () => {{
      pausePlayback();
      if (state.currentIndex > 0) {{
        stateAtDate(state.currentIndex - 1);
      }}
    }});
    
    document.getElementById('btn-next').addEventListener('click', () => {{
      pausePlayback();
      if (state.currentIndex < state.events.length) {{
        processEvent(state.events[state.currentIndex], false);
        state.currentIndex++;
        updateSlider(state.currentIndex);
      }}
    }});

    document.querySelectorAll('.speed-btn').forEach(btn => {{
      btn.addEventListener('click', (e) => {{
        document.querySelectorAll('.speed-btn').forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');
        state.speedMultiplier = parseFloat(e.target.dataset.speed);
      }});
    }});

    document.getElementById('chk-trace').addEventListener('change', (e) => {{
      state.showClosedTraces = e.target.checked;
      state.traceMarkers.forEach(m => {{
        if (state.showClosedTraces) {{
          m.addTo(state.map);
        }} else {{
          state.map.removeLayer(m);
        }}
      }});
    }});

    document.getElementById('start-year-lbl').innerText = (DATA.start_date || '2001').slice(0, 4);
    document.getElementById('end-year-lbl').innerText = (DATA.end_date || '2026').slice(0, 4);
  }}

  window.addEventListener('DOMContentLoaded', () => {{
    initMap();
    loadBaseline();
    bindControls();
  }});
</script>
</body>
</html>
"""
    return html_code


def render_timeline_section(
    history_df: pd.DataFrame,
    sido: str,
    sigungu: Optional[str] = None,
):
    """
    Streamlit UI의 지역심층분석 최하단에 타임라인 지도 섹션을 렌더링합니다.
    """
    is_all_sigungu = (
        sigungu is None
        or sigungu.startswith("전체")
        or "전체" in str(sigungu)
    )
    region_title = f"{sido} 전체" if is_all_sigungu else f"{sido} {sigungu}"

    st.markdown("---")
    st.subheader("⏱️ 스타벅스 매장 변화 타임라인")
    st.caption("개점·폐점 이력을 시간순으로 재생하여 지역 내 스타벅스 상권의 확장과 변화를 확인합니다.")

    # 기간 집중 보기 컨트롤 (요구사항 19)
    col_t1, col_t2 = st.columns([3, 1])
    with col_t1:
        period_choice = st.radio(
            "관측 재생 기간",
            options=["전체", "최근 10년", "최근 5년", "최근 3년"],
            index=0,
            horizontal=True,
            key=f"timeline_period_{sido}_{sigungu}",
        )
    with col_t2:
        st.markdown(
            f"<div style='text-align:right;font-size:12px;color:#888;padding-top:14px;'>"
            f"대상: <strong>{region_title}</strong></div>",
            unsafe_allow_html=True,
        )

    # 데이터 구축 및 컴포넌트 렌더링
    payload = build_timeline_payload(
        history_df=history_df,
        sido=sido,
        sigungu=sigungu,
        period=period_choice,
    )

    if "error" in payload:
        st.warning(payload["error"])
        return

    html_content = generate_timeline_html(payload)
    components.html(html_content, height=800, scrolling=False)

    # 하단 분석 통찰 콜아웃 박스 (요구사항 36)
    if "insight_text" in payload:
        st.info(payload["insight_text"])
