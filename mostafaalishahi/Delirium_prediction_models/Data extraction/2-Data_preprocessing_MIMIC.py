# %%
import pandas as pd
import csv
import sys
import os

import numpy as np
import shutil
pd.set_option('display.max_columns', 500)
pd.set_option('display.max_rows', 500)

mimic_path = "C:\\Users\\김한재\\Desktop\\ONEASH_local\\Delirium-Prediction\\mostafaalishahi\\Delirium_prediction_models\\Data\\mimic-iii-clinical-database-1.4"
root_path = "the directory that includes the main csv data"
data_processed_path = "C:\\Users\\김한재\\Desktop\\ONEASH_local\\Delirium-Prediction\\mostafaalishahi\\Delirium_prediction_models\\Data\\preprocessed"
all_data_deli = pd.read_csv(os.path.join(data_processed_path, 'all_data_delirium_mimic.csv'))

print(f"GENDER value counts:\n{all_data_deli['GENDER'].value_counts()}")

all_data_deli.loc[all_data_deli['CAM-ICU MS change'].notnull(),'CAM-ICU MS Change'] = all_data_deli['CAM-ICU MS change']

col_order = ['ICUSTAY_ID','BIN','HOURS','AGE', 'GENDER', 'Height','Weight','PATIENTWEIGHT',
             'Oxygen Saturation', 'Heart Rate','Temperature C', 'Temperature F','WBC',
             'Sodium','BUN','Glucose','direct bilirubin','Hemoglobin','Platelets',
             'Potassium','Chloride','Bicarbonate','Creatinine','ALT','AST','Alkaline Phosphate',
             'Delirium assessment','CAM-ICU MS Change','CAM-ICU Inattention','CAM-ICU Altered LOC',
             'CAM-ICU Disorganized thinking', 
             'CAM-ICU RASS LOC']

all_data_deli = all_data_deli[col_order]

print(f"All data deli head:\n{all_data_deli.head(1)}")
print(f"All data deli unique ICUSTAY_ID: {all_data_deli.groupby(['ICUSTAY_ID']).head(1).shape}")

# CAM Positive selection
#Positive CAM-ICU
feature1_pos = all_data_deli['CAM-ICU MS Change']==1
feature2_pos = (all_data_deli['CAM-ICU Inattention']==1) | (all_data_deli['CAM-ICU Inattention']==4)
feature3_pos = all_data_deli['CAM-ICU Altered LOC']==1
feature4_pos = all_data_deli['CAM-ICU Disorganized thinking']==1
cam_pos = all_data_deli[(feature1_pos&feature2_pos)&(feature3_pos|feature4_pos)]

cam_pos = all_data_deli[(feature1_pos&feature2_pos)&(feature3_pos|feature4_pos)]

print(f"Feature sums: {feature1_pos.sum()}, {feature2_pos.sum()}, {feature3_pos.sum()}, {feature4_pos.sum()}")

#Statistics of dataset
print("ICU Stays with CAM positive {0}" .format(cam_pos.ICUSTAY_ID.nunique()))
print("Unique ICU Stays {0} \n" .format(all_data_deli.ICUSTAY_ID.nunique()))

print("No. of records with CAM positive {0}" .format(cam_pos.shape[0]))
print("Total No. of records {0}" .format(all_data_deli.shape[0]))

pos_id = cam_pos.ICUSTAY_ID.unique()
cam_pos_df = all_data_deli[all_data_deli['ICUSTAY_ID'].isin(pos_id)]
all_data_deli['CAM'] = np.nan
print(f"Positive features sum: {((feature1_pos&feature2_pos)&(feature3_pos|feature4_pos)).sum()}")

all_data_deli.loc[((feature1_pos&feature2_pos)&(feature3_pos|feature4_pos)),'CAM']=1
all_data_deli['CAM'] = all_data_deli['CAM'].fillna(value=0)
print(f"CAM value counts:\n{all_data_deli['CAM'].value_counts()}")

print(f"All data deli columns: {all_data_deli.columns}")

all_data_deli.loc[all_data_deli['Weight'].notnull(),'PATIENTWEIGHT'] = all_data_deli['Weight']

