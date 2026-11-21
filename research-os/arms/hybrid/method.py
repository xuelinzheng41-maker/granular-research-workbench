"""hybrid arm: adaptive ball splitting with three-way uncertain band."""
import numpy as np

def _split_balls(X, y, purity_threshold=0.85, min_size=2):
    """Adaptive ball splitting using purity threshold."""
    balls = []
    
    def split(indices, depth=0):
        if len(indices) == 0:
            return
        sub_X = X[indices]
        sub_y = y[indices]
        classes, counts = np.unique(sub_y, return_counts=True)
        purity = counts.max() / len(sub_y)
        majority_label = classes[counts.argmax()]
        majority_count = counts.max()
        
        if purity >= purity_threshold or len(indices) <= min_size or depth > 15:
            center = sub_X.mean(axis=0)
            radius = np.linalg.norm(sub_X - center, axis=1).mean()
            balls.append({
                "center": center, "radius": radius,
                "label": majority_label, "purity": purity,
                "size": len(indices),
            })
            return
        
        variances = sub_X.var(axis=0)
        feat = variances.argmax()
        median = np.median(sub_X[:, feat])
        left = indices[sub_X[:, feat] <= median]
        right = indices[sub_X[:, feat] > median]
        
        if len(left) == 0 or len(right) == 0:
            center = sub_X.mean(axis=0)
            radius = np.linalg.norm(sub_X - center, axis=1).mean()
            balls.append({"center": center, "radius": radius,
                          "label": majority_label, "purity": purity, "size": len(indices)})
            return
        split(left, depth + 1)
        split(right, depth + 1)
    
    split(np.arange(len(X)))
    return balls


def fit_predict(x_train, y_train, x_test, *, seed, budget_s):
    rng = np.random.default_rng(seed)
    balls = _split_balls(x_train, y_train)
    
    if not balls:
        classes, counts = np.unique(y_train, return_counts=True)
        preds = np.full(len(x_test), classes[counts.argmax()])
        return {"predictions": preds.tolist(), "coverage": None,
                "artifacts": {"ball_count": 1}}
    
    centers = np.array([b["center"] for b in balls])
    purities = np.array([b["purity"] for b in balls])
    labels = np.array([b["label"] for b in balls])
    
    # Three-way uncertain band: alpha=0.7 (POS threshold), beta=0.3 (NEG threshold)
    alpha, beta = 0.7, 0.3
    
    preds = []
    uncertain_count = 0
    for x in x_test:
        dists = np.linalg.norm(centers - x, axis=1)
        nearest_idx = dists.argmin()
        ball_purity = purities[nearest_idx]
        
        if ball_purity >= alpha:
            # POS region: confident prediction
            preds.append(labels[nearest_idx])
        elif ball_purity <= beta:
            # NEG region: reject to majority class
            classes, counts = np.unique(y_train, return_counts=True)
            preds.append(classes[counts.argmax()])
        else:
            # Uncertain band: use 3 nearest balls voting
            uncertain_count += 1
            top3 = np.argsort(dists)[:3]
            top_labels = labels[top3]
            vals, cnts = np.unique(top_labels, return_counts=True)
            preds.append(vals[cnts.argmax()])
    
    coverage = 1.0 - uncertain_count / len(x_test) if x_test.size > 0 else 1.0
    
    return {
        "predictions": preds,
        "coverage": float(coverage),
        "artifacts": {"ball_count": len(balls), "uncertain_count": uncertain_count},
    }
