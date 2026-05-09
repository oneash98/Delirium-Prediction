# 2_data_transform.ipynb 설명

`src/2_data_transform.ipynb`는 `1_data_extraction.ipynb`의 산출물을 모델링 가능한 형태로 변환하는 노트북입니다. long-format 이벤트를 숫자화하고, 단위를 통일하고, ICU 입실 후 1시간 bin 단위 timeseries로 만든 뒤, 섬망 평가 시점마다 직전 8시간 window를 집계합니다.

## 입력 파일

`processed/extraction/`:

- `all_events.csv`: chart와 lab이 통합된 long-format 이벤트.
- `all_events_long.csv`: `all_events.csv`가 없을 때 fallback으로 사용합니다.
- `adm_pat_icu_all.csv`: inclusion/exclusion criteria 적용 전 전체 ICU stay 정보.
- `adm_pat_icu.csv`: `adm_pat_icu_all.csv`가 없을 때 fallback으로 사용하는 전체 ICU stay 정보.
- `medication_events.csv`: 약물 이벤트. 없으면 빈 DataFrame으로 처리합니다.
- `procedure_selected.csv`: 처치/장치 이벤트. 없으면 빈 DataFrame으로 처리합니다.

## 주요 산출물

`processed/transform/`:

- `cohort_attrition.csv`: 후반 cohort 확정 단계에서 inclusion/exclusion criteria별 stay 수, subject 수, admission 수, event 수 감소 요약.
- `adm_pat_icu_8hrs.csv`: 최종 cohort 기준을 통과한 ICU stay.
- `all_events_8hrs.csv`: 최종 cohort 기준을 통과한 stay에 해당하는 long-format 이벤트.
- `all_events_filtered.csv`: 값 숫자화, 단위 변환, multi-unit feature 분리, label 통합, 결측 value 제거 후 이벤트.
- `all_timeseries.csv`: 1시간 bin 기준 wide-format timeseries.
- `timeseries_imputed.csv`: 결측 처리 정책이 적용된 timeseries.
- `final_dataset.csv`: 모델링용 assessment-level 최종 데이터셋.
- `assessment_dataset_60min.csv`: `final_dataset.csv`와 같은 assessment-level 산출물.
- `hourly_timeseries_60min.csv`: 최종 저장용 hourly timeseries.

## 전체 흐름

1. 추출 단계의 `all_events`와 `adm_pat_icu`를 불러옵니다.
2. 시간 컬럼을 datetime으로 변환하고 전체 ICU stay 기준으로 변환 준비를 합니다.
3. 원본 `value`를 `value_str`로 보존하고, `valuenum` 또는 숫자형 문자열을 분석 가능한 숫자 `value`로 변환합니다.
4. 온도, 체중, 키, FiO2 등 단위를 통일합니다.
5. 변환 rule 적용 후에도 같은 변수 안에 여러 `valueuom`이 남으면 unit별 feature로 분리합니다.
6. `feature_name`을 사람이 읽기 쉬운 통합 `label`로 변환합니다.
7. ICU 입실 후 경과시간을 계산하고 1시간 단위 `bin`을 만듭니다.
8. long-format 이벤트를 stay-bin 기준 wide-format timeseries로 pivot합니다.
9. medication/procedure/device 노출을 hourly binary flag로 병합합니다.
10. 결측 처리 정책을 적용합니다.
11. 섬망 평가 시점을 기준으로 직전 8시간 window를 만들고 assessment-level feature로 집계합니다.
12. 가능한 후반 단계에서 inclusion/exclusion criteria를 순서대로 적용하고 cohort attrition을 저장합니다.
13. 최종 데이터셋과 중간 산출물을 저장합니다.

## Inclusion/Exclusion Criteria와 Cohort Attrition

inclusion/exclusion criteria는 가능한 후반 단계에서 적용합니다. 초반에 성인, LOS, 8시간 기준으로 데이터를 먼저 줄이면 이후 변수 생성 과정에서 전체 ICU stay 기준의 데이터 손실 흐름을 한 번에 보기 어렵기 때문입니다.

따라서 transform 초반에는 전체 ICU stay와 전체 이벤트를 유지한 채 값 숫자화, 단위 통일, hourly timeseries 생성, medication/procedure exposure 생성까지 진행합니다. 이후 assessment-level dataset을 만들기 직전 또는 만든 직후에 다음 기준을 순서대로 적용하면서 데이터 수 감소를 `cohort_attrition.csv`에 저장합니다.

적용 순서:

