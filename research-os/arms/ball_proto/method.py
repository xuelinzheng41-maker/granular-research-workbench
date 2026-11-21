"""ball_proto arm: granular-ball prototypes using purity-driven splitting."""
import numpy as np

def _split_to_pure_balls(X, y, purity_threshold=0.9, min_size=2):
    """Simple recursive purity-based ball generation."""
    balls = []  # list of (center, label, indices)
    
    def split(indices):
        if len(indices) == 0:
            return
        sub_X = X[indices]
        sub_y = y[indices]
        
        # Check purity
        classes, counts = np.unique(sub_y, return_counts=True)
        purity = counts.max() / len(sub_y)
        majority_label = classes[counts.argmax()]
        
        if purity >= purity_threshold or len(indices) <= min_size:
            center = sub_X.mean(axis=0)
            balls.append((center, majority_label))
            return
        
        # Split by median of most variable feature
        variances = sub_X.var(axis=0)
        feat = variances.argmax()
        median = np.median(sub_X[:, feat])
        left = indices[sub_X[:, feat] <= median]
        right = indices[sub_X[:, feat] > median]
        
        if len(left) == 0 or len(right) == 0:
            center = sub_X.mean(axis=0)
            balls.append((center, majority_label))
            return
        split(left)
        split(right)
    
    split(np.arange(len(X)))
    return balls

def fit_predict(x_train, y_train, x_test, *, seed, budget_s):
    rng = np.random.default_rng(seed)
    balls = _split_to_pure_balls(x_train, y_train, purity_threshold=0.9)
    
    if not balls:
        # Fallback: majority class
        classes, counts = np.unique(y_train, return_counts=True)
        preds = np.full(len(x_test), classes[counts.argmax()])
        return {"predictions": preds.tolist(), "coverage": None, "artifacts": {"ball_count": 1}}
    
    centers = np.array([b[0] for b in balls])
    ball_labels = np.array([b[1] for b in balls])
    
    # Predict: nearest ball center
    dists = np.linalg.norm(x_test[:, np.newaxis, :] - centers[np.newaxis, :, :], axis=2)
    nearest = dists.argmin(axis=1)
    preds = ball_labels[nearest]
    
    return {"predictions": preds.tolist(), "coverage": None, "artifacts": {"ball_count": len(balls)}}
