# 8_model_interpretation

`src/8_model_interpretation.ipynb`는 `src/6_modeling.ipynb`에서 학습한 future-only multi-horizon XGBoost 모델을 대상으로 모델 해석을 수행합니다.

## 입력 파일

`processed/data_split/`:

- `X_train_lstm.npy`
- `X_test_lstm.npy`
- `y_train_steps_lstm.npy`
- `y_test_steps_lstm.npy`
- `y_train_step_mask_lstm.npy`
- `y_test_step_mask_lstm.npy`
- `lstm_train_metadata.csv`
- `lstm_test_metadata.csv`

`models/`:

- `xgb_multi_horizon.joblib`

`models/clean_data/`:

- `lstm_feature_columns.json`

## 해석 방법

- Permutation feature importance: anchor `t` feature를 sequence 사이에서 섞고, `t~t+2` 기준 `within_t_plus_2` AUPRC 감소량을 중요도로 사용합니다.
- SHAP: `RUN_SHAP = True`로 설정한 경우 선택 horizon logit에 대해 SHAP feature importance를 계산합니다.

## 출력 파일

`outputs/model_interpretation/`:

- `xgb_multi_horizon_permutation_feature_importance.csv`
- `xgb_multi_horizon_shap_feature_importance.csv` (`RUN_SHAP = True`일 때)

`outputs/model_interpretation/figures/`:

- `xgb_multi_horizon_permutation_feature_importance_top.png`
- `xgb_multi_horizon_shap_feature_importance_top.png` (`RUN_SHAP = True`일 때)

## 주의 사항

현재 notebook은 `models/xgb_multi_horizon.joblib`가 있는 상태에서 실행합니다. 먼저 `src/6_modeling.ipynb`를 실행해 multi-horizon XGBoost 모델을 학습하고 저장합니다.
