# %% [markdown]
# # Within t+2 modeling
#
# This script trains comparison ML baselines and a single-output LSTM for the
# target "delirium occurs within t through t+2". ML baselines use only the
# current anchor time step t, while the LSTM uses the same t-3 through t input
# window as the sequence pipeline.

# %%
from __future__ import annotations

import argparse
import json
import random
import warnings
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import optuna
import pandas as pd
import torch
from sklearn.base import clone
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, confusion_matrix, roc_auc_score
from sklearn.model_selection import KFold, StratifiedKFold
from sklearn.preprocessing import StandardScaler
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

warnings.filterwarnings("ignore")


# %%
def resolve_project_dir() -> Path:
    cwd = Path.cwd().resolve()
    if cwd.name == "src" and cwd.parent.name == "Parkinson":
        return cwd.parent
    if cwd.name == "Parkinson":
        return cwd
    if (cwd / "Parkinson").exists():
        return cwd / "Parkinson"
    return cwd.parent


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True
    else:
        torch.set_num_threads(2)


def optional_import(module_name: str):
    try:
        return __import__(module_name)
    except ImportError:
        return None


def as_jsonable(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.ndarray,)):
        return value.tolist()
    if isinstance(value, dict):
        return {key: as_jsonable(val) for key, val in value.items()}
    if isinstance(value, list):
        return [as_jsonable(val) for val in value]
    return value


# %%
@dataclass
class ModelingData:
    x_train_seq: np.ndarray
    x_test_seq: np.ndarray
    x_train_t: np.ndarray
    x_test_t: np.ndarray
    y_train: np.ndarray
    y_test: np.ndarray
    meta_train: pd.DataFrame
    meta_test: pd.DataFrame


def load_modeling_data(project_dir: Path, require_full_target_window: bool = True) -> ModelingData:
    data_dir = project_dir / "processed" / "data_split"
    x_train_seq = np.load(data_dir / "X_train_lstm.npy").astype(np.float32)
    x_test_seq = np.load(data_dir / "X_test_lstm.npy").astype(np.float32)
    y_train = np.load(data_dir / "y_train_lstm.npy").astype(np.float32)
    y_test = np.load(data_dir / "y_test_lstm.npy").astype(np.float32)
    meta_train = pd.read_csv(data_dir / "lstm_train_metadata.csv")
    meta_test = pd.read_csv(data_dir / "lstm_test_metadata.csv")

    if require_full_target_window:
        train_keep = meta_train["target_available_count"].to_numpy() >= 3
        test_keep = meta_test["target_available_count"].to_numpy() >= 3
        x_train_seq = x_train_seq[train_keep]
        x_test_seq = x_test_seq[test_keep]
        y_train = y_train[train_keep]
        y_test = y_test[test_keep]
        meta_train = meta_train.loc[train_keep].reset_index(drop=True)
        meta_test = meta_test.loc[test_keep].reset_index(drop=True)

    return ModelingData(
        x_train_seq=x_train_seq,
        x_test_seq=x_test_seq,
        x_train_t=x_train_seq[:, -1, :].astype(np.float32),
        x_test_t=x_test_seq[:, -1, :].astype(np.float32),
        y_train=y_train,
        y_test=y_test,
        meta_train=meta_train,
        meta_test=meta_test,
    )


def make_subject_cv_folds(meta: pd.DataFrame, y: np.ndarray, n_folds: int, random_state: int) -> list[dict]:
    subject_summary = meta.assign(target=y).groupby("subject_id", as_index=False)["target"].max()
    subjects = subject_summary["subject_id"].to_numpy()
    labels = subject_summary["target"].to_numpy(dtype=int)
    if len(subjects) < 2:
        raise ValueError("At least two subjects are required for subject-level CV.")

    class_counts = pd.Series(labels).value_counts()
    can_stratify = len(class_counts) > 1 and class_counts.min() >= 2
    actual_folds = min(n_folds, int(class_counts.min())) if can_stratify else min(n_folds, len(subjects))
    actual_folds = max(actual_folds, 2)

    splitter = (
        StratifiedKFold(n_splits=actual_folds, shuffle=True, random_state=random_state)
        if can_stratify
        else KFold(n_splits=actual_folds, shuffle=True, random_state=random_state)
    )
    split_iter = splitter.split(subjects, labels) if can_stratify else splitter.split(subjects)

    folds = []
    subject_by_row = meta["subject_id"].to_numpy()
    for fold_id, (train_idx, val_idx) in enumerate(split_iter, start=1):
        train_subjects = set(subjects[train_idx])
        val_subjects = set(subjects[val_idx])
        train_mask = np.isin(subject_by_row, list(train_subjects))
        val_mask = np.isin(subject_by_row, list(val_subjects))
        folds.append(
            {
                "fold_id": fold_id,
                "train_mask": train_mask,
                "val_mask": val_mask,
                "n_train_subjects": len(train_subjects),
                "n_val_subjects": len(val_subjects),
                "train_positive_rate": float(y[train_mask].mean()),
                "val_positive_rate": float(y[val_mask].mean()),
            }
        )
    return folds


# %%
def binary_metric_dict(y_true: np.ndarray, y_prob: np.ndarray, threshold: float = 0.5) -> dict:
    y_true = y_true.astype(int)
    y_pred = (y_prob >= threshold).astype(int)
    if len(y_true) == 0:
        return {
            "auroc": np.nan,
            "auprc": np.nan,
            "sensitivity": np.nan,
            "specificity": np.nan,
            "ppv": np.nan,
            "npv": np.nan,
            "tp": 0,
            "fp": 0,
            "tn": 0,
            "fn": 0,
        }

    if len(np.unique(y_true)) == 2:
        auroc = roc_auc_score(y_true, y_prob)
        auprc = average_precision_score(y_true, y_prob)
    else:
        auroc = np.nan
        auprc = np.nan

    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    return {
        "auroc": auroc,
        "auprc": auprc,
        "sensitivity": tp / (tp + fn) if (tp + fn) else np.nan,
        "specificity": tn / (tn + fp) if (tn + fp) else np.nan,
        "ppv": tp / (tp + fp) if (tp + fp) else np.nan,
        "npv": tn / (tn + fn) if (tn + fn) else np.nan,
        "tp": int(tp),
        "fp": int(fp),
        "tn": int(tn),
        "fn": int(fn),
    }


