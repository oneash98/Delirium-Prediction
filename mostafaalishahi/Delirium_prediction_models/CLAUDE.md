# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Medical machine learning research project for predicting delirium in ICU patients using time-series electronic health records. Implements interpretable deep learning models (Bidirectional LSTM) alongside traditional models (Logistic Regression, Random Forest) on MIMIC-III and eICU databases.

## Running the Pipeline

Execute notebooks in order:

```bash
# 1. Data extraction and preprocessing
jupyter notebook "Data extraction/1-Data_extraction_MIMIC.ipynb"
jupyter notebook "Data extraction/2-Data_preprocessing_MIMIC.ipynb"
jupyter notebook "Data extraction/3-Data_extraction_preprocessing_eICU.ipynb"
jupyter notebook "Data extraction/4-Data_prep_MIMIC_eICU.ipynb"

# 2. Model training and evaluation (refactored version)
jupyter notebook "Model/Model_refactored.ipynb"

# 3. Interpretability analysis
jupyter notebook "Model/Interpertable.ipynb"
```

## Architecture

### Data Pipeline
- **Stage 1 (Notebooks 1-3):** Extract patient records from MIMIC-III/eICU, filter adults 18-89, identify delirium via CAM-ICU scoring (CHARTEVENTS items 228300-228337)
- **Stage 2 (Notebook 4):** Harmonize variable names across databases, unit conversions (lbs→kg, inches→cm), bin data into 60-minute time intervals, generate per-patient time-series CSVs by ICUSTAY_ID

### Models (Model_refactored.ipynb)

**사용 파일**: `Model/Model_refactored.ipynb` (기존 Model.ipynb는 단일 함수에 모든 코드 포함)

#### Data Loading
```python
# pos/neg 파일 분리 로딩 후 합치기
mimic_pos = pd.read_csv("Data/preprocessed/pos_mimic_imputed_24los.csv")
mimic_neg = pd.read_csv("Data/preprocessed/neg_mimic_imputed_24los.csv")
mimic_df = pd.concat([mimic_pos, mimic_neg], axis=0)
```

#### Model Input Columns (COLUMNS_ORD)
```python
['patientunitstayid', 'itemoffset',
 # Categorical (3)
 'Gender', 'Sofa', 'Sofa_wo_gcs',
 # Numerical (18)
 'Age', 'Height', 'Weight', 'Heart Rate', 'O2 Saturation',
 'Glucose', 'Temperature', 'Sodium', 'BUN', 'WBC', 'Hemoglobin',
 'Platelets', 'Potassium', 'Chloride', 'Bicarbonate', 'Creatinine',
 'Ventilation', 'Vasopressor dose',
 # Label
 'labelpt']
```

#### Model Types
- **Logistic Regression:** solver='liblinear', class_weight
- **Random Forest:** n_estimators=300, max_depth=6, max_features=8
- **Bidirectional LSTM:** Embedding(3 cat) + BiLSTM(128) + Dropout(0.2) + Dense(1, sigmoid)

#### Hyperparameters
```python
SEED_VALUE = 36
BATCH_SIZE = 128
PARAMS = {'lr': 0.000075, 'hidden_units': 128, 'dropout': 0.2, 'epochs': 50}

# Experiment parameters
MIN_TIME = 12/24/48      # Observation window (hours)
SKIP_TIME = 12/24/48/72/96  # Prediction horizon (hours)
HIGH_RECALL = False/True
```

#### Notebook Structure
| Section | Description |
|---------|-------------|
| 1-2 | Imports, Configuration, Seed |
| 3-4 | Data Loading (pos/neg 분리 로딩), Exploration |
| 5-6 | Time Window Selection, Data Transformation |
| 7-8 | Padding, Class Weighting |
| 9-10 | Model Definition, Training Functions |
| 11-13 | Metrics, Visualization, CV Pipeline |
| 14-17 | Run Experiments (LR→RF→LSTM), Results |

