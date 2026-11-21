"""
Research OS v2 - Dataset Registry and Loaders

Implements DESIGN.md §7:
- Dataset registry with status (ready, ready_with_scipy, needs_loader, needs_data)
- Unified loaders for text files (space/comma delimited) and MATLAB v5 files
- SHA256 verification for data integrity
- No silent fallbacks - missing files must exit 2

Supports:
- Text files: space or comma delimited, various naming conventions
- MATLAB v5 files: readable with scipy.io.loadmat
- Root directory files (Chainlink, EngyTime, S3, Segmentation, Twenty, Waveform)
- Non-standard names (MoCap = mocap_norm.txt)
"""

import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np


class DatasetStatus:
    """Dataset status values."""
    READY = "ready"  # Pure text, numpy can read
    READY_WITH_SCIPY = "ready_with_scipy"  # MATLAB v5, needs scipy
    NEEDS_LOADER = "needs_loader"  # MATLAB v7.3 or other format
    NEEDS_DATA = "needs_data"  # File missing


class DatasetRegistry:
    """Dataset registry manager."""
    
    def __init__(self, registry_path: Path):
        """
        Initialize registry from JSON file.
        
        Args:
            registry_path: Path to datasets.json
        """
        self.registry_path = registry_path
        
        if registry_path.exists():
            with open(registry_path, 'r', encoding='utf-8') as f:
                self.registry = json.load(f)
        else:
            self.registry = {
                "schema_version": 1,
                "root": "",
                "datasets": []
            }
    
    def save(self) -> None:
        """Save registry to JSON file."""
        # Use canonical JSON from records module
        sys.path.insert(0, str(Path(__file__).parent))
        from records import canonical_json
        
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.registry_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(canonical_json(self.registry))
    
    def get_dataset(self, dataset_id: str) -> Optional[Dict]:
        """Get dataset entry by ID."""
        for ds in self.registry["datasets"]:
            if ds["id"] == dataset_id:
                return ds
        return None
    
    def get_root(self) -> Path:
        """Get registry root path."""
        root = Path(self.registry["root"])
        return root if root.is_absolute() else self.registry_path.resolve().parent / root


def compute_file_sha256(file_path: Path) -> str:
    """
    Compute SHA256 hash of a file.
    
    Args:
        file_path: Path to file
        
    Returns:
        Hash in format "sha256:<hex>"
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    with open(file_path, 'rb') as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()
    
    return f"sha256:{file_hash}"


def _check_finite_labels(y: np.ndarray, source: Path) -> None:
    # Only floating and complex arrays can contain non-finite numeric values.
    if y.dtype.kind in ("f", "c") and not np.isfinite(y).all():
        raise ValueError(f"Non-finite label in {source}")


def load_text_pair(
    data_path: Path,
    labels_path: Path,
    delimiter: str = "whitespace",
    has_header: bool = False
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Load data and labels from separate text files.
    
    Args:
        data_path: Path to data file
        labels_path: Path to labels file
        delimiter: "whitespace" or "comma"
        has_header: Whether files have header row
        
    Returns:
        Tuple of (X, y) as numpy arrays
    """
    if not data_path.exists():
        raise FileNotFoundError(f"Data file not found: {data_path}")
    if not labels_path.exists():
        raise FileNotFoundError(f"Labels file not found: {labels_path}")
    
    # Determine delimiter
    if delimiter == "comma":
        delim = ","
    else:  # whitespace
        delim = None
    
    # Load data
    skiprows = 1 if has_header else 0
    
    try:
        X = np.loadtxt(data_path, delimiter=delim, skiprows=skiprows)
        y = np.loadtxt(labels_path, delimiter=delim, skiprows=skiprows)
    except Exception as e:
        raise ValueError(f"Failed to load data: {e}")
    
    # Ensure X is 2D
    if X.ndim == 1:
        X = X.reshape(-1, 1)
    
    # Ensure y is 1D
    y = y.ravel()
    
    if len(X) != len(y):
        raise ValueError(f"Data and labels length mismatch: {len(X)} vs {len(y)}")
    
    _check_finite_labels(y, labels_path)
    return X, y


