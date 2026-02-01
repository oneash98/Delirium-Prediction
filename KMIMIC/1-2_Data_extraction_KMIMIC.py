"""
Data extraction for KMIMIC dataset
Converted from Jupyter notebook
# AGE 조건 : 18세 이상
"""

import pandas as pd
import csv
import sys
import os
import numpy as np
import shutil
import argparse
pd.set_option('display.max_columns', 500)

# Default; can be overridden via CLI/env in batch runs
DISCHARGED_DATE = 301

# %%
def dataframe_from_csv(path, header=0, index_col=False):
    return pd.read_csv(path, header=header, index_col=index_col, low_memory=False)


def safe_astype_int(df, col, drop_invalid=True):
    """
    컬럼을 int로 변환. KMIMIC처럼 '001...0' 문자열/float 형태도 처리.
    drop_invalid=True면 변환 실패·결측 행 제거 후 int, False면 nullable Int64 반환.
    """
    if col not in df.columns:
        return df
    num = pd.to_numeric(df[col], errors="coerce")
    is_intlike = num.notna() & np.isclose(num, np.round(num), rtol=0, atol=1e-9)
    if drop_invalid:
        keep = is_intlike
        df = df.loc[keep].copy()
        df[col] = num.loc[df.index].round().astype(int)
        return df
    df = df.copy()
    df[col] = num.where(is_intlike, pd.NA).round().astype("Int64")
    return df

# %%
def parse_datetime_kmimic(ser):
    """
    datetime 파싱; KMIMIC 연도 비식별화(2xxx)로 pandas 범위(1677~2262) 밖이면
    연도를 범위 안으로 보정 후 파싱 (chart_event_analze.py와 동일 대응).
    """
    parsed = pd.to_datetime(ser, format='mixed', errors='coerce')
    raw = ser.astype(str).str.strip()
    na_mask = parsed.isna() & ser.notna() & (raw != '') & (raw != 'nan')
    if not na_mask.any():
        return parsed
    # ISO 형식(YYYY-MM-DDTHH:MM:SS)이면 연도만 보정
    match = raw[na_mask].str.extract(r'^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})', expand=False)
    if match is None or match.isna().all(axis=1).all():
        return parsed
    year = pd.to_numeric(match[0], errors='coerce')
    year_safe = np.nan_to_num(year, nan=2000).astype(np.int64)
    fixed_year = np.where(year > 2262, 2000 + (year_safe - 2000) % 262, np.where(year < 1677, 2000 + (year_safe - 2000) % 262, year_safe))
    fixed_str = pd.Series(fixed_year, index=match.index).astype(int).astype(str).str.zfill(4) + '-' + match[1] + '-' + match[2] + 'T' + match[3] + ':' + match[4] + ':' + match[5]
    parsed = parsed.copy()
    parsed.loc[na_mask] = pd.to_datetime(fixed_str, errors='coerce')
    return parsed

# %%
def norm_id(x):
    s = pd.Series(x, dtype="string")
    return s.str.strip().str.replace(r"\.0$", "", regex=True)

# %%
def _icustay_to_int64(series_or_arraylike):
    """
    ICUSTAY_ID를 안전하게 정수(Int64)로 변환.
    - 숫자형/문자형 혼합을 허용 (to_numeric(errors='coerce'))
    - 1.0 같은 값은 1로 변환
    - 1.2 같이 정수가 아닌 값은 <NA>로 남겨 TypeError를 방지
    """
    s = pd.to_numeric(pd.Series(series_or_arraylike), errors="coerce")
    is_intlike = s.notna() & np.isclose(s, np.round(s), rtol=0, atol=1e-9)
    s = s.where(is_intlike, pd.NA)
    return s.round().astype("Int64")

# %%
def _parse_cli_args(argv=None):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--discharged-date",
        type=int,
        default=int(os.environ.get("DISCHARGED_DATE", DISCHARGED_DATE)),
    )
    parser.add_argument(
        "--kmimic-root",
        type=str,
        default=os.environ.get("KMIMIC_ROOT", "/home/coder/workspace/datasets/KMIMIC_EMR"),
    )
    parser.add_argument(
        "--out-root",
        type=str,
        default=os.environ.get("OUT_ROOT", "/home/coder/workspace/src/hjkim/Data/preprocessed"),
    )
    # Notebook/배치 환경에서 알 수 없는 인자가 섞여도 실패하지 않게 처리
    args, _unknown = parser.parse_known_args(argv)
    return args


_args = _parse_cli_args()
DISCHARGED_DATE = _args.discharged_date

# Set paths (date-specific)
kmimic_path = os.path.join(_args.kmimic_root, str(DISCHARGED_DATE))
data_path = os.path.join(_args.out_root, str(DISCHARGED_DATE))
path_csv = data_path  # Use same path as data_path for CSV output

# Create output directory if it doesn't exist
os.makedirs(data_path, exist_ok=True)
print(f"[paths] kmimic_path={kmimic_path}")
print(f"[paths] data_path={data_path}")

# Patient (KMIMIC PATIENTS.csv: SUBJECT_ID, SEX, ANCHOR_AGE, ANCHOR_YEAR, ANCHOR_YEAR_GROUP, DOD)
patient = dataframe_from_csv(os.path.join(kmimic_path, 'PATIENTS.csv'),index_col=False)
# Drop only columns that exist (KMIMIC has no ROW_ID, DOD_HOSP, DOD_SSN, EXPIRE_FLAG)
cols_to_drop_patient = ['ROW_ID', 'DOD', 'DOD_HOSP', 'DOD_SSN', 'EXPIRE_FLAG', 'ANCHOR_YEAR', 'ANCHOR_YEAR_GROUP']
patient.drop(columns=[c for c in cols_to_drop_patient if c in patient.columns], inplace=True)

print(f"Patient shape: {patient.groupby(['SUBJECT_ID']).head(1).shape}")

# %%
# ICU-Stay (KMIMIC ICUSTAYS.csv: SUBJECT_ID, HADM_ID, STAY_ID, FIRST_CAREUNIT, LAST_CAREUNIT, INTIME, OUTTIME, LOS, OP_FLAG)
icu = dataframe_from_csv(os.path.join(kmimic_path, 'ICUSTAYS.csv'),index_col=False)
# Drop only columns that exist (KMIMIC has no ROW_ID, FIRST_WARDID, LAST_WARDID, DBSOURCE; uses STAY_ID not ICUSTAY_ID)
cols_to_drop_icu = ['ROW_ID', 'FIRST_CAREUNIT', 'LAST_CAREUNIT', 'FIRST_WARDID', 'LAST_WARDID', 'DBSOURCE', 'OP_FLAG']
icu.drop(columns=[c for c in cols_to_drop_icu if c in icu.columns], inplace=True)
# KMIMIC uses STAY_ID; rename to ICUSTAY_ID for compatibility with downstream code
if 'STAY_ID' in icu.columns and 'ICUSTAY_ID' not in icu.columns:
    icu.rename(columns={'STAY_ID': 'ICUSTAY_ID'}, inplace=True)

print(f"ICU shape: {icu.shape}")
print(f"ICU unique patients: {icu.groupby(['SUBJECT_ID']).head(1).shape}")


# %%
# Filter ICU Stays on Age (merge key: SUBJECT_ID from ICUSTAYS.csv / PATIENTS.csv)
merge_on_subject = 'SUBJECT_ID'  # ICUSTAYS.csv columns: SUBJECT_ID, HADM_ID, STAY_ID→ICUSTAY_ID, INTIME, OUTTIME, LOS
patient_icu = pd.merge(icu, patient, on=merge_on_subject)

