# %%
# %%
import pandas as pd
import csv
import sys
import os

import numpy as np
import shutil

pd.set_option('display.max_columns', 500)
pd.set_option('display.max_rows', 500)

# %%
mimic_path = ""
data_processed_path = "/home/coder/workspace/src/hjkim/Data/preprocessed/"

all_data_deli = pd.read_csv(os.path.join(data_processed_path, str(374), 'all_data_delirium_mimic.csv'))
for i in range(375, 415):
    try:
        temp = pd.read_csv(os.path.join(data_processed_path, str(i), 'all_data_delirium_mimic.csv'))
        all_data_deli = pd.concat([all_data_deli, temp])
    except:
        pass

print(f"GENDER value counts:\n{all_data_deli['GENDER'].value_counts()}")

# %%
for i in all_data_deli.columns:
    print(i)

# %%
col_order = ['ICUSTAY_ID', 'BIN', 'HOURS', 'AGE', 'GENDER', 'Body height', 'Body weight', 'oxygen saturation', 'Heart rate', 'Body temperature', 'WBC', 'Glucose', 'Diastolic blood pressure', 'Systolic blood pressure', 'Mean blood pressure', 'Respiratory rate', 'Hemoglobin', 'BUN', 'Sodium', 'Potassium', 'Osmolality', 'FiO2', 'pH', 'PaCO2', 'PaO2', 'Ammonia', 'ICP', 'Cortisol', 'Sedative drugs', 'Opiate drugs', 'Benzodiazepine drugs', 'Asthenia (finding)', 'Delirium (disorder)', 'Hyperirritability (finding)', 'Feeling agitated (finding)', 'Feeling irritable (finding)', 'Fluctuation of level of consciousness (finding)', 'Disorientated in time (finding)', 'Aggressive behavior (finding)', 'Disorientated in place (finding)', 'Difficulty sleeping (finding)', 'Disorientation for person (finding)', 'Incoherent speech (finding)', 'Sleep disorder (disorder)', 'Memory impairment (finding)', 'Disorientated (finding)', 'Insomnia (disorder)', 'Drowsy (finding)', 'Difficulty communicating (finding)', 'Finding of shouting (finding)', 'LOS', 'RASS', 'CAM-ICU']

all_data_deli = all_data_deli[col_order]

print(f"All data deli unique ICUSTAY_ID: {all_data_deli.groupby(['ICUSTAY_ID']).head(1).shape}")

# %%
# CAM Positive selection
#Positive CAM-ICU
cam_pos = all_data_deli[all_data_deli['CAM-ICU']==1]

#Statistics of dataset
print("ICU Stays with CAM positive {0}" .format(cam_pos.ICUSTAY_ID.nunique()))
print("Unique ICU Stays {0} \n" .format(all_data_deli.ICUSTAY_ID.nunique()))

print("No. of records with CAM positive {0}" .format(cam_pos.shape[0]))
print("Total No. of records {0}" .format(all_data_deli.shape[0]))

# %%
pos_id = cam_pos.ICUSTAY_ID.unique()
cam_pos_df = all_data_deli[all_data_deli['ICUSTAY_ID'].isin(pos_id)]

# %%
all_data_deli['CAM-ICU'] = all_data_deli['CAM-ICU'].fillna(value=0)
print(f"CAM value counts:\n{all_data_deli['CAM-ICU'].value_counts()}")

print(f"All data deli columns: {all_data_deli.columns}")


# %%
all_data_deli['Body weight']
print(f"PATIENTWEIGHT and Weight describe:\n{all_data_deli[['Body weight']].describe()}")

# %%
print(f"BIN describe:\n{all_data_deli.BIN.describe()}")

print(f"BIN < 0 shape: {all_data_deli[all_data_deli.BIN < 0].shape}")

# %%
data_copy  = all_data_deli.copy()

data_copy.rename(columns={"ICUSTAY_ID": "patientunitstayid", "BIN": "itemoffset",
                          "GENDER": "gender", "AGE": "age", "Body height": "admissionheight", "Body weight": "admissionweight",
                         "Heart rate": "Heart Rate","oxygen saturation": "O2 Saturation", "Glucose": "glucose", "Body temperature": "Temperature (C)",
                         "Sodium": "sodium","BUN": "BUN","WBC": "WBC x 1000",
                         "Bilirubin": "direct bilirubin"},inplace=True)

# %%
def check(x):
    try:
        x = float(str(x).strip())
    except:
        x = np.nan
    return x

def check_itemvalue(df):
    for c in df.columns:
        df[c] = df[c].apply(lambda x: check(x))
    return df

# %%
# labelling
print(f"Data copy columns: {data_copy.columns}")