#### Key Functions
| Function | Purpose |
|----------|---------|
| `pos_selection()` | 섬망 양성 환자 time window 선택 (onset - skip - min ~ onset - skip) |
| `neg_selection()` | 섬망 음성 환자 time window 선택 (last - skip - min ~ last - skip) |
| `reader_deli()` | DataFrame → (PID, X_cat, X_num, timestamps, nrows, y) 변환 |
| `pad_all_sequences()` | Variable-length → Fixed-length padding |
| `build_lstm_model()` | BiLSTM 모델 구축 |
| `train_lstm()` / `train_sklearn()` | 모델별 학습 함수 |
| `compute_metrics()` | AUC, AUPRC, PPV, NPV, MCC, Spec@90 계산 |
| `aggregate_cv_metrics()` | 5-fold 결과 + 95% CI 집계 |
| `run_cross_validation()` | Stratified K-Fold CV 실행 |

#### Output Files
- `.h5`: LSTM 모델 가중치 (TF2 format)
- `.json`: 메트릭 결과 (AUC, CI 등)
- `.png`: ROC/PR 커브 시각화

### Evaluation
- 5-fold Stratified K-Fold Cross-Validation
- Class-weighted sampling for imbalanced datasets
- Parametrized time windows: min_time (12/24/48h observation), skip_time (12/24/48/72/96h prediction horizon)
- Metrics: ROC-AUC with 95% CI, AU-PRC, Specificity@90% Sensitivity, PPV/NPV, MCC

### Interpretability (Interpertable.ipynb)
- Captum library: Integrated Gradients, Shapley Value Sampling, Guided Backprop
- SHAP summary plots for feature importance visualization
- Aggregates attributions across timesteps and folds

## Data Structure (2-Data_preprocessing_MIMIC)

### Column Rename Mapping (Line 206-220)
전처리 중간에 컬럼명이 변경됨. 이후 코드는 **새 컬럼명** 사용 필수.

| Original | Renamed |
|----------|---------|
| `age` | `Age` |
| `admissionheight` | `Height` |
| `admissionweight` | `Weight` |
| `glucose` | `Glucose` |
| `sodium` | `Sodium` |
| `Temperature (C)` | `Temperature` |
| `WBC x 1000` | `WBC` |
| `vent_flag` | `Ventilation` |
| `sofa` | `Sofa` |
| `sofa_wo_gcs` | `Sofa_wo_gcs` |
| `gender` | `Gender` |
| `rate_dopamine/epinephrine/...` | `Vasopressor dose` (합산 후 drop) |

### Data Flow
```
all_data_deli (raw)
    ↓ rename columns (206-220)
    ↓ merge SOFA, vent, vasopressor
new_df
    ↓ merge LOS + filter (LOS>=24, itemoffset>0)
new_df_los_nodups
    ↓ copy
label_deli (labelrec, labelpt 추가)
    ↓ copy
new_df (Imputation 시작, 이미 LOS 포함)
    ↓ ffill/bfill, drop high-missing cols
new_df_los_nodups (최종)
```

### Final Output Columns
```python
['patientunitstayid', 'itemoffset', 'Gender', 'Age', 'Height', 'Weight',
 'Heart Rate', 'O2 Saturation', 'Glucose', 'Temperature', 'Sodium', 'BUN',
 'WBC', 'Hemoglobin', 'Platelets', 'Potassium', 'Chloride', 'Bicarbonate',
 'Creatinine', 'Sofa', 'Sofa_wo_gcs', 'Ventilation', 'Vasopressor dose',
 'LOS', 'CAM', 'labelrec', 'labelpt']
```

### Output Files
- `pos_mimic_notimputed_24los.csv`: 섬망 양성, imputation 전
- `neg_mimic_notimputed_24los.csv`: 섬망 음성, imputation 전
- `pos_mimic_imputed_24los.csv`: 섬망 양성, imputation 후
- `neg_mimic_imputed_24los.csv`: 섬망 음성, imputation 후

## Key Configuration

- **Data paths:**
  - Preprocessing: `mimic_path`, `data_processed_path`
  - Model: `Data/preprocessed/pos_mimic_imputed_24los.csv`, `neg_mimic_imputed_24los.csv`
- **Random seed:** SEED_VALUE=36 throughout
- **GPU (TensorFlow 2.x):** `tf.config.experimental.set_memory_growth(gpu, True)`
