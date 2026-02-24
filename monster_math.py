import pandas as pd

def calculate_z_scores(df, categories):
    """
    Calculates Z-Scores.
    
    Args:
        categories: 
            - List ['G', 'A']: Assumes all are "Higher is Better".
            - Dict {'GAA': True, 'W': False}: True means "Lower is Better" (Invert).
    """
    # 1. Normalize Input: Convert simple list to dictionary (Default: False/No Invert)
    if isinstance(categories, list):
        cat_config = {c: False for c in categories}
    else:
        cat_config = categories

    z_cols = []
    
    # 2. Calculate Z-Scores
    for cat, invert in cat_config.items():
        # Skip if column missing
        if cat not in df.columns:
            continue
            
        col_name = cat
        mean = df[col_name].mean()
        std = df[col_name].std()
        
        # Avoid division by zero
        if std == 0:
            df[f'{cat}V'] = 0.0
        else:
            if invert:
                # INVERTED (Lower is Better): (Mean - Player) / Std
                # Example: League Avg 3.00 - Player 2.00 = +1.00 Z-Score
                df[f'{cat}V'] = (mean - df[col_name]) / std
            else:
                # STANDARD (Higher is Better): (Player - Mean) / Std
                df[f'{cat}V'] = (df[col_name] - mean) / std
        
        z_cols.append(f'{cat}V')

    # 3. Sum Total Value
    df['Value'] = df[z_cols].sum(axis=1)
    
    # Return sorted
    return df.sort_values(by='Value', ascending=False)