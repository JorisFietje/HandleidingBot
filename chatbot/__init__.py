"""Kern van de chatbot: handleidingen inlezen, doorzoeken en antwoorden genereren.

Dit package vervangt het vroegere monolithische chatbot.py en is opgesplitst per
verantwoordelijkheid:

- model       - de `Section`-dataclass + gedeelde constanten.
- text        - taaldetectie, trefwoorden, fuzzy-matching, glyph-opschoning, symbolen.
- embeddings  - het semantische model (lazy) + cosine-scores.
- loading     - PDF/Word/Markdown inlezen, opdelen in secties, kwaliteitsfilter.
- search      - de relevante secties bij een vraag vinden (hybride score + routing).
- images      - figuren uit PDF's lokaliseren en als URL aanbieden.
- answer      - intentieherkenning en het volledige chat-antwoord opbouwen.

De webserver (main.py) gebruikt `load_manuals`, `generate_answer`,
`generate_answer_stream` en `STOPWORDS`; die worden hieronder her-geëxporteerd zodat
`from chatbot import ...` blijft werken.
"""

from .model import STOPWORDS
from .loading import load_manuals
from .answer import generate_answer, generate_answer_stream

__all__ = ["STOPWORDS", "load_manuals", "generate_answer", "generate_answer_stream"]
