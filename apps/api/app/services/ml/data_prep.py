import os
import logging
import pandas as pd
import numpy as np
from typing import Tuple, Dict, Any, List, Optional

logger = logging.getLogger(__name__)

def load_elliptic_data(data_dir: Optional[str] = None) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Load the Elliptic++ dataset from CSV files.
    
    Args:
        data_dir: Path to the dataset directory. If None, uses ELLIPTIC_DATA_DIR env var
                  or defaults to 'D:\\SIH\\vajratrace\\data\\Elliptic++ Dataset'.
                  
    Returns:
        Tuple containing (features_df, classes_df, edges_df).
    """
    if data_dir is None:
        data_dir = os.environ.get('ELLIPTIC_DATA_DIR', r'D:\SIH\vajratrace\data\Elliptic++ Dataset')
        
    logger.info(f"Loading Elliptic data from {data_dir}")
    
    features_path = os.path.join(data_dir, 'txs_features.csv')
    classes_path = os.path.join(data_dir, 'txs_classes.csv')
    edges_path = os.path.join(data_dir, 'txs_edgelist.csv')
    
    logger.debug(f"Reading {features_path}")
    features_df = pd.read_csv(features_path)
    
    logger.debug(f"Reading {classes_path}")
    classes_df = pd.read_csv(classes_path)
    
    logger.debug(f"Reading {edges_path}")
    edges_df = pd.read_csv(edges_path)
    
    return features_df, classes_df, edges_df

def engineer_features(features_df: pd.DataFrame, classes_df: pd.DataFrame, edges_df: pd.DataFrame) -> pd.DataFrame:
    """
    Merge data, compute new features (graph degrees, temporal proxies), and filter classes.
    
    Args:
        features_df: DataFrame with transaction features.
        classes_df: DataFrame with transaction classes.
        edges_df: DataFrame with directed edges (txId1 -> txId2).
        
    Returns:
        Merged and processed DataFrame containing features and binary label.
    """
    logger.info("Starting feature engineering")
    
    # Merge features with classes
    df = pd.merge(features_df, classes_df, on='txId', how='inner')
    
    # Compute graph-level in_degree and out_degree from edgelist
    logger.info("Computing graph-level degrees")
    out_degrees = edges_df.groupby('txId1').size().reset_index(name='graph_out_degree')
    out_degrees.rename(columns={'txId1': 'txId'}, inplace=True)
    
    in_degrees = edges_df.groupby('txId2').size().reset_index(name='graph_in_degree')
    in_degrees.rename(columns={'txId2': 'txId'}, inplace=True)
    
    # Merge computed degrees back into the main DataFrame
    df = pd.merge(df, out_degrees, on='txId', how='left')
    df = pd.merge(df, in_degrees, on='txId', how='left')
    
    # Fill NaN degrees with 0 (nodes with no incoming/outgoing edges)
    df['graph_out_degree'] = df['graph_out_degree'].fillna(0).astype(int)
    df['graph_in_degree'] = df['graph_in_degree'].fillna(0).astype(int)
    
    # Temporal proxy features based on 'Time step'
    # Documented proxy: simulating hour of day and day of week
    logger.info("Computing temporal proxy features")
    df['hour_of_day'] = (df['Time step'] * 6) % 24
    df['day_of_week'] = df['Time step'] % 7
    
    # Handle classes
    # 1: illicit, 2: licit, 3: unknown
    # We EXCLUDE unknown class (class == 3) from training data
    # Convert labels: 1 (illicit) -> 1, 2 (licit) -> 0 (binary classification)
    logger.info("Filtering and converting classes")
    # Convert to string just in case it was loaded as object or string natively, but handle as numeric as well
    df['class'] = pd.to_numeric(df['class'], errors='coerce')
    
    # Filter out unknowns (class 3)
    unknown_count = (df['class'] == 3).sum()
    logger.info(f"Excluding {unknown_count} unknown transactions")
    df = df[df['class'] != 3].copy()
    
    # Create binary label
    df['label'] = df['class'].apply(lambda x: 1 if x == 1 else 0)
    
    return df

def prepare_splits(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, List[str]]:
    """
    Split the dataset into train/val/test using temporal ordering to prevent data leakage.
    
    Args:
        df: Processed DataFrame with 'Time step' and 'label'.
        
    Returns:
        Tuple of (X_train, X_val, X_test, y_train, y_val, y_test, feature_names).
    """
    logger.info("Preparing train/val/test splits")
    
    # Sort by temporal ordering
    df = df.sort_values('Time step')
    
    # Get unique timesteps
    timesteps = df['Time step'].unique()
    timesteps.sort()
    
    # 60/20/20 split based on temporal ordering
    n_steps = len(timesteps)
    train_end_idx = int(n_steps * 0.6)
    val_end_idx = int(n_steps * 0.8)
    
    train_steps = timesteps[:train_end_idx]
    val_steps = timesteps[train_end_idx:val_end_idx]
    test_steps = timesteps[val_end_idx:]
    
    train_df = df[df['Time step'].isin(train_steps)]
    val_df = df[df['Time step'].isin(val_steps)]
    test_df = df[df['Time step'].isin(test_steps)]
    
    # Define feature columns
    exclude_cols = {'txId', 'Time step', 'class', 'label'}
    feature_names = [col for col in df.columns if col not in exclude_cols]
    
    X_train = train_df[feature_names].values
    y_train = train_df['label'].values
    
    X_val = val_df[feature_names].values
    y_val = val_df['label'].values
    
    X_test = test_df[feature_names].values
    y_test = test_df['label'].values
    
    logger.info(f"Split complete. Train: {len(X_train)}, Val: {len(X_val)}, Test: {len(X_test)}")
    
    return X_train, X_val, X_test, y_train, y_val, y_test, feature_names

def get_prepared_data(data_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Convenience function that chains loading, feature engineering, and splitting.
    
    Args:
        data_dir: Optional path to the dataset directory.
        
    Returns:
        Dictionary containing all splits, feature names, and metadata.
    """
    # 1. Load data
    features_df, classes_df, edges_df = load_elliptic_data(data_dir)
    
    # Calculate initial stats for metadata
    # The original classes_df might have class as object or numeric
    classes_df['class'] = pd.to_numeric(classes_df['class'], errors='coerce')
    n_illicit = (classes_df['class'] == 1).sum()
    n_licit = (classes_df['class'] == 2).sum()
    n_unknown_excluded = (classes_df['class'] == 3).sum()
    
    # 2. Engineer features
    processed_df = engineer_features(features_df, classes_df, edges_df)
    
    # 3. Prepare splits
    X_train, X_val, X_test, y_train, y_val, y_test, feature_names = prepare_splits(processed_df)
    
    metadata = {
        "n_illicit": int(n_illicit),
        "n_licit": int(n_licit),
        "n_unknown_excluded": int(n_unknown_excluded),
        "n_features": len(feature_names),
        "n_train": len(X_train),
        "n_val": len(X_val),
        "n_test": len(X_test)
    }
    
    return {
        "X_train": X_train,
        "X_val": X_val,
        "X_test": X_test,
        "y_train": y_train,
        "y_val": y_val,
        "y_test": y_test,
        "feature_names": feature_names,
        "metadata": metadata
    }

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger.info("Running data preparation script")
    
    try:
        data = get_prepared_data()
        meta = data["metadata"]
        
        print("\n=== Elliptic++ Dataset Summary ===")
        print(f"Total Illicit transactions: {meta['n_illicit']}")
        print(f"Total Licit transactions: {meta['n_licit']}")
        print(f"Total Unknown transactions (excluded): {meta['n_unknown_excluded']}")
        print(f"Number of features used: {meta['n_features']}")
        print("\n=== Data Splits ===")
        print(f"Train size: {meta['n_train']}")
        print(f"Validation size: {meta['n_val']}")
        print(f"Test size: {meta['n_test']}")
        print(f"Total known samples: {meta['n_train'] + meta['n_val'] + meta['n_test']}")
    except Exception as e:
        logger.error(f"Failed to prepare data: {e}")
