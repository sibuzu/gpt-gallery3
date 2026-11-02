#!/usr/bin/env python3
"""Build only Gallery 3, retaining category order and Markdown descriptions."""
from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter
from pathlib import Path

from PIL import Image


SITE_DIR = Path(__file__).resolve().parent
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def title_for(path: Path) -> str:
    return path.stem.removeprefix("ChatGPT Image ").strip()


def image_dimensions(path: Path) -> dict[str, int]:
    # Read only the header; reserve layout space before downloading the image.
    with Image.open(path) as image:
        width, height = image.size
    return {"width": width, "height": height}


def single_line_description_for(path: Path) -> str | None:
    description_path = path.with_suffix(".md")
    if not description_path.exists():
        return None

    lines = [
        " ".join(line.split())
        for line in description_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if lines and lines[0].startswith("[") and lines[0].endswith("]"):
        return lines[0]

    if len(lines) != 1:
        return None

    text = lines[0]
    sentence_endings = sum(text.count(mark) for mark in ".!?。！？")
    if sentence_endings > 1:
        return None

    text = text.lstrip("\ufeff\u200b\u200c\u200d")
    cleaned = re.sub(r"^(?:(?:she\s+)?is\s+wearing|wearing)\s+", "", text, count=1, flags=re.IGNORECASE)
    if cleaned != text:
        text = cleaned
        text = text.removesuffix(".")
    if len(text.split()) > 15:
        return None
    return text or None


def category_sort_key(path: Path) -> tuple[int, str]:
    design_values = {
        "現代": 1,
        "雲紗": 2,
        "雅裁": 3,
        "線舞": 4,
        "元素": 5,
        "民族": 6,
    }
    if path.name in design_values:
        return (design_values[path.name], path.name)

    prefix = "設計"
    values = {
        "一": 1,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }
    if not path.name.startswith(prefix):
        return (10_000, path.name)

    suffix = path.name.removeprefix(prefix)
    if suffix in values:
        return (values[suffix], path.name)
    if suffix.startswith("十") and len(suffix) == 2 and suffix[1] in values:
        return (10 + values[suffix[1]], path.name)
    if len(suffix) in {2, 3} and suffix[0] in values and suffix[1] == "十":
        return (values[suffix[0]] * 10 + values.get(suffix[2:], 0), path.name)
    return (10_000, path.name)


def scan_images() -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    design_dir = SITE_DIR / "images"

    if not design_dir.is_dir():
        raise RuntimeError(f"Missing images directory: {design_dir}")

    for category_dir in sorted([path for path in design_dir.iterdir() if path.is_dir()], key=category_sort_key):
        files = sorted(
            [path for path in category_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS],
            key=lambda path: path.name,
        )

        for path in files:
            relative_path = path.relative_to(SITE_DIR).as_posix()
            item = {
                "category": category_dir.name,
                "src": relative_path,
                "hasDescription": path.with_suffix(".md").exists(),
                "title": title_for(path),
                **image_dimensions(path),
            }
            description_path = path.with_suffix(".md")
            if description_path.exists():
                content = description_path.read_bytes()
                blob = f"blob {len(content)}\0".encode("ascii") + content
                item["descriptionSha"] = hashlib.sha1(blob).hexdigest()
            description = single_line_description_for(path)
            if description:
                item["description"] = description
            items.append(item)

    return items


def write_if_changed(path: Path, content: str) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def main() -> None:
    items = scan_images()
    data_path = SITE_DIR / "scripts" / "design-data.js"
    marker = "// Runtime gallery3 loader\n"
    _, separator, loader = data_path.read_text(encoding="utf-8").partition(marker)
    if not separator:
        raise RuntimeError(f"Missing runtime loader in {data_path}")
    data = "window.__GALLERY_IMAGES__ = " + json.dumps(items, ensure_ascii=False, indent=2)
    data += ";\n\n" + marker + loader
    counts = dict(Counter(item["category"] for item in items))
    report = {"total_categorized": len(items), "category_counts": counts,
              "with_descriptions": sum(item["hasDescription"] for item in items)}
    index_path = SITE_DIR / "index.html"
    html = index_path.read_text(encoding="utf-8")
    version = str(int(time.time()))
    for asset in ("styles/design.css", "scripts/design-data.js", "scripts/design.js"):
        pattern = rf'((?:src|href)=")({re.escape(asset)})(?:\?[^"\']*)?(")'
        html = re.sub(pattern, lambda match: f'{match[1]}{match[2]}?v={version}{match[3]}', html)
    for path, content in {
        data_path: data,
        SITE_DIR / "catalog_report.json": json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        index_path: html,
    }.items():
        action = "Updated" if write_if_changed(path, content) else "Checked"
        print(f"{action} {path.relative_to(SITE_DIR)}.")
    print(f"Gallery 3: {len(items)} images; " + ", ".join(
        f"{category}: {count}" for category, count in counts.items()
    ))


if __name__ == "__main__":
    main()
