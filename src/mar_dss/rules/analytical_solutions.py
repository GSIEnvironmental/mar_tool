
import os
import numpy as np
from scipy.special import erf
from scipy.integrate import quad_vec
import matplotlib.pyplot as plt
from scipy.special import exp1


def concat(dh):    
    dh = [np.fliplr(dh), dh]
    dh = np.concatenate(dh, axis=1)
    dh = [np.flipud(dh), dh]
    dh = np.concatenate(dh, axis=0)
    return dh

def mirror(u, y_axis=True):

    u = [-1*np.fliplr(u), u]
    u = np.concatenate(u, axis=1)
    u = [np.flipud(u), u]
    u = np.concatenate(u, axis=0)
    u = np.fliplr(u)
    return u

def compute_integral(alpha, beta):
    def func(tau):
        return erf(alpha / np.sqrt(tau)) * erf(beta / np.sqrt(tau))
    
    result, error = quad_vec(func, 0, 1.0)
    return result


def mounding_integral_sum_at_point(x, y, l_half, a_half, t, k, b, sy):
    """
    Sum of the four Hantush-type integrals S1..S4 at (x, y) for a rectangular recharge strip.

    Matches the kernel used in :func:`compute_mounding_grid` and ``mymound.py``.
    ``l_half`` / ``a_half`` are half-length and half-width of the recharge area.

    Parameters ``t``, ``k``, ``b``, ``sy`` must be positive.
    """
    if t <= 0 or k <= 0 or b <= 0 or sy <= 0:
        return 0.0
    v = 4.0 * t * k * b / sy
    sv = np.sqrt(v)

    p1 = (l_half + x) / sv
    p2 = (a_half + y) / sv
    s1 = compute_integral(p1, p2)

    p1 = (l_half + x) / sv
    p2 = (a_half - y) / sv
    s2 = compute_integral(p1, p2)

    p1 = (l_half - x) / sv
    p2 = (a_half + y) / sv
    s3 = compute_integral(p1, p2)

    p1 = (l_half - x) / sv
    p2 = (a_half - y) / sv
    s4 = compute_integral(p1, p2)

    return s1 + s2 + s3 + s4


def compute_mounding_grid(Lx, Ly, N, l, a, t, b, w, k, sy, h0):
    """
    Hantush-type rectangular recharge mounding on ``[-Lx, Lx] × [-Ly, Ly]``.

    Uses ``2*N`` points per axis (same array size as the previous quarter-grid + ``concat`` layout).

    Returns ``x, y, h`` all with shape ``(2*N, 2*N)`` suitable for ``matplotlib.contour``.
    """
    if N is None:
        N = 20

    v = 4 * t * k * b / sy
    n_full = int(2 * N)
    x1 = np.linspace(-Lx, Lx, n_full)
    y1 = np.linspace(-Ly, Ly, n_full)
    x_q, y_q = np.meshgrid(x1, y1, indexing="xy")

    p1 = (l + x_q) / np.sqrt(v)
    p2 = (a + y_q) / np.sqrt(v)
    s1 = compute_integral(p1, p2)

    p1 = (l + x_q) / np.sqrt(v)
    p2 = (a - y_q) / np.sqrt(v)
    s2 = compute_integral(p1, p2)

    p1 = (l - x_q) / np.sqrt(v)
    p2 = (a + y_q) / np.sqrt(v)
    s3 = compute_integral(p1, p2)

    p1 = (l - x_q) / np.sqrt(v)
    p2 = (a - y_q) / np.sqrt(v)
    s4 = compute_integral(p1, p2)

    s = s1 + s2 + s3 + s4

    v1 = k * b / sy
    dh = (w / (2 * k)) * (v1 * t) * s
    h = h0 + (dh**0.5)
    return x_q, y_q, h

