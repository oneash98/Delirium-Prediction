# 2_data_transform.ipynb 설명

`src/2_data_transform.ipynb`는 `1_data_extraction.ipynb`의 산출물을 1시간 단위 hourly timeseries로 정리하고, cohort 기준 적용, EDA, subject-level train/test split까지 수행합니다.

이 노트북은 모델 입력 feature를 최종 생성하지 않습니다. Observation window별 mean/median/sd 집계, feature 선택, train 기준 imputation은 다음 모델링 단계에서 수행합니다.

## 입력 파일

`processed/extraction/`:

- `all_events_long.csv`: chart, lab, eMAR medication point event가 통합된 long-format 이벤트.
- `adm_pat_icu.csv`: ICU stay, admission, patient 기본 정보.
- `procedure_selected.csv`: procedure/device 이벤트.

## 주요 산출물

`processed/transform/`:

- `all_events_filtered.csv`: 값 숫자화와 단위 변환이 반영된 chart/lab/medication long-format 이벤트.
- `all_events_timeseries.csv`: chart/lab/medication point event를 60분 bin으로 pivot한 원본 hourly timeseries.
- `all_timeseries.csv`: procedure/device exposure와 weight/height static fill까지 반영한 전체 hourly timeseries.
- `hourly_timeseries_60min.csv`: cohort criteria 통과 후 `ever_delirium`, `split`이 붙은 hourly timeseries.
- `assessment_index_60min.csv`: 섬망 평가 시점 인덱스. 컬럼은 `subject_id`, `stay_id`, `assessment_bin`, `delirium`, `ever_delirium`, `split`.
- `cohort_attrition.csv`: inclusion/exclusion criteria별 subject, admission, stay, timeseries row, assessment row 감소 요약.
- `train_subject_ids.csv`, `test_subject_ids.csv`: subject-level random split 결과.

다음 파일은 현재 transform 흐름에서 생성하지 않습니다:

- `timeseries_imputed.csv`
- `final_dataset.csv`
- `assessment_dataset_60min.csv`

## 전체 흐름

1. 추출 단계의 `all_events_long.csv`와 `adm_pat_icu.csv`를 불러옵니다.
2. 시간 컬럼을 datetime으로 변환합니다.
3. 원본 `value`를 `value_str`로 보존하고, `valuenum` 또는 문자열 규칙을 통해 숫자형 `value`를 만듭니다.
4. 온도, 체중, 키 등 단위를 통일합니다.
5. ICU 입실 후 경과시간 `hours`와 60분 단위 `bin`을 계산합니다.
6. `stay_id`, `bin` 단위로 chart/lab 이벤트를 wide-format hourly timeseries로 pivot합니다.
7. `delirium` outcome을 그대로 유지합니다. 컬럼명을 `Delirium`으로 바꾸지 않습니다.
8. medication point event는 pivot 결과에서 실제 투약이 기록된 hour만 `1`로 유지하고, event가 없는 hour는 `0`으로 채웁니다.
9. procedure/device 이벤트는 interval이 겹치는 hourly bin으로 펼쳐 병합합니다.
10. `weight`, `height`만 stay별 첫 non-null 측정값으로 전체 hourly bin에 채웁니다.
11. inclusion/exclusion criteria를 적용하고 `cohort_attrition.csv`를 저장합니다.
12. subject-level `ever_delirium` label을 생성합니다.
13. 환자 기본정보, delirium assessment 주기, lab 측정 주기 EDA를 수행합니다.
14. subject-level 80/20 random train/test split을 만들고 산출물을 저장합니다.

## Outcome 정책

`delirium`은 `chartevents`의 `Delirium assessment`에서 온 assessment-level outcome입니다.

- `Positive`는 `1`
- `Negative`는 `0`
- `UTA` 또는 기타 해석 불가능한 값은 `NaN`
- 평가가 시행되지 않은 hourly bin도 `NaN`

`delirium`의 `NaN`은 단순 feature 결측이 아니라 평가 미시행 시간을 의미합니다.

## ever_delirium

`ever_delirium`은 EDA와 subject-level split 확인을 위한 subject-level label입니다.

- 같은 `subject_id`에서 `delirium == 1`이 한 번이라도 있으면 `1`
- 그렇지 않으면 `0`

`ever_delirium`은 assessment-level outcome인 `delirium`을 대체하지 않습니다.

## Medication/procedure 처리

Medication point event:

