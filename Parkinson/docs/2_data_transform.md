# 2_data_transform.ipynb 설명

`src/2_data_transform.ipynb`는 `1_data_extraction.ipynb`의 산출물을 숫자화, 단위 통일, ICU 입실 기준 12시간 구간 라벨링, charttime 기준 wide 변환, cohort 기준 적용 산출물로 변환합니다. EDA는 `src/3_eda.ipynb`, subject-level train/test split과 LSTM sequence index 생성은 `src/4_train_test_construction.ipynb`에서 수행합니다.

문서 순서는 실제 노트북의 마크다운 소제목 순서를 따릅니다.

## 데이터 로드

입력 파일은 `processed/extraction/` 아래 산출물입니다.

- `all_events_long.csv`: chart, lab, eMAR medication point event가 통합된 long-format 이벤트.
- `adm_pat_icu.csv`: ICU stay, admission, patient 기본 정보.
- `procedure_selected.csv`: procedure/device interval 이벤트.

주요 출력 파일은 `processed/transform/`에 저장됩니다.

- `all_events_filtered.csv`: 값 숫자화와 단위 변환이 반영된 chart/lab/medication long-format 이벤트.
- `all_events_12h_long.csv`: 전체 ICU stay의 chart/lab/medication event에 12시간 `bin`, `hours` 라벨을 붙인 long-format 이벤트. procedure/device row는 포함하지 않습니다.
- `all_events_12h_wide_by_charttime.csv`: 전체 ICU stay의 charttime 기준 wide table. 같은 `stay_id`/`charttime`에 측정된 feature가 같은 row에 들어가고, 측정되지 않은 feature는 `NaN`입니다. procedure/device exposure는 해당 charttime이 interval 안에 있으면 `1`, 아니면 `0`입니다.
- `all_events_12h_binned.csv`: 전체 ICU stay의 12시간 bin-level wide table. `extraction_variable_catalog.csv`의 `binning` 규칙에 따라 aggregation, most recent, at least once, static feature를 생성합니다.
- `events_12h_long.csv`: cohort criteria 통과 후 long-format 이벤트.
- `events_12h_wide_by_charttime.csv`: cohort criteria 통과 후 charttime 기준 wide table.
- `events_12h_binned.csv`: cohort criteria 통과 후 12시간 bin-level wide table.
- `assessment_index_12h.csv`: 섬망 평가 시점 인덱스. transform 직후 컬럼은 `subject_id`, `hadm_id`, `stay_id`, `charttime`, `assessment_bin`, `assessment_hours`, `delirium`, `value_str`, `ever_delirium`입니다.
- `cohort_final.csv`: cohort criteria를 통과한 stay-level cohort table. extraction 단계에서 `specialty`가 생성되면 그대로 포함합니다.
- `cohort_attrition.csv`: inclusion/exclusion criteria별 subject, admission, stay, 12시간 window 수 감소 요약.
- `data_distribution_summary_12h.txt`: 현재 notebook에서 확인 가능한 row count, source/bin/delirium 분포, height/weight coverage, procedure exposure count, cohort attrition, delirium assessment 간격 요약.

현재 transform 흐름에서는 `all_timeseries.csv`, `timeseries_wide.csv`, `timeseries_imputed.csv`, `final_dataset.csv`, `assessment_dataset_60min.csv`, `hourly_timeseries_60min.csv`, `assessment_index_60min.csv`를 생성하지 않습니다.

## VALUE 변환 (문자열 → 숫자)

원본 `value`는 `value_str`로 보존하고, `valuenum` 또는 문자열 규칙을 통해 숫자형 `value`를 만듭니다.

`delirium` 원천값은 `chartevents`의 `Delirium assessment`에서 온 assessment-level outcome입니다.

- `Positive`는 `1`
- `Negative`는 `0`
- `UTA` 또는 기타 해석 불가능한 값은 `NaN`
- wide table의 `delirium`은 12시간 `stay_id`/`bin` 단위 label입니다. 해당 bin 안 assessment 중 하나라도 `1`이면 `1`, assessment는 있지만 모두 `0`이면 `0`, assessment 자체가 없으면 `NaN`입니다.

wide table에서 `delirium`의 `NaN`은 단순 feature 결측이 아니라 해당 12시간 bin에 평가가 없었음을 의미합니다. 실제 assessment charttime의 원래 row는 long-format event와 `assessment_index_12h.csv`에서 확인합니다.

## 단위 변환

온도, 체중, 키 등 단위를 통일하고 `all_events_filtered.csv`를 저장합니다.

- Fahrenheit temperature는 Celsius로 변환합니다.
- Admission Weight (lbs.)는 kg로 변환합니다.
- `Daily Weight`는 catalog에서 기존 `weight` feature로 통합되어 kg 단위로 처리됩니다.
- inch height는 cm로 변환합니다.

