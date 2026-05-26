# 7_result_analysis

`src/7_result_analysis.ipynb`는 `src/6_modeling.ipynb`의 모델링 산출물을 읽어 test 성능을 요약하고, ROC/PR curve, bootstrap 비교, previous delirium 상태별 층화 평가를 정리합니다.

## 목적

- within `t~t+2` single-output 비교 모델의 test 핵심 metric 확인
- LightGBM, MLP, LSTM multi-horizon 모델의 within `t+2` 및 horizon별 핵심 metric 확인
- 전체 test set 기준 ROC/PR curve와 bootstrap AUPRC/AUROC 분포 확인
- single-output 모델과 multi-horizon 모델의 paired bootstrap 비교
- previous delirium 상태별 LightGBM multi-horizon 평가
- previous delirium 상태별 LightGBM single-output within `t+2` 평가

노트북에서 화면에 우선 표시하는 핵심 지표는 다음과 같습니다.

- within `t+2`: model, positive rate, AUROC, AUPRC, sensitivity, specificity, PPV, NPV
- multi-horizon: model, horizon별 positive rate/AUROC/AUPRC/evaluable count
- previous delirium subgroup: positive rate, AUROC, AUPRC, sensitivity, specificity, PPV, NPV, LR+, LR-

## 입력 파일

`processed/data_split/`:

- `events_12h_binned_with_split.csv`

`outputs/modeling/within_t_plus_2/`:

- `within_t_plus_2_test_metrics_summary.csv`
- `within_t_plus_2_test_predictions_all_models.csv`

`outputs/modeling/`:

- `lgbm_multi_horizon_test_metrics.csv`
- `lgbm_multi_horizon_test_metrics_by_horizon.csv`
- `lgbm_multi_horizon_test_predictions.csv`
- `multi_horizon_test_metrics_summary.csv`
- `mlp_multi_horizon_test_metrics_by_horizon.csv`
- `mlp_multi_horizon_test_predictions.csv`
- `lstm_gpu_test_metrics.csv`
- `lstm_gpu_test_metrics_by_horizon.csv`
- `lstm_gpu_test_predictions.csv`

## Previous Delirium 기준

Previous delirium 여부는 `events_12h_binned_with_split.csv`의 anchor row에 포함된 `prev_delirium`을 사용합니다. 이 값을 test prediction table의 `stay_id`, `anchor_bin`에 merge하여 `prev_delirium_group`을 생성합니다.

- `no_prev_delirium`: `prev_delirium == 0`
- `prev_delirium`: `prev_delirium == 1`

## Previous Delirium 평가 정의

Previous delirium 기준 층화 평가는 모든 group에서 delirium 발생을 positive class로 두고 계산합니다.

- `no_prev_delirium`: 이전 12h bin에 delirium이 없던 case
- `prev_delirium`: 이전 12h bin에 delirium이 있던 case

LightGBM multi-horizon 모델은 두 가지 층화 table을 생성합니다.

- within `t+2`: horizon별 probability를 결합한 `y_within_t_plus_2_prob_from_horizons`로 within `t~t+2` delirium 발생 여부를 평가
- horizon별: `y_t_prob`, `y_t_plus_1_prob`, `y_t_plus_2_prob`를 각각 `y_t`, `y_t_plus_1`, `y_t_plus_2` label에 대해 평가

LightGBM single-output 모델은 `within_t_plus_2` binary target 하나만 학습했으므로 previous delirium 층화 table도 within `t+2`만 생성합니다. horizon별 single-output table은 생성하지 않습니다.

화면 표시용 table에서는 `prev_delirium_group`, `target` 같은 내부 관리용 column을 숨기고 `comparison`, `model`, 핵심 metric 중심으로 보여줍니다. 원본 상세 column은 저장되는 CSV에 유지합니다.

## 분석 흐름

노트북은 다음 순서로 결과를 확인하도록 정리되어 있습니다.

1. 모델링 산출물 로딩 및 전체 test 핵심 metric 확인
2. 전체 test set 기준 within `t+2`, multi-horizon ROC/PR curve 확인
3. within `t+2` bootstrap metric distribution 확인
4. single-output vs multi-horizon paired bootstrap 비교
5. previous delirium 기준 LightGBM multi-horizon 층화 평가
6. previous delirium 기준 LightGBM single-output within `t+2` 층화 평가
7. previous delirium 정보가 결합된 prediction table과 key result table 저장

## 출력 파일

`outputs/modeling/`:

- `within_t_plus_2_bootstrap_metric_distributions.csv`
- `single_vs_multi_horizon_within_t_plus_2_bootstrap_metric_distributions.csv`
- `single_vs_multi_horizon_within_t_plus_2_bootstrap_p_values.csv`
- `lgbm_multi_horizon_prev_delirium_stratified_metrics.csv`
- `lgbm_multi_horizon_prev_delirium_horizon_metrics.csv`
- `lgbm_single_output_prev_delirium_stratified_metrics.csv`
- `within_t_plus_2_test_predictions_all_models_with_prev_delirium.csv`
- `lgbm_multi_horizon_test_predictions_with_prev_delirium.csv`
- `mlp_multi_horizon_test_predictions_with_prev_delirium.csv`
- `lstm_gpu_test_predictions_with_prev_delirium.csv`

`outputs/modeling/figures/`:

- `within_t_plus_2_test_roc_pr_curves_by_model.png`
- `within_t_plus_2_bootstrap_metric_boxplots_by_model.png`
- `multi_horizon_within_t_plus_2_roc_pr_curves_by_model.png`
- `single_vs_multi_horizon_within_t_plus_2_bootstrap_boxplots.png`

`outputs/result_analysis/`:

- `within_t_plus_2_core_test_metrics.csv`
- `multi_horizon_core_test_metrics.csv`
- `lgbm_prev_delirium_within_t_plus_2_metrics.csv`
- `lgbm_prev_delirium_horizon_metrics.csv`
- `lgbm_single_output_prev_delirium_within_t_plus_2_metrics.csv`
- `single_vs_multi_horizon_within_t_plus_2_bootstrap_p_values.csv`
- `key_result_summary.md`

## 실행 순서

`src/6_modeling.ipynb` 실행 후 `src/7_result_analysis.ipynb`를 위에서 아래로 실행합니다. `src/8_model_interpretation.ipynb`는 모델 해석용 노트북이며, 결과 분석과 별도로 실행합니다.