print(f"Patient ICU shape: {patient_icu.groupby(['SUBJECT_ID']).head(1).shape}")
print(f"Patient ICU by HADM_ID: {patient_icu.groupby(['HADM_ID']).head(1).shape}")
print(f"Patient ICU total shape: {patient_icu.shape}")


# %%
# AGE: KMIMIC has ANCHOR_AGE (e.g. "87 years"); MIMIC has DOB (date of birth)
if 'DOB' in patient_icu.columns:
    patient_icu['DOBYear'] = pd.to_datetime(patient_icu['DOB'], format='mixed', errors='coerce')
    patient_icu['DOBYear'] = patient_icu.DOBYear.dt.year
    patient_icu['INTIMEYear'] = pd.to_datetime(patient_icu['INTIME'], format='mixed', errors='coerce')
    patient_icu['INTIMEYear'] = patient_icu.INTIMEYear.dt.year
    patient_icu['AGE'] = patient_icu['INTIMEYear'] - patient_icu['DOBYear']
    patient_icu.drop(columns=['DOBYear', 'INTIMEYear', 'DOB'], inplace=True)
elif 'ANCHOR_AGE' in patient_icu.columns:
    # ANCHOR_AGE format: "87 years", "79 years" -> extract numeric part
    patient_icu['AGE'] = patient_icu['ANCHOR_AGE'].astype(str).str.extract(r'(\d+)', expand=False).astype(float)
    patient_icu.drop(columns=['ANCHOR_AGE'], inplace=True)
else:
    raise KeyError("Neither DOB nor ANCHOR_AGE found in patient_icu; check PATIENTS.csv columns.")

# KMIMIC PATIENTS has SEX; downstream expects GENDER
if 'SEX' in patient_icu.columns and 'GENDER' not in patient_icu.columns:
    patient_icu.rename(columns={'SEX': 'GENDER'}, inplace=True)

patient_icu_adults = patient_icu[patient_icu.AGE >= 18]
print(f"Patients (AGE >= 18): {patient_icu_adults.groupby(['SUBJECT_ID']).head(1).shape}")
print(f"Patients (AGE >= 18) total: {patient_icu_adults.shape}")

patient_icu = patient_icu[patient_icu.AGE >= 18]

# %%


# %%
# Admission (KMIMIC ADMISSIONS.csv: SUBJECT_ID, HADM_ID, ADMITTIME, DISCHTIME, DEATHTIME, ADMISSION_TYPE,
# ADMISSION_LOCATION, DISCHARGE_LOCATION, INSURANCE, LANGUAGE, MARITAL_STATUS, ETHNICITY, EDREGTIME, EDOUTTIME,
# HOSPITAL_EXPIRE_FLAG, ICU_EXPIRE_FLAG, NATIONALITY, HOSPITAL_ID; no ROW_ID, HAS_CHARTEVENTS_DATA, RELIGION)
admission = dataframe_from_csv(os.path.join(kmimic_path, 'ADMISSIONS.csv'),index_col=False)
cols_to_drop_admission = ['ROW_ID', 'ADMITTIME', 'DISCHTIME', 'DEATHTIME', 'ADMISSION_TYPE', 'ADMISSION_LOCATION',
                          'DISCHARGE_LOCATION', 'EDREGTIME', 'EDOUTTIME', 'HAS_CHARTEVENTS_DATA', 'HOSPITAL_EXPIRE_FLAG',
                          'INSURANCE', 'LANGUAGE', 'RELIGION', 'MARITAL_STATUS', 'ICU_EXPIRE_FLAG', 'NATIONALITY', 'HOSPITAL_ID', 'ETHNICITY']
admission.drop(columns=[c for c in cols_to_drop_admission if c in admission.columns], inplace=True)
# KMIMIC has no DIAGNOSIS column; add placeholder so downstream col selection works
if 'DIAGNOSIS' not in admission.columns:
    admission['DIAGNOSIS'] = 'nodx'

print(f"Admission head:\n{admission.head()}")
print(f"Admission shape: {admission.shape}")


# %%
# Full ICUStays Information
adm_pat_icu = pd.merge(patient_icu, admission, on='HADM_ID')

adm_pat_icu.drop(columns=['SUBJECT_ID_y'], inplace=True)
col = ['SUBJECT_ID_x', 'HADM_ID', 'ICUSTAY_ID', 'GENDER', 'AGE', 'LOS', 'INTIME', 'OUTTIME', 'DIAGNOSIS']
adm_pat_icu = adm_pat_icu[col]
adm_pat_icu.columns = ['SUBJECT_ID', 'HADM_ID', 'ICUSTAY_ID', 'GENDER', 'AGE', 'LOS', 'INTIME', 'OUTTIME', 'DIAGNOSIS']


# %%
g_map = {'F': 1, 'M': 2}
def transform_gender(gender_series):
    global g_map
    return {'GENDER': gender_series.fillna('').apply(lambda s: g_map[s] if s in g_map else g_map[''])}

adm_pat_icu.update(transform_gender(adm_pat_icu.GENDER))


# %%
def transform_dx_into_id(df):
    df['DIAGNOSIS'] = df['DIAGNOSIS'].fillna('nodx')
    dx_type = df['DIAGNOSIS'].unique()
    dict_dx_key = pd.factorize(dx_type)[1]
    dict_dx_val = pd.factorize(dx_type)[0]
    dictionary  = dict(zip(dict_dx_key, dict_dx_val))
    df['DIAGNOSIS'] = df['DIAGNOSIS'].map(dictionary)
    return df

adm_pat_icu = transform_dx_into_id(adm_pat_icu)

print(f"Adm pat icu head:\n{adm_pat_icu.head()}")
print(f"Adm pat icu shape: {adm_pat_icu.shape}")

# %%


# %%
# ========== 섬망 관련 추출 (197번 라인 이후 통합) ==========
vocab_chart_path = r"/home/coder/workspace/datasets/KMIMIC_VOCA/M_CHARTEVENTS.csv" 

# ========== 섬망 치료제(항정신병약) 처방 기반 cohort 정의 ==========
# 섬망 치료제 처방(STAY_ID 기준) 이력이 있는 ICU stay만 추출
vocab_prescriptions_path = "/home/coder/workspace/datasets/KMIMIC_VOCA/M_PRESCRIPTIONS_GSN.csv"
antipsy_gsn = ['N05AD01', 'N05AH04', 'N05AX08', 'N05AH03']

try:
    vocab_prescriptions = pd.read_csv(vocab_prescriptions_path, encoding='cp949', on_bad_lines='skip')
except Exception:
    vocab_prescriptions = pd.read_csv(vocab_prescriptions_path, encoding='utf-8', on_bad_lines='skip')

prescriptions = dataframe_from_csv(os.path.join(kmimic_path, 'PRESCRIPTIONS.csv'), index_col=False)
if 'GSN' not in prescriptions.columns:
    raise KeyError("PRESCRIPTIONS.csv must include 'GSN' column for antipsychotic filtering.")
prescriptions['GSN'] = norm_id(prescriptions['GSN'])
vocab_prescriptions['GSN'] = norm_id(vocab_prescriptions['GSN'])

