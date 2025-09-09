# create\_defs\_for\_owl\_file.md

> Boilerplate SKOS documentation generator for OWL ontologies
> **Scope:** pass-1 autogen of `skos:definition` (human-readable) and `skos:scopeNote` (technical/audit) using RDFlib + OWL RL reasoning.
> **Primary audience:** Michael (RDFLib-curious) and Devi (new to Semantic Web).

---

## Table of contents

* [What this tool does](#what-this-tool-does)
* [Key design choices](#key-design-choices)
* [Installation](#installation)
* [CLI usage](#cli-usage)
* [How it works (pipeline)](#how-it-works-pipeline)

  * [1) Parse input](#1-parse-input)
  * [2) Reasoning](#2-reasoning)
  * [3) Read vs write graphs](#3-read-vs-write-graphs)
  * [4) Generators](#4-generators)
* [Generated text & idempotence](#generated-text--idempotence)
* [Helper functions (mini reference)](#helper-functions-mini-reference)
* [Examples](#examples)
* [Protégé compatibility](#protege-compatibility)
* [Performance notes](#performance-notes)
* [Troubleshooting](#troubleshooting)
* [Limitations & future work](#limitations--future-work)
* [Contributing](#contributing)
* [License](#license)

---

## What this tool does

Given a Turtle ontology (e.g., `People_Ontology.ttl`), this script:

* Runs an **OWL RL reasoner** (via `owlrl`) to materialize easy entailments you expect authoring tools to use (e.g., inherited domains/ranges, subclass chains, equivalent classes).
* Writes **boilerplate documentation** into the ontology as:

  * `skos:definition` for:

    * **Classes:** “A \<ClassLabel> is a kind of \<Parent> …”
    * **Datatype properties:** “The data property \<p> records a \<Domain>’s \<p> as an \<range> value …”
    * **Object properties:** Sentence bundle describing domain/range, super-/sub-properties, inverse, and characteristics (symmetric, transitive, etc.)
  * `skos:scopeNote` for **technical audit sentences** (e.g., rendered `equivalentClass` / `subClassOf` expressions).
* Annotates all generated literals with an **AUTOGEN token** (e.g., `⟦AUTOGEN:P1:2025-09-09⟧`) to support idempotence and safe overwrite behavior.

You get a new file named `<input>_with_documentation.ttl` (or a custom output path).

---

## Key design choices

1. **Reason, but don’t pollute the output.**
   We run reasoning in memory, then **read** from the reasoned graph and **write only SKOS annotations** to the original graph. This avoids serializing reasoner-introduced blank nodes like `rdf:List`, or axiomatic clutter (`rdfs:Resource`, etc.).

2. **Minimal parent listing.**
   For class definitions, we list only **minimal named parents** (no reflexive `C ⊑ C`, no `owl:Thing`, and no redundant ancestors). So “Child” lists “Person” (not the whole Person→Agent→Animal chain).

3. **Idempotence with tags.**
   We only add/replace literals that carry our `⟦AUTOGEN:P1:…⟧` or legacy tokens—no accidental duplication of author-written text.

4. **Two documentation channels.**

   * `skos:definition`: short, human-readable boilerplate (input for later pass that polishes prose).
   * `skos:scopeNote`: deterministic **technical** rendering (audit trail of axioms that informed the definition).

---

## Installation

```bash
# Recommend Python 3.10+ in a virtualenv
pip install rdflib==6.* owlrl==6.*        # versions known to work well
```

Optional (handy while iterating):

```bash
pip install rdfextras
```

---

## CLI usage

```bash
# From the repo: .../GitHub/Semantic_Web_Tools/docsgen/src
python create_defs_for_owl_file.py People_Ontology.ttl

# Options:
#   -o, --output         Custom output path (TTL)
#   --on-exist           overwrite | error | backup   (default: overwrite)
#   --no-scope-notes     Skip generating SKOS technical scope notes
```

Behavior when output exists:

* `overwrite` (default): replace the file
* `error`: abort with non-zero exit
* `backup`: rename existing to `<name>.bak-YYYYmmdd-HHMMSS`, then write new

---

## How it works (pipeline)

### 1) Parse input

```python
g_base = Graph()
g_base.parse("People_Ontology.ttl", format="turtle")
```

### 2) Reasoning

```python
g_reason = g_base  # reasoning is applied in-place to this Graph
DeductiveClosure(
    OWLRL_Semantics,
    axiomatic_triples=False,  # avoid dumping RDFS/RDF axioms into graph
    datatype_axioms=False     # keep it lean; ranges are fine without this
).expand(g_reason)
```

* **Why `False` for both flags?**
  Reduces bnode noise and keeps output Protégé-friendly. You still get the entailments you care about (e.g., inherited domain/range via super-properties, subclass chain materialization).

### 3) Read vs write graphs

* **Read** from `g_reason` (the reasoned graph).
* **Write** to `g_base` (the graph that will be serialized).
* This ensures **only** your SKOS annotations are added to the file—no extra owlrl artifacts.

### 4) Generators

1. `add_class_definitions(g_reason, g_base, today_iso)`

   * Finds **minimal named parents** and writes:
     `A Child is a kind of Person. ⟦AUTOGEN:P1:DATE⟧`
2. `add_datatype_property_definitions(g_reason, g_base, today_iso)`

   * Computes **effective** domain/range via property frontier (super-properties + equivalent properties).
3. `add_object_property_definitions(g_reason, g_base, today_iso)`

   * Describes relation sentence, super/sub properties, inverse, and characteristics (functional, symmetric, etc.).
4. `add_class_axiom_scope_notes(g_reason, g_base, today_iso, include_scope_note=…)`

   * Renders `equivalentClass` and `subClassOf` expressions into technical English, skipping reflexive/self/Thing/Nothing noise.

Finally:

```python
g_base.serialize(destination=out_path, format="turtle")
```

---

## Generated text & idempotence

All generated literals end with an **AUTOGEN token** like:

```
⟦AUTOGEN:P1:2025-09-09⟧
```

* On re-runs, if an entity already has a `skos:definition` (or `skos:scopeNote`) containing an AUTOGEN token, it will **not** be replaced unless `OVERWRITE_EXISTING_AUTOGEN = True`.
* Author-written definitions without the AUTOGEN token are **left untouched**.

---

## Helper functions (mini reference)

* `label_for(g, uri)`
  Prefer `rdfs:label` else use local name; underscores → spaces.

* `qname_or_str(g, uri)`
  Try compact QName (e.g., `xsd:integer`); fallback to local name.

* `minimal_named_parents(g, cls)`
  Returns minimal set of **named** superclasses for `cls` from the **reasoned** graph, excluding `owl:Thing`, `owl:Nothing`, and `cls` itself, and removing redundant ancestors (`P` is dropped if `P ⊑* Q` for another parent `Q`).

* `property_frontier(g, p)`
  Fixed-point over `{p} ∪ eq(p) ∪ super*(p)` to collect all super-properties and `owl:equivalentProperty` peers that may contribute domain/range.

* `effective_domains(g, p)` / `effective_ranges(g, p)`
  Aggregate `rdfs:domain`/`rdfs:range` across the property frontier (handles inheritance like `hasColleague ⊑ hasSocialRelation` → domain/range inherited from super).

* `_render_class_expr_technical(g, expr)`
  Deterministic rendering for a subset of class expressions:

  * Named classes
  * `intersectionOf` (joins as “both … and …” / “all of …, and …”)
  * Common `owl:Restriction` patterns (some/all/hasValue/cardinality; qualified data/object)

---

## Examples

**Class definition (minimal parents)**

```
A Child is a kind of Person. ⟦AUTOGEN:P1:2025-09-09⟧
```

**Datatype property**

```
The data property age records a Person's age as an xsd:integer value. ⟦AUTOGEN:P1:2025-09-09⟧
```

**Object property (+ characteristics)**

```
The property ‘has colleague’ is a relation between Person and Person. 
It is a sub-property of ‘has social relationship’. 
This means that if x has colleague y then x has social relationship y. 
It is symmetric which means that if x relates to y, then y relates to x. 
It is irreflexive which means that no individual relates to itself by this property. 
⟦AUTOGEN:P1:2025-09-09⟧
```

**Technical scope note (audit)**

```
A ‘Child’ is equivalent to both Person and has at least one ‘age’ value that is an xsd:integer < 18. 
A ‘Child’ is a kind of has at least one ‘eats’ to Living Thing. 
⟦AUTOGEN:P1:2025-09-09⟧
```

---

## Protégé compatibility

* Output only includes **your ontology + SKOS literals**—no `rdf:List`/axiomatic triples get serialized.
* Classes remain **OWL classes**; no `rdf:Class`/`rdfs:Resource` injected by us.
* Domain/range inheritance is **materialized** for documentation purposes (as text), but we do **not** rewrite your TBox.

---

## Performance notes

* OWL RL closure is linear-ish on typical authoring ontologies, but large hierarchies can slow things down.
* We keep rendering deterministic and string-only (no SPARQL), avoiding expensive graph rewrites.
* If you hit slowdowns, consider:

  * Using `--no-scope-notes` for big ontologies.
  * Running on CPython 3.11+ (faster dict/set ops help).

---

## Troubleshooting

* **`SyntaxWarning: invalid escape sequence '\G'`**
  That’s from backslashes in docstrings. We switched example paths to forward slashes (`…/GitHub/...`). If you reintroduce Windows-style backslashes in a docstring, either use raw strings (`r"..."`) or double the backslashes (`\\`).

* **Protégé shows odd bnodes or RDF types**
  Ensure you’re opening the **output** file. The script writes only SKOS literals; if you see `rdf:List` etc., you may be looking at an older run (before the read/write split) or the reasoned graph was serialized by mistake.

* **Self-subclass sentences**
  We explicitly filter `cls ⊑ cls` in both class definitions and scope notes. If you see them again, verify you pasted the latest definitions of `direct_superclasses`, `minimal_named_parents`, and `add_class_axiom_scope_notes`.

---

## Limitations & future work

* Union/Complement rendering in scope notes is partial (we fully support `intersectionOf`; `unionOf` is handled in some property text, but class-side `unionOf` is intentionally conservative).
* Datatype facet wording is intentionally terse (e.g., “< 18”); pass-2 LLM polishing is expected to improve naturalness.
* No multilingual labels yet; we always pull the default `rdfs:label` if present.

---

## Contributing

* Keep **idempotence** rules intact (always append `⟦AUTOGEN:P1:YYYY-MM-DD⟧` on generated literals).
* Any new generator should:

  1. read from the reasoned graph,
  2. write only SKOS annotations to the base graph, and
  3. avoid serializing structural changes.

Suggested structure:

```
docsgen/
  src/
    create_defs_for_owl_file.py
  docs/
    create_defs_for_owl_file.md   ← this file
```

---

## License

Add your project’s license here (e.g., Apache-2.0, MIT), or link to the repo’s LICENSE file.

---

**That’s it.** Drop this file into your repo wiki or `docs/` directory as `create_defs_for_owl_file.md`.
