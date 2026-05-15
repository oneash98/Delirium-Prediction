# 1_data_extraction.ipynb 설명

`src/1_data_extraction.ipynb`는 Parkinson 코호트의 원천 MIMIC-IV CSV에서 ICU stay 정보, chart event, lab event, eMAR medication event, procedure/device event를 추출하는 노트북입니다. 변수 목록은 노트북 코드에 직접 적지 않고 `src/extraction_variable_catalog.csv`를 읽어서 사용합니다.

핵심 목적은 다음 단계인 `2_data_transform.ipynb`가 사용할 수 있도록, 원천 테이블에서 필요한 행만 골라 중간 산출물로 저장하는 것입니다.

## 입력 파일

노트북은 `Parkinson/src`에서 실행된다는 전제로 `PROJECT_DIR = Path.cwd().resolve().parent`를 설정합니다.

필수 입력:

- `data/patients.csv`
- `data/admissions.csv`
- `data/icustays.csv`
- `data/d_items.csv`
- `data/d_labitems.csv`
- `src/extraction_variable_catalog.csv`
- `data/chartevents.csv`
- `data/labevents.csv`
- `data/emar.csv`
- `data/procedureevents.csv`

## 주요 산출물

`processed/extraction/`:

- `adm_pat_icu.csv`: inclusion/exclusion criteria 적용 전 전체 ICU stay 기준 테이블. ICU 입실 시점의 `services.curr_service`를 `specialty`로 포함합니다.
- `chart_selected.csv`: catalog의 `chartevents` 행에 해당하는 chart event.
- `lab_selected.csv`: catalog의 `labevents` 행에 해당하는 lab event.
- `medication_events.csv`: catalog의 `emar` 행에 해당하는 약물 투약 이벤트.
- `procedure_selected.csv`: catalog의 `procedureevents` 행에 해당하는 procedure/device 이벤트.
- `all_events_long.csv`: chart, lab, eMAR medication point event를 통합한 long-format event table.

현재 노트북은 `adm_pat_icu_all.csv` 또는 `all_events.csv`를 별도로 저장하지 않습니다. transform 노트북은 `adm_pat_icu.csv`와 `all_events_long.csv`를 입력으로 사용합니다.

## 노트북 순서

아래 섹션은 `src/1_data_extraction.ipynb`의 마크다운 소제목 순서를 따릅니다.

| 노트북 소제목 | 이 문서의 섹션 |
| --- | --- |
| `## 1. Cohort` | 코호트 생성 |
| `## 2. CHARTEVENTS 추출` | 변수 Catalog 사용, Chart Event 추출, Delirium Outcome 확인 |
| `## 3. LABEVENTS 추출` | Lab Event 추출, Unit 처리 주의사항 |
| `## 4. EMAR 약물 추출` | Medication Event 추출 |
| `## 5. PROCEDUREEVENTS 추출` | Procedure/Device Event 추출 |
| `## 6. Long-format event table 저장` | Long-format Event Table |

## 1. Cohort

`icustays`를 중심으로 환자 정보와 입원 정보를 붙입니다.

결합되는 주요 정보:

- `subject_id`, `hadm_id`, `stay_id`
- `gender`, `anchor_age`, `anchor_year`, `anchor_year_group`, `dod`
- `admittime`, `dischtime`, `deathtime`, `admission_type`, `race`
- `intime`, `outtime`
- `icu_los_hours`


## 2. CHARTEVENTS 추출

### 변수 Catalog 사용

Catalog 로드는 노트북 앞부분에서 수행하고, source별 subset 생성은 각 추출 섹션에서 수행합니다.

`extraction_variable_catalog.csv`는 현재 다음 컬럼 구조를 사용합니다.

- `source_table`
- `itemid`
- `category`
- `label`
- `feature_name`
- `type`
- `unit_or_window`
- `transform_note`

사용 방식:

- `chartevents`, `labevents`, `procedureevents`는 `itemid` 기준으로 추출합니다.
- `emar`는 `itemid`를 사용하지 않고 `label`에 들어 있는 eMAR medication 문자열 기준으로 추출합니다.
- catalog에 있는 변수는 별도의 included flag 없이 모두 추출 대상입니다.

### Chart Event 추출

`chartevents.csv`는 `chunksize=1_000_000`으로 나누어 읽습니다.

현재 catalog 기준 주요 추출 대상:

- Outcome: `Delirium assessment`
- Neurologic/sedation: RASS, GCS eye/verbal/motor
- Vital signs: heart rate, respiratory rate, SpO2, arterial saturation, non-invasive BP, arterial BP, temperature
- Body measures: admission weight, height
- Bedside glucose: serum, finger stick, whole blood glucose

현재 arterial BP는 기본 arterial BP item과 `ART BP Systolic`, `ART BP Diastolic`이 함께 포함되어 있습니다.

중요 처리:

- `itemid`가 chart catalog에 있는 행만 남깁니다.
- `d_items`에서 `label`, `category`, `unitname`을 붙입니다.
- catalog에서 `feature_name`, `type`을 붙입니다.
- `subject_id`, `hadm_id`, `stay_id` 기준으로 ICU stay 정보를 붙입니다.
- `charttime`이 ICU `intime`과 `outtime` 사이에 있는 행만 유지합니다.

### Delirium Outcome 확인

`Delirium assessment`는 이 섹션에서 chart event로 추출합니다. 숫자 label 변환은 `2_data_transform.ipynb`의 `## VALUE 변환 (문자열 → 숫자)`에서 수행합니다.

`Delirium assessment`는 `chartevents`에서 추출되는 outcome 후보입니다. extraction 단계에서는 원본 `value`, `valuenum`, `valueuom`을 유지하고, `Positive`, `Negative`, `UTA` 같은 값의 숫자화는 transform 단계에서 처리합니다.

## 3. LABEVENTS 추출

`labevents.csv`도 `chunksize=1_000_000`으로 나누어 읽습니다.

현재 catalog 기준 주요 추출 대상:

- Chemistry/electrolytes: glucose, bicarbonate, chloride, sodium, potassium, BUN, creatinine, magnesium, phosphate, anion gap
- Calcium/bilirubin 계열: total/free calcium, total/direct/indirect bilirubin
- CBC: hematocrit, hemoglobin, platelet count, WBC
- Liver/nutrition: ALT, AST, albumin
- ABG/coagulation: lactate, pH, pCO2, pO2, INR, PT, PTT

비슷한 lab 항목은 같은 `feature_name`으로 묶어 추출합니다. 예를 들어 WBC 관련 item은 `wbc`, hemoglobin 관련 item은 `hemoglobin`, hematocrit 관련 item은 `hematocrit`으로 들어갑니다.

중요 처리:

- `itemid`가 lab catalog에 있는 행만 남깁니다.
- `d_labitems`에서 원본 lab `label`을 붙입니다.
- catalog에서 `feature_name`, `type`을 붙입니다.
- `subject_id`, `hadm_id` 기준으로 ICU stay 정보를 붙입니다.
- lab `charttime`이 ICU `intime`과 `outtime` 사이에 있는 행만 유지합니다.

### Unit 처리 주의사항

Extraction 단계에서는 각 추출 섹션에서 원본 `valueuom`을 유지합니다. 단위 변환은 `2_data_transform.ipynb`의 `## 단위 변환`에서 수행합니다.

`d_items.csv`, `d_labitems.csv` 또는 catalog의 unit 정보만으로 실제 측정값의 단위가 항상 하나라고 가정하지 않습니다. 실제 event table에서는 같은 `itemid`라도 `valueuom`이 여러 값으로 기록될 수 있습니다.

따라서 extraction 단계에서는 원본 `valueuom`을 유지합니다. 단위 변환, 같은 변수 안의 multi-unit 확인, 필요 시 unit별 feature 분리는 `2_data_transform.ipynb`에서 처리합니다.

## 4. EMAR 약물 추출

현재 약물 정보는 `prescriptions.csv`가 아니라 `emar.csv`에서 가져옵니다. 이유는 eMAR가 실제 투약 시점인 `charttime`을 제공하기 때문입니다.

추출 방식:

- catalog의 `source_table == 'emar'` 행을 사용합니다.
- eMAR catalog의 `label`을 `medication_name`으로 사용합니다.
- `emar.medication`도 공백을 정리해 `medication_name`으로 만든 뒤 catalog와 merge합니다.
- 정규식이나 부분 문자열 검색이 아니라 정확한 medication label merge로 추출합니다.

투약이 실제로 이루어진 event만 남기기 위해 `event_txt`는 투약/시작/확인 계열 값만 사용합니다.

현재 medication feature:

- `levodopa_related`
- `comt_inhibitor`
- `dopamine_agonist`
- `maob_inhibitor`
- `amantadine`
- `anticholinergic`
- `benzodiazepine`
- `opioid`
- `sedatives`
- `antipsychotic`
- `vasopressor`

중요 처리:

- `subject_id`, `hadm_id` 기준으로 ICU stay 정보를 붙입니다.
- `charttime`이 ICU `intime`과 `outtime` 사이에 있는 투약 이벤트만 유지합니다.
- medication은 `medication_events.csv`로 별도 저장하면서, 동시에 `all_events_long.csv`에도 point event로 포함합니다.
- `all_events_long.csv` 안의 medication row는 실제 투약 관련 eMAR event가 기록된 `charttime`에만 `value=1`, `valuenum=1`로 들어갑니다.
- Observation window 안 약물 노출 여부는 transform 단계가 아니라 모델링 단계에서 window 길이에 맞춰 계산합니다.

## 5. PROCEDUREEVENTS 추출

현재 `procedureevents.csv`에서는 catalog에 포함된 ventilation procedure만 itemid 기준으로 추출합니다.

현재 추출 대상:

- `Invasive Ventilation`
- `Non-invasive Ventilation`

중요 처리:

- `starttime`, `endtime`을 datetime으로 변환합니다.
- catalog에서 `feature_name`, `type`을 붙입니다.
- `subject_id`, `hadm_id`, `stay_id` 기준으로 ICU stay 정보를 붙입니다.
- procedure 구간이 ICU stay 구간과 겹치는 이벤트만 유지합니다.

procedure exposure 변환은 transform 단계에서 수행합니다. 즉 extraction에서는 interval 정보를 유지하고, transform에서 charttime 기준 wide table의 각 row 시간이 해당 procedure interval 안에 들어오면 1로 표시합니다.

## 6. Long-format event table 저장

chart, lab, medication point event는 같은 컬럼 구조로 맞춘 뒤 concat합니다.

공통 컬럼:

- `source_table`
- `subject_id`
- `hadm_id`
- `stay_id`
- `charttime`
- `itemid`
- `label`
- `feature_name`
- `type`
- `value`
- `valuenum`
- `valueuom`

`all_events_long.csv`에는 chart, lab, eMAR medication point event가 포함됩니다.

- chart/lab row는 원본 측정값을 유지합니다.
- medication row는 이미 투약 관련 `event_txt`로 필터링된 eMAR event이며, 실제 event가 기록된 `charttime`에 `value=1`로 저장됩니다.
- procedure/device는 `starttime`~`endtime` interval 정보가 필요하므로 `procedure_selected.csv`로 별도 유지합니다.

## 현재 Extraction 단계에서 하지 않는 일

다음 처리는 transform 단계에서 수행합니다.

- LSTM 모델링을 위한 ICU LOS 72시간 이상 기준의 inclusion/exclusion criteria 적용
- 문자열 value의 숫자화
- 온도, 체중, 키, FiO2 등 단위 변환
- multi-unit feature 분리
- 12시간 구간 라벨링, charttime 기준 wide table, 12시간 bin-level wide table 생성
- medication observation-window exposure 생성
- procedure charttime-interval exposure flag 생성
- 결측 처리
- 섬망 평가 직전 8시간 window 집계

## 주의사항

- `chartevents.csv`, `labevents.csv`는 매우 크므로 chunk 처리 방식을 유지합니다.
- `Delirium assessment`는 outcome 후보로 추출하지만, 숫자 label 변환은 transform 단계에서 합니다.
- eMAR medication 매핑은 현재 catalog에 들어 있는 `emar.medication` 문자열에 의존합니다. 다른 데이터 추출본에서는 medication 이름 차이로 누락될 수 있습니다.
- lab과 eMAR medication은 `subject_id`, `hadm_id` 기준으로 ICU stay에 붙이고, chart/procedure는 `subject_id`, `hadm_id`, `stay_id` 기준으로 붙입니다.
- `services.csv`는 필수 입력으로 가정합니다. ICU 입실 시점 이전의 가장 최근 `curr_service`를 `specialty`로 저장합니다.
- 이 노트북은 extraction만 수행합니다. 12시간 라벨 long-format event, charttime 기준 wide table, 12시간 bin-level wide table, assessment index 생성은 `2_data_transform.ipynb`, EDA는 `3_eda.ipynb`, train/test split과 모델링 입력 준비는 `4_modeling.ipynb`에서 처리합니다.
