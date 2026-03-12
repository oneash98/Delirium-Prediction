# MIMIC-IV 데이터 추출 워크플로우

> **버전**: v4 (2026-02-03 업데이트)
> **SQL 파일**: `src/1_mimiciv_extraction.sql`

---

## 1. 개요

MIMIC-IV 데이터셋에서 섬망(Delirium) 예측 모델을 위한 데이터를 추출하는 SQL 파이프라인입니다.

### 사용 테이블
| 테이블 | 설명 |
|--------|------|
| CHARTEVENTS | 활력징후, 섬망평가(CAM-ICU), RASS 등 |
| LABEVENTS | 검사 결과 (전해질, 혈액검사 등) |
| INPUTEVENTS | 약물 투여 (진정제, 승압제 등) |

### 제외된 테이블
- ~~PRESCRIPTIONS~~: 처방 데이터 (사용 안함)
- ~~DATETIMEEVENTS~~: 환자 response (제외됨)

---

## 2. 파이프라인 구조

```
STEP 1: 코호트 정의
    ├── icustay_delirium (CAM-ICU 기록이 있는 stay_id)
    └── adm_pat_icu (환자 기본 정보, 18세 이상)

STEP 2: 원본 데이터 추출
    ├── chart_data (CHARTEVENTS)
    ├── lab_data (LABEVENTS)
    └── input_data (INPUTEVENTS)

STEP 3: ICU 체류 기간 필터링
    ├── chart_filtered
    ├── lab_filtered
    └── input_filtered

STEP 3.5: 변수 선택
    ├── chart_selected
    ├── lab_selected
    └── input_selected

STEP 4: 통합 테이블
    └── all_events
```

---

## 3. 상세 단계

### STEP 1: 코호트 정의

#### 1-1. 섬망 코호트 (CAM-ICU 기록 있는 ICU stay)
```sql
CREATE TABLE workdb.icustay_delirium AS
SELECT DISTINCT stay_id
FROM mimiciv.chartevents
WHERE itemid IN (229324, 229326, 228302, 228303, 228300,
                 228335, 228336, 228337, 229325, 228301, 228334);
```

#### 1-2. 환자-ICU 기본 정보
```sql
CREATE TABLE workdb.adm_pat_icu AS
SELECT
    p.subject_id, a.hadm_id, i.stay_id,
    p.gender, p.anchor_age AS age, i.los, a.admission_type,
    TRY_CAST(i.intime AS TIMESTAMP) AS intime,
    TRY_CAST(i.outtime AS TIMESTAMP) AS outtime
FROM mimiciv.icustays i
INNER JOIN mimiciv.patients p ON i.subject_id = p.subject_id
INNER JOIN mimiciv.admissions a ON i.hadm_id = a.hadm_id
INNER JOIN workdb.icustay_delirium id ON i.stay_id = id.stay_id
WHERE p.anchor_age >= 18
      AND i.intime IS NOT NULL
      AND i.outtime IS NOT NULL;
```

**필터링 조건:**
- 18세 이상 성인
- CAM-ICU 평가 기록이 있는 ICU stay

---

### STEP 2: 원본 데이터 추출

각 테이블에서 코호트(icustay_delirium)에 해당하는 데이터만 추출:
- `chart_data`: CHARTEVENTS + D_ITEMS
- `lab_data`: LABEVENTS + D_LABITEMS
- `input_data`: INPUTEVENTS + D_ITEMS

---

### STEP 3: ICU 체류 기간 필터링

ICU 입실(intime) ~ 퇴실(outtime) 사이의 이벤트만 포함:
- `chart_filtered`
- `lab_filtered`
- `input_filtered`

---

### STEP 3.5: 변수 선택

#### CHART 변수 (chart_selected)

| 카테고리 | 변수 |
|----------|------|
| **섬망 평가 (CAM-ICU)** | CAM-ICU Inattention, CAM-ICU Altered LOC, CAM-ICU MS Change, CAM-ICU RASS LOC, CAM-ICU Disorganized thinking |
| **의식/신경** | Richmond-RAS Scale, Goal Richmond-RAS Scale |
| **활력 징후** | Heart Rate, O2 saturation pulseoxymetry, Arterial O2 Saturation, Temperature Fahrenheit, Temperature Celsius, Arterial Blood Pressure mean, Non Invasive Blood Pressure mean |
| **신체 측정** | Admission Weight (Kg), Admission Weight (lbs.), Daily Weight, Height (cm), Height |
| **Ventilator** | Ventilator Type |
| **기타** | Glucose, Glucose (serum), Glucose finger stick (range 70-100), Glucose (whole blood) |

#### LAB 변수 (lab_selected)

