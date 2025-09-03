#!/usr/bin/env python3
"""
Pass 1: Generate boilerplate SKOS definitions for classes and datatype properties.

Classes (excluding owl:Thing, owl:Nothing):
  "A <ClassLabel> is a kind of <Super1>. A <ClassLabel> is a kind of <Super2>. ... ⟦AUTOGEN:P1:YYYY-MM-DD⟧"

Datatype properties (owl:DatatypeProperty, excluding owl:topDataProperty / owl:bottomDataProperty):
  T1 template per explicit domain (or domainless fallback), ranges joined with "or":
  "The data property <prop> records a <DomainLabel>'s <prop> as an <range1 [or range2 ...]> value. ⟦AUTOGEN:P1:DATE⟧"
  If there are multiple domains, emit one sentence per domain in the same definition literal.
  If no domain → "records the <prop> as an <range> value."
  If no range → "records a <DomainLabel>'s <prop> as a literal value."

Idempotence:
  - Adds an autogen definition only if the term does not already have one containing ⟦AUTOGEN:P1:...⟧ or ⟦AUTOGEN:P2:...⟧
  - Set OVERWRITE_EXISTING_AUTOGEN = True to replace prior autogen definitions.

Usage:
  python create_defs_for_owl_file.py path/to/ontology.ttl
"""

import sys
import re
from pathlib import Path
from datetime import date

from rdflib import Graph, Namespace, RDF, RDFS, OWL, URIRef, Literal
from rdflib.namespace import SKOS, split_uri
import argparse
from datetime import datetime

# --------------------
# Settings
# --------------------
OVERWRITE_EXISTING_AUTOGEN = False  # True -> replace existing ⟦AUTOGEN:*⟧ definitions

# Autogen markers (U+27E6/27E7 are the corner brackets ⟦ ⟧)
P1_TOKEN_RE = re.compile(r"\u27E6AUTOGEN:P1:\d{4}-\d{2}-\d{2}\u27E7")
P2_TOKEN_RE = re.compile(r"\u27E6AUTOGEN:P2:\d{4}-\d{2}-\d{2}\u27E7")
LEGACY_MARKER_RE = re.compile(r"Auto generated comment\s+\d{4}-\d{2}-\d{2}\s*$", re.IGNORECASE)

# --------------------
# Helpers
# --------------------
def label_for(g: Graph, uri: URIRef) -> str:
    """Prefer rdfs:label; otherwise use local name. Replace underscores with spaces."""
    for _, _, lab in g.triples((uri, RDFS.label, None)):
        if isinstance(lab, Literal):
            return str(lab)
    try:
        _, local = split_uri(uri)
    except Exception:
        # last path or fragment
        u = str(uri)
        local = u.split('#')[-1] if '#' in u else u.rsplit('/', 1)[-1]
    return local.replace('_', ' ')

def qname_or_str(g: Graph, uri: URIRef) -> str:
    """Return a compact QName if possible (e.g., xsd:decimal); else fallback to local name."""
    try:
        q = g.namespace_manager.normalizeUri(uri)  # may return QName or full IRI
        if ':' in q and not q.startswith('http'):
            return q
    except Exception:
        pass
    # fallback to local
    return label_for(g, uri).replace(' ', '_')

def direct_superclasses(g: Graph, cls: URIRef):
    """All explicit URI superclasses (exclude bnodes/restrictions and owl:Nothing)."""
    supers = []
    for _, _, sup in g.triples((cls, RDFS.subClassOf, None)):
        if isinstance(sup, URIRef) and sup != OWL.Nothing:
            supers.append(sup)
    # stable order
    seen = set()
    ordered = []
    for s in supers:
        if s not in seen:
            ordered.append(s)
            seen.add(s)
    return ordered

def has_autogen_def(g: Graph, subject: URIRef) -> bool:
    """True if subject already has a skos:definition with an AUTOGEN token (P1 or P2) or legacy marker."""
    for _, _, val in g.triples((subject, SKOS.definition, None)):
        if isinstance(val, Literal):
            txt = str(val)
            if P1_TOKEN_RE.search(txt) or P2_TOKEN_RE.search(txt) or LEGACY_MARKER_RE.search(txt):
                return True
    return False

def remove_autogen_defs(g: Graph, subject: URIRef):
    """Remove existing AUTOGEN skos:definition(s) for subject."""
    to_remove = []
    for _, p, val in g.triples((subject, SKOS.definition, None)):
        if isinstance(val, Literal):
            txt = str(val)
            if P1_TOKEN_RE.search(txt) or P2_TOKEN_RE.search(txt) or LEGACY_MARKER_RE.search(txt):
                to_remove.append((subject, p, val))
    for t in to_remove:
        g.remove(t)

