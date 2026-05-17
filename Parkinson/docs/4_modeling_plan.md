# 4_modeling 계획

이 문서는 모델링 단계 작업 계획입니다. Subject-level train/test split과 LSTM sequence index 구성의 구현 상세는 `4_train_test_construction.md`에 정리합니다.

모델링 단계에서는 12시간 bin-level table을 사용해 subject-level train/test split과 padded LSTM sequence를 만든 뒤, train 기준 feature selection과 imputation을 수행합니다.

## 입력 파일

`processed/transform/`:

- `events_12h_binned.csv`: cohort criteria를 통과한 12시간 bin-level wide table. `extraction_variable_catalog.csv`의 `binning` 규칙으로 생성된 집계/최신값/노출/static feature를 포함합니다.
- `cohort_final.csv`: cohort criteria를 통과한 stay-level cohort table.

`split` 컬럼과 `train_subject_ids.csv`, `test_subject_ids.csv`는 `4_train_test_construction.ipynb` 실행 후 생성됩니다.

## 환자 단위 무작위 train/test 분할

`4_train_test_construction.ipynb`에서 subject 단위 80/20 random split을 수행합니다.

- `ever_delirium`은 EDA와 split 확인용 subject-level label이며, 기본 모델 target으로 쓰지 않습니다.
- Train/test split은 subject-level로 생성하고 이후 preprocessing/modeling 단계에서 그대로 사용합니다.

## Split 산출물 저장

`4_train_test_construction.ipynb`에서 생성하는 split 산출물입니다.

- `events_12h_binned.csv`에 `split` 컬럼을 저장합니다.
- `cohort_final.csv`에 `split` 컬럼을 저장합니다.
- `train_subject_ids.csv`, `test_subject_ids.csv`를 저장합니다.

## 모델링 핵심 원칙

- Bin-level outcome은 `delirium`입니다.
- 기본 모델 구조는 12시간 bin을 time step으로 사용하는 LSTM입니다.
- 입력은 최대 4개 time step의 feature이며, 실제 bin 수가 4개보다 적으면 왼쪽을 `PAD`로 채웁니다.
- 예측 대상은 anchor bin과 그 다음 2개 time step의 delirium 여부입니다. 실제 target이 없는 위치는 `PAD`로 두고 target mask를 0으로 설정해 loss에서 제외합니다.
- 각 stay 안에서 anchor bin을 오른쪽으로 sliding하며 가능한 sequence row를 생성합니다.
- 첫 anchor는 `t2`입니다. PAD 3개와 `t1`만 있는 sequence는 만들지 않습니다.
- Transform 단계 cohort inclusion은 ICU LOS 24시간 이상입니다.
- Window 길이, feature 제외 기준, imputation 값은 train set에서만 결정합니다.
- Test set은 train에서 정한 window, feature 목록, imputation 값을 그대로 적용받습니다.

## LSTM Time Step 구성

12시간 bin-level table인 `events_12h_binned.csv`를 기본 입력 feature source로 사용합니다.

한 training example은 ICU stay 안의 anchor bin 1개를 기준으로 구성합니다.

- Input: 최대 4개 time step feature, 부족한 앞쪽 step은 `PAD`
- Target: anchor bin, anchor+1, anchor+2의 delirium 여부
- Target mask: 실제 target horizon은 1, `PAD` target horizon은 0
- 각 time step은 12시간 bin입니다.

Anchor는 stay 안의 `t2`부터 마지막 bin까지 순서대로 사용합니다. 따라서 bin이 10개인 stay는 최대 9개 sequence row를 만들 수 있습니다.

## Feature 생성

Feature 생성은 `events_12h_binned.csv`를 기준으로 수행합니다.

`events_12h_binned.csv`에는 `prev_delirium`이 포함됩니다. 이는 같은 stay의 직전 12시간 bin에서의 delirium 결과이며, 첫 time step은 입원 전 직전 결과가 없으므로 `0`입니다.

식별/metadata:

- `subject_id`
- `stay_id`
- `bin`
- `split`
- `delirium`

기본정보:

- `age`
- `gender`
- `race`
- `los_hours`

Static/body measure:

- `weight`
- `height`

Binary exposure:

- medication feature
- procedure/device feature
- window 안에서 한 번이라도 exposure가 있으면 `1`, 아니면 `0`

