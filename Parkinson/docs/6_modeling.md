# 6_modeling

## Within t+2 비교 모델 추가

`src/6_modeling_within_t_plus_2.ipynb`는 기존 전처리 산출물(`processed/data_split/`)을 그대로 사용해 비교용 ML baseline과 single-output LSTM을 학습합니다. 재사용 가능한 함수와 CLI 실행용 코드는 `src/6_modeling_within_t_plus_2.py`에 함께 둡니다.

- ML/deep learning baseline: LR, RF, XGB, LightGBM, MLP
- ML input: `X_*_lstm.npy[:, -1, :]`, 즉 anchor `t` 시점 feature만 사용
- ML target: `y_*_lstm.npy`, 즉 `t`, `t+1`, `t+2` 중 delirium 발생 여부
- target window: binary within target에는 horizon별 mask가 없으므로 기본값은 `target_available_count >= 3`인 full `t~t+2` window만 사용
- LSTM input: 기존과 동일하게 `t-3~t` 4개 time step
- LSTM output: encoder-decoder horizon 3개 출력이 아니라 `within_t_plus_2` binary logit 1개
- CV: 기존과 동일하게 train split 내부 subject-level K-fold
- tuning objective: CV 평균 AUPRC
- GPU: PyTorch MLP/LSTM은 CUDA 사용, XGB/LightGBM은 CUDA가 보이면 GPU parameter를 우선 사용

실행 예시:

```bash
Parkinson/src/6_modeling_within_t_plus_2.ipynb
```

빠른 smoke test:

```bash
python Parkinson/src/6_modeling_within_t_plus_2.py --models LR MLP LSTM --n-folds 2 --n-trials-ml 1 --n-trials-mlp 1 --n-trials-lstm 1 --max-epochs 1
```

기존 masked multi-horizon 노트북처럼 마지막 bin 근처의 partial target window까지 포함하려면 `--allow-partial-target-window`를 추가합니다.

XGB/LightGBM이 없는 환경에서는 해당 모델만 skip됩니다. 필요한 패키지는 `Parkinson/requirements-modeling.txt`에 정리했습니다.

주요 출력:

- `outputs/modeling/within_t_plus_2/*_t_point_tuning_results.csv`
- `outputs/modeling/within_t_plus_2/*_t_point_test_metrics.csv`
- `outputs/modeling/within_t_plus_2/mlp_t_point_test_metrics.csv`
- `outputs/modeling/within_t_plus_2/lstm_within_t_plus_2_tuning_results.csv`
- `outputs/modeling/within_t_plus_2/lstm_within_t_plus_2_test_metrics.csv`
- `outputs/modeling/within_t_plus_2/within_t_plus_2_test_metrics_summary.csv`
- `models/within_t_plus_2/*_t_point_within_t_plus_2.joblib`
- `models/within_t_plus_2/lstm_within_t_plus_2_best_model.pt`

`src/6_modeling.ipynb`는 `5_data_preprocessing.ipynb`에서 생성한 LSTM tensor를 사용해 encoder-decoder multi-horizon LSTM을 학습하고, masked loss/metric으로 검증 및 test 평가를 수행합니다.

노트북은 주피터에서 위에서 아래로 한 셀씩 실행하는 흐름을 전제로 구성합니다. 각 단계는 준비, 로딩, subject-level CV 구성, 모델/평가 함수 정의, hyperparameter tuning, 전체 train 재학습, test 평가, 결과 저장 순서입니다.

## 입력 파일

`processed/data_split/`:

- `X_train_lstm.npy`: train LSTM 입력 tensor, shape `(sequence, time, feature)`.
- `X_test_lstm.npy`: test LSTM 입력 tensor.
- `y_train_lstm.npy`: train `within_t_plus_2` target.
- `y_test_lstm.npy`: test `within_t_plus_2` target.
- `y_train_steps_lstm.npy`: train horizon별 target, columns `y_t`, `y_t_plus_1`, `y_t_plus_2`.
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
5. Hyperparameter tuning: Optuna로 CV 평균 macro AUPRC 기준 best trial 선택.
6. Best parameter 전체 train 재학습과 test 평가: 선택된 best parameter로 전체 train set을 다시 학습한 뒤 test set metric과 prediction 생성.
7. 결과 저장: tuning 결과, test metric, prediction, model checkpoint, config 저장.

