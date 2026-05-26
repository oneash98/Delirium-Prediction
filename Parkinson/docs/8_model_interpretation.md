# 8_model_interpretation

`src/8_model_interpretation.ipynb`는 `src/6_modeling.ipynb`에서 학습한 LightGBM 모델을 대상으로 calibration, decision curve analysis, feature importance, SHAP 해석을 수행합니다. 해석 대상은 LightGBM multi-horizon 모델과 LightGBM single-output within `t+2` 모델입니다.

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

- `lgbm_multi_horizon.joblib`
- `within_t_plus_2/lgbm_t_point_within_t_plus_2.joblib`

`models/clean_data/`:

- `lstm_feature_columns.json`
- `lstm_preprocessor.joblib` fallback: feature column json이 없을 때 feature column list를 읽는 용도

## 해석 대상

LightGBM multi-horizon 모델:

- 입력: anchor `t` 시점 feature
- 출력: `y_t`, `y_t_plus_1`, `y_t_plus_2` horizon별 probability
- within `t+2` probability: horizon별 probability를 결합해 `1 - prod(1 - p_horizon)`로 계산
- SHAP 대상 horizon: `SHAP_HORIZON`, 기본값 `y_t_plus_2`

LightGBM single-output 모델:

- 입력: anchor `t` 시점 feature
- 출력: within `t~t+2` delirium probability 하나
- 해석 target: `within_t_plus_2`

## 해석 방법

- Calibration: predicted probability decile별 평균 예측확률과 observed event rate를 비교합니다.
- Decision curve analysis: threshold probability별 model, treat-all, treat-none net benefit을 계산합니다.
- Permutation feature importance: explain subset에서 feature 값을 sample 사이에 섞은 뒤 AUPRC/AUROC가 얼마나 감소하는지 계산합니다. 기본 plot은 `drop_within_t_plus_2_auprc` 기준입니다.
- Gain importance: LightGBM tree split에서 feature가 만든 누적 gain과 split count를 저장합니다.
- SHAP mean absolute importance: `RUN_SHAP = True`일 때 feature별 평균 `|SHAP value|`를 저장하고 bar plot으로 표시합니다.
- SHAP beeswarm: `RUN_SHAP = True`일 때 sample별 SHAP value 분포와 feature value 방향성을 함께 보여주는 summary plot을 저장합니다.

Permutation importance는 성능 기반 중요도입니다. SHAP은 각 sample의 예측값에 feature가 어느 방향과 크기로 기여했는지 보는 예측값 분해 기반 해석입니다. Gain importance는 LightGBM 학습 과정의 내부 split 개선량입니다.

## 설정값

- `EXPLAIN_SAMPLE_SIZE = 512`: permutation importance와 SHAP 계산에 사용할 test subset 크기
- `PERMUTATION_REPEATS = 3`: feature별 permutation 반복 횟수
- `TOP_N_PLOT = 25`: figure에 표시할 상위 feature 수
- `RUN_SHAP = True`: SHAP CSV와 figure 생성 여부
- `SHAP_EXPLAIN_SIZE = 512`: SHAP 계산에 사용할 sample 수
- `SHAP_HORIZON = "y_t_plus_2"`: multi-horizon LightGBM에서 SHAP을 계산할 horizon

## 출력 파일

`outputs/model_interpretation/`:

- `lgbm_multi_horizon_calibration_summary.csv`
- `lgbm_multi_horizon_calibration_curve.csv`
- `lgbm_multi_horizon_decision_curve.csv`
- `lgbm_multi_horizon_permutation_feature_importance.csv`
- `lgbm_multi_horizon_gain_feature_importance.csv`
- `lgbm_multi_horizon_shap_feature_importance.csv` (`RUN_SHAP = True`일 때)
- `lgbm_single_output_calibration_summary.csv`
- `lgbm_single_output_calibration_curve.csv`
- `lgbm_single_output_decision_curve.csv`
- `lgbm_single_output_permutation_feature_importance.csv`
- `lgbm_single_output_gain_feature_importance.csv`
- `lgbm_single_output_shap_feature_importance.csv` (`RUN_SHAP = True`일 때)

`outputs/model_interpretation/figures/`:

- `lgbm_multi_horizon_calibration.png`
- `lgbm_multi_horizon_decision_curve.png`
- `lgbm_multi_horizon_permutation_feature_importance_top.png`
- `lgbm_multi_horizon_gain_importance_y_t.png`
- `lgbm_multi_horizon_gain_importance_y_t_plus_1.png`
- `lgbm_multi_horizon_gain_importance_y_t_plus_2.png`
- `lgbm_multi_horizon_shap_feature_importance_top.png` (`RUN_SHAP = True`일 때)
- `lgbm_multi_horizon_shap_beeswarm.png` (`RUN_SHAP = True`일 때)
- `lgbm_single_output_calibration.png`
- `lgbm_single_output_decision_curve.png`
- `lgbm_single_output_permutation_feature_importance_top.png`
- `lgbm_single_output_gain_importance_top.png`
- `lgbm_single_output_shap_feature_importance_top.png` (`RUN_SHAP = True`일 때)
- `lgbm_single_output_shap_beeswarm.png` (`RUN_SHAP = True`일 때)

## 실행 순서와 주의 사항

먼저 `src/6_modeling.ipynb`를 실행해 `lgbm_multi_horizon.joblib`와 `within_t_plus_2/lgbm_t_point_within_t_plus_2.joblib`를 생성해야 합니다. 이후 `src/8_model_interpretation.ipynb`를 위에서 아래로 실행합니다.

SHAP 계산은 `RUN_SHAP = True`일 때만 수행됩니다. 실행 시간이 부담되면 `RUN_SHAP = False`로 바꿔 calibration, DCA, permutation importance, gain importance만 생성할 수 있습니다.
