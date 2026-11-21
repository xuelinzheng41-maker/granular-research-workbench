"""random_control arm: random predictions (must vary across seeds per v1 gate rule)."""
import numpy as np

def fit_predict(x_train, y_train, x_test, *, seed, budget_s):
    rng = np.random.default_rng(seed)
    classes = np.unique(y_train)
    # Must vary across seeds: use stratified random predictions
    preds = classes[rng.integers(0, len(classes), size=len(x_test))]
    return {"predictions": preds.tolist(), "coverage": None, "artifacts": {"ball_count": 0}}