prescriptions = pd.merge(prescriptions, vocab_prescriptions, on=['GSN'], how='left')
prescriptions_antipsy = prescriptions[prescriptions['GSN'].isin(antipsy_gsn)].copy()
prescriptions_antipsy.to_csv(os.path.join(data_path, 'prescriptions_antipsy.csv'), index=False)
print(f"PRESCRIPTIONS antipsy rows: {len(prescriptions_antipsy)}, saved to prescriptions_antipsy.csv")

stay_col_rx = 'STAY_ID' if 'STAY_ID' in prescriptions_antipsy.columns else 'ICUSTAY_ID'
icustay_antipsy = prescriptions_antipsy[stay_col_rx].dropna().unique()
icustay_antipsy = set(norm_id(icustay_antipsy).dropna().tolist())
print(f"ICU stays with antipsy (PRESCRIPTIONS, unique): {len(icustay_antipsy)}")

# Downstream에서 공통으로 사용할 cohort stay set
icustay_cohort = icustay_antipsy

# admission/ICU stay 테이블도 cohort로 제한 (불필요한 환자 폴더 생성/불필요한 right join 방지)
adm_pat_icu['ICUSTAY_ID'] = norm_id(adm_pat_icu['ICUSTAY_ID'])
adm_pat_icu = adm_pat_icu[adm_pat_icu['ICUSTAY_ID'].isin(icustay_cohort)].copy()
print(f"Adm pat icu (antipsy cohort) shape: {adm_pat_icu.shape}")

# %%
# CHARTEVENTS 로드 후 cohort stay만 사용 (downstream 호환)
chart_path = os.path.join(kmimic_path, 'CHARTEVENTS.csv')
chart = dataframe_from_csv(chart_path, index_col=False)
chart.drop(
    columns=[
        'ROW_ID', 'SUBJECT_ID', 'HADM_ID', 'STORETIME',
        'CGID', 'RESULTSTATUS', 'STOPPED', 'WARNING', 'ERROR'
    ],
    inplace=True,
    errors='ignore'
)
# stay 컬럼 결정 (위 코드와 동일한 로직)
stay_col = 'STAY_ID' if 'STAY_ID' in chart.columns else 'ICUSTAY_ID'
# stay 값 있는 행만 유지
chart = chart.loc[chart[stay_col].notnull()].copy()
# 형 변환
chart[stay_col] = norm_id(chart[stay_col])

# 섬망 치료제(항정신병약) 처방 ICU stay만 필터링
chart = chart[chart[stay_col].isin(icustay_cohort)]
# 값 확인
chart['VALUE'].unique()

# %%
# D_ITEM - LABEL for other Tables (KMIMIC D_ITEMS.csv: ITEMID, LABEL, ABBREVIATION, LINKSTO, CATEGORY, UNITNAME, PARAM_TYPE, LOWNORMALVALUE, HIGHNORMALVALUE)
d_item = dataframe_from_csv(os.path.join(kmimic_path, 'D_ITEMS.csv'), index_col=False)
cols_to_drop_d_item = ['ABBREVIATION', 'CATEGORY', 'UNITNAME', 'CONCEPTID', 'ROW_ID', 'DBSOURCE', 'LINKSTO',
                       'PARAM_TYPE', 'LOWNORMALVALUE', 'HIGHNORMALVALUE']
d_item.drop(columns=[c for c in cols_to_drop_d_item if c in d_item.columns], inplace=True)

print(f"D_ITEM head:\n{d_item.head()}")

# %%
# Add Item_id to chart (LABEL from D_ITEMS)
chart = pd.merge(chart, d_item, on='ITEMID')

print(f"Chart head:\n{chart.head()}")
print(f"Chart shape: {chart.shape}")


# %%
# VALUE → VALUENUM 매핑 (섬망 등 코딩)
chart.loc[chart['VALUE'] == 'No'       , 'VALUENUM'] = 0
chart.loc[chart['VALUE'] == 'Negative' , 'VALUENUM'] = 0
chart.loc[chart['VALUE'] == 'No (Stop - Not delirious)' , 'VALUENUM'] = 0
chart.loc[chart['VALUE'] == 'Yes'     , 'VALUENUM'] = 1
chart.loc[chart['VALUE'] == 'Positive', 'VALUENUM'] = 1
chart.loc[chart['VALUE'] == 'Yes (Continue)', 'VALUENUM'] = 1
chart.loc[chart['VALUE'] == '양성', 'VALUENUM'] = 1
chart.loc[chart['VALUE'] == '음성', 'VALUENUM'] = 0

chart.drop(columns=['VALUE'], inplace=True)
chart = chart.loc[chart.VALUENUM.notnull()]

# %%
# Add FSN_item to chart
vocab_chart = pd.read_csv(vocab_chart_path, encoding='cp949', on_bad_lines='skip')
vocab_chart = vocab_chart[['itemid', 'category', 'FSN_id', 'FSN_term']]
vocab_chart.columns = ['ITEMID', 'category', 'FSN_id', 'FSN_term']

chart = pd.merge(chart, vocab_chart, on='ITEMID')

print(f"Chart head:\n{chart.head()}")
print(f"Chart shape: {chart.shape}")

# %%
chart.columns

# %%
chart.CHARTTIME = parse_datetime_kmimic(chart.CHARTTIME)
chart.VALUEUOM = chart.VALUEUOM.fillna('').astype(str)
col = ['STAY_ID', 'ITEMID', 'LABEL', 'category', 'FSN_id', 'FSN_term', 'VALUENUM', 'VALUEUOM', 'CHARTTIME']
chart = chart[col]
chart.rename(columns = {'STAY_ID': 'ICUSTAY_ID', 'VALUENUM': 'VALUE'}, inplace=True)

chart['ICUSTAY_ID'] = norm_id(chart['ICUSTAY_ID'])

# %%
def check(x):
    try:
        x = float(str(x).strip())
    except:
        x = np.nan
    return x

def check_itemvalue(df):
    df['VALUE'] = df['VALUE'].apply(lambda x: check(x))
    df['VALUE'] = df.VALUE.astype(float)
    return df

chart = check_itemvalue(chart)
chart = chart.loc[chart.VALUE.notnull()]

# %%
# FSN_ids
chart_features = [
       '29463-7', # Body weight 
       '8302-2', #Height
       '59410-1', # Oxygen Saturagion
       '8867-4',  #Heart rate
       '8310-5', # Temperature C
       '74774-1', # Glucose
       '19996-8', # FiO2
       '1345050000', # RASS
       '8480-6', # NBP - Systolic
       '8462-4', # NBP - Diastloic
       '8478-0', # NBP - Mean
       '3027801', # PaO2
       '3027946', # PaCo2
       '9279-1', # Respiratory Rate
       '3019977', # pH
       '60956-0' # Intracranial pressure
]

# %%
chart = chart[chart['FSN_id'].isin(chart_features)]

# %%
chart.to_csv(os.path.join(data_path, 'chart.csv'),index=False)

# %%
# 항정신병약 처방 시간(STARTTIME)을 최종 이벤트 테이블에 포함
# all_tables / timeseries 생성 시 함께 concat 되도록 chart/lab/drug과 동일하게 ICUSTAY_ID, CHARTTIME, VALUE를 제공
prescriptions_antipsy_events = prescriptions_antipsy.copy()
if 'STARTTIME' not in prescriptions_antipsy_events.columns:
    raise KeyError("PRESCRIPTIONS.csv must include 'STARTTIME' column to include prescription time.")
