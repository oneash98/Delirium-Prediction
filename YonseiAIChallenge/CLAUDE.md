# MIMIC-IV 섬망 예측 프로젝트

## 프로젝트 개요

MIMIC-IV 데이터셋에서 섬망(Delirium) 예측 모델을 위한 데이터를 추출·전처리하고, 머신러닝 모델을 학습·평가하는 파이프라인입니다.

---

## 전체 파이프라인

```
1_mimiciv_extraction.sql     2_Data_transform.ipynb        3_Models.ipynb
─────────────────────────   ─────────────────────────   ──────────────────────────

MIMIC-IV 원본 테이블          all_events.csv               final_dataset.csv
  │                         + adm_pat_icu.csv               │
  ├─ STEP 1: 코호트 정의      │                             ├─ Data Split (train/test)
  ├─ STEP 2: 원본 데이터 추출  ├─ STEP 1: VALUE 변환          ├─ Outlier & Imputation
  ├─ STEP 3: ICU 체류 필터링   ├─ STEP 2: 단위 변환           ├─ Optuna 하이퍼파라미터 튜닝
  ├─ STEP 3.5: 변수 선택      ├─ STEP 3: 라벨 통합           │   (모델별 best_params JSON 저장)
  └─ STEP 4: 통합            ├─ STEP 4: 시간 계산           ├─ K-Fold CV (best params)
       │                     ├─ STEP 5: 60분 비닝           ├─ Final Training & Test
       ▼                     ├─ STEP 6: CAM-ICU 분류        │   (모델 객체 저장)
  all_events.csv             ├─ STEP 7: Imputation          └─ Quick CV (default params)
  adm_pat_icu.csv            └─ STEP 8: 8h 윈도우 집계            │
                                   │                             ▼
                                   ▼                        models/optuna/
                              final_dataset.csv             models/quick/
```

---

## 코호트 정의

- CAM-ICU 평가 기록이 있는 ICU stay
- 18세 이상 성인
- LOS(Length of Stay) 8일 이상

---

## 파일 구조

```
YonseiAIChallenge/
├── CLAUDE.md
├── src/
│   ├── 1_mimiciv_extraction.sql       # 데이터 추출 SQL (AWS Athena)
│   ├── 2_Data_transform.ipynb         # 데이터 변환 노트북
│   └── 3_Models.ipynb                 # 모델링 노트북 (Optuna + CV + 평가)
├── Data/                              # 데이터 파일 (git 미추적)
│   ├── all_events.csv
│   ├── adm_pat_icu.csv
│   ├── all_events_8hrs.csv
│   ├── adm_pat_icu_8hrs.csv
│   ├── all_events_filtered.csv
│   ├── all_timeseries.csv
│   ├── timeseries_imputed.csv
│   └── final_dataset.csv
├── models/                            # 학습된 모델 및 결과 (git 미추적)
│   ├── optuna/                        # Optuna best params 모델
│   │   ├── best_params_LR.json        # 모델별 best 하이퍼파라미터
│   │   ├── best_params_RF.json
│   │   ├── best_params_XGB.json
│   │   ├── best_params_MLP.json
│   │   ├── lr_model.joblib            # 학습된 모델 객체
│   │   ├── rf_model.joblib
│   │   ├── xgb_model.joblib
│   │   ├── mlp_model.pt
│   │   ├── lr_scaler.joblib           # StandardScaler (LR, MLP용)
│   │   ├── mlp_scaler.joblib
│   │   ├── *_test_metrics.json        # 테스트 셋 평가 결과
│   │   └── test_curves.png            # ROC/PR 커브
│   └── quick/                         # Default params 모델
│       └── (동일 구조)
└── docs/
    ├── 1-Data_extraction_MIMIC_workflow.md
    ├── 2-Data_transform_workflow.md
    └── 3-Models_workflow.md
```

---

## 최종 데이터셋 (final_dataset.csv)

각 행 = 하나의 CAM-ICU 평가 시점 (8시간 윈도우 집계)

### 변수 목록

| 구분 | 변수 | 집계 방식 |
|------|------|-----------|
| **식별** | stay_id, cam_bin | - |
| **인구통계** | age, gender, los | 첫 번째 값 |
| **활력징후** | Heart Rate, Mean BP, Oxygen Saturation, Temperature | 8h mean + std |
| **약물** | Propofol, Opiates, Benzodiazepines, Ketamine, Vasopressors | 8h 내 사용 → 1/0 |
| **장비** | Ventilator | 8h 내 사용 → 1/0 |
| **의식** | RASS | 최신값 |
| **신체계측** | Weight | 최신값 |
| **혈액** | WBC, Hemoglobin, Hematocrit, Platelets | 최신값 |
| **전해질** | Sodium, Potassium, Chloride, Bicarbonate, Calcium, Magnesium, Phosphate | 최신값 |
| **신장/간** | BUN, Creatinine, ALT | 최신값 |
| **기타 검사** | Glucose, Lactate, pH, pCO2, pO2 | 최신값 |
| **타겟** | CAM-ICU (0/1) | - |

