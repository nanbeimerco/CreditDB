"""
Item-User Bias Decomposition Model.
Implements the baseline linear additive model:
    R_{ui} = \mu + b_u + b_i + \epsilon_{ui}
Optimized via Regularized Alternating Least Squares (ALS):
    min_{b_u, b_i} sum_{(u,i)} (R_{ui} - (\mu + b_u + b_i))^2 + \lambda_1 * sum_u b_u^2 + \lambda_2 * sum_i b_i^2
"""

from __future__ import annotations
import math
from typing import Dict, List, Tuple, Union, Optional
import numpy as np
import pandas as pd


class ItemUserBiasModel:
    """
    Solves for user bias (b_u) and item bias (b_i) from observed rating matrix R_{ui}.
    Item bias b_i represents the pure, de-biased latent capability score of anime i.
    """

    def __init__(
        self,
        lambda_user: float = 10.0,
        lambda_item: float = 10.0,
        max_iter: int = 50,
        tol: float = 1e-5,
        verbose: bool = False,
    ):
        """
        Args:
            lambda_user: Regularization parameter lambda_1 for user bias b_u.
            lambda_item: Regularization parameter lambda_2 for item bias b_i.
            max_iter: Maximum ALS iterations.
            tol: Tolerance for convergence criterion (change in loss).
            verbose: If True, prints iteration progress and loss.
        """
        self.lambda_user = float(lambda_user)
        self.lambda_item = float(lambda_item)
        self.max_iter = max_iter
        self.tol = tol
        self.verbose = verbose

        self.global_mean: float = 0.0
        self.user_biases: Dict[Union[int, str], float] = {}
        self.item_biases: Dict[Union[int, str], float] = {}
        self.loss_history: List[float] = []
        self.is_fitted: bool = False

    def fit(
        self,
        data: Union[pd.DataFrame, List[Tuple[Union[int, str], Union[int, str], float]]],
        user_col: str = "user_id",
        item_col: str = "item_id",
        score_col: str = "score",
    ) -> "ItemUserBiasModel":
        """
        Fits the ALS bias decomposition model.

        Args:
            data: DataFrame or list of (user_id, item_id, score) tuples.
            user_col: Column name for user ID if DataFrame.
            item_col: Column name for item ID if DataFrame.
            score_col: Column name for rating score if DataFrame.

        Returns:
            self
        """
        if isinstance(data, pd.DataFrame):
            users = data[user_col].values
            items = data[item_col].values
            scores = data[score_col].values.astype(float)
        else:
            users = np.array([x[0] for x in data])
            items = np.array([x[1] for x in data])
            scores = np.array([float(x[2]) for x in data])

        if len(scores) == 0:
            raise ValueError("Input data cannot be empty.")

        self.global_mean = float(np.mean(scores))
        residuals = scores - self.global_mean

        # Group data by user and by item
        user_to_items: Dict[Union[int, str], List[int]] = {}
        item_to_users: Dict[Union[int, str], List[int]] = {}

        for idx in range(len(scores)):
            u = users[idx]
            i = items[idx]
            if u not in user_to_items:
                user_to_items[u] = []
            user_to_items[u].append(idx)

            if i not in item_to_users:
                item_to_users[i] = []
            item_to_users[i].append(idx)

        # Initialize biases to 0.0
        b_u: Dict[Union[int, str], float] = {u: 0.0 for u in user_to_items}
        b_i: Dict[Union[int, str], float] = {i: 0.0 for i in item_to_users}

        self.loss_history = []
        prev_loss = float("inf")

        for iteration in range(self.max_iter):
            # 1. Update user biases: b_u = sum_{i in I_u} (R_{ui} - \mu - b_i) / (|I_u| + \lambda_1)
            for u, indices in user_to_items.items():
                sum_residual_item = sum(residuals[idx] - b_i[items[idx]] for idx in indices)
                b_u[u] = sum_residual_item / (len(indices) + self.lambda_user)

            # 2. Update item biases: b_i = sum_{u in U_i} (R_{ui} - \mu - b_u) / (|U_i| + \lambda_2)
            for i, indices in item_to_users.items():
                sum_residual_user = sum(residuals[idx] - b_u[users[idx]] for idx in indices)
                b_i[i] = sum_residual_user / (len(indices) + self.lambda_item)

            # 3. Calculate regularized squared loss
            sq_err = 0.0
            for idx in range(len(scores)):
                pred = self.global_mean + b_u[users[idx]] + b_i[items[idx]]
                sq_err += (scores[idx] - pred) ** 2

            reg_u = self.lambda_user * sum(v ** 2 for v in b_u.values())
            reg_i = self.lambda_item * sum(v ** 2 for v in b_i.values())
            total_loss = sq_err + reg_u + reg_i
            self.loss_history.append(total_loss)

            if self.verbose:
                rmse = math.sqrt(sq_err / len(scores))
                print(f"Iteration {iteration + 1}/{self.max_iter} - Loss: {total_loss:.4f}, RMSE: {rmse:.4f}")

            if abs(prev_loss - total_loss) < self.tol:
                if self.verbose:
                    print(f"Converged at iteration {iteration + 1}")
                break
            prev_loss = total_loss

        self.user_biases = b_u
        self.item_biases = b_i
        self.is_fitted = True
        return self

    def predict(self, user_id: Union[int, str], item_id: Union[int, str]) -> float:
        """
        Predicts score R_{ui} = \mu + b_u + b_i.
        Uses 0.0 for unknown user/item bias.
        """
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted before calling predict.")
        bu = self.user_biases.get(user_id, 0.0)
        bi = self.item_biases.get(item_id, 0.0)
        return self.global_mean + bu + bi

    def get_item_biases(self) -> Dict[Union[int, str], float]:
        """Returns dictionary mapping item_id -> de-biased latent capability score b_i."""
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted first.")
        return dict(self.item_biases)

    def get_user_biases(self) -> Dict[Union[int, str], float]:
        """Returns dictionary mapping user_id -> user severity bias b_u."""
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted first.")
        return dict(self.user_biases)
