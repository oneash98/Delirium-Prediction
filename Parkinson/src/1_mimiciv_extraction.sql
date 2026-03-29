-- Compare counts across:
-- among patients with a Parkinson diagnosis:
-- 1) anybody with the insertion
-- 2) insertion at any time, among patients who were admitted to ICU
-- 3) insertion during ICU
WITH target_procedures AS (
    SELECT
        icd_code,
        icd_version,
        long_title
    FROM mimiciv.d_icd_procedures
    WHERE lower(long_title) IN (
        'insertion of neurostimulator generator into skull',
        'insertion of neurostimulator lead into cerebral ventricle',
        'revision of neurostimulator lead in brain',
        'revision of neurostimulator lead in cerebral ventricle',
        'revision of neurostimulator lead in cranial nerve',
        'implantation or replacement of intracranial neurostimulator lead(s)',
        'insertion of neurostimulator lead into brain',
        'cranial implantation or replacement of neurostimulator pulse generator',
        'revision of neurostimulator generator in skull',
        '"insertion of neurostimulator generator into skull',
        '"insertion of neurostimulator lead into cerebral ventricle',
        '"revision of neurostimulator lead in brain',
        '"revision of neurostimulator lead in cerebral ventricle',
        '"revision of neurostimulator lead in cranial nerve',
        '"implantation or replacement of intracranial neurostimulator lead(s)',
        '"insertion of neurostimulator lead into brain',
        '"cranial implantation or replacement of neurostimulator pulse generator',
        '"revision of neurostimulator generator in skull'
    )
),
parkinson_patients AS (
    SELECT DISTINCT
        dx.subject_id
    FROM mimiciv.diagnoses_icd AS dx
    INNER JOIN mimiciv.d_icd_diagnoses AS dd
        ON dx.icd_code = dd.icd_code
       AND dx.icd_version = dd.icd_version
    WHERE lower(dd.long_title) LIKE '%parkinson%'
),
matched_procedures AS (
    SELECT
        p.subject_id,
        p.hadm_id,
        p.chartdate,
        p.seq_num,
        p.icd_code,
        p.icd_version,
        d.long_title
    FROM mimiciv.procedures_icd AS p
    INNER JOIN target_procedures AS d
        ON p.icd_code = d.icd_code
       AND p.icd_version = d.icd_version
    INNER JOIN parkinson_patients AS pp
        ON p.subject_id = pp.subject_id
),
icu_stays AS (
    SELECT
        subject_id,
        hadm_id,
        stay_id,
        DATE(TRY_CAST(intime AS timestamp)) AS icu_intime_date,
        DATE(TRY_CAST(outtime AS timestamp)) AS icu_outtime_date
    FROM mimiciv.icustays
),
patients_with_icu_history AS (
    SELECT DISTINCT
        mp.subject_id
    FROM matched_procedures AS mp
    INNER JOIN icu_stays AS icu
        ON mp.subject_id = icu.subject_id
       AND mp.hadm_id = icu.hadm_id
),
during_icu_patients AS (
    SELECT DISTINCT
        mp.subject_id
    FROM matched_procedures AS mp
    INNER JOIN icu_stays AS icu
        ON mp.subject_id = icu.subject_id
       AND mp.hadm_id = icu.hadm_id
    WHERE mp.chartdate BETWEEN icu.icu_intime_date AND icu.icu_outtime_date
)
SELECT
    'Parkinson patients with neurostimulator lead insertion' AS condition,
    COUNT(DISTINCT subject_id) AS patient_count
FROM matched_procedures

UNION ALL

SELECT
    'Parkinson patients with neurostimulator lead insertion and any ICU admission' AS condition,
    COUNT(*) AS patient_count
FROM patients_with_icu_history

UNION ALL

SELECT
    'Parkinson patients with insertion during ICU stay' AS condition,
    COUNT(*) AS patient_count
FROM during_icu_patients;


