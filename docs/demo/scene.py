"""README demo scene. Run the app on a scratch DB first:
    DATABASE_URL=sqlite:///demo.db streamlit run app.py --server.port 8791 --server.headless true
Then:
    python docs/demo/scene.py
    python ~/.claude/skills/demo-gif/scripts/compose.py docs/demo/build --out docs/demo.gif
"""
import os, sys; sys.path.insert(0, os.path.expanduser("~/.claude/skills/demo-gif/scripts"))
from pathlib import Path
from director import Director, run

URL = "http://localhost:8791"


async def scene(d: Director):
    p = d.page
    await p.goto(URL, wait_until="networkidle")
    await p.get_by_role("button", name="Find candidates").wait_for()
    await d.hold(2.0)
    d._log("nav", url=URL)  # start the edit once the app has fully rendered
    await d.caption("Describe the role", step=1)
    await d.type(p.get_by_label("Hiring company"), "Acme Realty", cps=22)
    await d.hold(0.3)
    await d.caption("Let the agent source", step=2)
    await d.click(p.get_by_role("button", name="Find candidates"))
    await d.fast(p.get_by_text("Why this score").first.wait_for(timeout=400_000),
                 label="Sourcing")
    await d.hold(1.0)
    await d.caption("Check the evidence behind a score", step=3)
    why = p.get_by_text("Why this score").first
    await d.click(why)
    await d.hold(0.4)
    box = p.get_by_test_id("stExpander").first
    await d.focus(box, zoom=1.35)
    await d.arrow(box, "Quoted evidence")
    await d.hold(1.2)
    await d.clear_arrow(); await d.unfocus()
    await d.caption("Approve the shortlist", step=4)
    for radio in (await p.get_by_text("Approve", exact=True).all())[:1]:
        await d.click(radio)
        await d.hold(0.2)
    await d.caption("Export with a contact queue", step=5)
    await d.click(p.get_by_role("button", name="Finalize shortlist"))
    await p.get_by_role("heading", name="Contact queue").wait_for(timeout=120_000)
    await d.scroll(300, dur=0.7)
    await d.hold(1.4)


run(scene, out=str(Path(__file__).with_name("build")), title="Talent Sourcing Agent",
    subtitle="Hiring brief to evidence-scored shortlist", url_label="localhost:8501", headless=True)
