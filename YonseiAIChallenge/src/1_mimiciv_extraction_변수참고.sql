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

-- 2-4. DATETIMEEVENTS 원본 추출 (환자 response 관련)
CREATE TABLE workdb.datetime_data AS
SELECT
    de.stay_id,
    de.itemid,
    di.label,
    de.value,
    TRY_CAST(de.charttime AS TIMESTAMP) AS charttime
FROM mimiciv.datetimeevents de
INNER JOIN mimiciv.d_items di ON de.itemid = di.itemid
INNER JOIN workdb.icustay_delirium id ON de.stay_id = id.stay_id
WHERE de.stay_id IS NOT NULL
      AND de.charttime IS NOT NULL;

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

-- 3-4. DATETIME 필터링
CREATE TABLE workdb.datetime_filtered AS
SELECT d.*
FROM workdb.datetime_data d
INNER JOIN workdb.adm_pat_icu api ON d.stay_id = api.stay_id
WHERE d.charttime > api.intime
      AND d.charttime < api.outtime;

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
    -- TODO: CAM-ICU 관련 label 추가 확인 필요

    -- ========== 의식/신경 ==========
    'GCS - Eye Opening',
    'Eye Opening',
    'GCS - Motor Response',
    'Motor Response',
    'GCS - Verbal Response',
    'Verbal Response',
    'GCS Total',
    'Richmond-RAS Scale',
    'Goal Richmond-RAS Scale',
    'RASS',

    -- ========== 활력 징후 ==========
    'Heart Rate',
    'Respiratory Rate',
    'O2 saturation pulseoxymetry',
    'SpO2',
    'Temperature Fahrenheit',
    'Temperature Celsius',
    'Arterial BP [Systolic]',
    'Arterial BP [Diastolic]',
    'Arterial BP Mean',
    'Non Invasive Blood Pressure systolic',
    'Non Invasive Blood Pressure diastolic',
    'Non Invasive Blood Pressure mean',
    -- TODO: 활력징후 label 추가 확인 필요

    -- ========== 신체 측정 ==========
    'Admission Weight (Kg)',
    'Admission Weight (lbs.)',
    'Daily Weight',
    'Height (cm)',
    'Height',
    'Admit Ht',
    'Height Inches',
    -- TODO: Weight, Height label 추가 확인 필요

    -- ========== 호흡 ==========
    'Inspired O2 Fraction',
    'FiO2',
    'FiO2 Set',
    -- TODO: FiO2 관련 label 추가 확인 필요

    -- ========== 기타 ==========
    'Glucose',
    'Glucose (serum)',
    'BUN',
    'Heparin Dose (per hour)',
    'Insulin'
    -- TODO: 기타 chart 변수 추가 확인 필요
);

-- 3.5-2. LAB 변수 필터링
CREATE TABLE workdb.lab_selected AS
SELECT * FROM workdb.lab_filtered
WHERE label IN (
    -- ========== 혈액 ==========
    'White Blood Cells',
    'WBC',
    'WBC Count',
    'Hemoglobin',
    'Hematocrit',
    'Platelet Count',
    'Platelets',

    -- ========== 전해질 ==========
    'Sodium',
    'Sodium, Whole Blood',
    'Potassium',
    'Potassium, Whole Blood',
    'Chloride',
    'Chloride, Whole Blood',
    'Bicarbonate',
    'Calcium, Total',
    'Magnesium',
    'Phosphate',

    -- ========== 신장/간 ==========
    'Urea Nitrogen',  -- BUN
    'Creatinine',
    'Alanine Aminotransferase (ALT)',
    'Asparate Aminotransferase (AST)',
    'Alkaline Phosphatase',
    'Bilirubin, Total',
    'Bilirubin, Direct',
    'Albumin',

    -- ========== 기타 ==========
    'Glucose',
    'Lactate',
    'Ammonia',
    'pH',
    'pCO2',
    'pO2',
    'INR(PT)',
    'PT',
    'PTT',
    'Oxygen Saturation'
    -- TODO: Lab 변수 추가 확인 필요
);

-- 3.5-3. INPUT 변수 필터링
CREATE TABLE workdb.input_selected AS
SELECT * FROM workdb.input_filtered
WHERE label IN (
    -- ========== 진정제/진통제 ==========
    'Propofol',
    'Fentanyl',
    'Fentanyl (Concentrate)',
    'Fentanyl (Push)',
    'Morphine Sulfate',
    'Midazolam (Versed)',
    'Midazolam',
    'Lorazepam (Ativan)',
    'Lorazepam',
    'Dexmedetomidine (Precedex)',
    'Ketamine',

    -- ========== 승압제 ==========
    'Norepinephrine',
    'Levophed',
    'Epinephrine',
    'Vasopressin',
    'Dopamine',
    'Dobutamine',

    -- ========== 기타 ==========
    'Heparin Sodium',
    'Heparin',
    'Insulin - Regular',
    'Insulin - Glargine',
    'Insulin'
    -- TODO: Input 변수 추가 확인 필요
);

-- 3.5-4. DATETIME 변수 필터링 (환자 response)
-- TODO: DATETIMEEVENTS에서 필요한 label 확인 후 필터링 추가
-- 현재는 일단 모든 데이터 포함 (데이터 확인 후 수정 필요)
CREATE TABLE workdb.datetime_selected AS
SELECT * FROM workdb.datetime_filtered;
-- WHERE label IN (
--     -- ========== 인지/의식 관련 ==========
--     'Disorientation',
--     'Confusion',
--     'Agitation',
--     -- ========== 행동 관련 ==========
--     -- TODO: 행동 관련 label 추가
-- );

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
FROM workdb.input_selected

UNION ALL

-- DATETIMEEVENTS (환자 response)
SELECT
    stay_id,
    itemid,
    label,
    value AS value_str,
    1.0 AS value_num,  -- 이벤트 발생 = 1
    NULL AS valueuom,
    charttime,
    'datetime' AS source
FROM workdb.datetime_selected;

-- ============================================================================
-- 품질 확인
-- ============================================================================
-- SELECT COUNT(DISTINCT stay_id) FROM workdb.adm_pat_icu;
-- SELECT source, COUNT(*) FROM workdb.all_events GROUP BY source;
-- SELECT label, COUNT(*) FROM workdb.datetime_filtered GROUP BY label ORDER BY COUNT(*) DESC LIMIT 50;
