"""Model diagnostics: core consistency, leverage, congruence and component matching."""

from __future__ import annotations

import numpy as np
from scipy.optimize import linear_sum_assignment


def core_consistency(X: np.ndarray, A: np.ndarray, B: np.ndarray, C: np.ndarray) -> float:
    """CORCONDIA in percent (Bro & Kiers 2003, J. Chemometrics 17:274-286).

    The least-squares Tucker3 core for the given loadings is
    ``X x1 A+ x2 B+ x3 C+`` (``+`` = pseudo-inverse); with ``T`` the
    superdiagonal identity core, ``CC = 100 (1 - ||G - T||^2 / F)``.
    ``X`` must be complete: impute missing values (e.g. with the model) first.
    """
    if not np.isfinite(X).all():
        raise ValueError("core_consistency needs a complete array; impute missing values")
    F = A.shape[1]
    G = np.tensordot(np.linalg.pinv(A), X, axes=(1, 0))  # F x J x K
    G = np.tensordot(G, np.linalg.pinv(B), axes=(1, 1))  # F x K x F
    G = np.tensordot(G, np.linalg.pinv(C), axes=(1, 1))  # F x F x F
    T = np.zeros((F, F, F))
    T[np.arange(F), np.arange(F), np.arange(F)] = 1.0
    return float(100.0 * (1.0 - np.sum((G - T) ** 2) / F))


def leverage(M: np.ndarray) -> np.ndarray:
    """Leverage of each row of a loading matrix: diag(M (M^T M)^-1 M^T)."""
    return np.einsum("if,fg,ig->i", M, np.linalg.pinv(M.T @ M), M)


def tucker_congruence(P: np.ndarray, Q: np.ndarray) -> np.ndarray:
    """Tucker's congruence coefficients between the columns of P and Q (F_P x F_Q)."""
    P = np.asarray(P, dtype=float)
    Q = np.asarray(Q, dtype=float)
    num = P.T @ Q
    den = np.outer(np.linalg.norm(P, axis=0), np.linalg.norm(Q, axis=0))
    with np.errstate(invalid="ignore", divide="ignore"):
        return num / den


def match_components(
    ex1: np.ndarray, em1: np.ndarray, ex2: np.ndarray, em2: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Pair components of two models by maximising the product of ex and em congruence.

    Returns ``(order2, tcc_ex, tcc_em)``: model 2's component ``order2[f]``
    matches model 1's component ``f``, with the congruences of each pair.
    """
    tex = tucker_congruence(ex1, ex2)
    tem = tucker_congruence(em1, em2)
    rows, cols = linear_sum_assignment(-(tex * tem))
    order = cols[np.argsort(rows)]
    f = np.arange(len(order))
    return order, tex[f, order], tem[f, order]