def positive_weight(y: np.ndarray) -> float:
    pos = float(y.sum())
    neg = float(len(y) - pos)
    return neg / max(pos, 1.0)


# %% [markdown]
# ## ML baselines

# %%
def xgb_gpu_params(use_gpu: bool) -> dict:
    if not use_gpu:
        return {"tree_method": "hist"}

    xgboost = optional_import("xgboost")
    if xgboost is None:
        return {"tree_method": "hist"}

    major = int(xgboost.__version__.split(".")[0])
    if major >= 2:
        return {"tree_method": "hist", "device": "cuda"}
    return {"tree_method": "gpu_hist", "predictor": "gpu_predictor"}


def lgbm_gpu_params(use_gpu: bool) -> dict:
    return {"device_type": "gpu"} if use_gpu else {"device_type": "cpu"}


def suggest_ml_params(trial: optuna.Trial, model_name: str) -> dict:
    if model_name == "LR":
        return {
            "C": trial.suggest_float("C", 1e-3, 1e2, log=True),
            "penalty": trial.suggest_categorical("penalty", ["l1", "l2"]),
        }
    if model_name == "RF":
        return {
            "n_estimators": trial.suggest_int("n_estimators", 200, 800, step=100),
            "max_depth": trial.suggest_categorical("max_depth", [None, 4, 8, 12, 16, 24]),
            "min_samples_split": trial.suggest_categorical("min_samples_split", [2, 5, 10, 20]),
            "min_samples_leaf": trial.suggest_categorical("min_samples_leaf", [1, 2, 4, 8]),
            "max_features": trial.suggest_categorical("max_features", ["sqrt", "log2", 0.5]),
        }
    if model_name == "XGB":
        return {
            "n_estimators": trial.suggest_int("n_estimators", 200, 800, step=100),
            "max_depth": trial.suggest_int("max_depth", 2, 8),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "min_child_weight": trial.suggest_float("min_child_weight", 1.0, 20.0, log=True),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 1.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True),
        }
    if model_name == "LGBM":
        return {
            "n_estimators": trial.suggest_int("n_estimators", 200, 1000, step=100),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            "num_leaves": trial.suggest_int("num_leaves", 15, 127),
            "max_depth": trial.suggest_categorical("max_depth", [-1, 3, 5, 7, 9, 12]),
            "min_child_samples": trial.suggest_int("min_child_samples", 10, 100),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 1.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True),
        }
    raise ValueError(f"Unknown ML model: {model_name}")


def build_ml_estimator(model_name: str, params: dict, y_train: np.ndarray, random_state: int, use_gpu: bool):
    if model_name == "LR":
        return LogisticRegression(
            **params,
            solver="liblinear",
            class_weight="balanced",
            max_iter=2000,
            random_state=random_state,
        )
    if model_name == "RF":
        return RandomForestClassifier(
            **params,
            class_weight="balanced_subsample",
            n_jobs=-1,
            random_state=random_state,
        )
    if model_name == "XGB":
        xgboost = optional_import("xgboost")
        if xgboost is None:
            raise ImportError("xgboost is not installed. Install xgboost to train the XGB baseline.")
        return xgboost.XGBClassifier(
            **params,
            **xgb_gpu_params(use_gpu),
            objective="binary:logistic",
            eval_metric="aucpr",
            scale_pos_weight=positive_weight(y_train),
            random_state=random_state,
            n_jobs=-1,
        )
    if model_name == "LGBM":
        lightgbm = optional_import("lightgbm")
        if lightgbm is None:
            raise ImportError("lightgbm is not installed. Install lightgbm to train the LightGBM baseline.")
        return lightgbm.LGBMClassifier(
            **params,
            **lgbm_gpu_params(use_gpu),
            objective="binary",
            scale_pos_weight=positive_weight(y_train),
            random_state=random_state,
            n_jobs=-1,
            verbosity=-1,
        )
    raise ValueError(f"Unknown ML model: {model_name}")


def fit_ml_estimator(model_name: str, estimator, x_train: np.ndarray, y_train: np.ndarray, use_scaler: bool):
    scaler = StandardScaler() if use_scaler else None
    x_fit = scaler.fit_transform(x_train) if scaler is not None else x_train
    try:
        estimator.fit(x_fit, y_train.astype(int))
        return estimator, scaler, None
    except Exception as exc:
        if model_name == "XGB" and (
            estimator.get_params().get("device") == "cuda"
            or estimator.get_params().get("tree_method") == "gpu_hist"
        ):
            estimator = clone(estimator)
            fallback_params = {"tree_method": "hist"}
            if "device" in estimator.get_params():
                fallback_params["device"] = "cpu"
            if "predictor" in estimator.get_params():
                fallback_params["predictor"] = "auto"
            estimator.set_params(**fallback_params)
            estimator.fit(x_fit, y_train.astype(int))
            return estimator, scaler, f"XGBoost GPU fit failed and fell back to CPU: {exc}"
        if model_name == "LGBM" and estimator.get_params().get("device_type") == "gpu":
            estimator = clone(estimator)
            estimator.set_params(device_type="cpu")
            estimator.fit(x_fit, y_train.astype(int))
            return estimator, scaler, f"LightGBM GPU fit failed and fell back to CPU: {exc}"
        raise


