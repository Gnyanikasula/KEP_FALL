from owlready2 import *

p = r"D:\dpv-2.2.1\dpv\dpv-owl.rdf"

onto = get_ontology(p).load()

print("Loaded")
print(len(list(onto.classes())))