| 카테고리 | 변수 |
|----------|------|
| **혈액** | White Blood Cells, WBC Count, Hemoglobin, Hematocrit, Platelet Count |
| **전해질** | Sodium, "Sodium, Potassium, "Potassium, Chloride, "Chloride, Bicarbonate, "Bicarbonate, "Calcium, Magnesium, "Magnesium, Phosphate, "Phosphate |
| **신장/간** | Urea Nitrogen, "Urea Nitrogen", Creatinine, "Creatinine", Urine Creatinine, Creatine Kinase (CK), "Creatine Kinase, Alanine Aminotransferase (ALT), Asparate Aminotransferase (AST), Bilirubin, "Bilirubin, Albumin, "Albumin |
| **기타** | Lactate, Ammonia, pH, pCO2, pO2 |

> **참고**: 따옴표로 시작하는 변수(`"Sodium` 등)는 MIMIC-IV의 Whole Blood 측정값

#### INPUT 변수 (input_selected)

| 카테고리 | 변수 |
|----------|------|
| **진정제/진통제** | Propofol, Fentanyl, Morphine Sulfate, Fentanyl (Concentrate), Midazolam (Versed), Lorazepam (Ativan), Diazepam (Valium), Ketamine |
| **승압제** | Vasopressin, Dobutamine, Phenylephrine (50/250), Phenylephrine (200/250) |

---

### STEP 4: 통합 테이블

```sql
CREATE TABLE workdb.all_events AS
-- CHARTEVENTS
SELECT stay_id, itemid, label, value AS value_str, valuenum AS value_num,
       valueuom, charttime, 'chart' AS source
FROM workdb.chart_selected
UNION ALL
-- LABEVENTS
SELECT stay_id, itemid, label, value AS value_str, valuenum AS value_num,
       valueuom, charttime, 'lab' AS source
FROM workdb.lab_selected
UNION ALL
-- INPUTEVENTS
SELECT stay_id, itemid, label, NULL AS value_str, amount AS value_num,
       amountuom AS valueuom, starttime AS charttime, 'input' AS source
FROM workdb.input_selected;
```

**통합 컬럼 스키마:**
| 컬럼 | 설명 |
|------|------|
| stay_id | ICU 체류 ID |
| itemid | 항목 ID |
| label | 항목명 |
| value_str | 문자열 값 |
| value_num | 수치 값 |
| valueuom | 단위 |
| charttime | 측정 시간 |
| source | 데이터 소스 (chart/lab/input) |

---

## 4. 워크플로우 다이어그램

```
PATIENTS ─────┐
              ├─→ adm_pat_icu (18세 이상)
ICUSTAYS ─────┤
              │
ADMISSIONS ───┘
              │
              ↓
CHARTEVENTS ─→ CAM-ICU 기록 있는 stay_id → icustay_delirium
              │
              ├─────────────────────────────────┐
              ↓                                 │
   ┌──────────┼──────────┐                      │
   ↓          ↓          ↓                      │
CHART       LAB       INPUT                     │
   ↓          ↓          ↓                      │
 _data      _data      _data                    │
   ↓          ↓          ↓                      │
 _filtered  _filtered  _filtered                │
   ↓          ↓          ↓                      │
 _selected  _selected  _selected                │
   │          │          │                      │
   └──────────┴──────────┘                      │
              ↓                                 │
         all_events ←───────────────────────────┘
```

---

## 5. 품질 확인 쿼리

```sql
-- 코호트 크기
SELECT COUNT(DISTINCT stay_id) FROM workdb.adm_pat_icu;

-- 소스별 이벤트 수
SELECT source, COUNT(*) FROM workdb.all_events GROUP BY source;

-- 라벨별 이벤트 수 (상위 50개)
SELECT label, COUNT(*)
FROM workdb.all_events
GROUP BY label
ORDER BY COUNT(*) DESC
LIMIT 50;
```

---

## 6. 다음 단계: 데이터 변환

`all_events` 테이블을 기반으로 다음 변환 수행 (별도 SQL):
1. VALUE 변환 (Yes/No → 1/0)
2. 라벨 통합 (동일 의미 변수 합치기)
3. 단위 변환 (lbs → kg, °F → °C, inch → cm)
4. 시간 계산 (ICU 입실 기준)
5. 60분 비닝 + 피봇 → timeseries

---

## 7. 변경 이력

| 날짜 | 변경 내용 |
|------|-----------|
| 2024-02-02 | 초기 SQL 작성 (PostgreSQL 버전) |
| 2024-02-02 | AWS Athena 호환 버전으로 수정 |
| 2024-02-02 | PRESCRIPTIONS 제외, DATETIMEEVENTS 추가 |
| 2026-02-03 | DATETIMEEVENTS 제외, 변수 목록 간소화 |
| 2026-02-03 | STEP 3.5 (변수 선택) 추가, 워크플로우 문서 업데이트 |
| 2026-02-05 | 다음 단계(§6) 설명 보강: 3_Models.ipynb 모델링 파이프라인 연결 |
