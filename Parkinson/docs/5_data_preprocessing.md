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
- `current_delirium`: 현재 anchor/input bin의 delirium 결과, binary feature로 포함
- `race`: categorical feature로 포함
- `los_hours`: 전체 ICU 재원시간이므로 미래 정보 성격으로 제외

`extraction_variable_catalog.csv`의 `type`을 기준으로 feature를 분류합니다.

- `type == binary`: `binary_cols`
- `type == categorical`: `categorical_cols`
- 위 둘과 제외 컬럼을 뺀 나머지: `numeric_cols`

Catalog의 `feature_name`과 정확히 일치하는 binary/categorical 변수만 해당 그룹으로 분류합니다. 그 외 binned aggregation 파생 컬럼은 numeric feature로 처리합니다.

`current_delirium`은 transform 단계에서 만든 파생 feature라 catalog에 직접 없으므로 preprocessing에서 binary로 명시합니다. `race`도 catalog에 직접 없으므로 categorical로 명시합니다.

## Preprocessing 규칙

- train split 기준으로만 missingness, imputation 값, scaling 값, category level을 fit
- 결측치가 심한 변수는 명시 목록 기준으로 `binned`에서 실제 제거
- numeric feature: train 기준 imputation 후 `StandardScaler` 적용
- lab/most recent numeric feature: 해당 컬럼의 train median으로 imputation
- aggregation numeric feature: `{feature}_mean`, `{feature}_median`, `{feature}_min`, `{feature}_max`, `{feature}_latest`는 같은 feature의 `{feature}_latest` train median으로 imputation
- aggregation의 `{feature}_count`, `{feature}_std` 및 기타 numeric feature: 해당 컬럼의 train median으로 imputation
- numeric binary feature: `0/1` 그대로 사용, missing은 `0`
- text binary feature: train level 기준 one-hot
- categorical feature: train level 기준 one-hot
- test split은 train에서 정한 feature 목록과 preprocessing 값만 적용

## Sequence Tensor 생성

`lstm_sequence_index_train.csv`, `lstm_sequence_index_test.csv`의 `input_bins`를 사용해 각 sequence row의 input tensor를 만듭니다.

- `PAD` input step: zero-vector
- 실제 input bin: `(stay_id, bin)` 기준 feature row lookup
- sequence 1개: `input_bins`의 각 time step을 feature vector로 바꾼 `(time, feature)` matrix
- 전체 input tensor: sequence별 matrix를 쌓은 `(sequence, time, feature)` array
- input mask: 실제 input bin은 `1`, left-padded `PAD` step은 `0`
- target: `y_t_plus_1`, `y_t_plus_2`
- target mask: `y_t_plus_1_mask`, `y_t_plus_2_mask`
- binary target: `y_t_plus_1`, `y_t_plus_2` 중 하나라도 positive인 `y_within_t_plus_2`; metadata에는 `y_within_t_plus_1`도 함께 저장

## 출력 파일

`processed/data_split/`:

- `X_train_lstm.npy`
- `X_test_lstm.npy`
- `X_train_input_mask_lstm.npy`
- `X_test_input_mask_lstm.npy`
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