Transform binned table의 `delirium`은 12시간 `stay_id`/`bin` 단위 label입니다. 해당 bin 안 assessment 중 하나라도 positive면 `1`, assessment는 있지만 positive가 없으면 `0`, assessment 자체가 없으면 `NaN`입니다. 현재 train/test construction은 이 bin-level label만 사용합니다.

Medication feature는 transform 단계에서 실제 투약 event가 기록된 charttime row만 `1`입니다. 모델링 단계에서는 candidate observation window 안에 해당 medication feature가 한 번이라도 `1`이면 window-level exposure `1`로 집계합니다.

Procedure/device feature는 transform 단계에서 charttime row의 `charttime`이 procedure interval 안에 들어오면 `1`입니다. 모델링 단계에서는 medication과 동일하게 window 안 max 값으로 window-level exposure를 만듭니다.

연속형 임상 변수:

- vital
- lab
- neuro score
- coagulation/ABG/chemistry/CBC

각 연속형 변수는 transform 단계의 12시간 bin 집계값을 사용합니다.

- aggregation feature
- latest/most recent feature
- measurement count 또는 exposure indicator
- missingness indicator 또는 observed indicator

## Missingness와 Feature Selection

EDA 단계에서는 전체 cohort의 관측 패턴을 보되, 실제 feature 제외 결정은 train set 기준으로 수행합니다.

Train set에서 계산할 항목:

- feature별 missing rate
- feature별 observed sequence 수
- feature별 positive/negative outcome에서의 observed rate
- horizon mask별 evaluable target 수

기본 제외 기준:

- train sequence 기준 missing rate가 지나치게 높은 feature는 제외 후보로 표시합니다.
- 최초 threshold는 95%로 두고, 모델 성능과 임상적 중요도를 함께 보고 조정합니다.

중요:

- Test missingness를 보고 feature 제외 여부를 결정하지 않습니다.
- Test missingness는 최종 보고용으로만 출력합니다.

## Imputation

Imputation은 train set에서 fit하고 test set에는 transform만 적용합니다.

기본 정책:

- 연속형 window feature: train median
- binary exposure feature: 0
- count feature: 0
- categorical feature: train mode 또는 explicit `Unknown`

Imputer 객체와 feature 목록은 저장합니다.

저장 후보:

- `models/preprocess/lstm_feature_columns.json`
- `models/preprocess/lstm_preprocessor.joblib`
- `models/preprocess/lstm_preprocess_params.json`

## 모델 비교

각 모델 후보에 대해 동일한 train/test subject split과 sequence index를 사용합니다.

비교 절차:

1. train sequence에서 preprocessing을 fit합니다.
2. train 기준 feature exclusion과 imputation을 fit합니다.
3. 같은 설정을 test sequence에 적용합니다.
4. masked target loss/metric으로 모델을 비교합니다.
5. 가장 유망한 모델과 hyperparameter를 선택합니다.

모델 후보:

- Multi-output LSTM
- Logistic Regression baseline
- Random Forest baseline
- XGBoost baseline

우선 평가 지표:

- AUPRC
- AUROC
- sensitivity/specificity
- PPV/NPV
- calibration summary

Class imbalance가 있으므로 AUPRC를 주요 비교 지표로 둡니다.

## 산출물 계획

모델링 단계에서 생성할 파일:

- `processed/modeling/events_12h_binned_with_split.csv`
- `processed/modeling/cohort_final_with_split.csv`
- `processed/modeling/lstm_sequence_index_train.csv`
- `processed/modeling/lstm_sequence_index_test.csv`
- `processed/modeling/y_train_step_mask_lstm.npy`
- `processed/modeling/y_test_step_mask_lstm.npy`
- `processed/modeling/lstm_preprocessing_summary.csv`
- `processed/modeling/lstm_test_metrics.csv`
- `processed/modeling/lstm_test_metrics_by_horizon.csv`
- `processed/modeling/lstm_test_predictions.csv`
- `models/preprocess/` 아래 feature list, imputer, categorical mapping
- `models/` 아래 학습 모델과 평가 결과

## QA 체크

모델링 노트북은 다음을 반드시 출력합니다.

- train/test sequence row 수
- train/test `delirium` 분포
- target mask별 evaluable horizon 수
- window 후보별 feature 수
- train/test imputation 전후 결측률
- 최종 모델 입력에 NaN이 남아 있는지

## 아직 결정할 수 있는 항목

다음 항목은 모델링 실험을 하며 조정합니다.

- observation window 후보 추가/삭제
- high-missingness threshold
- feature aggregation 종류 확대 여부
- categorical encoding 방식
- model family와 hyperparameter search 범위
