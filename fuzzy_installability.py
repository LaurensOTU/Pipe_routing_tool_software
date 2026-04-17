"""
fuzzy_installability.py
-----------------------
Converts a clearance distance (mm) around a pipe into an installability score
and time multiplier, using fuzzy membership functions calibrated from engineer
questionnaire data.

No external fuzzy library required — implemented in pure NumPy.

Usage:
    from fuzzy_installability import FuzzyInstallability

    fuzzy = FuzzyInstallability(csv_path="path/to/questionnaire.csv")
    label, time_mult, score = fuzzy.get_score(clearance_mm=350)
    # label        → e.g. "tight"
    # time_mult    → e.g. 2.1  (installation takes 2.1× baseline)
    # score        → e.g. 0.5  (0.0 = impossible, 1.0 = fully clear)
"""

import os
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Default parameters (used when CSV is missing or has too few responses)
# These are based on the current 3-response pilot dataset.
# ---------------------------------------------------------------------------
DEFAULT_CENTERS = {
    'impossible':  133.0,   # mm
    'too_tight':   200.0,
    'tight':       317.0,
    'sufficient':  533.0,
    'clear':      1033.0,
}

# Time multipliers per category — from questionnaire "Answer below for..."
# Median values across responses. 1.0 = no extra time, 3.5 = 3.0x+ (worst case)
DEFAULT_MULTIPLIERS = {
    'impossible': 4.0,
    'too_tight':  3.0,
    'tight':      2.0,
    'sufficient': 1.0,
    'clear':      1.0,
}

# Normalised installability score per category label (0 = bad, 1 = ideal)
# s_k derived by normalising with 9 responses from multipliers
CATEGORY_SCORES = {
    'impossible': 0.00,
    'too_tight':  0.36,
    'tight':      0.629,
    'sufficient': 0.935,
    'clear':      1.00,
}

# Ordered category names (low → high clearance)
ORDERED_CATS = ['impossible', 'too_tight', 'tight', 'sufficient', 'clear']

# Multiplier string → float mapping from questionnaire response format
# Handles both "3.0x +" (space) and "3.0x+" (no space), and "<1.0x" (faster than baseline)
MULT_PARSE = {
    '<1.0x': 0.8, '1.0x': 1.0, '1.5x': 1.5, '2.0x': 2.0,
    '2.5x':  2.5, '3.0x': 3.0, '3.0x +': 3.5, '3.0x+': 3.5,
}

# Questionnaire column names
SPACE_COLS = {
    'impossible': "Impossible (e.g. normal or special tools don't fit)",
    'too_tight':  "Too Tight (work is possible, but requires extreme care of special tools)",
    'tight':      "Tight (work is possible, but movement is limited)",
    'sufficient': "Sufficient (work is possible with objects around)",
    'clear':      "Clear (More space than this makes no difference)",
}
MULT_COLS = {
    'too_tight':  "Answer below for the following conditions.Too Tight",
    'tight':      "Answer below for the following conditions.Tight",
    'sufficient': "Answer below for the following conditions.Sufficient",
    'clear':      "Answer below for the following conditions.Clear",
}