def load_mat_v5(data_path: Path) -> Tuple[np.ndarray, np.ndarray]:
    """Load MAT features and embedded labels, or zeros when labels are absent."""
    X, y, _ = _load_mat_v5(data_path)
    return X, y


def _load_mat_v5(
    data_path: Path, use_embedded_labels: bool = True
) -> Tuple[np.ndarray, np.ndarray, bool]:
    """Read MAT features and report whether the returned labels are embedded."""
    if not data_path.exists():
        raise FileNotFoundError(f"Data file not found: {data_path}")
    
    try:
        from scipy.io import loadmat
    except ImportError:
        raise ImportError("scipy is required for MATLAB v5 files")
    
    try:
        mat_data = loadmat(data_path)
    except Exception as e:
        raise ValueError(f"Failed to load MATLAB file: {e}")
    
    # Common MATLAB variable names
    possible_data_keys = ['X', 'data', 'features', 'x', 'points']
    possible_label_keys = ['y', 'labels', 'label', 'target', 'Y']
    
    X = None
    y = None
    
    for key in possible_data_keys:
        if key in mat_data:
            X = mat_data[key]
            break
    
    if use_embedded_labels:
        for key in possible_label_keys:
            if key in mat_data:
                y = mat_data[key]
                break
    
    if X is None:
        available = [k for k in mat_data.keys() if not k.startswith('__')]
        raise ValueError(f"Could not find data in MATLAB file. Available keys: {available}")
    
    has_labels = y is not None
    if not has_labels:
        y = np.zeros(len(X))
    
    # Ensure proper shapes
    if X.ndim == 1:
        X = X.reshape(-1, 1)
    
    y = y.ravel()
    
    if len(X) != len(y):
        raise ValueError(f"Data and labels length mismatch: {len(X)} vs {len(y)}")

    if has_labels:
        _check_finite_labels(y, data_path)
    return X, y, has_labels


def _load_mat_external_labels(labels_path: Path, rows: int) -> Tuple[np.ndarray, str]:
    """Read one finite numeric label per line and hash the exact bytes parsed."""
    try:
        contents = labels_path.read_bytes()
    except FileNotFoundError as e:
        raise FileNotFoundError(f"Labels file not found: {labels_path}") from e

    labels = []
    for line_no, line in enumerate(contents.decode("utf-8").splitlines(), start=1):
        fields = line.split()
        if len(fields) != 1:
            raise ValueError(f"Invalid label format in {labels_path} at line {line_no}: expected one number")
        try:
            label = float(fields[0])
        except ValueError as e:
            raise ValueError(f"Invalid label format in {labels_path} at line {line_no}: expected one number") from e
        if not np.isfinite(label):
            raise ValueError(f"Non-finite label in {labels_path} at line {line_no}")
        labels.append(label)

    if len(labels) != rows:
        raise ValueError(f"Data and labels length mismatch: {rows} vs {len(labels)} ({labels_path})")
    return np.asarray(labels, dtype=float), f"sha256:{hashlib.sha256(contents).hexdigest()}"


def load_dataset(
    dataset_entry: Dict,
    root: Path
) -> Tuple[np.ndarray, np.ndarray, Dict[str, str]]:
    """Return (X, y, hashes); explicit MAT external labels replace any embedded labels."""
    X, y, hashes, _ = load_dataset_with_label_info(dataset_entry, root)
    return X, y, hashes