prescriptions_antipsy_events['ICUSTAY_ID'] = norm_id(
    prescriptions_antipsy_events['STAY_ID'] if 'STAY_ID' in prescriptions_antipsy_events.columns else prescriptions_antipsy_events.get('ICUSTAY_ID')
)
prescriptions_antipsy_events['CHARTTIME'] = parse_datetime_kmimic(prescriptions_antipsy_events['STARTTIME'])
prescriptions_antipsy_events = prescriptions_antipsy_events.loc[
    prescriptions_antipsy_events['ICUSTAY_ID'].notna() & prescriptions_antipsy_events['CHARTTIME'].notna()
].copy()
prescriptions_antipsy_events['LABEL'] = 'Antipsychotic prescription'
prescriptions_antipsy_events['ITEMID'] = prescriptions_antipsy_events['GSN']
prescriptions_antipsy_events['VALUE'] = 1.0
prescriptions_antipsy_events['VALUEUOM'] = ''
prescriptions_antipsy_events = prescriptions_antipsy_events[['ICUSTAY_ID', 'ITEMID', 'LABEL', 'VALUE', 'VALUEUOM', 'CHARTTIME']]
prescriptions_antipsy_events.to_csv(os.path.join(data_path, 'prescriptions_antipsy_events.csv'), index=False)
print(f"PRESCRIPTIONS antipsy events rows: {len(prescriptions_antipsy_events)}, saved to prescriptions_antipsy_events.csv")

# %%
# LAB Events (KMIMIC: LABEVENT_ID, STAY_ID 사용; ROW_ID 없음. drop은 존재하는 컬럼만)
lab = dataframe_from_csv(os.path.join(kmimic_path, 'LABEVENTS.csv'),index_col=False)
# VALUE가 비어있고 VALUENUM이 있으면 VALUE를 VALUENUM으로 채움 (drop 전에 처리)
if 'VALUENUM' in lab.columns:
    empty_val = lab['VALUE'].isna() | (lab['VALUE'].astype(str).str.strip() == '')
    lab.loc[empty_val, 'VALUE'] = lab.loc[empty_val, 'VALUENUM']
lab.drop(columns=[c for c in ['ROW_ID', 'LABEVENT_ID', 'VALUENUM', 'FLAG'] if c in lab.columns], inplace=True)


# %%
# Add FSN_item to LAB Events
vocab_lab_path = '/home/coder/workspace/datasets/KMIMIC_VOCA/M_LABEVENTS.csv'
vocab_lab = pd.read_csv(vocab_lab_path, encoding='utf-8-sig', on_bad_lines='skip')
vocab_lab = vocab_lab[['itemid', 'label', 'omop_concept_id_1', 'concept_name_1']]
vocab_lab.columns = ['ITEMID', 'label', 'omop_concept_id', 'concept_name']
lab = pd.merge(lab, vocab_lab, on='ITEMID')

# %%
# ITEMID 문자열 통일·공백 제거 후 merge (타입/공백 차이로 매칭 실패 방지)
lab['ITEMID'] = norm_id(lab['ITEMID'])
d_lab = dataframe_from_csv(os.path.join(kmimic_path, 'D_LABITEMS.csv'),index_col=False)
# KMIMIC D_LABITEMS: ITEMID, LABEL, FLUID, CATEGORY, EDI_CODE (ROW_ID·LOINC_CODE 없음)
d_lab.drop(columns=[c for c in ['ROW_ID', 'FLUID', 'CATEGORY', 'LOINC_CODE', 'EDI_CODE'] if c in d_lab.columns], inplace=True)
d_lab['ITEMID'] = norm_id(d_lab['ITEMID'])

# %%
lab_dlab = pd.merge(lab, d_lab, on='ITEMID', how='inner')
lab_dlab.VALUEUOM = lab_dlab.VALUEUOM.fillna('').astype(str)
lab_dlab = lab_dlab.loc[lab_dlab.VALUE.notnull()]

print(f"Lab dlab head:\n{lab_dlab.head()}")
print(f"Lab dlab shape: {lab_dlab.shape}")

# %%
# Add icu-stay to Lab events
icu_lab = pd.merge(lab_dlab, adm_pat_icu, how='right', on=['SUBJECT_ID', 'HADM_ID'])

icu_lab.INTIME    = parse_datetime_kmimic(icu_lab.INTIME)
icu_lab.OUTTIME   = parse_datetime_kmimic(icu_lab.OUTTIME)
icu_lab.CHARTTIME = parse_datetime_kmimic(icu_lab.CHARTTIME)

# %%
icu_lab = icu_lab[(icu_lab['CHARTTIME'] > icu_lab['INTIME']) & (icu_lab['CHARTTIME'] < icu_lab['OUTTIME'])]
# KMIMIC: lab에 STAY_ID가 있으면 해당 ICU stay와 일치하는 행만 유지
if 'STAY_ID' in icu_lab.columns:
    icu_lab = icu_lab[norm_id(icu_lab['STAY_ID']) == norm_id(icu_lab['ICUSTAY_ID'])]

icu_lab = icu_lab[['ICUSTAY_ID', 'ITEMID', 'LABEL', 'VALUE', 'VALUEUOM', 'CHARTTIME', 'omop_concept_id', 'concept_name']]


# %%
# KMIMIC LAB ITEMID는 문자열(예: 001L31090)일 수 있음 → 숫자로만 이뤄진 경우만 int 변환
_numeric_itemid = pd.to_numeric(icu_lab['ITEMID'], errors='coerce')
if _numeric_itemid.notna().all():
    icu_lab['ITEMID'] = _numeric_itemid.astype(int)

icu_lab = check_itemvalue(icu_lab)
icu_lab = icu_lab.loc[icu_lab.VALUE.notnull()]

print(f"ICU lab head:\n{icu_lab.head()}")
print(f"ICU lab shape: {icu_lab.shape}")
print(f"ICU lab labels: {icu_lab['concept_name'].unique()}")

# %%
# Filter Lab Event based on Delirium icustay  and Features
icu_lab['ICUSTAY_ID'] = norm_id(icu_lab['ICUSTAY_ID'])
icu_lab = icu_lab[icu_lab['ICUSTAY_ID'].isin(icustay_cohort)]

print(f"ICU lab with Chloride: {icu_lab[icu_lab['LABEL'].str.contains('Chloride')].shape}")


# %%
# lab FSN 
icu_lab_features = [
    3000905, # WBC (Leukocytes)
    3019550, # Sodium in blood
    3013682, # BUN
    3002173, # Hemoglobin (Arterial)
    3000963, # Hemoglobin (blood)
    3023103, # potassium (serum or plasma)
    3008295, # serum osmolality
    3030942, # Ammonia in blood
    3009682, # Cortisol in blood
    3019977, # pH
    3027946, # pCO2
    3027801 # pO2
]

# %%
icu_lab = icu_lab[icu_lab['omop_concept_id'].isin(icu_lab_features)]
print(f"ICU lab with Hemoglobin: {icu_lab[icu_lab['omop_concept_id'] == 3002173].shape}")
print(f"ICU lab shape: {icu_lab.shape}")

# %%
print(f"ICU lab head:\n{icu_lab.head()}")
print(f"ICU lab shape: {icu_lab.shape}")
print(f"ICU lab labels: {icu_lab.LABEL.unique()}")

# %%
icu_lab.to_csv(os.path.join(data_path, 'icu_lab.csv'),index=False)

# %%
# DATETIME Event에서 약물 관련 데이터 추출
datetime_events = dataframe_from_csv(os.path.join(kmimic_path, 'DATETIMEEVENTS.csv'),index_col=False)
datetime_events = datetime_events[['SUBJECT_ID', 'HADM_ID', 'STAY_ID', 'CHARTTIME', 'ITEMID']]

