"""Non-negative CP/PARAFAC of a 3-way array with missing values (numpy only).

Algorithm: alternating updates of the three factor matrices with HALS
(hierarchical alternating least squares; Cichocki & Phan 2009, IEICE Trans.
Fundamentals E92-A:708-721), which solves each column's non-negative least
squares problem exactly. Missing values are handled by expectation-
maximisation: before each sweep they are replaced by the current model
(Tomasi & Bro 2005, Chemometr. Intell. Lab. Syst. 75:163-180), the approach of
the N-way toolbox used by drEEM.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

EPS = 1e-16  # floor for non-negative entries; keeps HALS columns from dying


@dataclass
class CPResult:
    A: np.ndarray
    B: np.ndarray
    C: np.ndarray
    sse: float
    n_iter: int
    converged: bool
    sse_trace: list[float] = field(default_factory=list)


def khatri_rao(P: np.ndarray, Q: np.ndarray) -> np.ndarray:
    """Column-wise Kronecker product; row index p * len(Q) + q."""
    return (P[:, None, :] * Q[None, :, :]).reshape(-1, P.shape[1])


def unfold(X: np.ndarray, mode: int) -> np.ndarray:
    return np.moveaxis(X, mode, 0).reshape(X.shape[mode], -1)


def reconstruct(A: np.ndarray, B: np.ndarray, C: np.ndarray) -> np.ndarray:
    return (khatri_rao(A, B) @ C.T).reshape(A.shape[0], B.shape[0], C.shape[0])


def _hals_update(M: np.ndarray, R: np.ndarray, G: np.ndarray) -> None:
    """In-place HALS sweep over the columns of M for min ||X_(n) - M P^T||, M >= 0."""
    for f in range(M.shape[1]):
        if G[f, f] <= 0:
            continue
        M[:, f] = np.maximum(EPS, M[:, f] + (R[:, f] - M @ G[:, f]) / G[f, f])


def _balance(A: np.ndarray, B: np.ndarray, C: np.ndarray) -> None:
    """Unit-norm columns for B and C; the scale goes into A."""
    nb = np.linalg.norm(B, axis=0)
    nc = np.linalg.norm(C, axis=0)
    nb[nb == 0] = 1
    nc[nc == 0] = 1
    B /= nb
    C /= nc
    A *= nb * nc


def nn_parafac(
    X: np.ndarray,
    rank: int,
    *,
    init: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None,
    random_state: int | np.random.Generator | None = None,
    tol: float = 1e-8,
    max_iter: int = 5000,
) -> CPResult:
    """Fit X (I x J x K, NaN = missing) ~ sum_f a_f o b_f o c_f with A, B, C >= 0.

    Stops when the relative decrease of the residual sum of squares over the
    observed entries falls below ``tol``, or after ``max_iter`` sweeps.
    """
    X = np.asarray(X, dtype=float)
    if X.ndim != 3:
        raise ValueError("X must be 3-way")
    observed = np.isfinite(X)
    if not observed.any():
        raise ValueError("X has no observed values")
    rng = np.random.default_rng(random_state)
    n_i, n_j, n_k = X.shape
    if init is None:
        A = rng.random((n_i, rank))
        B = rng.random((n_j, rank))
        C = rng.random((n_k, rank))
    else:
        A, B, C = (np.array(m, dtype=float, copy=True) for m in init)
    A, B, C = (np.maximum(m, EPS) for m in (A, B, C))
    _balance(A, B, C)

    has_missing = not observed.all()
    # least-squares scale of the random start, so missing values start near the data
    model = reconstruct(A, B, C)
    s = np.sum(X[observed] * model[observed]) / max(np.sum(model[observed] ** 2), EPS)
    A *= max(s, EPS)
    model *= max(s, EPS)
    Xf = X

    trace: list[float] = []
    prev = np.inf
    converged = False
    n_iter = 0
    for n_iter in range(1, max_iter + 1):  # noqa: B007 (n_iter is reported after the loop)
        if has_missing:
            Xf = np.where(observed, X, model)
        # MTTKRPs as BLAS products without unfolding copies: T = X x3 C (I x J x F)
        T = Xf @ C
        _hals_update(A, np.einsum("ijf,jf->if", T, B), (B.T @ B) * (C.T @ C))
        _hals_update(B, np.einsum("ijf,if->jf", T, A), (A.T @ A) * (C.T @ C))
        _hals_update(C, Xf.reshape(n_i * n_j, n_k).T @ khatri_rao(A, B),
                     (A.T @ A) * (B.T @ B))
        _balance(A, B, C)

        model = reconstruct(A, B, C)
        sse = float(np.sum((X - model)[observed] ** 2))
        trace.append(sse)
        if np.isfinite(prev) and abs(prev - sse) <= tol * max(prev, EPS):
            converged = True
            break
        prev = sse
    return CPResult(A, B, C, trace[-1], n_iter, converged, trace)