def fahr_to_celsius(temp_fahr):
    """Convert Fahrenheit to Celsius
    Return Celsius conversion of input"""
    temp_celsius = (temp_fahr - 32) * 5 / 9
    return temp_celsius

print(f"Temperature F describe:\n{all_data_deli['Temperature F'].describe()}")

all_data_deli["Temperature F"] = fahr_to_celsius(all_data_deli["Temperature F"])

print(f"Temperature F describe after conversion:\n{all_data_deli['Temperature F'].describe()}")

all_data_deli.loc[all_data_deli['Temperature F'].notnull(),'Temperature C'] = all_data_deli['Temperature F']

print(f"Temperature F and C describe:\n{all_data_deli[['Temperature F','Temperature C']].describe()}")

print(f"PATIENTWEIGHT and Weight describe:\n{all_data_deli[['PATIENTWEIGHT','Weight']].describe()}")

print(f"All data deli head:\n{all_data_deli.head()}")

print(f"BIN describe:\n{all_data_deli.BIN.describe()}")

print(f"BIN < 0 shape: {all_data_deli[all_data_deli.BIN < 0].shape}")

data_copy  = all_data_deli.copy()

print(f"Data copy head:\n{data_copy.head()}")

data_copy.rename(columns={"ICUSTAY_ID": "patientunitstayid", "BIN": "itemoffset",
                          "GENDER": "gender","AGE": "age","Height": "admissionheight","PATIENTWEIGHT": "admissionweight",
                         "Heart Rate": "Heart Rate","Oxygen Saturation": "O2 Saturation","Glucose": "glucose","Temperature C": "Temperature (C)",
                         "Sodium": "sodium","BUN": "BUN","WBC": "WBC x 1000",
                         "Bilirubin": "direct bilirubin"},inplace=True)

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

# labelling
print(f"Data copy columns: {data_copy.columns}")

order_columns = ['patientunitstayid','itemoffset', 
       'gender', 'age', 'admissionheight',
       'admissionweight', 'Heart Rate', 'O2 Saturation', 'glucose', 'Temperature (C)',
       'sodium','BUN', 'WBC x 1000', 'direct bilirubin',
       'Hemoglobin','Platelets','Potassium', 'Chloride', 'Bicarbonate', 'Creatinine',
       'ALT', 'AST', 'Alkaline Phosphate','CAM']

data_copy = data_copy[data_copy['itemoffset'] > -7]
label_deli = data_copy.copy()
label_deli['labelrec'] = np.nan
label_deli.loc[label_deli['CAM']==1,'labelrec']=1
label_deli.loc[label_deli['CAM']==0,'labelrec']=0
label_deli['labelpt'] = np.nan
pos_cam_coh = label_deli[label_deli['labelrec']==1]['patientunitstayid'].unique()
label_deli.loc[label_deli['patientunitstayid'].isin(pos_cam_coh), 'labelpt']=1
label_deli.loc[~(label_deli['patientunitstayid'].isin(pos_cam_coh)), 'labelpt']=0

print(f"Label deli groupby patientunitstayid count: {label_deli.groupby('patientunitstayid').count().shape}")

# Add Sofa score to dataframe
data_copy = label_deli[order_columns]
df_mimic = data_copy.copy()
sofa = pd.read_csv(os.path.join(data_processed_path, 'mimic_pivoted_sofa.csv'))
df_mimic['day'] = np.nan
for i in range(-7,1000):
    df_mimic.loc[((df_mimic['itemoffset'] <= i*24) & (df_mimic['itemoffset'] >= (i-1)*24)),'day'] = i  
sofa.rename(columns={'icustay_id':'patientunitstayid'},inplace=True)
set_sofa = set(sofa.patientunitstayid.unique())
set_mimic = set(df_mimic.patientunitstayid.unique())
inters = list(set_sofa.intersection(set_mimic))
print(f"Intersection length: {len(inters)}")
new_df = pd.merge(df_mimic, sofa, how='left', left_on=['patientunitstayid','day'],right_on=['patientunitstayid','day'])

print(f"New df head:\n{new_df.head()}")

print(f"New df columns: {new_df.columns}")

