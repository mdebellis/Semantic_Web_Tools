from rdflib import Graph, RDF, RDFS, OWL, Namespace, Literal
from rdflib.namespace import SKOS

# Example ontology snippet
ttl = """
@prefix : <http://ex.org/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .

:Animal a owl:Class ; rdfs:label "Animal" .
:Mammal a owl:Class ; rdfs:label "Mammal" ; rdfs:subClassOf :Animal .
:Dog a owl:Class ; rdfs:label "Dog" ; rdfs:subClassOf :Mammal .
"""

# Load into RDFLib graph
g = Graph().parse(data=ttl, format="turtle")

# Iterate over classes
for cls in g.subjects(RDF.type, OWL.Class):
    label = g.value(cls, RDFS.label)
    superclass = g.value(cls, RDFS.subClassOf)
    superclass_label = g.value(superclass, RDFS.label) if superclass else None

    if label and superclass_label:
        definition = f"Every {label} is a kind of {superclass_label}."
        g.add((cls, SKOS.definition, Literal(definition)))

# Print out the results
for cls, definition in g.subject_objects(SKOS.definition):
    print(cls, "→", definition)

# Serialize with added definitions
print("\n-----\nTTL output with definitions:\n")
print(g.serialize(format="turtle"))
