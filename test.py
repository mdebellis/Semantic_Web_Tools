
from rdflib import Graph

ttl = """
@prefix : <http://ex.org/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .

:Animal a owl:Class ; rdfs:label "Animal" .
:Dog a owl:Class ; rdfs:label "Dog" ; rdfs:subClassOf :Animal .
"""

g = Graph().parse(data=ttl, format="turtle")
print("Triple count:", len(g))
for s, p, o in g:
    print(s, p, o)

