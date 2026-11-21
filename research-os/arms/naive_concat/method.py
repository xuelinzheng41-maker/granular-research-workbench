"""naive_concat arm: predict using KNN on raw features (simple baseline)."""
import numpy as np
try:
    from sklearn.neighbors import KNeighborsClassifier
except ImportError:
    raise

def fit_predict(x_train, y_train, x_test, *, seed, budget_s):
    rng = np.random.default_rng(seed)
    n = min(5, len(x_train))
    clf = KNeighborsClassifier(n_neighbors=n, algorithm='auto')
    clf.fit(x_train, y_train)
    preds = clf.predict(x_test)
    return {"predictions": preds.tolist(), "coverage": None, "artifacts": {"ball_count": n}}
