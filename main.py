import streamlit as st
import requests
import pandas as pd
import datetime
import pytz
import plotly.express as px  # 파이 차트를 그리기 위한 라이브러리 추가

# 앱 제목 설정 (페이지 탭 이름과 레이아웃 설정)
st.set_page_config(page_title="박스오피스", page_icon="🍿", layout="wide")
st.title("🍿 일일 박스오피스 순위")

# 1. 한국 시간 기준으로 '어제' 날짜 계산하기
kst_timezone = pytz.timezone('Asia/Seoul')
now_kst = datetime.datetime.now(kst_timezone)
yesterday_kst = now_kst - datetime.timedelta(days=1)
yesterday_date = yesterday_kst.date()

# 💡 [추가] 화면 좌측 사이드바에 달력 배치하기
with st.sidebar:
    st.header("📅 날짜 선택")
    selected_date = st.date_input(
        "조회할 날짜를 고르세요",
        value=yesterday_date,
        max_value=yesterday_date
    )
    st.caption("※ 오늘 날짜의 데이터는 내일 발표됩니다.")

target_dt = selected_date.strftime('%Y%m%d')
display_date = selected_date.strftime('%Y년 %m월 %d일')

st.subheader(f"📊 {display_date} 기준")

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

if not movie_list:
    st.warning(f"📭 {display_date}은(는) 아직 집계 전입니다.")
    st.stop()

# 5. 데이터프레임으로 변환 및 데이터 가공
df = pd.DataFrame(movie_list)

numeric_columns = ['rank', 'rankInten', 'audiCnt', 'audiAcc', 'scrnCnt']
for col in numeric_columns:
    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)

# 매출 점유율(salesShare)을 실수(float)로 변환
df['salesShare'] = pd.to_numeric(df['salesShare'], errors='coerce').fillna(0.0)

def format_trend(x):
    if x > 0:
        return f"▲ {x}"
    elif x < 0:
        return f"▼ {abs(x)}"
    else:
        return "-"

df['순위 변동'] = df['rankInten'].apply(format_trend)

# 💡 [추가] 신규 진입 영화는 🆕, 100만 돌파는 🏆 이모지 붙이기
def format_movie_name(row):
    name = row['movieNm']
    if row['rankOldAndNew'] == 'NEW':
        name = "🆕 " + name
    if row['audiAcc'] >= 1000000:
        name = name + " 🏆"
    return name

df['movieNm'] = df.apply(format_movie_name, axis=1)

# 6. 화면 출력: 1위 영화 지표 카드
st.write("---")
st.write("### 🥇 1위 영화")
top_movie = df.iloc[0]

col1, col2, col3 = st.columns(3)
col1.metric(label="영화명", value=top_movie['movieNm'])

delta_text = None
if top_movie['rankInten'] > 0:
    delta_text = f"전일대비 {top_movie['rankInten']} 계단 상승"
elif top_movie['rankInten'] < 0:
    delta_text = f"전일대비 {abs(top_movie['rankInten'])} 계단 하락"

col2.metric(label="일일 관객수", value=f"{top_movie['audiCnt']:,}명", delta=delta_text)
col3.metric(label="누적 관객수", value=f"{top_movie['audiAcc']:,}명")

# 7. 화면 출력: 차트 영역 (2단 나누기)
st.write("---")
# 화면을 반으로 나누어 왼쪽엔 막대그래프, 오른쪽엔 파이 차트를 배치합니다.
chart_col1, chart_col2 = st.columns(2)

top5_df = df.head(5).copy()

with chart_col1:
    st.write("#### 📊 관객수 상위 5편")
    bar_df = top5_df.set_index('movieNm')
    st.bar_chart(bar_df['audiCnt'])

with chart_col2:
    st.write("#### 🥧 상위 5편 매출 점유율")
    # 💡 [추가] Plotly를 이용한 도넛 형태의 파이 차트
    fig = px.pie(top5_df, values='salesShare', names='movieNm', hole=0.4)
    fig.update_traces(textposition='inside', textinfo='percent+label')
    # 범례 숨기기 및 여백 줄이기
    fig.update_layout(showlegend=False, margin=dict(t=0, b=0, l=0, r=0))
    st.plotly_chart(fig, use_container_width=True)

# 8. 화면 출력: 전체 영화 데이터 표
st.write("---")
st.write("### 📋 박스오피스 전체 순위표")

display_df = df[['rank', '순위 변동', 'movieNm', 'openDt', 'audiCnt', 'audiAcc', 'salesShare', 'scrnCnt']].copy()
display_df.columns = ['순위', '순위 변동', '영화명', '개봉일', '관객수', '누적관객', '매출점유율(%)', '스크린수']

def color_trend(val):
    if isinstance(val, str):
        if '▲' in val:
            return 'color: red;'
        elif '▼' in val:
            return 'color: blue;'
    return ''

try:
    styler = display_df.style.map(color_trend, subset=['순위 변동'])
except AttributeError:
    styler = display_df.style.applymap(color_trend, subset=['순위 변동'])

# 매출 점유율 퍼센트(%) 포맷팅 추가
formatted_df = styler.format({
    "관객수": "{:,}",
    "누적관객": "{:,}",
    "스크린수": "{:,}",
    "매출점유율(%)": "{:.1f}%"
})

st.dataframe(formatted_df, use_container_width=True, hide_index=True)
