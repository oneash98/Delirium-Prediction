# 5_data_preprocessing

`src/5_data_preprocessing.ipynb`는 `4_train_test_construction.ipynb` 산출물을 받아 LSTM 입력 tensor와 target mask를 생성합니다.

## 입력 파일

`processed/data_split/`:

- `events_12h_binned_with_split.csv`
- `lstm_sequence_index_train.csv`
- `lstm_sequence_index_test.csv`

`src/`:

- `extraction_variable_catalog.csv`

## Feature 분류

학습 입력 feature는 `events_12h_binned_with_split.csv`에서 가져옵니다.

- 제외 컬럼: `subject_id`, `hadm_id`, `stay_id`, `bin`, `bin_start`, `bin_end`, `split`, `intime`, `outtime`, `delirium`, `ever_delirium`, `los_hours`, `admission_type`, `specialty`
- 포함 컬럼: `hours`
- `hours`: 현재 bin까지의 ICU 경과시간
- `prev_delirium`: 직전 12시간 bin의 delirium 결과, binary feature로 포함
- `race`: categorical feature로 포함
- `los_hours`: 전체 ICU 재원시간이므로 미래 정보 성격으로 제외

`extraction_variable_catalog.csv`의 `type`을 기준으로 feature를 분류합니다.

- `type == binary`: `binary_cols`
- `type == categorical`: `categorical_cols`
- 위 둘과 제외 컬럼을 뺀 나머지: `numeric_cols`

Catalog의 `feature_name`과 정확히 일치하는 binary/categorical 변수만 해당 그룹으로 분류합니다. 그 외 binned aggregation 파생 컬럼은 numeric feature로 처리합니다.

`prev_delirium`은 transform 단계에서 만든 파생 feature라 catalog에 직접 없으므로 preprocessing에서 binary로 명시합니다. `race`도 catalog에 직접 없으므로 categorical로 명시합니다.

## Preprocessing 규칙

- train split 기준으로만 missingness, median, mean, std, category level을 fit
- numeric feature: train median imputation 후 train mean/std scaling
- numeric high-missing feature: train missing rate가 `MISSING_THRESHOLD` 초과면 제외
- numeric binary feature: `0/1` 그대로 사용, missing은 `0`
- text binary feature: train level 기준 one-hot
- categorical feature: train level 기준 one-hot
- test split은 train에서 정한 feature 목록과 preprocessing 값만 적용

## Sequence Tensor 생성

`lstm_sequence_index_train.csv`, `lstm_sequence_index_test.csv`의 `input_bins`를 사용해 각 sequence row의 input tensor를 만듭니다.

- `PAD` input step: zero-vector
- 실제 input bin: `(stay_id, bin)` 기준 feature row lookup
- target: `y_t`, `y_t_plus_1`, `y_t_plus_2`
- target mask: `y_t_mask`, `y_t_plus_1_mask`, `y_t_plus_2_mask`

## 출력 파일

`processed/data_split/`:

- `X_train_lstm.npy`
- `X_test_lstm.npy`
- `y_train_lstm.npy`
- `y_test_lstm.npy`
- `y_train_steps_lstm.npy`
- `y_test_steps_lstm.npy`
- `y_train_step_mask_lstm.npy`
- `y_test_step_mask_lstm.npy`
- `lstm_train_metadata.csv`
- `lstm_test_metadata.csv`
- `feature_missingness_train.csv`
- `feature_missingness_test.csv`
- `lstm_preprocessing_summary.csv`

`models/clean_data/`:

- `lstm_feature_columns.json`
- `lstm_preprocess_params.json`
- `lstm_preprocessor.joblib`