## Add other variables to dataframe
data_copy = new_df
df_mimic = data_copy.copy()
df_vent = pd.read_csv(os.path.join(data_processed_path, 'mimic_wes.csv'))
df_vent.rename(columns={'icustay_id':'patientunitstayid'},inplace=True)
new_df = pd.merge(df_mimic, df_vent, how='left',left_on=['patientunitstayid','itemoffset'],right_on=['patientunitstayid','hr'])

print(f"New df columns after vent merge: {new_df.columns}")

columns_order = ['patientunitstayid', 'itemoffset', 'gender', 'age', 'admissionheight',
       'admissionweight', 'Heart Rate', 'O2 Saturation', 'glucose',
       'Temperature (C)', 'sodium', 'BUN', 'WBC x 1000', 'direct bilirubin',
       'Hemoglobin', 'Platelets', 'Potassium', 'Chloride', 'Bicarbonate',
       'Creatinine', 'ALT', 'AST', 'Alkaline Phosphate', 'sofa', 'sofa_wo_gcs',
       'vent_flag','rate_dopamine', 'rate_epinephrine', 'rate_norepinephrine',
       'rate_phenylephrine', 'fluidin', 'fluidout','CAM']

new_df = new_df[columns_order]

## Imputation patient wise for weight and height
for i in ['admissionheight','admissionweight']:
    new_df[i] = new_df.groupby("patientunitstayid")[i].transform(lambda v: v.ffill())
    new_df[i] = new_df.groupby("patientunitstayid")[i].transform(lambda v: v.bfill())

# Missing values
## record-wise
import missingno as msno
import seaborn as sns
import matplotlib.pyplot as plt
columns = columns_order 
percent_missing = new_df[columns].isnull().sum() * 100 / len(new_df)
missing_value_df = pd.DataFrame({'column_name': columns,'percent_missing': percent_missing})
missing_value_df.sort_values('percent_missing', inplace=True)
missing_value_df.reset_index(inplace=True, drop=True)
print(f"Missing value df:\n{missing_value_df}")

## Patient-wise
df_g = new_df[columns_order].groupby("patientunitstayid").apply(lambda x: x.notnull().mean())

for i in df_g.columns:
    df_g[i] = df_g[i].replace({0:np.nan})

#after Imputation
import missingno as msno
import seaborn as sns
import matplotlib.pyplot as plt
columns = df_g.columns
percent_missing = df_g.isnull().sum() * 100 / len(df_g)
missing_value_df = pd.DataFrame({'column_name': columns,'percent_missing': percent_missing})
missing_value_df.sort_values('percent_missing', inplace=True)
missing_value_df.reset_index(inplace=True, drop=True)
print(f"Missing value df after imputation:\n{missing_value_df}")

# Correlation
new_df.rename(index=str, columns={"admissionheight": "Height",
                                  "admissionweight":"Weight",
                                  "glucose" : "Glucose",
                                  "sodium" : "Sodium",
                                  "vent_flag" : "Ventilation",
                                  "rate_dopamine" : "Dopamine",
                                  "rate_epinephrine" : "Epinephrine",
                                  "rate_norepinephrine":"Norepinephrine",
                                  "rate_phenylephrine":"Phenylephrine",
                                  "gender":"Gender",
                                  "sofa":"Sofa",
                                  "sofa_wo_gcs":"Sofa_wo_gcs",
                                  "Temperature (C)" : "Temperature",
                                  "WBC x 1000": "WBC",
                                  "age":"Age"}, inplace=True)

new_df['Epinephrine'] = new_df['Epinephrine'].fillna(value=0)
new_df['Norepinephrine'] = new_df['Norepinephrine'].fillna(value=0)
new_df['Phenylephrine'] = new_df['Phenylephrine'].fillna(value=0)
new_df['Dopamine'] = new_df['Dopamine'].fillna(value=0)

new_df['Vasopressor dose'] = np.nan
new_df['Vasopressor dose'] = new_df['Epinephrine']+new_df['Norepinephrine'] + new_df['Phenylephrine']/10 + new_df['Dopamine']/2
new_df.drop(columns=['Epinephrine', 'Norepinephrine','Phenylephrine','Dopamine'],inplace=True)