## Delirium assessment 간격 확인

단위 변환 이후, 시간 계산 전에 `feature_name == 'delirium'`인 assessment timepoint를 `stay_id`, `charttime` 기준으로 정렬합니다.

- 동일 `stay_id`/`charttime` 중복은 하나의 assessment timepoint로 간주합니다.
- 같은 stay 안의 연속 assessment 간격을 시간 단위로 계산합니다.
- 전체 mean/median 및 stay-level interval 요약을 출력합니다.

## 시간 계산 (ICU 입실 기준)

`adm_pat_icu`의 ICU 입실/퇴실 정보를 붙이고, ICU 입실 후 실제 경과시간으로 12시간 구간 라벨을 만듭니다.

- `bin`: `1, 2, 3, 4, ...`
- `hours`: `12, 24, 36, 48, ...`
- `hours == bin * 12`

경계 처리는 `(0, 12]`, `(12, 24]`, `(24, 36]`처럼 구간 끝 시점 라벨을 사용합니다. 예를 들어 ICU 입실 후 정확히 12시간째 event는 `bin = 1`, `hours = 12`입니다.

## 12시간 구간 라벨링 (long-format events)

chart/lab/eMAR medication event row는 집계하지 않고 유지합니다.

- row 단위는 원본 event입니다.
- `stay_id`, `charttime`, `bin`, `feature_name`, `itemid` 순으로 정렬합니다.
- 같은 12시간 bin 안의 여러 charttime을 합치지 않습니다.
- procedure/device는 long event row로 추가하지 않습니다.

## 12시간 구간 라벨링 (wide-format by charttime)

long-format chart/lab/medication event를 charttime 기준 wide-format으로 펼칩니다.

- row 단위는 `subject_id`, `hadm_id`, `stay_id`, `charttime`, `bin`, `hours`입니다.
- column 단위는 `feature_name`입니다.
- 같은 정확한 `charttime`에 측정된 feature들은 같은 row에 들어갑니다.
- 해당 `charttime`에 측정되지 않은 feature는 `NaN`입니다.
- 같은 12시간 bin 안의 여러 charttime은 `max`, `mean` 등으로 집계하지 않습니다.
- 정확히 같은 `stay_id`/`charttime`/`feature_name` 중복만 첫 번째 관측값을 유지합니다.
- `height`, `weight`는 stay 안에서 가장 처음 측정된 값을 전체 charttime row에 채웁니다.

## 처치/장치 노출 추가

wide-format table을 먼저 만든 뒤, `procedure_selected.csv`의 interval을 적용합니다. Procedure/device interval은 미리 binning하지 않고 interval 형태로 유지합니다.

- 종료 시간이 없으면 시작 시간을 종료 시간으로 사용합니다.
- interval이 ICU stay의 `intime`/`outtime`을 벗어나면 ICU stay 구간으로 잘라냅니다.
- procedure/device interval과 겹치는 실제 charttime row에만 procedure feature를 `1`로 표시합니다.
- charttime row가 procedure interval 밖이면 같은 12시간 bin 안에 있더라도 `0`으로 둡니다.
- procedure/device exposure 컬럼은 charttime row의 `charttime`이 procedure interval 안에 있으면 `1`, 아니면 `0`입니다.

## delirium 라벨 생성

charttime 기준 wide table에 12시간 bin/window 단위 `delirium` label을 붙입니다.

- 같은 `stay_id`/`bin` 안 assessment 중 하나라도 `1`이면 `1`입니다.
- assessment는 있지만 모두 `0`이면 `0`입니다.
- assessment 자체가 없으면 `NaN`입니다.
- 같은 `stay_id`/`bin` 안의 모든 charttime row는 같은 `delirium` 값을 갖습니다.

## ever_delirium 라벨 생성

`ever_delirium`은 EDA와 subject-level split 확인을 위한 subject-level label입니다. 12시간 bin/window `delirium` label 생성 직후, 포함/제외 기준 적용 전에 만듭니다.

- 같은 `subject_id`에서 12시간 bin/window `delirium == 1`이 한 번이라도 있으면 `1`
- 그렇지 않으면 `0`

`ever_delirium`은 assessment-level outcome인 `delirium`을 대체하지 않습니다.

## 12시간 binning

charttime 기준 wide table과 별도로, 12시간 bin을 row 단위로 하는 `all_events_12h_binned.csv`를 생성합니다. 이 table은 `extraction_variable_catalog.csv`의 `binning` 컬럼을 기준으로 feature별 집계 방식을 적용합니다.

