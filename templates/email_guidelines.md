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
- 110–170 words in the body (before the link and footer). Skimmable.

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
4. **The offer** — you already made them a *free, no-obligation sample page* and
   put the link in. Insert the literal token `{{SAMPLE_PAGE_URL}}` on its own
   line where the link should appear (the publish script swaps in the real URL).
5. **Soft CTA** — offer a short, no-pressure 15-minute chat / reply if it's of
   interest; make clear there's no obligation.

> Do **NOT** write a signature or opt-out line — the publish script appends a
> standardized footer automatically (see below). End the body after the CTA.

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
  "body": "…multi-line Hungarian text, contains the {{SAMPLE_PAGE_URL}} token…",
  "notes": "FB About oldalon találtam / nem volt e-mail, csak telefon"
}
```
- If **no e-mail** was found: still write email.json with `email_address: ""`,
  fill `notes` with where you looked, and do **not** build an index.html. The
  publish script will mark the row `no_email` and skip it.
- If an e-mail **was** found: also write the filled `index.html` (from
  `templates/landing_base.html`) into the same folder.

## Footer appended automatically by the publish script (do not write it yourself)
```
—
Hartmann Attila · webfejlesztő
✉ {GMAIL_ADDRESS}   ·   Portfólió: https://attila-hartmann.github.io/attila-website/?lang=hu
LinkedIn: https://www.linkedin.com/in/attila-hartmann-b7b41a24b/

Ezt a levelet azért kapta, mert nyilvánosan elérhető céges elérhetőséget találtam Önökhöz.
Ha nem kíván több ilyen levelet kapni, válaszoljon ennyivel: „leiratkozás”, és többé nem írok.
```

## Worked example (body)
```
Tisztelt Kovács Fogászat!

Rákerestem Önökre, és a 4,8 csillagos, 132 értékelésből álló Google-profil
alapján látszik, hogy sok páciens elégedett a budapesti rendelővel.

Egy dolog viszont feltűnt: nincs saját weboldaluk. Aki ma fogorvost keres,
előbb rákeres a neten – weboldal nélkül viszont könnyen egy versenytársnál köt
ki, pedig az Önök munkája és értékelései meggyőzőbbek lennének.

Egy egyszerű, mobilbarát oldal segítene: megjelennének a Google-keresésben,
a páciensek 0–24-ben tájékozódhatnának, és akár online is időpontot kérhetnének.

Hogy ne csak beszéljek róla, készítettem Önöknek egy ingyenes mintaoldalt – itt
megnézhetik, kötelezettség nélkül:

{{SAMPLE_PAGE_URL}}

Ha érdekesnek találják, szívesen beszélgetnék róla 15 percben, vagy válaszol egy
sort erre a levélre. Ha nem aktuális, az is teljesen rendben.
```