def predict_ml_proba(estimator, scaler, x: np.ndarray) -> np.ndarray:
    x_eval = scaler.transform(x) if scaler is not None else x
    return estimator.predict_proba(x_eval)[:, 1]


def run_ml_tuning(
    model_name: str,
    data: ModelingData,
    folds: list[dict],
    output_dir: Path,
    model_dir: Path,
    n_trials: int,
    random_state: int,
    use_gpu: bool,
) -> dict | None:
    trial_rows = []
    fold_rows = []
    use_scaler = model_name == "LR"

    def objective(trial: optuna.Trial) -> float:
        params = suggest_ml_params(trial, model_name)
        current_fold_rows = []
        for fold in folds:
            train_mask = fold["train_mask"]
            val_mask = fold["val_mask"]
            estimator = build_ml_estimator(model_name, params, data.y_train[train_mask], random_state, use_gpu)
            estimator, scaler, fallback_reason = fit_ml_estimator(
                model_name,
                estimator,
                data.x_train_t[train_mask],
                data.y_train[train_mask],
                use_scaler=use_scaler,
            )
            val_prob = predict_ml_proba(estimator, scaler, data.x_train_t[val_mask])
            metrics = binary_metric_dict(data.y_train[val_mask], val_prob)
            row = {
                "model": model_name,
                "trial_id": trial.number + 1,
                "optuna_trial_number": trial.number,
                "fold_id": fold["fold_id"],
                "gpu_requested": bool(use_gpu and model_name in {"XGB", "LGBM"}),
                "fallback_reason": fallback_reason,
                **params,
                **metrics,
            }
            current_fold_rows.append(row)
            fold_rows.append(row)

        fold_df = pd.DataFrame(current_fold_rows)
        metric_cols = ["auroc", "auprc", "sensitivity", "specificity", "ppv", "npv"]
        row = {
            "model": model_name,
            "trial_id": trial.number + 1,
            "optuna_trial_number": trial.number,
            **params,
            **fold_df[metric_cols].mean(numeric_only=True).add_prefix("cv_mean_").to_dict(),
            **fold_df[metric_cols].std(numeric_only=True).add_prefix("cv_std_").to_dict(),
        }
        trial_rows.append(row)
        trial.set_user_attr("metrics", row)
        return row["cv_mean_auprc"]

    try:
        study = optuna.create_study(
            direction="maximize",
            sampler=optuna.samplers.TPESampler(seed=random_state),
            study_name=f"{model_name.lower()}_t_point_within_t_plus_2",
        )
        study.optimize(objective, n_trials=n_trials)
    except ImportError as exc:
        print(f"[{model_name}] skipped: {exc}")
        return None

    tuning_results = pd.DataFrame(trial_rows).sort_values(["cv_mean_auprc", "cv_mean_auroc"], ascending=False)
    cv_fold_metrics = pd.DataFrame(fold_rows)
    tuning_results.to_csv(output_dir / f"{model_name.lower()}_t_point_tuning_results.csv", index=False)
    cv_fold_metrics.to_csv(output_dir / f"{model_name.lower()}_t_point_cv_fold_metrics.csv", index=False)
    study.trials_dataframe(attrs=("number", "value", "params", "state")).to_csv(
        output_dir / f"{model_name.lower()}_t_point_optuna_trials.csv",
        index=False,
    )

    best_params = study.best_trial.params
    estimator = build_ml_estimator(model_name, best_params, data.y_train, random_state, use_gpu)
    estimator, scaler, fallback_reason = fit_ml_estimator(
        model_name,
        estimator,
        data.x_train_t,
        data.y_train,
        use_scaler=use_scaler,
    )
    test_prob = predict_ml_proba(estimator, scaler, data.x_test_t)
    test_metrics = binary_metric_dict(data.y_test, test_prob)
    test_metrics.update(
        {
            "model": model_name,
            "split": "test",
            "target": "within_t_plus_2",
            "input": "current_t_point_only",
            "optuna_best_value": float(study.best_value),
            "gpu_requested": bool(use_gpu and model_name in {"XGB", "LGBM"}),
            "fallback_reason": fallback_reason,
            **best_params,
        }
    )

    predictions = data.meta_test.copy()
    predictions["y_within_t_plus_2_true"] = data.y_test.astype(int)
    predictions[f"{model_name.lower()}_t_point_prob"] = test_prob
    predictions[f"{model_name.lower()}_t_point_pred_0_5"] = (test_prob >= 0.5).astype(int)
    pd.DataFrame([test_metrics]).to_csv(output_dir / f"{model_name.lower()}_t_point_test_metrics.csv", index=False)
    predictions.to_csv(output_dir / f"{model_name.lower()}_t_point_test_predictions.csv", index=False)
    joblib.dump(
        {
            "model": estimator,
            "scaler": scaler,
            "best_params": best_params,
            "cv_metrics": study.best_trial.user_attrs["metrics"],
            "test_metrics": test_metrics,
            "input": "current_t_point_only",
            "target": "within_t_plus_2",
        },
        model_dir / f"{model_name.lower()}_t_point_within_t_plus_2.joblib",
    )
    return test_metrics


# %% [markdown]
# ## Single-output LSTM

# %%
class MLPTPointClassifier(nn.Module):
    def __init__(self, input_size: int, hidden_size: int, num_layers: int, dropout: float):
        super().__init__()
        layers = []
        in_size = input_size
        for _ in range(num_layers):
            layers.extend(
                [
                    nn.Linear(in_size, hidden_size),
                    nn.ReLU(),
                    nn.Dropout(dropout),
                ]
            )
            in_size = hidden_size
        layers.append(nn.Linear(in_size, 1))
        self.network = nn.Sequential(*layers)

    def forward(self, x):
        return self.network(x).squeeze(-1)


