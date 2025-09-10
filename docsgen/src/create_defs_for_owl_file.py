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
  Make sure you are in the directory: .../GitHub/Semantic_Web_Tools/docsgen/src
  python create_defs_for_owl_file.py People_Ontology.ttl
"""

import sys
import re
from pathlib import Path
from datetime import date

from rdflib import Graph, RDF, RDFS, OWL, URIRef, Literal
from rdflib.namespace import SKOS, split_uri, XSD
import argparse
from datetime import datetime
from owlrl import DeductiveClosure, OWLRL_Semantics

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
    """All explicit URI superclasses (exclude bnodes/restrictions, owl:Nothing, and reflexive cls⊑cls)."""
    supers = []
    for _, _, sup in g.triples((cls, RDFS.subClassOf, None)):
        if isinstance(sup, URIRef) and sup not in (OWL.Nothing, cls):
            supers.append(sup)
    # stable order
    seen = set()
    ordered = []
    for s in supers:
        if s not in seen:
            ordered.append(s)
            seen.add(s)
    return ordered

def minimal_named_parents(g: Graph, cls: URIRef):
    """
    Return the minimal set of *named* superclasses for `cls` from the (reasoned) graph,
    excluding OWL.Thing, OWL.Nothing, and reflexive cls ⊑ cls.
    A parent P is kept only if there is no other parent Q (Q != P) such that P ⊑* Q.
    """
    # candidate parents: named superclasses only
    parents = [
        p for p in g.objects(cls, RDFS.subClassOf)
        if isinstance(p, URIRef) and p not in (OWL.Thing, OWL.Nothing, cls)
    ]
    if not parents:
        return []

    def is_subclass_of(a: URIRef, b: URIRef) -> bool:
        """True iff a ⊑* b in g (reflexive-transitive)."""
        if a == b:
            return True
        seen = set([a])
        stack = [a]
        while stack:
            cur = stack.pop()
            for sup in g.objects(cur, RDFS.subClassOf):
                if not isinstance(sup, URIRef):
                    continue
                if sup == b:
                    return True
                if sup not in seen:
                    seen.add(sup)
                    stack.append(sup)
        return False

    # keep only minimal parents
    minimal = []
    for p in parents:
        if any(q != p and is_subclass_of(p, q) for q in parents):
            continue  # p is redundant (it’s below another parent)
        minimal.append(p)
    return minimal



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


def super_properties_transitive(g: Graph, p: URIRef):
    """All super-properties of p via transitive rdfs:subPropertyOf (including direct ones)."""
    visited, stack = set(), [p]
    supers = set()
    while stack:
        cur = stack.pop()
        if cur in visited:
            continue
        visited.add(cur)
        for sup in g.objects(cur, RDFS.subPropertyOf):
            if isinstance(sup, URIRef):
                supers.add(sup)
                stack.append(sup)
    return supers


def eq_properties(g: Graph, p: URIRef):
    eq = set(g.objects(p, OWL.equivalentProperty)) | set(g.subjects(OWL.equivalentProperty, p))
    return {q for q in eq if isinstance(q, URIRef)}


def property_frontier(g: Graph, p: URIRef):
    """
    Fixed-point closure over: {p} ∪ eq(p) ∪ super*(p) ∪ eq(super*(p)) ∪ super*(eq(...)) ...
    """
    frontier = {p}
    changed = True
    while changed:
        changed = False
        new = set()
        for q in list(frontier):
            new |= super_properties_transitive(g, q)
            new |= eq_properties(g, q)
        if not new.issubset(frontier):
            frontier |= new
            changed = True
    return frontier


def effective_domains(g: Graph, p: URIRef):
    doms = set()
    for prop in property_frontier(g, p):
        doms.update(g.objects(prop, RDFS.domain))
    return list(doms)


def effective_ranges(g: Graph, p: URIRef):
    rngs = set()
    for prop in property_frontier(g, p):
        rngs.update(g.objects(prop, RDFS.range))
    return list(rngs)


# ---------- Class Axiom Rendering (technical) ----------

def _render_rdf_list(g: Graph, head: URIRef):
    members = []
    while head and head != RDF.nil:
        first = g.value(head, RDF.first)
        if first is not None:
            members.append(first)
        head = g.value(head, RDF.rest)
    return members


def _render_datatype_range(g: Graph, node) -> str:
    """
    Render a datatype or a datatype restriction into a compact technical phrase.
    Examples:
      xsd:integer                           -> "an xsd:integer"
      [owl:onDatatype xsd:integer ;
       owl:withRestrictions ( [ xsd:maxExclusive 18 ] ) ]
                                             -> "an xsd:integer < 18"
    """
    # Simple datatype URI
    if isinstance(node, URIRef):
        return f"an {qname_or_str(g, node)}"

    # Datatype restriction: onDatatype + withRestrictions
    on_dt = g.value(node, OWL.onDatatype)
    if on_dt is None:
        return "a literal"

    base = f"an {qname_or_str(g, on_dt)}"
    facets = []

    wr_head = g.value(node, OWL.withRestrictions)
    if wr_head:
        for bn in _render_rdf_list(g, wr_head):
            for pred, val in g.predicate_objects(bn):
                if not isinstance(pred, URIRef):
                    continue
                # Recognize common XSD facets
                if pred == XSD.minInclusive:
                    facets.append(f"≥ {val}")
                elif pred == XSD.maxInclusive:
                    facets.append(f"≤ {val}")
                elif pred == XSD.minExclusive:
                    facets.append(f"> {val}")
                elif pred == XSD.maxExclusive:
                    facets.append(f"< {val}")
                elif pred == XSD.pattern:
                    facets.append(f"matching pattern {val}")
                elif pred == XSD.length:
                    facets.append(f"with length = {val}")
                elif pred == XSD.minLength:
                    facets.append(f"with length ≥ {val}")
                elif pred == XSD.maxLength:
                    facets.append(f"with length ≤ {val}")

    return f"{base} {' and '.join(facets)}" if facets else base


def _is_data_range(g: Graph, node) -> bool:
    """True if node looks like a datatype or a datatype restriction."""
    if isinstance(node, URIRef) and str(node).startswith(str(XSD)):
        return True
    return g.value(node, OWL.onDatatype) is not None


def _render_class_expr_technical(g: Graph, expr: URIRef) -> str:
    """
    Deterministic, technical rendering for a subset of class expressions:
      - Named class -> its label
      - owl:unionOf([...])  -> "either A or B"
      - owl:intersectionOf([...]) -> "both A and B" / "all of ..."
      - owl:oneOf([...])    -> "either a or b" (enumeration of individuals)
      - owl:Restriction on owl:onProperty with some/all/cardinality variants
      - Fallback for unhandled blank nodes -> "an anonymous class expression"
    """

    def _either_join(parts: list[str]) -> str:
        if not parts:
            return ""
        if len(parts) == 1:
            return parts[0]
        if len(parts) == 2:
            return f"either {parts[0]} or {parts[1]}"
        mid = ", ".join(parts[:-1])
        return f"either {mid}, or {parts[-1]}"

    # unionOf
    union = g.value(expr, OWL.unionOf)
    if union:
        items = [_render_class_expr_technical(g, m) for m in _render_rdf_list(g, union)]
        items = [i for i in items if i]
        return _either_join(items)

    # intersectionOf
    inter = g.value(expr, OWL.intersectionOf)
    if inter:
        parts = [_render_class_expr_technical(g, m) for m in _render_rdf_list(g, inter)]
        parts = [p for p in parts if p]
        if len(parts) == 1:
            return parts[0]
        if len(parts) == 2:
            return f"both {parts[0]} and {parts[1]}"
        mid = ", ".join(parts[:-1])
        return f"all of {mid}, and {parts[-1]}"

    # oneOf (enumeration of individuals)
    oneof = g.value(expr, OWL.oneOf)
    if oneof:
        labels = []
        for m in _render_rdf_list(g, oneof):
            if isinstance(m, URIRef):
                labels.append(label_for(g, m))
            else:
                # Literal or bnode individual; show as string safely
                labels.append(str(m))
        labels = [l for l in labels if l]
        return _either_join(labels)

    # Restriction (unchanged from your version)
    if (expr, RDF.type, OWL.Restriction) in g:
        p = g.value(expr, OWL.onProperty)
        p_label = label_for(g, p) if isinstance(p, URIRef) else "<?>"

        # Qualified cardinalities
        qcard = g.value(expr, OWL.qualifiedCardinality)
        qmin  = g.value(expr, OWL.minQualifiedCardinality)
        qmax  = g.value(expr, OWL.maxQualifiedCardinality)
        qcls  = g.value(expr, OWL.onClass)
        qdr   = g.value(expr, OWL.onDataRange)

        # Unqualified cardinalities
        ucard = g.value(expr, OWL.cardinality)
        umin  = g.value(expr, OWL.minCardinality)
        umax  = g.value(expr, OWL.maxCardinality)

        some  = g.value(expr, OWL.someValuesFrom)
        allv  = g.value(expr, OWL.allValuesFrom)
        hasv  = g.value(expr, OWL.hasValue)
        hasself = (expr, OWL.hasSelf, Literal(True)) in g

        def cls_txt(c):
            return label_for(g, c) if isinstance(c, URIRef) else "Thing"

        if hasv is not None:
            obj_txt = label_for(g, hasv) if isinstance(hasv, URIRef) else str(hasv)
            return f"has ‘{p_label}’ value {obj_txt}"

        if hasself:
            return f"is related to itself by ‘{p_label}’"

        if qcard is not None and qcls is not None:
            n = int(str(qcard));  return f"has exactly {n} ‘{p_label}’ to {cls_txt(qcls)}"
        if qmin  is not None and qcls is not None:
            n = int(str(qmin));   return f"has at least {n} ‘{p_label}’ to {cls_txt(qcls)}"
        if qmax  is not None and qcls is not None:
            n = int(str(qmax));   return f"has at most {n} ‘{p_label}’ to {cls_txt(qcls)}"

        if qcard is not None and qdr is not None:
            n = int(str(qcard));  return f"has exactly {n} ‘{p_label}’ values that are {_render_datatype_range(g, qdr)}"
        if qmin  is not None and qdr is not None:
            n = int(str(qmin));   return f"has at least {n} ‘{p_label}’ values that are {_render_datatype_range(g, qdr)}"
        if qmax  is not None and qdr is not None:
            n = int(str(qmax));   return f"has at most {n} ‘{p_label}’ values that are {_render_datatype_range(g, qdr)}"

        if ucard is not None:
            n = int(str(ucard));  return f"has exactly {n} ‘{p_label}’"
        if umin  is not None:
            n = int(str(umin));   return f"has at least {n} ‘{p_label}’"
        if umax  is not None:
            n = int(str(umax));   return f"has at most {n} ‘{p_label}’"

        if some is not None:
            if _is_data_range(g, some) or (isinstance(p, URIRef) and (p, RDF.type, OWL.DatatypeProperty) in g):
                return f"has at least one ‘{p_label}’ value that is {_render_datatype_range(g, some)}"
            return f"has at least one ‘{p_label}’ to {cls_txt(some)}"

        if allv is not None:
            if _is_data_range(g, allv) or (isinstance(p, URIRef) and (p, RDF.type, OWL.DatatypeProperty) in g):
                return f"only has ‘{p_label}’ values that are {_render_datatype_range(g, allv)}"
            return f"only has ‘{p_label}’ to {cls_txt(allv)}"

        return f"has a restriction on ‘{p_label}’"

    # Named class or fallback
    if isinstance(expr, URIRef):
        return label_for(g, expr)
    return "an anonymous class expression"



def _render_equiv_or_sub_sentence(g: Graph, cls: URIRef, expr: URIRef, relation: str) -> str:
    """
    relation in {'equivalent to', 'a kind of'}.
    Produce: "A ‘Label’ is equivalent to both A and has exactly 0 ‘p’ to Person."
    """
    cls_label = label_for(g, cls)
    rhs = _render_class_expr_technical(g, expr)
    # Prepend article "A" only when starting the class sentence
    return f"A ‘{cls_label}’ is {relation} {rhs}."


# --------------------
# Generators (READ from g_read; WRITE to g_write)
# --------------------

def add_class_definitions(g_read: Graph, g_write: Graph, today_iso: str):
    """Generate autogen skos:definition for classes, using minimal named parents from the reasoned graph."""
    classes = set(s for s in g_read.subjects(RDF.type, OWL.Class) if isinstance(s, URIRef))
    classes.update(s for s, _, _ in g_read.triples((None, RDFS.subClassOf, None)) if isinstance(s, URIRef))
    classes.discard(OWL.Thing)
    classes.discard(OWL.Nothing)

    added = updated = 0
    for cls in sorted(classes, key=lambda u: str(u)):
        # Check/update against the graph we will serialize
        if has_autogen_def(g_write, cls) and not OVERWRITE_EXISTING_AUTOGEN:
            continue
        if OVERWRITE_EXISTING_AUTOGEN and has_autogen_def(g_write, cls):
            remove_autogen_defs(g_write, cls)
            updated += 1
        else:
            added += 1

        cls_label = label_for(g_read, cls)
        parents = minimal_named_parents(g_read, cls)

        sentences = [f"A {cls_label} is a kind of {label_for(g_read, p)}." for p in parents]
        # If no named parents other than Thing were found, emit no parent sentences.
        text = (" ".join(sentences) + (" " if sentences else "")) + f"⟦AUTOGEN:P1:{today_iso}⟧"

        g_write.add((cls, SKOS.definition, Literal(text)))
    return added, updated



def add_datatype_property_definitions(g_read: Graph, g_write: Graph, today_iso: str):
    """Generate autogen skos:definition for datatype properties (T1 template)."""
    props = set(s for s in g_read.subjects(RDF.type, OWL.DatatypeProperty) if isinstance(s, URIRef))

    # Exclude top/bottom data property if present
    try:
        props.discard(OWL.topDataProperty)
        props.discard(OWL.bottomDataProperty)
    except AttributeError:
        pass  # rdflib may not expose these in some versions; no harm

    added = updated = 0
    for prop in sorted(props, key=lambda u: str(u)):
        if has_autogen_def(g_write, prop) and not OVERWRITE_EXISTING_AUTOGEN:
            continue
        if OVERWRITE_EXISTING_AUTOGEN and has_autogen_def(g_write, prop):
            remove_autogen_defs(g_write, prop)
            updated += 1
        else:
            added += 1

        prop_label = label_for(g_read, prop)

        # Domains/ranges from effective (super* + equivalent) on the REASONED graph
        domains = [d for d in effective_domains(g_read, prop) if isinstance(d, URIRef)]
        ranges = [r for r in effective_ranges(g_read, prop) if isinstance(r, URIRef)]

        if ranges:
            range_text = join_or([qname_or_str(g_read, r) for r in ranges])
            article = "an" if range_text[:1].lower() in set("aeioux") else "a"
            rng_phrase = f"as {article} {range_text} value."
        else:
            rng_phrase = "as a literal value."

        sentences = []
        if domains:
            for d in domains:
                d_label = label_for(g_read, d)
                sentences.append(f"The data property {prop_label} records a {d_label}'s {prop_label} {rng_phrase}")
        else:
            sentences.append(f"The data property {prop_label} records the {prop_label} {rng_phrase}")

        sentences = sentences_unique_preserve_order([s.strip() if s.endswith('.') else s.strip() for s in sentences])
        text_body = " ".join(s if s.endswith('.') else s + '.' for s in sentences)
        text = f"{text_body} ⟦AUTOGEN:P1:{today_iso}⟧"

        g_write.add((prop, SKOS.definition, Literal(text)))
    return added, updated


def add_class_axiom_scope_notes(g_read: Graph, g_write: Graph, today_iso: str, include_scope_note: bool = True):
    """
    Generate AUTOGEN technical sentences for class axioms into skos:scopeNote.
    Reads axioms from g_read; writes notes to g_write.
    """
    if not include_scope_note:
        return 0, 0

    def _has_autogen_scope(gw: Graph, s: URIRef) -> bool:
        for _, _, val in gw.triples((s, SKOS.scopeNote, None)):
            if isinstance(val, Literal):
                txt = str(val)
                if P1_TOKEN_RE.search(txt) or P2_TOKEN_RE.search(txt) or LEGACY_MARKER_RE.search(txt):
                    return True
        return False

    def _remove_autogen_scope(gw: Graph, s: URIRef):
        to_remove = []
        for _, p, val in gw.triples((s, SKOS.scopeNote, None)):
            if isinstance(val, Literal):
                txt = str(val)
                if P1_TOKEN_RE.search(txt) or P2_TOKEN_RE.search(txt) or LEGACY_MARKER_RE.search(txt):
                    to_remove.append((s, p, val))
        for t in to_remove:
            gw.remove(t)

    classes = set(s for s in g_read.subjects(RDF.type, OWL.Class) if isinstance(s, URIRef))
    classes.discard(OWL.Thing); classes.discard(OWL.Nothing)

    added = updated = 0
    for cls in sorted(classes, key=lambda u: str(u)):
        exprs = []

        # owl:equivalentClass (skip reflexive cls ≡ cls)
        for _, _, e in g_read.triples((cls, OWL.equivalentClass, None)):
            if e == cls:
                continue
            exprs.append(("equivalent to", e))

        # rdfs:subClassOf (skip Nothing, Thing, and reflexive cls ⊑ cls)
        for _, _, e in g_read.triples((cls, RDFS.subClassOf, None)):
            if e in (OWL.Nothing, OWL.Thing, cls):
                continue
            exprs.append(("a kind of", e))

        if not exprs:
            continue

        if _has_autogen_scope(g_write, cls) and not OVERWRITE_EXISTING_AUTOGEN:
            continue
        if OVERWRITE_EXISTING_AUTOGEN and _has_autogen_scope(g_write, cls):
            _remove_autogen_scope(g_write, cls); updated += 1
        else:
            added += 1

        sentences = [_render_equiv_or_sub_sentence(g_read, cls, e, rel) for (rel, e) in exprs]
        sentences = sentences_unique_preserve_order([s.strip() for s in sentences if s and s.strip()])
        body = " ".join(s if s.endswith('.') else s + '.' for s in sentences)
        text = f"{body} ⟦AUTOGEN:P1:{today_iso}⟧"

        g_write.add((cls, SKOS.scopeNote, Literal(text)))

    return added, updated



def add_object_property_definitions(g_read: Graph, g_write: Graph, today_iso: str):
    """Generate autogen skos:definition for object properties (reads from g_read, writes to g_write)."""
    # Local helpers (kept inside to avoid polluting module namespace)
    def _label_for(u: URIRef) -> str:
        return label_for(g_read, u)

    def _render_list_members(head: URIRef):
        members = []
        while head and head != RDF.nil:
            first = g_read.value(head, RDF.first)
            if first is not None:
                members.append(first)
            head = g_read.value(head, RDF.rest)
        return members

    def _render_class_expr(cls: URIRef) -> str:
        # unionOf → "either A or B"
        union_list = g_read.value(cls, OWL.unionOf)
        if union_list:
            labels = [_label_for(m) for m in _render_list_members(union_list)]
            if len(labels) == 1:
                return labels[0]
            if len(labels) == 2:
                return f"either {labels[0]} or {labels[1]}"
            mid = ", ".join(labels[:-1])
            return f"either {mid}, or {labels[-1]}"

        # intersectionOf → "both A and B" / "all of ..."
        inter_list = g_read.value(cls, OWL.intersectionOf)
        if inter_list:
            labels = [_label_for(m) for m in _render_list_members(inter_list)]
            if len(labels) == 1:
                return labels[0]
            if len(labels) == 2:
                return f"both {labels[0]} and {labels[1]}"
            mid = ", ".join(labels[:-1])
            return f"all of {mid}, and {labels[-1]}"

        return _label_for(cls)

    def _first_sentence_relation(p: URIRef) -> str:
        domains = effective_domains(g_read, p)
        ranges = effective_ranges(g_read, p)

        def _join_as_intersection(labels):
            if not labels:
                return "Thing"
            if len(labels) == 1:
                return labels[0]
            if len(labels) == 2:
                return f"both {labels[0]} and {labels[1]}"
            mid = ", ".join(labels[:-1])
            return f"all of {mid}, and {labels[-1]}"

        def _phrase(vals):
            if not vals:
                return "Thing"
            if len(vals) == 1:
                return _render_class_expr(vals[0])  # works for URIRef or BNode
            # Multiple domain/range triples ⇒ intersection per RDFS
            rendered = [_render_class_expr(v) for v in vals]
            return _join_as_intersection(rendered)

        d_txt = _phrase(domains)
        r_txt = _phrase(ranges)
        return f"a relation between {d_txt} and {r_txt}"

    def _property_characteristics(p: URIRef):
        sents = []
        if (p, RDF.type, OWL.FunctionalProperty) in g_read:
            sents.append("It is functional which means that each subject can relate to at most one object by this property.")
        if (p, RDF.type, OWL.InverseFunctionalProperty) in g_read:
            sents.append("It is inverse functional which means that each object can be related to by at most one subject via this property.")
        if (p, RDF.type, OWL.TransitiveProperty) in g_read:
            sents.append("It is transitive which means that if x relates to y and y relates to z, then x relates to z.")
        if (p, RDF.type, OWL.SymmetricProperty) in g_read:
            sents.append("It is symmetric which means that if x relates to y, then y relates to x.")
        if (p, RDF.type, OWL.AsymmetricProperty) in g_read:
            sents.append("It is asymmetric which means that if x relates to y, then y cannot relate to x by this property.")
        if (p, RDF.type, OWL.ReflexiveProperty) in g_read:
            sents.append("It is reflexive which means that every individual relates to itself by this property.")
        if (p, RDF.type, OWL.IrreflexiveProperty) in g_read:
            sents.append("It is irreflexive which means that no individual relates to itself by this property.")
        return sents

    def _quote_first_use(name: str, seen: set) -> str:
        if name not in seen:
            seen.add(name)
            return f"‘{name}’"
        return name

    # Gather object properties from the REASONED graph
    props = set(s for s in g_read.subjects(RDF.type, OWL.ObjectProperty) if isinstance(s, URIRef))
    # Exclude top/bottom object property if present
    try:
        props.discard(OWL.topObjectProperty)
        props.discard(OWL.bottomObjectProperty)
    except AttributeError:
        pass

    added = updated = 0

    for p in sorted(props, key=lambda u: str(u)):
        # AUTOGEN overwrite behavior mirrors your other generators (check against WRITE graph)
        if has_autogen_def(g_write, p) and not OVERWRITE_EXISTING_AUTOGEN:
            continue
        if OVERWRITE_EXISTING_AUTOGEN and has_autogen_def(g_write, p):
            remove_autogen_defs(g_write, p)
            updated += 1
        else:
            added += 1

        seen_labels = set()
        p_label = _label_for(p)
        p_label_q = _quote_first_use(p_label, seen_labels)

        parts = []
        # First sentence
        parts.append(f"The property {p_label_q} is {_first_sentence_relation(p)}.")

        # Super-properties (skip reflexive p ⊑ p)
        supers = [s for s in g_read.objects(p, RDFS.subPropertyOf) if isinstance(s, URIRef) and s != p]
        if supers:
            super_labels_q = [_quote_first_use(_label_for(s), seen_labels) for s in supers]
            if len(super_labels_q) == 1:
                parts.append(f"It is a sub-property of {super_labels_q[0]}.")
            else:
                joined = ", ".join(super_labels_q[:-1]) + f", and {super_labels_q[-1]}"
                parts.append(f"It is a sub-property of {joined}.")
            for s in supers:
                s_lbl = _label_for(s)
                parts.append(f"This means that if x {p_label} y then x {s_lbl} y.")

        # Sub-properties
        subs = [s for s in g_read.subjects(RDFS.subPropertyOf, p) if isinstance(s, URIRef)]
        if subs:
            sub_labels_q = [_quote_first_use(_label_for(s), seen_labels) for s in subs]
            if len(sub_labels_q) == 1:
                parts.append(f"It is the super-property for {sub_labels_q[0]}.")
            else:
                joined = ", ".join(sub_labels_q[:-1]) + f", and {sub_labels_q[-1]}"
                parts.append(f"It is the super-property for {joined}.")
            for s in subs:
                s_lbl = _label_for(s)
                parts.append(f"This means that if a subject x {s_lbl} y then x {p_label} y.")

        # Inverse (both directions)
        inverses = set(g_read.objects(p, OWL.inverseOf)) | set(g_read.subjects(OWL.inverseOf, p))
        if inverses:
            inv = next(iter(inverses))
            inv_lbl = _label_for(inv)
            inv_lbl_q = _quote_first_use(inv_lbl, seen_labels)
            parts.append(f"It has inverse {inv_lbl_q}, which means that if x {p_label} y then y {inv_lbl} x.")

        # Characteristics in Protégé order
        parts.extend(_property_characteristics(p))

        # Compose, uniquify, punctuate, and add AUTOGEN token
        parts = sentences_unique_preserve_order([s.strip() for s in parts if s and s.strip()])
        body = " ".join(s if s.endswith('.') else s + '.' for s in parts)
        text = f"{body} ⟦AUTOGEN:P1:{today_iso}⟧"

        g_write.add((p, SKOS.definition, Literal(text)))

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
    parser.add_argument(
        "--no-scope-notes",
        action="store_true",
        help="Do not generate skos:scopeNote technical sentences for class axioms."
    )

    args = parser.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"Input file not found: {in_path}", file=sys.stderr)
        sys.exit(1)

    # Load base (to be serialized)
    g_base = Graph()
    g_base.parse(in_path.as_posix(), format="turtle")

    # Reason on a separate copy (read-only view)
    g_reason = Graph()
    g_reason += g_base
    # Keep axiomatic/datatype entailments out to avoid clutter
    DeductiveClosure(
        OWLRL_Semantics,
        axiomatic_triples=False,
        datatype_axioms=False
    ).expand(g_reason)

    today = date.today().isoformat()

    cls_added, cls_updated = add_class_definitions(g_reason, g_base, today)
    dp_added, dp_updated = add_datatype_property_definitions(g_reason, g_base, today)
    op_added, op_updated = add_object_property_definitions(g_reason, g_base, today)

    cls_axiom_added, cls_axiom_updated = add_class_axiom_scope_notes(
        g_reason, g_base, today, include_scope_note=(not args.no_scope_notes)
    )

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

    g_base.serialize(destination=out_path.as_posix(), format="turtle")

    print(f"Classes:    added {cls_added}" + (f", updated {cls_updated}" if OVERWRITE_EXISTING_AUTOGEN else ""))
    print(f"Data props: added {dp_added}" + (f", updated {dp_updated}" if OVERWRITE_EXISTING_AUTOGEN else ""))
    print(f"Object props: added {op_added}" + (f", updated {op_updated}" if OVERWRITE_EXISTING_AUTOGEN else ""))
    print(f"Class axioms (scopeNote): added {cls_axiom_added}" + (
        f", updated {cls_axiom_updated}" if OVERWRITE_EXISTING_AUTOGEN else ""))

    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main_cli()