- medication은 `all_events_long.csv`에 포함된 eMAR point event를 사용합니다.
- extraction 단계에서 이미 투약 관련 `event_txt`만 필터링되어 있습니다.
- transform 단계에서는 실제 투약 event가 기록된 `charttime`의 hour만 `1`입니다.
- 같은 stay-bin-feature에 여러 투약 event가 있으면 pivot의 `max`로 `1`이 됩니다.
- event가 없는 hour의 medication feature는 `0`으로 채웁니다.
- observation window 안 노출 여부는 모델링 단계에서 window 길이에 맞춰 계산합니다.

Procedure/device exposure:

- `procedure_selected.csv`를 사용합니다.
- procedure 시작/종료 시간이 현재 hour bin과 겹치면 exposure `1`로 표시합니다.
- 종료 시간이 없으면 시작 시간을 종료 시간으로 사용합니다.
- ICU stay의 `outtime`을 넘어가는 bin은 잘라냅니다.

## Weight/height 처리

`weight`, `height`만 stay 안에서 첫 non-null 측정값을 전체 시간축에 확장합니다.

- 첫 측정값이 있는 stay: 모든 hourly bin에 같은 값이 들어갑니다.
- 첫 측정값이 없는 stay: 그대로 `NaN`입니다.
- vital, lab, neuro 변수에는 hourly forward-fill, backward-fill, median imputation을 적용하지 않습니다.

## Inclusion/Exclusion Criteria와 Cohort Attrition

Criteria는 hourly timeseries 생성과 exposure 병합 후 적용합니다.

적용 순서:

1. 전체 ICU stays from extraction
2. 성인 환자: `anchor_age >= 18`
3. 유효한 ICU 입실/퇴실 시간: `intime`, `outtime` 존재
4. 양수 ICU LOS: `icu_los_hours > 0`
5. 8시간 이상 ICU LOS: `icu_los_hours >= 8`
6. Delirium assessment 존재

`cohort_attrition.csv`에는 각 단계의 `n_subjects`, `n_hadm`, `n_stays`, `timeseries_rows`, `assessment_rows`, 이전 단계 대비 제거 stay 수, 초기 대비 stay 비율이 저장됩니다.

## EDA

EDA는 feature engineering 전 데이터 구조 확인에 초점을 둡니다.

Patient basics and ever_delirium:

- subject 수, stay 수
- subject당 ICU stay 수
- Parkinson cohort 기간
- subject-level `ever_delirium` 분포
- age, gender, race, admission_type, ICU LOS 요약
- `ever_delirium`별 기본정보 비교

Delirium assessment cadence:

- assessment row 수
- stay/subject별 assessment count
- stay 안에서 assessment 간격 median/IQR
- ICU 입실 후 첫 assessment까지 걸린 시간
- ICU hour/day당 assessment 빈도

Lab measurement cadence:

- lab feature별 측정 count
- lab feature별 stay/subject coverage
- lab feature별 stay 내부 측정 간격 median/IQR
- 어떤 lab이든 측정된 시점 기준의 전체 lab 간격

## Train/Test Split

Split은 subject 단위 random split입니다.

- `TEST_SIZE = 0.2`
- `RANDOM_STATE = 42`
- unstratified
- 같은 `subject_id`의 모든 stay와 assessment는 같은 split에 속합니다.

Split 결과는 다음에 반영됩니다:

- `hourly_timeseries_60min.csv`의 `split` 컬럼
- `assessment_index_60min.csv`의 `split` 컬럼
- `train_subject_ids.csv`
- `test_subject_ids.csv`

## 모델링 단계로 넘긴 것

다음 작업은 이 transform 노트북에서 수행하지 않습니다.

- observation window 길이 후보 탐색
- window별 mean/median/sd feature 생성
- train set 기준 변수 제외 또는 feature selection
- train set 기준 imputer fitting
- 모델 입력용 최종 tabular dataset 생성
- 모델 학습, 검증, 평가

이 내용은 `docs/3_modeling_plan.md`에 정리합니다.

## 주의사항

- `delirium` 컬럼명은 lowercase로 유지합니다.
- 앞선 셀에서 만들어져야 하는 컬럼은 뒤 셀에서 존재한다고 가정합니다.
- hourly `delirium`의 `NaN`은 평가 미시행 시간입니다.
- transform 단계에서는 lab/vital/neuro feature를 보간하지 않습니다.
- 모델 성능 비교에 필요한 window feature와 imputation은 train/test split 이후 모델링 단계에서 train 기준으로 수행해야 합니다.
