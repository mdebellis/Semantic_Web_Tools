#!/usr/bin/env python3
"""
Pass 2: Polish auto-generated class definitions in-place using ChatGPT.

- Selects only skos:definition literals that contain the P1 token "⟦AUTOGEN:P1:YYYY-MM-DD⟧"
  (also supports legacy "Auto generated comment" suffix if no token is present).
- Sends just the pre-token text to the model with strict copy-edit instructions.
- Replaces the literal with the polished text + " ⟦AUTOGEN:P2:YYYY-MM-DD⟧".
- Leaves human-authored definitions alone.

Usage:
  python polish_definitions.py path/to/ontology_with_documentation.ttl
"""

import os
import re
import sys
from pathlib import Path
from datetime import date

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import SKOS

try:
    # Official OpenAI SDK (pip install openai)
    from openai import OpenAI
except Exception as e:
    raise SystemExit("Missing dependency: pip install openai\n" + str(e))

# --------------------
# Configuration
# --------------------
MODEL_NAME = os.environ.get("OPENAI_MODEL", "gpt-5")  # change to "gpt-4o" if you don't have gpt-5
USE_LANGUAGE_TAGS = False   # True -> add @en ; False -> untagged literal
P1_TOKEN_RE = re.compile(r"\u27E6AUTOGEN:P1:(\d{4}-\d{2}-\d{2})\u27E7")  # ⟦AUTOGEN:P1:YYYY-MM-DD⟧
P2_TOKEN_RE = re.compile(r"\u27E6AUTOGEN:P2:(\d{4}-\d{2}-\d{2})\u27E7")
LEGACY_MARKER_RE = re.compile(r"Auto generated comment\s+\d{4}-\d{2}-\d{2}\s*$", re.IGNORECASE)

INSTRUCTIONS = (
    "You are a meticulous technical copyeditor for ontology documentation. "
    "Polish the following sentence(s) for grammar and readability only. "
    "Do NOT add, remove, or change any facts, entities, or their relationships. "
    "Keep the sentence order. Keep all technical terms exactly as written. "
    "Return ONLY the edited text, without quotes or extra commentary."
)

# --------------------
# Helpers
# --------------------
def split_autogen_text(raw: str):
    """
    Return (core_text, token) if this is an autogen-P1 string; otherwise (None, None).
    Supports:
      - New style: "... ⟦AUTOGEN:P1:YYYY-MM-DD⟧"
      - Legacy:    "... Auto generated comment YYYY-MM-DD"
    """
    # Already P2? Skip
    if P2_TOKEN_RE.search(raw):
        return None, None

    m = P1_TOKEN_RE.search(raw)
    if m:
        core = raw[: m.start()].rstrip()
        token = m.group(0)
        return core, token

    # Legacy support
    if LEGACY_MARKER_RE.search(raw):
        core = LEGACY_MARKER_RE.sub("", raw).rstrip()
        # fabricate a token date if none present
        today = date.today().isoformat()
        token = f"⟦AUTOGEN:P1:{today}⟧"
        return core, token

    return None, None

def polish_text(client: OpenAI, text: str) -> str:
    """
    Call OpenAI Responses API to copy-edit `text`. Returns polished text.
    """
    resp = client.responses.create(
        model=MODEL_NAME,
        instructions=INSTRUCTIONS,
        input=text,
    )
    return resp.output_text.strip()

# --------------------
# Main
# --------------------
def main(in_path: str):
    in_path = Path(in_path)
    if not in_path.exists():
        raise SystemExit(f"Input file not found: {in_path}")

    client = OpenAI()  # reads OPENAI_API_KEY from environment

    g = Graph()
    g.parse(in_path.as_posix(), format="turtle")

    updated = 0
    for cls, _, lit in list(g.triples((None, SKOS.definition, None))):
        if not isinstance(lit, Literal):
            continue

        core, token = split_autogen_text(str(lit))
        if core is None:
            continue  # not our target

        # Copy-edit the core text via LLM
        try:
            polished = polish_text(client, core)
        except Exception as e:
            print(f"[WARN] Skipping one definition due to API error: {e}")
            continue

        # Replace with polished + P2 token
        p2 = f"⟦AUTOGEN:P2:{date.today().isoformat()}⟧"
        new_text = f"{polished} {p2}"

        # Preserve language tag option
        lang = "en" if USE_LANGUAGE_TAGS else None

        # Remove old literal; add new one
        g.remove((cls, SKOS.definition, lit))
        g.add((cls, SKOS.definition, Literal(new_text, lang=lang)))
        updated += 1

    # Output file name: add "_polished" before extension
    stem = in_path.stem
    out_name = f"{stem}_polished.ttl"
    out_path = in_path.with_name(out_name)
    g.serialize(destination=out_path.as_posix(), format="turtle")

    print(f"Polished {updated} auto-generated definition(s).")
    print(f"Wrote: {out_path}")

if __name__ == "__main__":
    if len(sys.argv) != 1 and len(sys.argv) != 2:
        print("Usage: python polish_definitions.py path/to/ontology.ttl", file=sys.stderr)
        sys.exit(2)
    path = sys.argv[1] if len(sys.argv) == 2 else "ontology_with_documentation.ttl"
    main(path)