# datetimeevnets 상의 FSN_id 참고
vocab_datetime_path = "/home/coder/workspace/datasets/KMIMIC_VOCA/M_DATETIMEEVENTS.csv" 
vocab_datetime = pd.read_csv(vocab_datetime_path, encoding='cp949', on_bad_lines='skip')
vocab_datetime = vocab_datetime[['itemid', 'label', 'FSN1_id', 'FSN1_term']]
vocab_datetime.columns = ['ITEMID', 'LABEL', 'FSN_id', 'FSN_term']
datetime_events = pd.merge(datetime_events, vocab_datetime, on='ITEMID')

# %%
# Add icu-stay to drug events
icu_datetime = pd.merge(datetime_events, adm_pat_icu, how='right', on=['SUBJECT_ID', 'HADM_ID'])

icu_datetime.INTIME    = parse_datetime_kmimic(icu_datetime.INTIME)
icu_datetime.OUTTIME   = parse_datetime_kmimic(icu_datetime.OUTTIME)
icu_datetime.CHARTTIME = parse_datetime_kmimic(icu_datetime.CHARTTIME)

# %%
icu_datetime = icu_datetime[(icu_datetime['CHARTTIME'] > icu_datetime['INTIME']) & (icu_datetime['CHARTTIME'] < icu_datetime['OUTTIME'])]

# %%
# KMIMIC: lab에 STAY_ID가 있으면 해당 ICU stay와 일치하는 행만 유지
if 'STAY_ID' in icu_datetime.columns:
    icu_datetime = icu_datetime[icu_datetime['STAY_ID'] == icu_datetime['ICUSTAY_ID']]

# %%
icu_datetime = icu_datetime[['ICUSTAY_ID', 'ITEMID', 'LABEL', 'CHARTTIME', 'FSN_id', 'FSN_term']]

# KMIMIC LAB ITEMID는 문자열(예: 001L31090)일 수 있음 → 숫자로만 이뤄진 경우만 int 변환
_numeric_itemid = pd.to_numeric(icu_datetime['ITEMID'], errors='coerce')
if _numeric_itemid.notna().all():
    icu_datetime['ITEMID'] = _numeric_itemid.astype(int)

print(f"ICU datetime head:\n{icu_datetime.head()}")
print(f"ICU datetime shape: {icu_datetime.shape}")
print(f"ICU datetime labels: {icu_datetime['FSN_term'].unique()}")

# %%
# Filter Drug Events
icu_datetime['ICUSTAY_ID'] = norm_id(icu_datetime['ICUSTAY_ID'])
icu_datetime = icu_datetime[icu_datetime['ICUSTAY_ID'].isin(icustay_cohort)]
len(icu_datetime)

# %%
# drug FSN
drug_features = [
    72641008, #Administration of sedative 
    726582005, #Opiate therapy 
    770571009,	#Benzodiazepine therapy 
    103746007, #Heparin therapy
]

# %%
icu_drugs = icu_datetime[icu_datetime['FSN_id'].isin(drug_features)]
print(f"ICU drug with sedatives: {icu_drugs[icu_drugs['FSN_id'] == 72641008].shape}")
print(f"ICU drug shape: {icu_drugs.shape}")

# %%
print(f"ICU drugs head:\n{icu_drugs.head()}")
print(f"ICU drugs shape: {icu_drugs.shape}")
print(f"ICU drugs labels: {icu_drugs.LABEL.unique()}")

# %%
icu_drugs.to_csv(os.path.join(data_path, 'icu_drugs.csv'),index=False)

# %%


# %%
# ========== 섬망 관련 환자 반응 추출 ==========

# 섬망 관련 FSN_id (SNOMED CT 개념 ID, 첨부 이미지 기준) - Delirium (disorder)=2776000, 우선순위 4~1 항목
DELIRIUM_FSN_IDS = {
    2776000,    # Delirium (disorder) - 우선순위 4
    45150006,   # Auditory hallucinations (finding)
    288579009,  # Difficulty communicating (finding)
    286410009,  # Difficulty speaking intelligibly (finding)
    62476001,   # Disorientated (finding)
    72440003,   # Disorientated in place (finding)
    19657006,   # Disorientated in time (finding)
    62766000,   # Disorientation for person (finding)
    64270008,   # Disturbance of understanding (finding)
    830285008,  # Fluctuation of level of consciousness (finding)
    386806002,  # Impaired cognition (finding)
    284596004,  # Incoherent speech (finding)
    386807006,  # Memory impairment (finding)
    64269007,   # Visual hallucinations (finding)
    61372001,   # Aggressive behavior (finding)
    24199005,   # Feeling agitated (finding)
    55929007,   # Feeling irritable (finding)
    366004006,  # Finding of shouting (finding)
    33624008,   # Hyperirritability (finding)
    26677001,   # Sleep pattern disturbance (finding)
    713567005,  # Sleeps during day (finding)
    301345002,  # Difficulty sleeping (finding)
    112082005,  # Inappropriate behavior (finding)
    193462001,  # Insomnia (disorder)
    105481005,  # Refusing food (finding)
    423884000,  # Repetitious behavior (finding)
    609583009,  # Repetitive questioning (finding)
    39898005,   # Sleep disorder (disorder)
    13791008,   # Asthenia (finding)
    271782001,  # Drowsy (finding)
    248261008,  # Oversleeps (disorder)
    162221009,  # Restlessness (finding)
}


# %%
# DELIRIUM_FSN_IDS로 최종 필터링
icu_delirium = icu_datetime[icu_datetime['FSN_id'].isin(DELIRIUM_FSN_IDS)]
print(f"ICU delirium with 'delirium': {icu_delirium[icu_delirium['FSN_id'] == 2776000].shape}")
print(f"ICU delirium FSN_term final:\n{icu_delirium['FSN_term'].unique()}")


# %%
print(f"ICU delirium head:\n{icu_delirium.head()}")
print(f"ICU delirium shape: {icu_delirium.shape}")
print(f"ICU delirium labels: {icu_delirium.LABEL.unique()}")

# %%
# 저장
icu_delirium.to_csv(os.path.join(data_path, 'icu_delirium.csv'), index=False)

# %%


# %%
# All Tables
chart = pd.read_csv(os.path.join(data_path, 'chart.csv'))
icu_lab = pd.read_csv(os.path.join(data_path, 'icu_lab.csv'))
icu_drugs = pd.read_csv(os.path.join(data_path, 'icu_drugs.csv'))
icu_delirium = pd.read_csv(os.path.join(data_path, 'icu_delirium.csv'))

# %%
# icu_drugs와 icu_delirium에 VALUE 컬럼 추가 (이벤트 발생 = 1)
# DATETIMEEVENTS 테이블에는 VALUE가 없으므로 발생 여부만 기록
icu_drugs['VALUE'] = 1
icu_delirium['VALUE'] = 1

# %%
chart['LABEL'] = chart['LABEL'].where(chart['FSN_term'].isna(), chart['FSN_term'])
icu_lab['LABEL'] = icu_lab['LABEL'].where(icu_lab['concept_name'].isna(), icu_lab['concept_name'])
icu_drugs['LABEL'] = icu_drugs['LABEL'].where(icu_drugs['FSN_term'].isna(), icu_drugs['FSN_term'])
icu_delirium['LABEL'] = icu_delirium['LABEL'].where(icu_delirium['FSN_term'].isna(), icu_delirium['FSN_term'])

