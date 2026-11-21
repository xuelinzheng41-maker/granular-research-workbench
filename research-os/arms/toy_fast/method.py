"""Toy fast arm: predict majority class (always finishes in <1s)."""
import numpy as np


def fit_predict(x_train, y_train, x_test, *, seed, budget_s):
    rng = np.random.default_rng(seed)
    classes, counts = np.unique(y_train, return_counts=True)
    majority = classes[np.argmax(counts)]
    predictions = np.full(len(x_test), majority, dtype=float)
    # Add tiny random noise so random_control is not constant
    noise = rng.integers(0, len(classes), size=len(x_test))
    predictions = classes[noise % len(classes)]
    return {"predictions": predictions.tolist(), "coverage": None, "artifacts": {}}
