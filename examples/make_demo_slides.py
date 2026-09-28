"""Create a small original slide PDF to try the app."""

from pathlib import Path

import pymupdf


def main():
    output = Path(__file__).with_name("demo-slides.pdf")
    document = pymupdf.open()
    slides = [
        ("B-trees", "A balanced search tree designed for efficient disk access.", "Several keys per node keep the tree shallow."),
        ("Search", "B-tree search follows one child pointer at each level.", "Balanced height gives logarithmic search time."),
        ("Insertion and split", "A full node is split during insertion.", "Promote the middle key; every leaf stays at the same depth."),
    ]
    for number, (title, line1, line2) in enumerate(slides, 1):
        page = document.new_page(width=960, height=540)
        page.draw_rect(page.rect, color=None, fill=(0.055, 0.105, 0.15))
        page.insert_text((65, 83), "LECTURELENS / DATA STRUCTURES", fontsize=12, color=(0.68, 0.88, 0.73))
        page.insert_text((65, 205), title, fontsize=50, color=(0.94, 0.97, 0.96))
        page.insert_text((65, 283), line1, fontsize=20, color=(0.76, 0.87, 0.86))
        page.insert_text((65, 327), line2, fontsize=20, color=(0.76, 0.87, 0.86))
        page.insert_text((65, 500), f"{number:02d} / 03", fontsize=12, color=(0.52, 0.67, 0.69))
    document.save(output)
    print(output)


if __name__ == "__main__":
    main()

