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


def shift_shape_congruence(P: np.ndarray, Q: np.ndarray, wavelengths: np.ndarray) -> np.ndarray:
    """Shift- and shape-sensitive congruence between the columns of P and Q (F_P x F_Q).

    SSC (Wünsch et al. 2019, Anal. Methods 11:888-893) lowers Tucker's
    congruence when two spectra peak at different wavelengths or have
    different widths, which TCC hardly notices::

        SSC = TCC - alpha - beta
        alpha = |wavelength of maximum(p) - wavelength of maximum(q)| / range
        beta  = |area(p / max p) - area(q / max q)| / range

    with ``range`` = last - first wavelength. The areas are trapezoidal
    integrals over ``wavelengths``, so SSC does not depend on the wavelength
    step; staRdom's ``ssc`` sums the points instead, which on a 1 nm grid
    differs only by the half-weight of the two end points. Wünsch et al.
    compare emission spectra with SSC and excitation spectra with TCC.
    """
    P = np.asarray(P, dtype=float)
    Q = np.asarray(Q, dtype=float)
    wl = np.asarray(wavelengths, dtype=float)
    if P.shape[0] != wl.size or Q.shape[0] != wl.size:
        raise ValueError("P, Q and wavelengths must have the same number of rows")
    span = float(wl.max() - wl.min())
    if span <= 0:
        raise ValueError("wavelengths must span a range")

    def peak_and_area(M: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        top = M.max(axis=0)
        if np.any(top <= 0):
            raise ValueError("every spectrum must have a positive maximum")
        return wl[M.argmax(axis=0)], np.trapezoid(M / top, wl, axis=0)

    peak_p, area_p = peak_and_area(P)
    peak_q, area_q = peak_and_area(Q)
    alpha = np.abs(peak_p[:, None] - peak_q[None, :]) / span
    beta = np.abs(area_p[:, None] - area_q[None, :]) / span
    return tucker_congruence(P, Q) - alpha - beta


def eemqual(model, split) -> dict[str, float]:
    """EEMqual = fit x core consistency x split-half similarity (Bro & Vidal 2011).

    Bro & Vidal (2011, Chemom. Intell. Lab. Syst. 106:86-92) rank PARAFAC
    models by the product of three numbers between 0 and 1. In eemkit they are:

    * ``fit``: explained variance / 100;
    * ``core_consistency``: core consistency / 100, negative values set to 0;
    * ``split_half``: the lowest Tucker congruence of the split-half validation
      (``split.attrs["min_tcc"]``, over every test, component and mode).

    The split-half term is an eemkit choice: staRdom's ``eempf_eemqual`` uses
    the product of the best congruence of each component, which is never
    lower. EEMqual compares models fitted to the same data; it does not
    replace looking at the components.
    """
    fit = float(model.attrs["explained_variance_pct"]) / 100.0
    cc = max(float(model.attrs["core_consistency_pct"]), 0.0) / 100.0
    sh = float(split.attrs["min_tcc"])
    return {"fit": fit, "core_consistency": cc, "split_half": sh, "eemqual": fit * cc * sh}


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