print(f"Vasopressor dose notnull sum: {new_df['Vasopressor dose'].notnull().sum()}")

columns_for_corr = ['Age', 'Height',
       'Weight', 'Heart Rate', 'O2 Saturation', 'Glucose',
       'Temperature', 'Sodium', 'BUN', 'WBC', 
       'Hemoglobin', 'Platelets', 'Potassium', 'Chloride', 'Bicarbonate',
       'Creatinine','Ventilation','Vasopressor dose','Gender','Sofa', 'Sofa_wo_gcs',  'CAM']

print(f"Columns for corr: {new_df[columns_for_corr].columns}")

import seaborn as sns
import matplotlib.pyplot as plt

colormap = plt.cm.RdBu

mask = np.zeros(new_df[columns_for_corr].corr().shape, dtype=bool)
mask[np.tril_indices(len(mask))] = True
mask = ~mask

plt.figure(figsize=(10,10))

sns.set(font_scale=1.4)
plt.title('Pearson Correlation of Features', y=1.05, size=15)

sns.heatmap(new_df[columns_for_corr].corr(), mask = mask, linewidths=0.1,vmax=1.0, square=True, cmap=colormap, linecolor='white', annot=False)

plt.savefig('mimic_corr.png',dpi=450, facecolor='white', bbox_inches = 'tight',transparent=True)
plt.show()

# Save not imputed data
los = pd.read_csv(os.path.join(mimic_path, 'ICUSTAYS.csv'))
los = los[['ICUSTAY_ID','LOS']]
los.head()
los['LOS'] = los['LOS'] * 24
los.rename(columns={"ICUSTAY_ID": "patientunitstayid"},inplace=True)
new_df_los = pd.merge(new_df, los, how='left', left_on=['patientunitstayid'],right_on=['patientunitstayid'])
print(f"New df los patientunitstayid nunique: {new_df_los.patientunitstayid.nunique()}")
new_df_los = new_df_los[new_df_los['LOS']>=24] #CHANGE TO 48
new_df_los = new_df_los[new_df_los['itemoffset'] > 0] #CHANGE TO ZERO
new_df_los_nodups = new_df_los.drop_duplicates()

print(f"New df los nodups groupby patientunitstayid count: {new_df_los_nodups.groupby('patientunitstayid').count().shape}")

label_deli = new_df_los_nodups.copy()
label_deli['labelrec'] = np.nan
label_deli.loc[label_deli['CAM']==1,'labelrec']=1
label_deli.loc[label_deli['CAM']==0,'labelrec']=0
label_deli['labelpt'] = np.nan
pos_cam_coh = label_deli[label_deli['labelrec']==1]['patientunitstayid'].unique()
label_deli.loc[label_deli['patientunitstayid'].isin(pos_cam_coh), 'labelpt']=1
label_deli.loc[~(label_deli['patientunitstayid'].isin(pos_cam_coh)), 'labelpt']=0
pos_cam_df = label_deli[label_deli['labelpt']==1].copy()
neg_cam_df = label_deli[label_deli['labelpt']==0].copy()
pos_cam_df = pos_cam_df.reset_index(drop=True)
neg_cam_df = neg_cam_df.reset_index(drop=True)
pos_cam_df.to_csv(os.path.join(data_processed_path, 'pos_mimic_notimputed_24los.csv'), index=False)
neg_cam_df.to_csv(os.path.join(data_processed_path, 'neg_mimic_notimputed_24los.csv'), index=False)

# Imputation
new_df = label_deli.copy()

# 컬럼명이 이미 rename되었으므로 새 컬럼명 사용
mean_columns = ['Age', 'Height', 'Weight']

# mean Imputation of each patient
for i in mean_columns:
    new_df[i] = new_df[i].fillna(new_df.groupby("patientunitstayid")[i].transform('mean'))

## Impute with mean of whole cohort
for i in mean_columns:
    new_df[i] = new_df[i].fillna(new_df[i].mean())

print(f"New df columns: {new_df.columns}")

# Ventilation만 남아있음 (Dopamine 등은 이미 Vasopressor dose로 합쳐지고 drop됨)
zero_columns = ['Ventilation']

