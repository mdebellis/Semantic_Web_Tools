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
Our plan is to use a two phased approach: 1) Create basic documentation by just doing simple pattern matching. Don't worry about things like proper pluralization, subject-verb agreement. Just get the axioms documented.
2) Use an LLM to make the definitions in phase 1 readable and follow standards. E.g., the first standard we are going to use is the BFO/OBO Aristotilean model: A <class> is a kind of <super-class> that <some logical restriction>. E.g., a Child is a Person who is less than 18 years old. So far we've implemented both phases but phase 1 is further along than phase 2. For phase 1 we are using RDFLib because I made a bet with a friend that I was capable of using technologies other than Protege and AllegroGraph. Just kidding, because we want this tool to be usable for everyone and installing a graph database, even the free version of AllegroGraph (which is awesome and everyone should go get it anyway) is overkill for this. We want something with a light footprint that can just be loaded as any other Python library so RDFLib seems to fit the bill. The documentation for the phase 1 code is here: https://github.com/mdebellis/Semantic_Web_Tools/blob/main/docsgen/docs/create_defs_for_owl_file.md




