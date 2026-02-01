# Agent Notes: `1-2_Data_extraction_KMIMIC.py`

이 문서는 `Data extraction/1-2_Data_extraction_KMIMIC.py`의 최신 동작을 빠르게 재현/이해하기 위한 “기억용” 요약이다.

## 목적
- KMIMIC(비식별화된 MIMIC 유사 스키마)에서 **65세 이상 ICU stay** 코호트를 만들고,
- CAM-ICU 기반으로 섬망 코호트(stay)를 정의한 뒤,
- 차트/검사실(Lab)/약물 및 섬망 관련 반응 이벤트를 추출해 stay 단위로 분해하고,
- **60분 binning 시계열(timeseries)** 을 만들어 폴더별 최종 CSV(`all_data_delirium_kmimic.csv`)를 생성한다.
- 실행 단위: `Data extraction/1-2_Data_extraction_KMIMIC.py`는 **한 번 실행할 때 KMIMIC_EMR의 특정 폴더 1개만 처리**한다.
  - 여러 폴더(예: 440~442)를 연속 처리하려면 배치 러너(`Data extraction/run_kmimic_extraction_batch.py`)를 사용한다.

## 입력/출력(환경변수 기반, 폴더별 산출물)
- 입력 베이스: `KMIMIC_ROOT` (기본값은 코드 내 기본 경로)
  - 실제 입력 폴더: `${KMIMIC_ROOT}/{KMIMIC_FOLDER}` (예: `.../440`)
- 출력 베이스: `OUTPUT_ROOT` (기본값은 코드 내 기본 경로)
  - 실제 출력 폴더: `${OUTPUT_ROOT}/{KMIMIC_FOLDER}` (예: `.../440`)
- 처리 폴더:
  - 단일 실행: `KMIMIC_FOLDER=440` 처럼 1개 지정
  - 다중 실행: `run_kmimic_extraction_batch.py --range 440 442` 또는 `--folders 440 441 442`
- Vocabulary(공통):
  - 차트 vocab: `VOCAB_CHART_PATH = /home/coder/workspace/datasets/KMIMIC_VOCA/M_CHARTEVENTS.csv`
  - 랩 vocab: `VOCAB_LAB_PATH = /home/coder/workspace/datasets/KMIMIC_VOCA/M_LABEVENTS.csv`
  - datetime vocab: `VOCAB_DATETIME_PATH = /home/coder/workspace/datasets/KMIMIC_VOCA/M_DATETIMEEVENTS.csv`

## 핵심 전처리/코호트
- `ICUSTAYS.csv`의 `STAY_ID`를 downstream 호환을 위해 `ICUSTAY_ID`로 rename.
- 환자/ICU merge 후 `AGE` 생성:
  - MIMIC 스타일(`DOB` 존재)면 `INTIMEYear - DOBYear`
  - KMIMIC(`ANCHOR_AGE` 존재)면 `"87 years"`에서 숫자 추출
- **AGE >= 65**만 유지(주석에 “65세 이상으로 변경” 명시).
- 성별: `SEX` → `GENDER` rename 후 `g_map = {'F':1,'M':2,'':0}`로 매핑(기타 문자는 0).
- 진단: `DIAGNOSIS` 결측을 `'nodx'`로 채운 뒤 `factorize`로 정수 ID로 변환.

## 날짜 파싱 (KMIMIC 연도 보정)
- `parse_datetime_kmimic()`:
  - pandas가 처리 못하는 연도(비식별화로 2xxx 등, pandas 허용범위 1677~2262 밖)를 **연도만 안전 범위로 보정** 후 재파싱.
  - ISO 형태 `YYYY-MM-DDTHH:MM:SS`에 대해 정규식으로 연도 부분만 교정.

