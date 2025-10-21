import streamlit as st
import pandas as pd
from datetime import datetime
import numpy as np

df = pd.read_excel("data/KRX_sector_mktcap.xlsx")

# DATE 컬럼 datetime으로 변환
df['DATE'] = df['DATE'].astype(str)
df['DATE'] = pd.to_datetime(df['DATE'], format='%Y%m%d', errors='coerce')

# --- 상단 고정: 제목 ---
st.title("업종별 시가총액 분석 앱")

# --- 상단 고정: 기간 필터 ---
col1, col2 = st.columns(2)

with col1:
    period_unit = st.selectbox(
        "기간 단위", 
        options=["년", "월", "주", "일"]
    )

with col2:
    start_date = pd.to_datetime(df['DATE'].min())
    end_date = pd.to_datetime(df['DATE'].max())
    selected_range = st.date_input(
        "기간",
        [start_date, end_date]
    )

# 선택된 기간에 따라 필터링
filtered_df = df[(df['DATE'] >= pd.to_datetime(selected_range[0])) & 
                 (df['DATE'] <= pd.to_datetime(selected_range[1]))]

# --- 기간 단위 컬럼 생성 ---
filtered_df['YEAR'] = filtered_df['DATE'].dt.year
filtered_df['MONTH'] = filtered_df['DATE'].dt.to_period('M')
filtered_df['WEEK'] = filtered_df['DATE'].dt.to_period('W')

# --- 기간 단위에 따라 aggregate ---
if period_unit == "년":
    agg_df = filtered_df.groupby(['YEAR', 'IDX_IND_NM'])['MKTCAP'].sum().reset_index()
elif period_unit == "월":
    agg_df = filtered_df.groupby(['MONTH', 'IDX_IND_NM'])['MKTCAP'].sum().reset_index()
elif period_unit == "주":
    agg_df = filtered_df.groupby(['WEEK', 'IDX_IND_NM'])['MKTCAP'].sum().reset_index()
else:  # 일 단위
    agg_df = filtered_df.groupby(['DATE', 'IDX_IND_NM'])['MKTCAP'].sum().reset_index()

agg_df = agg_df.rename(columns={
    'IDX_IND_NM': '업종명',
    'MKTCAP': '시가총액'
})

# --- 페이지 선택 ---
page = st.radio(
    "페이지 선택",
    options=["Page 1: Raw Data", "Page 2: 변동성 계산", "Page 3: Top 5 업종"]
)

st.markdown("---")

# 페이지별 표시
if page == "Page 1: Raw Data":
    st.write("Page 1: 선택한 기간 단위별 집계")

    # agg_df 복사본 생성
    raw_df = agg_df.copy()
    
    # 시가총액을 억 단위로 변환
    raw_df['시가총액'] = (raw_df['시가총액'] / 1e8).round().astype(int)
    
    # 컬럼명에 단위 표시
    raw_df = raw_df.rename(columns={'시가총액': '시가총액(억)'})
    
    # 표시
    st.dataframe(raw_df)

