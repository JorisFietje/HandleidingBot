## 1. Wat is HandleidingChat?

Wij hebben een chatbot gebouwd die vragen beantwoordt op basis van technische
handleidingen (PDF, Word, Markdown). De applicatie doorzoekt de handleidingen
semantisch, kiest de meest relevante secties, en laat een lokale LLM (via Ollama) op
basis daarvan een antwoord formuleren. Bij elk antwoord tonen wij een klikbare
bronvermelding naar de exacte pagina in de PDF, en waar relevant ook de bijbehorende
afbeelding(en).

**Technische opzet:** wij gebruiken een FastAPI-backend, sentence-transformers voor
semantisch zoeken, rapidfuzz voor fuzzy-matching, PyMuPDF/python-docx voor het inlezen
van documenten, Ollama voor het genereren van antwoorden, en een vanilla HTML/CSS/JS-
frontend.

---

## 2. Roadmap (per fase)

### Fase 1 — Fundament (v1.0.0)
Wij zijn begonnen met:
- Een volledige pagina-layout met uitschuifbare zijbalk (geen losse chat-widget meer).
- Sessiebeheer via `localStorage` (max. 20 gesprekken; 2 uur inactiviteit = nieuw gesprek).
- Semantisch zoeken via `paraphrase-multilingual-MiniLM-L12-v2` (sentence-transformers).
- Fuzzy-matching via rapidfuzz voor typefoutbestendig zoeken.
- Ondersteuning voor Markdown-handleidingen (`.md`).
- Een FastAPI-backend met een `/chat`-endpoint.

### Fase 2 — Meer documentformaten (v1.1.0)
Daarna hebben wij toegevoegd:
- Ondersteuning voor PDF (`.pdf`) via PyMuPDF — automatische sectiedetectie op
  lettergrootte en vetgedrukte tekst.
- Ondersteuning voor Word (`.docx`) via python-docx — sectiedetectie op Heading-stijlen.
- Automatische sessietitels op basis van de eerste vraag.
- Hernoemen/verwijderen van sessies via een 3-punten-menu in de zijbalk.
- Hybride zoekscoring: cosine-similariteit + fuzzy-boost.

### Fase 3 — Bronvermelding & verfijning (v1.2.0)
Vervolgens hebben wij de bronvermelding en relevantie aangescherpt:
- Klikbare bronvermelding met directe link naar de exacte PDF-pagina (`#page=N`).
- PDF's serveren wij via `/handleidingen/<bestandsnaam>`.
- Wij houden het paginanummer per sectie bij tijdens het inladen.
- Wij verhoogden de cosine-drempel (0.15 → 0.42) zodat irrelevante vragen geen
  resultaat meer geven.
- Wij filteren zwakke secties (te korte titel/inhoud) weg.

### Fase 4 — LLM-aansturing & afstelbaarheid (v1.3.0)
Om de antwoordkwaliteit te kunnen sturen, bouwden wij:
- Een adminpagina op `/admin` om de lokale LLM live af te stellen zonder herstart.
- Instelbare LLM-parameters (model, temperature, top_p/top_k, repeat_penalty,
  num_predict, num_ctx, seed, systeemprompt) en retrieval-parameters (top_n, drempels).
- Validatie en begrenzing van instellingen, opgeslagen in `admin_settings.json`.
- Een testset-runner die `testset.json` tegen de huidige instellingen draait en
  automatisch scoort op sleutelwoord-dekking (goed/deels/mis), met een samenvatting
  bovenaan.

### Fase 5 — Afbeeldingen uit de PDF (huidig)
Op dit moment hebben wij gebouwd:
- On-demand renderen van figuren uit de PDF via een `/afbeelding`-endpoint.
- Detectie van figuur-regio's (vectortekeningen én ingebedde rasters).
- Koppeling van tekstverwijzingen ("zie afbeelding 17") aan de juiste pagina/figuur.
- Een afbeeldingsgalerij onder het antwoord met lightbox-weergave in de frontend.

---

## 3. Problemen waar wij tegenaan liepen & hoe wij ze hebben opgelost

### 3.1 Retrieval — de juiste sectie vinden

**Probleem: irrelevante vragen leverden toch resultaten op.**
Met een lage cosine-drempel (0.15) kreeg elke vraag wel "iets" terug, ook als er niets
relevants in de handleiding stond.
*Onze oplossing:* wij verhoogden de drempel naar 0.42 en splitsten hem in twee waarden
(`drempel_globaal` en `drempel_filter`), beide instelbaar via de adminpagina. Daardoor
geven niet-passende vragen netjes "niets gevonden" in plaats van een misleidend antwoord.

