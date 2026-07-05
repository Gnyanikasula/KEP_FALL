from eval_p4 import _extract_articles

import re

# paste the function here, then:
print(_extract_articles("DUAA 2025, ArtS80-22B"))   # should give {'s80-22b'}
print(_extract_articles("DUAA 2025, Article 22C"))   # should give {'s80-22c'}
print(_extract_articles("UK MDR 2002, Reg. 5"))      # should give {'5'}
print(_extract_articles("GDPR, Article 9"))      # should give {'9'}
print(_extract_articles("UK MDR Reg. 5"))      # should give {'2', '8', '9'}