mapping = {
    'Oxygen saturation in Arterial blood by Pulse oximetry --on room air': 'oxygen saturation',
       'Leukocytes [#/volume] in Blood by Automated count': 'WBC',
       'Hemoglobin [Mass/volume] in Blood': 'Hemoglobin',
       'pH of Arterial blood': 'pH',
       'Carbon dioxide [Partial pressure] in Arterial blood': 'PaCO2',
       'Oxygen [Partial pressure] in Arterial blood': 'PaO2',
       'Urea nitrogen [Mass/volume] in Serum or Plasma': 'BUN',
       'Sodium [Moles/volume] in Serum or Plasma': 'Sodium',
       'Potassium [Moles/volume] in Serum or Plasma': 'Potassium',
       'Osmolality of Serum or Plasma': 'Osmolality',
       'Oxygen/Inspired gas Respiratory system --on ventilator': 'FiO2',
       'Richmond Agitation Sedation Scale score (observable entity)': 'RASS',
       'Glucose [Mass/volume] in Serum, Plasma or Blood': 'Glucose',
       'Intracranial pressure (ICP)': 'ICP',
       'Hemoglobin [Mass/volume] in Arterial blood': 'Hemoglobin',
       'Ammonia [Mass/volume] in Blood': 'Ammonia',
       'Cortisol [Mass/volume] in Serum or Plasma': 'Cortisol',
       'Administration of sedative (procedure)': 'Sedative drugs',
       'Heparin therapy (procedure)': 'Heparin drugs', 
       'Opiate therapy (procedure)': 'Opiate drugs',
       'Benzodiazepine therapy (procedure)': 'Benzodiazepine drugs'
}

chart['LABEL'] = chart['LABEL'].replace(mapping)
icu_lab['LABEL'] = icu_lab['LABEL'].replace(mapping)
icu_drugs['LABEL'] = icu_drugs['LABEL'].replace(mapping)
icu_delirium['LABEL'] = icu_delirium['LABEL'].replace(mapping)

# %%
tables = [chart, icu_lab, icu_drugs, icu_delirium, prescriptions_antipsy_events]
all_tables = pd.concat(tables, ignore_index=True)

# %%
all_tables = all_tables.sort_values(by=['ICUSTAY_ID','CHARTTIME'], axis=0)
all_tables.reset_index(inplace=True, drop=True)

all_tables = check_itemvalue(all_tables)

print(f"All tables head:\n{all_tables.head()}")
print(f"All tables shape: {all_tables.shape}")
print(f"All tables unique ICUSTAY_ID: {all_tables.ICUSTAY_ID.nunique()}")
print(f"All tables unique LABEL: {all_tables.LABEL.nunique()}")

all_tables.to_csv(os.path.join(data_path, 'all_tables.csv'), index=False)

# %%
def cohort_stay_id(frame):
    cohort = pd.Series(frame.ICUSTAY_ID.unique())
    # KMIMIC: ICUSTAY_ID를 정수 → 문자열로 통일 (float .0 제거)
    # 이미 문자열이면 숫자 캐스팅하지 말고 정규화만 수행
    if pd.api.types.is_string_dtype(cohort) or pd.api.types.is_object_dtype(cohort):
        cohort_str = norm_id(cohort).replace({"<NA>": pd.NA, "nan": pd.NA, "None": pd.NA})
        cohort_str = cohort_str.dropna()
        cohort_str = cohort_str[cohort_str != ""]
        return cohort_str.values
    # 숫자형이면 정수로 볼 수 있는 값만 안전 변환
    cohort_int = _icustay_to_int64(cohort).dropna()
    return cohort_int.astype(str).str.strip().values

# def _icustay_to_int64(series_or_arraylike):
#     s = pd.to_numeric(pd.Series(series_or_arraylike), errors='coerce')
#     # 정수로 볼 수 있는 값만 유지 (부동소수 오차 허용)
#     is_intlike = s.notna() & np.isclose(s, np.round(s), rtol=0, atol=1e-9)
#     s = s.where(is_intlike, pd.NA)
#     return s.round().astype("Int64")

def icustay_to_str(series):
    """ICUSTAY_ID를 정수 → 문자열로 변환 (float .0 제거)."""
    s = pd.Series(series)
    # 이미 문자열/오브젝트면 숫자로 바꾸려 하지 말고 정규화만 수행
    if pd.api.types.is_string_dtype(s) or pd.api.types.is_object_dtype(s):
        return norm_id(s)
    # 숫자형이면 소수점이 있는 값은 <NA>로 남겨 비교/필터에서 자동 제외되도록 함
    return _icustay_to_int64(s).astype("string").str.strip()

# %%
# ADMISSION
def break_up_admission_by_unit_stay(adm, data_path, stayid, verbose=1):
    unit_stays = stayid
    nb_unit_stays = len(unit_stays) if hasattr(unit_stays, '__len__') else unit_stays.shape[0]
    adm['ICUSTAY_ID'] = icustay_to_str(adm['ICUSTAY_ID'])
    for i, stay_id in enumerate(unit_stays):
        if verbose:
            sys.stdout.write('\rStayID {0} of {1}...'.format(i+1, nb_unit_stays))
        stay_id_str = str(stay_id).strip()
        dn = os.path.join(data_path, 'patients', stay_id_str)
        try:
            os.makedirs(dn)
        except:
            pass
        adm.loc[adm.ICUSTAY_ID == stay_id_str].to_csv(os.path.join(dn, 'admission.csv'), index=False)
    if verbose:
        sys.stdout.write('DONE!\n')

stay_id_Adm = cohort_stay_id(adm_pat_icu)
break_up_admission_by_unit_stay(adm_pat_icu, data_path, stayid=stay_id_Adm, verbose=1)


# CHART
def break_up_chart_by_unit_stay(chart, data_path, stayid, verbose=1):
    unit_stays = stayid
    nb_unit_stays = len(unit_stays) if hasattr(unit_stays, '__len__') else unit_stays.shape[0]
    chart['ICUSTAY_ID'] = icustay_to_str(chart['ICUSTAY_ID'])
    for i, stay_id in enumerate(unit_stays):
        if verbose:
            sys.stdout.write('\rStayID {0} of {1}...'.format(i+1, nb_unit_stays))
        stay_id_str = str(stay_id).strip()
        dn = os.path.join(data_path, 'patients', stay_id_str)
        try:
            os.makedirs(dn)
        except:
            pass
        chart.loc[chart.ICUSTAY_ID == stay_id_str].to_csv(os.path.join(dn, 'chart.csv'), index=False)
    if verbose:
        sys.stdout.write('DONE!\n')

stay_id_chart = cohort_stay_id(chart)
break_up_chart_by_unit_stay(chart, data_path, stayid=stay_id_chart, verbose=1)

# ICU - LAB
def break_up_icu_lab_by_unit_stay(icu_lab, data_path, stayid, verbose=1):
    unit_stays = stayid
    nb_unit_stays = len(unit_stays) if hasattr(unit_stays, '__len__') else unit_stays.shape[0]
    icu_lab['ICUSTAY_ID'] = icustay_to_str(icu_lab['ICUSTAY_ID'])
    for i, stay_id in enumerate(unit_stays):
        if verbose:
            sys.stdout.write('\rStayID {0} of {1}...'.format(i+1, nb_unit_stays))
        stay_id_str = str(stay_id).strip()
        dn = os.path.join(data_path, 'patients', stay_id_str)
        try:
            os.makedirs(dn)
        except:
            pass
        icu_lab.loc[icu_lab.ICUSTAY_ID == stay_id_str].to_csv(os.path.join(dn, 'icu_lab.csv'), index=False)
    if verbose:
        sys.stdout.write('DONE!\n')

