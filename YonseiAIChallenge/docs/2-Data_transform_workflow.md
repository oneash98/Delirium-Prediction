# 데이터 변환 워크플로우

> **노트북**: `src/2_Data_transform.ipynb`
> **입력**: `all_events.csv`, `adm_pat_icu.csv`
> **출력**: `final_dataset.csv`

---

## 전체 흐름

```
all_events.csv ─────────────────────────────────────────────────────┐
adm_pat_icu.csv ───┐                                               │
                   │                                               │
    STEP 0: LOS ≥ 8일 필터링                                       │
                   │                                               │
    STEP 1: VALUE 변환 (문자열 → 숫자)                               │
    STEP 2: 단위 변환 (°F→°C, lbs→kg, inch→cm)                      │
    STEP 3: 라벨 통합 (동일 의미 변수 합치기)                          │
                   │                                               │
                   ▼                                               │
           all_events_filtered.csv                                 │
                   │                                               │
    STEP 4: 시간 계산 (ICU 입실 기준 hours, 입실 이후만)               │
    STEP 5: 60분 비닝 + 피봇 → Wide format timeseries                │
    STEP 6: CAM-ICU 양성/음성 분류                                   │
                   │                                               │
                   ▼                                               │
           all_timeseries.csv                                      │
                   │                                               │
    STEP 7: Imputation (zero-fill, ffill, bfill)                   │
                   │                                               │
                   ▼                                               │
           timeseries_imputed.csv                                  │
                   │                                               │
    STEP 8: CAM-ICU 평가 시점 기준 8시간 윈도우 집계                    │
           → 결측률 높은 변수 제외                                     │
                   │                                               │
                   ▼                                               │
           final_dataset.csv                                       │
```

---

## 상세 단계

### STEP 0: LOS 필터링

- `adm_pat_icu`에서 LOS(Length of Stay) 8일 미만 제거
- `all_events`에서 해당 stay_id만 유지
- 출력: `all_events_8hrs.csv`, `adm_pat_icu_8hrs.csv`

---

### STEP 1: VALUE 변환 (문자열 → 숫자)

문자열 값을 숫자로 매핑:

| value_str | value_num |
|-----------|-----------|
| `"+2 Frequent nonpurposeful movement` | 2 |
| `"+1 Anxious` | 1 |
| `"-2 Light sedation` | -2 |
| `"-3 Moderate sedation` | -3 |
| `"-4 Deep sedation` | -4 |
| `"-5 Unarousable` | -5 |
| `"+4 Combative` | 4 |
| `No` / `No (less than 3 errors...)` | 0 |
| `Yes` / `"Yes (3 or more errors` | 1 |
| `<0.1` | 0 |
| Ventilator Type (존재 시) | 1 |

- `Bilirubin` 라벨 제거 (데이터 이슈)
- `value_num` → `value`로 컬럼명 변경

---

### STEP 2: 단위 변환

| 변환 | 공식 |
|------|------|
| Temperature °F → °C | `(F - 32) × 5/9` |
| Weight lbs → kg | `lbs × 0.453592` |
| Height inch → cm | `inch × 2.54` |

---

### STEP 3: 라벨 통합

동일 의미의 여러 원본 라벨을 하나의 통합 라벨로 매핑:

| 통합 라벨 | 원본 라벨 |
|-----------|-----------|
| RASS | Richmond-RAS Scale, Goal Richmond-RAS Scale |
| Weight | Admission Weight (Kg), Admission Weight (lbs.), Daily Weight |
| Height | Height (cm), Height |
| Heart Rate | Heart Rate, Heart rate |
| Temperature | Temperature Fahrenheit, Temperature Celsius |
| Oxygen Saturation | O2 saturation pulseoxymetry, Arterial O2 Saturation |
| Mean BP | Arterial Blood Pressure mean, Non Invasive Blood Pressure mean |
| Glucose | Glucose, Glucose (serum), Glucose finger stick, Glucose (whole blood) |
| Opiates | Fentanyl, Fentanyl (Concentrate), Morphine Sulfate |
| Benzodiazepines | Midazolam (Versed), Lorazepam (Ativan), Diazepam (Valium) |
| Vasopressors | Vasopressin, Dobutamine, Phenylephrine (50/250), Phenylephrine (200/250) |

- NULL 값 제거 후 저장: `all_events_filtered.csv`

---

### STEP 4: 시간 계산

- `adm_pat_icu`와 조인하여 환자 정보(age, gender, los) 추가
- `hours = (charttime - intime)` (시간 단위)
- ICU 입실 이후 데이터만 유지 (`hours >= 0`)
- 60분 비닝: `bin = floor(hours)`

---

### STEP 5: 60분 비닝 + 피봇

- `(stay_id, bin)` 단위로 각 라벨의 MAX 값을 피봇
- 결과: Wide format timeseries (각 행 = 1 stay × 1시간)
- 피봇 대상: 40개 변수 (활력징후, 검사값, 약물, CAM-ICU 하위항목 등)

---

### STEP 6: CAM-ICU 양성/음성 분류