## 경로 설정

노트북은 실행 위치가 다음 중 어디인지 확인해 `PROJECT_DIR`을 설정합니다.

- `Parkinson/src`
- `Parkinson`
- repository root

따라서 Jupyter를 `Parkinson/src`, `Parkinson`, repository root 중 어디에서 열어도 `Parkinson/processed/data_split`을 찾을 수 있습니다.

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
- decoder: 미래 observed feature 없이 horizon embedding sequence를 입력받아 `y_t`, `y_t_plus_1`, `y_t_plus_2` logit을 순차 생성
- classifier 출력: horizon별 1개 logit, 최종 shape `(batch, 3)`
- output horizon: `y_t`, `y_t_plus_1`, `y_t_plus_2`

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
- `within_t_plus_1_*`: `t~t+1` 중 하나라도 양성인 window 기준 metric
- `within_t_plus_2_*`: `t~t+2` 중 하나라도 양성인 window 기준 metric

Hyperparameter tuning의 선택 기준은 fold별 `macro_auprc`의 CV 평균입니다. Class imbalance가 있는 outcome이므로 AUPRC를 주요 기준으로 사용합니다.

## Hyperparameter Tuning

Optuna 설정:

- `N_TRIALS = 30`
- sampler: `TPESampler(seed=RANDOM_STATE)`

탐색 공간:

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
- fold별 best checkpoint 기준: validation fold `macro_auprc`
- 최종 모델: best parameter로 전체 train set을 CV 평균 best epoch만큼 재학습

## 출력 파일

`outputs/modeling/`:

- `lstm_gpu_tuning_results.csv`: Optuna trial별 CV 평균/표준편차 metric.
- `lstm_gpu_optuna_trials.csv`: Optuna trial summary와 parameter.
- `lstm_gpu_cv_fold_metrics.csv`: trial/fold별 validation fold summary metric.
- `lstm_gpu_cv_fold_metrics_by_horizon.csv`: trial/fold별 validation fold horizon metric.
- `lstm_gpu_cv_fold_history.csv`: trial/fold/epoch별 train loss와 validation summary metric.
- `lstm_gpu_test_metrics.csv`: best parameter로 재학습한 최종 model의 test summary metric.
- `lstm_gpu_test_metrics_by_horizon.csv`: best parameter로 재학습한 최종 model의 test horizon별 metric.
- `lstm_gpu_test_predictions.csv`: test sequence별 true label, mask, probability, threshold 0.5 prediction.
- `figures/lstm_final_train_loss.png`: 최종 전체 train 재학습의 train loss curve.
- `figures/lstm_best_trial_cv_macro_auprc.png`: best trial의 fold별 validation macro AUPRC curve와 epoch별 CV 평균 curve.
- `figures/lstm_test_horizon_auprc_auroc.png`: test set horizon별 AUPRC/AUROC bar plot.

`models/`:

- `lstm_best_model_gpu.pt`: model state dict, parameters, CV/test metric이 포함된 PyTorch payload.
- `lstm_best_model_gpu_config.json`: best model 설정과 평가 결과 요약.

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
- best trial의 CV validation macro AUPRC curve
- test horizon별 AUPRC/AUROC bar plot
- 최종 test summary metric과 horizon별 metric

## 주의 사항

- `best_trial`은 tuning 셀 실행 후 생성됩니다. test 평가 섹션은 tuning 완료 후 실행해야 합니다.
- Notebook output은 재현성을 위해 저장하지 않습니다. 필요한 결과는 CSV, `.pt`, `.json` 파일로 저장합니다.
- Test set은 hyperparameter 선택에 사용하지 않고, best model 선택 후 최종 평가에만 사용합니다.
