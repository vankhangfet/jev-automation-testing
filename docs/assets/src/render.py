"""Deterministic frame renderer: loads an HTML page exposing window.onFrame(t)
and screenshots every frame. Usage: render.py page.html seconds fps w h outdir [scale]"""
import sys, pathlib
from playwright.sync_api import sync_playwright

page_path, seconds, fps, w, h, outdir = sys.argv[1:7]
scale = float(sys.argv[7]) if len(sys.argv) > 7 else 1.0
seconds, fps, w, h = float(seconds), int(fps), int(w), int(h)
out = pathlib.Path(outdir); out.mkdir(parents=True, exist_ok=True)
import os
A=int(os.environ.get("FA","0")); B=os.environ.get("FB")

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=scale)
    pg.goto(pathlib.Path(page_path).resolve().as_uri())
    pg.evaluate("document.fonts.ready")
    pg.evaluate("window.__manual = true")
    n = int(round(seconds * fps))
    for i in range(A, int(B) if B else n):
        pg.evaluate(f"window.onFrame({i / fps})")
        pg.screenshot(path=str(out / f"f{i:05d}.png"))
    b.close()
print("frames:", n)
