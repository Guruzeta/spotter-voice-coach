"""Drive the whiteboard like the agent would and save screenshots (needs `npm run dev` running).

uv run --with playwright python scripts/board_check.py
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).parent / "board_shots"
OUT.mkdir(exist_ok=True)

STEP1 = 'flowchart LR\n A["Spring pulls back"]'
STEP2 = STEP1 + '\n A --> B["Mass speeds up"]'
STEP3 = STEP2 + '\n B --> C["Overshoots center"]\n C --> A'

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1400, "height": 860})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("http://localhost:5173/")
    page.wait_for_function("window.board")
    page.evaluate("board.agenda(['The question','The setup','Energy drift','Takeaways'], 2)")
    page.evaluate(f"board.sketch({STEP1!r}, 'Why it oscillates')")
    page.wait_for_timeout(1600)
    page.evaluate(f"board.sketch({STEP2!r})")
    page.wait_for_timeout(500)
    page.screenshot(path=OUT / "1_mid_draw.png")
    page.wait_for_timeout(1500)
    page.evaluate(f"board.sketch({STEP3!r})")
    page.evaluate("board.write('T = 2π√(m/k) ≈ 6.28')")
    page.wait_for_timeout(5000)
    page.screenshot(path=OUT / "2_done.png")
    print("errors:", errors or "none")
    browser.close()