-- Among the same Parkinson + neurostimulator cohort, count patients with a delirium diagnosis.
WITH target_procedures AS (
    SELECT
        icd_code,
        icd_version,
        long_title
    FROM mimiciv.d_icd_procedures
    WHERE lower(long_title) IN (
        'insertion of neurostimulator generator into skull',
        'insertion of neurostimulator lead into cerebral ventricle',
        'revision of neurostimulator lead in brain',
        'revision of neurostimulator lead in cerebral ventricle',
        'revision of neurostimulator lead in cranial nerve',
        'implantation or replacement of intracranial neurostimulator lead(s)',
        'insertion of neurostimulator lead into brain',
        'cranial implantation or replacement of neurostimulator pulse generator',
        'revision of neurostimulator generator in skull',
        '"insertion of neurostimulator generator into skull',
        '"insertion of neurostimulator lead into cerebral ventricle',
        '"revision of neurostimulator lead in brain',
        '"revision of neurostimulator lead in cerebral ventricle',
        '"revision of neurostimulator lead in cranial nerve',
        '"implantation or replacement of intracranial neurostimulator lead(s)',
        '"insertion of neurostimulator lead into brain',
        '"cranial implantation or replacement of neurostimulator pulse generator',
        '"revision of neurostimulator generator in skull'
    )
),
parkinson_patients AS (
    SELECT DISTINCT
        dx.subject_id
    FROM mimiciv.diagnoses_icd AS dx
    INNER JOIN mimiciv.d_icd_diagnoses AS dd
        ON dx.icd_code = dd.icd_code
       AND dx.icd_version = dd.icd_version
    WHERE lower(dd.long_title) LIKE '%parkinson%'
),
cohort_patients AS (
    SELECT DISTINCT
        p.subject_id
    FROM mimiciv.procedures_icd AS p
    INNER JOIN target_procedures AS tp
        ON p.icd_code = tp.icd_code
       AND p.icd_version = tp.icd_version
    INNER JOIN parkinson_patients AS pp
        ON p.subject_id = pp.subject_id
),
delirium_patients AS (
    SELECT DISTINCT
        dx.subject_id
    FROM mimiciv.diagnoses_icd AS dx
    INNER JOIN mimiciv.d_icd_diagnoses AS dd
        ON dx.icd_code = dd.icd_code
       AND dx.icd_version = dd.icd_version
    WHERE lower(dd.long_title) LIKE '%delirium%'
)
SELECT
    COUNT(*) AS parkinson_neurostimulator_patients_with_delirium_diagnosis
FROM cohort_patients AS cp
INNER JOIN delirium_patients AS dp
    ON cp.subject_id = dp.subject_id;


-- Count patients with:
-- 1) a Parkinson diagnosis
-- 2) an anticholinergic prescription
-- and compare those with and without a delirium diagnosis
WITH parkinson_patients AS (
    SELECT DISTINCT
        dx.subject_id
    FROM mimiciv.diagnoses_icd AS dx
    INNER JOIN mimiciv.d_icd_diagnoses AS dd
        ON dx.icd_code = dd.icd_code
       AND dx.icd_version = dd.icd_version
    WHERE lower(dd.long_title) LIKE '%parkinson%'
),
anticholinergic_patients AS (
    SELECT DISTINCT
        subject_id
    FROM mimiciv.prescriptions
    WHERE lower(drug) IN (
        'benztropine',
        'trihexyphenidyl',
        'biperiden',
        'procyclidine',
        'orphenadrine',
        'diphenhydramine',
        'hydroxyzine',
        'promethazine',
        'scopolamine',
        'glycopyrrolate',
        'oxybutynin',
        'tolterodine',
        'fesoterodine',
        'solifenacin',
        'darifenacin',
        'trospium'
    )
),
delirium_patients AS (
    SELECT DISTINCT
        dx.subject_id
    FROM mimiciv.diagnoses_icd AS dx
    INNER JOIN mimiciv.d_icd_diagnoses AS dd
        ON dx.icd_code = dd.icd_code
       AND dx.icd_version = dd.icd_version
    WHERE lower(dd.long_title) LIKE '%delirium%'
),
base_cohort AS (
    SELECT DISTINCT
        p.subject_id
    FROM parkinson_patients AS p
    INNER JOIN anticholinergic_patients AS a
        ON p.subject_id = a.subject_id
)
SELECT
    'Parkinson patients prescribed anticholinergics with delirium' AS condition,
    COUNT(DISTINCT b.subject_id) AS patient_count
FROM base_cohort AS b
INNER JOIN delirium_patients AS d
    ON b.subject_id = d.subject_id

UNION ALL

SELECT
    'Parkinson patients prescribed anticholinergics without delirium' AS condition,
    COUNT(DISTINCT b.subject_id) AS patient_count
FROM base_cohort AS b
LEFT JOIN delirium_patients AS d
    ON b.subject_id = d.subject_id
WHERE d.subject_id IS NULL;
