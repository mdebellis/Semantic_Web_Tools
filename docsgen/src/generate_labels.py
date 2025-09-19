"""
generate_labels.py
------------------

Utility for automatically generating rdfs:label values in an ontology.

How to use
==========

from rdflib import Graph
from generate_labels import generate_labels

# Load your ontology into an RDFLib graph
g = Graph()
g.parse("people.ttl", format="turtle")

# 1. Historical behavior (no language tag, plain literals)
report = generate_labels(g, "http://michaeldebellis.com/people/", lang=None)
print(report)

# 2. Recommended for book examples (English language tag)
report = generate_labels(g, "http://michaeldebellis.com/people/", lang="en")
print(report)

# Save the updated graph
g.serialize("people_with_labels.ttl", format="turtle")

Notes
-----
- Only entities in the given ontology namespace are considered.
- Classes and individuals keep capitalization from the IRI.
- Properties are lowercased in labels.
- Entities already having a label (for that language) are skipped (idempotent).
- Built-in OWL terms like owl:Thing, owl:Nothing, owl:topObjectProperty,
  and owl:topDataProperty are always skipped.
- The function returns a simple report dict with counts and a few examples.
"""

# pip install rdflib>=6
from rdflib import Graph, Namespace, URIRef, RDF, RDFS, OWL, Literal

