"""Compare against two visually confirmed empty Summary panels.

The game has two empty-panel variants. A single template left 1,332 changed
pixels in the other variant and incorrectly counted its background as a body.
"""
from PIL import Image, ImageChops

BODY_BOX = (260, 320, 950, 950)
EMPTY_REFERENCES = (
    'pc-gallery-001-r4/build/frames/frame_03503.png',
    'pc-wide-import-001-r1-s02/build/frames/frame_03103.png',
)

def load_empty_panels(runs):
    panels = []
    for relative in EMPTY_REFERENCES:
        with Image.open(runs / relative) as frame:
            panels.append(frame.convert('RGB').crop(BODY_BOX))
    return panels

def pixels_from_empty(body, panels):
    return min(sum(n for k, n in enumerate(
        ImageChops.difference(body, panel).convert('L').histogram()) if k > 10)
        for panel in panels)
