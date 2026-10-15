"""Create an original Jersey-colored icon for the Intel Mac app."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

SIZE = 1024
img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((38, 38, 986, 986), radius=200, fill="#121212", outline="#F4B942", width=26)
d.rounded_rectangle((115, 145, 910, 300), radius=24, fill="#008C45")
d.rounded_rectangle((115, 725, 910, 875), radius=24, fill="#C62828")
try:
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 260)
    small = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 62)
except OSError:
    font = ImageFont.load_default()
    small = font
d.text((512, 512), "BBS", font=font, fill="#F5F5F0", anchor="mm", stroke_width=2, stroke_fill="#F4B942")
d.text((512, 218), "THE SITDOWN", font=small, fill="#FFFFFF", anchor="mm")
d.text((512, 797), "NORTH JERSEY", font=small, fill="#FFFFFF", anchor="mm")
out = Path("build")
out.mkdir(exist_ok=True)
img.save(out / "sitdown-icon.png")
