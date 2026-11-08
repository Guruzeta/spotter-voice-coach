"""Hit the running backend the same way the voice agent does. Usage: uv run python smoke_test.py"""
import httpx

CODE = """
from simulate import simulate
rows = simulate("verlet", 0.01, k=8, m=2, x0=1, v0=0, t_end=20)
t = np.array([r[0] for r in rows]); x = np.array([r[1] for r in rows])
up = t[1:][(x[:-1] < 0) & (x[1:] >= 0)]
print("simulated period", round(np.mean(np.diff(up)), 4), "theory", round(2 * np.pi * np.sqrt(2 / 8), 4))
plt.plot(t, x, label="simulation"); plt.plot(t, np.cos(2 * t), "--", label="exact"); plt.legend()
"""

r = httpx.post("http://localhost:8000/api/run", json={"purpose": "smoke test: m=2, k=8 oscillator", "code": CODE}, timeout=120)
print(r.json())
