# Parkinson Project Guide

이 문서는 `Parkinson` 하위 작업을 이어받는 에이전트와 연구자가 전체 데이터 파이프라인을 빠르게 이해하기 위한 안내서입니다.

## 목적

MIMIC-IV 기반 Parkinson 코호트에서 ICU 섬망 평가를 outcome으로 사용하기 위해 다음 흐름을 구성합니다.

1. 원천 CSV에서 ICU stay 코호트와 임상 이벤트를 추출합니다.
2. 추출된 long-format 이벤트에 ICU 입실 기준 12시간 구간 라벨을 붙이고, charttime 기준 wide table을 생성합니다.
3. 12시간 bin-level table에서 subject-level train/test split과 padded LSTM sequence index를 만듭니다.

## 주요 경로

- `src/1_data_extraction.ipynb`: 원천 MIMIC-IV CSV에서 cohort, chart, lab, medication, procedure 이벤트를 추출합니다.
- `src/2_data_transform.ipynb`: 추출 결과를 숫자화, 단위 통일, 12시간 구간 라벨링, charttime 기준 wide 변환, cohort 기준 적용 산출물로 변환합니다.
- `src/3_eda.ipynb`: transform 산출물을 읽어 환자 기본정보와 12시간 bin-level feature missingness EDA를 수행합니다.
- `src/4_train_test_construction.ipynb`: transform 산출물을 읽어 subject-level train/test split과 LSTM sequence index를 만듭니다.
- `src/5_data_preprocessing.ipynb`: split 산출물과 sequence index를 읽어 LSTM tensor와 target mask를 생성합니다.
- `src/6_modeling.ipynb`: LSTM 모델을 학습하고 masked loss/metric으로 평가합니다.
- `src/extraction_variable_catalog.md`: 추출 대상 변수 catalog 문서입니다.
- `src/extraction_variable_catalog.csv`: 추출 대상 변수 catalog의 CSV 버전입니다.
- `data/`: 원천 CSV 파일 위치입니다. 민감 데이터는 git에 올리지 않습니다.
- `processed/extraction/`: extraction notebook의 산출물 위치입니다.
- `processed/transform/`: transform notebook의 산출물 위치입니다.
- `reports/`: 추출 커버리지와 요약 리포트 위치입니다.
- `docs/1_data_extraction.md`: `1_data_extraction.ipynb` 상세 설명입니다.
- `docs/2_data_transform.md`: `2_data_transform.ipynb` 상세 설명입니다.
- `docs/3_eda.md`: `3_eda.ipynb` 상세 설명입니다.
- `docs/4_train_test_construction.md`: `4_train_test_construction.ipynb` 상세 설명입니다.
- `docs/4_modeling_plan.md`: 모델링 단계 계획입니다.

## 실행 순서

1. Jupyter 작업 디렉터리를 `Parkinson/src`로 둡니다.
2. `1_data_extraction.ipynb`를 위에서 아래로 실행합니다.
3. `2_data_transform.ipynb`를 위에서 아래로 실행합니다.
4. 필요 시 `3_eda.ipynb`를 실행해 cohort EDA를 확인합니다.
5. `4_train_test_construction.ipynb`를 실행해 subject-level train/test split과 LSTM sequence index를 생성합니다.
6. `5_data_preprocessing.ipynb`를 실행해 tensor와 target mask를 생성합니다.
7. `6_modeling.ipynb`를 실행해 masked LSTM 모델을 학습합니다.

노트북은 `PROJECT_DIR = Path.cwd().resolve().parent`를 사용합니다. 따라서 현재 작업 디렉터리가 `Parkinson/src`일 때 `PROJECT_DIR`이 `Parkinson`으로 잡힙니다.

## 데이터 흐름

```text
Parkinson/data/*.csv
  -> src/1_data_extraction.ipynb
  -> processed/extraction/
       adm_pat_icu.csv
       adm_pat_icu_all.csv
       chart_selected.csv
       lab_selected.csv
       medication_events.csv
       procedure_selected.csv
       all_events_long.csv
  -> src/2_data_transform.ipynb
  -> processed/transform/
       cohort_attrition.csv
       all_events_filtered.csv
       all_events_12h_long.csv
       all_events_12h_wide_by_charttime.csv
       all_events_12h_binned.csv
       events_12h_long.csv
       events_12h_wide_by_charttime.csv
       events_12h_binned.csv
       assessment_index_12h.csv
       cohort_final.csv
       data_distribution_summary_12h.txt
  -> src/3_eda.ipynb
  -> src/4_train_test_construction.ipynb
  -> processed/modeling/
       train_subject_ids.csv
       test_subject_ids.csv
       events_12h_binned_with_split.csv
       cohort_final_with_split.csv
       lstm_sequence_index.csv
       lstm_sequence_index_train.csv
       lstm_sequence_index_test.csv
  -> src/5_data_preprocessing.ipynb
  -> processed/modeling/
       X_train_lstm.npy
       X_test_lstm.npy
       y_train_steps_lstm.npy
       y_test_steps_lstm.npy
       y_train_step_mask_lstm.npy
       y_test_step_mask_lstm.npy
  -> src/6_modeling.ipynb
```

