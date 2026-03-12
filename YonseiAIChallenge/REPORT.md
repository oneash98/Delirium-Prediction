# MIMIC-IV 기반 ICU 섬망 예측 모델 연구 보고서

> **프로젝트**: YonseiAI Challenge - Delirium Prediction
> **데이터셋**: MIMIC-IV (Medical Information Mart for Intensive Care)
> **작성일**: 2026-02-05

---

## 목차

1. [연구 개요](#1-연구-개요)
2. [데이터 추출](#2-데이터-추출)
3. [데이터 전처리](#3-데이터-전처리)
4. [탐색적 데이터 분석](#4-탐색적-데이터-분석)
5. [모델링](#5-모델링)
6. [결과](#6-결과)
7. [결론 및 논의](#7-결론-및-논의)

---

## 1. 연구 개요

### 1.1 연구 목적

중환자실(ICU) 환자에서 섬망(Delirium)은 사망률 증가, 재원 기간 연장, 인지 기능 저하와 연관된 중요한 임상 문제입니다. 본 연구는 MIMIC-IV 데이터베이스를 활용하여 **CAM-ICU (Confusion Assessment Method for ICU) 평가 시점을 기준으로 섬망 발생을 예측**하는 머신러닝 모델을 개발하고 평가하는 것을 목적으로 합니다.

### 1.2 연구 설계

- **예측 타겟**: CAM-ICU 양성 여부 (0: 음성, 1: 양성)
- **예측 윈도우**: CAM-ICU 평가 시점 이전 8시간 데이터 기반
- **분석 단위**: 개별 CAM-ICU 평가 시점 (환자당 다수 평가 포함)

### 1.3 전체 파이프라인

```
1_mimiciv_extraction.sql     2_Data_transform.ipynb        3_Models.ipynb
─────────────────────────   ─────────────────────────   ──────────────────────────

MIMIC-IV 원본 테이블          all_events.csv               final_dataset.csv
  │                         + adm_pat_icu.csv               │
  ├─ 코호트 정의              │                             ├─ Data Split
  ├─ 원본 데이터 추출          ├─ VALUE 변환                  ├─ Outlier 처리
  ├─ ICU 체류 필터링           ├─ 단위 변환                   ├─ Optuna 튜닝
  ├─ 변수 선택                ├─ 라벨 통합                   ├─ K-Fold CV
  └─ 통합                    ├─ 시간 계산                   └─ Final Training
       │                     ├─ 60분 비닝                        │
       ▼                     ├─ CAM-ICU 분류                     ▼
  all_events.csv             ├─ Imputation               models/optuna/
  adm_pat_icu.csv            └─ 8h 윈도우 집계             models/quick/
                                   │
                                   ▼
                              final_dataset.csv
```

---

## 2. 데이터 추출

### 2.1 데이터 소스

MIMIC-IV 데이터베이스의 다음 테이블을 사용하였습니다:

| 테이블 | 설명 | 사용 목적 |
|--------|------|----------|
| CHARTEVENTS | 활력징후, 섬망평가, 의식수준 등 | CAM-ICU, RASS, 활력징후 |
| LABEVENTS | 검사실 결과 | 혈액, 전해질, 간/신장 수치 |
| INPUTEVENTS | 약물 투여 기록 | 진정제, 승압제 |
| PATIENTS | 환자 기본 정보 | 연령, 성별 |
| ICUSTAYS | ICU 체류 정보 | 입퇴실 시간, 재원기간 |

### 2.2 코호트 정의

**포함 기준:**
- CAM-ICU 평가 기록이 있는 ICU stay
- 18세 이상 성인
- ICU 재원기간(LOS) 8일 이상

**원본 데이터 규모:**

| 단계 | 데이터 | 규모 |
|------|--------|------|
| 원본 | all_events | **38,276,100**개 이벤트 |
| 원본 | adm_pat_icu | **72,729**개 ICU stay |

### 2.3 추출 변수

#### 활력징후 (CHARTEVENTS)
- Heart Rate, Temperature, Mean BP, Oxygen Saturation
- Richmond-RAS Scale (RASS)
- CAM-ICU 하위 항목 (Inattention, MS Change, RASS LOC, Disorganized thinking)

#### 검사실 결과 (LABEVENTS)
- 혈액: WBC, Hemoglobin, Hematocrit, Platelets
- 전해질: Sodium, Potassium, Chloride, Bicarbonate, Calcium, Magnesium, Phosphate
- 신장/간: BUN, Creatinine, ALT
- 기타: Glucose, Lactate, pH, pCO2, pO2

#### 약물 투여 (INPUTEVENTS)
- 진정제: Propofol, Benzodiazepines (Midazolam, Lorazepam, Diazepam), Ketamine
- 진통제: Opiates (Fentanyl, Morphine)
- 승압제: Vasopressors (Vasopressin, Dobutamine, Phenylephrine)

---

## 3. 데이터 전처리

### 3.1 단위 변환

일관성 있는 분석을 위해 다음 단위 변환을 수행하였습니다:

| 변환 | 공식 | 해당 행 수 |
|------|------|-----------|
| Temperature °F → °C | (F - 32) × 5/9 | 738,677 |
| Weight lbs → kg | lbs × 0.453592 | 19,365 |
| Height inch → cm | inch × 2.54 | 101 |

### 3.2 라벨 통합

동일한 의미를 가진 여러 변수를 단일 라벨로 통합하였습니다:

| 통합 라벨 | 원본 라벨 |
|-----------|-----------|
| RASS | Richmond-RAS Scale, Goal Richmond-RAS Scale |
| Weight | Admission Weight (Kg), Admission Weight (lbs.), Daily Weight |
| Temperature | Temperature Fahrenheit, Temperature Celsius |
| Opiates | Fentanyl, Fentanyl (Concentrate), Morphine Sulfate |
| Benzodiazepines | Midazolam (Versed), Lorazepam (Ativan), Diazepam (Valium) |

### 3.3 시계열 변환

- ICU 입실(intime) 기준 시간(hours) 계산
- 60분 단위 비닝 (bin = floor(hours))
- Wide format 피봇 테이블 생성

**시계열 데이터 규모:**

| 단계 | 행 수 | ICU stay 수 |
|------|-------|-------------|
| LOS ≥ 8일 필터링 후 | 17,400,216 | 7,661 |
| 시계열 피봇 후 | **2,868,290** | **7,661** |

### 3.4 CAM-ICU 분류

CAM-ICU 양성 판정 기준:
```
CAM-ICU Positive = (Feature1 AND Feature2) AND (Feature3 OR Feature4)

Feature1: CAM-ICU MS Change == 1        (의식 변화)
Feature2: CAM-ICU Inattention == 1 or 4 (주의력 장애)
Feature3: CAM-ICU RASS LOC == 1         (의식 수준 변화)
Feature4: CAM-ICU Disorganized thinking == 1 (비조직적 사고)
```

**CAM-ICU 평가 현황:**

| 구분 | 개수 |
|------|------|
| 전체 시계열 레코드 | 2,868,290 |
| CAM-ICU 평가 시점 | 200,909 |
| - 양성 (Positive) | 6,767 (3.37%) |
| - 음성 (Negative) | 194,142 (96.63%) |
| 미평가 시점 (NaN) | 2,667,381 |

**환자 수준 분포:**
- 섬망 경험 환자 (ever delirious): 2,471명
- 섬망 비경험 환자 (never delirious): 5,185명

### 3.5 결측치 처리 (Imputation)

| 단계 | 대상 변수 | 처리 방법 |
|------|----------|-----------|
| 1 | 약물/장비 | NaN → 0 (미기록 = 미사용) |
| 2 | Weight, Height | 환자별 forward-fill + backward-fill |
| 3 | 임상 측정값 | 환자별 forward-fill |
| 4 | 임상 측정값 | 환자별 backward-fill (초기 시간대) |

### 3.6 8시간 윈도우 집계

CAM-ICU 평가 시점(cam_bin)으로부터 이전 8시간(cam_bin-7 ~ cam_bin) 데이터를 하나의 행으로 집계하였습니다.

**필터링:** `cam_bin >= 7` (입실 후 8시간 미만 평가 제외)

**집계 규칙:**

| 구분 | 변수 | 집계 방법 |
|------|------|-----------|
| 활력징후 | Heart Rate, Mean BP, Oxygen Saturation, Temperature | 8h mean + std |
| 약물/장비 | Propofol, Opiates, Benzodiazepines 등 | 8h 내 사용 여부 → 1/0 |
| 검사/의식 | Weight, RASS, Lab 결과 | 최신 시점 값 |

**제외된 변수 (결측률 높음):**

| 변수 | 결측률 | 제외 사유 |
|------|--------|----------|
| Height | 98.6% | 대부분 미측정 |
| Ammonia | 91.2% | 대부분 미측정 |
| Albumin | 19.0% | 높은 결측률 |
| Bilirubin | 12.4% | 높은 결측률 |
| AST | 11.3% | 높은 결측률 |

---

## 4. 탐색적 데이터 분석

### 4.1 최종 데이터셋 규모

| 항목 | 값 |
|------|-----|
| **총 샘플 수 (CAM-ICU 평가)** | **195,440** |
| **고유 ICU stay 수** | **7,644** |
| **특성(Feature) 수** | **37** |

### 4.2 타겟 변수 분포

#### 샘플 수준 (Sample-level)

| 클래스 | 개수 | 비율 |
|--------|------|------|
| CAM-ICU 음성 (0) | 188,739 | 96.57% |
| CAM-ICU 양성 (1) | 6,701 | **3.43%** |

#### 환자 수준 (Patient-level)

| 클래스 | 환자 수 | 비율 |
|--------|---------|------|
| 섬망 비경험 (Never) | 5,207 | 68.12% |
| 섬망 경험 (Ever) | 2,437 | **31.88%** |

### 4.3 클래스 불균형 처리

심각한 클래스 불균형(양성률 3.43%)에 대응하기 위해:
- sklearn: `class_weight='balanced'` 적용
- XGBoost: `scale_pos_weight = neg_count / pos_count` 적용
- PyTorch MLP: `BCEWithLogitsLoss` + `pos_weight` 적용

**계산된 클래스 가중치:**
- Class 0 (음성): 0.5178
- Class 1 (양성): 14.5829
- 가중치 비율: **28.2x**

### 4.4 최종 변수 목록 (37개)

| 구분 | 변수명 | 개수 |
|------|--------|------|
| 인구통계 | age, gender | 2 |
| 활력징후 (mean) | Heart Rate, Mean BP, Oxygen Saturation, Temperature | 4 |
| 활력징후 (std) | Heart Rate_std, Mean BP_std, Oxygen Saturation_std, Temperature_std | 4 |
| 약물 | Propofol, Opiates, Benzodiazepines, Ketamine, Vasopressors | 5 |
| 장비 | Ventilator | 1 |
| 의식 | RASS | 1 |
| 신체계측 | Weight | 1 |
| 혈액 | WBC, Hemoglobin, Hematocrit, Platelets | 4 |
| 전해질 | Sodium, Potassium, Chloride, Bicarbonate, Calcium, Magnesium, Phosphate | 7 |
| 신장/간 | BUN, Creatinine, ALT | 3 |
| 기타 검사 | Glucose, Lactate, pH, pCO2, pO2 | 5 |

---

## 5. 모델링

### 5.1 데이터 분할

| 세트 | 샘플 수 | 양성 수 | 양성률 |
|------|---------|---------|--------|
| **Train** | **156,352** | 5,361 | 3.43% |
| **Test** | **39,088** | 1,340 | 3.43% |

- Stratified split (층화 추출)으로 클래스 비율 유지
- test_size = 0.2
- random_state = 42

### 5.2 전처리 파이프라인

1. **이상치 처리**: IQR 기반 clipping (연속형 변수)
2. **결측치 처리**: Train set 기준 median imputation

### 5.3 모델 구성

| 모델 | 라이브러리 | 특이사항 |
|------|-----------|----------|
| **Logistic Regression (LR)** | sklearn | solver=liblinear, class_weight=balanced, StandardScaler |
| **Random Forest (RF)** | sklearn | max_features=8, class_weight=balanced |
| **XGBoost (XGB)** | xgboost | n_estimators=300, scale_pos_weight |
| **MLP** | PyTorch | 3-layer, BCEWithLogitsLoss + pos_weight |

### 5.4 Optuna 하이퍼파라미터 튜닝

**설정:**
- 최적화 목표: AUPRC 최대화
- Trial 수: 8
- Cross-validation: 5-Fold

**탐색 범위 및 최적 파라미터:**

| 모델 | 파라미터 | 탐색 범위 | 최적값 |
|------|----------|-----------|--------|
| **LR** | C | 0.01 ~ 100 (log) | 63.54 |
| | penalty | l1, l2 | l1 |
| **RF** | n_estimators | 100 ~ 500 | 447 |
| | max_depth | 10 ~ 30 | 25 |
| | min_samples_split | 2, 5, 10 | 2 |
| **XGB** | learning_rate | 0.01 ~ 0.2 (log) | 0.079 |
| | max_depth | 3 ~ 9 | 8 |
| | subsample | 0.6 ~ 1.0 | 0.773 |
| **MLP** | hidden_dim | 128, 256, 512 | 128 |
| | dropout | 0.1 ~ 0.5 | 0.443 |
| | lr | 1e-4 ~ 1e-2 (log) | 0.00258 |

**Optuna 튜닝 결과 (AUPRC):**

| 모델 | Best AUPRC |
|------|------------|
| XGB | **0.5072** |
| RF | 0.4334 |
| MLP | 0.1703 |
| LR | 0.1064 |

### 5.5 교차 검증

**설정:**
- 5-Fold Stratified K-Fold
- Best params 사용

**Fold별 샘플 분포:**

| Fold | Train 샘플 | 양성 수 | Val 샘플 | 양성 수 |
|------|-----------|---------|---------|---------|
| 1 | 125,081 | 4,289 | 31,271 | 1,072 |
| 2 | 125,081 | 4,288 | 31,271 | 1,073 |
| 3 | 125,082 | 4,289 | 31,270 | 1,072 |
| 4 | 125,082 | 4,289 | 31,270 | 1,072 |
| 5 | 125,082 | 4,289 | 31,270 | 1,072 |

---

## 6. 결과

### 6.1 교차 검증 결과 (5-Fold, Best Params)

| 모델 | AUC-ROC (95% CI) | AUPRC (95% CI) | PPV | NPV | MCC |
|------|------------------|----------------|-----|-----|-----|
| **XGB** | **0.9602 (0.9582-0.9622)** | **0.5072 (0.4888-0.5256)** | 0.4058 | 0.9906 | 0.5283 |
| RF | 0.9548 (0.9507-0.9588) | 0.4334 (0.4042-0.4626) | 0.3597 | 0.9921 | 0.5093 |
| MLP | 0.8631 (0.8607-0.8655) | 0.1769 (0.1670-0.1868) | 0.0987 | 0.9936 | 0.2330 |
| LR | 0.8052 (0.8017-0.8088) | 0.1064 (0.1026-0.1103) | 0.0752 | 0.9918 | 0.1794 |

### 6.2 Test Set 최종 결과 (Optuna Best Params)

| 모델 | AUC-ROC | AUPRC | PPV | NPV | MCC | Spec@90 |
|------|---------|-------|-----|-----|-----|---------|
| **XGB** | **0.9593** | **0.5045** | 0.3960 | 0.9913 | 0.5285 | **0.9317** |
| RF | 0.9538 | 0.4294 | 0.3571 | 0.9922 | 0.5086 | 0.9305 |
| MLP | 0.8632 | 0.1801 | 0.1015 | 0.9929 | 0.2349 | 0.6832 |
| LR | 0.8072 | 0.1102 | 0.0748 | 0.9915 | 0.1774 | 0.5378 |

> **Spec@90**: 90% Sensitivity에서의 Specificity

### 6.3 Quick CV 결과 (Default Params, 비교용)

| 모델 | AUC-ROC (95% CI) | AUPRC (95% CI) |
|------|------------------|----------------|
| XGB | 0.9592 (0.9569-0.9615) | 0.4794 (0.4590-0.4998) |
| RF | 0.9531 (0.9493-0.9569) | 0.4180 (0.3866-0.4494) |
| LR | 0.8049 (0.8013-0.8085) | 0.1063 (0.1025-0.1101) |

→ Optuna 튜닝으로 XGB AUPRC **5.2%p 향상** (0.4794 → 0.5045)

### 6.4 성능 해석

#### Baseline 대비 성능
- 단순 양성률 기반 baseline AUPRC: **0.0343** (3.43%)
- XGB AUPRC: **0.5045** → baseline 대비 **14.7배** 향상

#### 클래스 불균형 하에서의 해석
- **높은 NPV (>99%)**: 음성 예측의 높은 신뢰도 (실제 음성을 잘 맞춤)
- **중간 PPV (~40%)**: 양성 예측 시 약 40%가 실제 양성
- **높은 Spec@90 (93%)**: 90% sensitivity 유지하면서 93% specificity 달성

---

## 7. 결론 및 논의

### 7.1 주요 발견

1. **XGBoost가 최고 성능** 달성
   - AUC-ROC 0.96, AUPRC 0.50으로 섬망 예측에 효과적
   - 3.43%의 극심한 클래스 불균형에서도 우수한 성능

2. **Tree 기반 모델의 우수성**
   - RF, XGB가 LR, MLP보다 현저히 높은 성능
   - 비선형 관계 및 변수 간 상호작용 포착에 유리

3. **딥러닝(MLP)의 제한적 성능**
   - 표 형식 데이터에서 MLP는 tree 기반 모델 대비 열위
   - 충분한 데이터에도 불구하고 AUPRC 0.18로 제한적

### 7.2 임상적 의의

- **스크리닝 도구로서의 활용**: 높은 NPV로 음성 예측 신뢰 가능
- **고위험군 식별**: PPV 40%로 양성 예측 환자 집중 관리 가능
- **8시간 윈도우 기반 예측**: 실시간 모니터링 시스템 적용 가능

### 7.3 한계점

1. **단일 기관 데이터**: MIMIC-IV (Beth Israel Deaconess Medical Center)로 일반화 제한
2. **후향적 연구**: 전향적 검증 필요
3. **CAM-ICU 의존**: 평가 누락 시점 예측 불가
4. **시간 의존성 미고려**: 순차적 패턴 미반영 (LSTM 등 미적용)

### 7.4 향후 연구 방향

- 외부 검증 (eICU, 국내 데이터)
- 시계열 모델 적용 (LSTM, Transformer)
- 설명 가능성 분석 (SHAP, Feature Importance)
- 전향적 임상 검증

---

## 부록

### A. 파일 구조

```
YonseiAIChallenge/
├── src/
│   ├── 1_mimiciv_extraction.sql    # 데이터 추출 SQL
│   ├── 2_Data_transform.ipynb      # 데이터 전처리
│   └── 3_Models.ipynb              # 모델링
├── Data/
│   ├── all_events.csv              # 원본 이벤트 (38.3M rows)
│   ├── adm_pat_icu.csv             # ICU 체류 정보 (72.7K stays)
│   ├── all_timeseries.csv          # 시계열 (2.9M rows)
│   ├── timeseries_imputed.csv      # Imputation 완료
│   └── final_dataset.csv           # 최종 (195.4K rows)
├── models/
│   ├── optuna/                     # Optuna 튜닝 모델
│   └── quick/                      # Default 모델
└── docs/
    ├── 1-Data_extraction_MIMIC_workflow.md
    ├── 2-Data_transform_workflow.md
    └── 3-Models_workflow.md
```

### B. 주요 설정값

```python
SEED_VALUE = 42
N_SPLITS = 5              # K-Fold CV
N_TRIALS = 8              # Optuna trials
N_JOBS = 4                # Parallel jobs
TEST_SIZE = 0.2           # Train/Test split
DATA_DIR = '../Data'
OPTUNA_SAVE_DIR = '../models/optuna'
```

### C. 데이터 흐름 요약

| 단계 | 파일 | 행 수 | ICU stay 수 |
|------|------|-------|-------------|
| 원본 추출 | all_events.csv | 38,276,100 | 72,729 |
| LOS 필터링 | - | 17,400,216 | 7,661 |
| 시계열 피봇 | all_timeseries.csv | 2,868,290 | 7,661 |
| Imputation | timeseries_imputed.csv | 2,868,290 | 7,661 |
| 8h 윈도우 집계 | **final_dataset.csv** | **195,440** | **7,644** |

---

*Generated with Claude Code*