def make_binary_loader(
    x: np.ndarray,
    y: np.ndarray,
    batch_size: int,
    shuffle: bool,
    pin_memory: bool,
    random_state: int,
) -> DataLoader:
    dataset = TensorDataset(torch.from_numpy(x).float(), torch.from_numpy(y).float())
    generator = torch.Generator().manual_seed(random_state)
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        generator=generator,
        num_workers=0,
        pin_memory=pin_memory,
    )


def predict_binary_torch_proba(
    model: nn.Module,
    x: np.ndarray,
    batch_size: int,
    device: torch.device,
    non_blocking: bool,
    amp_enabled: bool,
) -> np.ndarray:
    model.eval()
    dummy_y = np.zeros(len(x), dtype=np.float32)
    loader = make_binary_loader(x, dummy_y, batch_size, shuffle=False, pin_memory=device.type == "cuda", random_state=0)
    probs = []
    with torch.no_grad():
        for xb, _ in loader:
            xb = xb.to(device, non_blocking=non_blocking)
            with torch.amp.autocast(device_type=device.type, enabled=amp_enabled):
                logits = model(xb)
            probs.append(torch.sigmoid(logits.float()).detach().cpu().numpy())
    return np.concatenate(probs, axis=0)


def suggest_mlp_params(trial: optuna.Trial) -> dict:
    return {
        "hidden_size": trial.suggest_categorical("hidden_size", [64, 128, 256, 512]),
        "num_layers": trial.suggest_int("num_layers", 1, 3),
        "dropout": trial.suggest_float("dropout", 0.0, 0.5),
        "lr": trial.suggest_float("lr", 1e-4, 3e-3, log=True),
        "batch_size": trial.suggest_categorical("batch_size", [32, 64, 128]),
        "weight_decay": trial.suggest_float("weight_decay", 1e-6, 1e-3, log=True),
    }


def train_mlp_fold(
    params: dict,
    fold: dict,
    data: ModelingData,
    max_epochs: int,
    patience: int,
    random_state: int,
    device: torch.device,
    amp_enabled: bool,
) -> tuple[dict, dict]:
    train_mask = fold["train_mask"]
    val_mask = fold["val_mask"]
    pin_memory = device.type == "cuda"
    non_blocking = device.type == "cuda"

    scaler_obj = StandardScaler()
    x_fold_train = scaler_obj.fit_transform(data.x_train_t[train_mask]).astype(np.float32)
    x_fold_val = scaler_obj.transform(data.x_train_t[val_mask]).astype(np.float32)

    model = MLPTPointClassifier(
        input_size=data.x_train_t.shape[1],
        hidden_size=params["hidden_size"],
        num_layers=params["num_layers"],
        dropout=params["dropout"],
    ).to(device)
    pos_weight = torch.tensor([positive_weight(data.y_train[train_mask])], dtype=torch.float32, device=device)
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    optimizer = torch.optim.AdamW(model.parameters(), lr=params["lr"], weight_decay=params["weight_decay"])
    scaler = torch.amp.GradScaler("cuda", enabled=amp_enabled)
    train_loader = make_binary_loader(
        x_fold_train,
        data.y_train[train_mask],
        params["batch_size"],
        shuffle=True,
        pin_memory=pin_memory,
        random_state=random_state,
    )

    best_state = None
    best_score = -np.inf
    best_epoch = 0
    epochs_without_improve = 0
    history = []

    for epoch in range(1, max_epochs + 1):
        model.train()
        losses = []
        for xb, yb in train_loader:
            xb = xb.to(device, non_blocking=non_blocking)
            yb = yb.to(device, non_blocking=non_blocking)
            optimizer.zero_grad(set_to_none=True)
            with torch.amp.autocast(device_type=device.type, enabled=amp_enabled):
                logits = model(xb)
                loss = criterion(logits, yb)
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            scaler.step(optimizer)
            scaler.update()
            losses.append(float(loss.detach().cpu()))

        val_prob = predict_binary_torch_proba(model, x_fold_val, params["batch_size"], device, non_blocking, amp_enabled)
        metrics = binary_metric_dict(data.y_train[val_mask], val_prob)
        score = metrics["auprc"] if not np.isnan(metrics["auprc"]) else -np.inf
        history.append({"epoch": epoch, "train_loss": float(np.mean(losses)), **metrics})

        if best_state is None or score > best_score:
            best_score = score
            best_epoch = epoch
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
            epochs_without_improve = 0
        else:
            epochs_without_improve += 1
            if epochs_without_improve >= patience:
                break

    model.load_state_dict(best_state)
    val_prob = predict_binary_torch_proba(model, x_fold_val, params["batch_size"], device, non_blocking, amp_enabled)
    final_metrics = binary_metric_dict(data.y_train[val_mask], val_prob)
    final_metrics.update({"fold_id": fold["fold_id"], "best_epoch": best_epoch, "epochs_run": len(history), "best_score": best_score})

    if device.type == "cuda":
        torch.cuda.empty_cache()
    return final_metrics, {"history": history, "state_dict": best_state, "scaler": scaler_obj}


