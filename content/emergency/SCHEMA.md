# Emergency numbers (`content/emergency/<CC>.json`)

One file per country, named with the country's ISO 3166-1 alpha-2 code in capitals (`CL.json`). The table is read like
the guides: offline, no network. A wrong number in an emergency is worse than none, so every number carries where it
came from and when someone last checked it, and `app/tests/test_emergency_numbers.py` fails when one does not.

This folder holds the data and its format only. Nothing in the app reads it yet: choosing the country, the picker and
what to show when the country is unknown are still being discussed in the issue.

```json
{
  "country": "Chile",
  "code": "CL",
  "calling_code": "+56",
  "languages": ["es"],
  "general": null,
  "services": [
    {
      "kind": "ambulance",
      "name": "SAMU",
      "number": "131",
      "how": ["call"],
      "works_from": ["mobile", "landline"],
      "works_from_source": "https://example.gov/dialling-rules",
      "free": true,
      "free_source": "https://example.gov/costs",
      "url": "https://example.gov/samu",
      "keywords": {"es": ["ambulancia", "samu"], "en": ["ambulance"]},
      "when": "Free-text note: when to use this number, or where it applies.",
      "source": "https://example.gov/page",
      "checked_on": "2026-11-21",
      "verified": "official"
    }
  ]
}
```

## Country fields

| Field | Meaning |
| --- | --- |
| `country` | The country's name in English. |
| `code` | ISO 3166-1 alpha-2, capitals. Must match the file name. |
| `calling_code` | The country calling code: `+` and one to three digits (`+56`). |
| `languages` | Required. The country's main languages, as two-letter ISO 639-1 codes without a region (`es`, `qu`, `ay`; never `es-cl`, never a three-letter code), each listed once, up to 4 main languages (not "the official languages": a country such as Bolivia, South Africa or India names many more; list the main ones people actually use).  Every service's `keywords` must cover exactly these languages plus `en`, none of them empty; the test fails otherwise. |
| `general` | The `number` of the service that answers any emergency, or `null`. `null` means no unified line is recorded here; it does not say the country has none, unless a source establishes that. It must match a `number` in `services`. |
| `services` | The list of numbers, most reliable first. At least one. |

## Service fields

| Field | Meaning |
| --- | --- |
| `kind` | `general`, `ambulance`, `fire`, `police`, `poison`, `crisis` (suicide and mental-health crisis lines) or `other`. |
| `name` | What the service is called locally (`SAMU`, `Bomberos`). |
| `number` | Digits, spaces, and a leading `+` or `*` only, as it is dialled. |
| `how` | One or more of `call`, `sms`, `chat`, `app`. |
| `works_from` | Any of `mobile`, `landline`, `voip`. List only what a source says; empty when the source does not say. |
| `keywords` | Language code only (two lower-case letters, ISO 639-1: `es`, `qu`, `ay`; never a region such as `es-cl` or a three-letter code, which the test rejects) to a list of words a person might type to find this service ("bomberos" / "fire"). One list for every language in the country's `languages`, plus `en`, no more and no fewer, and none empty. Lower case. |
| `area_whole_country` | Optional. `true` (yes) when a source says the number covers the whole country, `false` (no) when a source says it does not. Leave it out when no source says. |
| `area` | Optional, and only when `area_whole_country` is not `true`. The specific place the number covers, in free text (a comuna, a city). Numbers that belong to one comuna, such as the 1XXX municipal lines, need it. Leave it out when no source says. |
| `url` | Optional. The web address of the service's own page, where a person can read more. It is not evidence for any claim (the `*_source` fields are); leave it out when the service has no page of its own. |
| `works_from_source` | The page that says `works_from`. Required when `works_from` is not empty; leave it out otherwise. |
| `free` | `true` or `false` when a source says whether it costs money, `null` when none does. `true` means both the call and the service are free; `false` when either costs something (a call charged at landline rates to a free service is `false`). Always present. |
| `free_source` | The page that says `free`. Required when `free` is not `null`; leave it out otherwise. |
| `when` | A free-text note, in English: when this number is the right one and where it applies. Empty string if there is nothing to add. |
| `source` | The web address of the page the number and its name were read from. A country's own government or the service's own page. A list of addresses when more than one page backs the row (a numbering resolution and the decree that created the service). |
| `checked_on` | `YYYY-MM-DD`, the day someone read the number on that page. Not in the future. |
| `verified` | `official`: seen on an official page. `found_online`: only found elsewhere. The app labels `found_online` numbers as unverified. |

## Checking a row

Each claim has its own source, so an editor can check one claim without the others: `source` for the number and its
name, `works_from_source` for where it can be dialled from, `free_source` for the cost. A claim no page backs is left
unknown (`works_from: []`, `free: null`), never filled in from memory. The sources may be different pages: in
`CL.json`, 130 to 134 and 136 to 138 are read in Subtel's numbering appendix (Resolución 1534), the dialling in
Decreto 747 art. 15 and the cost in Decreto 18 art. 21; 147 and 1455 are in the same appendix, but no source says how
they can be dialled or whether they are free, so those stay unknown. `when` holds only what a person needs to know; it does not carry the legal
basis. It stays within what the row's cited pages say: advice such as "call another service first" goes in only with
a source of its own.

Every value has one JSON type, checked row by row: text is a string, `free` and `area_whole_country` are `true` or
`false` (never `0` or `1`, never the word "yes"), `how`, `works_from` and the keyword lists hold strings, and a wrong
type fails the test with a plain message instead of passing or crashing it.

A key that is not in this document fails the test (a typo such as `works_form` would otherwise pass unnoticed), and so
does the same `number` listed twice in one file.

A service whose `source` could not be reached is not added. A number nobody can source stays out of the table.

## Showing it (not part of this change)

The agreed idea: an urgent guide or answer shows two numbers, the one for this emergency plus the most reliable
fallback, with "See all numbers" for the rest; a calm question ("what's the police number in Chile?") shows the full
list. That is why `services` is ordered and why `verified` exists.
