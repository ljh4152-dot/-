import streamlit as st
import requests
import pandas as pd
import datetime
import pytz

# 앱 제목 설정
st.title("🍿 일일 박스오피스 순위")

# 1. 한국 시간 기준으로 '어제' 날짜 계산하기
# 배포 서버의 시간이 한국과 다를 수 있으므로 명시적으로 한국 시간대(KST)를 사용합니다.
kst_timezone = pytz.timezone('Asia/Seoul')
now_kst = datetime.datetime.now(kst_timezone)
yesterday_kst = now_kst - datetime.timedelta(days=1)

# API 요청에 필요한 'YYYYMMDD' 형식으로 변환
target_dt = yesterday_kst.strftime('%Y%m%d')
display_date = yesterday_kst.strftime('%Y년 %m월 %d일')

st.subheader(f"{display_date} 기준")

# 2. 비밀 금고(secrets)에서 API 키 불러오기
try:
    api_key = st.secrets["KOBIS_KEY"]
except KeyError:
    # 키가 없을 경우 안내 메시지 출력 후 앱 실행 중단
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
    # HTTP 에러가 발생했는지 확인
    response.raise_for_status()
except Exception as e:
    st.error("🚨 영화진흥위원회 서버와 통신하는 데 실패했습니다. 잠시 후 다시 시도해 주세요.")
    st.stop()

# 4. 응답 데이터 처리 및 에러 확인
data = response.json()

# KOBIS API는 키가 틀려도 200 상태코드와 함께 faultInfo 상자를 보냅니다.
if "faultInfo" in data:
    error_message = data["faultInfo"].get("message", "알 수 없는 에러")
    st.error(f"🚨 API 요청이 거절되었습니다. 인증키가 유효한지 확인해 주세요.\n\n에러 내용: {error_message}")
    st.stop()

# 정상적인 응답 구조인지 확인
if "boxOfficeResult" not in data or "dailyBoxOfficeList" not in data["boxOfficeResult"]:
    st.error("🚨 알 수 없는 데이터 구조입니다. API 명세가 변경되었을 수 있습니다.")
    st.stop()

movie_list = data["boxOfficeResult"]["dailyBoxOfficeList"]

# 영화 목록이 비어있는 경우 (아직 집계 전이거나 데이터가 없는 날)
if not movie_list:
    st.warning(f"📭 {display_date}의 박스오피스 데이터가 아직 집계되지 않았거나 제공되지 않습니다.")
    st.stop()

# 5. 데이터프레임으로 변환 및 데이터 가공
df = pd.DataFrame(movie_list)

# API에서 숫자가 모두 문자열로 오기 때문에 정수형으로 변환해 줍니다.
numeric_columns = ['rank', 'rankInten', 'audiCnt', 'audiAcc', 'scrnCnt']
for col in numeric_columns:
    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)

# 6. 화면 출력: 1위 영화 지표 카드 (3장)
st.write("---")
st.write("### 🥇 1위 영화")
top_movie = df.iloc[0] # 순위가 가장 높은 첫 번째 데이터

col1, col2, col3 = st.columns(3)
col1.metric(label="영화명", value=top_movie['movieNm'])
col2.metric(label="일일 관객수", value=f"{top_movie['audiCnt']:,}명", delta=f"전일대비 순위 {top_movie['rankInten']}" if top_movie['rankInten'] != 0 else None)
col3.metric(label="누적 관객수", value=f"{top_movie['audiAcc']:,}명")

# 7. 화면 출력: 관객수 상위 5편 막대그래프
st.write("---")
st.write("### 📊 관객수 상위 5편")
top5_df = df.head(5).copy()
# 그래프의 X축에 영화명을 표시하기 위해 인덱스로 설정합니다.
top5_df.set_index('movieNm', inplace=True)
# 스트림릿 내장 차트로 일일 관객수를 그립니다.
st.bar_chart(top5_df['audiCnt'])

# 8. 화면 출력: 전체 영화 데이터 표
st.write("---")
st.write("### 📋 박스오피스 전체 순위표")

# 화면에 보여줄 열만 선택하고 이름을 한글로 보기 좋게 변경합니다.
display_df = df[['rank', 'movieNm', 'openDt', 'audiCnt', 'audiAcc', 'scrnCnt']].copy()
display_df.columns = ['순위', '영화명', '개봉일', '관객수', '누적관객', '스크린수']

# 천 단위 콤마 포맷팅을 적용하여 보기 좋게 출력합니다.
formatted_df = display_df.style.format({
    "관객수": "{:,}",
    "누적관객": "{:,}",
    "스크린수": "{:,}"
})

st.dataframe(formatted_df, use_container_width=True, hide_index=True)
