# 6_modeling

`src/6_modeling.ipynb`는 기존 전처리 산출물(`processed/data_split/`)을 그대로 사용해 within `t+1~t+2` 비교 모델을 먼저 학습하고, 마지막에 multi-horizon XGBoost, multi-output MLP, encoder-decoder LSTM을 추가 테스트로 학습합니다. 모델링 구현은 해당 `.ipynb` 안에 둡니다.

## Within t+2 비교 모델

- ML/deep learning baseline: LR, RF, XGB, LightGBM, MLP
- ML input: `X_*_lstm.npy[:, -1, :]`, 즉 anchor `t` 시점 feature만 사용
- ML target: `y_*_lstm.npy`, 즉 `t+1`, `t+2` 중 delirium 발생 여부
- target window: binary within target에는 horizon별 mask가 없으므로 `target_available_count >= 2`인 full `t+1~t+2` window만 사용
- feature scaling: `5_data_preprocessing.ipynb`에서 train 기준 numeric imputation과 `StandardScaler`가 이미 적용된 `X_*_lstm.npy`를 그대로 사용하며, 모델링 노트북에서는 LR/MLP 포함 baseline에 별도 sklearn scaler를 다시 fit하지 않음
- LSTM input: 최대 `t-3~t` 4개 time step이며, 초기 anchor의 left padding은 input mask로 제외
- LSTM output: encoder-decoder horizon 2개 출력이 아니라 `within_t_plus_2` binary logit 1개
- CV: train split 내부 subject-level stratified K-fold
- tuning objective: CV 평균 AUPRC
- GPU: PyTorch MLP/LSTM은 CUDA 사용, XGB/LightGBM은 CUDA가 보이면 GPU parameter를 우선 사용하고 GPU fit 실패 시 CPU로 재학습

실행:

```bash
Parkinson/src/6_modeling.ipynb
```

필요한 패키지는 `Parkinson/requirements-modeling.txt`에 정리했습니다.

### 통합 노트북 실행 흐름

1. 실행 준비: library import, 경로 설정, 설정값, CUDA device와 seed 설정.
2. 전처리 산출물 로딩: `required_files` 정의 후 `X_train`, `X_test`, `y_train_within_t_plus_2`, `y_test_within_t_plus_2`, horizon별 target/mask, metadata를 직접 로딩합니다.
3. Full target window subset 생성: within `t+1~t+2` 비교 모델용으로 `target_available_count >= 2`인 row를 별도 `*_within` 변수에 저장합니다.
4. 공통 subject-level CV split 생성: 전체 train metadata 기준 subject split을 만든 뒤, within 비교 모델과 multi-horizon 모델에 각각 row mask를 적용합니다.
5. Within `t+1~t+2` 비교 모델 학습: LR/RF/XGB/LightGBM, MLP, single-output LSTM 순서로 Optuna tuning과 전체 train 재학습/test 평가를 수행합니다.
6. Within `t+1~t+2` 최종 비교 저장: 모델별 test metric summary와 모델별 probability를 합친 row-level prediction table을 저장합니다.
7. Multi-horizon 추가 테스트: XGBoost horizon별 독립 모델, multi-output MLP, encoder-decoder LSTM을 학습하고 horizon별 test probability와 metric을 저장합니다.

### Within t+2 구현 셀 구조

ML baseline 구현은 모델별로 나누어 둡니다.

- `ML baseline 공통 함수`: estimator fit, prediction, XGB/LightGBM GPU 실패 시 CPU 재학습.
- `Logistic Regression baseline`: LR 탐색 공간과 estimator.
- `Random Forest baseline`: RF 탐색 공간과 estimator.
- `XGBoost baseline`: XGB GPU parameter, 탐색 공간, estimator.
- `LightGBM baseline`: LightGBM GPU parameter, 탐색 공간, estimator.
- `ML baseline dispatch 함수`: 모델명에 따라 위 함수들을 연결합니다.
- `ML baseline tuning 함수`: subject-level CV, Optuna tuning, test 평가, 저장을 수행합니다.