def generate_labels(g: Graph, ontology_iri: str, lang: str | None = None):
    """
    Add rdfs:label for entities in a given ontology namespace that lack one.

    Behavior mirrors your SNAP-SPARQL:
      - Classes: label = localname with '_' -> ' ' (no case change), skip owl:Thing, owl:Nothing
      - Individuals: label = localname with '_' -> ' ' (no case change)
      - Object/Data properties: label = lowercased localname with '_' -> ' ', skip owl:topObjectProperty/DataProperty
      - Only operate on IRIs that start with ontology_iri (namespace filter)
      - Idempotent:
           * lang is None  -> only add if there is no existing plain (untagged) label
           * lang = "xx"   -> only add if there is no existing label with that language
      - Does NOT alter existing labels, does not remove anything.

    Args:
        g: rdflib.Graph to mutate in place
        ontology_iri: the namespace IRI prefix (e.g., "http://michaeldebellis.com/people/")
        lang: language tag to add (e.g., "en"), or None for plain literals

    Returns:
        dict with counts and a few examples
    """
    ns_prefix = ontology_iri
    if not ns_prefix.endswith(("/", "#")):
        # allow exact-prefix matches even if user doesn't include a trailing separator
        ns_prefix = ontology_iri

    # Built-ins to avoid
    OWL_THING = OWL.Thing
    OWL_NOTHING = OWL.Nothing
    OWL_TOP_OBJ = OWL.topObjectProperty
    OWL_TOP_DATA = OWL.topDataProperty

    # Helpers
    def in_ns(u: URIRef) -> bool:
        s = str(u)
        return s.startswith(ns_prefix)

    def local_from_ns(u: URIRef) -> str:
        s = str(u)
        if not s.startswith(ns_prefix):
            return ""
        return s[len(ns_prefix):]

    def make_label_from_local(local: str, for_property: bool) -> str:
        # SNAP pattern: replace underscores with spaces; properties lowercased, others unchanged
        label = local.replace("_", " ").strip()
        if for_property:
            label = label.lower()
        return label

    def needs_label(u: URIRef) -> bool:
        # global check (any label at all)? Not used directly; we do per-lang logic below.
        return (u, RDFS.label, None) not in g

    def already_has_label_for_lang(u: URIRef, lang_tag: str | None) -> bool:
        for _, _, lit in g.triples((u, RDFS.label, None)):
            if isinstance(lit, Literal):
                if lang_tag is None and (lit.language is None):
                    return True
                if lang_tag is not None and lit.language == lang_tag:
                    return True
        return False

    def add_label(u: URIRef, text: str):
        if not text:
            return False
        lit = Literal(text, lang=lang) if lang is not None else Literal(text)
        g.add((u, RDFS.label, lit))
        return True

    # Collect candidates by type
    classes = set(s for s, _, t in g.triples((None, RDF.type, OWL.Class)) if in_ns(s))
    obj_props = set(s for s, _, t in g.triples((None, RDF.type, OWL.ObjectProperty)) if in_ns(s))
    data_props = set(s for s, _, t in g.triples((None, RDF.type, OWL.DatatypeProperty)) if in_ns(s))

    # Individuals: anything in the namespace that has an rdf:type, but is not a Class or Property
    # (More general than SNAP's explicit `a owl:Thing`, and closer to common data.)
    property_types = {OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty, OWL.TransitiveProperty,
                      OWL.SymmetricProperty, OWL.FunctionalProperty, OWL.InverseFunctionalProperty}
    individuals = set()
    for s, _, t in g.triples((None, RDF.type, None)):
        if not isinstance(s, URIRef) or not in_ns(s):
            continue
        if t == OWL.Class or t in property_types:
            continue
        individuals.add(s)

    report = {
        "created": 0,
        "skipped_existing": 0,
        "namespace_filtered": 0,
        "examples_created": [],
    }

    # Classes (skip OWL:Thing/Nothing explicitly)
    for c in classes:
        if c in (OWL_THING, OWL_NOTHING):
            continue
        local = local_from_ns(c)
        if not local:
            report["namespace_filtered"] += 1
            continue
        if already_has_label_for_lang(c, lang):
            report["skipped_existing"] += 1
            continue
        lbl = make_label_from_local(local, for_property=False)
        if add_label(c, lbl):
            report["created"] += 1
            if len(report["examples_created"]) < 5:
                report["examples_created"].append((str(c), lbl))

    # Object properties (skip topObjectProperty)
    for p in obj_props:
        if p == OWL_TOP_OBJ:
            continue
        local = local_from_ns(p)
        if not local:
            report["namespace_filtered"] += 1
            continue
        if already_has_label_for_lang(p, lang):
            report["skipped_existing"] += 1
            continue
        lbl = make_label_from_local(local, for_property=True)
        if add_label(p, lbl):
            report["created"] += 1
            if len(report["examples_created"]) < 5:
                report["examples_created"].append((str(p), lbl))

    # Data properties (skip topDataProperty)
    for p in data_props:
        if p == OWL_TOP_DATA:
            continue
        local = local_from_ns(p)
        if not local:
            report["namespace_filtered"] += 1
            continue
        if already_has_label_for_lang(p, lang):
            report["skipped_existing"] += 1
            continue
        lbl = make_label_from_local(local, for_property=True)
        if add_label(p, lbl):
            report["created"] += 1
            if len(report["examples_created"]) < 5:
                report["examples_created"].append((str(p), lbl))

    # Individuals
    for i in individuals:
        # No extra built-in filters needed here; we already filtered out classes & properties
        local = local_from_ns(i)
        if not local:
            report["namespace_filtered"] += 1
            continue
        if already_has_label_for_lang(i, lang):
            report["skipped_existing"] += 1
            continue
        lbl = make_label_from_local(local, for_property=False)
        if add_label(i, lbl):
            report["created"] += 1
            if len(report["examples_created"]) < 5:
                report["examples_created"].append((str(i), lbl))

    return report

if __name__ == "__main__":
    import sys, os
    from rdflib import Graph

    if len(sys.argv) < 3:
        print("Usage: python generate_labels.py <ontology_file> <ontology_iri> [lang]")
        sys.exit(1)

    infile = sys.argv[1]
    ontology_iri = sys.argv[2]
    lang = sys.argv[3] if len(sys.argv) > 3 else "en"

    g = Graph()
    g.parse(infile, format="turtle")

    report = generate_labels(g, ontology_iri, lang=lang)
    print("Report:", report)

    root, ext = os.path.splitext(infile)
    outfile = f"{root}_with_labels{ext or '.ttl'}"
    g.serialize(outfile, format="turtle")
    print(f"Saved updated graph to {outfile}")
