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
Ha nem kíván több ilyen levelet kapni, válaszoljon ennyivel: „leiratkozás”.
```

## Worked example (body)
```
Tisztelt Kovács Fogászat!

Rákerestem Önökre, és a 4,8 csillagos, 132 értékelésből álló Google-profil
alapján látszik, hogy sok páciens elégedett a rendelőjük szolgáltatásaival.

Egy dolog viszont feltűnt: nincsen saját weboldaluk. A legtöbb új vendég ma már online tájékozódik, mielőtt időpontot foglal. Egy modern weboldal segíthet abban, hogy könnyebben megtalálják Önöket, és nagyobb bizalommal jelentkezzenek be.

Egy egyszerű, mobilra optimalizált weboldal segíthetne Önöknek abban, hogy megjelenjenek a Google-keresésekben és így a páciensek könnyebben megtalálják Önöket, gyorsan áttekinthetőek legyenek a szolgáltatások, és az érdeklődők egyszerűbben kapcsolatba léphessenek Önökkel.

Hogy ne csak beszéljek róla, készítettem Önöknek egy ingyenes mintaoldalt, hogy lássák, hogyan nézhetne ki egy modern weboldal az Önök számára – itt
megnézhetik, kötelezettség nélkül:

{{SAMPLE_PAGE_URL}}

Ha úgy érzik, hogy egy modernebb online megjelenés hasznos lenne a vállalkozásuk számára, kérem válaszoljanak erre az e-mailre, és szívesen megmutatom, hogy milyen lehetőségeket látok. Egy rövid, kötelezettségmentes konzultáció keretében át tudjuk beszélni az elképzeléseiket és a lehetőségeket. Ha most nem aktuális, természetesen nem szükséges reagálniuk.
```