def compute_recharge_rate(x,y,t,del_h, spread_area, k,b,sy):

    v = 4*t*k*b/sy
    l = np.sqrt(spread_area)
    a = l
    p1 = (l+x)/np.sqrt(v)
    p2 = (a+y)/np.sqrt(v)
    s1 = compute_integral(p1, p2)

    p1 = (l+x)/np.sqrt(v)
    p2 = (a-y)/np.sqrt(v)
    s2 = compute_integral(p1, p2)

    p1 = (l-x)/np.sqrt(v)
    p2 = (a+y)/np.sqrt(v)
    s3 = compute_integral(p1, p2)

    p1 = (l-x)/np.sqrt(v)
    p2 = (a-y)/np.sqrt(v)
    s4 = compute_integral(p1, p2)

    s = s1+s2+s3+s4

    h2 = np.power(del_h, 2)
    v1 =k*b/sy

    recharge_rate = 2 * k * h2/(v1*t*s)    
    return recharge_rate

def compute_recharge_mound(x,y,t,recharge_rate, spread_area, k,b,sy):

    v = 4*t*k*b/sy
    l = np.sqrt(spread_area)
    a = l
    p1 = (l+x)/np.sqrt(v)
    p2 = (a+y)/np.sqrt(v)
    s1 = compute_integral(p1, p2)

    p1 = (l+x)/np.sqrt(v)
    p2 = (a-y)/np.sqrt(v)
    s2 = compute_integral(p1, p2)

    p1 = (l-x)/np.sqrt(v)
    p2 = (a+y)/np.sqrt(v)
    s3 = compute_integral(p1, p2)

    p1 = (l-x)/np.sqrt(v)
    p2 = (a-y)/np.sqrt(v)
    s4 = compute_integral(p1, p2)

    s = s1+s2+s3+s4

    
    v1 =k*b/sy

    #recharge_rate = 2 * k * h2/(v1*t*s)
    h2 = recharge_rate * v1 * t * s / (2 * k)
    del_h = np.power(h2, 0.5)    
    return del_h

def theis_drawdown_or_Q(Q_or_dh, T, S, r, t, compute_Q=True):
    """
    Computes the drawdown (dh) or pumping rate (Q) in a confined aquifer using 
    the Theis (Transient) solution.

    The Theis equation is given by: s = (Q / (4 * pi * T)) * W(u)

    Parameters:
    -----------
    Q : float
        Pumping rate (Volume/Time, e.g., m^3/day).
    T : float
        Aquifer Transmissivity (Area/Time, e.g., m^2/day).
    S : float
        Aquifer Storativity (dimensionless).
    r : float
        Radial distance from the pumping well (Length, e.g., m).
    t : float
        Time since pumping started (Time, e.g., day).

    Returns:
    --------
    float
        The calculated drawdown (s) at distance 'r' and time 't' (Length, e.g., m).
        Returns 0 if time 't' is zero to avoid division by zero.
    """
    # Ensure all inputs are positive floats
    if T <= 0 or S <= 0 or r <= 0:
        raise ValueError("Q, T, S, and r must be positive.")

    # Handle the t=0 case, as drawdown is zero before pumping starts
    if t <= 0:
        return 0.0

    # 1. Calculate the 'u' parameter (Dimensionless time/distance parameter)
    # u = (r^2 * S) / (4 * T * t)
    # 
    try:
        u = (r**2 * S) / (4 * T * t)
    except Exception as e:
        print(f"Error calculating u: {e}")
        return 0.0

    # 2. Calculate the Well Function W(u)
    # The Well Function W(u) is mathematically equivalent to the Exponential Integral E1(u)
    # W(u) = E1(u) = integral from u to infinity of (e^-y / y) dy
    try:
        # exp1 is the scipy function for the Exponential Integral E1(u)
        W_u = exp1(u)
    except Exception as e:
        # Fallback for extreme u values, although exp1 is robust
        print(f"Error calculating W(u): {e}. Returning 0.")
        return 0.0

    # 3. Calculate Drawdown (s)
    # s = (Q / (4 * pi * T)) * W(u)
    if compute_Q:
        drawdown = Q_or_dh
        Q = (drawdown/W_u) * (4 * np.pi * T)
        return Q

    else:
        Q = Q_or_dh
        drawdown= (Q / (4 * np.pi * T)) * W_u
        return drawdown