**Probleem: typefouten en samengestelde woorden werden gemist.**
Puur semantisch zoeken miste trefwoord-matches; "beschrijving" vond bijvoorbeeld
"opdrachtbeschrijving" niet, en typefouten kelderden de score.
*Onze oplossing:* wij combineren cosine-similariteit met een genormaliseerde fuzzy-boost
(rapidfuzz) tot één hybride score. Wij gebruiken `partial_ratio` tegen de volledige
titeltekst voor samengestelde woorden en `ratio` per token voor typefouten, met extra
gewicht als de match in de titel zit.

**Probleem: het antwoord kwam soms uit de handleiding van het verkeerde apparaat.**
Bij meerdere handleidingen konden wij een vraag over model "789" beantwoorden uit de
handleiding van een ander model.
*Onze oplossing:* wij bouwden een model-detectie die modelnummers uit de
handleidingnamen indexeert (alfanumerieke tokens met een cijfer, ≥3 tekens). Noemt de
vraag zo'n nummer, dan routeren wij de zoekopdracht naar die handleiding. Noemt de vraag
géén model maar staat het onderwerp in meerdere handleidingen, dan vragen wij éérst om
welk apparaat het gaat — met alleen de relevante apparaten als keuze.

**Probleem: bijna-identieke secties verschenen dubbel als bron.**
*Onze oplossing:* wij dedupliceren op titel en op `fuzz.ratio` van de eerste 300 tekens
van de inhoud (>88 = duplicaat).

