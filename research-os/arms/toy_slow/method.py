"""Toy slow arm: intentionally exceeds budget to test timeout path."""
import time
import numpy as np


def fit_predict(x_train, y_train, x_test, *, seed, budget_s):
    # Sleep 3x the budget so the subprocess times out
    time.sleep(budget_s * 3 + 1)
    return {"predictions": [0] * len(x_test), "coverage": None, "artifacts": {}}