stay_id_icu_lab = cohort_stay_id(icu_lab)
break_up_icu_lab_by_unit_stay(icu_lab, data_path, stayid=stay_id_icu_lab, verbose=1)

# ICU - DRUGS
def break_up_icu_drugs_by_unit_stay(icu_drugs, data_path, stayid, verbose=1):
    unit_stays = stayid
    nb_unit_stays = len(unit_stays) if hasattr(unit_stays, '__len__') else unit_stays.shape[0]
    icu_drugs['ICUSTAY_ID'] = icustay_to_str(icu_drugs['ICUSTAY_ID'])
    for i, stay_id in enumerate(unit_stays):
        if verbose:
            sys.stdout.write('\rStayID {0} of {1}...'.format(i+1, nb_unit_stays))
        stay_id_str = str(stay_id).strip()
        dn = os.path.join(data_path, 'patients', stay_id_str)
        try:
            os.makedirs(dn)
        except:
            pass
        icu_drugs.loc[icu_drugs.ICUSTAY_ID == stay_id_str].to_csv(os.path.join(dn, 'icu_drugs.csv'), index=False)
    if verbose:
        sys.stdout.write('DONE!\n')

stay_id_icu_drugs = cohort_stay_id(icu_drugs)
break_up_icu_drugs_by_unit_stay(icu_drugs, data_path, stayid=stay_id_icu_drugs, verbose=1)

# ICU - DELIRIUM
def break_up_icu_delirium_by_unit_stay(icu_delirium, data_path, stayid, verbose=1):
    unit_stays = stayid
    nb_unit_stays = len(unit_stays) if hasattr(unit_stays, '__len__') else unit_stays.shape[0]
    icu_delirium['ICUSTAY_ID'] = icustay_to_str(icu_delirium['ICUSTAY_ID'])
    for i, stay_id in enumerate(unit_stays):
        if verbose:
            sys.stdout.write('\rStayID {0} of {1}...'.format(i+1, nb_unit_stays))
        stay_id_str = str(stay_id).strip()
        dn = os.path.join(data_path, 'patients', stay_id_str)
        try:
            os.makedirs(dn)
        except:
            pass
        icu_delirium.loc[icu_delirium.ICUSTAY_ID == stay_id_str].to_csv(os.path.join(dn, 'icu_delirium.csv'), index=False)
    if verbose:
        sys.stdout.write('DONE!\n')

stay_id_icu_delirium = cohort_stay_id(icu_delirium)
break_up_icu_delirium_by_unit_stay(icu_delirium, data_path, stayid=stay_id_icu_delirium, verbose=1)

# ALL TABLES
def break_up_all_tables_by_unit_stay(all_tables, data_path, stayid, verbose=1):
    unit_stays = stayid
    nb_unit_stays = len(unit_stays) if hasattr(unit_stays, '__len__') else unit_stays.shape[0]
    all_tables['ICUSTAY_ID'] = icustay_to_str(all_tables['ICUSTAY_ID'])
    for i, stay_id in enumerate(unit_stays):
        if verbose:
            sys.stdout.write('\rStayID {0} of {1}...'.format(i+1, nb_unit_stays))
        stay_id_str = str(stay_id).strip()
        dn = os.path.join(data_path, 'patients', stay_id_str)
        try:
            os.makedirs(dn)
        except:
            pass
        all_tables.loc[all_tables.ICUSTAY_ID == stay_id_str].to_csv(os.path.join(dn, 'all_tables.csv'), index=False)
    if verbose:
        sys.stdout.write('DONE!\n')

stay_id_all_tables = cohort_stay_id(all_tables)
break_up_all_tables_by_unit_stay(all_tables, data_path, stayid=stay_id_all_tables, verbose=1)

# %%
# Extract Time Series
all_variables = list(all_tables.LABEL.unique())

print(f"All variables: {all_variables}")

# %%
def filter_on_variabels(all_tables, all_variables):
    all_tables = all_tables[all_tables['LABEL'].isin(all_variables)]
    return all_tables

def convert_events_to_timeseries(all_features, all_variables):
    metadata  = all_features[['CHARTTIME', 'ICUSTAY_ID']].sort_values(by=['CHARTTIME'])\
                    .drop_duplicates(keep='first').set_index('CHARTTIME')
    timeserie = all_features[['CHARTTIME', 'LABEL', 'VALUE']]\
                    .sort_values(by=['CHARTTIME'], axis=0)\
                    .drop_duplicates(subset=['CHARTTIME', 'LABEL'], keep='last')
    time_piv  = timeserie.pivot(index='CHARTTIME', columns='LABEL', values='VALUE')
    timeseries = time_piv.merge(metadata, left_index=True, right_index=True).sort_index(axis=0).reset_index()
    for v in all_variables:
        if v not in timeseries.columns:
            timeseries[v] = np.nan
    return timeseries

def binning(final, x=60):
    final.CHARTTIME = parse_datetime_kmimic(final.CHARTTIME)
    if 'INTIME' not in final.columns:
        raise ValueError("INTIME column not found in final DataFrame. Required for binning.")
    final.INTIME = parse_datetime_kmimic(final.INTIME)
    final['HOURS'] = (final.CHARTTIME - final.INTIME).apply(lambda s: s / np.timedelta64(1, 's')) / 60./60
    # Keep CHARTTIME until after RASS fill; needed to preserve temporal ordering if we use "last" in bin.
    drop_cols = ['SUBJECT_ID', 'HADM_ID', 'INTIME', 'OUTTIME']
    final.drop(columns=[c for c in drop_cols if c in final.columns], inplace=True)
    final['MINUTES'] = (final.HOURS).apply(lambda s: s * 60)
    final['BIN'] = (final['MINUTES']/ x).astype(int)

  # BIN < 0 제거 (CHARTTIME < INTIME인 ICU 입실 전 데이터)
    final = final[final['BIN'] >= 0]

    numeric_cols = final.select_dtypes(include=[np.number]).columns.tolist()
    if 'BIN' in numeric_cols:
        numeric_cols.remove('BIN')
    if 'MINUTES' in numeric_cols:
        numeric_cols.remove('MINUTES')
    if 'HOURS' in numeric_cols:
        numeric_cols.remove('HOURS')

    if len(numeric_cols) > 0:
        # IMPORTANT: Don't mean-impute RASS; it must remain an integer in [-5, 4].
        mean_impute_cols = [c for c in numeric_cols if c != 'RASS']
        if len(mean_impute_cols) > 0:
            numeric_filled = final[mean_impute_cols].fillna(
                final.groupby(['BIN'])[mean_impute_cols].transform('mean')
            )
            final[mean_impute_cols] = numeric_filled

    # RASS: fill within BIN using last observed value (preserves integer),
    # then force integer range [-5, 4].
    if 'RASS' in final.columns:
        final = final.sort_values(by=['CHARTTIME'])
        final['RASS'] = pd.to_numeric(final['RASS'], errors='coerce')
        final['RASS'] = final['RASS'].fillna(final.groupby('BIN')['RASS'].transform('last'))
        final['RASS'] = (
            np.rint(final['RASS'])
            .clip(-5, 4)
            .astype('Int64')
        )

    object_cols = final.select_dtypes(include=['object']).columns.tolist()
    if len(object_cols) > 0:
        final[object_cols] = final[object_cols].ffill().bfill()

    final.drop(columns=[c for c in ['CHARTTIME'] if c in final.columns], inplace=True)
    final.drop_duplicates(subset=['BIN'], keep='last',inplace=True)
    return final


