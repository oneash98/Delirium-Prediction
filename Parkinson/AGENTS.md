# Parkinson Project Guide

이 문서는 `Parkinson` 하위 작업을 이어받는 에이전트와 연구자가 전체 데이터 파이프라인을 빠르게 이해하기 위한 안내서입니다.

## 목적

MIMIC-IV 기반 Parkinson 코호트에서 ICU 섬망 평가를 outcome으로 사용하기 위해 다음 흐름을 구성합니다.

1. 원천 CSV에서 ICU stay 코호트와 임상 이벤트를 추출합니다.
2. 추출된 long-format 이벤트를 1시간 단위 timeseries로 변환합니다.
3. 섬망 평가 시점마다 직전 8시간 window를 집계해 모델링용 assessment-level 데이터셋을 만듭니다.

## 주요 경로

- `src/1_data_extraction.ipynb`: 원천 MIMIC-IV CSV에서 cohort, chart, lab, medication, procedure 이벤트를 추출합니다.
- `src/2_data_transform.ipynb`: 추출 결과를 숫자화, 단위 통일, 시간 binning, 결측 처리, 8시간 window 집계로 변환합니다.
- `src/extraction_variable_catalog.md`: 추출 대상 변수 catalog 문서입니다.
- `src/extraction_variable_catalog.csv`: 추출 대상 변수 catalog의 CSV 버전입니다.
- `data/`: 원천 CSV 파일 위치입니다. 민감 데이터는 git에 올리지 않습니다.
- `processed/extraction/`: extraction notebook의 산출물 위치입니다.
- `processed/transform/`: transform notebook의 산출물 위치입니다.
- `reports/`: 추출 커버리지와 요약 리포트 위치입니다.
- `docs/1_data_extraction.md`: `1_data_extraction.ipynb` 상세 설명입니다.
- `docs/2_data_transform.md`: `2_data_transform.ipynb` 상세 설명입니다.

## 실행 순서

1. Jupyter 작업 디렉터리를 `Parkinson/src`로 둡니다.
2. `1_data_extraction.ipynb`를 위에서 아래로 실행합니다.
3. `2_data_transform.ipynb`를 위에서 아래로 실행합니다.

노트북은 `PROJECT_DIR = Path.cwd().resolve().parent`를 사용합니다. 따라서 현재 작업 디렉터리가 `Parkinson/src`일 때 `PROJECT_DIR`이 `Parkinson`으로 잡힙니다.

## 데이터 흐름

```text
Parkinson/data/*.csv
  -> src/1_data_extraction.ipynb
  -> processed/extraction/
       adm_pat_icu.csv
       adm_pat_icu_all.csv
       chart_selected.csv
       lab_selected.csv
       medication_events.csv
       procedure_selected.csv
       all_events.csv
  -> src/2_data_transform.ipynb
  -> processed/transform/
       cohort_attrition.csv
       adm_pat_icu_8hrs.csv
       all_events_8hrs.csv
       all_events_filtered.csv
       all_timeseries.csv
       timeseries_imputed.csv
       final_dataset.csv
       assessment_dataset_60min.csv
       hourly_timeseries_60min.csv
```

## 코호트 기준

- ICU stay 단위로 `patients`, `admissions`, `icustays`를 결합합니다.
- 성인 환자만 포함합니다. 기준은 `anchor_age >= 18`입니다.
- ICU 입실/퇴실 시간이 있고 재원시간이 양수인 stay만 유지합니다.
- `1_data_extraction.ipynb`에서는 위 기준을 적용하지 않고 전체 ICU stay 테이블을 저장합니다.
- `2_data_transform.ipynb`에서 성인, 유효한 ICU 시간, 양수 LOS, 8시간 이상 LOS 기준을 순서대로 적용하고 `cohort_attrition.csv`로 저장합니다.

## Outcome 정의

- outcome은 `chartevents`의 `Delirium assessment`입니다.
- transform 단계에서 `Positive`는 `1`, `Negative`는 `0`으로 변환합니다.
- `UTA` 또는 기타 해석 불가능한 평가는 `NaN`으로 남기며 최종 assessment dataset에서는 outcome 시점으로 쓰지 않습니다.
- 시간별 timeseries에서는 섬망 평가가 시행된 bin에만 `Delirium` 값이 있고, 나머지 시간은 `NaN`입니다.

## Feature 범위

- Chart: 섬망 평가, RASS, GCS, 방향감각, 활력징후, 체중/키, 산소치료 및 환기 관련 변수, bedside glucose.
- Lab: 전해질, CBC, 간기능, lactate, ABG, coagulation 관련 변수.
- Medication: Parkinson 약제, benzodiazepine, opioid, sedative/anesthetic, antipsychotic, anticholinergic burden, sleep agent.
- Procedure/device: invasive/non-invasive ventilation, intubation, extubation, EEG.

## 변환 정책 요약

- 시간축은 ICU 입실 후 경과시간 기준 1시간 bin입니다.
- 같은 stay-bin에 여러 이벤트가 있으면 pivot 단계에서 `max`를 사용합니다.
- 단위는 공통 단위로 맞춥니다. 예: Fahrenheit to Celsius, pounds to kg, FiO2 0-1 to percent.
- 변환 rule 적용 후에도 같은 `source_table` + `feature_name` 안에 `valueuom`이 2개 이상이면 unit별 feature로 분리합니다.
- 약물/처치/장치 feature는 binary exposure flag로 만듭니다.
- 약물은 eMAR 투약 시점과 8시간 lookback을 반영합니다.
- 처치/장치는 이벤트 구간과 현재 hour bin이 겹치면 노출로 표시합니다.
- 체중/키는 stay 내 forward-fill과 backward-fill을 적용합니다.
- 활력징후는 최대 4시간까지만 forward-fill합니다.
- Lab은 시간별 보간하지 않고 최종 8시간 window에서 최신값을 사용합니다.

## 최종 데이터셋 단위

`final_dataset.csv`와 `assessment_dataset_60min.csv`는 섬망 평가 1건을 1행으로 하는 assessment-level 데이터셋입니다.

- group key: `stay_id`, `assessment_bin`, `Delirium`
- window: 평가 시점 포함 직전 8개 hourly bins
- demographics: window 내 첫 값
- vitals: 8시간 평균과 표준편차
- medication/procedure/device: window 내 노출 여부 max
- lab/body/neuro: window 내 최신 관측값

## 작업 시 주의사항

- 사용자가 명시적으로 요청하지 않은 기존 주석은 수정하거나 삭제하지 않습니다.
- 코드 수정 시 새 로직 설명에 꼭 필요한 최소 주석만 추가합니다.
- 기존 코드, 노트북 셀 구조, 문서 내용은 요청 범위에 필요한 부분만 최소 변경합니다.
- 원천 MIMIC-IV 데이터와 산출 CSV는 민감 정보가 될 수 있으므로 git에 포함하지 않습니다.
- 기존 notebook의 실행 순서 의존성이 강합니다. 셀을 재배치할 때는 중간 저장 파일과 변수명을 함께 확인합니다.
- extraction 단계의 `adm_pat_icu.csv`와 `adm_pat_icu_all.csv`는 전체 ICU stay 기준입니다. 최종 8시간 이상 코호트 파일은 transform 단계의 `adm_pat_icu_8hrs.csv`입니다.
- notebook JSON을 수정할 때는 저장 후 `json.load`로 파일이 깨지지 않았는지 확인합니다.
- 코드를 바꾼 뒤에는 가능하면 작은 샘플 또는 dry-run으로 산출물 컬럼이 유지되는지 확인합니다.
