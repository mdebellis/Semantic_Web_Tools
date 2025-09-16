from rdflib import Graph, Namespace, URIRef, RDF, RDFS, OWL

def relation_transformation(
    g: Graph,
    *,
    base_ns: Namespace,
    class_name: str,             # "Employee"
    relation_property_name: str, # "has_employer"
    new_class_name: str,         # "Employment"
    new_link_property_name: str | None = None,  # default -> "has_<new_class_name>".lower()
    person_superclass_local: str | None = None, # e.g., "Person"; else original class
    dry_run: bool = False,
):
    C  = base_ns[class_name]
    R  = base_ns[relation_property_name]
    N  = base_ns[new_class_name]
    L  = base_ns[new_link_property_name] if new_link_property_name else base_ns[f"has_{new_class_name.lower()}"]
    # NEW: inverse property I
    I  = base_ns[f"is_{new_class_name.lower()}_of"]

    PersonLike = base_ns[person_superclass_local] if person_superclass_local else C

    def _ensure_decl(iri: URIRef, rdf_type: URIRef):
        if (iri, RDF.type, rdf_type) not in g and not dry_run:
            g.add((iri, RDF.type, rdf_type))

    # --- SCHEMA updates ---
    _ensure_decl(N, OWL.Class)
    _ensure_decl(L, OWL.ObjectProperty)
    _ensure_decl(I, OWL.ObjectProperty)  # NEW

    # Domain/range for link L: PersonLike -> N
    if not dry_run:
        if (L, RDFS.domain, PersonLike) not in g: g.add((L, RDFS.domain, PersonLike))
        if (L, RDFS.range,  N)          not in g: g.add((L, RDFS.range,  N))
        # NEW: inverse property schema N -> PersonLike + inverseOf axioms (both directions for robustness)
        if (I, RDFS.domain, N)          not in g: g.add((I, RDFS.domain, N))
        if (I, RDFS.range,  PersonLike) not in g: g.add((I, RDFS.range,  PersonLike))
        if (L, OWL.inverseOf, I)        not in g: g.add((L, OWL.inverseOf, I))
        if (I, OWL.inverseOf, L)        not in g: g.add((I, OWL.inverseOf, L))

    # Flip domains of properties with domain C -> N (includes R if explicitly C)
    props_with_domain_C = [p for p, _, d in g.triples((None, RDFS.domain, None)) if d == C]
    if (R, RDFS.domain, C) in g and R not in props_with_domain_C:
        props_with_domain_C.append(R)
    for p in props_with_domain_C:
        if (p, RDFS.domain, C) in g and not dry_run:
            g.remove((p, RDFS.domain, C))
            g.add((p, RDFS.domain, N))

    # --- DATA migration (unchanged) ---
    from uuid import uuid4
    def _local_name(iri_like) -> str:
        s = str(iri_like)
        for sep in ['#','/',':']:
            if sep in s: s = s.rsplit(sep,1)[-1]
        return s
    def _safe_local(s: str) -> str:
        import re
        s = re.sub(r'[^A-Za-z0-9_]+','_', s)
        return s or str(uuid4()).replace('-', '_')
    def _mint_N_instance(x: URIRef, key: str) -> URIRef:
        local = f"{new_class_name}_{_local_name(x)}_{_safe_local(_local_name(key))}"
        return base_ns[local]

    move_props = set(props_with_domain_C)
    move_props.discard(L)

    instances = {s for s, _, _ in g.triples((None, RDF.type, C))}

    for x in instances:
        employers = {o for _, _, o in g.triples((x, R, None))}
        other_asserts = [(p, v) for p in move_props for _, _, v in g.triples((x, p, None)) if p != R]

        if employers:
            for o in employers:
                n_inst = _mint_N_instance(x, key=str(o))
                if not dry_run:
                    g.add((n_inst, RDF.type, N))
                    # Forward and inverse links
                    g.add((x, L, n_inst))
                    g.add((n_inst, I, x))
                    # Move R
                    if (x, R, o) in g:
                        g.remove((x, R, o))
                        g.add((n_inst, R, o))
                    # Copy other props to N-node, then erase on x
                    for p, v in other_asserts:
                        g.add((n_inst, p, v))
            if not dry_run:
                for p, v in other_asserts:
                    if (x, p, v) in g: g.remove((x, p, v))
        else:
            if other_asserts:
                n_inst = _mint_N_instance(x, key=str(uuid4()))
                if not dry_run:
                    g.add((n_inst, RDF.type, N))
                    g.add((x, L, n_inst))
                    g.add((n_inst, I, x))  # inverse link
                    for p, v in other_asserts:
                        g.add((n_inst, p, v))
                        if (x, p, v) in g: g.remove((x, p, v))

    return (C, R, N)