**Probleem: foutcode-vragen vonden de foutcodetabel slecht.**
*Onze oplossing:* wij breiden error-vragen uit met extra zoektermen ("foutcode fout
oplossing zelftest tabel") en geven secties met titels als "oplossing", "foutcode",
"storing" of "error" een score-boost.

**Probleem: vragen over displaypatronen zoals "-----" werkten niet.**
Een kale symboolreeks heeft geen semantische betekenis voor het embedding-model.
*Onze oplossing:* secties die de symboolreeks letterlijk bevatten geven wij een sterke
boost, en in de vraag aan het LLM vervangen wij de reeks door "woord (reeks)" — bijv.
`streepjes (-----)` — zodat het model de koppeling met de handleidingtekst legt.

**Probleem: antwoorden mengden Nederlands en Engels.**
Sommige handleidingen zijn Engelstalig; een Nederlandse vraag kon een Engelse sectie
terugkrijgen.
*Onze oplossing:* wij voegden een eenvoudige taaldetectie op basis van stopwoorden toe.
Bij gelijke relevantie prefereren wij secties in dezelfde taal als de vraag.

### 3.2 Documenten inlezen

**Probleem: PDF's hebben geen expliciete sectiestructuur.**
*Onze oplossing:* wij detecteren secties op opmaak — een regel is een kop als die groter
is dan de body-tekst óf vetgedrukt is, en niet te lang. De body-lettergrootte bepalen
wij als de meest voorkomende fontgrootte in het document.

**Probleem: rommelige "secties" (inhoudsopgaven, losse nummers, lege blokken).**
*Onze oplossing:* wij passen een kwaliteitsfilter toe bij het laden — weg met secties
met lege/te korte inhoud (<80 tekens), te korte titel (<3 tekens), of inhoud die voor
minder dan 40% uit letters bestaat.

**Probleem: icoon-glyphs uit symboolfonts verschenen als vervang-tekens.**
Knoppen, waarschuwings- en aansluitmarkers zitten in de Private Use Area
(U+E000–U+F8FF) en hebben geen leesbare Unicode-mapping.
*Onze oplossing:* zulke glyphs vervangen wij door een neutrale placeholder `[knop]` in de
getoonde tekst. Belangrijk: wij schonen alléén de tekst die wij de gebruiker tonen — de
context die naar het LLM gaat laten wij ongemoeid, zodat de embeddings/antwoorden niet
onbedoeld veranderen.

### 3.3 Afbeeldingen uit de PDF

**Probleem: veel handleidingen bevatten geen foto's maar vectortekeningen.**
Alleen ingebedde rasterafbeeldingen ophalen miste de meeste figuren.
*Onze oplossing:* wij detecteren figuur-regio's via `cluster_drawings()` (vectorfiguren)
én `get_images()` (rasters), filteren logo's/iconen (te klein) en volledige-paginakaders
weg, en dedupliceren overlappende regio's.

**Probleem: een figuur waar de tekst naar verwijst, staat soms op een vervolgpagina.**
Een verwijzing "zie afbeelding 17" kon naar een figuur op een pagina wijzen die formeel
bij een volgende sectie hoort.
*Onze oplossing:* tijdens het inladen bouwen wij een figuur-index
(`{nummer: (pagina, y-positie)}`). Bij een tekstverwijzing zoeken wij het bijschrift op
en kiezen wij de figuur-regio net boven dat bijschrift, ook als die op een andere pagina
staat.

**Probleem: afbeeldingen vooraf opslaan kost ruimte en is lastig te onderhouden.**
*Onze oplossing:* wij slaan niets op — de afbeelding renderen wij pas als de browser de
URL opvraagt (`/afbeelding`-endpoint met pagina + clip-rechthoek). Zo werken nieuwe
PDF's automatisch mee, zonder voorbewerkingsstap.

### 3.4 LLM-antwoorden

**Probleem: de antwoordkwaliteit was niet stuurbaar.**
Wij gebruikten Ollama's standaardinstellingen, die hardcoded stonden; afstellen vereiste
codewijzigingen en herstarts.
*Onze oplossing:* wij brachten alle LLM- en retrieval-parameters onder in een centrale
`settings`-module en een adminpagina. Wijzigingen valideren en begrenzen wij, slaan wij
op in `admin_settings.json` en passen wij direct toe — zonder herstart.

**Probleem: wij konden niet objectief zien of een instelling het beter of slechter maakte.**
*Onze oplossing:* wij bouwden een testset-runner op de adminpagina. Die draait onze
handleidingspecifieke testvragen (`testset.json`) tegen de huidige instellingen en
scoort automatisch op sleutelwoord-dekking (goed/deels/mis), inclusief ontbrekende
sleutelwoorden en een samenvatting. Getalnotaties (`10.000` vs `10000`) normaliseren wij
zodat ze gelijk tellen. In de praktijk zetten wij `temperature` op 0 met een vaste
`seed`, zodat verschillen tussen runs door onze instellingen komen en niet door toeval.

**Probleem: het model plakte soms een "niet gevonden"-melding achter een prima antwoord.**
Dit "hedging"-gedrag maakte goede antwoorden onnodig onzeker.
*Onze oplossing:* wij strippen die melding als er een inhoudelijk antwoord overblijft
(≥25 tekens). Staat de melding er alléén, dan laten wij hem staan als echte melding.

**Probleem: een afbeelding-instructie in de systeemprompt maakte kleinere modellen overdreven terughoudend.**
*Onze oplossing:* wij voegen géén afbeelding-instructie aan de prompt toe. De verwijzing
("Zie de afbeelding hieronder.") plakken wij deterministisch in code achter het antwoord
— alleen als er daadwerkelijk figuren zijn. Zo houden wij de antwoordkwaliteit hoog en
verzint het model geen figuurnummers.

### 3.5 Frontend & UX

**Probleem: de oude bronvermelding (twee grote sectiekaarten) nam te veel ruimte in.**
*Onze oplossing:* wij vervingen die door een compacte bronbalk met klikbare pill-knoppen
(bestandsnaam + paginanummer) in hetzelfde berichtblok; dubbele bronnen voegen wij samen.

**Probleem: het filterwidget voor handleidingen was omslachtig.**
*Onze oplossing:* wij verwijderden het — wij zoeken nu automatisch over alle
handleidingen, met de model-routing en de "welk apparaat?"-vraag als vangnet.

**Overige UX-verbeteringen die wij doorvoerden:** een auto-resizing invoerveld
(1→2 regels), begrensde berichtbreedtes, een lightbox voor afbeeldingen, en een
admin-knop in de header.

---

## 4. Bekende aandachtspunten / mogelijke vervolgstappen

- Onze sectiedetectie in PDF's leunt op opmaak; documenten zonder duidelijke
  koppenstructuur geven mindere resultaten.
- Gescande PDF's zonder tekstlaag werken niet (wij hebben geen OCR).
- Onze taaldetectie is stopwoord-gebaseerd en simpel; voor korte vragen kan dat
  "onbekend" opleveren.
- Onze testset is handmatig en handleidingspecifiek; uitbreiden verbetert de meetwaarde.
- Mogelijke vervolgstappen die wij zien: OCR voor gescande PDF's, betere kopdetectie, en
  een uitgebreidere automatische evaluatie.
