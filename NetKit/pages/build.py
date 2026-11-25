"""Build the GitHub Pages artifact into a new directory."""

import argparse
import json
from pathlib import Path
import shutil
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = ("apps", "groups", "flags")
RAW_ROOT = "https://raw.githubusercontent.com/kakbga/Icon-backup/main/NetKit/main/"


def build(output):
    output.mkdir(parents=True)
    for filename in ("index.html", "style.css", "app.js"):
        shutil.copyfile(ROOT / "pages" / filename, output / filename)

    icons = []
    for category in CATEGORIES:
        relative_directory = Path("icon") / category
        source_directory = ROOT / relative_directory
        if not source_directory.exists():
            # Git omits empty directories when the last icon is removed.
            continue
        for source in sorted(source_directory.iterdir(), key=lambda path: (path.name.casefold(), path.name)):
            if not source.is_file() or source.suffix.lower() != ".png":
                continue

            destination = output / relative_directory / source.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)

            url_path = f"icon/{category}/{quote(source.name, safe='')}"
            icons.append({
                "category": category,
                "name": source.stem,
                "filename": source.name,
                "image": url_path,
                "rawUrl": RAW_ROOT + url_path,
            })

    (output / "icons.json").write_text(
        json.dumps(icons, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    icon_set = {
        "name": "NetKit Icons",
        "description": "PNG icons for apps, regions, and proxy groups.",
        "icons": [{"name": icon["name"], "url": icon["rawUrl"]} for icon in icons],
    }
    # Keep the published URL for existing subscriptions.
    (output / "surge-icons.json").write_text(
        json.dumps(icon_set, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Built {len(icons)} icons in {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Path to a new output directory")
    build(parser.parse_args().output)
