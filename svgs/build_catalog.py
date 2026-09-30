from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
EXCLUDED_NAMES = {
    "CopilotIcon.svg",
    "copilot-logo-dark.svg",
    "copilot-logo-hc.svg",
    "copilot-logo-light.svg",
}


def main() -> None:
    items = [
        {"file": path.name, "name": path.stem}
        for path in sorted(ROOT.glob("*.svg"), key=lambda item: item.name.casefold())
        if path.name not in EXCLUDED_NAMES
    ]
    payload = {
        "version": 1,
        "count": len(items),
        "items": items,
    }
    output = ROOT / "svg-catalog.json"
    output.write_text(
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(items)} drawings to {output}")


if __name__ == "__main__":
    main()