elif page == "Page 2: 변동성 계산":
    st.subheader("업종별 시가총액 변동성")

    if agg_df.empty:
        st.warning("선택된 기간에 데이터가 없습니다.")
    else:
        # 기간 단위 컬럼 결정
        period_col = None
        for col in ['YEAR', 'MONTH', 'WEEK', 'DATE']:
            if col in agg_df.columns:
                period_col = col
                break

        # --- End-to-End 변동성 (정수로 반올림) ---
        start_df = agg_df.groupby('업종명').first()['시가총액']
        end_df = agg_df.groupby('업종명').last()['시가총액']
        e2e_vol = ((end_df - start_df) / start_df * 100)
        # 양수는 올림, 음수는 내림 후 int
        e2e_vol = e2e_vol.apply(lambda x: int(np.ceil(x)) if x > 0 else int(np.floor(x))).reset_index()
        e2e_vol.columns = ['업종명', 'End-to-End 변동성(%)']
        st.markdown("### End-to-End 변동성 (%)")
        st.dataframe(e2e_vol.sort_values('End-to-End 변동성(%)', ascending=False))

        # --- Incremental 변동성 (Wide Format, round up/down, int) ---
        inc_wide_list = []
        for sector, group in agg_df.groupby('업종명'):
            group = group.sort_values(period_col)
            prev = group['시가총액'].shift(1)
            inc = ((group['시가총액'] - prev) / prev * 100).iloc[1:].dropna()

            # 양수는 올림, 음수는 내림 후 int
            inc = inc.apply(lambda x: int(np.ceil(x)) if x > 0 else int(np.floor(x)))

            col_names = [f"{group[period_col].iloc[i-1]}→{group[period_col].iloc[i]}" 
                         for i in range(1, len(group))]
            inc_wide_list.append(pd.DataFrame([inc.values], index=[sector], columns=col_names, dtype=int))

        inc_wide_df = pd.concat(inc_wide_list, axis=0)

        # 시간 순서로 컬럼 정렬
        def sort_period_key(col):
            try:
                left, right = col.split('→')
                left_date = pd.Period(left).to_timestamp()
                return left_date
            except Exception:
                return pd.Timestamp.max

        inc_wide_df = inc_wide_df.reindex(sorted(inc_wide_df.columns, key=sort_period_key), axis=1)
        st.markdown("### Incremental 변동성 (%)")
        st.dataframe(inc_wide_df)

        # --- Time Series 그래프 (억 단위, 값/업종 표시) ---
        st.markdown("### 업종별 시가총액 변화 (억 단위)")

        ts_df = filtered_df.copy()
        ts_df['업종명'] = ts_df['IDX_IND_NM']

        # 기간 단위 index 변환 및 문자열 포맷
        if period_unit == "년":
            ts_df['period_index'] = ts_df['YEAR'].astype(str)
        elif period_unit == "월":
            ts_df['period_index'] = ts_df['MONTH'].dt.to_timestamp().dt.strftime('%Y-%m')
        elif period_unit == "주":
            ts_df['period_index'] = ts_df['WEEK'].dt.to_timestamp().dt.strftime('%Y-%m-%d')
        else:
            ts_df['period_index'] = ts_df['DATE'].dt.strftime('%Y-%m-%d')

        ts_df = ts_df.groupby(['period_index', '업종명'])['MKTCAP'].sum().reset_index()
        ts_df = ts_df.pivot(index='period_index', columns='업종명', values='MKTCAP') / 1e8  # 억 단위
        ts_df = ts_df.sort_index()
        st.line_chart(ts_df)


elif page == "Page 3: Top 5 업종":
    st.subheader("Top 5 성장 변동성 업종 시각화")

    if agg_df.empty:
        st.warning("선택된 기간에 데이터가 없습니다.")
    else:
        # --- 기간 단위 컬럼 결정 ---
        period_col = None
        for col in ['YEAR', 'MONTH', 'WEEK', 'DATE']:
            if col in agg_df.columns:
                period_col = col
                break

        # --- End-to-End 변동성 계산 ---
        start_df = agg_df.groupby('업종명').first()['시가총액']
        end_df = agg_df.groupby('업종명').last()['시가총액']
        e2e_vol = ((end_df - start_df) / start_df * 100)
        # 양수는 올림, 음수는 내림 후 int
        e2e_vol = e2e_vol.apply(lambda x: int(np.ceil(x)) if x > 0 else int(np.floor(x))).reset_index()
        e2e_vol.columns = ['업종명', 'End-to-End 변동성(%)']

        # --- Top 5 성장 변동성 업종 선택 (+ 변동성 기준) ---
        top5_up = e2e_vol.sort_values('End-to-End 변동성(%)', ascending=False).head(5)
        st.markdown("### Top 5 성장 변동성 업종")
        st.dataframe(top5_up)

        # --- Top 5 업종 시가총액 Time Series ---
        ts_df = filtered_df.copy()
        ts_df['업종명'] = ts_df['IDX_IND_NM']

        # 기간 단위 index 변환 및 문자열 포맷
        if period_unit == "년":
            ts_df['period_index'] = ts_df['YEAR'].astype(str)
        elif period_unit == "월":
            ts_df['period_index'] = ts_df['MONTH'].dt.to_timestamp().dt.strftime('%Y-%m')
        elif period_unit == "주":
            ts_df['period_index'] = ts_df['WEEK'].dt.to_timestamp().dt.strftime('%Y-%m-%d')
        else:
            ts_df['period_index'] = ts_df['DATE'].dt.strftime('%Y-%m-%d')

        # Top 5 업종만 필터링
        ts_df = ts_df[ts_df['업종명'].isin(top5_up['업종명'])]

        ts_df = ts_df.groupby(['period_index', '업종명'])['MKTCAP'].sum().reset_index()
        ts_df = ts_df.pivot(index='period_index', columns='업종명', values='MKTCAP') / 1e8  # 억 단위
        ts_df = ts_df.sort_index()

        st.markdown("### Top 5 업종 시가총액 변화 (억 단위)")
        st.line_chart(ts_df)
