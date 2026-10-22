import streamlit as st
import requests
import pandas as pd
import datetime
import pytz

# 앱 제목 설정
st.title("🍿 일일 박스오피스 순위")

# 1. 한국 시간 기준으로 '어제' 날짜 계산하기
kst_timezone = pytz.timezone('Asia/Seoul')
now_kst = datetime.datetime.now(kst_timezone)
yesterday_kst = now_kst - datetime.timedelta(days=1)
yesterday_date = yesterday_kst.date() # 시간 빼고 날짜만 추출

# 💡 [추가] 달력 위젯으로 조회 날짜 선택하기 (기본값과 최대값을 '어제'로 제한)
selected_date = st.date_input(
    "조회할 날짜를 선택하세요",
    value=yesterday_date,
    max_value=yesterday_date
)

# API 요청에 필요한 'YYYYMMDD' 형식으로 변환
target_dt = selected_date.strftime('%Y%m%d')
display_date = selected_date.strftime('%Y년 %m월 %d일')

st.subheader(f"{display_date} 기준")

# 2. 비밀 금고(secrets)에서 API 키 불러오기
try:
    api_key = st.secrets["KOBIS_KEY"]
except KeyError:
    st.error("🚨 API 인증키를 찾을 수 없습니다. Streamlit Cloud의 [Settings] - [Secrets]에 `KOBIS_KEY`를 등록해 주세요.")
    st.stop()

# 3. KOBIS API 요청하기
url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
params = {
    "key": api_key,
    "targetDt": target_dt
}

try:
    response = requests.get(url, params=params)
    response.raise_for_status()
except Exception as e:
    st.error("🚨 영화진흥위원회 서버와 통신하는 데 실패했습니다. 잠시 후 다시 시도해 주세요.")
    st.stop()

# 4. 응답 데이터 처리 및 에러 확인
data = response.json()

if "faultInfo" in data:
    error_message = data["faultInfo"].get("message", "알 수 없는 에러")
    st.error(f"🚨 API 요청이 거절되었습니다. 인증키가 유효한지 확인해 주세요.\n\n에러 내용: {error_message}")
    st.stop()

if "boxOfficeResult" not in data or "dailyBoxOfficeList" not in data["boxOfficeResult"]:
    st.error("🚨 알 수 없는 데이터 구조입니다. API 명세가 변경되었을 수 있습니다.")
    st.stop()

movie_list = data["boxOfficeResult"]["dailyBoxOfficeList"]

# 💡 [추가] 영화 목록이 비어있는 경우 안내 (집계 전)
if not movie_list:
    st.warning(f"📭 {display_date}은(는) 아직 집계 전입니다.")
    st.stop()

# 5. 데이터프레임으로 변환 및 데이터 가공
df = pd.DataFrame(movie_list)

# 숫자로 쓸 데이터들을 정수로 변환
numeric_columns = ['rank', 'rankInten', 'audiCnt', 'audiAcc', 'scrnCnt']
for col in numeric_columns:
    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)

# 💡 [추가] 순위 변동 기호 만들기 (오르면 ▲, 내리면 ▼, 그대로면 -)
def format_trend(x):
    if x > 0:
        return f"▲ {x}"
    elif x < 0:
        return f"▼ {abs(x)}"
    else:
        return "-"

df['순위 변동'] = df['rankInten'].apply(format_trend)

# 💡 [추가] 누적 관객 100만 명 이상 영화 이름 옆에 트로피 붙이기
df['movieNm'] = df.apply(
    lambda row: row['movieNm'] + ' 🏆' if row['audiAcc'] >= 1000000 else row['movieNm'], 
    axis=1
)

# 6. 화면 출력: 1위 영화 지표 카드 (3장)
st.write("---")
st.write("### 🥇 1위 영화")
top_movie = df.iloc[0]

col1, col2, col3 = st.columns(3)
col1.metric(label="영화명", value=top_movie['movieNm'])

# 지표 카드 하단에 들어갈 증감 텍스트 (순위 변동)
delta_text = None
if top_movie['rankInten'] > 0:
    delta_text = f"전일대비 {top_movie['rankInten']} 계단 상승"
elif top_movie['rankInten'] < 0:
    delta_text = f"전일대비 {abs(top_movie['rankInten'])} 계단 하락"

col2.metric(label="일일 관객수", value=f"{top_movie['audiCnt']:,}명", delta=delta_text)
col3.metric(label="누적 관객수", value=f"{top_movie['audiAcc']:,}명")

# 7. 화면 출력: 관객수 상위 5편 막대그래프
st.write("---")
st.write("### 📊 관객수 상위 5편")
top5_df = df.head(5).copy()
top5_df.set_index('movieNm', inplace=True)
st.bar_chart(top5_df['audiCnt'])

# 8. 화면 출력: 전체 영화 데이터 표
st.write("---")
st.write("### 📋 박스오피스 전체 순위표")

# 화면에 보여줄 열만 고르고 순서를 정리합니다.
display_df = df[['rank', '순위 변동', 'movieNm', 'openDt', 'audiCnt', 'audiAcc', 'scrnCnt']].copy()
display_df.columns = ['순위', '순위 변동', '영화명', '개봉일', '관객수', '누적관객', '스크린수']

# 💡 [추가] 표 안의 글자 색상을 바꾸는 함수 (▲는 빨간색, ▼는 파란색)
def color_trend(val):
    if isinstance(val, str):
        if '▲' in val:
            return 'color: red;'
        elif '▼' in val:
            return 'color: blue;'
    return ''

# 판다스 버전에 따라 호환되도록 색상 칠하기(map 또는 applymap) 적용 후, 숫자 포맷팅
try:
    styler = display_df.style.map(color_trend, subset=['순위 변동'])
except AttributeError:
    # 구버전 판다스를 위한 대비책
    styler = display_df.style.applymap(color_trend, subset=['순위 변동'])

formatted_df = styler.format({
    "관객수": "{:,}",
    "누적관객": "{:,}",
    "스크린수": "{:,}"
})

# 깔끔하게 인덱스(행 번호)를 숨기고 너비를 꽉 채워서 표를 그립니다.
st.dataframe(formatted_df, use_container_width=True, hide_index=True)
