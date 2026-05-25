# 7_result_analysis

`src/7_result_analysis.ipynb`는 `src/6_modeling.ipynb`의 모델링 산출물을 읽어 test 성능을 요약하고, ROC/PR curve와 previous delirium 상태별 추가 평가를 확인합니다.

## 목적

- within `t~t+2` 비교 모델의 test 핵심 metric 확인
- multi-horizon XGBoost, multi-output MLP, encoder-decoder LSTM의 within `t+2` 및 horizon별 핵심 metric 확인
- 전체 test set 기준 ROC/PR curve 확인
- XGB multi-horizon 모델의 previous delirium 상태별 평가
- 이전 bin에 delirium이 없던 case에서 future delirium 예측 성능 평가
- 이전 bin에 delirium이 있던 case에서 future delirium 예측 성능 평가

노트북에서 화면에 우선 표시하는 핵심 지표는 다음과 같습니다.

- within `t+2`: model, AUROC, AUPRC, sensitivity, specificity, PPV, NPV
- multi-horizon: model, within `t+2`의 AUROC/AUPRC/sensitivity/specificity/PPV/NPV, 그리고 `t`, `t+1`, `t+2` 각각의 AUROC/AUPRC

## 입력 파일

`processed/data_split/`:

- `events_12h_binned_with_split.csv`

`outputs/modeling/within_t_plus_2/`:

- `within_t_plus_2_test_metrics_summary.csv`
- `within_t_plus_2_test_predictions_all_models.csv`

`outputs/modeling/`:

- `lstm_gpu_test_predictions.csv`
- `xgb_multi_horizon_test_predictions.csv`
- `mlp_multi_horizon_test_predictions.csv`
- `multi_horizon_test_metrics_summary.csv`
- `xgb_multi_horizon_test_metrics_by_horizon.csv`
- `mlp_multi_horizon_test_metrics_by_horizon.csv`
- `lstm_gpu_test_metrics.csv`
- `lstm_gpu_test_metrics_by_horizon.csv`

## Previous Delirium 기준

Previous delirium 여부는 `events_12h_binned_with_split.csv`의 anchor row에 포함된 `prev_delirium`을 사용합니다. 이 값을 test prediction table의 `stay_id`, `anchor_bin`에 merge하여 `prev_delirium_group`을 생성합니다.

- `no_prev_delirium`: `prev_delirium == 0`
- `prev_delirium`: `prev_delirium == 1`

## 평가 정의

Previous delirium 기준 층화 평가는 모든 group에서 delirium 발생을 positive class로 두고 계산합니다.

- `no_prev_delirium`: 이전 12h bin에 delirium이 없던 case에서 within `t~t+2` delirium 발생 여부 평가
- `prev_delirium`: 이전 12h bin에 delirium이 있던 case에서 within `t~t+2` delirium 발생 여부 평가

두 group 모두 true label은 delirium 발생 여부이며, probability는 XGB multi-horizon 모델의 delirium probability를 그대로 사용합니다.

XGB multi-horizon 모델은 추가로 horizon별 `y_t`, `y_t_plus_1`, `y_t_plus_2`에 대해 같은 방식으로 각 horizon의 delirium 발생을 positive class로 평가합니다.

화면 표시용 table에서는 `prev_delirium_group`, `target` 같은 내부 관리용 column을 숨기고 `comparison`, `model`, 핵심 metric 중심으로 보여줍니다. 원본 상세 column은 저장되는 CSV에 유지합니다.

## 분석 흐름

노트북은 다음 순서로 결과를 확인하도록 정리되어 있습니다.

1. 모델링 산출물 로딩 및 전체 test 핵심 metric 확인
2. 전체 test set 기준 within `t+2`, multi-horizon ROC/PR curve 확인
3. Previous delirium 기준 층화 평가와 시각화
4. Previous delirium 정보가 결합된 prediction table 저장

## 출력 파일

`outputs/modeling/`:

- `xgb_multi_horizon_prev_delirium_stratified_metrics.csv`
- `xgb_multi_horizon_prev_delirium_horizon_metrics.csv`
- `within_t_plus_2_test_predictions_all_models_with_prev_delirium.csv`
- `xgb_multi_horizon_test_predictions_with_prev_delirium.csv`
- `mlp_multi_horizon_test_predictions_with_prev_delirium.csv`
- `lstm_gpu_test_predictions_with_prev_delirium.csv`

`outputs/modeling/figures/`:

- `within_t_plus_2_test_roc_pr_curves_by_model.png`
- `multi_horizon_within_t_plus_2_roc_pr_curves_by_model.png`
- `multi_horizon_test_horizon_roc_pr_curves_by_model.png`
- `xgb_multi_horizon_prev_delirium_within_t_plus_2_auprc.png`
- `xgb_multi_horizon_prev_delirium_horizon_auprc.png`

## 실행 순서

`src/6_modeling.ipynb` 실행 후 `src/7_result_analysis.ipynb`를 위에서 아래로 실행합니다. `src/8_model_interpretation.ipynb`는 모델 해석용 노트북이며, 결과 분석과 별도로 실행합니다.
