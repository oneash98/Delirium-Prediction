# 모델링 워크플로우

> **노트북**: `src/3_Models.ipynb`
> **입력**: `Data/final_dataset.csv`
> **출력**: `models/optuna/`, `models/quick/`

---

## 전체 흐름

```
final_dataset.csv
    │
    ├─ Section 1-5: Imports, Config, Data Loading, Exploration, Class Weighting
    │
    ├─ Section 6: Data Split (Stratified train/test)
    │
    ├─ Section 7: Outlier Detection & Median Imputation
    │
    ├─ Section 8: Optuna Hyperparameter Tuning
    │       ├─ LR  → best_params_LR.json
    │       ├─ RF  → best_params_RF.json
    │       ├─ XGB → best_params_XGB.json
    │       └─ MLP → best_params_MLP.json
    │
    ├─ Section 9: Helper Functions (compute_metrics, aggregate_cv_metrics)
    │
    ├─ Section 10: K-Fold CV 준비 (folds 리스트 생성)
    │
    ├─ Section 11: Cross Validation with Best Params
    │       └─ Load best_params_*.json → 10-Fold CV 실행
    │
    ├─ Section 12-13: Visualization (ROC/PR curves), Save Results
    │
    ├─ Section 14: Final Model Training (Optuna best params)
    │       └─ 전체 train set 학습 → test set 평가 → 모델 저장
    │
    └─ Section 15: Quick CV (Default Hyperparameters, 5-Fold)
            └─ 동일 구조, default params 사용
```

---

## 상세 단계

### Section 6: Data Split

```python
FEATURE_COLS = [col for col in df.columns if col not in ['stay_id', 'cam_bin', 'CAM-ICU', 'los']]
TARGET_COL = 'CAM-ICU'

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=SEED_VALUE, stratify=y
)
```

- `stay_id`, `cam_bin`, `los`는 feature에서 제외
- Stratified split으로 클래스 비율 유지

---

### Section 7: Outlier Detection & Imputation

- Binary/categorical 컬럼 (0/1 값만 가지는 컬럼) 식별 → outlier 처리 제외
- 연속형 변수: IQR 기반 outlier clipping
- 결측값: `SimpleImputer(strategy='median')`

---

### Section 8: Optuna Hyperparameter Tuning

각 모델별로 Optuna study를 생성하여 AUPRC를 최대화하는 하이퍼파라미터를 탐색.

#### 공통 설정

```python
N_TRIALS = 8
N_JOBS = 4          # MLP는 n_jobs=1 (PyTorch 호환)
OPTUNA_SAVE_DIR = '../models/optuna'
```

#### 모델별 탐색 범위

**Logistic Regression:**
| 파라미터 | 범위 | 스케일 |
|----------|------|--------|
| C | 0.01 ~ 100.0 | log |
| penalty | l1, l2 | categorical |

- 고정: solver=liblinear, class_weight=balanced
- StandardScaler 적용 (needs_scaling=True)

**Random Forest:**
| 파라미터 | 범위 | 스케일 |
|----------|------|--------|
| n_estimators | 100 ~ 500 | int |
| max_depth | 10 ~ 30 | int |
| min_samples_split | 2, 5, 10 | categorical |

- 고정: max_features=8, class_weight=balanced

**XGBoost:**
| 파라미터 | 범위 | 스케일 |
|----------|------|--------|
| learning_rate | 0.01 ~ 0.2 | log |
| max_depth | 3 ~ 9 | int |
| subsample | 0.6 ~ 1.0 | float |

- 고정: n_estimators=300, scale_pos_weight=neg/pos

**MLP (PyTorch):**
| 파라미터 | 범위 | 스케일 |
|----------|------|--------|
| hidden_dim | 128, 256, 512 | categorical |
| dropout | 0.1 ~ 0.5 | float |
| lr | 1e-4 ~ 1e-2 | log |

- 구조: Linear(in→hidden) → ReLU → Dropout → Linear(hidden→hidden/2) → ReLU → Dropout → Linear(hidden/2→1)
- BCEWithLogitsLoss + pos_weight

#### 하이퍼파라미터 저장

각 모델의 Optuna 셀 끝에서 **개별 JSON 파일**로 즉시 저장:

```
models/optuna/
├── best_params_LR.json
├── best_params_RF.json
├── best_params_XGB.json
└── best_params_MLP.json
```

JSON 구조:
```json
{
  "params": {"C": 1.23, "penalty": "l2"},
  "best_value": 0.4567
}
```

모델별로 개별 저장되므로, 특정 모델만 다시 튜닝하고 저장하는 것이 가능.

---

### Section 10-11: Cross Validation with Best Params

#### 파라미터 로드

```python
model_names = ["LR", "RF", "XGB", "MLP"]
for name in model_names:
    path = f"{OPTUNA_SAVE_DIR}/best_params_{name}.json"
    with open(path, "r") as f:
        loaded_params[name] = json.load(f)

best_lr_params = loaded_params["LR"]["params"]
# ...
```

커널 재시작 후 Optuna를 다시 실행하지 않고도, 저장된 params를 로드하여 바로 CV 실행 가능.

#### CV 실행

- 10-Fold Stratified K-Fold
- 각 fold에서 모델 학습 → validation set에서 확률 예측 → metrics 계산
- `aggregate_cv_metrics()`로 fold별 결과 집계 (mean, std, 95% CI)

---

### Section 14: Final Model Training & Test Evaluation

Optuna best params로 **전체 train set**에 최종 학습 후 **test set** 평가.

#### 저장되는 파일

| 파일 | 설명 |
|------|------|
| `lr_model.joblib` | LR 모델 객체 |
| `lr_scaler.joblib` | LR용 StandardScaler |
| `rf_model.joblib` | RF 모델 객체 |
| `xgb_model.joblib` | XGB 모델 객체 |
| `mlp_model.pt` | MLP state_dict + params + in_dim |
| `mlp_scaler.joblib` | MLP용 StandardScaler |
| `*_test_metrics.json` | 모델별 test set 평가 결과 |
| `test_curves.png` | ROC/PR 커브 시각화 |

---

### Section 15: Quick CV (Default Hyperparameters)

Optuna 없이 고정된 default 하이퍼파라미터로 5-Fold CV 및 평가.
`models/quick/` 디렉토리에 동일 구조로 저장.

---

## 평가 지표

| 지표 | 설명 |
|------|------|
| **AUPRC** | Area Under Precision-Recall Curve (Optuna 최적화 대상) |
| AUC-ROC | Area Under ROC Curve |
| PPV | Positive Predictive Value (Precision) |
| NPV | Negative Predictive Value |
| MCC | Matthews Correlation Coefficient |
| Spec@90 | Specificity at 90% Sensitivity |

모든 지표는 fold별로 계산 후 95% CI (Wilson score interval)와 함께 보고.

---

## 주요 설정 요약

```python
SEED_VALUE = 42
N_SPLITS = 10              # K-Fold CV (Optuna best params)
QUICK_N_SPLITS = 5         # Quick CV (default params)
N_TRIALS = 8               # Optuna trials per model
N_JOBS = 4                 # Optuna parallel jobs
DATA_DIR = '../Data'
OPTUNA_SAVE_DIR = '../models/optuna'
QUICK_SAVE_DIR = '../models/quick'
```

---

## 변경 이력

| 날짜 | 변경 내용 |
|------|-----------|
| 2026-02-05 | 초기 작성 (전체 모델링 파이프라인 문서화) |
| 2026-02-05 | Optuna best params 모델별 개별 JSON 저장/로드 구현 |
