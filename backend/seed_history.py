"""Seed 8 weeks of realistic training history (lb) so Spotter has something to reason over."""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "history.csv"

# exercise: (starting top-set weight, weekly increase)
LIFTS = {"squat": (185, 5), "bench press": (135, 2.5), "deadlift": (225, 5), "goblet squat": (25, 2.5)}


def main():
    rng = random.Random(3)
    rows = []
    start = date.today() - timedelta(weeks=8)
    for week in range(8):
        day = start + timedelta(weeks=week)
        for ex, (w0, inc) in LIFTS.items():
            stall = week >= 6 and ex == "bench press"  # bench has stalled for 2 weeks
            top = w0 + inc * (5 if stall else week)
            for s in range(3):
                reps = 5 if s < 2 else rng.choice([4, 5])
                rpe = round(min(10, 7 + 0.5 * s + rng.choice([0, 0.5]) + (0.5 if stall else 0)), 1)
                rows.append([day.isoformat(), ex, top, reps, rpe])
    OUT.parent.mkdir(exist_ok=True)
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "exercise", "weight_lb", "reps", "rpe"])
        w.writerows(rows)
    print(f"wrote {len(rows)} sets to {OUT}")


if __name__ == "__main__":
    main()
