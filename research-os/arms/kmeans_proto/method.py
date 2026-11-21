"""kmeans_proto arm: K-means prototypes for classification."""
import numpy as np
try:
    from sklearn.cluster import KMeans
    from sklearn.metrics.pairwise import euclidean_distances
except ImportError:
    raise

def fit_predict(x_train, y_train, x_test, *, seed, budget_s):
    rng = np.random.default_rng(seed)
    classes, counts = np.unique(y_train, return_counts=True)
    n_clusters = min(len(classes) * 3, len(x_train) // 5 + 1, 50)
    
    # Fit K-means
    km = KMeans(n_clusters=n_clusters, random_state=int(rng.integers(0, 2**31)), n_init=3, max_iter=100)
    km.fit(x_train)
    
    # Assign majority class label to each centroid
    labels = km.predict(x_train)
    centroid_labels = np.zeros(n_clusters, dtype=y_train.dtype)
    for k in range(n_clusters):
        mask = labels == k
        if mask.any():
            vals, cnts = np.unique(y_train[mask], return_counts=True)
            centroid_labels[k] = vals[np.argmax(cnts)]
        else:
            centroid_labels[k] = classes[0]
    
    # Predict: assign label of nearest centroid
    test_labels_idx = km.predict(x_test)
    preds = centroid_labels[test_labels_idx]
    return {"predictions": preds.tolist(), "coverage": None, "artifacts": {"ball_count": n_clusters}}
