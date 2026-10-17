"""Generate a distinctive New York skyline icon without external artwork."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

SIZE = 1024
img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((34, 34, 990, 990), radius=215, fill="#061018", outline="#F2BE51", width=24)
d.rounded_rectangle((67, 67, 957, 957), radius=184, outline="#8C672C", width=5)
# Original stylized skyline with Empire State Building at center.
buildings = [(105, 560, 205, 825), (210, 500, 275, 825), (285, 610, 355, 825),
             (365, 480, 430, 825), (590, 530, 675, 825), (685, 440, 745, 825),
             (755, 585, 830, 825), (835, 515, 910, 825)]
for x1, y1, x2, y2 in buildings:
    d.rectangle((x1, y1, x2, y2), fill="#172B3C")
    for y in range(y1 + 22, y2 - 12, 35):
        for x in range(x1 + 14, x2 - 8, 22):
            d.rectangle((x, y, x + 6, y + 12), fill="#E7AE47")
d.rectangle((445, 385, 575, 825), fill="#E6AE45")
d.polygon([(432, 395), (588, 395), (563, 345), (457, 345)], fill="#F2BE51")
d.rectangle((480, 265, 540, 345), fill="#F2BE51")
d.rectangle((505, 188, 515, 265), fill="#F2BE51")
d.ellipse((501, 178, 519, 196), fill="#FFF2C5")
d.line([(105, 830), (910, 830)], fill="#F2BE51", width=12)
try:
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 108)
except OSError:
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 108)
    except OSError:
        font = ImageFont.load_default()
d.rounded_rectangle((205, 844, 819, 952), radius=22, fill="#07111A", outline="#F2BE51", width=5)
d.text((512, 897), "NY  BBS", font=font, anchor="mm", fill="#F2BE51")
out = Path("build")
out.mkdir(exist_ok=True)
img.save(out / "empire-icon.png")