**양성 판정 기준:**
```
CAM-ICU Positive = (Feature1 AND Feature2) AND (Feature3 OR Feature4)

Feature1: CAM-ICU MS Change == 1        (의식 변화)
Feature2: CAM-ICU Inattention == 1 or 4 (주의력 장애)
Feature3: CAM-ICU RASS LOC == 1         (의식 수준 변화)
Feature4: CAM-ICU Disorganized thinking == 1 (비조직적 사고)
```

- 평가 수행 시점: `CAM-ICU = 0` (음성) 또는 `1` (양성)
- 미평가 시점: `CAM-ICU = NaN`
- 하위 항목 4개 컬럼 제거 후 저장: `all_timeseries.csv`

---

### STEP 7: Imputation

| 단계 | 대상 | 방법 |
|------|------|------|
| 7-1 | 약물/장비 (Propofol, Opiates, Benzodiazepines, Ketamine, Vasopressors, Ventilator) | `NaN → 0` (미기록 = 미사용) |
| 7-2 | 신체계측 (Weight, Height) | 환자별 ffill + bfill |
| 7-3 | 임상 측정값 (활력징후, 검사값 28개) | 환자별 forward-fill |
| 7-4 | 임상 측정값 (동일) | 환자별 backward-fill (초기 시간대 보간) |
| 7-5 | - | 결측률 확인 |

- 저장: `timeseries_imputed.csv`

---

### STEP 8: 8시간 윈도우 집계

CAM-ICU 평가 시점으로부터 이전 8시간(`cam_bin-7 ~ cam_bin`) 데이터를 하나의 row로 집계.

**필터링:**
- `cam_bin >= 7` (입실 후 8시간 미만 평가 제외, 윈도우 불완전)

**집계 규칙:**

| 구분 | 변수 | 방법 |
|------|------|------|
| 활력징후 | Heart Rate, Mean BP, Oxygen Saturation, Temperature | 8h mean + std |
| 약물/장비 | Propofol, Opiates, Benzodiazepines, Ketamine, Vasopressors, Ventilator | 8h 내 사용 이력 → 1/0 |
| 신체계측 + 검사결과 | Weight, RASS, 혈액/전해질/신장간/기타 검사 | 최신 시점 값 |

**결측률 높은 변수 제외:**

| 변수 | 결측률 | 사유 |
|------|--------|------|
| Height | 98.6% | 대부분 미측정 |
| Ammonia | 91.2% | 대부분 미측정 |
| Albumin | 19.0% | 높은 결측률 |
| Bilirubin | 12.4% | 높은 결측률 |
| AST | 11.3% | 높은 결측률 |

- 저장: `final_dataset.csv`

---

## 최종 데이터셋 스키마

| 컬럼 | 타입 | 설명 |
|------|------|------|
| stay_id | int | ICU 체류 ID |
| cam_bin | int | CAM-ICU 평가 시점 (bin) |
| CAM-ICU | 0/1 | **타겟** (양성=1, 음성=0) |
| age | int | 나이 |
| gender | int | 성별 |
| los | float | ICU 체류 기간 (일) |
| Heart Rate_mean | float | 8h 평균 심박수 |
| Heart Rate_std | float | 8h 심박수 표준편차 |
| Mean BP_mean | float | 8h 평균 혈압 |
| Mean BP_std | float | 8h 혈압 표준편차 |
| Oxygen Saturation_mean | float | 8h 평균 산소포화도 |
| Oxygen Saturation_std | float | 8h 산소포화도 표준편차 |
| Temperature_mean | float | 8h 평균 체온 (°C) |
| Temperature_std | float | 8h 체온 표준편차 |
| Propofol | 0/1 | 8h 사용 여부 |
| Opiates | 0/1 | 8h 사용 여부 |
| Benzodiazepines | 0/1 | 8h 사용 여부 |
| Ketamine | 0/1 | 8h 사용 여부 |
| Vasopressors | 0/1 | 8h 사용 여부 |
| Ventilator | 0/1 | 8h 사용 여부 |
| Weight | float | 최신 체중 (kg) |
| RASS | float | 최신 RASS 점수 |
| WBC | float | 최신 백혈구 수 |
| Hemoglobin | float | 최신 헤모글로빈 |
| Hematocrit | float | 최신 헤마토크릿 |
| Platelets | float | 최신 혈소판 수 |
| Sodium | float | 최신 나트륨 |
| Potassium | float | 최신 칼륨 |
| Chloride | float | 최신 염소 |
| Bicarbonate | float | 최신 중탄산염 |
| Calcium | float | 최신 칼슘 |
| Magnesium | float | 최신 마그네슘 |
| Phosphate | float | 최신 인산염 |
| BUN | float | 최신 혈중요소질소 |
| Creatinine | float | 최신 크레아티닌 |
| ALT | float | 최신 ALT |
| Glucose | float | 최신 혈당 |
| Lactate | float | 최신 젖산 |
| pH | float | 최신 pH |
| pCO2 | float | 최신 이산화탄소분압 |
| pO2 | float | 최신 산소분압 |

---

## 다음 단계

`final_dataset.csv`를 입력으로 `src/3_Models.ipynb`에서 모델링 수행:
- 상세: `docs/3-Models_workflow.md`

---

## 변경 이력

| 날짜 | 변경 내용 |
|------|-----------|
| 2026-02-04 | 초기 작성 (STEP 1~8 전체 워크플로우) |
| 2026-02-05 | 다음 단계(모델링) 링크 추가 |
