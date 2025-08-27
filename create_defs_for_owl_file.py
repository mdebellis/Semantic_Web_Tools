from pathlib import Path
from rdflib import Graph, RDF, RDFS, OWL, Literal, URIRef, BNode
from rdflib.namespace import SKOS

def _label(g: Graph, term) -> str:
    lab = g.value(term, RDFS.label)
    if isinstance(lab, Literal):
        return str(lab)
    return str(term).rstrip('/#').split('/')[-1].split('#')[-1]

def _iter_rdf_list(g: Graph, head):
    """Yield members of an RDF list starting at 'head'."""
    while head and head != RDF.nil:
        first = g.value(head, RDF.first)
        if first is not None:
            yield first
        head = g.value(head, RDF.rest)

def _collect_from_expr(g: Graph, expr, genus_out: set[URIRef], restr_sents: list[str], cls_label: str):
    """Collect named superclasses and restriction sentences from a class expression node."""
    # Case 1: named class -> genus
    if isinstance(expr, URIRef) and expr != OWL.Thing:
        genus_out.add(expr)
        return
    # Case 2: explicit Restriction
    if (expr, RDF.type, OWL.Restriction) in g:
        prop = g.value(expr, OWL.onProperty)
        if not isinstance(prop, URIRef):
            return
        prop_lab = _label(g, prop)
        # some / only / value
        filler = g.value(expr, OWL.someValuesFrom)
        if filler:
            restr_sents.append(f"A {cls_label} {prop_lab} some {_label(g, filler)}.")
            return
        filler = g.value(expr, OWL.allValuesFrom)
        if filler:
            restr_sents.append(f"A {cls_label} {prop_lab} only {_label(g, filler)}.")
            return
        filler = g.value(expr, OWL.hasValue)
        if filler is not None:
            ftxt = _label(g, filler) if isinstance(filler, (URIRef, BNode)) else str(filler)
            restr_sents.append(f"A {cls_label} {prop_lab} value {ftxt}.")
            return
        # cardinalities
        for pred, word in [(OWL.minCardinality, "min"),
                           (OWL.maxCardinality, "max"),
                           (OWL.cardinality, "exact")]:
            n = g.value(expr, pred)
            if isinstance(n, Literal):
                try:
                    restr_sents.append(f"A {cls_label} {prop_lab} {word} {int(n)}.")
                except Exception:
                    pass
                return
        return
    # Case 3: intersectionOf expression
    int_list = g.value(expr, OWL.intersectionOf)
    if int_list:
        for part in _iter_rdf_list(g, int_list):
            _collect_from_expr(g, part, genus_out, restr_sents, cls_label)

def add_definitions_with_axioms(turtle_path: str):
    """Load TTL, add skos:definition strings using genus (superclasses) and axioms (restrictions), save -with-defs.ttl."""
    infile = Path(turtle_path)
    outfile = infile.with_name(infile.stem + "-with-defs.ttl")

    g = Graph().parse(infile, format="turtle")

    for cls in g.subjects(RDF.type, OWL.Class):
        cls_label = _label(g, cls)
        genus: set[URIRef] = set()
        restr_sents: list[str] = []

        # Look under rdfs:subClassOf (both named classes and anonymous expressions)
        for sup in g.objects(cls, RDFS.subClassOf):
            _collect_from_expr(g, sup, genus, restr_sents, cls_label)

        # Also look under owl:equivalentClass (common place to stash genus+differentia)
        for eq in g.objects(cls, OWL.equivalentClass):
            _collect_from_expr(g, eq, genus, restr_sents, cls_label)

        # Emit genus sentences
        for sup in sorted(genus, key=lambda x: _label(g, x).lower()):
            g.add((cls, SKOS.definition, Literal(f"A {cls_label} is a kind of {_label(g, sup)}.")))

        # Emit restriction sentences
        for sent in restr_sents:
            g.add((cls, SKOS.definition, Literal(sent)))

    g.serialize(destination=outfile, format="turtle")
    print(f"Wrote: {outfile}")

# Example:
add_definitions_with_axioms("example.ttl")
