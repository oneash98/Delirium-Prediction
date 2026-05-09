# 3_modeling 계획

이 문서는 `2_data_transform.ipynb` 이후 모델링 단계에서 수행할 작업 계획입니다.

Transform 단계는 hourly timeseries와 assessment index, subject-level split까지만 만듭니다. 모델링 단계에서는 train/test split을 유지한 상태에서 observation window feature를 만들고, train 기준으로 feature selection과 imputation을 수행합니다.

## 입력 파일

`processed/transform/`:

- `hourly_timeseries_60min.csv`: cohort criteria를 통과한 hourly timeseries. `ever_delirium`, `split` 포함.
- `assessment_index_60min.csv`: assessment-level index. `subject_id`, `stay_id`, `assessment_bin`, `delirium`, `ever_delirium`, `split` 포함.
- `train_subject_ids.csv`, `test_subject_ids.csv`: subject-level split 고정용 파일.

## 핵심 원칙

- Assessment-level outcome은 `delirium`입니다.
- `ever_delirium`은 EDA와 split 확인용 subject-level label이며, 기본 모델 target으로 쓰지 않습니다.
- Train/test split은 `2_data_transform.ipynb`에서 만든 subject-level split을 그대로 사용합니다.
- Window 길이, feature 제외 기준, imputation 값은 train set에서만 결정합니다.
- Test set은 train에서 정한 window, feature 목록, imputation 값을 그대로 적용받습니다.

## Observation Window 후보

섬망 평가 시점 `assessment_bin = b`에 대해 직전 observation window를 만듭니다.

후보 window 길이는 모델링 노트북에서 비교합니다. 기본 후보:

- 4시간: `b-3`부터 `b`
- 8시간: `b-7`부터 `b`
- 12시간: `b-11`부터 `b`
- 24시간: `b-23`부터 `b`

각 후보는 평가 시점을 포함합니다. Window 시작 전 데이터가 부족한 assessment를 어떻게 처리할지는 train set에서 비교 가능하도록 명시적으로 기록합니다.

기본안:

- full window를 구성할 수 없는 assessment는 제외합니다.
- 제외 수를 train/test별로 출력합니다.

## Feature 생성

Feature 생성은 `hourly_timeseries_60min.csv`와 `assessment_index_60min.csv`를 결합해 수행합니다.

식별/metadata:

- `subject_id`
- `stay_id`
- `assessment_bin`
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

Medication feature는 transform 단계에서 실제 투약 event가 기록된 hourly bin만 `1`입니다. 모델링 단계에서는 candidate observation window 안에 해당 medication feature가 한 번이라도 `1`이면 window-level exposure `1`로 집계합니다.

Procedure/device feature는 transform 단계에서 procedure interval과 겹치는 hourly bin이 이미 `1`입니다. 모델링 단계에서는 medication과 동일하게 window 안 max 값으로 window-level exposure를 만듭니다.

연속형 임상 변수:

- vital
- lab
- neuro score
- coagulation/ABG/chemistry/CBC

각 연속형 변수에 대해 window 안 관측값으로 다음 feature를 생성합니다.

- mean
- median
- standard deviation
- minimum
- maximum
- latest observed value
- measurement count
- missingness indicator 또는 observed indicator

초기 모델에서는 feature 수를 줄이기 위해 mean, median, std, latest, count부터 시작하고, min/max는 필요 시 확장합니다.

## Missingness와 Feature Selection

EDA 단계에서는 전체 cohort의 관측 패턴을 보되, 실제 feature 제외 결정은 train set 기준으로 수행합니다.

Train set에서 계산할 항목:

- feature별 missing rate
- feature별 observed assessment 수
- feature별 positive/negative outcome에서의 observed rate
- window 후보별 missingness 변화

기본 제외 기준:

- train assessment 기준 missing rate가 지나치게 높은 feature는 제외 후보로 표시합니다.
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

- `models/preprocess/window_{hours}h_feature_columns.json`
- `models/preprocess/window_{hours}h_imputer.joblib`
- `models/preprocess/window_{hours}h_categorical_mapping.json`

## Window 후보 비교

각 window 후보에 대해 동일한 train/test subject split을 사용합니다.

비교 절차:

1. train assessment에서 window feature를 생성합니다.
2. train 기준 feature exclusion과 imputation을 fit합니다.
3. 같은 설정을 test assessment에 적용합니다.
4. baseline model로 후보 window를 빠르게 비교합니다.
5. 가장 유망한 window를 선택해 본 모델링으로 진행합니다.

Baseline model 후보:

- Logistic Regression
- Random Forest
- XGBoost

우선 평가 지표:

- AUPRC
- AUROC
- sensitivity/specificity
- PPV/NPV
- calibration summary

Class imbalance가 있으므로 AUPRC를 주요 비교 지표로 둡니다.

## 산출물 계획

모델링 단계에서 생성할 파일:

- `processed/modeling/window_{hours}h_train_features.csv`
- `processed/modeling/window_{hours}h_test_features.csv`
- `processed/modeling/window_{hours}h_feature_missingness_train.csv`
- `processed/modeling/window_{hours}h_feature_missingness_test.csv`
- `processed/modeling/window_comparison_metrics.csv`
- `models/preprocess/` 아래 feature list, imputer, categorical mapping
- `models/` 아래 학습 모델과 평가 결과

## QA 체크

모델링 노트북은 다음을 반드시 출력합니다.

- train/test subject overlap이 0인지
- train/test assessment row 수
- train/test `delirium` 분포
- window 후보별 full-window 제외 row 수
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