1. 전체 ICU stays from extraction
2. 성인 환자: `anchor_age >= 18`
3. 유효한 ICU 입실/퇴실 시간: `intime`, `outtime` 존재
4. 양수 ICU LOS: `icu_los_hours > 0`
5. 8시간 이상 ICU LOS: `icu_los_hours >= 8`
6. Delirium assessment 존재
7. Delirium assessment가 완전한 직전 8시간 window를 가짐

처리 결과:

- `adm_pat_icu_8hrs.csv`: 최종 cohort 기준을 통과한 stay.
- `all_events_8hrs.csv`: 최종 cohort 기준을 통과한 stay에 속한 이벤트만 남긴 파일.
- `cohort_attrition.csv`: 각 기준별 `n_stays`, `n_subjects`, `n_hadm`, `event_rows`, `event_stays`, 이전 단계 대비 제거 수, 초기 대비 비율.

## 값 숫자화

먼저 원본 `value` 컬럼을 `value_str`로 보존합니다. 그 다음 `valuenum`을 우선 숫자형 `value`로 사용하고, `valuenum`이 비어 있지만 원본 `value_str`이 숫자 문자열인 경우에는 그 값을 fallback으로 사용합니다. 숫자로 변환되지 않는 문자열 값은 별도 규칙으로 처리합니다.

주요 변환:

- Delirium assessment: `Positive -> 1`, `Negative -> 0`
- RASS text: `Alert and calm -> 0` 등 문자열 scale을 숫자 점수로 변환
- GCS 항목: eye/verbal/motor response 문자열을 GCS 점수로 변환
- Orientation/command response: 가능한 값은 점수 또는 binary 값으로 변환
- 해석 불가능하거나 모델 입력에 쓰기 어려운 값은 `NaN`으로 남깁니다.

이후 `value`가 여전히 `NaN`인 행은 제거합니다.

## 단위 통일

동일한 임상 의미의 변수가 서로 다른 단위로 들어오는 경우 공통 단위로 맞춥니다.

주요 규칙:

- Temperature: Fahrenheit를 Celsius로 변환합니다.
- Weight: pounds를 kg으로 변환합니다.
- Height: inch를 cm로 변환합니다.
- FiO2: 0-1 fraction으로 기록된 값은 percent로 변환합니다.
- Temperature, weight, height, FiO2는 변환 후 각각 `degC`, `kg`, `cm`, `%`로 `valueuom`을 맞춥니다.
- 변환 rule 적용 후에도 같은 `source_table` + `feature_name` 안에 `valueuom`이 2개 이상이면 unit별 feature로 분리합니다.

unit별 feature 분리 예시:

- `d_dimer` + `ng/mL` -> `d_dimer__ng_per_ml`
- `d_dimer` + `ng/mL FEU` -> `d_dimer__ng_per_ml_feu`

분리된 변수는 label에도 unit이 붙습니다. 예: `D-Dimer [ng/mL]`, `D-Dimer [ng/mL FEU]`.

## 통합 label

`feature_name`을 최종 pivot용 label로 변환합니다. 예를 들어 여러 원본 label이 같은 임상 개념이면 하나의 label로 묶습니다. Unit별로 분리된 feature는 label 뒤에 unit을 붙여 구분합니다.

예시:

- `temperature_c -> Temperature`
- `spo2`, `arterial_o2_saturation -> Oxygen Saturation`
- `nibp_mbp`, `abp_mbp -> Mean BP`
- `glucose_lab`, chart glucose variants -> Glucose`
- `platelet_count -> Platelets`
- `bun -> BUN`
- `delirium_assessment -> Delirium assessment`

## Hourly Timeseries 생성

환자/입원/ICU 정보를 이벤트에 붙인 뒤 ICU 입실 후 경과시간을 계산합니다.

- `hours = charttime - intime`
- `bin = int(hours)`
- ICU 입실 이전 이벤트와 퇴실 이후 이벤트는 제거합니다.

그 다음 `stay_id`, `bin` 단위로 기본 정보와 pivot table을 결합합니다.

기본 정보:

- `hours`
- `age`
- `gender`
- `los_hours`
- `subject_id`
- `hadm_id`
- `admission_type`
- `race`
- `hospital_expire_flag`

pivot 대상:

- Delirium assessment
- Vital signs
- RASS/GCS/orientation
- Weight/height
- CBC, electrolytes, chemistry, ABG, coagulation
- Ventilator/O2 delivery device

같은 stay-bin-label에 여러 값이 있으면 `max`를 사용합니다.

## Delirium 컬럼 처리

`Delirium assessment`는 `Delirium`으로 rename합니다.

- 평가 시점: `0` 또는 `1`
- 평가가 없는 시간 bin: `NaN`

이 설계 때문에 hourly timeseries의 `Delirium` 결측은 단순 결측이 아니라 "평가가 시행되지 않은 시간"을 의미합니다.

## Medication Exposure 변환

`medication_events.csv`를 불러와 `charttime` 기준 eMAR medication feature별 hourly binary flag를 만듭니다.

정책:

- `MED_LOOKBACK_HOURS = 8`
- eMAR 투약 시점이 포함된 hour부터 8시간 동안 노출로 표시합니다.
- eMAR medication은 처방 interval이 아니므로 `starttime`, `stoptime`, `event_start`, `event_end`를 사용하지 않습니다.
- 노출이 있는 stay-bin-feature는 `1`, 없으면 최종 병합 후 `0`입니다.

의도:

- 섬망 평가 직전 8시간 동안 영향을 줄 수 있는 약물 exposure를 반영합니다.

## Procedure/Device Exposure 변환

`procedure_selected.csv`를 불러와 procedure/device feature별 hourly binary flag를 만듭니다.

정책:

- procedure 시작/종료 시간이 현재 hour bin과 겹치면 `1`입니다.
- 종료 시간이 없으면 시작 시간을 종료 시간으로 대체합니다.
- ICU stay의 outtime을 넘어가는 bin은 잘라냅니다.

## 결측 처리 정책

결측 처리는 변수 성격에 따라 다르게 적용합니다.

Binary exposure:

- medication, procedure, `Ventilator`는 결측을 `0`으로 채웁니다.
- 관찰되지 않은 노출은 미노출로 해석합니다.

Static/body measure:

- `Weight`, `Height`는 같은 stay 내에서 forward-fill 후 backward-fill합니다.
- stay 내 관측값을 전체 시간축에 확장하는 정책입니다.

Vital signs:

- `Heart Rate`, `Respiratory Rate`, `Temperature`, `Oxygen Saturation`, `Mean BP`, `Systolic BP`, `Diastolic BP`, `FiO2`, `O2 Flow`는 stay별 forward-fill을 적용합니다.
- 최대 4시간까지만 채워 오래된 값이 무한히 전파되지 않게 합니다.

Lab:

- hourly timeseries에서는 강제 보간하지 않습니다.
- 최종 8시간 window 집계 단계에서 window 내 최신 관측값을 사용합니다.

## 8시간 Assessment Window 생성

`Delirium` 값이 있는 시간 bin을 assessment 시점으로 봅니다.

제외 기준:

- `assessment_bin < 7`인 평가는 제외합니다.
- 이유는 평가 시점 포함 직전 8개 hourly bins를 구성할 수 없기 때문입니다.

window 정의:

```text
assessment_bin = b
window bins = b-7, b-6, ..., b
```

각 assessment를 8개 bin으로 explode한 뒤 hourly timeseries와 병합해 집계 입력을 만듭니다.

## 최종 Feature 집계

최종 데이터셋은 섬망 평가 1건을 1행으로 합니다.

Group key:

- `stay_id`
- `assessment_bin`
- `Delirium`

집계 방식:

- Demographics: 첫 값
- Vital signs: 8시간 window 내 평균과 표준편차
- Medication/procedure/device binary: window 내 max
- Labs/body/neuro: window 내 최신값

최종 정렬:

- `stay_id`
- `assessment_bin`

## QA 셀

마지막 단계에서 다음을 확인합니다.

- 최종 데이터셋 shape
- unique stay 수
- Delirium class distribution
- 컬럼 목록
- 변수별 결측률
- 수동 drop 이후 shape와 컬럼 목록

현재 수동 drop cell의 `drop_cols = []`이므로 기본적으로 제거되는 변수는 없습니다.

## 주의사항

- `all_events.csv`가 없으면 `all_events_long.csv`를 fallback으로 읽습니다.
- transform은 `adm_pat_icu_all.csv`를 우선 읽고, 없으면 `adm_pat_icu.csv`를 fallback으로 읽습니다.
- value 변환 규칙은 문자열 표기에 민감합니다. 새 데이터에서 다른 표현이 나오면 숫자화 규칙을 보강해야 합니다.
- hourly `Delirium`의 NaN은 outcome 결측이 아니라 평가 미시행 시간입니다.
- lab을 hourly 보간하지 않는 정책은 모델링 해석에 중요합니다. 변경 시 최종 window 집계 방식도 함께 검토해야 합니다.
