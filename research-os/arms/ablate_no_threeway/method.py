"""ablate_no_threeway arm: hybrid without three-way decision (all balls treated as POS)."""
import numpy as np

def _split_balls(X, y, purity_threshold=0.85, min_size=2):
    balls = []
    def split(indices, depth=0):
        if len(indices) == 0: return
        sub_X, sub_y = X[indices], y[indices]
        classes, counts = np.unique(sub_y, return_counts=True)
        purity = counts.max() / len(sub_y)
        majority_label = classes[counts.argmax()]
        if purity >= purity_threshold or len(indices) <= min_size or depth > 15:
            balls.append({"center": sub_X.mean(0), "label": majority_label, "size": len(indices)})
            return
        feat = sub_X.var(0).argmax()
        median = np.median(sub_X[:, feat])
        left = indices[sub_X[:, feat] <= median]
        right = indices[sub_X[:, feat] > median]
        if len(left) == 0 or len(right) == 0:
            balls.append({"center": sub_X.mean(0), "label": majority_label, "size": len(indices)})
            return
        split(left, depth+1); split(right, depth+1)
    split(np.arange(len(X)))
    return balls

def fit_predict(x_train, y_train, x_test, *, seed, budget_s):
    rng = np.random.default_rng(seed)
    balls = _split_balls(x_train, y_train)
    if not balls:
        classes, counts = np.unique(y_train, return_counts=True)
        preds = np.full(len(x_test), classes[counts.argmax()])
        return {"predictions": preds.tolist(), "coverage": None, "artifacts": {"ball_count": 1}}
    
    centers = np.array([b["center"] for b in balls])
    labels = np.array([b["label"] for b in balls])
    
    # No three-way: simply predict nearest ball (all POS)
    dists = np.linalg.norm(x_test[:, np.newaxis, :] - centers[np.newaxis, :, :], axis=2)
    preds = labels[dists.argmin(axis=1)]
    return {"predictions": preds.tolist(), "coverage": 1.0,
            "artifacts": {"ball_count": len(balls)}}
