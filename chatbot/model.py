"""Gedeeld datamodel en constanten voor de chatbot.

Hier staan de `Section`-dataclass (één sectie uit een handleiding) en de constanten
die door meerdere modules in dit package worden gebruikt. Dit bestand heeft bewust
geen interne afhankelijkheden, zodat het door alle andere modules veilig kan worden
geïmporteerd zonder kans op circulaire imports.
"""

import os
from dataclasses import dataclass, field

import numpy as np

MANUALS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "handleidingen")

STOPWORDS = {
    "de", "het", "een", "en", "of", "is", "ik", "je", "jij", "mijn", "hoe",
    "wat", "waar", "wanneer", "waarom", "kan", "kun", "wil", "moet", "mag",
    "dat", "dit", "die", "deze", "met", "van", "voor", "naar", "in", "op",
    "aan", "uit", "over", "bij", "om", "te", "zijn", "heeft", "hebben",
    "niet", "ook", "maar", "dan", "als", "er", "nog", "al", "zo", "wel",
    "via", "door", "wordt", "worden", "werd", "was", "bent", "ben",
    "had", "zal", "zou", "ga", "gaan", "ging",
}

ENGLISH_STOPWORDS = {
    "the", "and", "for", "are", "was", "were", "this", "that", "with",
    "have", "from", "they", "will", "been", "their", "when", "your",
    "can", "also", "use", "using", "used", "call", "visit", "contact",
    "press", "select", "display", "function", "button", "connect",
}

GREETINGS = {"hoi", "hallo", "hey", "hi", "goedemorgen", "goedemiddag", "goedenavond"}
THANKS    = {"bedankt", "dankjewel", "dank", "dankje", "thanks"}
FAREWELLS = {"doei", "dag", "bye", "ciao"}

TOPIC_OPTIONS = [
    "Installatie",
    "Storing of foutcode",
    "Onderhoud & reiniging",
    "Technische specificaties",
    "Andere handleiding",
]


@dataclass
class Section:
    title: str
    content: str
    manual_name: str
    file_name: str = ""
    page: int | None = None
    end_page: int | None = None
    _tokens: set[str]     = field(default_factory=set, repr=False)
    _embedding: np.ndarray | None = field(default=None, repr=False)
