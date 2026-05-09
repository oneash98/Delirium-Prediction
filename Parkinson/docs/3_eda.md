# 3_eda.ipynb 설명

`src/3_eda.ipynb`는 `2_data_transform.ipynb`가 만든 cohort 산출물을 읽어 feature engineering 전 데이터 구조를 확인합니다. 이 노트북은 산출 CSV를 새로 만들거나 train/test split을 생성하지 않습니다.

## 입력 파일

`processed/transform/`:

- `hourly_timeseries_60min.csv`: cohort criteria를 통과한 hourly timeseries.
- `cohort_final.csv`: cohort criteria를 통과한 stay-level cohort table.
- `cohort_attrition.csv`: inclusion/exclusion criteria별 attrition table.
- `all_events_filtered.csv`: lab 측정 주기 확인에 사용하는 long-format event table.

## 노트북 순서

아래 섹션은 `src/3_eda.ipynb`의 마크다운 소제목 순서를 따릅니다.

| 노트북 소제목 | 확인 내용 |
| --- | --- |
| `## EDA: 환자 기본정보와 ever_delirium` | subject/stay 수, cohort 기간, `ever_delirium` 분포, 기본정보 요약 |
| `## EDA: 섬망 평가 주기` | assessment count, interval, first assessment hour, assessment frequency |
| `## EDA: 검사실(lab) 측정 주기` | lab feature별 측정 수, coverage, 측정 간격 |

## EDA: 환자 기본정보와 ever_delirium

- subject 수, stay 수
- subject당 ICU stay 수
- Parkinson cohort 기간
- subject-level `ever_delirium` 분포
- age, gender, race, admission_type, ICU LOS 요약
- `ever_delirium`별 기본정보 비교

## EDA: 섬망 평가 주기

- assessment row 수
- stay/subject별 assessment count
- stay 안에서 assessment 간격 median/IQR
- ICU 입실 후 첫 assessment까지 걸린 시간
- ICU hour/day당 assessment 빈도

## EDA: 검사실(lab) 측정 주기

- lab feature별 측정 count
- lab feature별 stay/subject coverage
- lab feature별 stay 내부 측정 간격 median/IQR
- 어떤 lab이든 측정된 시점 기준의 전체 lab 간격

## 주의사항

- EDA는 전체 cohort의 관측 패턴을 확인하기 위한 단계입니다.
- 실제 feature 제외, missingness threshold, imputation 값 결정은 `4_modeling.ipynb`에서 train set 기준으로 수행합니다.