ML baseline과 MLP baseline은 `5_data_preprocessing.ipynb`에서 저장한 feature matrix를 그대로 사용합니다. numeric feature는 이미 train split 기준 imputation과 scaling이 적용되어 있으므로, `6_modeling.ipynb`에서는 fold별 또는 전체 train 기준 sklearn `StandardScaler`를 다시 fit하지 않습니다. PyTorch 코드의 `torch.amp.GradScaler`는 mixed precision gradient scaling 용도이며 feature scaling과 별개입니다.

MLP와 single-output LSTM도 각각 다음 셀로 분리합니다.

- 모델과 DataLoader
- 탐색 공간
- fold 학습 함수
- 전체 train 재학습 함수
- tuning 함수

### Within t+2 Hyperparameter 탐색 공간

LR:

- `C`: 1e-3-1e2, log scale
- `penalty`: `l1`, `l2`
- 고정 설정: `solver="liblinear"`, `class_weight="balanced"`, `max_iter=2000`

RF:

- `n_estimators`: 200-800, step 100
- `max_depth`: `None`, 4, 8, 12, 16, 24
- `min_samples_split`: 2, 5, 10, 20
- `min_samples_leaf`: 1, 2, 4, 8
- `max_features`: `sqrt`, `log2`, 0.5
- 고정 설정: `class_weight="balanced_subsample"`, `n_jobs=-1`

XGB:

- `n_estimators`: 200-800, step 100
- `max_depth`: 2-8
- `learning_rate`: 0.01-0.2, log scale
- `subsample`: 0.6-1.0
- `colsample_bytree`: 0.6-1.0
- `min_child_weight`: 1.0-20.0, log scale
- `reg_alpha`: 1e-8-1.0, log scale
- `reg_lambda`: 1e-3-10.0, log scale
- 고정 설정: `objective="binary:logistic"`, `eval_metric="aucpr"`, train fold 기준 `scale_pos_weight`

LightGBM:

- `n_estimators`: 200-1000, step 100
- `learning_rate`: 0.01-0.2, log scale
- `num_leaves`: 15-127
- `max_depth`: -1, 3, 5, 7, 9, 12
- `min_child_samples`: 10-100
- `subsample`: 0.6-1.0
- `colsample_bytree`: 0.6-1.0
- `reg_alpha`: 1e-8-1.0, log scale
- `reg_lambda`: 1e-3-10.0, log scale
- 고정 설정: `objective="binary"`, train fold 기준 `scale_pos_weight`

MLP:

- `hidden_size`: 64, 128, 256, 512
- `num_layers`: 1-3
- `dropout`: 0.0-0.5
- `lr`: 1e-4-3e-3, log scale
- `batch_size`: 32, 64, 128
- `weight_decay`: 1e-6-1e-3, log scale
- 학습 설정: `BCEWithLogitsLoss(pos_weight=...)`, AdamW, gradient clipping max norm 5.0, early stopping patience 5

Single-output LSTM:

- `hidden_size`: 32, 64, 128, 256
- `num_layers`: 1-3
- `dropout`: 0.0-0.5
- `lr`: 1e-4-3e-3, log scale
- `batch_size`: 32, 64, 128
- `weight_decay`: 1e-6-1e-3, log scale
- 학습 설정: `BCEWithLogitsLoss(pos_weight=...)`, AdamW, gradient clipping max norm 5.0, early stopping patience 5

주요 출력:

- `outputs/modeling/within_t_plus_2/*_t_point_tuning_results.csv`
- `outputs/modeling/within_t_plus_2/*_t_point_cv_fold_metrics.csv`
- `outputs/modeling/within_t_plus_2/*_t_point_optuna_trials.csv`
- `outputs/modeling/within_t_plus_2/*_t_point_test_metrics.csv`
- `outputs/modeling/within_t_plus_2/*_t_point_test_predictions.csv`
- `outputs/modeling/within_t_plus_2/mlp_t_point_tuning_results.csv`
- `outputs/modeling/within_t_plus_2/mlp_t_point_cv_fold_metrics.csv`
- `outputs/modeling/within_t_plus_2/mlp_t_point_cv_fold_history.csv`
- `outputs/modeling/within_t_plus_2/mlp_t_point_optuna_trials.csv`
- `outputs/modeling/within_t_plus_2/mlp_t_point_test_metrics.csv`
- `outputs/modeling/within_t_plus_2/mlp_t_point_test_predictions.csv`
- `outputs/modeling/within_t_plus_2/lstm_within_t_plus_2_tuning_results.csv`
- `outputs/modeling/within_t_plus_2/lstm_within_t_plus_2_cv_fold_metrics.csv`
- `outputs/modeling/within_t_plus_2/lstm_within_t_plus_2_cv_fold_history.csv`
- `outputs/modeling/within_t_plus_2/lstm_within_t_plus_2_optuna_trials.csv`
- `outputs/modeling/within_t_plus_2/lstm_within_t_plus_2_test_metrics.csv`
- `outputs/modeling/within_t_plus_2/lstm_within_t_plus_2_test_predictions.csv`
- `outputs/modeling/within_t_plus_2/within_t_plus_2_test_metrics_summary.csv`
- `outputs/modeling/within_t_plus_2/within_t_plus_2_test_predictions_all_models.csv`
- `models/within_t_plus_2/*_t_point_within_t_plus_2.joblib`
- `models/within_t_plus_2/mlp_t_point_within_t_plus_2_best_model.pt`
- `models/within_t_plus_2/lstm_within_t_plus_2_best_model.pt`
- `models/within_t_plus_2/lstm_within_t_plus_2_best_model_config.json`

Multi-horizon 추가 테스트는 `5_data_preprocessing.ipynb`에서 생성한 LSTM tensor와 horizon별 target mask를 사용합니다. XGBoost와 multi-output MLP는 anchor `t` 시점 feature를 입력으로 쓰고, encoder-decoder LSTM은 `t-3~t` sequence 전체를 입력으로 사용합니다.

노트북은 주피터에서 위에서 아래로 한 셀씩 실행하는 흐름을 전제로 구성합니다. 각 단계는 준비, 로딩, subject-level CV 구성, 모델/평가 함수 정의, hyperparameter tuning, 전체 train 재학습, test 평가, 결과 저장 순서입니다.

## 입력 파일

`processed/data_split/`:

- `X_train_lstm.npy`: train LSTM 입력 tensor, shape `(sequence, time, feature)`.
- `X_test_lstm.npy`: test LSTM 입력 tensor.
- `X_train_input_mask_lstm.npy`: train LSTM input mask, shape `(sequence, time)`.
- `X_test_input_mask_lstm.npy`: test LSTM input mask.
- `y_train_lstm.npy`: train `within_t_plus_2` target.
- `y_test_lstm.npy`: test `within_t_plus_2` target.
- `y_train_steps_lstm.npy`: train horizon별 target, columns `y_t_plus_1`, `y_t_plus_2`.
- `y_test_steps_lstm.npy`: test horizon별 target.
- `y_train_step_mask_lstm.npy`: train horizon별 평가 가능 여부 mask.
- `y_test_step_mask_lstm.npy`: test horizon별 평가 가능 여부 mask.
- `lstm_train_metadata.csv`: train sequence metadata.
- `lstm_test_metadata.csv`: test sequence metadata.

## 노트북 실행 흐름

1. 실행 준비: library import, 난수 고정, 경로 설정, PyTorch device 선택.
2. 전처리 산출물 로딩: LSTM tensor, target, mask, metadata 로딩과 기본 분포 확인.
3. Subject-level cross-validation split: train set 내부에서 `subject_id` 기준 K-fold CV 구성.
4. 모델과 평가 함수 정의: LSTM class, DataLoader, metric, prediction 함수 정의.
5. Hyperparameter tuning: Optuna로 CV 평균 within `t+1~t+2` AUPRC 기준 best trial 선택.
6. Best parameter 전체 train 재학습과 test 평가: 선택된 best parameter로 전체 train set을 다시 학습한 뒤 test set metric과 prediction 생성.
7. 결과 저장: tuning 결과, test metric, prediction, model checkpoint, config 저장.

## 경로 설정

노트북은 Jupyter 작업 디렉터리를 `Parkinson/src`로 둔 상태에서 실행합니다. `PROJECT_DIR`은 `Path.cwd().resolve().parent`로 고정합니다.