## 피처 세트(상수)
- CAM-ICU 선정 기준: `CAMICU_FSN_IDS = [1351493007]` (vocab에서 FSN_id로 CAM-ICU ITEMID 찾음)
- Chart 피처: `CHART_FEATURES` (문자열 FSN/LOINC 혼합)
  - 예: CAM-ICU(`1351493007`), 체중(`29463-7`), 키(`8302-2`), SpO2(`59410-1`), HR(`8867-4`), Temp(`8310-5`), Glucose(`74774-1`), FiO2(`19996-8`), RASS(`1345050000`), NBP syst/diast/mean(`8480-6`,`8462-4`,`8478-0`), RR(`9279-1`), pH/PaCO2/PaO2(`3019977`,`3027946`,`3027801`), ICP(`60956-0`)
- Lab 피처: `LAB_FEATURES` (OMOP concept_id)
- Drug 피처: `DRUG_FEATURES` (FSN_id)
- Delirium 반응 피처: `DELIRIUM_FSN_IDS` (FSN_id 집합)

## 처리 흐름(폴더 하나 기준: `process_single_folder(folder_num)`)

### 1) CAM-ICU 기반 코호트 stay 추출(CHARTEVENTS)
- `get_itemids_from_chart_vocab(VOCAB_CHART_PATH, CAMICU_FSN_IDS)`로 CAM-ICU 관련 `ITEMID` 목록(`camicu_itemids`)을 만든다.
- `CHARTEVENTS.csv`에서 `ITEMID ∈ camicu_itemids` 필터링 후 `VALUE ∈ {'음성','양성'}`만 유지.
- CAM-ICU 관측 stay 목록: `icustay_camicu = unique(STAY_ID 또는 ICUSTAY_ID)` (이후 모든 테이블은 이 stay로 필터링).

### 2) Chart 추출/정규화(CHARTEVENTS → `chart.csv`)
- `D_ITEMS.csv`와 merge하여 `LABEL` 확보.
- `VALUE`를 `VALUENUM`으로 매핑:
  - CAM-ICU 등: `No/Negative/음성 → 0`, `Yes/Positive/양성 → 1`
  - RASS: 문자열(예: `-5 Unarousable ...`, `+4 Combative ...`)을 -5~+4 범위 정수로 매핑
- `VOCAB_CHART_PATH`와 merge하여 `FSN_id`, `FSN_term` 추가.
- `parse_datetime_kmimic()`로 `CHARTTIME` 파싱/보정.
- 최종 스키마를 정리해 `VALUE`(수치)로 통일 후,
  - `FSN_id ∈ CHART_FEATURES`만 남기고
  - `ICUSTAY_ID ∈ icustay_camicu`만 남긴 뒤 저장: `${data_path}/chart.csv`

### 3) Lab 추출(LABEVENTS → `icu_lab.csv`)
- `LABEVENTS.csv`에서 `VALUE`가 비어있으면 `VALUENUM`으로 보강 후 불필요 컬럼 drop.
- `VOCAB_LAB_PATH(M_LABEVENTS.csv)`와 merge하여 `omop_concept_id`, `concept_name`를 붙인다.
- (가능하면) `D_LABITEMS.csv`와 merge.
- `adm_pat_icu`와 right join 후 `INTIME < CHARTTIME < OUTTIME`만 유지(+ `STAY_ID==ICUSTAY_ID` 조건이 있으면 적용).
- `ICUSTAY_ID ∈ icustay_camicu` 및 `omop_concept_id ∈ LAB_FEATURES`로 필터 후 저장: `${data_path}/icu_lab.csv`

### 4) DATETIMEEVENTS → 약물/섬망 관련 반응(`icu_drugs.csv`, `icu_delirium.csv`)
- `DATETIMEEVENTS.csv`에 `M_DATETIMEEVENTS.csv`(vocab) merge로 `FSN_id`, `FSN_term` 추가.
- `adm_pat_icu`와 right join 후 `INTIME < CHARTTIME < OUTTIME` 유지(+ `STAY_ID==ICUSTAY_ID` 조건 적용 가능).
- CAM-ICU stay로 필터.
- 약물 feature(FSN id):
  - sedative(72641008), opiate(726582005), benzodiazepine(770571009), heparin(103746007)
  - 저장: `icu_drugs.csv`
