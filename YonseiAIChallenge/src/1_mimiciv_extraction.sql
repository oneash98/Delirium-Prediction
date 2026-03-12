-- ============================================================================
-- MIMIC-IV Data Extraction v3
-- 기반: 1-Data_extraction_MIMIC workflow
-- PRESCRIPTIONS 제외, DATETIMEEVENTS 추가 (환자 response)
-- ============================================================================

-- ============================================================================
-- STEP 1: 코호트 정의
-- ============================================================================

-- 1-1. CAM-ICU 기록이 있는 stay_id (섬망 코호트)
CREATE TABLE workdb.icustay_delirium AS
SELECT DISTINCT stay_id
FROM mimiciv.chartevents
WHERE itemid IN (229324, 229326, 228302, 228303, 228300, 228335, 228336, 228337, 229325, 228301, 228334);

-- 1-2. 환자-ICU 기본 정보 (18세 이상)
CREATE TABLE workdb.adm_pat_icu AS
SELECT
    p.subject_id,
    a.hadm_id,
    i.stay_id,
    p.gender,
    p.anchor_age AS age,
    i.los,
    a.admission_type,
    TRY_CAST(i.intime AS TIMESTAMP) AS intime,
    TRY_CAST(i.outtime AS TIMESTAMP) AS outtime
FROM mimiciv.icustays i
INNER JOIN mimiciv.patients p ON i.subject_id = p.subject_id
INNER JOIN mimiciv.admissions a ON i.hadm_id = a.hadm_id
INNER JOIN workdb.icustay_delirium id ON i.stay_id = id.stay_id
WHERE p.anchor_age >= 18
      AND i.intime IS NOT NULL
      AND i.outtime IS NOT NULL;

-- ============================================================================
-- STEP 2: 원본 데이터 추출
-- ============================================================================

-- 2-1. CHARTEVENTS 원본 추출
CREATE TABLE workdb.chart_data AS
SELECT
    ce.stay_id,
    ce.itemid,
    di.label,
    ce.value,
    ce.valuenum,
    ce.valueuom,
    TRY_CAST(ce.charttime AS TIMESTAMP) AS charttime
FROM mimiciv.chartevents ce
INNER JOIN mimiciv.d_items di ON ce.itemid = di.itemid
INNER JOIN workdb.icustay_delirium id ON ce.stay_id = id.stay_id
WHERE ce.stay_id IS NOT NULL
      AND ce.charttime IS NOT NULL;

-- 2-2. LABEVENTS 원본 추출
CREATE TABLE workdb.lab_data AS
SELECT
    le.subject_id,
    api.stay_id,
    le.itemid,
    dl.label,
    le.value,
    le.valuenum,
    le.valueuom,
    TRY_CAST(le.charttime AS TIMESTAMP) AS charttime
FROM mimiciv.labevents le
INNER JOIN mimiciv.d_labitems dl ON le.itemid = dl.itemid
INNER JOIN workdb.adm_pat_icu api ON le.subject_id = api.subject_id
WHERE le.charttime IS NOT NULL;

-- 2-3. INPUTEVENTS 원본 추출
CREATE TABLE workdb.input_data AS
SELECT
    ie.stay_id,
    ie.itemid,
    di.label,
    ie.amount,
    ie.amountuom,
    TRY_CAST(ie.starttime AS TIMESTAMP) AS starttime,
    TRY_CAST(ie.endtime AS TIMESTAMP) AS endtime
FROM mimiciv.inputevents ie
INNER JOIN mimiciv.d_items di ON ie.itemid = di.itemid
INNER JOIN workdb.icustay_delirium id ON ie.stay_id = id.stay_id
WHERE ie.stay_id IS NOT NULL
      AND ie.starttime IS NOT NULL;

-- ============================================================================
-- STEP 3: ICU 체류 기간 내 데이터만 필터링
-- ============================================================================

-- 3-1. CHART 필터링
CREATE TABLE workdb.chart_filtered AS
SELECT c.*
FROM workdb.chart_data c
INNER JOIN workdb.adm_pat_icu api ON c.stay_id = api.stay_id
WHERE c.charttime > api.intime
      AND c.charttime < api.outtime;

-- 3-2. LAB 필터링
CREATE TABLE workdb.lab_filtered AS
SELECT l.*
FROM workdb.lab_data l
INNER JOIN workdb.adm_pat_icu api ON l.stay_id = api.stay_id
WHERE l.charttime > api.intime
      AND l.charttime < api.outtime;

-- 3-3. INPUT 필터링
CREATE TABLE workdb.input_filtered AS
SELECT i.*
FROM workdb.input_data i
INNER JOIN workdb.adm_pat_icu api ON i.stay_id = api.stay_id
WHERE i.starttime > api.intime
      AND i.starttime < api.outtime;

