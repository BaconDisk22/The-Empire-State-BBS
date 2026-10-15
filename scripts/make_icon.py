"""Create an original Empire State-colored icon for the Intel Mac app."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

SIZE = 1024
img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((38, 38, 986, 986), radius=200, fill="#172C46", outline="#E9BB43", width=26)
d.rounded_rectangle((115, 145, 910, 300), radius=24, fill="#36513D")
d.rounded_rectangle((115, 725, 910, 875), radius=24, fill="#C5A46D")
try:
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 260)
    small = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 62)
except OSError:
    font = ImageFont.load_default()
    small = font
d.text((512, 512), "BBS", font=font, fill="#F2E8D5", anchor="mm", stroke_width=2, stroke_fill="#E9BB43")
d.text((512, 218), "EMPIRE STATE", font=small, fill="#FFFFFF", anchor="mm")
d.text((512, 797), "NEW YORK", font=small, fill="#FFFFFF", anchor="mm")
out = Path("build")
out.mkdir(exist_ok=True)
img.save(out / "empire-icon.png")
