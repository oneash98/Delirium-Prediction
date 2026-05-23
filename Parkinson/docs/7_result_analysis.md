# 7_result_analysis

`src/7_result_analysis.ipynb`는 `src/6_modeling.ipynb`의 모델링 산출물을 읽어 결과 시각화와 t-1 delirium 상태별 추가 평가를 수행합니다.

## 목적

- within `t~t+2` 비교 모델의 test 성능 시각화
- 모델별 row-level predicted probability 분포 확인
- single-output LSTM과 multi-horizon LSTM의 t-1 delirium 상태별 평가
- t-1에 delirium이 없던 case에서 new onset 예측 성능 평가
- t-1에 delirium이 있던 case에서 recovery 예측 성능 평가

## 입력 파일

`processed/data_split/`:

- `events_12h_binned_with_split.csv`

`outputs/modeling/within_t_plus_2/`:

- `within_t_plus_2_test_metrics_summary.csv`
- `within_t_plus_2_test_predictions_all_models.csv`

`outputs/modeling/`:

- `lstm_gpu_test_predictions.csv`
- `lstm_gpu_test_metrics.csv`
- `lstm_gpu_test_metrics_by_horizon.csv`

## t-1 Delirium 기준

t-1 delirium 여부는 `events_12h_binned_with_split.csv`의 anchor row에 포함된 `prev_delirium`을 사용합니다. 이 값을 test prediction table의 `stay_id`, `anchor_bin`에 merge하여 `t_minus_1_delirium`과 `t_minus_1_group`을 생성합니다.

- `no_prior_delirium`: `t_minus_1_delirium == 0`
- `prior_delirium`: `t_minus_1_delirium == 1`

## 평가 정의

New onset 평가:

- 대상: `no_prior_delirium`
- true label: within `t~t+2` delirium 발생 여부
- probability: 각 모델의 delirium probability

Recovery 평가:

- 대상: `prior_delirium`
- true label: within `t~t+2` 동안 delirium이 없는지 여부
- probability: `1 - delirium_probability`

Multi-horizon LSTM은 추가로 horizon별 `y_t`, `y_t_plus_1`, `y_t_plus_2`에 대해 같은 방식으로 new onset/recovery를 평가합니다. 즉, t-1 delirium이 없던 case에서는 각 horizon의 delirium 발생을 보고, t-1 delirium이 있던 case에서는 각 horizon의 non-delirium을 recovery로 봅니다.

## 출력 파일

`outputs/modeling/`:

- `within_t_plus_2_t_minus_1_stratified_metrics.csv`
- `lstm_t_minus_1_stratified_metrics.csv`
- `multi_horizon_lstm_t_minus_1_horizon_metrics.csv`
- `within_t_plus_2_test_predictions_all_models_with_t_minus_1.csv`
- `lstm_gpu_test_predictions_with_t_minus_1.csv`

`outputs/modeling/figures/`:

- `within_t_plus_2_test_auprc_by_model.png`
- `within_t_plus_2_probability_distribution_by_model.png`
- `result_analysis_multi_horizon_lstm_metrics.png`
- `within_t_plus_2_t_minus_1_stratified_auprc.png`
- `lstm_t_minus_1_stratified_auprc_auroc.png`
- `multi_horizon_lstm_t_minus_1_horizon_auprc.png`

## 실행 순서

`src/6_modeling.ipynb` 실행 후 `src/7_result_analysis.ipynb`를 위에서 아래로 실행합니다. `src/8_model_interpretation.ipynb`는 모델 해석용 노트북이며, 결과 분석과 별도로 실행합니다.