# %%
order_columns = ['patientunitstayid','itemoffset', 'HOURS',
       'gender', 'age', 'admissionheight',
       'admissionweight', 'Heart Rate', 'O2 Saturation', 'glucose', 'Temperature (C)',
       'WBC x 1000', 'Diastolic blood pressure',
       'Systolic blood pressure', 'Mean blood pressure', 'Respiratory rate',
       'Hemoglobin', 'BUN', 'sodium', 'Potassium', 'Osmolality', 'FiO2', 'pH',
       'PaCO2', 'PaO2', 'Ammonia', 'ICP', 'Cortisol', 'Sedative drugs',
       'Opiate drugs', 'Benzodiazepine drugs',
       'Delirium (disorder)',
       'Hyperirritability (finding)', 'Feeling agitated (finding)',
       'Feeling irritable (finding)',
       'Fluctuation of level of consciousness (finding)',
       'Disorientated in time (finding)', 'Aggressive behavior (finding)',
       'Disorientated in place (finding)', 'Difficulty sleeping (finding)',
       'Disorientation for person (finding)', 'Incoherent speech (finding)',
       'Sleep disorder (disorder)', 'Memory impairment (finding)',
       'Disorientated (finding)', 'Insomnia (disorder)', 
       'Asthenia (finding)', 'Drowsy (finding)',
       'Difficulty communicating (finding)', 'Finding of shouting (finding)',
       'LOS', 'RASS', 'CAM-ICU']

data_copy = data_copy[data_copy['itemoffset'] > -7]
label_deli = data_copy.copy()
label_deli['labelrec'] = np.nan
label_deli.loc[label_deli['CAM-ICU']==1,'labelrec']=1
label_deli.loc[label_deli['CAM-ICU']==0,'labelrec']=0
label_deli['labelpt'] = np.nan
pos_cam_coh = label_deli[label_deli['labelrec']==1]['patientunitstayid'].unique()
label_deli.loc[label_deli['patientunitstayid'].isin(pos_cam_coh), 'labelpt']=1
label_deli.loc[~(label_deli['patientunitstayid'].isin(pos_cam_coh)), 'labelpt']=0

print(f"Label deli groupby patientunitstayid count: {label_deli.groupby('patientunitstayid').count().shape}")

# %%
new_df = label_deli[order_columns]

# %%
## Imputation patient wise for weight and height
for i in ['admissionheight','admissionweight']:
    new_df[i] = new_df.groupby("patientunitstayid")[i].transform(lambda v: v.ffill())
    new_df[i] = new_df.groupby("patientunitstayid")[i].transform(lambda v: v.bfill())

# %%
# Missing values
## record-wise
import missingno as msno
import seaborn as sns
import matplotlib.pyplot as plt
columns = order_columns
sel = new_df.loc[:, columns]
percent_missing = sel.isnull().mean() * 100
missing_value_df = percent_missing.reset_index()
missing_value_df.columns = ["column_name", "percent_missing"]
missing_value_df.sort_values('percent_missing', inplace=True)
missing_value_df.reset_index(inplace=True, drop=True)
print(f"Missing value df:\n{missing_value_df}")

# %%
## Patient-wise
df_g = sel.groupby("patientunitstayid").apply(lambda x: x.notnull().mean())

for i in df_g.columns:
    df_g[i] = df_g[i].replace({0:np.nan})

columns = df_g.columns
percent_missing = df_g.isnull().sum() * 100 / len(df_g)
missing_value_df = pd.DataFrame({'column_name': columns,'percent_missing': percent_missing})
missing_value_df.sort_values('percent_missing', inplace=True)
missing_value_df.reset_index(inplace=True, drop=True)
print(f"Missing value df after imputation:\n{missing_value_df}")

# %%
# %%
# Binary indicator columns (time-specific): if a value exists at that time => 1, else 0.
# IMPORTANT: Do NOT forward/back-fill these columns across time.
def _cols_between(col_list, start_name, end_name):
    if start_name not in col_list or end_name not in col_list:
        return []
    i0 = col_list.index(start_name)
    i1 = col_list.index(end_name)
    if i0 > i1:
        i0, i1 = i1, i0
    return col_list[i0 : i1 + 1]

binary_indicator_cols = _cols_between(
    order_columns,
    "Sedative drugs",
    "Finding of shouting (finding)",
)

def _to_binary_indicator(df, cols):
    existing = [c for c in cols if c in df.columns]
    for c in existing:
        s = pd.to_numeric(df[c], errors="coerce")
        df[c] = (s.fillna(0) != 0).astype("int8")
    return df

new_df = _to_binary_indicator(new_df, binary_indicator_cols)
new_df = _to_binary_indicator(new_df, ["FiO2"])

# %%
# Imputation (based on your `order_columns`; no SOFA / epinephrine / vasopressor logic)
work_df = new_df.copy()

