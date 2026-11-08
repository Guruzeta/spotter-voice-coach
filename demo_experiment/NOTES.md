# spring-mass sim — comparing integrators

(notes dumped from chat w/ LLM, not cleaned up)

- mass on a spring, no friction. m=1, k=1 for most runs, start at x=1 at rest, simulate to t=100
- asked claude to write a sim with a few integrators (euler, symplectic euler, verlet, rk4) and sweep dt
- run_2 energy goes crazy?? should be constant, there's no friction. bug in the code or physics?
- run_3 and run_4 look fine to the eye, haven't checked energy carefully
- run_5 (rk4) probably the "best" but not sure what best means here
- run_6 I set dt=2.1 by accident and it exploded. why does verlet explode, I thought it was the "good" one
- run_7 stiffer spring (k=4), should oscillate faster? by how much?
- TODO: check the period actually matches theory
- TODO: which integrator should I use for long runs

files:
- configs.csv — method, timestep dt, spring constant k, mass m, initial position/velocity, end time
- runs/run_*.csv — t, x (position), v (velocity), energy, logged every 0.1 time units
- simulate.py — the simulation code (can import simulate() to run new configs)