## 코호트 기준

- ICU stay 단위로 `patients`, `admissions`, `icustays`를 결합합니다.
- `services.csv`를 필수 입력으로 사용하고 ICU 입실 시점의 `curr_service`를 `specialty`로 결합합니다.
- ICU 재원시간이 양수인 stay만 유지합니다.
- `1_data_extraction.ipynb`에서는 위 기준을 적용하지 않고 전체 ICU stay 테이블을 저장합니다.
- `2_data_transform.ipynb`에서 ICU LOS 24시간 이상 기준을 적용하고 `cohort_attrition.csv`로 저장합니다.

## Outcome 정의

- outcome은 `chartevents`의 `Delirium assessment`입니다.
- transform 단계에서 `Positive`는 `1`, `Negative`는 `0`으로 변환합니다.
- `UTA` 또는 기타 해석 불가능한 평가는 `NaN`으로 남깁니다.
- train/test construction과 LSTM 모델링에서는 `events_12h_binned.csv`의 12시간 `stay_id`/`bin` label만 target으로 사용합니다. 해당 bin 안 assessment 중 하나라도 positive면 `1`, assessment는 있지만 positive가 없으면 `0`, assessment 자체가 없으면 `NaN`입니다.

## Feature 범위

- Chart: 섬망 평가, RASS, GCS, 방향감각, 활력징후, 체중/키, 산소치료 및 환기 관련 변수, bedside glucose.
- Lab: 전해질, CBC, 간기능, lactate, ABG, coagulation 관련 변수.
- Medication: Parkinson 약제, benzodiazepine, opioid, sedative/anesthetic, antipsychotic, anticholinergic burden, sleep agent.
- Procedure/device: invasive/non-invasive ventilation, intubation, extubation, EEG.

## 변환 정책 요약

- 시간축은 ICU 입실 후 경과시간 기준 12시간 구간 라벨입니다. `bin`은 `1, 2, 3, ...`, `hours`는 `12, 24, 36, ...`입니다.
- chart/lab/medication event는 long-format에서 집계하지 않고 유지합니다.
- wide table은 charttime 기준입니다. 같은 정확한 `stay_id`/`charttime`에 측정된 feature만 같은 row에 들어가며, 같은 12시간 bin 안의 여러 charttime을 `max`로 합치지 않습니다.
- 단, wide table의 `delirium`은 12시간 bin/window label로 별도 생성합니다.
- 별도 12시간 bin-level wide table인 `all_events_12h_binned.csv`와 cohort-filtered `events_12h_binned.csv`를 생성합니다. 이 table은 `extraction_variable_catalog.csv`의 `binning` 규칙에 따라 `aggregation`, `most recent`, `at least once`, `static` feature를 만듭니다. `most recent` 변수는 직전 bin 값으로 forward fill하고 첫 bin 결측은 두 번째 bin 값으로 첫 bin만 채웁니다. `aggregation` 변수는 `count < 3`이면 `std = NaN`, 빈 bin은 직전 `latest` 하나로 `mean`/`median`/`min`/`max`/`latest`와 `count = 1`을 채우며, 첫 bin 결측은 두 번째 bin의 가장 이른 값으로 같은 방식으로 채웁니다.
- 단위는 공통 단위로 맞춥니다. 예: Fahrenheit to Celsius, pounds to kg, FiO2 0-1 to percent.
- 변환 rule 적용 후에도 같은 `source_table` + `feature_name` 안에 `valueuom`이 2개 이상이면 unit별 feature로 분리합니다.
- 약물 feature는 extraction 단계에서 `all_events_long.csv`에 point event로 포함하며, 실제 투약 charttime에 `1`로 둡니다.
- 처치/장치는 long event row로 만들지 않습니다. charttime 기준 wide table에서는 현재 row의 `charttime`이 interval 안에 들어오면 `1`, 12시간 bin-level table에서는 procedure interval이 bin과 겹치면 `1`로 표시합니다.
- 체중/키는 wide table에서 stay 안의 첫 측정값으로 전체 charttime row를 채웁니다.
- 활력징후, Lab, neuro 변수는 transform 단계에서 시간별 보간하지 않습니다.

## 최종 데이터셋 단위