new_df[zero_columns] = new_df[zero_columns].fillna(value=0)

# 현재 new_df에 존재하는 컬럼으로 columns_order 재정의
columns_order_current = [col for col in new_df.columns if col != 'labelrec' and col != 'labelpt']

# PATIENT WISE
df_g = new_df[columns_order_current].groupby("patientunitstayid").apply(lambda x: x.notnull().mean(), include_groups=False)
for i in df_g.columns:
    df_g[i] = df_g[i].replace({0:np.nan})
import missingno as msno
import seaborn as sns
import matplotlib.pyplot as plt
columns = df_g.columns
percent_missing = df_g.isnull().sum() * 100 / len(df_g)
missing_value_df = pd.DataFrame({'column_name': columns,'percent_missing': percent_missing})
missing_value_df.sort_values('percent_missing', inplace=True)
missing_value_df.reset_index(inplace=True, drop=True)
print(f"Missing value df after zero fill:\n{missing_value_df}")

# FFill - rename된 컬럼명 사용, drop된 컬럼 제외
forward_columns = ['Heart Rate', 'O2 Saturation', 'Glucose',
       'Temperature', 'Sodium', 'BUN', 'WBC',
       'Hemoglobin', 'Platelets', 'Potassium', 'Chloride', 'Bicarbonate',
       'Creatinine', 'Sofa', 'Sofa_wo_gcs']

for i in forward_columns:
    if i in new_df.columns:
        new_df[i] = new_df.groupby("patientunitstayid")[i].transform(lambda v: v.ffill())

# PATIENT WISE

df_g = new_df[columns_order_current].groupby("patientunitstayid").apply(lambda x: x.notnull().mean(), include_groups=False)

for i in df_g.columns:
    df_g[i] = df_g[i].replace({0:np.nan})

import missingno as msno
import seaborn as sns
import matplotlib.pyplot as plt
columns = df_g.columns
percent_missing = df_g.isnull().sum() * 100 / len(df_g)
missing_value_df = pd.DataFrame({'column_name': columns,'percent_missing': percent_missing})
missing_value_df.sort_values('percent_missing', inplace=True)
missing_value_df.reset_index(inplace=True, drop=True)
print(f"Missing value df after forward fill:\n{missing_value_df}")

# BFill
back_columns = forward_columns

for i in back_columns:
    if i in new_df.columns:
        new_df[i] = new_df.groupby("patientunitstayid")[i].transform(lambda v: v.bfill())

#After Bfill
df_g = new_df[columns_order_current].groupby("patientunitstayid").apply(lambda x: x.notnull().mean(), include_groups=False)

for i in df_g.columns:
    df_g[i] = df_g[i].replace({0:np.nan})

import missingno as msno
import seaborn as sns
import matplotlib.pyplot as plt
columns = df_g.columns
percent_missing = df_g.isnull().sum() * 100 / len(df_g)
missing_value_df = pd.DataFrame({'column_name': columns,'percent_missing': percent_missing})
missing_value_df.sort_values('percent_missing', inplace=True)
missing_value_df.reset_index(inplace=True, drop=True)
print(f"Missing value df after backward fill:\n{missing_value_df}")

# Drop columns with high missing rate (ALT,AST,Alk Ph, Dir Bil) - 이미 drop된 컬럼은 제외
cols_to_drop = ['ALT', 'AST', 'Alkaline Phosphate', 'direct bilirubin', 'fluidin', 'fluidout']
cols_to_drop_existing = [c for c in cols_to_drop if c in new_df.columns]
if cols_to_drop_existing:
    new_df.drop(columns=cols_to_drop_existing, inplace=True)
print(f"New df patientunitstayid nunique: {new_df.patientunitstayid.nunique()}")
print(f"New df shape: {new_df.shape}")

# new_df는 이미 label_deli에서 복사되었고, label_deli는 new_df_los_nodups에서 복사됨
# 따라서 이미 LOS가 포함되어 있고 LOS>=24, itemoffset>0 필터링도 완료된 상태
# 중복 제거만 수행
new_df_los_nodups = new_df.drop_duplicates()

## LOS at least 24/48 hours