def train_mlp_full(
    params: dict,
    data: ModelingData,
    epochs: int,
    random_state: int,
    device: torch.device,
    amp_enabled: bool,
) -> dict:
    pin_memory = device.type == "cuda"
    non_blocking = device.type == "cuda"
    scaler_obj = StandardScaler()
    x_train_scaled = scaler_obj.fit_transform(data.x_train_t).astype(np.float32)

    model = MLPTPointClassifier(
        input_size=data.x_train_t.shape[1],
        hidden_size=params["hidden_size"],
        num_layers=params["num_layers"],
        dropout=params["dropout"],
    ).to(device)
    pos_weight = torch.tensor([positive_weight(data.y_train)], dtype=torch.float32, device=device)
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    optimizer = torch.optim.AdamW(model.parameters(), lr=params["lr"], weight_decay=params["weight_decay"])
    scaler = torch.amp.GradScaler("cuda", enabled=amp_enabled)
    train_loader = make_binary_loader(x_train_scaled, data.y_train, params["batch_size"], True, pin_memory, random_state)
    history = []

    for epoch in range(1, epochs + 1):
        model.train()
        losses = []
        for xb, yb in train_loader:
            xb = xb.to(device, non_blocking=non_blocking)
            yb = yb.to(device, non_blocking=non_blocking)
            optimizer.zero_grad(set_to_none=True)
            with torch.amp.autocast(device_type=device.type, enabled=amp_enabled):
                logits = model(xb)
                loss = criterion(logits, yb)
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            scaler.step(optimizer)
            scaler.update()
            losses.append(float(loss.detach().cpu()))
        history.append({"epoch": epoch, "train_loss": float(np.mean(losses))})

    state_dict = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
    if device.type == "cuda":
        torch.cuda.empty_cache()
    return {"state_dict": state_dict, "history": history, "epochs_run": epochs, "scaler": scaler_obj}


def run_mlp_tuning(
    data: ModelingData,
    folds: list[dict],
    output_dir: Path,
    model_dir: Path,
    n_trials: int,
    max_epochs: int,
    patience: int,
    random_state: int,
    device: torch.device,
    amp_enabled: bool,
) -> dict:
    trial_rows = []
    fold_rows = []
    history_rows = []

    def objective(trial: optuna.Trial) -> float:
        params = suggest_mlp_params(trial)
        current_rows = []
        fold_epochs = []
        for fold in folds:
            metrics, artifact = train_mlp_fold(params, fold, data, max_epochs, patience, random_state, device, amp_enabled)
            row = {
                "model": "MLP",
                "trial_id": trial.number + 1,
                "optuna_trial_number": trial.number,
                **params,
                **metrics,
            }
            current_rows.append(row)
            fold_rows.append(row)
            fold_epochs.append(metrics["best_epoch"])

            history_df = pd.DataFrame(artifact["history"])
            history_df.insert(0, "fold_id", fold["fold_id"])
            history_df.insert(0, "trial_id", trial.number + 1)
            history_df.insert(0, "optuna_trial_number", trial.number)
            history_rows.append(history_df)

        fold_df = pd.DataFrame(current_rows)
        metric_cols = ["auroc", "auprc", "sensitivity", "specificity", "ppv", "npv", "best_epoch", "epochs_run"]
        row = {
            "model": "MLP",
            "trial_id": trial.number + 1,
            "optuna_trial_number": trial.number,
            **params,
            "final_epochs": int(max(1, round(float(np.mean(fold_epochs))))),
            **fold_df[metric_cols].mean(numeric_only=True).add_prefix("cv_mean_").to_dict(),
            **fold_df[metric_cols].std(numeric_only=True).add_prefix("cv_std_").to_dict(),
        }
        trial_rows.append(row)
        trial.set_user_attr("metrics", row)
        trial.set_user_attr("final_epochs", row["final_epochs"])
        return row["cv_mean_auprc"]

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=random_state),
        study_name="mlp_t_point_within_t_plus_2",
    )
    study.optimize(objective, n_trials=n_trials)

    tuning_results = pd.DataFrame(trial_rows).sort_values(["cv_mean_auprc", "cv_mean_auroc"], ascending=False)
    pd.DataFrame(fold_rows).to_csv(output_dir / "mlp_t_point_cv_fold_metrics.csv", index=False)
    tuning_results.to_csv(output_dir / "mlp_t_point_tuning_results.csv", index=False)
    if history_rows:
        pd.concat(history_rows, ignore_index=True).to_csv(output_dir / "mlp_t_point_cv_fold_history.csv", index=False)
    study.trials_dataframe(attrs=("number", "value", "params", "state")).to_csv(
        output_dir / "mlp_t_point_optuna_trials.csv",
        index=False,
    )

    best_params = study.best_trial.params
    final_artifact = train_mlp_full(
        best_params,
        data,
        epochs=study.best_trial.user_attrs["final_epochs"],
        random_state=random_state,
        device=device,
        amp_enabled=amp_enabled,
    )
    model = MLPTPointClassifier(
        input_size=data.x_train_t.shape[1],
        hidden_size=best_params["hidden_size"],
        num_layers=best_params["num_layers"],
        dropout=best_params["dropout"],
    ).to(device)
    model.load_state_dict(final_artifact["state_dict"])
    x_test_scaled = final_artifact["scaler"].transform(data.x_test_t).astype(np.float32)
    test_prob = predict_binary_torch_proba(model, x_test_scaled, best_params["batch_size"], device, device.type == "cuda", amp_enabled)
    test_metrics = binary_metric_dict(data.y_test, test_prob)
    test_metrics.update(
        {
            "model": "MLP",
            "split": "test",
            "target": "within_t_plus_2",
            "input": "current_t_point_only",
            "optuna_best_value": float(study.best_value),
            "optuna_best_trial_number": int(study.best_trial.number),
            "final_epochs": final_artifact["epochs_run"],
            "device": str(device),
            **best_params,
        }
    )

    predictions = data.meta_test.copy()
    predictions["y_within_t_plus_2_true"] = data.y_test.astype(int)
    predictions["mlp_t_point_prob"] = test_prob
    predictions["mlp_t_point_pred_0_5"] = (test_prob >= 0.5).astype(int)
    pd.DataFrame([test_metrics]).to_csv(output_dir / "mlp_t_point_test_metrics.csv", index=False)
    predictions.to_csv(output_dir / "mlp_t_point_test_predictions.csv", index=False)

    torch.save(
        {
            "model_architecture": "mlp_t_point_within_t_plus_2",
            "model_state_dict": final_artifact["state_dict"],
            "scaler": final_artifact["scaler"],
            "params": best_params,
            "cv_metrics": study.best_trial.user_attrs["metrics"],
            "optuna_best_value": float(study.best_value),
            "optuna_best_trial_number": int(study.best_trial.number),
            "final_train_history": final_artifact["history"],
            "test_metrics": test_metrics,
            "input_size": int(data.x_train_t.shape[1]),
            "output_size": 1,
            "target": "within_t_plus_2",
            "device": str(device),
            "amp_enabled": amp_enabled,
        },
        model_dir / "mlp_t_point_within_t_plus_2_best_model.pt",
    )
    return test_metrics


