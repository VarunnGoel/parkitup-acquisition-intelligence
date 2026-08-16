"""Small statistical helpers that keep the project SciPy-free.

Pandas delegates ``method="spearman"`` to SciPy.  The project deliberately
does not depend on SciPy, so Spearman correlation is computed directly as the
Pearson correlation of average ranks.  That is the standard definition and
also handles ties in the same way expected by the analysis.
"""

from __future__ import annotations

import pandas as pd


def spearman_correlation(left: pd.Series, right: pd.Series) -> float:
    """Return pairwise Spearman rank correlation without SciPy."""
    pair = pd.concat(
        [pd.to_numeric(left, errors="coerce"), pd.to_numeric(right, errors="coerce")],
        axis=1,
    ).dropna()
    if len(pair) < 2:
        return float("nan")
    ranked = pair.rank(method="average")
    return float(ranked.iloc[:, 0].corr(ranked.iloc[:, 1], method="pearson"))


def spearman_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a Spearman correlation matrix using pairwise complete ranks."""
    numeric = frame.apply(pd.to_numeric, errors="coerce")
    columns = list(numeric.columns)
    result = pd.DataFrame(index=columns, columns=columns, dtype=float)
    for left in columns:
        for right in columns:
            result.loc[left, right] = spearman_correlation(numeric[left], numeric[right])
    return result