- row 단위는 `subject_id`, `hadm_id`, `stay_id`, `bin`, `hours`, `bin_start`, `bin_end`입니다.
- 기본 정보로 `age`, `gender`, `los_hours`, `admission_type`, `race`, `specialty`, `hospital_expire_flag`, `intime`, `outtime`을 가능한 컬럼 범위에서 유지합니다.
- `aggregation`: 같은 stay/bin/feature 안의 numeric value로 `mean`, `median`, `std`, `count`, `min`, `max`, `latest` 컬럼을 만듭니다. 컬럼명은 `{feature}_{stat}` 형식입니다.
  - 해당 bin의 측정 횟수 `count < 3`이면 `std`는 `NaN`으로 둡니다.
  - 해당 bin에 측정값이 없고 같은 stay의 직전 관측 `latest`가 있으면, 그 직전 `latest` 하나로 `mean`, `median`, `min`, `max`, `latest`를 채우고 `count = 1`, `std = NaN`으로 둡니다.
  - 첫 번째 bin에 측정값이 없고 두 번째 bin에 측정값이 있으면, 두 번째 bin의 가장 이른 측정값 하나로 첫 번째 bin의 `mean`, `median`, `min`, `max`, `latest`를 채우고 `count = 1`, `std = NaN`으로 둡니다.
- `most recent`: 각 bin 안의 최신값을 사용하고, stay 안에서 이전 bin의 값을 forward-fill합니다. 첫 번째 bin에 값이 없고 두 번째 bin에 값이 있으면, 두 번째 bin의 최신값으로 첫 번째 bin만 채웁니다.
- `at least once`: medication, delirium assessment 같은 point event는 bin 안에 한 번이라도 있으면 `1`, 없으면 `0`입니다.
- `prev_delirium`: 같은 stay의 직전 12시간 bin에서의 `delirium` 결과입니다. 첫 bin은 입원 전 직전 delirium 결과가 없으므로 `0`으로 둡니다.
- `static`: height/weight 같은 event-derived static feature는 stay 안의 첫 관측값을 전체 bin에 반복합니다. `age`, `gender`는 admission/patient 정보에서 가져옵니다.
- procedure/device interval은 12시간 bin과 겹치면 해당 procedure feature를 `1`로 표시합니다. charttime 기준 wide table과 달리 interval과 bin의 overlap 기준입니다.

## 포함/제외 기준 적용

Criteria는 12시간 라벨링과 wide table 생성 후 적용합니다.

모델링은 12시간 bin을 time step으로 쓰는 LSTM 구조를 전제로 합니다. Transform 단계의 cohort inclusion은 ICU LOS 24시간 이상으로 적용하고, 4개 input step 및 이후 target step을 만들 수 없는 sequence는 train/test construction 단계에서 제외합니다.

적용 순서:

1. 전체 ICU stays from extraction
2. 24시간 이상 ICU LOS: `icu_los_hours >= 24`

12시간 window 수는 ICU LOS 기준으로 계산합니다.

- `total_12h_windows`: `ceil(icu_los_hours / 12)`의 stay별 합.
- `candidate_12h_windows_excl_first48_last12`: LSTM 입력 4개 time step에 해당하는 첫 48시간과 퇴실 직전 마지막 12시간을 제외한 12시간 window의 stay별 합.

`cohort_attrition.csv`에는 각 단계의 `n_subjects`, `n_hadm`, `n_stays`, 12시간 window 수, 이전 단계 대비 제거 stay 수, 초기 대비 stay 비율이 저장됩니다.

## 산출물 저장

산출물은 마지막 셀에 몰아서 저장하지 않고, 각 데이터프레임이 완성되는 셀에서 바로 저장합니다.

- `events_12h_long.csv`
- `events_12h_wide_by_charttime.csv`
- `events_12h_binned.csv`
- `assessment_index_12h.csv`
- `cohort_final.csv`
- `cohort_attrition.csv`
- `all_events_12h_long.csv`
- `all_events_12h_wide_by_charttime.csv`
- `all_events_12h_binned.csv`
- `data_distribution_summary_12h.txt`

`assessment_index_12h.csv`는 섬망 평가가 실제로 시행된 시점만 모아둔 assessment-level reference입니다. 현재 train/test construction과 LSTM 모델링은 `events_12h_binned.csv`의 bin-level `delirium` label만 사용합니다.

## 다음 단계

- `3_eda.ipynb`: 환자 기본정보, delirium assessment 주기, lab 측정 주기 EDA를 수행합니다.
- `4_train_test_construction.ipynb`: subject-level train/test split과 padded LSTM sequence index를 생성합니다.
- `5_data_preprocessing.ipynb`: sequence index를 LSTM tensor와 target mask로 변환합니다.
- `6_modeling.ipynb`: masked loss/metric 기반 LSTM 모델링을 수행합니다.

모델 성능 비교에 필요한 feature selection과 imputation은 train/test split 이후 train 기준으로 수행해야 합니다.