모델링 입력의 기본 단위는 `lstm_sequence_index.csv`의 ICU stay별 sequence row입니다.

- key: `example_id`, `subject_id`, `hadm_id`, `stay_id`, `anchor_bin`
- input: `input_bins`, `input_mask`
- output: `y_t`, `y_t_plus_1`, `y_t_plus_2`
- loss mask: `y_t_mask`, `y_t_plus_1_mask`, `y_t_plus_2_mask`
- split: `4_train_test_construction.ipynb` 실행 후 subject-level random train/test split

Feature selection, imputation, PAD zero-vector 변환은 `5_data_preprocessing.ipynb`에서 train 기준으로 수행합니다.

기본 모델링 방향은 12시간 bin을 time step으로 쓰는 LSTM입니다. 각 stay 안에서 anchor bin을 오른쪽으로 sliding하며 sequence row를 생성합니다. 첫 anchor는 `t2`이며, PAD 3개와 `t1`만 있는 sequence는 만들지 않습니다. 최대 4개 time step의 feature를 입력으로 사용하고, 실제 input bin 수가 4개보다 적으면 왼쪽을 `PAD`로 채웁니다. 출력은 anchor bin 및 다음 2개 time step의 delirium 여부이며, 실제 target이 없는 위치는 target mask를 0으로 설정해 loss에서 제외합니다. Transform 단계 cohort inclusion은 ICU LOS 24시간 이상입니다. Candidate sequence count는 `t2`부터 마지막 bin까지의 anchor 수를 기록합니다.

12시간 bin-level table에는 `prev_delirium` feature가 포함됩니다. 이는 같은 stay의 직전 bin `delirium` 결과이며 첫 bin은 `0`입니다.
Preprocessing 단계에서는 `hours`를 현재 bin까지의 ICU 경과시간 feature로 포함하고, `race`를 categorical feature로 포함하며, 전체 ICU 재원시간인 `los_hours`는 제외합니다. `prev_delirium`은 catalog에 없는 파생 feature지만 binary feature로 포함합니다. Feature type은 `extraction_variable_catalog.csv`를 기준으로 분류하며, catalog binary/text binary, categorical, numeric feature를 분리해 처리합니다.

## 작업 시 주의사항

- 사용자가 명시적으로 요청하지 않은 기존 주석은 수정하거나 삭제하지 않습니다.
- 코드 수정 시 새 로직 설명에 꼭 필요한 최소 주석만 추가합니다.
- 기존 코드, 노트북 셀 구조, 문서 내용은 요청 범위에 필요한 부분만 최소 변경합니다.
- 원천 MIMIC-IV 데이터와 산출 CSV는 민감 정보가 될 수 있으므로 git에 포함하지 않습니다.
- 기존 notebook의 실행 순서 의존성이 강합니다. 셀을 재배치할 때는 중간 저장 파일과 변수명을 함께 확인합니다.
- 앞선 단계에서 생성되어야 하는 파일이나 디렉터리는 존재한다고 가정합니다. `if not exist`, `mkdir(exist_ok=True)`, 누락 파일 대체 생성 같은 방어 코드는 사용하지 않습니다.
- 앞선 notebook 셀에서 생성되어야 하는 변수나 컬럼은 뒤 셀에서 존재한다고 가정하고 그대로 사용합니다. 예: 기대 컬럼 부재를 대비하는 방어 코드는 사용하지 않습니다.
- extraction 단계의 `adm_pat_icu.csv`는 전체 ICU stay 기준입니다. 최종 cohort는 transform 단계 산출물에, train/test split은 modeling 단계 산출물에 반영합니다.
- notebook JSON을 수정할 때는 저장 후 `json.load`로 파일이 깨지지 않았는지 확인합니다.
- 코드를 바꾼 뒤에는 가능하면 작은 샘플 또는 dry-run으로 산출물 컬럼이 유지되는지 확인합니다.

## Windows 한글 인코딩 주의

- Windows PowerShell에서 heredoc, inline script, shell redirection으로 한글 문자열을 파일에 직접 쓰지 않습니다.
- 한글 주석이나 한글 문서를 수정할 때는 `apply_patch`를 우선 사용합니다.
- notebook이나 JSON을 구조적으로 수정해야 해서 스크립트가 필요한 경우, 한글 literal을 스크립트 안에 직접 넣지 않거나 Unicode escape를 사용합니다.
- 한글 수정 뒤에는 반복 물음표나 Unicode replacement character 같은 깨진 문자 여부를 확인합니다.
- PowerShell 화면 출력은 인코딩 표시가 틀릴 수 있으므로, 실제 파일 내용은 UTF-8로 읽은 `repr` 출력 또는 JSON parse 결과로 확인합니다.