def join_or(items):
    """Join items with ' or ' (no Oxford comma, minimalism)."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return " or ".join(items)

def sentences_unique_preserve_order(sentences):
    seen = set()
    out = []
    for s in sentences:
        if s not in seen:
            out.append(s)
            seen.add(s)
    return out

# --------------------
# Generators
# --------------------
def add_class_definitions(g: Graph, today_iso: str):
    """Generate autogen skos:definition for classes."""
    classes = set(s for s in g.subjects(RDF.type, OWL.Class) if isinstance(s, URIRef))
    classes.update(s for s, _, _ in g.triples((None, RDFS.subClassOf, None)) if isinstance(s, URIRef))
    classes.discard(OWL.Thing)
    classes.discard(OWL.Nothing)

    added = updated = 0
    for cls in sorted(classes, key=lambda u: str(u)):
        if has_autogen_def(g, cls) and not OVERWRITE_EXISTING_AUTOGEN:
            continue
        if OVERWRITE_EXISTING_AUTOGEN and has_autogen_def(g, cls):
            remove_autogen_defs(g, cls)
            updated += 1
        else:
            added += 1

        supers = direct_superclasses(g, cls) or [OWL.Thing]
        cls_label = label_for(g, cls)

        sentences = [f"A {cls_label} is a kind of {label_for(g, s)}." for s in supers]
        text = " ".join(sentences) + f" ⟦AUTOGEN:P1:{today_iso}⟧"

        g.add((cls, SKOS.definition, Literal(text)))
    return added, updated

def add_datatype_property_definitions(g: Graph, today_iso: str):
    """Generate autogen skos:definition for datatype properties (T1 template)."""
    props = set(s for s in g.subjects(RDF.type, OWL.DatatypeProperty) if isinstance(s, URIRef))

    # Exclude top/bottom data property if present
    try:
        props.discard(OWL.topDataProperty)
        props.discard(OWL.bottomDataProperty)
    except AttributeError:
        pass  # rdflib may not expose these in some versions; no harm

    added = updated = 0
    for prop in sorted(props, key=lambda u: str(u)):
        if has_autogen_def(g, prop) and not OVERWRITE_EXISTING_AUTOGEN:
            continue
        if OVERWRITE_EXISTING_AUTOGEN and has_autogen_def(g, prop):
            remove_autogen_defs(g, prop)
            updated += 1
        else:
            added += 1

        prop_label = label_for(g, prop)

        # domains: URIRefs only (skip bnodes/complex expressions)
        domains = [d for d in g.objects(prop, RDFS.domain) if isinstance(d, URIRef)]
        # ranges: URIRefs only; render as QName if possible
        ranges = [r for r in g.objects(prop, RDFS.range) if isinstance(r, URIRef)]
        if ranges:
            range_text = join_or([qname_or_str(g, r) for r in ranges])
            # simple article heuristic; LLM pass will polish if needed
            article = "an" if range_text[:1].lower() in set("aeioux") else "a"
            rng_phrase = f"as {article} {range_text} value."
        else:
            rng_phrase = "as a literal value."

        sentences = []
        if domains:
            for d in domains:
                d_label = label_for(g, d)
                sentences.append(f"The data property {prop_label} records a {d_label}'s {prop_label} {rng_phrase}")
        else:
            sentences.append(f"The data property {prop_label} records the {prop_label} {rng_phrase}")

        # ensure uniqueness & tidy join
        sentences = sentences_unique_preserve_order([s.strip() if s.endswith('.') else s.strip() for s in sentences])
        text_body = " ".join(s if s.endswith('.') else s + '.' for s in sentences)
        text = f"{text_body} ⟦AUTOGEN:P1:{today_iso}⟧"

        g.add((prop, SKOS.definition, Literal(text)))

    return added, updated

# --------------------
# Main
# --------------------
def main_cli():
    parser = argparse.ArgumentParser(
        description="Generate boilerplate SKOS definitions for classes and datatype properties."
    )
    parser.add_argument("input", help="Path to the input Turtle ontology (e.g., People_Ontology.ttl)")
    parser.add_argument(
        "-o", "--output",
        help="Output TTL path. Defaults to <input>_with_documentation.ttl"
    )
    parser.add_argument(
        "--on-exist",
        choices=["overwrite", "error", "backup"],
        default="overwrite",
        help="Behavior if the output file already exists. Default: overwrite"
    )
    args = parser.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"Input file not found: {in_path}", file=sys.stderr)
        sys.exit(1)

    g = Graph()
    g.parse(in_path.as_posix(), format="turtle")

    today = date.today().isoformat()

    cls_added, cls_updated = add_class_definitions(g, today)
    dp_added, dp_updated = add_datatype_property_definitions(g, today)

    out_path = Path(args.output) if args.output else in_path.with_name(in_path.stem + "_with_documentation.ttl")

    # Handle existing output
    if out_path.exists():
        if args.on_exist == "error":
            print(f"Refusing to overwrite existing file: {out_path}", file=sys.stderr)
            sys.exit(3)
        elif args.on_exist == "backup":
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = out_path.with_suffix(out_path.suffix + f".bak-{ts}")
            try:
                out_path.rename(backup)
                print(f"Backed up existing output to: {backup}")
            except Exception as e:
                print(f"Failed to back up existing file: {e}", file=sys.stderr)
                sys.exit(4)
        # overwrite: do nothing special

    g.serialize(destination=out_path.as_posix(), format="turtle")

    print(f"Classes:    added {cls_added}" + (f", updated {cls_updated}" if OVERWRITE_EXISTING_AUTOGEN else ""))
    print(f"Data props: added {dp_added}" + (f", updated {dp_updated}" if OVERWRITE_EXISTING_AUTOGEN else ""))
    print(f"Wrote: {out_path}")

if __name__ == "__main__":
    main_cli()