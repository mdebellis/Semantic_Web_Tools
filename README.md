# Semantic_Web_Tools
SPARQL and other tools to do things like generate labels from IRIs, generate skos:documentation strings,...

The latest project we are starting is: 
### Automatic Definition Generation

Most ontology toolchains either require heavy templating (e.g. DOSDPs with YAML) or provide research prototypes that are hard to integrate into real projects (e.g. OntoVerbal, SWAT). Our approach is deliberately lightweight:

* **No extra setup** — as long as your ontology has `rdfs:label`s and follows basic conventions, the tool will generate textual definitions automatically.
* **Direct use of OWL axioms** — genus–differentia structure is extracted from subclass axioms and restrictions, in line with OBO/BFO best practices.
* **NLP-assisted readability** — integrating with mainstream NLP libraries (NLTK, spaCy) allows simple post-processing to make sentences more natural, e.g. “has\_covering some Feathers” → “is covered with feathers.”
* **Practical integration** — implemented in Python using RDFLib, so it can run as a script or be embedded in larger pipelines without learning new syntaxes or maintaining YAML files.
* **Useful for Retrieval Augmented Generation (RAG)** — These strings can also be useful when defining RAG systems. The generated strings can be included in the strings that have vectors defined. In this way the LLM has all the logical knowledge in the ontology. 

This fills a gap between heavyweight OBO workflows and one-off academic demos by providing a **modern, practical, and reproducible way to generate human-readable documentation directly from OWL ontologies**.



