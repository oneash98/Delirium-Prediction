# 3_eda.ipynb 설명

`src/3_eda.ipynb`는 `2_data_transform.ipynb`가 만든 12시간 bin-level 산출물과 최종 cohort를 읽어 EDA 표와 그림을 생성합니다. 이 노트북은 train/test split을 생성하지 않습니다.

## 입력 파일

`processed/transform/`:

- `events_12h_binned.csv`: cohort criteria를 통과한 12시간 bin-level wide table.
- `cohort_final.csv`: cohort criteria를 통과한 stay-level cohort table.

## 출력 파일

`outputs/eda/`:

- `delirium_label_summary.csv`
- `delirium_distribution.png`
- `baseline_characteristics_plots.png`
- `specialty_distribution_by_delirium.csv`
- `specialty_distribution_by_delirium.png`
- `normality_summary.csv`
- `normality_diagnostics.png`
- `table1_characteristics.csv`
- `delirium_assessment_interval_distribution.png`
- `delirium_assessment_interval_summary.csv`
- `delirium_assessment_stay_interval_summary.csv`

## 노트북 순서

아래 섹션은 `src/3_eda.ipynb`의 마크다운 소제목 순서를 따릅니다.

| 노트북 소제목 | 확인 내용 |
| --- | --- |
| `## EDA: 환자 기본정보` | subject/stay 수, subject-level `ever_delirium` 분포, 12시간 bin-level delirium label 분포, 기본정보 시각화, specialty 분포, age/height/weight/LOS 정규성 진단, Table 1 형태의 baseline characteristics |
| `## Delirium assessment 간격 분포` | `all_events_filtered.csv`에서 delirium assessment timepoint를 정렬해 연속 평가 간격 histogram과 요약 CSV를 생성 |
| `## Delirium 첫 발생 시점 분포` | subject-level 첫 delirium 발생 시점을 LOS median 이내에서 요약하고 시각화 |

## Delirium assessment 간격 분포

- 입력: `processed/transform/all_events_filtered.csv`
- 동일 `stay_id`/`charttime` 중복은 하나의 assessment timepoint로 간주합니다.
- 같은 ICU stay 안에서 연속 delirium assessment 사이의 시간 간격을 hour 단위로 계산합니다.
- `delirium_assessment_interval_distribution.png`는 긴 tail 때문에 48시간까지 표시하고, mean/median 기준선은 전체 interval 기준으로 표시합니다.
- 전체 interval 요약은 `delirium_assessment_interval_summary.csv`, stay별 interval 요약은 `delirium_assessment_stay_interval_summary.csv`에 저장합니다.

## EDA: 환자 기본정보

- subject 수, stay 수
- subject당 ICU stay 수
- subject-level `ever_delirium` 분포
- 12시간 bin-level 전체 label, 48시간 이후 label, 36시간까지 label의 delirium 개수와 비율
- subject-level sex, age, height, weight, ICU LOS 분포 시각화
- top 10 specialty의 No delirium / Ever delirium subject 수 기준 별도 분포
- age, height, weight, ICU LOS의 Shapiro-Wilk test, histogram, Q-Q plot
- Delirium vs Non-delirium subject-level baseline characteristics table: age, sex, height, weight, ICU LOS, race, admission type, specialty

## 주의사항

- EDA는 전체 cohort의 관측 패턴을 확인하기 위한 단계입니다.
- Height와 weight는 `events_12h_binned.csv`에서 subject별 median으로 요약해 `subject_summary`에 붙입니다.
- Height는 non-missing subject 수가 적어 정규성 검정과 Table 1 p-value 해석에 주의가 필요합니다.
- Table 1의 연속형 변수 p-value는 Mann-Whitney U test, 범주형 변수 p-value는 chi-square test를 사용합니다.
