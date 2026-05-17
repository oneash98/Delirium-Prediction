# 4_train_test_construction

`src/4_train_test_construction.ipynb`는 transform 산출물을 받아 subject-level train/test split과 LSTM sequence index를 생성합니다.

## 입력 파일

`processed/transform/`:

- `events_12h_binned.csv`: 12시간 bin-level feature table
- `cohort_final.csv`: stay-level cohort table, `ever_delirium` 포함

## Subject-level Split

분할 단위는 `subject_id`입니다.

- 기본 비율: train/test = 80/20
- stratification label: subject-level `ever_delirium`
- 같은 subject의 모든 stay와 bin row는 같은 split에 배정
- 출력 확인: split별 `ever_delirium_0`, `ever_delirium_1`, `n_subjects`

`ever_delirium`은 split stratification용 subject-level label입니다. 모델 target은 `events_12h_binned.csv`의 bin-level `delirium`입니다.

## LSTM Sequence Index

각 ICU stay 안에서 anchor bin을 오른쪽으로 sliding하며 sequence row를 생성합니다.

- 입력 길이: 4
- 출력 길이: 3
- anchor 후보: `t2`부터 마지막 실제 bin
- 실제 input bin이 4개 미만이면 입력 앞쪽을 `PAD`로 채움
- 실제 future target이 없으면 target 위치를 `PAD`로 채우고 mask를 0으로 설정

구성 규칙:

| anchor | 입력 X | 출력 Y | loss 대상 |
| --- | --- | --- | --- |
| `t2` | `PAD,PAD,t1,t2` | `t2,t3,t4` | 실제 label이 있는 target |
| `t3` | `PAD,t1,t2,t3` | `t3,t4,t5` | 실제 label이 있는 target |
| `t4` | `t1,t2,t3,t4` | `t4,t5,t6` | 실제 label이 있는 target |
| `t5` | `t2,t3,t4,t5` | `t5,t6,t7` | 실제 label이 있는 target |
| 마지막 bin | 최근 4개 bin | `t_last,PAD,PAD` | `t_last` |

예를 들어 bin이 10개인 stay는 anchor `t2`부터 `t10`까지 최대 9개 sequence row를 만들 수 있습니다. PAD 3개와 `t1`만 있는 sequence는 만들지 않습니다.

## Sequence Columns

식별자:

- `example_id`
- `subject_id`
- `hadm_id`
- `stay_id`
- `split`
- `n_observed_bins`
- `anchor_bin`

입력/출력 bin:

- `input_bins`: 길이 4, `PAD` 포함 가능
- `input_mask`: 실제 input bin은 1, `PAD`는 0
- `target_bins`: 길이 3, `PAD` 포함 가능
- `target_mask`: 실제 target horizon은 1, `PAD` target horizon은 0
- `target_available_count`: 실제 target horizon 수

target:

- `y_t`
- `y_t_plus_1`
- `y_t_plus_2`
- `y_t_mask`
- `y_t_plus_1_mask`
- `y_t_plus_2_mask`
- `y_any_t_to_t_plus_2`

`PAD` target의 label은 placeholder `0`입니다. 실제 loss와 metric은 mask 1 위치만 사용합니다.

## 출력 파일

`processed/modeling/`:

- `events_12h_binned_with_split.csv`
- `cohort_final_with_split.csv`
- `train_subject_ids.csv`
- `test_subject_ids.csv`
- `subject_split_summary.csv`
- `train_test_split_summary.csv`
- `lstm_sequence_index.csv`
- `lstm_sequence_index_train.csv`
- `lstm_sequence_index_test.csv`

## Downstream 연결

`5_data_preprocessing.ipynb`는 `input_bins`의 `PAD`를 zero-vector로 변환하고, target mask를 `y_train_step_mask_lstm.npy`, `y_test_step_mask_lstm.npy`로 저장합니다.

`6_modeling.ipynb`는 masked BCE loss를 사용합니다. `target_mask = 0`인 위치는 loss와 horizon별 metric에서 제외합니다.
