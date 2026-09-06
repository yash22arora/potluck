"""Create .env if missing, and fill in any blank generated values.

Run by `make env`. Safe to run repeatedly: it never overwrites a value you have
already set, and it backfills keys added to .env.example after your .env was
created — which is exactly the situation that leaves you staring at
"SECRET_KEY is not set" on a project you set up last week.
"""

from __future__ import annotations

import pathlib
import re
import secrets

ENV = pathlib.Path(".env")
EXAMPLE = pathlib.Path(".env.example")

# Keys the project can generate for you, and how.
GENERATED = {"SECRET_KEY": lambda: secrets.token_urlsafe(32)}


def _value_of(text: str, key: str) -> str | None:
    match = re.search(rf"^{re.escape(key)}=(.*)$", text, re.MULTILINE)
    return match.group(1).strip() if match else None


def main() -> None:
    if not EXAMPLE.exists():
        raise SystemExit(".env.example is missing — are you in the repo root?")

    created = False
    if not ENV.exists():
        ENV.write_text(EXAMPLE.read_text())
        created = True

    text = ENV.read_text()
    changed = []

    # Backfill keys that exist in the example but not in .env at all.
    for line in EXAMPLE.read_text().splitlines():
        match = re.match(r"^([A-Z][A-Z0-9_]*)=", line)
        if not match:
            continue
        key = match.group(1)
        if _value_of(text, key) is None:
            text += f"\n{line}"
            changed.append(f"added {key}")

    # Fill blanks we know how to generate.
    for key, generate in GENERATED.items():
        if not _value_of(text, key):
            value = generate()
            if re.search(rf"^{re.escape(key)}=.*$", text, re.MULTILINE):
                text = re.sub(
                    rf"^{re.escape(key)}=.*$", f"{key}={value}", text, count=1, flags=re.MULTILINE
                )
            else:
                text += f"\n{key}={value}"
            changed.append(f"generated {key}")

    if not text.endswith("\n"):
        text += "\n"
    ENV.write_text(text)

    if created:
        print("created .env from .env.example")
    for note in changed:
        print(f"  {note}")
    if not created and not changed:
        print(".env is already complete")
    else:
        print("\nrestart the app so it picks up the new values:  make down && make up")


if __name__ == "__main__":
    main()