# 1) Binary indicators: keep time-specific and already 0/1
work_df = _to_binary_indicator(work_df, binary_indicator_cols)
work_df = _to_binary_indicator(work_df, ["FiO2"])

# 2) Patient-wise forward/back fill for numeric time-series columns (exclude binary indicators)
id_cols = ["patientunitstayid", "itemoffset", "HOURS"]
static_cols = ["gender", "age", "admissionheight", "admissionweight"]
label_cols = ["CAM-ICU", "labelrec", "labelpt"]
fio2_indicator_cols = [c for c in ["FiO2"] if c in work_df.columns]
exclude_cols = set(id_cols + static_cols + label_cols + binary_indicator_cols + fio2_indicator_cols)

time_numeric_cols = [c for c in order_columns if c in work_df.columns and c not in exclude_cols]

for c in time_numeric_cols:
    work_df[c] = pd.to_numeric(work_df[c], errors="coerce")
    work_df[c] = work_df.groupby("patientunitstayid")[c].transform(lambda v: v.ffill())
    work_df[c] = work_df.groupby("patientunitstayid")[c].transform(lambda v: v.bfill())

# 3) Static columns
if "gender" in work_df.columns:
    work_df["gender"] = work_df.groupby("patientunitstayid")["gender"].transform(
        lambda s: s.ffill().bfill()
    )
    if work_df["gender"].isnull().any():
        work_df["gender"] = work_df["gender"].fillna(work_df["gender"].mode(dropna=True).iloc[0])

for c in ["age", "admissionheight", "admissionweight"]:
    if c in work_df.columns:
        work_df[c] = pd.to_numeric(work_df[c], errors="coerce")
        work_df[c] = work_df[c].fillna(work_df.groupby("patientunitstayid")[c].transform("mean"))
        work_df[c] = work_df[c].fillna(work_df[c].mean())

# 4) Final fill to ensure no missing values in feature columns
for c in order_columns:
    if c not in work_df.columns:
        continue
    if c in binary_indicator_cols:
        work_df[c] = work_df[c].fillna(0).astype("int8")
        continue
    if c in fio2_indicator_cols:
        work_df[c] = work_df[c].fillna(0).astype("int8")
        continue
    if c in id_cols:
        continue
    if c in ["CAM-ICU"]:
        work_df[c] = pd.to_numeric(work_df[c], errors="coerce").fillna(0)
        continue
    s = pd.to_numeric(work_df[c], errors="coerce")
    if s.notnull().any():
        work_df[c] = s.fillna(s.mean())
    else:
        work_df[c] = work_df[c].fillna(0)

# 5) LOS merge/filter
work_df = work_df[work_df["LOS"] >= 9]
work_df = work_df[work_df["itemoffset"] > 0]
new_df_los_nodups = work_df.drop_duplicates()

print(f"New df los nodups shape: {new_df_los_nodups.shape}")
print(f"New df los nodups patientunitstayid nunique: {new_df_los_nodups.patientunitstayid.nunique()}")

# %%
### split CAM pos and CAM neg
label_deli = new_df_los_nodups.copy()
label_deli['labelrec'] = np.nan
label_deli.loc[label_deli['CAM-ICU']==1,'labelrec']=1
label_deli.loc[label_deli['CAM-ICU']==0,'labelrec']=0
label_deli['labelpt'] = np.nan

pos_cam_coh = label_deli[label_deli['labelrec']==1]['patientunitstayid'].unique()
label_deli.loc[label_deli['patientunitstayid'].isin(pos_cam_coh), 'labelpt']=1
label_deli.loc[~(label_deli['patientunitstayid'].isin(pos_cam_coh)), 'labelpt']=0

print(f"Label deli tail:\n{label_deli.tail(1)}")

# %%
pos_cam_df = label_deli[label_deli['labelpt']==1].copy()
neg_cam_df = label_deli[label_deli['labelpt']==0].copy()
pos_cam_df = pos_cam_df.reset_index(drop=True)
neg_cam_df = neg_cam_df.reset_index(drop=True)

print(f"Pos cam df patientunitstayid nunique: {pos_cam_df['patientunitstayid'].nunique()}, Neg cam df patientunitstayid nunique: {neg_cam_df['patientunitstayid'].nunique()}")

# %%
neg_cam_df['CAM'] = neg_cam_df['labelpt']
pos_cam_df['CAM'] = pos_cam_df['labelpt']

pos_cam_df.to_csv(os.path.join(data_processed_path, 'pos_mimic_imputed_24los.csv'), index=False)
neg_cam_df.to_csv(os.path.join(data_processed_path, 'neg_mimic_imputed_24los.csv'), index=False)

mimic_df = pd.concat([neg_cam_df, pos_cam_df],axis=0)

print(f"Mimic df patientunitstayid nunique: {mimic_df.patientunitstayid.nunique()}")

print("Data preprocessing completed successfully!")
