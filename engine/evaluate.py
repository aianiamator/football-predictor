"""Evaluation metrics for 1X2 forecasts.

Separates two questions that are constantly conflated:

  1. "Did the model name the right winner?"  -> accuracy, precision, recall, F1
  2. "Were the probabilities honest?"        -> Brier, log loss, calibration

The second matters more for this product. A forecast that says 45% and is right
45% of the time is doing its job even when the argmax is wrong, and a model with
slightly lower accuracy but better calibration is the better forecaster.

Nothing here changes a forecast. It only measures them.
"""
from __future__ import annotations

import math

import numpy as np

OUTCOMES = ("H", "D", "A")
EPS = 1e-15


# --------------------------------------------------------------------------
# Proper scoring rules
# --------------------------------------------------------------------------

def log_loss(probs: np.ndarray, y: np.ndarray) -> float:
    """Mean negative log probability of what actually happened. Lower is better."""
    p = np.clip(probs[np.arange(len(y)), y], EPS, 1.0)
    return float(-np.mean(np.log(p)))


def brier(probs: np.ndarray, y: np.ndarray) -> float:
    """Multiclass Brier score: mean squared error against the one-hot outcome.

    Ranges 0 (perfect) to 2 (maximally wrong). Unlike log loss it is bounded,
    so a single confident miss cannot dominate the average.
    """
    onehot = np.zeros_like(probs)
    onehot[np.arange(len(y)), y] = 1.0
    return float(np.mean(np.sum((probs - onehot) ** 2, axis=1)))


def brier_skill_score(probs: np.ndarray, y: np.ndarray, reference: np.ndarray) -> float:
    """Fractional improvement in Brier over a reference forecast. >0 is better."""
    b, r = brier(probs, y), brier(reference, y)
    return float(1.0 - b / r) if r > 0 else float("nan")


# --------------------------------------------------------------------------
# Classification metrics
# --------------------------------------------------------------------------