### Missing values - rename된 컬럼명 사용
columns_order_los = ['patientunitstayid', 'itemoffset', 'Gender', 'Age', 'Height',
       'Weight', 'Heart Rate', 'O2 Saturation', 'Glucose',
       'Temperature', 'Sodium', 'BUN', 'WBC', 'Hemoglobin',
       'Platelets', 'Potassium', 'Chloride', 'Bicarbonate',
       'Creatinine', 'Sofa', 'Sofa_wo_gcs',
       'Ventilation', 'Vasopressor dose', 'LOS', 'CAM']

# 실제 존재하는 컬럼만 필터링
columns_order_los = [c for c in columns_order_los if c in new_df_los_nodups.columns]

df_g = new_df_los_nodups[columns_order_los].groupby("patientunitstayid").apply(lambda x: x.notnull().mean(), include_groups=False)
for i in df_g.columns:
    df_g[i] = df_g[i].replace({0:np.nan})
#after Imputation
import missingno as msno
import seaborn as sns
import matplotlib.pyplot as plt
columns = df_g.columns
percent_missing = df_g.isnull().sum() * 100 / len(df_g)
missing_value_df = pd.DataFrame({'column_name': columns,'percent_missing': percent_missing})
missing_value_df.sort_values('percent_missing', inplace=True)
missing_value_df.reset_index(inplace=True, drop=True)
print(f"Missing value df after LOS filter:\n{missing_value_df}")

# Drop Patients with missing values - rename된 컬럼명 사용
dropna_cols = ['Heart Rate', 'O2 Saturation', 'Glucose',
       'Temperature', 'Sodium', 'BUN', 'WBC', 'Hemoglobin',
       'Platelets', 'Potassium', 'Chloride', 'Bicarbonate', 'Creatinine',
       'Sofa', 'Sofa_wo_gcs', 'Ventilation', 'Vasopressor dose']
# 실제 존재하는 컬럼만 필터링
dropna_cols = [c for c in dropna_cols if c in new_df_los_nodups.columns]
new_df_los_nodups = new_df_los_nodups.dropna(subset=dropna_cols)

print(f"New df los nodups shape: {new_df_los_nodups.shape}")

print(f"New df los nodups patientunitstayid nunique: {new_df_los_nodups.patientunitstayid.nunique()}")

### split CAM pos and CAM neg
label_deli = new_df_los_nodups.copy()
label_deli['labelrec'] = np.nan
label_deli.loc[label_deli['CAM']==1,'labelrec']=1
label_deli.loc[label_deli['CAM']==0,'labelrec']=0
label_deli['labelpt'] = np.nan

pos_cam_coh = label_deli[label_deli['labelrec']==1]['patientunitstayid'].unique()
label_deli.loc[label_deli['patientunitstayid'].isin(pos_cam_coh), 'labelpt']=1
label_deli.loc[~(label_deli['patientunitstayid'].isin(pos_cam_coh)), 'labelpt']=0

print(f"Label deli tail:\n{label_deli.tail(1)}")

pos_cam_df = label_deli[label_deli['labelpt']==1].copy()
neg_cam_df = label_deli[label_deli['labelpt']==0].copy()
pos_cam_df = pos_cam_df.reset_index(drop=True)
neg_cam_df = neg_cam_df.reset_index(drop=True)

print(f"Pos cam df patientunitstayid nunique: {pos_cam_df['patientunitstayid'].nunique()}, Neg cam df patientunitstayid nunique: {neg_cam_df['patientunitstayid'].nunique()}")

neg_cam_df['CAM'] = neg_cam_df['labelpt']
pos_cam_df['CAM'] = pos_cam_df['labelpt']

pos_cam_df.to_csv(os.path.join(data_processed_path, 'pos_mimic_imputed_24los.csv'), index=False)
neg_cam_df.to_csv(os.path.join(data_processed_path, 'neg_mimic_imputed_24los.csv'), index=False)

mimic_df = pd.concat([neg_cam_df, pos_cam_df],axis=0)

print(f"Mimic df patientunitstayid nunique: {mimic_df.patientunitstayid.nunique()}")

print("Data preprocessing completed successfully!")