-- ============================================================================
-- STEP 3.5: 필요한 변수만 필터링
-- ============================================================================

-- 3.5-1. CHART 변수 필터링
CREATE TABLE workdb.chart_selected AS
SELECT * FROM workdb.chart_filtered
WHERE label IN (
    -- ========== 섬망 평가 (CAM-ICU) ==========
    'CAM-ICU Inattention',
    'CAM-ICU Altered LOC',
    'CAM-ICU MS Change',
    'CAM-ICU RASS LOC',
    'CAM-ICU Disorganized thinking',
    -- ========== 의식/신경 ==========
    'Richmond-RAS Scale',
    'Goal Richmond-RAS Scale',
    -- ========== 활력 징후 ==========
    'Heart Rate',
    'O2 saturation pulseoxymetry',
    'Arterial O2 Saturation',
    'Temperature Fahrenheit',
    'Temperature Celsius',
    'Arterial Blood Pressure mean',
    'Non Invasive Blood Pressure mean',
    -- ========== 신체 측정 ==========
    'Admission Weight (Kg)',
    'Admission Weight (lbs.)',
    'Daily Weight',
    'Height (cm)',
    'Height',
    -- ========== Ventilator ==========
    'Ventilator Type',
    -- ========== 기타 ==========
    'Glucose',
    'Glucose (serum)',
    'Glucose finger stick (range 70-100)',
    'Glucose (whole blood)'
);

-- 3.5-2. LAB 변수 필터링
CREATE TABLE workdb.lab_selected AS
SELECT * FROM workdb.lab_filtered
WHERE label IN (
    -- ========== 혈액 ==========
    'White Blood Cells',
    'WBC Count',
    'Hemoglobin',
    'Hematocrit',
    'Platelet Count',

    -- ========== 전해질 ==========
    'Sodium',
    '"Sodium',
    'Potassium',
    '"Potassium',
    'Chloride',
    '"Chloride',
    'Bicarbonate',
    '"Bicarbonate',
    '"Calcium',
    'Magnesium',
    '"Magnesium',
    'Phosphate',
    '"Phosphate',

    -- ========== 신장/간 ==========
    'Urea Nitrogen',
    '"Urea Nitrogen"',  -- BUN
    'Creatinine',
    '"Creatinine"',
    'Urine Creatinine',
    'Creatine Kinase (CK)',
    '"Creatine Kinase',
    'Alanine Aminotransferase (ALT)',
    'Asparate Aminotransferase (AST)',
    'Bilirubin',
    '"Bilirubin',
    'Albumin',
    '"Albumin',

    -- ========== 기타 ==========
    'Lactate',
    'Ammonia',
    'pH',
    'pCO2',
    'pO2'
);

-- 3.5-3. INPUT 변수 필터링
CREATE TABLE workdb.input_selected AS
SELECT * FROM workdb.input_filtered
WHERE label IN (
    -- ========== 진정제/진통제 ==========
    'Propofol',
    'Fentanyl',
    'Morphine Sulfate',
    'Fentanyl (Concentrate)',
    'Morphine Sulfate',
    'Midazolam (Versed)',
    'Lorazepam (Ativan)',
    'Diazepam (Valium)',
    'Ketamine', -- dissociative anesthetic

    -- ========== 승압제 ==========
    'Vasopressin',
    'Dobutamine',
    'Phenylephrine (50/250)',
    'Phenylephrine (200/250)'
);

-- ============================================================================
-- STEP 4: 통합 테이블
-- ============================================================================

CREATE TABLE workdb.all_events AS
-- CHARTEVENTS
SELECT
    stay_id,
    itemid,
    label,
    value AS value_str,
    valuenum AS value_num,
    valueuom,
    charttime,
    'chart' AS source
FROM workdb.chart_selected

UNION ALL

-- LABEVENTS
SELECT
    stay_id,
    itemid,
    label,
    value AS value_str,
    valuenum AS value_num,
    valueuom,
    charttime,
    'lab' AS source
FROM workdb.lab_selected

UNION ALL

-- INPUTEVENTS
SELECT
    stay_id,
    itemid,
    label,
    NULL AS value_str,
    amount AS value_num,
    amountuom AS valueuom,
    starttime AS charttime,
    'input' AS source
FROM workdb.input_selected;

-- ============================================================================
-- 품질 확인
-- ============================================================================
-- SELECT COUNT(DISTINCT stay_id) FROM workdb.adm_pat_icu;
-- SELECT source, COUNT(*) FROM workdb.all_events GROUP BY source;
-- SELECT label, COUNT(*) FROM workdb.datetime_filtered GROUP BY label ORDER BY COUNT(*) DESC LIMIT 50;
