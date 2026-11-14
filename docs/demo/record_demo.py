"""Record the README demo: brief -> live sourcing -> review -> export.

Run the app first (scratch DB so the demo does not touch production):
    DATABASE_URL=sqlite:///demo.db streamlit run app.py --server.port 8599 --server.headless true
Then:
    python docs/demo/record_demo.py
    bash docs/demo/make_gif.sh
Writes docs/demo/raw.webm and docs/demo/marks.json (phase timestamps used to speed up the wait).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://localhost:8599"
OUT = Path(__file__).parent
SIZE = {"width": 1280, "height": 800}


def main() -> None:
    marks: dict[str, float] = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport=SIZE, record_video_dir=str(OUT / "tmp"), record_video_size=SIZE)
        page = ctx.new_page()
        t0 = time.monotonic()
        mark = lambda name: marks.__setitem__(name, round(time.monotonic() - t0, 2))  # noqa: E731

        page.goto(URL)
        page.get_by_role("button", name="Find candidates").wait_for()
        page.wait_for_timeout(2500)
        mark("loaded")

        company = page.get_by_label("Hiring company")
        company.click()
        company.press("Control+A")
        company.press_sequentially("Acme Realty", delay=90)
        page.wait_for_timeout(600)
        page.get_by_label("Role title").click()
        page.wait_for_timeout(400)
        page.mouse.move(150, 500)
        for _ in range(6):
            page.mouse.wheel(0, 120)
            page.wait_for_timeout(150)
        page.wait_for_timeout(1200)
        page.get_by_role("button", name="Find candidates").click()
        mark("sourcing_start")

        page.get_by_role("button", name="Approve all that meet must-haves").wait_for(timeout=600_000)
        mark("review")
        page.wait_for_timeout(2500)

        page.mouse.move(800, 500)
        for _ in range(4):
            page.mouse.wheel(0, 130)
            page.wait_for_timeout(200)
        page.wait_for_timeout(800)
        page.get_by_text("Why this score").first.click()
        page.wait_for_timeout(3500)
        bulk = page.get_by_role("button", name="Approve all that meet must-haves")
        if bulk.is_enabled():
            bulk.click()
            page.wait_for_timeout(2000)
        for radio in page.get_by_text("Approve", exact=True).all()[:2]:
            radio.scroll_into_view_if_needed()
            page.wait_for_timeout(700)
            radio.click()
            page.wait_for_timeout(1300)
        page.wait_for_timeout(1000)

        page.mouse.wheel(0, -5000)
        page.wait_for_timeout(600)
        page.get_by_role("tab", name="Search strategy").click()
        page.wait_for_timeout(3000)
        page.get_by_role("tab", name="Review candidates").click()
        page.wait_for_timeout(800)

        finalize = page.get_by_role("button", name="Finalize shortlist")
        finalize.scroll_into_view_if_needed()
        page.wait_for_timeout(1500)
        finalize.click()
        page.get_by_role("heading", name="Contact queue").wait_for(timeout=120_000)
        mark("export")
        page.mouse.move(800, 400)
        page.wait_for_timeout(2000)
        for _ in range(4):
            page.mouse.wheel(0, 130)
            page.wait_for_timeout(200)
        page.wait_for_timeout(2500)
        mark("end")

        video = page.video
        ctx.close()
        video.save_as(OUT / "raw.webm")
        video.delete()
        browser.close()
    (OUT / "marks.json").write_text(json.dumps(marks, indent=2))
    print(marks)


if __name__ == "__main__":
    main()