### 제외된 변수 (결측률 높음)
- Height (98.6%), Ammonia (91.2%), Albumin (19.0%), Bilirubin (12.4%), AST (11.3%)

---

## 모델링 (3_Models.ipynb)

### 모델 종류

| 모델 | 라이브러리 | 특이사항 |
|------|-----------|----------|
| Logistic Regression | sklearn | solver=liblinear, class_weight=balanced, StandardScaler 적용 |
| Random Forest | sklearn | max_features=8, class_weight=balanced |
| XGBoost | xgboost | n_estimators=300, scale_pos_weight 자동 계산 |
| MLP | PyTorch | 3-layer (Linear→ReLU→Dropout), BCEWithLogitsLoss, pos_weight |

### 노트북 구조

| 섹션 | 설명 |
|------|------|
| 1-5 | Imports, Config, Data Loading, Exploration, Class Weighting |
| 6 | Data Split (train_test_split, stratified) |
| 7 | Outlier Detection & Median Imputation |
| 8 | Optuna 하이퍼파라미터 튜닝 (모델별 best_params JSON 개별 저장) |
| 9 | Helper Functions (compute_metrics, aggregate_cv_metrics) |
| 10-11 | K-Fold CV 준비 → Best Params로 Cross Validation |
| 12-13 | Visualization (ROC/PR curves), Save Results |
| 14 | Final Model Training (Optuna) & Test Evaluation |
| 15 | Quick CV (Default Hyperparameters) |

### Optuna 하이퍼파라미터 저장/로드

Optuna 튜닝 후 모델별로 `models/optuna/best_params_{MODEL}.json`에 개별 저장:

```python
# 저장 (각 Optuna 셀 끝에서 자동 실행)
# → models/optuna/best_params_LR.json
# → models/optuna/best_params_RF.json
# → models/optuna/best_params_XGB.json
# → models/optuna/best_params_MLP.json

# 로드 (Cross Validation 섹션 시작 시)
best_lr_params = loaded_params["LR"]["params"]
best_rf_params = loaded_params["RF"]["params"]
# ...
```

JSON 구조: `{"params": {...}, "best_value": float}`

커널 재시작 후 Optuna를 다시 실행하지 않고도, 저장된 params를 로드하여 CV/Training 가능.

### Optuna 탐색 범위

| 모델 | 하이퍼파라미터 | 범위 |
|------|--------------|------|
| LR | C | 0.01 ~ 100 (log) |
| LR | penalty | l1, l2 |
| RF | n_estimators | 100 ~ 500 |
| RF | max_depth | 10 ~ 30 |
| RF | min_samples_split | 2, 5, 10 |
| XGB | learning_rate | 0.01 ~ 0.2 (log) |
| XGB | max_depth | 3 ~ 9 |
| XGB | subsample | 0.6 ~ 1.0 |
| MLP | hidden_dim | 128, 256, 512 |
| MLP | dropout | 0.1 ~ 0.5 |
| MLP | lr | 1e-4 ~ 1e-2 (log) |

### 평가 지표

- **AUPRC** (Optuna 최적화 대상)
- AUC-ROC, PPV, NPV, MCC, Specificity@90% Sensitivity
- 95% CI (Wilson score interval)

### 주요 설정

```python
SEED_VALUE = 42
N_SPLITS = 10          # K-Fold CV
N_TRIALS = 8           # Optuna trials
N_JOBS = 4             # Optuna parallel jobs
DATA_DIR = '../Data'
OPTUNA_SAVE_DIR = '../models/optuna'
QUICK_SAVE_DIR = '../models/quick'
```

---

## 참조 문서

- 데이터 추출 워크플로우: `docs/1-Data_extraction_MIMIC_workflow.md`
- 데이터 변환 워크플로우: `docs/2-Data_transform_workflow.md`
- 모델링 워크플로우: `docs/3-Models_workflow.md`
- 원본 참조: `mostafaalishahi/Delirium_prediction_models/`

---

## AWS Athena 실행 환경

- 소스 DB: `mimiciv`
- 출력 DB: `workdb`

---

## 변경 이력

| 날짜 | 변경 내용 |
|------|-----------|
| 2026-02-02 | 초기 SQL 작성 및 Athena 호환 수정 |
| 2026-02-03 | 변수 선택(STEP 3.5) 추가, 워크플로우 문서 작성 |
| 2026-02-04 | 데이터 변환 노트북 완성 (STEP 1~8), CLAUDE.md 구조 정리 |
| 2026-02-05 | 3_Models.ipynb 모델링 파이프라인 추가, Optuna best params 모델별 개별 저장/로드 구현 |