- 섬망 관련 반응 feature(FSN id 집합 `DELIRIUM_FSN_IDS`, “delirium(2776000)” 및 hallucination, disorientation, sleep disturbance 등 다수)
  - 저장: `icu_delirium.csv`
- DATETIMEEVENTS에는 값이 없어서, 후반부에서 `icu_drugs['VALUE']=1`, `icu_delirium['VALUE']=1`로 이벤트 발생 여부만 기록.

### 5) 테이블 통합 → stay 폴더 분해 → 시계열 생성
- `chart`, `icu_lab`, `icu_drugs`, `icu_delirium`을 로드 후 `LABEL`을 term 기반으로 정규화(FSN_term / concept_name 우선).
- `LABEL_MAPPING`으로 일부 라벨명을 축약/정규화.
- stay별로 `data_path/patients/{ICUSTAY_ID}/` 폴더 생성 후,
  - `break_up_by_unit_stay()`로 `admission.csv`, `chart.csv`, `icu_lab.csv`, `icu_drugs.csv`, `icu_delirium.csv`, `all_tables.csv`를 저장.
- `convert_events_to_timeseries()`:
  - (CHARTTIME, LABEL, VALUE)를 pivot하여 wide 형태 timeseries 생성(동일 (시간, 라벨)은 마지막 값 유지).
- `binning(x=60)`:
  - `HOURS`/`MINUTES` 계산 후 `BIN = floor(MINUTES/x)`.
  - **BIN < 0 제거**(ICU 입실 전 기록 제거).
  - 숫자 컬럼은 BIN별 평균으로 결측 보간, 문자열 컬럼은 ffill/bfill.
  - BIN 중복 제거(마지막 유지).
- `extract_time_series_from_subject()`:
  - 각 stay 폴더에서 `admission.csv` + `all_tables.csv`를 읽어 `timeseries.csv` 생성.
  - 생성 실패한 stay는 `delete_wo_timeseries()`로 폴더를 삭제.
- 최종적으로 모든 `timeseries.csv`를 concat하여 `${data_path}/all_data_delirium_kmimic.csv` 생성.

## 주요 출력물(대표)
- `${OUTPUT_ROOT}/{KMIMIC_FOLDER}/chart.csv`
- `${OUTPUT_ROOT}/{KMIMIC_FOLDER}/icu_lab.csv`
- `${OUTPUT_ROOT}/{KMIMIC_FOLDER}/icu_drugs.csv`
- `${OUTPUT_ROOT}/{KMIMIC_FOLDER}/icu_delirium.csv`
- `${OUTPUT_ROOT}/{KMIMIC_FOLDER}/all_tables.csv`
- `${OUTPUT_ROOT}/{KMIMIC_FOLDER}/patients/{ICUSTAY_ID}/timeseries.csv`
- `${OUTPUT_ROOT}/{KMIMIC_FOLDER}/all_data_delirium_mimic.csv`

## 주의/메모(잠재 이슈)
- 경로가 리눅스 절대경로로 하드코딩되어 있어 로컬/다른 환경에서는 상수(`KMIMIC_BASE_PATH`, `DATA_OUTPUT_BASE`, `VOCAB_*`) 수정이 필요.
- 폴더별로 `PATIENTS.csv`/`ICUSTAYS.csv`가 없으면 해당 폴더는 스킵/실패 처리.
- `CHART_FEATURES`는 문자열(LOINC 등)과 숫자 문자열이 섞여 있어, `FSN_id` 컬럼의 타입/표현이 달라지면 필터가 비어질 수 있음(인코딩/타입 확인 필요).