class FuzzyInstallability:
    """
    Fuzzy membership function system for pipe installation space evaluation.

    Membership functions are either triangular (sparse data) or Gaussian
    (richer data), built automatically from questionnaire CSV responses.
    Falls back to hardcoded defaults if no CSV is available.
    """

    def __init__(self, csv_path: str = None):
        self.min_val      = 50.0   # Default floor
        self.max_val      = 1250.0 # Default ceiling
        self.universe     = np.arange(self.min_val, self.max_val, 10, dtype=float)
        self.centers      = dict(DEFAULT_CENTERS)
        self.multipliers  = dict(DEFAULT_MULTIPLIERS)
        self.mf_arrays    = {}
        self.n_responses  = 0
        self.stds         = {k: 0.0 for k in ORDERED_CATS}

        if csv_path:
            self._load_csv(csv_path)

        self._build_mfs()

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_csv(self, csv_path: str):
        """Parse questionnaire CSV and extract mean centers + multipliers."""
        if not os.path.exists(csv_path):
            print(f"[FuzzyInstallability] CSV not found: {csv_path}. Using defaults.")
            return
        try:
            df = pd.read_csv(csv_path)
            self.n_responses = len(df)
            print(f"[FuzzyInstallability] Loaded {self.n_responses} questionnaire responses.")

            all_vals = []
            # Space threshold centers
            for key, col in SPACE_COLS.items():
                if col in df.columns:
                    vals = pd.to_numeric(df[col], errors='coerce').dropna()
                    if len(vals) > 0:
                        all_vals.extend(vals.tolist())
                        self.centers[key] = float(vals.mean())
                        self.stds[key]    = float(vals.std(ddof=1)) if len(vals) > 1 else 0.0

            if all_vals:
                self.min_val = max(0.0, min(all_vals))
                self.max_val = max(all_vals) + 100.0
                # Re-build universe with new bounds
                self.universe = np.arange(self.min_val, self.max_val, 10, dtype=float)

            # Time multipliers
            for key, col in MULT_COLS.items():
                if col in df.columns:
                    parsed = df[col].dropna().map(
                        lambda x: MULT_PARSE.get(str(x).strip(), None)
                    ).dropna()
                    if len(parsed) > 0:
                        self.multipliers[key] = float(parsed.mean())

            # impossible has no multiplier column — keep default (4.0)
            self.multipliers['impossible'] = DEFAULT_MULTIPLIERS['impossible']

        except Exception as exc:
            print(f"[FuzzyInstallability] Error reading CSV: {exc}. Using defaults.")

    # ------------------------------------------------------------------
    # Membership function construction
    # ------------------------------------------------------------------

    def _gaussmf(self, x: np.ndarray, mean: float, sigma: float) -> np.ndarray:
        """Gaussian membership function."""
        return np.exp(-0.5 * ((x - mean) / sigma) ** 2)

    def _trimf(self, x: np.ndarray, a: float, b: float, c: float) -> np.ndarray:
        """Triangular membership function defined by [a, b, c]."""
        mf = np.zeros_like(x, dtype=float)
        if b > a:
            mask = (x >= a) & (x <= b)
            mf[mask] = (x[mask] - a) / (b - a)
        mf[x == b] = 1.0
        if c > b:
            mask = (x > b) & (x <= c)
            mf[mask] = (c - x[mask]) / (c - b)
        return mf

    def _build_mfs(self):
        """Build one membership function per category."""
        c = [self.centers[k] for k in ORDERED_CATS]
        n = len(ORDERED_CATS)

        for idx, key in enumerate(ORDERED_CATS):
            center = c[idx]
            # Neighbour midpoints define triangle extent
            left  = self.min_val      if idx == 0     else (c[idx - 1] + c[idx]) / 2.0
            right = self.max_val - 1  if idx == n - 1 else (c[idx] + c[idx + 1]) / 2.0

            if self.n_responses > 3 and self.stds[key] > 0:
                sigma = max(self.stds[key], 20.0)
                mf = self._gaussmf(self.universe, center, sigma)
                
                # Apply "Shoulders":
                if idx == 0: # Impossible: Stay at 1.0 for everything below the mean
                    mf[self.universe <= center] = 1.0
                elif idx == n - 1: # Clear: Stay at 1.0 for everything above the mean
                    mf[self.universe >= center] = 1.0
            else:
                a = left
                b = float(center)
                cc = right
                
                # For triangular shoulders:
                if idx == 0:
                    mf = self._trimf(self.universe, a, b, cc)
                    mf[self.universe <= b] = 1.0
                elif idx == n - 1:
                    mf = self._trimf(self.universe, a, b, cc)
                    mf[self.universe >= b] = 1.0
                else:
                    b  = max(b, a + 1.0)
                    cc = max(cc, b + 1.0)
                    mf = self._trimf(self.universe, a, b, cc)

            self.mf_arrays[key] = mf

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_score(self, clearance_mm: float):
        """
        Convert a clearance distance to installability metrics.

        Parameters
        ----------
        clearance_mm : float
            Available space around the pipe in millimetres.

        Returns
        -------
        label : str
            Dominant fuzzy category ('impossible', 'too_tight', 'tight',
            'sufficient', 'clear').
        time_multiplier : float
            Weighted installation time multiplier (1.0 = baseline).
        inst_score : float
            Normalised installability score: 0.0 (impossible) → 1.0 (clear).
        """
        clipped = float(np.clip(clearance_mm, self.universe[0], self.universe[-1]))

        # Membership degree for each category at this clearance value
        memberships = {
            k: float(np.interp(clipped, self.universe, self.mf_arrays[k]))
            for k in ORDERED_CATS
        }

        # Dominant label
        label = max(memberships, key=memberships.get)

        total = sum(memberships.values())
        if total > 1e-9:
            time_mult  = sum(self.multipliers[k] * v for k, v in memberships.items()) / total
            inst_score = sum(CATEGORY_SCORES[k]     * v for k, v in memberships.items()) / total
        else:
            time_mult  = 1.0
            inst_score = 1.0

        return label, round(time_mult, 3), round(inst_score, 3)

    def summary(self):
        """Print a summary of the loaded membership function parameters."""
        print("\n" + "="*55)
        print("  FuzzyInstallability — Membership Function Summary")
        print("="*55)
        print(f"  Responses loaded : {self.n_responses}")
        mf_type = "Gaussian" if self.n_responses > 3 else "Triangular"
        print(f"  Function type    : {mf_type}")
        print()
        print(f"  {'Category':<12}  {'Center (mm)':>12}  {'Multiplier':>10}  {'Score':>6}")
        print(f"  {'-'*12}  {'-'*12}  {'-'*10}  {'-'*6}")
        for k in ORDERED_CATS:
            print(f"  {k:<12}  {self.centers[k]:>12.1f}  "
                  f"{self.multipliers[k]:>10.2f}  {CATEGORY_SCORES[k]:>6.2f}")
        print()

    def preview(self, test_values: list = None):
        """Print fuzzification results for a list of clearance values."""
        if test_values is None:
            test_values = [75, 133, 200, 317, 450, 533, 750, 1033]
        print(f"\n  {'Clearance (mm)':<16} {'Label':<12} {'Time mult':>10} {'Score':>8}")
        print(f"  {'-'*16} {'-'*12} {'-'*10} {'-'*8}")
        for v in test_values:
            label, mult, score = self.get_score(v)
            print(f"  {v:<16} {label:<12} {mult:>10.2f} {score:>8.3f}")
        print()