## Cross-Validation Split

`6_modeling.ipynb`는 이미 만들어진 train/test split을 바꾸지 않습니다. 대신 hyperparameter tuning을 위해 train split 안에서만 subject-level K-fold CV를 수행합니다.

- 분리 단위: `subject_id`
- fold 수: `N_FOLDS = 5`
- stratification 기준: subject별 `y_within_t_plus_2` 최대값
- 목적: 같은 환자의 sequence가 fold train과 validation fold에 동시에 들어가는 leakage 방지

## 모델 구조

기본 모델은 encoder-decoder multi-horizon LSTM입니다.

- 입력: 4개 12시간 time step의 feature tensor
- encoder: `t-3`부터 `t`까지의 input sequence를 읽고 마지막 hidden/cell state를 생성
- decoder: 미래 observed feature 없이 horizon embedding sequence를 입력받아 `y_t_plus_1`, `y_t_plus_2` logit을 순차 생성
- classifier 출력: horizon별 1개 logit, 최종 shape `(batch, 2)`
- output horizon: `y_t_plus_1`, `y_t_plus_2`

`num_layers == 1`이면 PyTorch LSTM 내부 dropout은 적용하지 않고, decoder output 뒤의 classifier dropout만 적용합니다.

## Loss와 Mask 처리

학습 loss는 `BCEWithLogitsLoss(reduction="none")`로 계산한 뒤 target mask를 곱해 평균냅니다.

- `target_mask = 1`: 실제 target이 존재하는 horizon, loss와 metric에 포함
- `target_mask = 0`: 실제 target이 없는 horizon, loss와 horizon별 metric에서 제외

Class imbalance 보정을 위해 horizon별 `pos_weight`를 각 fold의 train target 기준으로 계산합니다. 최종 test용 전체 train 재학습에서는 전체 train target 기준으로 다시 계산합니다.

## 평가 지표

Horizon별 metric:

- AUROC
- AUPRC
- sensitivity
- specificity
- PPV
- NPV
- TP/FP/TN/FN
- evaluable target 수

Summary metric:

- `macro_auroc`: horizon별 AUROC 평균
- `macro_auprc`: horizon별 AUPRC 평균
- `within_t_plus_1_*`: `t+1` 양성 기준 metric
- `within_t_plus_2_*`: `t+1~t+2` 중 하나라도 양성인 window 기준 metric

Hyperparameter tuning의 선택 기준은 fold별 `within_t_plus_2_auprc`의 CV 평균입니다. 최종 비교 endpoint가 within `t+1~t+2` binary outcome이므로, multi-horizon 모델도 horizon별 probability를 결합한 within-window AUPRC를 기준으로 선택합니다. `macro_auprc`와 horizon별 AUPRC는 보조 성능 지표로 함께 저장합니다.

## Hyperparameter Tuning

Optuna 설정:

- `N_TRIALS_MULTI_XGB = 30`
- `N_TRIALS_MULTI_MLP = 30`
- `N_TRIALS_MULTI_HORIZON = 30`
- sampler: `TPESampler(seed=RANDOM_STATE)`

XGBoost horizon별 독립 모델:

- 입력: anchor `t` 시점 feature
- 출력: `y_t_plus_1`, `y_t_plus_2` 각각에 대한 독립 binary classifier
- 탐색 공간: within `t+1~t+2` XGB baseline과 동일
- 평가: horizon별 probability를 `masked_horizon_metrics`에 넣어 within-window AUPRC, macro AUPRC, horizon별 metric 계산

Multi-output MLP:

- 입력: anchor `t` 시점 feature
- 출력: 2개 logit, 즉 `y_t_plus_1`, `y_t_plus_2`
- masked BCE loss: target mask가 0인 horizon은 loss에서 제외

Encoder-decoder LSTM 탐색 공간:

- `hidden_size`: 32, 64, 128, 256
- `num_layers`: 1-3
- `dropout`: 0.0-0.5
- `lr`: 1e-4-3e-3, log scale
- `batch_size`: 32, 64, 128
- `weight_decay`: 1e-6-1e-3, log scale

학습 설정:

- `MAX_EPOCHS = 25`
- `PATIENCE = 5`
- optimizer: AdamW
- gradient clipping: max norm 5.0
- fold별 best checkpoint 기준: validation fold `within_t_plus_2_auprc`
- 최종 모델: best parameter로 전체 train set을 CV 평균 best epoch만큼 재학습

## 출력 파일

`outputs/modeling/`:

- `multi_horizon_test_metrics_summary.csv`: XGBoost, multi-output MLP, encoder-decoder LSTM의 multi-horizon test summary.
- `xgb_multi_horizon_tuning_results.csv`
- `xgb_multi_horizon_optuna_trials.csv`
- `xgb_multi_horizon_cv_fold_metrics.csv`
- `xgb_multi_horizon_test_metrics.csv`
- `xgb_multi_horizon_test_metrics_by_horizon.csv`
- `xgb_multi_horizon_test_predictions.csv`
- `mlp_multi_horizon_tuning_results.csv`
- `mlp_multi_horizon_optuna_trials.csv`
- `mlp_multi_horizon_cv_fold_metrics.csv`
- `mlp_multi_horizon_cv_fold_metrics_by_horizon.csv`
- `mlp_multi_horizon_cv_fold_history.csv`
- `mlp_multi_horizon_test_metrics.csv`
- `mlp_multi_horizon_test_metrics_by_horizon.csv`
- `mlp_multi_horizon_test_predictions.csv`
- `lstm_gpu_tuning_results.csv`: Optuna trial별 CV 평균/표준편차 metric.
- `lstm_gpu_optuna_trials.csv`: Optuna trial summary와 parameter.
- `lstm_gpu_cv_fold_metrics.csv`: trial/fold별 validation fold summary metric.
- `lstm_gpu_cv_fold_metrics_by_horizon.csv`: trial/fold별 validation fold horizon metric.
- `lstm_gpu_cv_fold_history.csv`: trial/fold/epoch별 train loss와 validation summary metric.
- `lstm_gpu_test_metrics.csv`: best parameter로 재학습한 최종 model의 test summary metric.
- `lstm_gpu_test_metrics_by_horizon.csv`: best parameter로 재학습한 최종 model의 test horizon별 metric.
- `lstm_gpu_test_predictions.csv`: test sequence별 true label, mask, probability, threshold 0.5 prediction.
- `figures/lstm_final_train_loss.png`: 최종 전체 train 재학습의 train loss curve.
- `figures/lstm_best_trial_cv_within_t_plus_2_auprc.png`: best trial의 fold별 validation within `t+1~t+2` AUPRC curve와 epoch별 CV 평균 curve.
- `figures/lstm_test_horizon_auprc_auroc.png`: test set horizon별 AUPRC/AUROC bar plot.

`models/`:

- `lstm_best_model_gpu.pt`: model state dict, parameters, CV/test metric이 포함된 PyTorch payload.
- `lstm_best_model_gpu_config.json`: best model 설정과 평가 결과 요약.
- `xgb_multi_horizon.joblib`: horizon별 XGBoost model payload.
- `mlp_multi_horizon_best_model.pt`: multi-output MLP model payload.

## QA 체크

노트북 실행 중 확인하는 항목입니다.

- train/test input tensor shape
- train/test `within_t_plus_1`, `within_t_plus_2` positive rate
- horizon별 evaluable target 수
- horizon별 masked positive rate
- train/test input NaN 개수
- CV fold별 train/validation sequence 수와 subject 수
- CV fold별 validation horizon positive rate
- Optuna trial별 CV 평균 핵심 metric
- 최종 train loss curve
- best trial의 CV validation within `t+1~t+2` AUPRC curve
- test horizon별 AUPRC/AUROC bar plot
- 최종 test summary metric과 horizon별 metric

## 주의 사항

- `best_trial`은 tuning 셀 실행 후 생성됩니다. test 평가 섹션은 tuning 완료 후 실행해야 합니다.
- Notebook output은 재현성을 위해 저장하지 않습니다. 필요한 결과는 CSV, `.pt`, `.json` 파일로 저장합니다.
- Test set은 hyperparameter 선택에 사용하지 않고, best model 선택 후 최종 평가에만 사용합니다.