def load_dataset_with_label_info(
    dataset_entry: Dict,
    root: Path
) -> Tuple[np.ndarray, np.ndarray, Dict[str, str], bool]:
    """Load a dataset and report whether y comes from a real label source."""
    dataset_id = dataset_entry["id"]
    loader = dataset_entry["loader"]
    status = dataset_entry["status"]
    
    # Check status
    if status == DatasetStatus.NEEDS_LOADER:
        raise ValueError(f"Dataset {dataset_id} requires a loader that is not available (status: {status})")
    
    if status == DatasetStatus.NEEDS_DATA:
        raise FileNotFoundError(f"Dataset {dataset_id} has missing data files (status: {status})")
    
    # Resolve paths
    data_rel = dataset_entry["data"]
    data_path = root / data_rel
    
    sha256_dict = {}
    source = dataset_entry.get("label_source")
    source_kind = None
    if "label_source" in dataset_entry:
        if not isinstance(source, dict) or source.get("kind") not in ("separate_file", "none"):
            raise ValueError(f"Dataset {dataset_id} has an invalid label_source")
        if loader != "mat_v5":
            raise ValueError(f"Dataset {dataset_id}: explicit label_source requires the mat_v5 loader")
        source_kind = source["kind"]

    if loader == "txt_pair":
        # Text pair loader
        labels_rel = dataset_entry["labels"]
        labels_path = root / labels_rel
        
        delimiter = dataset_entry.get("delimiter", "whitespace")
        has_header = dataset_entry.get("has_header", False)
        
        X, y = load_text_pair(data_path, labels_path, delimiter, has_header)
        has_labels = True
        
        # Compute hashes
        sha256_dict["data"] = compute_file_sha256(data_path)
        sha256_dict["labels"] = compute_file_sha256(labels_path)
        
    elif loader in ["mat_v5", "mat_v73"]:
        # MATLAB loader
        if loader == "mat_v73":
            raise ValueError(f"Dataset {dataset_id} requires MATLAB v7.3 support (h5py)")
        
        X, y, has_labels = _load_mat_v5(data_path, use_embedded_labels=source_kind is None)
        if source_kind == "separate_file":
            label_path = source.get("path")
            if not isinstance(label_path, str) or not label_path.strip():
                raise ValueError(f"Dataset {dataset_id}: label_source.path is required")
            label_path = Path(label_path)
            if label_path.anchor or not label_path.parts or ".." in label_path.parts:
                raise ValueError(f"Dataset {dataset_id}: label_source.path must be relative to the dataset root")
            y, sha256_dict["labels"] = _load_mat_external_labels(root / label_path, len(X))
            has_labels = True
        
        # Compute hash
        sha256_dict["data"] = compute_file_sha256(data_path)
        
    else:
        raise ValueError(f"Unknown loader type: {loader}")
    
    return X, y, sha256_dict, has_labels


def verify_dataset(
    dataset_entry: Dict,
    root: Path
) -> Tuple[bool, Optional[str]]:
    """
    Verify dataset can be loaded and matches expected properties.
    
    Args:
        dataset_entry: Dataset entry from registry
        root: Root directory path
        
    Returns:
        Tuple of (success, error_message)
    """
    try:
        X, _, sha256_dict = load_dataset(dataset_entry, root)
        return verify_loaded_dataset(dataset_entry, X, sha256_dict)
    except FileNotFoundError as e:
        return False, f"File not found: {e}"
    except ValueError as e:
        return False, f"Load error: {e}"
    except Exception as e:
        return False, f"Unexpected error: {e}"


def verify_loaded_dataset(
    dataset_entry: Dict,
    X: np.ndarray,
    sha256_dict: Dict[str, str]
) -> Tuple[bool, Optional[str]]:
    """Validate registry dimensions and declared hashes against an existing load."""
    expected_rows = dataset_entry.get("rows")
    expected_features = dataset_entry.get("features")
    if expected_rows is not None and len(X) != expected_rows:
        return False, f"Row count mismatch: expected {expected_rows}, got {len(X)}"
    if expected_features is not None and X.shape[1] != expected_features:
        return False, f"Feature count mismatch: expected {expected_features}, got {X.shape[1]}"

    for key, expected_hash in (dataset_entry.get("sha256") or {}).items():
        actual_hash = sha256_dict.get(key)
        if actual_hash != expected_hash:
            return False, f"SHA256 mismatch for {key}: expected {expected_hash}, got {actual_hash or 'not computed'}"
    return True, None


def get_label_distribution(y: np.ndarray) -> Dict[str, int]:
    """
    Get label distribution as a dict.
    
    Args:
        y: Label array
        
    Returns:
        Dict mapping label -> count
    """
    unique, counts = np.unique(y, return_counts=True)
    return {str(label): int(count) for label, count in zip(unique, counts)}
