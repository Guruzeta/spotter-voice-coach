"""Mass on a spring (simple harmonic oscillator), integrated with different numerical methods.

    m x'' = -k x        exact: x(t) = x0 cos(w t) + (v0/w) sin(w t),  w = sqrt(k/m),  period T = 2*pi/w
    energy E = 0.5 m v^2 + 0.5 k x^2  (should stay constant)

Usage:
    python simulate.py                 # regenerate every run listed in configs.csv
    from simulate import simulate      # run a new configuration, returns a list of rows
"""
import csv
import math
from pathlib import Path

ROOT = Path(__file__).parent


def step_euler(x, v, dt, k, m):
    a = -k / m * x
    return x + v * dt, v + a * dt


def step_symplectic_euler(x, v, dt, k, m):
    v = v - k / m * x * dt
    return x + v * dt, v


def step_verlet(x, v, dt, k, m):
    a = -k / m * x
    x_new = x + v * dt + 0.5 * a * dt * dt
    a_new = -k / m * x_new
    return x_new, v + 0.5 * (a + a_new) * dt


def step_rk4(x, v, dt, k, m):
    def f(x_, v_):
        return v_, -k / m * x_

    k1 = f(x, v)
    k2 = f(x + 0.5 * dt * k1[0], v + 0.5 * dt * k1[1])
    k3 = f(x + 0.5 * dt * k2[0], v + 0.5 * dt * k2[1])
    k4 = f(x + dt * k3[0], v + dt * k3[1])
    return (
        x + dt / 6 * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0]),
        v + dt / 6 * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1]),
    )


METHODS = {
    "euler": step_euler,
    "symplectic_euler": step_symplectic_euler,
    "verlet": step_verlet,
    "rk4": step_rk4,
}


def simulate(method, dt, k=1.0, m=1.0, x0=1.0, v0=0.0, t_end=100.0, log_every=0.1):
    """Returns rows of (t, x, v, energy). Stops early if the solution blows up."""
    stepper = METHODS[method]
    n_steps = int(round(t_end / dt))
    every = max(1, int(round(log_every / dt)))
    x, v, rows = x0, v0, []
    for i in range(n_steps + 1):
        energy = 0.5 * m * v * v + 0.5 * k * x * x
        if i % every == 0:
            rows.append((round(i * dt, 6), x, v, energy))
        if not math.isfinite(energy) or energy > 1e12:
            rows.append((round(i * dt, 6), x, v, energy))
            break
        x, v = stepper(x, v, dt, k, m)
    return rows


def main():
    with open(ROOT / "configs.csv") as f:
        configs = list(csv.DictReader(f))
    (ROOT / "runs").mkdir(exist_ok=True)
    for c in configs:
        rows = simulate(c["method"], float(c["dt"]), float(c["k"]), float(c["m"]), float(c["x0"]), float(c["v0"]), float(c["t_end"]))
        with open(ROOT / "runs" / f"{c['run_id']}.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["t", "x", "v", "energy"])
            w.writerows((t, f"{x:.6g}", f"{v:.6g}", f"{e:.6g}") for t, x, v, e in rows)
        print(f"{c['run_id']}: {c['method']:>16} dt={c['dt']:<5} k={c['k']} -> {len(rows)} rows, final energy {rows[-1][3]:.4g}")


if __name__ == "__main__":
    main()