patients_path = os.path.join(data_path, 'patients')
print(f"Number of stay directories: {len(os.listdir(patients_path))}")

# %%
def extract_time_series_from_subject(data_path, all_variables):
    patients_dir = os.path.join(data_path, 'patients')
    success_count = 0
    error_count = 0
    filtered_rass_count = 0
    for stay_dir in os.listdir(patients_dir):
        dn = os.path.join(patients_dir, stay_dir)
        if not os.path.isdir(dn):
            continue
        try:
            sys.stdout.flush()

            # Remove stale output from previous runs so filtered stays don't get included accidentally.
            stale_ts = os.path.join(dn, 'timeseries.csv')
            if os.path.isfile(stale_ts):
                os.remove(stale_ts)

            admission_path = os.path.join(dn, 'admission.csv')
            all_tables_path = os.path.join(dn, 'all_tables.csv')
            if not os.path.isfile(admission_path) or not os.path.isfile(all_tables_path):
                continue

            admission  = dataframe_from_csv(admission_path)
            all_tables = dataframe_from_csv(all_tables_path)
            all_tables = filter_on_variabels(all_tables, all_variables)

            if len(all_tables) == 0:
                continue

            all_features = all_tables.sort_values(by=['CHARTTIME'])
            timeepisode  = convert_events_to_timeseries(all_features, all_variables)

            admission['ICUSTAY_ID'] = icustay_to_str(admission['ICUSTAY_ID'])
            timeepisode['ICUSTAY_ID'] = icustay_to_str(timeepisode['ICUSTAY_ID'])

            final  = pd.merge(timeepisode, admission, on='ICUSTAY_ID', how='inner')
            if len(final) == 0:
                continue

            final  = final.sort_values(by=['CHARTTIME'])
            df_bin = binning(final, 60)

            # Patient filtering rule:
            # Keep only stays with RASS scores >= -1 (exclude deeper sedation).
            # If RASS is entirely missing for the stay, exclude it as well.
            if 'RASS' in df_bin.columns:
                rass_series = pd.to_numeric(df_bin['RASS'], errors='coerce').dropna()
                if rass_series.empty or (rass_series < -1).any():
                    filtered_rass_count += 1
                    continue

            df_bin.to_csv(os.path.join(dn, 'timeseries.csv'), index=False)
            sys.stdout.write('\rWrite StayID {0}...\n'.format(stay_dir))
            if not os.path.isfile(os.path.join(dn,'timeseries.csv')):
                error_count += 1
                continue
            success_count += 1
        except Exception as e:
            error_count += 1
            sys.stdout.write('\rError processing StayID {0}: {1}\n'.format(stay_dir, str(e)))
            continue
    print(f'DONE: {success_count} successful, {error_count} errors, {filtered_rass_count} filtered by RASS<-1')

extract_time_series_from_subject(data_path, all_variables)

# %%
def extract_time_series_from_subject(data_path, all_variables):
    patients_dir = os.path.join(data_path, 'patients')
    success_count = 0
    error_count = 0
    filtered_rass_count = 0
    for stay_dir in os.listdir(patients_dir):
        dn = os.path.join(patients_dir, stay_dir)
        if not os.path.isdir(dn):
            continue
        try:
            sys.stdout.flush()

            # Remove stale output from previous runs so filtered stays don't get included accidentally.
            stale_ts = os.path.join(dn, 'timeseries.csv')
            if os.path.isfile(stale_ts):
                os.remove(stale_ts)

            admission_path = os.path.join(dn, 'admission.csv')
            all_tables_path = os.path.join(dn, 'all_tables.csv')
            if not os.path.isfile(admission_path) or not os.path.isfile(all_tables_path):
                continue

            admission  = dataframe_from_csv(admission_path)
            all_tables = dataframe_from_csv(all_tables_path)
            all_tables = filter_on_variabels(all_tables, all_variables)

            if len(all_tables) == 0:
                continue

            all_features = all_tables.sort_values(by=['CHARTTIME'])
            timeepisode  = convert_events_to_timeseries(all_features, all_variables)

            admission['ICUSTAY_ID'] = icustay_to_str(admission['ICUSTAY_ID'])
            timeepisode['ICUSTAY_ID'] = icustay_to_str(timeepisode['ICUSTAY_ID'])

            final  = pd.merge(timeepisode, admission, on='ICUSTAY_ID', how='inner')
            if len(final) == 0:
                continue

            final  = final.sort_values(by=['CHARTTIME'])
            df_bin = binning(final, 60)

            # Patient filtering rule:
            # Keep only stays with RASS scores >= -1 (exclude deeper sedation).
            # If RASS is entirely missing for the stay, exclude it as well.
            if 'RASS' in df_bin.columns:
                rass_series = pd.to_numeric(df_bin['RASS'], errors='coerce').dropna()
                if rass_series.empty or (rass_series < -1).any():
                    filtered_rass_count += 1
                    continue

            df_bin.to_csv(os.path.join(dn, 'timeseries.csv'), index=False)
            sys.stdout.write('\rWrite StayID {0}...\n'.format(stay_dir))
            if not os.path.isfile(os.path.join(dn,'timeseries.csv')):
                error_count += 1
                continue
            success_count += 1
        except Exception as e:
            error_count += 1
            sys.stdout.write('\rError processing StayID {0}: {1}\n'.format(stay_dir, str(e)))
            continue
    print(f'DONE: {success_count} successful, {error_count} errors, {filtered_rass_count} filtered by RASS<-1')

extract_time_series_from_subject(data_path, all_variables)

def delete_wo_timeseries(t_path):
    patients_dir = os.path.join(t_path, 'patients')
    for stay_dir in os.listdir(patients_dir):
        dn = os.path.join(patients_dir, stay_dir)
        if not os.path.isdir(dn):
            continue
        try:
            sys.stdout.flush()
            if not os.path.isfile(os.path.join(dn, 'timeseries.csv')):
                shutil.rmtree(dn)
        except:
            continue
    print('DONE deleting')

delete_wo_timeseries(data_path)

print(f"Number of stay directories after cleanup: {len(os.listdir(patients_path))}")

all_stays  = pd.Series(os.listdir(patients_path))
all_filenames = []
for stay_id in (all_stays):
    dn = os.path.join(patients_path, stay_id)
    if not os.path.isdir(dn):
        continue
    df_file = os.path.join(dn, 'timeseries.csv')
    if os.path.isfile(df_file):
        all_filenames.append(df_file)

print(f"Found {len(all_filenames)} timeseries files to combine")

if len(all_filenames) == 0:
    print("WARNING: No timeseries files found. Cannot create combined CSV.")
    print("Please check if extract_time_series_from_subject completed successfully.")
else:
    combined_csv = pd.concat([pd.read_csv(f) for f in all_filenames])
    out_file = os.path.join(path_csv, 'all_data_delirium_mimic.csv')
    combined_csv.to_csv(out_file, index=False)
    print(f"Combined CSV saved: {len(combined_csv)} rows, {len(combined_csv.columns)} columns")
    print(f"Combined CSV path: {out_file}")
    print(f"Combined CSV exists after save: {os.path.isfile(out_file)}")
    print("Data extraction completed successfully!")

# %%

# %%


# %%


# %%


# %%


# %%


# %%


# %%


# %%