class LSTMWithinClassifier(nn.Module):
    def __init__(self, input_size: int, hidden_size: int, num_layers: int, dropout: float):
        super().__init__()
        lstm_dropout = dropout if num_layers > 1 else 0.0
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=lstm_dropout,
        )
        self.head = nn.Sequential(nn.Dropout(dropout), nn.Linear(hidden_size, 1))

    def forward(self, x):
        _, (hidden, _) = self.lstm(x)
        return self.head(hidden[-1]).squeeze(-1)


def make_lstm_loader(
    x: np.ndarray,
    y: np.ndarray,
    batch_size: int,
    shuffle: bool,
    pin_memory: bool,
    random_state: int,
) -> DataLoader:
    dataset = TensorDataset(torch.from_numpy(x).float(), torch.from_numpy(y).float())
    generator = torch.Generator().manual_seed(random_state)
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        generator=generator,
        num_workers=0,
        pin_memory=pin_memory,
    )


def predict_lstm_proba(model: nn.Module, x: np.ndarray, batch_size: int, device: torch.device, non_blocking: bool, amp_enabled: bool) -> np.ndarray:
    model.eval()
    dummy_y = np.zeros(len(x), dtype=np.float32)
    loader = make_lstm_loader(x, dummy_y, batch_size, shuffle=False, pin_memory=device.type == "cuda", random_state=0)
    probs = []
    with torch.no_grad():
        for xb, _ in loader:
            xb = xb.to(device, non_blocking=non_blocking)
            with torch.amp.autocast(device_type=device.type, enabled=amp_enabled):
                logits = model(xb)
            probs.append(torch.sigmoid(logits.float()).detach().cpu().numpy())
    return np.concatenate(probs, axis=0)


def suggest_lstm_params(trial: optuna.Trial) -> dict:
    num_layers = trial.suggest_int("num_layers", 1, 3)
    return {
        "hidden_size": trial.suggest_categorical("hidden_size", [32, 64, 128, 256]),
        "num_layers": num_layers,
        "dropout": trial.suggest_float("dropout", 0.0, 0.5),
        "lr": trial.suggest_float("lr", 1e-4, 3e-3, log=True),
        "batch_size": trial.suggest_categorical("batch_size", [32, 64, 128]),
        "weight_decay": trial.suggest_float("weight_decay", 1e-6, 1e-3, log=True),
    }


def train_lstm_fold(
    params: dict,
    fold: dict,
    data: ModelingData,
    max_epochs: int,
    patience: int,
    random_state: int,
    device: torch.device,
    amp_enabled: bool,
) -> tuple[dict, dict]:
    train_mask = fold["train_mask"]
    val_mask = fold["val_mask"]
    pin_memory = device.type == "cuda"
    non_blocking = device.type == "cuda"

    model = LSTMWithinClassifier(
        input_size=data.x_train_seq.shape[2],
        hidden_size=params["hidden_size"],
        num_layers=params["num_layers"],
        dropout=params["dropout"],
    ).to(device)
    pos_weight = torch.tensor([positive_weight(data.y_train[train_mask])], dtype=torch.float32, device=device)
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    optimizer = torch.optim.AdamW(model.parameters(), lr=params["lr"], weight_decay=params["weight_decay"])
    scaler = torch.amp.GradScaler("cuda", enabled=amp_enabled)
    train_loader = make_lstm_loader(
        data.x_train_seq[train_mask],
        data.y_train[train_mask],
        params["batch_size"],
        shuffle=True,
        pin_memory=pin_memory,
        random_state=random_state,
    )

    best_state = None
    best_score = -np.inf
    best_epoch = 0
    epochs_without_improve = 0
    history = []

    for epoch in range(1, max_epochs + 1):
        model.train()
        losses = []
        for xb, yb in train_loader:
            xb = xb.to(device, non_blocking=non_blocking)
            yb = yb.to(device, non_blocking=non_blocking)
            optimizer.zero_grad(set_to_none=True)
            with torch.amp.autocast(device_type=device.type, enabled=amp_enabled):
                logits = model(xb)
                loss = criterion(logits, yb)
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            scaler.step(optimizer)
            scaler.update()
            losses.append(float(loss.detach().cpu()))

        val_prob = predict_lstm_proba(
            model,
            data.x_train_seq[val_mask],
            params["batch_size"],
            device,
            non_blocking,
            amp_enabled,
        )
        metrics = binary_metric_dict(data.y_train[val_mask], val_prob)
        score = metrics["auprc"] if not np.isnan(metrics["auprc"]) else -np.inf
        history.append({"epoch": epoch, "train_loss": float(np.mean(losses)), **metrics})

        if best_state is None or score > best_score:
            best_score = score
            best_epoch = epoch
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
            epochs_without_improve = 0
        else:
            epochs_without_improve += 1
            if epochs_without_improve >= patience:
                break

    model.load_state_dict(best_state)
    val_prob = predict_lstm_proba(model, data.x_train_seq[val_mask], params["batch_size"], device, non_blocking, amp_enabled)
    final_metrics = binary_metric_dict(data.y_train[val_mask], val_prob)
    final_metrics.update({"fold_id": fold["fold_id"], "best_epoch": best_epoch, "epochs_run": len(history), "best_score": best_score})

    if device.type == "cuda":
        torch.cuda.empty_cache()
    return final_metrics, {"history": history, "state_dict": best_state}


