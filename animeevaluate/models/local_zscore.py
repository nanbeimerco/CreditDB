"""
Local Z-Score Standardization Model by Release Year Window.
Implements:
    Z_i = (b_i - \mu_{t(i)}) / \sigma_{t(i)}
Where:
    - t(i): release year of anime i
    - \mu_{t(i)}: mean of b_j for anime j in window [t(i) - W, t(i) + W]
    - \sigma_{t(i)}: standard deviation of b_j in window [t(i) - W, t(i) + W]
    - Z_i: target relative deviation score (leak-free & era-invariant)
"""

from __future__ import annotations
import math
from typing import Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd


class LocalZScoreModel:
    """
    Standardizes item biases b_i using local moving windows around release year t(i).
    Eliminates historical inflation/deflation and era-dependent scoring differences.
    """

    def __init__(
        self,
        window_size: int = 3,
        min_items_in_window: int = 3,
        eps: float = 1e-6,
    ):
        """
        Args:
            window_size: Half-window W in years (window span is [year - W, year + W]).
            min_items_in_window: Minimum sample size in window before expanding or smoothing.
            eps: Small constant to avoid zero-division in standard deviation.
        """
        self.window_size = window_size
        self.min_items = min_items_in_window
        self.eps = eps

        self.global_b_mean: float = 0.0
        self.global_b_std: float = 1.0
        self.item_years: Dict[Union[int, str], int] = {}
        self.item_biases: Dict[Union[int, str], float] = {}
        self.item_zscores: Dict[Union[int, str], float] = {}
        self.year_stats_cache: Dict[int, Tuple[float, float, int]] = {}
        self.is_fitted: bool = False

    def fit_transform(
        self,
        item_biases: Dict[Union[int, str], float],
        item_years: Dict[Union[int, str], int],
    ) -> Dict[Union[int, str], float]:
        """
        Fits window statistics and transforms item biases to local Z-scores.

        Args:
            item_biases: Dictionary mapping item_id -> de-biased score b_i
            item_years: Dictionary mapping item_id -> release year t(i)

        Returns:
            Dictionary mapping item_id -> local Z-score Z_i
        """
        self.item_biases = dict(item_biases)
        self.item_years = dict(item_years)

        valid_items = [i for i in self.item_biases if i in self.item_years]
        if not valid_items:
            raise ValueError("No common items found between item_biases and item_years.")

        all_b = [self.item_biases[i] for i in valid_items]
        self.global_b_mean = float(np.mean(all_b))
        self.global_b_std = float(np.std(all_b)) + self.eps

        # Group items by year
        year_to_items: Dict[int, List[Union[int, str]]] = {}
        for i in valid_items:
            yr = self.item_years[i]
            if yr not in year_to_items:
                year_to_items[yr] = []
            year_to_items[yr].append(i)

        self.year_stats_cache = {}
        self.item_zscores = {}

        for i in valid_items:
            yr = self.item_years[i]
            mu_t, sigma_t = self._get_year_stats(yr, year_to_items)
            b_val = self.item_biases[i]
            z_val = (b_val - mu_t) / max(sigma_t, self.eps)
            self.item_zscores[i] = float(z_val)

        self.is_fitted = True
        return dict(self.item_zscores)

    def _get_year_stats(
        self,
        target_year: int,
        year_to_items: Dict[int, List[Union[int, str]]],
    ) -> Tuple[float, float]:
        """Computes or retrieves mean and std for the window [target_year - W, target_year + W]."""
        if target_year in self.year_stats_cache:
            mu, sigma, _ = self.year_stats_cache[target_year]
            return mu, sigma

        current_w = self.window_size
        window_b: List[float] = []

        while len(window_b) < self.min_items and current_w <= 15:
            window_b = []
            for y in range(target_year - current_w, target_year + current_w + 1):
                for item_id in year_to_items.get(y, []):
                    window_b.append(self.item_biases[item_id])
            current_w += 1

        if len(window_b) < self.min_items:
            # Fall back to global stats
            mu = self.global_b_mean
            sigma = self.global_b_std
            count = len(window_b)
        else:
            mu = float(np.mean(window_b))
            sigma = float(np.std(window_b))
            if sigma < self.eps:
                sigma = self.global_b_std
            count = len(window_b)

        self.year_stats_cache[target_year] = (mu, sigma, count)
        return mu, sigma

    def transform_single(self, b_val: float, release_year: int) -> float:
        """Transforms a single b_i value at given release year into local Z-score."""
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted before transforming.")
        if release_year in self.year_stats_cache:
            mu, sigma, _ = self.year_stats_cache[release_year]
        else:
            mu = self.global_b_mean
            sigma = self.global_b_std
        return float((b_val - mu) / max(sigma, self.eps))

    def inverse_transform_single(self, z_val: float, release_year: int) -> float:
        """Inverts a local Z-score back to estimated item bias b_i."""
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted before inverse transforming.")
        if release_year in self.year_stats_cache:
            mu, sigma, _ = self.year_stats_cache[release_year]
        else:
            mu = self.global_b_mean
            sigma = self.global_b_std
        return float(z_val * sigma + mu)
