# Outreach e-mail guidelines (Hungarian cold outreach)

The agent writes one personalized e-mail per eligible business. The goal is a
warm, human, trustworthy note from **Hartmann Attila**, a real web developer,
offering to help a business with a great reputation but no proper website.

## Voice
- **Hungarian**, magázás (formal "Ön"), but friendly and human — like a real
  person who genuinely looked them up, not a mass mailer.
- Direct yet respectful. Short paragraphs. No buzzwords, no "enterprise" jargon,
  no exclamation-mark spam, no ALL CAPS, no "INGYENES!!!".
- Small-business framing: *"egyszerű, megbízható weboldal, ami ügyfeleket hoz"* —
  not Angular/framework talk.
- Build rapport with a **specific, true** detail (their real Google rating /
  review count, their town, their field). Never invent facts.
- 60–110 words in the body — ONLY the opener, the gap, and the benefits (everything
  after that is added automatically by the script). Skimmable.

## Structure of the body
1. **Personal opener** — name the business + an honest compliment grounded in
   their Google reviews (e.g. *"a(z) {review_count} Google-értékelés és {rating}
   csillag alapján sokan elégedettek Önökkel {city}ban"*).
2. **The gap** — they clearly do good work, yet there's no real website, so
   potential ügyfelek who search online don't find/​trust them, or land on a
   competitor.
3. **2–3 concrete 2026 benefits** (pick what fits the industry): megjelenés a
   Google-keresésben, 0–24 elérhetőség, online időpontfoglalás, hitelesség a
   versenytársakkal szemben, mobilbarát bemutatkozás.
**STOP after the benefits.** Do **NOT** write the sentence that introduces the sample
page, do **NOT** include any link or the `{{SAMPLE_PAGE_URL}}` token, and do **NOT**
write a closing call-to-action or a sign-off. The publish script adds — automatically and
identically on every e-mail — a fixed sample-page introduction, the sample-page button,
the value-proposition + free-domain cards, a fixed closing paragraph, and the footer.
Your `body` is ONLY: the personal opener, the gap, and the 2–3 concrete benefits.

## Subject line
- Per-business and specific; never identical across e-mails. Calm, not clickbait.
- Examples: *"Weboldal-ötlet a(z) {name} számára"*, *"{name} – készítettem Önöknek
  egy mintaoldalt"*, *"{city}i {industry}: pár gondolat az online megjelenésről"*.

## email.json contract (write this file to `.tmp/prepared/<place_id>/email.json`)
```json
{
  "place_id": "ChIJ...",
  "email_address": "info@pelda.hu",        // "" if none could be found
  "email_source": "facebook",              // facebook|instagram|websearch|manual|""
  "subject": "…",
  "body": "…personal opener + the gap + 2–3 benefits ONLY (no link, no token, no closing)…",
  "notes": "FB About oldalon találtam / nem volt e-mail, csak telefon",
  "domain_candidates": ["kovacsfogaszat", "drkovacs", "kovacsfogaszatbudapest", "kovacsdental"]
}
```
- **`domain_candidates`** — 4–6 brandable domain *stems* (no TLD, no dot) derived from
  the business name / field / town, so the publish script can check which are free and show
  2–3 "ez lehetne az Öné" options. Rules: **lowercase ASCII only**, Hungarian accents
  transliterated (á→a, é→e, í→i, ó/ö/ő→o, ú/ü/ű→u), no spaces/punctuation. Order best first.
  Do **NOT** mention domains in the body prose — the script renders them in a separate card.
- If **no e-mail** was found: still write email.json with `email_address: ""`,
  fill `notes` with where you looked, and do **not** build an index.html. The
  publish script will mark the row `no_email` and skip it.
- If an e-mail **was** found: also write the filled `index.html` (from
  `templates/landing_base.html`) into the same folder.

## Footer appended automatically by the publish script (do not write it yourself)
```
—
Hartmann Attila · webfejlesztő
✉ {GMAIL_ADDRESS}   ·   Weboldal: https://attila-hartmann.github.io/attila-website/?lang=hu
LinkedIn: https://www.linkedin.com/in/attila-hartmann-b7b41a24b/

Ezt a levelet azért kapta, mert nyilvánosan elérhető céges elérhetőséget találtam Önökhöz.
Ha nem kíván több ilyen levelet kapni, válaszoljon ennyivel: „leiratkozás”.
```

## Worked example (body)
```
Tisztelt Kovács Fogászat!

Rákerestem Önökre, és a 4,8 csillagos, 132 értékelésből álló Google-profil
alapján látszik, hogy sok páciens elégedett a rendelőjük szolgáltatásaival.

Egy dolog viszont feltűnt: nincsen saját weboldaluk. A legtöbb új vendég ma már
online tájékozódik, mielőtt időpontot foglal – saját oldal nélkül viszont könnyen
egy versenytársnál köt ki.

Egy egyszerű, mobilra optimalizált weboldal sokat segítene: megjelennének a
Google-keresésben, a szolgáltatások gyorsan áttekinthetőek lennének, és az
érdeklődők bármikor könnyen kapcsolatba léphetnének Önökkel.
```
The body STOPS here. The publish script then automatically appends — identically on
every e-mail — the fixed sample-page introduction, the "Megnézem a mintaoldalt" button,
the value + free-domain cards, the fixed closing paragraph, and the footer.
