"""
Helpers for Plotly 2-D plots: ``go.Contour`` only accepts 1-D ``x``/``y`` axes.
"""

import numpy as np
from scipy.interpolate import griddata


def rectilinear_grid_for_plotly_contour(x_mesh, y_mesh, z_val, *, n_boost=96):
    """
    Resample ``z`` on a structured (2-D) ``x_mesh``/``y_mesh`` to a rectilinear grid.

    ``go.Contour`` only supports 1-D ``x`` and ``y`` with 2-D ``z`` (row = y, col = x).
    Matplotlib-style Hantush mirror grids use 2-D coordinate arrays; passing those as
    Plotly ``x``/``y`` breaks rendering. This helper interpolates onto ``linspace`` axes.
    """
    xm = np.asarray(x_mesh, dtype=float)
    ym = np.asarray(y_mesh, dtype=float)
    zv = np.asarray(z_val, dtype=float)
    if xm.shape != ym.shape or xm.shape != zv.shape:
        raise ValueError(f"x_grid, y_grid, z must match shapes; got {xm.shape}, {ym.shape}, {zv.shape}")

    pts = np.column_stack([xm.ravel(), ym.ravel()])
    vals = zv.ravel()
    finite = np.isfinite(vals) & np.all(np.isfinite(pts), axis=1)
    if not np.any(finite):
        raise ValueError("no finite z samples for contour resampling")

    x_min = float(np.nanmin(xm))
    x_max = float(np.nanmax(xm))
    y_min = float(np.nanmin(ym))
    y_max = float(np.nanmax(ym))
    n_src = max(xm.shape)
    n = int(np.clip(n_boost, 48, min(200, max(48, 6 * n_src))))

    xi = np.linspace(x_min, x_max, n)
    yi = np.linspace(y_min, y_max, n)
    Xi, Yi = np.meshgrid(xi, yi, indexing="xy")
    zi = griddata(pts[finite], vals[finite], (Xi, Yi), method="linear")
    if np.any(~np.isfinite(zi)):
        zi_nn = griddata(pts[finite], vals[finite], (Xi, Yi), method="nearest")
        zi = np.where(np.isfinite(zi), zi, zi_nn)
    return xi, yi, zi