def train_lstm_full(
    params: dict,
    data: ModelingData,
    epochs: int,
    random_state: int,
    device: torch.device,
    amp_enabled: bool,
) -> dict:
    pin_memory = device.type == "cuda"
    non_blocking = device.type == "cuda"
    model = LSTMWithinClassifier(
        input_size=data.x_train_seq.shape[2],
        hidden_size=params["hidden_size"],
        num_layers=params["num_layers"],
        dropout=params["dropout"],
    ).to(device)
    pos_weight = torch.tensor([positive_weight(data.y_train)], dtype=torch.float32, device=device)
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    optimizer = torch.optim.AdamW(model.parameters(), lr=params["lr"], weight_decay=params["weight_decay"])
    scaler = torch.amp.GradScaler("cuda", enabled=amp_enabled)
    train_loader = make_lstm_loader(data.x_train_seq, data.y_train, params["batch_size"], True, pin_memory, random_state)
    history = []

    for epoch in range(1, epochs + 1):
        model.train()
        losses = []
        for xb, yb in train_loader:
            xb = xb.to(device, non_blocking=non_blocking)
            yb = yb.to(device, non_blocking=non_blocking)
            optimizer.zero_grad(set_to_none=True)
            with torch.amp.autocast(device_type=device.type, enabled=amp_enabled):
                logits = model(xb)
                loss = criterion(logits, yb)
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            scaler.step(optimizer)
            scaler.update()
            losses.append(float(loss.detach().cpu()))
        history.append({"epoch": epoch, "train_loss": float(np.mean(losses))})

    state_dict = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
    if device.type == "cuda":
        torch.cuda.empty_cache()
    return {"state_dict": state_dict, "history": history, "epochs_run": epochs}


def run_lstm_tuning(
    data: ModelingData,
    folds: list[dict],
    output_dir: Path,
    model_dir: Path,
    n_trials: int,
    max_epochs: int,
    patience: int,
    random_state: int,
    device: torch.device,
    amp_enabled: bool,
) -> dict:
    trial_rows = []
    fold_rows = []
    history_rows = []

    def objective(trial: optuna.Trial) -> float:
        params = suggest_lstm_params(trial)
        current_rows = []
        fold_epochs = []
        for fold in folds:
            metrics, artifact = train_lstm_fold(params, fold, data, max_epochs, patience, random_state, device, amp_enabled)
            row = {
                "model": "LSTM",
                "trial_id": trial.number + 1,
                "optuna_trial_number": trial.number,
                **params,
                **metrics,
            }
            current_rows.append(row)
            fold_rows.append(row)
            fold_epochs.append(metrics["best_epoch"])

            history_df = pd.DataFrame(artifact["history"])
            history_df.insert(0, "fold_id", fold["fold_id"])
            history_df.insert(0, "trial_id", trial.number + 1)
            history_df.insert(0, "optuna_trial_number", trial.number)
            history_rows.append(history_df)

        fold_df = pd.DataFrame(current_rows)
        metric_cols = ["auroc", "auprc", "sensitivity", "specificity", "ppv", "npv", "best_epoch", "epochs_run"]
        row = {
            "model": "LSTM",
            "trial_id": trial.number + 1,
            "optuna_trial_number": trial.number,
            **params,
            "final_epochs": int(max(1, round(float(np.mean(fold_epochs))))),
            **fold_df[metric_cols].mean(numeric_only=True).add_prefix("cv_mean_").to_dict(),
            **fold_df[metric_cols].std(numeric_only=True).add_prefix("cv_std_").to_dict(),
        }
        trial_rows.append(row)
        trial.set_user_attr("metrics", row)
        trial.set_user_attr("final_epochs", row["final_epochs"])
        return row["cv_mean_auprc"]

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=random_state),
        study_name="single_output_lstm_within_t_plus_2",
    )
    study.optimize(objective, n_trials=n_trials)

    tuning_results = pd.DataFrame(trial_rows).sort_values(["cv_mean_auprc", "cv_mean_auroc"], ascending=False)
    pd.DataFrame(fold_rows).to_csv(output_dir / "lstm_within_t_plus_2_cv_fold_metrics.csv", index=False)
    tuning_results.to_csv(output_dir / "lstm_within_t_plus_2_tuning_results.csv", index=False)
    if history_rows:
        pd.concat(history_rows, ignore_index=True).to_csv(output_dir / "lstm_within_t_plus_2_cv_fold_history.csv", index=False)
    study.trials_dataframe(attrs=("number", "value", "params", "state")).to_csv(
        output_dir / "lstm_within_t_plus_2_optuna_trials.csv",
        index=False,
    )

    best_params = study.best_trial.params
    final_artifact = train_lstm_full(
        best_params,
        data,
        epochs=study.best_trial.user_attrs["final_epochs"],
        random_state=random_state,
        device=device,
        amp_enabled=amp_enabled,
    )
    model = LSTMWithinClassifier(
        input_size=data.x_train_seq.shape[2],
        hidden_size=best_params["hidden_size"],
        num_layers=best_params["num_layers"],
        dropout=best_params["dropout"],
    ).to(device)
    model.load_state_dict(final_artifact["state_dict"])
    test_prob = predict_lstm_proba(model, data.x_test_seq, best_params["batch_size"], device, device.type == "cuda", amp_enabled)
    test_metrics = binary_metric_dict(data.y_test, test_prob)
    test_metrics.update(
        {
            "model": "LSTM",
            "split": "test",
            "target": "within_t_plus_2",
            "input": "sequence_t_minus_3_to_t",
            "optuna_best_value": float(study.best_value),
            "optuna_best_trial_number": int(study.best_trial.number),
            "final_epochs": final_artifact["epochs_run"],
            **best_params,
        }
    )

    predictions = data.meta_test.copy()
    predictions["y_within_t_plus_2_true"] = data.y_test.astype(int)
    predictions["lstm_within_t_plus_2_prob"] = test_prob
    predictions["lstm_within_t_plus_2_pred_0_5"] = (test_prob >= 0.5).astype(int)
    pd.DataFrame([test_metrics]).to_csv(output_dir / "lstm_within_t_plus_2_test_metrics.csv", index=False)
    predictions.to_csv(output_dir / "lstm_within_t_plus_2_test_predictions.csv", index=False)

    torch.save(
        {
            "model_architecture": "lstm_single_output_within_t_plus_2",
            "model_state_dict": final_artifact["state_dict"],
            "params": best_params,
            "cv_metrics": study.best_trial.user_attrs["metrics"],
            "optuna_best_value": float(study.best_value),
            "optuna_best_trial_number": int(study.best_trial.number),
            "final_train_history": final_artifact["history"],
            "test_metrics": test_metrics,
            "input_size": int(data.x_train_seq.shape[2]),
            "sequence_length": int(data.x_train_seq.shape[1]),
            "output_size": 1,
            "target": "within_t_plus_2",
            "device": str(device),
            "amp_enabled": amp_enabled,
        },
        model_dir / "lstm_within_t_plus_2_best_model.pt",
    )
    with open(model_dir / "lstm_within_t_plus_2_best_model_config.json", "w", encoding="utf-8") as f:
        json.dump(
            as_jsonable(
                {
                    "model_architecture": "lstm_single_output_within_t_plus_2",
                    "params": best_params,
                    "cv_metrics": study.best_trial.user_attrs["metrics"],
                    "optuna_best_value": float(study.best_value),
                    "optuna_best_trial_number": int(study.best_trial.number),
                    "final_train_history": final_artifact["history"],
                    "test_metrics": test_metrics,
                    "input_size": int(data.x_train_seq.shape[2]),
                    "sequence_length": int(data.x_train_seq.shape[1]),
                    "output_size": 1,
                    "target": "within_t_plus_2",
                    "device": str(device),
                    "amp_enabled": amp_enabled,
                }
            ),
            f,
            indent=2,
            ensure_ascii=False,
        )
    return test_metrics