def confusion(pred: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Rows = actual, columns = predicted, in H/D/A order."""
    m = np.zeros((3, 3), dtype=int)
    for a, p in zip(y, pred):
        m[a, p] += 1
    return m


def per_class(pred: np.ndarray, y: np.ndarray) -> dict:
    """Precision, recall and F1 for each of H, D, A."""
    out = {}
    for i, name in enumerate(OUTCOMES):
        tp = int(((pred == i) & (y == i)).sum())
        fp = int(((pred == i) & (y != i)).sum())
        fn = int(((pred != i) & (y == i)).sum())
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        out[name] = {"precision": prec, "recall": rec, "f1": f1,
                     "support": int((y == i).sum()), "predicted": int((pred == i).sum())}
    return out


def balanced_accuracy(pred: np.ndarray, y: np.ndarray) -> float:
    """Mean per-class recall.

    Reported because plain accuracy hides the draw problem: a model that never
    names a draw can still look fine on accuracy while scoring 0 recall on a
    quarter of all matches.
    """
    recalls = [((pred == i) & (y == i)).sum() / max((y == i).sum(), 1) for i in range(3)]
    return float(np.mean(recalls))


# --------------------------------------------------------------------------
# Calibration
# --------------------------------------------------------------------------

def reliability(probs: np.ndarray, y: np.ndarray, n_bins: int = 10) -> list[dict]:
    """Pooled reliability over all three outcomes.

    Every match contributes three (predicted, happened?) pairs. A calibrated
    model has observed frequency ~ mean predicted in every bin.
    """
    p = probs.reshape(-1)
    onehot = np.zeros_like(probs)
    onehot[np.arange(len(y)), y] = 1.0
    hit = onehot.reshape(-1)

    edges = np.linspace(0.0, 1.0, n_bins + 1)
    rows = []
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        m = (p >= lo) & (p < hi) if i < n_bins - 1 else (p >= lo) & (p <= hi)
        n = int(m.sum())
        rows.append({
            "bin": f"{lo:.1f}-{hi:.1f}", "n": n,
            "mean_predicted": float(p[m].mean()) if n else None,
            "observed": float(hit[m].mean()) if n else None,
            "gap": float(hit[m].mean() - p[m].mean()) if n else None,
        })
    return rows


def expected_calibration_error(probs: np.ndarray, y: np.ndarray, n_bins: int = 10) -> float:
    """ECE: sample-weighted mean |observed - predicted| across reliability bins."""
    rows = reliability(probs, y, n_bins)
    total = sum(r["n"] for r in rows)
    if not total:
        return float("nan")
    return float(sum(r["n"] * abs(r["gap"]) for r in rows if r["n"]) / total)


def class_calibration(probs: np.ndarray, y: np.ndarray, cls: int, bins) -> list[dict]:
    """Calibration for ONE outcome, e.g. the draw, at custom bin edges."""
    p = probs[:, cls]
    hit = (y == cls).astype(float)
    rows = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (p >= lo) & (p < hi)
        n = int(m.sum())
        if n:
            rows.append({"band": f"{lo:.2f}-{hi:.2f}", "n": n,
                         "mean_predicted": float(p[m].mean()),
                         "observed": float(hit[m].mean()),
                         "gap": float(hit[m].mean() - p[m].mean())})
    return rows


# --------------------------------------------------------------------------
# Uncertainty description (does not alter any forecast)
# --------------------------------------------------------------------------

def entropy(probs: np.ndarray) -> np.ndarray:
    """Shannon entropy in bits, 0 (certain) to log2(3)=1.585 (no information)."""
    p = np.clip(probs, EPS, 1.0)
    return (-np.sum(p * np.log2(p), axis=1)).astype(float)


def describe(probs: np.ndarray) -> dict:
    """Per-match uncertainty measures used by the decision layer."""
    srt = np.sort(probs, axis=1)[:, ::-1]
    return {
        "top": srt[:, 0],
        "second": srt[:, 1],
        "margin": srt[:, 0] - srt[:, 1],
        "entropy": entropy(probs),
        "draw_prob": probs[:, 1],
        "home_away_gap": np.abs(probs[:, 0] - probs[:, 2]),
    }


# --------------------------------------------------------------------------
# Statistical significance
# --------------------------------------------------------------------------

def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a proportion. Better than the normal
    approximation at the sample sizes and rates seen here."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = successes / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def paired_score_test(a: np.ndarray, b: np.ndarray) -> dict:
    """Paired comparison of two per-match score arrays (lower = better).

    Uses the SAME matches for both models, so the pairing removes match
    difficulty as a source of variance. Reports the mean difference with a
    normal-approximation confidence interval and a two-sided p-value.
    """
    d = np.asarray(a, float) - np.asarray(b, float)
    n = len(d)
    if n < 2:
        return {"n": n, "mean_diff": float("nan"), "p_value": float("nan")}
    mean = float(d.mean())
    se = float(d.std(ddof=1) / math.sqrt(n))
    if se == 0:
        return {"n": n, "mean_diff": mean, "se": 0.0, "z": float("nan"),
                "p_value": float("nan"), "ci95": (mean, mean)}
    z = mean / se
    p = math.erfc(abs(z) / math.sqrt(2))
    return {"n": n, "mean_diff": mean, "se": se, "z": z, "p_value": p,
            "ci95": (mean - 1.96 * se, mean + 1.96 * se)}


def per_match_log_loss(probs: np.ndarray, y: np.ndarray) -> np.ndarray:
    return -np.log(np.clip(probs[np.arange(len(y)), y], EPS, 1.0))


def per_match_brier(probs: np.ndarray, y: np.ndarray) -> np.ndarray:
    onehot = np.zeros_like(probs)
    onehot[np.arange(len(y)), y] = 1.0
    return np.sum((probs - onehot) ** 2, axis=1)


# --------------------------------------------------------------------------
# One-shot report
# --------------------------------------------------------------------------

def evaluate(probs: np.ndarray, y: np.ndarray, label: str = "") -> dict:
    """Every headline metric for one set of forecasts."""
    probs = np.asarray(probs, float)
    y = np.asarray(y, int)
    pred = probs.argmax(axis=1)
    n = len(y)
    correct = int((pred == y).sum())

    # Reference forecasts for skill scores.
    base_rate = np.bincount(y, minlength=3) / n
    climatology = np.tile(base_rate, (n, 1))

    return {
        "label": label,
        "n": n,
        "accuracy": correct / n,
        "accuracy_ci95": wilson_interval(correct, n),
        "balanced_accuracy": balanced_accuracy(pred, y),
        "log_loss": log_loss(probs, y),
        "brier": brier(probs, y),
        "brier_skill_vs_climatology": brier_skill_score(probs, y, climatology),
        "ece": expected_calibration_error(probs, y),
        "per_class": per_class(pred, y),
        "confusion": confusion(pred, y).tolist(),
        "predicted_counts": {o: int((pred == i).sum()) for i, o in enumerate(OUTCOMES)},
        "actual_counts": {o: int((y == i).sum()) for i, o in enumerate(OUTCOMES)},
        "mean_top_prob": float(probs.max(axis=1).mean()),
        "mean_entropy": float(entropy(probs).mean()),
    }


def print_report(r: dict) -> None:
    print(f"\n{'=' * 70}")
    print(f"{r['label']}   n = {r['n']:,}")
    print("=" * 70)
    lo, hi = r["accuracy_ci95"]
    print(f"  accuracy            {r['accuracy']*100:6.2f}%   95% CI [{lo*100:.2f}, {hi*100:.2f}]")
    print(f"  balanced accuracy   {r['balanced_accuracy']*100:6.2f}%")
    print(f"  log loss            {r['log_loss']:6.4f}   (lower is better)")
    print(f"  Brier               {r['brier']:6.4f}   (lower is better)")
    print(f"  Brier skill vs base {r['brier_skill_vs_climatology']*100:+6.2f}%")
    print(f"  calibration error   {r['ece']*100:6.2f}pp")
    print(f"  mean top prob       {r['mean_top_prob']*100:6.2f}%   mean entropy {r['mean_entropy']:.3f} bits")
    print(f"\n  {'class':<8}{'precision':>11}{'recall':>9}{'F1':>8}{'predicted':>11}{'actual':>9}")
    for o in OUTCOMES:
        c = r["per_class"][o]
        print(f"  {o:<8}{c['precision']*100:>10.1f}%{c['recall']*100:>8.1f}%"
              f"{c['f1']*100:>7.1f}%{c['predicted']:>11,}{c['support']:>9,}")
    print(f"\n  confusion (rows = actual, cols = predicted)")
    print(f"           {'H':>8}{'D':>8}{'A':>8}")
    for i, o in enumerate(OUTCOMES):
        print(f"    {o:<6}" + "".join(f"{v:>8,}" for v in r["confusion"][i]))
