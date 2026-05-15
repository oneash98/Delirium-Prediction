# 4_modeling 계획

이 문서는 `4_modeling.ipynb`에서 수행할 모델링 단계 작업 계획입니다. `3_eda.ipynb`는 별도 EDA 노트북입니다.

Transform 단계는 12시간 라벨이 붙은 long-format event, charttime 기준 wide table, 12시간 bin-level wide table, assessment index를 만듭니다. 모델링 단계에서는 subject-level train/test split을 생성한 뒤 observation window feature를 만들고, train 기준으로 feature selection과 imputation을 수행합니다.

## 입력 파일

`processed/transform/`:

- `events_12h_wide_by_charttime.csv`: cohort criteria를 통과한 charttime 기준 wide table. 같은 12시간 bin 안의 여러 charttime은 집계하지 않습니다.
- `events_12h_binned.csv`: cohort criteria를 통과한 12시간 bin-level wide table. `extraction_variable_catalog.csv`의 `binning` 규칙으로 생성된 집계/최신값/노출/static feature를 포함합니다.
- `events_12h_long.csv`: cohort criteria를 통과한 12시간 라벨 long-format event table. `ever_delirium` 포함.
- `assessment_index_12h.csv`: assessment-level index. `subject_id`, `hadm_id`, `stay_id`, `charttime`, `assessment_bin`, `assessment_hours`, `delirium`, `ever_delirium` 포함.
- `cohort_final.csv`: cohort criteria를 통과한 stay-level cohort table.

`split` 컬럼과 `train_subject_ids.csv`, `test_subject_ids.csv`는 이 노트북의 `## 환자 단위 무작위 train/test 분할`, `## Split 산출물 저장` 이후 생성됩니다.

## 환자 단위 무작위 train/test 분할

현재 `4_modeling.ipynb`에 구현된 첫 번째 섹션입니다. Subject 단위로 80/20 random split을 수행하고, 같은 subject의 모든 stay와 assessment가 같은 split에 속하는지 확인합니다.

- `ever_delirium`은 EDA와 split 확인용 subject-level label이며, 기본 모델 target으로 쓰지 않습니다.
- Train/test split은 `4_modeling.ipynb`에서 subject-level로 생성하고 이후 모델링 단계에서 그대로 사용합니다.

## Split 산출물 저장

현재 `4_modeling.ipynb`에 구현된 두 번째 섹션입니다.

- `events_12h_wide_by_charttime.csv`에 `split` 컬럼을 저장합니다.
- `events_12h_long.csv`에 `split` 컬럼을 저장합니다.
- `assessment_index_12h.csv`에 `split` 컬럼을 저장합니다.
- `cohort_final.csv`에 `split` 컬럼을 저장합니다.
- `train_subject_ids.csv`, `test_subject_ids.csv`를 저장합니다.

## 모델링 핵심 원칙

- Assessment-level outcome은 `delirium`입니다.
- 기본 모델 구조는 12시간 bin을 time step으로 사용하는 LSTM입니다.
- 입력은 연속된 4개 time step의 feature입니다.
- 예측 대상은 입력의 4번째 time step과 그 다음 2개 time step의 delirium 여부입니다.
- 72시간 ICU LOS 기준은 최소 6개 12시간 time step, 즉 4개 입력 step과 2개 추가 예측 step을 확보하기 위한 기준입니다.
- Window 길이, feature 제외 기준, imputation 값은 train set에서만 결정합니다.
- Test set은 train에서 정한 window, feature 목록, imputation 값을 그대로 적용받습니다.

## LSTM Time Step 구성

12시간 bin-level table인 `events_12h_binned.csv`를 기본 입력 feature source로 사용합니다.

한 training example은 연속된 6개 12시간 time step을 기준으로 구성합니다.

- Input: `t-3`, `t-2`, `t-1`, `t`의 4개 time step feature
- Target: `t`, `t+1`, `t+2`의 delirium 여부
- 각 time step은 12시간 bin입니다.

Transform 단계의 candidate window count는 첫 48시간과 퇴실 직전 마지막 12시간을 제외한 12시간 bin 수를 기록합니다. 첫 48시간은 4개 input step 확보를 위한 warm-up 구간이고, 마지막 12시간은 퇴실 직전 partial/near-discharge 영향을 줄이기 위해 제외합니다.

기본안:

- 4개 input step과 2개 future target step을 구성할 수 없는 example은 제외합니다.
- 제외 수를 train/test별로 출력합니다.

## Feature 생성

Feature 생성은 `events_12h_binned.csv`를 기본으로 수행합니다. 필요 시 charttime-level 검토에는 `events_12h_wide_by_charttime.csv`와 long-format event를 보조적으로 사용합니다.

`events_12h_binned.csv`에는 `prev_delirium`이 포함됩니다. 이는 같은 stay의 직전 12시간 bin에서의 delirium 결과이며, 첫 time step은 입원 전 직전 결과가 없으므로 `0`입니다.

식별/metadata:

- `subject_id`
- `stay_id`
- `charttime`
- `assessment_bin`
- `assessment_hours`
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

Transform wide table의 `delirium`은 12시간 `stay_id`/`bin` 단위 label입니다. 해당 bin 안 assessment 중 하나라도 positive면 `1`, assessment는 있지만 positive가 없으면 `0`, assessment 자체가 없으면 `NaN`입니다. 실제 assessment charttime의 원래 row는 long-format event와 `assessment_index_12h.csv`에서 확인합니다.

Medication feature는 transform 단계에서 실제 투약 event가 기록된 charttime row만 `1`입니다. 모델링 단계에서는 candidate observation window 안에 해당 medication feature가 한 번이라도 `1`이면 window-level exposure `1`로 집계합니다.

Procedure/device feature는 transform 단계에서 charttime row의 `charttime`이 procedure interval 안에 들어오면 `1`입니다. 모델링 단계에서는 medication과 동일하게 window 안 max 값으로 window-level exposure를 만듭니다.

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