# %%
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train t-point ML baselines and single-output within t+2 LSTM.")
    parser.add_argument("--n-folds", type=int, default=5)
    parser.add_argument("--n-trials-ml", type=int, default=30)
    parser.add_argument("--n-trials-mlp", type=int, default=30)
    parser.add_argument("--n-trials-lstm", type=int, default=30)
    parser.add_argument("--max-epochs", type=int, default=25)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument(
        "--allow-partial-target-window",
        action="store_true",
        help="Use rows whose t+1 or t+2 target is unavailable. Default keeps only full t, t+1, t+2 windows.",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=["LR", "RF", "XGB", "LGBM", "MLP", "LSTM"],
        choices=["LR", "RF", "XGB", "LGBM", "MLP", "LSTM"],
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    seed_everything(args.random_state)
    project_dir = resolve_project_dir()
    output_dir = project_dir / "outputs" / "modeling" / "within_t_plus_2"
    model_dir = project_dir / "models" / "within_t_plus_2"
    output_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    amp_enabled = device.type == "cuda"
    print(f"project_dir: {project_dir}")
    print(f"device: {device}")
    if device.type == "cuda":
        print(f"gpu: {torch.cuda.get_device_name(0)}")

    data = load_modeling_data(project_dir, require_full_target_window=not args.allow_partial_target_window)
    folds = make_subject_cv_folds(data.meta_train, data.y_train, args.n_folds, args.random_state)
    print(
        "data:",
        {
            "x_train_seq": data.x_train_seq.shape,
            "x_train_t": data.x_train_t.shape,
            "train_positive_rate": float(data.y_train.mean()),
            "n_folds": len(folds),
            "target_window": "partial_allowed" if args.allow_partial_target_window else "full_t_to_t_plus_2_only",
        },
    )

    test_metric_rows = []
    for model_name in [name for name in args.models if name not in {"MLP", "LSTM"}]:
        print(f"\n=== {model_name}: current t-point ML baseline ===")
        result = run_ml_tuning(
            model_name=model_name,
            data=data,
            folds=folds,
            output_dir=output_dir,
            model_dir=model_dir,
            n_trials=args.n_trials_ml,
            random_state=args.random_state,
            use_gpu=device.type == "cuda",
        )
        if result is not None:
            test_metric_rows.append(result)

    if "MLP" in args.models:
        print("\n=== MLP: current t-point deep learning baseline ===")
        test_metric_rows.append(
            run_mlp_tuning(
                data=data,
                folds=folds,
                output_dir=output_dir,
                model_dir=model_dir,
                n_trials=args.n_trials_mlp,
                max_epochs=args.max_epochs,
                patience=args.patience,
                random_state=args.random_state,
                device=device,
                amp_enabled=amp_enabled,
            )
        )

    if "LSTM" in args.models:
        print("\n=== LSTM: sequence t-3 through t, single within t+2 output ===")
        test_metric_rows.append(
            run_lstm_tuning(
                data=data,
                folds=folds,
                output_dir=output_dir,
                model_dir=model_dir,
                n_trials=args.n_trials_lstm,
                max_epochs=args.max_epochs,
                patience=args.patience,
                random_state=args.random_state,
                device=device,
                amp_enabled=amp_enabled,
            )
        )

    if test_metric_rows:
        summary = pd.DataFrame(test_metric_rows).sort_values("auprc", ascending=False)
        summary.to_csv(output_dir / "within_t_plus_2_test_metrics_summary.csv", index=False)
        print("\nTest metrics summary")
        print(summary[["model", "input", "auprc", "auroc", "sensitivity", "specificity", "ppv", "npv"]])


if __name__ == "__main__":
    main()
