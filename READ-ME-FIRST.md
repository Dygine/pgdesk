# Fix: the toggle still would not stay on — and the layout

## Why my last fix did not work

There are **three** places a settings field has to be declared, and all three
discard silently when they disagree. I fixed two and missed the first one.

```
1. frontend  WRITABLE map in MasterSettings.jsx   <- still broken until now
2. backend   PlatformSettingsUpdate schema         <- fixed last round
3. backend   WRITABLE set in the service           <- fixed originally
```

`buildPayload()` loops over that frontend map and sends only what it lists. The
Dygine fields were not in it, so the browser never sent them at all. The request
succeeded, the response came back without them, the form re-seeded from that
response, and the toggle reverted — with no error at any layer.

So my previous patch was correct but insufficient. Gate 1 was still dropping
them before the request left the browser.

## Layout

The card was sitting in one half of a two-column grid. It carries a URL, a key
id, two secrets, two buttons, warnings and a code block — at half width the
fields wrapped and the "do not swap these two secrets" warning became unreadable,
which is the one thing on that card that most needs reading.

Now: full width, with the URL and key id paired across two columns, the two
secrets paired directly under their warning, and everything else full width.

## Two files

```
frontend/src/pages/master/MasterSettings.jsx   the four missing fields + full width
frontend/src/pages/master/DygineCard.jsx       accepts className, body restructured
```

Copy both over the ones in your repo, then from the repo root:

```powershell
git add .
git commit -m "fix: dygine fields were never sent by the browser"
git push origin main
```

Frontend only. No backend change, no migration.

## After it deploys

Master admin → Settings → Dygine Pay:

1. URL: `https://dygine-pay.onrender.com`
2. Key id: `dgn_test_BAEavLU1y84sxjYR`
3. Leave both secret fields empty — they are already stored
4. Turn the toggle on
5. **Save changes** at the top of the page
6. **Reload** — the toggle must still be on. If it is not, tell me before going further.
7. **Test connection**

## Still outstanding on the Dygine side

PGGuru has no webhook URL yet — Dygine admin → Products & keys shows "No webhook
URL — this tool gets no events". Set it to:

```
https://pgdesk-api.onrender.com/api/v1/webhooks/dygine
```

Without it, payments will succeed and subscriptions will never extend.
