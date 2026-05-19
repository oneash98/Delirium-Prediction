# 6_modeling

`src/6_modeling.ipynb`는 `5_data_preprocessing.ipynb`에서 생성한 LSTM tensor를 사용해 multi-output LSTM을 학습하고, masked loss/metric으로 검증 및 test 평가를 수행합니다.

노트북은 주피터에서 위에서 아래로 한 셀씩 실행하는 흐름을 전제로 구성합니다. 각 단계는 준비, 로딩, validation split, 모델/평가 함수 정의, hyperparameter tuning, test 평가, 결과 저장 순서입니다.

## 입력 파일

`processed/modeling/`:

- `X_train_lstm.npy`: train LSTM 입력 tensor, shape `(sequence, time, feature)`.
- `X_test_lstm.npy`: test LSTM 입력 tensor.
- `y_train_lstm.npy`: train any-event target.
- `y_test_lstm.npy`: test any-event target.
- `y_train_steps_lstm.npy`: train horizon별 target, columns `y_t`, `y_t_plus_1`, `y_t_plus_2`.
- `y_test_steps_lstm.npy`: test horizon별 target.
- `y_train_step_mask_lstm.npy`: train horizon별 평가 가능 여부 mask.
- `y_test_step_mask_lstm.npy`: test horizon별 평가 가능 여부 mask.
- `lstm_train_metadata.csv`: train sequence metadata.
- `lstm_test_metadata.csv`: test sequence metadata.

## 노트북 실행 흐름

1. 실행 준비: library import, 난수 고정, 경로 설정, PyTorch device 선택.
2. 전처리 산출물 로딩: LSTM tensor, target, mask, metadata 로딩과 기본 분포 확인.
3. Subject-level validation split: train set 내부에서 `subject_id` 기준 validation set 분리.
4. 모델과 평가 함수 정의: LSTM class, DataLoader, metric, prediction 함수 정의.
5. Hyperparameter tuning: validation macro AUPRC 기준 best trial 선택.
6. Best model test 평가: best checkpoint로 test set metric과 prediction 생성.
7. 결과 저장: tuning 결과, test metric, prediction, model checkpoint, config 저장.

## 경로 설정

노트북은 실행 위치가 다음 중 어디인지 확인해 `PROJECT_DIR`을 설정합니다.

- `Parkinson/src`
- `Parkinson`
- repository root

따라서 Jupyter를 `Parkinson/src`에서 열어도 되고, repository root에서 열어도 `Parkinson/processed/modeling`을 찾을 수 있습니다.

## Validation Split

`6_modeling.ipynb`는 이미 만들어진 train/test split을 바꾸지 않습니다. 대신 hyperparameter tuning을 위해 train split 안에서만 validation split을 새로 만듭니다.

- 분리 단위: `subject_id`
- validation 비율: `VAL_SIZE = 0.20`
- stratification 기준: subject별 `y_any` 최대값
- 목적: 같은 환자의 sequence가 inner train과 validation에 동시에 들어가는 leakage 방지

## 모델 구조

기본 모델은 multi-output LSTM입니다.

- 입력: 4개 12시간 time step의 feature tensor
- LSTM 출력: 마지막 hidden state
- classifier 출력: 3개 logit
- output horizon: `y_t`, `y_t_plus_1`, `y_t_plus_2`

`num_layers == 1`이면 PyTorch LSTM 내부 dropout은 적용하지 않고, 마지막 hidden state 뒤의 classifier dropout만 적용합니다.

## Loss와 Mask 처리

학습 loss는 `BCEWithLogitsLoss(reduction="none")`로 계산한 뒤 target mask를 곱해 평균냅니다.

- `target_mask = 1`: 실제 target이 존재하는 horizon, loss와 metric에 포함
- `target_mask = 0`: 실제 target이 없는 horizon, loss와 horizon별 metric에서 제외

Class imbalance 보정을 위해 horizon별 `pos_weight`를 inner train target 기준으로 계산합니다.

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
- `any_*`: 3개 horizon 중 하나라도 양성인 any-event 기준 metric

Hyperparameter tuning의 선택 기준은 `macro_auprc`입니다. Class imbalance가 있는 outcome이므로 AUPRC를 주요 기준으로 사용합니다.

## Hyperparameter Tuning

현재 grid:

- `hidden_size`: 32, 64
- `num_layers`: 1, 2
- `dropout`: 0.0, 0.2
- `lr`: 1e-3
- `batch_size`: 64
- `weight_decay`: 1e-4

학습 설정:

- `MAX_EPOCHS = 25`
- `PATIENCE = 5`
- optimizer: AdamW
- gradient clipping: max norm 5.0
- best checkpoint 기준: validation `macro_auprc`

## 출력 파일

`outputs/modeling/`:

- `lstm_tuning_results.csv`: hyperparameter trial별 validation metric.
- `lstm_test_metrics.csv`: best model test summary metric.
- `lstm_test_metrics_by_horizon.csv`: best model test horizon별 metric.
- `lstm_test_predictions.csv`: test sequence별 true label, mask, probability, threshold 0.5 prediction.

`models/`:

- `lstm_best_model.pt`: model state dict, parameters, validation/test metric이 포함된 PyTorch payload.
- `lstm_best_model_config.json`: best model 설정과 평가 결과 요약.

## QA 체크

노트북 실행 중 확인하는 항목입니다.

- train/test input tensor shape
- train/test any-event positive rate
- horizon별 evaluable target 수
- horizon별 masked positive rate
- train/test input NaN 개수
- inner train/validation sequence 수와 subject 수
- validation horizon별 positive rate
- tuning trial별 핵심 metric
- 최종 test summary metric과 horizon별 metric

## 주의 사항

- `best_artifact`는 tuning 셀 실행 후 생성됩니다. test 평가 섹션은 tuning 완료 후 실행해야 합니다.
- Notebook output은 재현성을 위해 저장하지 않습니다. 필요한 결과는 CSV, `.pt`, `.json` 파일로 저장합니다.
- Test set은 hyperparameter 선택에 사용하지 않고, best model 선택 후 최종 평가에만 사용합니다.
