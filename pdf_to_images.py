import sys
import fitz

pdf_path = sys.argv[1]
prefix = sys.argv[2]
doc = fitz.open(pdf_path)
for i, page in enumerate(doc):
    pix = page.get_pixmap(dpi=150)
    pix.save(f"{prefix}_{i+1}.png")
    print(f"Saved {prefix}_{i+1}.png")
