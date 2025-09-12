# How to Use `owl_to_shacl`

The `owl_to_shacl` function generates SHACL constraints automatically from an OWL ontology.  
It can also (optionally) remove datatype ranges from the ontology and write out a refactored copy.

---

## Basic Usage

### 1. Auto-discover datatype properties
By default, the function looks for all `owl:DatatypeProperty` terms that have a range of
`xsd:decimal`, `xsd:integer`, or `xsd:dateTime` and generates SHACL shapes to validate them.

from mymodule import owl_to_shacl

shacl_file, ref_file = owl_to_shacl("people_ontology.ttl")
print("SHACL written to:", shacl_file)
Input: people_ontology.ttl

Output: people_ontology_constraints.shacl.ttl

ref_file will be None since remove_ranges was not set.

2. Target specific properties with CURIEs

If the ontology defines prefixes, you can pass specific properties by CURIE (e.g., ex:has_birthdate).
shacl_file, ref_file = owl_to_shacl(
    "people_ontology.ttl",
    datatype_properties=["ex:has_birthdate", "ex:has_income"]
)
3. Use bare local names with a base IRI

If you prefer to list bare property names, provide an iri_base (and optionally iri_sep).
You can also set remove_ranges=True to strip the rdfs:range triples from the ontology
and write a refactored copy.
shacl_file, ref_file = owl_to_shacl(
    "sensor.owl",
    datatype_properties=["reading_timestamp", "reading_value"],
    iri_base="https://example.org/sensor#",
    remove_ranges=True
)

print("SHACL written to:", shacl_file)
print("Refactored ontology written to:", ref_file)
Input: sensor.owl

Output (SHACL): sensor_constraints.shacl.ttl

Output (refactored ontology): sensor_refactored.ttl

Parameters Summary

path (str) — Path to the ontology file.

datatype_properties (list[str], optional)
List of properties to process. Can be:

Full IRI (http://ex.org/has_birthdate)

CURIE (ex:has_birthdate) if the prefix is declared

Bare name (has_birthdate) if iri_base is provided
Default: auto-discover decimal, integer, and dateTime properties.

remove_ranges (bool, default False) — If true, remove the rdfs:range from each targeted property and save a _refactored.ttl copy.

shacl_path (str, optional) — Output path for SHACL file. Defaults to <basename>_constraints.shacl.ttl.

iri_base (str, optional) — Base IRI for resolving bare local names.

iri_sep (str, optional) — Separator for base IRIs (# or /). If not provided, inferred from ontology.

strict_ident_check (bool, default True) — If true, error if a listed property is not an owl:DatatypeProperty.
Worked Example
Example Ontology (input)

people_ontology.ttl:

@prefix ex: <http://example.org/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

ex:has_birthdate a owl:DatatypeProperty ;
    rdfs:range xsd:dateTime .

ex:has_income a owl:DatatypeProperty ;
    rdfs:range xsd:decimal .

Generated SHACL (output)

people_ontology_constraints.shacl.ttl:

@prefix ex: <http://example.org/> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

# Constraint for ex:has_birthdate
ex:has_birthdate_Shape a sh:NodeShape ;
    sh:targetSubjectsOf ex:has_birthdate ;
    sh:property [
        sh:path ex:has_birthdate ;
        sh:datatype xsd:dateTime ;
        sh:message "Value of http://example.org/has_birthdate must have datatype http://www.w3.org/2001/XMLSchema#dateTime."
    ] .

# Constraint for ex:has_income
ex:has_income_Shape a sh:NodeShape ;
    sh:targetSubjectsOf ex:has_income ;
    sh:property [
        sh:path ex:has_income ;
        sh:datatype xsd:decimal ;
        sh:message "Value of http://example.org/has_income must have datatype http://www.w3.org/2001/XMLSchema#decimal."
    ] .

How to run
shacl_file, ref_file = owl_to_shacl("people_ontology.ttl")
print("SHACL written to:", shacl_file)


Output SHACL file: people_ontology_constraints.shacl.ttl

No refactored file unless remove_ranges=True is set.

Notes

SHACL constraints generated are strict: each property must have the declared XSD datatype.

This first version does not generate tolerant sh:or branches for messy values (strings, patterns). That can be added later.

The refactored ontology is always written in Turtle (.ttl).
