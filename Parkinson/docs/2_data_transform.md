# 2_data_transform.ipynb 설명

`src/2_data_transform.ipynb`는 `1_data_extraction.ipynb`의 산출물을 1시간 단위 hourly timeseries로 정리하고 cohort 기준까지 적용합니다. EDA는 `src/3_eda.ipynb`, subject-level train/test split은 `src/4_modeling.ipynb`에서 수행합니다.

문서 순서는 실제 노트북의 마크다운 소제목 순서를 따릅니다.

## 데이터 로드

입력 파일은 `processed/extraction/` 아래 산출물입니다.

- `all_events_long.csv`: chart, lab, eMAR medication point event가 통합된 long-format 이벤트.
- `adm_pat_icu.csv`: ICU stay, admission, patient 기본 정보.
- `procedure_selected.csv`: procedure/device 이벤트.

주요 출력 파일은 `processed/transform/`에 저장됩니다.

- `all_events_filtered.csv`: 값 숫자화와 단위 변환이 반영된 chart/lab/medication long-format 이벤트.
- `all_events_timeseries.csv`: chart/lab/medication point event를 60분 bin으로 pivot한 원본 hourly timeseries.
- `all_timeseries.csv`: procedure/device exposure와 weight/height static fill까지 반영한 전체 hourly timeseries.
- `hourly_timeseries_60min.csv`: cohort criteria 통과 후 `ever_delirium`이 붙은 hourly timeseries. `split` 컬럼은 `4_modeling.ipynb` 실행 후 추가됩니다.
- `assessment_index_60min.csv`: 섬망 평가 시점 인덱스. transform 직후 컬럼은 `subject_id`, `stay_id`, `assessment_bin`, `delirium`, `ever_delirium`입니다. `split` 컬럼은 `4_modeling.ipynb` 실행 후 추가됩니다.
- `cohort_final.csv`: cohort criteria를 통과한 stay-level cohort table.
- `cohort_attrition.csv`: inclusion/exclusion criteria별 subject, admission, stay, timeseries row, assessment row 감소 요약.

현재 transform 흐름에서는 `timeseries_imputed.csv`, `final_dataset.csv`, `assessment_dataset_60min.csv`를 생성하지 않습니다.

## VALUE 변환 (문자열 → 숫자)

원본 `value`는 `value_str`로 보존하고, `valuenum` 또는 문자열 규칙을 통해 숫자형 `value`를 만듭니다.

`delirium`은 `chartevents`의 `Delirium assessment`에서 온 assessment-level outcome입니다.

- `Positive`는 `1`
- `Negative`는 `0`
- `UTA` 또는 기타 해석 불가능한 값은 `NaN`
- 평가가 시행되지 않은 hourly bin도 `NaN`

`delirium`의 `NaN`은 단순 feature 결측이 아니라 평가 미시행 시간을 의미합니다.

## 단위 변환

온도, 체중, 키 등 단위를 통일하고 `all_events_filtered.csv`를 저장합니다.

- Fahrenheit temperature는 Celsius로 변환합니다.
- Admission Weight (lbs.)는 kg로 변환합니다.
- `Daily Weight`는 catalog에서 기존 `weight` feature로 통합되어 kg 단위로 처리됩니다.
- inch height는 cm로 변환합니다.

## 시간 계산 (ICU 입실 기준)

`adm_pat_icu`의 ICU 입실/퇴실 정보를 붙이고, ICU 입실 후 경과시간 `hours`와 60분 단위 `bin`을 계산합니다.

이후 cohort 기준에서 사용하는 `icu_los_hours`, `hours >= 24` 조건은 이 시간축을 기준으로 해석합니다.

## 60분 비닝 및 피봇 (최종 시계열)

`stay_id`, `bin` 단위로 long-format event를 wide-format hourly timeseries로 pivot합니다.

- 같은 stay-bin-feature에 여러 값이 있으면 `max`를 사용합니다.
- `delirium` outcome은 lowercase 컬럼명으로 유지합니다.
- medication point event는 실제 투약 event가 기록된 `charttime`의 hour만 `1`입니다.
- event가 없는 hour의 medication feature는 `0`으로 채웁니다.

## 처치/장치 노출 병합

`procedure_selected.csv`를 사용해 procedure/device interval과 겹치는 hourly bin을 exposure `1`로 표시합니다.

- 종료 시간이 없으면 시작 시간을 종료 시간으로 사용합니다.
- ICU stay의 `outtime`을 넘어가는 bin은 잘라냅니다.
- observation window 안 노출 여부는 모델링 단계에서 window 길이에 맞춰 계산합니다.

## 기본정보 보간

`weight`, `height`만 stay 안에서 첫 non-null 측정값을 전체 시간축에 확장합니다.

- 첫 측정값이 있는 stay: 모든 hourly bin에 같은 값이 들어갑니다.
- 첫 측정값이 없는 stay: 그대로 `NaN`입니다.
- vital, lab, neuro 변수에는 hourly forward-fill, backward-fill, median imputation을 적용하지 않습니다.

## 포함/제외 기준 적용

Criteria는 hourly timeseries 생성과 exposure 병합 후 적용합니다.

적용 순서:

1. 전체 ICU stays from extraction
2. 양수 ICU LOS: `icu_los_hours > 0`
3. 24시간 이상 ICU LOS: `icu_los_hours >= 24`
4. ICU 입실 24시간 이후 Delirium assessment 존재: `delirium` non-null and `hours >= 24`

`cohort_attrition.csv`에는 각 단계의 `n_subjects`, `n_hadm`, `n_stays`, `timeseries_rows`, `assessment_rows`, 이전 단계 대비 제거 stay 수, 초기 대비 stay 비율이 저장됩니다.

## ever_delirium 라벨 생성

`ever_delirium`은 EDA와 subject-level split 확인을 위한 subject-level label입니다.

- 같은 `subject_id`에서 `delirium == 1`이 한 번이라도 있으면 `1`
- 그렇지 않으면 `0`

`ever_delirium`은 assessment-level outcome인 `delirium`을 대체하지 않습니다.

## 산출물 저장

다음 산출물을 저장합니다.

- `hourly_timeseries_60min.csv`
- `assessment_index_60min.csv`
- `cohort_final.csv`
- `cohort_attrition.csv`

`assessment_index_60min.csv`는 섬망 평가가 실제로 시행된 시점만 모아둔 assessment-level index입니다. 각 행은 모델링 단계에서 예측 대상이 되는 평가 시점 1건이며, `assessment_bin` 직전 observation window를 `hourly_timeseries_60min.csv`에서 가져와 feature를 만들게 됩니다.

## 다음 단계

- `3_eda.ipynb`: 환자 기본정보, delirium assessment 주기, lab 측정 주기 EDA를 수행합니다.
- `4_modeling.ipynb`: subject-level train/test split을 만들고, 이후 observation window feature와 모델링 입력 준비를 수행합니다.

모델 성능 비교에 필요한 window feature와 imputation은 `4_modeling.ipynb`의 train/test split 이후 train 기준으로 수행해야 합니다.
