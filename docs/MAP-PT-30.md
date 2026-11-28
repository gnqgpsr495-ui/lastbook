# Madeira (PT-30): a working offline map

The first Portugal region built on the plan in [REGIONS-PT.md](REGIONS-PT.md): streets, named places, help
points and street addresses for Madeira, built from redistributable sources by one command, kept in its own
folder. It follows the file formats in [MAPS.md](MAPS.md). The region keeps its full ID, `PT-30`: the ISO
3166-2:PT code, the NUTS II code and the former district of Madeira coincide, so the ID is the same whichever
division the region format settles on (the proposal's rows are lower-case, `pt-30`; the case is #31's call).

This is a builder and a testable map set, not an installer: the shared region format and the regional
address-index IDs are still being designed (#31), and the shared map builder work is #25 — nothing here touches
`engine/`, `server.py`, `web/`, `packaging/`, the release manifest, the setup flow or the search runtime, because
`tools/build_map.py` runs unchanged. The sidecar carries its normalisation rule in `meta.norm = pt-1`; the
address fixtures at the end are what a future runtime path can be checked against.

## Build it

```sh
python3 tools/build_region_pt_30.py fetch    # downloads the sources, about 1.03 GB, into derived/regions/PT-30/source/
python3 tools/build_region_pt_30.py build    # stages derived/regions/PT-30/data.new/, checks it, then swaps it into data/
python3 tools/build_region_pt_30.py check    # validates data/; exits non-zero on any failure
python3 tools/build_region_pt_30.py demo     # adds an empty library beside it for trying the map alone
python3 server.py --data derived/regions/PT-30/demo --no-index
```

Python 3.9 or newer and its standard library; no GDAL, no other packages. `fetch` is the only step that uses
the network, and it keeps files whose SHA-256 matches the previous fetch. Everything is written under
`derived/regions/PT-30/`, so no existing map set changes. A build never rewrites a good output: it stages into
`data.new/`, checks the staging, and only then replaces `data/` — a rebuild that fails or stops leaves the last
good `data/` (with its `build.json`) as it was, and one that stops between the two final renames is repaired by
the next build. An output kept from the earlier builder carries its report beside `data/` rather than inside it;
`check` reads that legacy report for the live map until a successful build replaces it — a staging folder without
its own report is reported as missing, never validated against another output's report.
`data/build.json` records every source (URL, dated file name, data date, licence, size,
SHA-256) and every output (size, SHA-256).

## Sources

| What | Source | Licence | Attribution |
|---|---|---|---|
| Streets, water, land use, buildings, named places and points | OpenStreetMap via Geofabrik, `portugal-261121-free.gpkg.zip` (data of 21 November 2026; the dated name is recorded). No Madeira subregion exists, so the country extract is cut to the region box at build time | ODbL 1.0 | © OpenStreetMap contributors (already on the map) |
| Street addresses (house, street, postcode, freguesia) | INE address register, distributed by OpenAddresses as `pt_addresses.csv.zip` (5,911,139 rows; the 130,271 inside the region box are the ones kept) | CC BY 4.0 | Instituto Nacional de Estatística, I.P. |
| Region box, municípios and freguesias | CAOP 2025, Região Autónoma da Madeira, `CAOP_RAM_2025-gpkg.zip` (served 2 February 2026) | CC BY 4.0 | Direção-Geral do Território |

The CAOP register is a high-value dataset under Regulation (EU) 2023/138 of the Open Data Directive, and DGT's
open-data page states the licence: CC BY 4.0, with naming the Direção-Geral do Território as the only duty.
That settles what [REGIONS-PT.md](REGIONS-PT.md) left for a browser check: the proposal's GISCO-derived boxes
were research-only because Eurostat's terms limit commercial use; a shipped build needs a source without that
limit, and the CAOP is the one REGIONS-PT.md named for it.

## The region box

The box is the exact WGS84 extent of the official CAOP 2025 NUTS II polygon, every vertex converted from
EPSG:5016 (PTRA08 / UTM zone 28N), plus the 0.15° margin and the outward rounding REGIONS-PT.md uses:

| Edge | Official extent (raw) | Published box (with margin) | GISCO raw (REGIONS-PT.md) |
|---|---|---|---|
| West | −17.265938 | −17.42 | −17.2659996 |
| South | 30.028778 | 29.87 | 30.0256728 |
| East | −15.853671 | −15.70 | −15.8554201 |
| North | 33.128161 | 33.28 | 33.1039936 |

The official polygon moves only the north edge, by 0.024°: Porto Santo's northern tip, which the GISCO 1:3M
generalisation does not carry. West, south and east agree with GISCO by at most 0.0031°, and the Selvagens Islands
(30.029° N–30.14° N) are in both, so the earlier address-group cross-checks hold unchanged. All 130,271 INE
address rows sit inside the official box, and the address count measured in REGIONS-PT.md reproduces exactly.
The pilot updates the `pt-30` row of [regions-pt-proposed.json](regions-pt-proposed.json) to the CAOP figures;
the seven continental rows keep GISCO and the two Azores rows their address-point boxes until each is verified
the same way.

## What the build holds

Built on 22 November 2026 from the sources above, and rebuilt on 24 November 2026 with the pt-1 and
house-label corrections described under "The pt-1 rule" (every count unchanged). A full `fetch`, `build`,
`check` takes about 12 minutes, most of it downloading; the build itself runs in about 40 seconds, most of
that reading the 1.7 GB country extract to cut it.

| File | Size | SHA-256 (this build) | Holds |
|---|---|---|---|
| `derived/geo/national.sqlite` | 33.3 MB | `d54ed9ec…e6d6` | 51,294 road features plus water, land, rail, buildings and places from OpenStreetMap, cut to the region box; 2,705 help and supply points across 35 classes |
| `derived/geo/map.sqlite` | 0.03 MB | `401df1ab…19cd` | empty map tables with the source and bounds metadata, as in a US state map |
| `derived/geo/places.sqlite` | 2.0 MB | `8dcb17a9…f1ed` | 11 municípios and 54 freguesias from the CAOP, 25 postcode areas (the CP4 prefixes) and 10,483 street names from the addresses, 959 named OpenStreetMap places and 1,256 named points |
| `derived/geo/addresses/PT-30.sqlite` | 12.4 MB | `595b0dad…d0e5` | 88,218 indexed addresses, `meta.norm = pt-1` |
| `map-set.json` | 189 B | `a873469b…d331` | the file list and sizes, as every map set carries |

Full checksums are in `data/build.json`, which also records every source (URL, dated file name, data date, licence,
size, SHA-256).

Every place in the place finder answers through the app in `--data` mode: "Funchal" returns the CAOP
município, the OpenStreetMap city and the four CAOP freguesias; "9050" returns the postcode area.

## The pt-1 rule

Portuguese street names in the INE register are uppercase with an abbreviated leading type (`R DE SANTA
MARIA`, `CAM S JOSE`, `ESTR DOMINGOS D ORNELAS`), and many carry accents. `pt-1` folds the accents, lowercases,
collapses spaces, expands the leading street type (`R`→`rua`, `CAM`→`caminho`, `ESTR`→`estrada`, `AV`→
`avenida`, `TV`→`travessa`, `BC`→`beco`, `LG`→`largo`, `ER`→`estrada regional`, and the rest of the ~30 types
the Madeira rows carry) and the name abbreviations in any position (`S`→`sao`, `STA`→`santa`, `STO`→`santo`,
`D`/`DA`/`DO`→`de`, `DR`→`doutor`, `CMDT`→`comandante`). `R DE SANTA MARIA`, `Rua de Santa Maria` and
`r de santa maria` then share one key, as do `CAM S JOSE` and `Caminho São José`. Separated accents compose
first (NFC), so a Mac or iOS paste of `São` with the tilde as its own character folds the same way, as `de-1`
does. The house label keeps the register's spelling: a plain numeral carrying a non-zero digit loses its
leading zero (`007` becomes `7`), while composite labels (`0E`, `013A`, `5 1J`) and an all-zero label
(`000`) stay as written, so what a door shows is what a query finds. The
rule lives in the builder and travels to the runtime with the index; nothing in the US search path changes.

The expansions do real matching work: the register's `ER 222` rows (626 of them) share a key with
OpenStreetMap's `Estrada Regional 222`, and `ESTR S JOÃO` with `Estrada São João`.

## What the build lacks

- **Help points come from OpenStreetMap only.** Berlin's build replaced four kinds with an official register;
  Portugal has no equivalent national register with terms the pilot could confirm, so hospitals, pharmacies,
  police and fire stations are OSM points here and the map's `help_points` meta says so. A register with clear
  terms (e.g. for pharmacies) is the one thing that would upgrade this build later.
- **The base map.** `national.sqlite` covers the US only; Madeira draws from the detailed map once you zoom in
  past the base map, as with every regional build so far (#31, Berlin, FR-BN).
- **Address search through the app.** The sidecar opens with `--data` today; installing it from Setup and
  searching it needs the shared regional address-index work tracked in #31. The fixtures below are the check.
- **Terrain, crops and the water inventory.** The US sources do not apply; Portugal replacements are listed in
  REGIONS-PT.md ("What was checked, and what was not") and stay out of this first build.

## Data quirks, measured

These are properties of the INE register worth knowing before using the index:

- **42,053 of the 130,271 rows have no usable house number**: 36,272 rural doors registered without one
  (sítios and caminhos mostly), and 5,781 more that a number-first index cannot take — a word where the number
  goes (`BL`, `B`) or no street name at all. They stay out of the address index and are counted; their streets
  still appear in the place finder, which is the way to find them today.
- **The street field sometimes carries a building descriptor**: `AV ARRIAGA CONJUNTO MONUMENTAL INFANTE` is one
  street (31 rows, all with number 75). And the house field carries floor and door forms on the rows the index
  keeps (`5 1J`, `5A`, `11 B`, `0E`) — both are kept verbatim; the future search rule reads the number it leads with.
- **Some central streets share one geocoded point** across what look like distinct doors (`AV ARRIAGA`
  501/506/508 all carry −16.91222, 32.64674), and some numbers look postal rather than real (a central avenue
  numbered 501+). The register is what it is; the index reproduces it and the doc says so.
- **Street names start with a digit occasionally** (`1 VEREDA JOÃO GONÇALVES ZARCO`), and freguesia names carry
  a município disambiguator (`SEIXAL PMZ`). Both are kept as written.
- **Postcodes are stored without the hyphen** (`9000-077` becomes `9000077`) in the index; the place finder's
  postcode areas are the CP4 prefixes people search. The hyphen issue REGIONS-PT.md noted for the Overture
  builder is handled at the source here.
- **Freguesias that span islands need an anchor.** Funchal (Sé) holds downtown Funchal and the Selvagens,
  which are larger in land area and richer in coastline vertices than the downtown ring they belong with, so
  neither vertex count nor polygon area picks the right ring; the build centres each freguesia on the ring
  nearest its município's centroid, and all ten of Funchal's freguesias land in the city.

## Offline search check

`check` runs without the network and exits non-zero on any failure: SHA-256 of every output as built, SQLite
integrity, road and help-point counts, every help point inside the box plus the 0.15° margin, the address
arithmetic (88,218 indexed + 42,053 without a number = the 130,271 REGIONS-PT.md measured), every address
inside the official box with a 9000–9400 postcode, the pt-1 keys against the rule on a 500-row sample, the
house labels against the register's forms (nothing reduced to a fragment, no plain numeral still padded), and
the place finder answering for a município, a freguesia and a postcode. The place finder was also exercised
through the running server in `--data` mode ("Funchal", "Câmara de Lobos", "9000").

Address fixtures for the future runtime path — each is a register row whose point sits on the OpenStreetMap
road of the same name in the built map, within 10–35 m of it (proximity queries against `national.sqlite`,
22 November 2026), so no claim rests on one dataset. The same expectations live as
`app/tests/fixtures/pt_30_queries.json` with the contract tests in `app/tests/test_build_region_pt_30.py`,
in the `de_be_queries.json` form (#433): twelve verbatim rows of this index, the queries with their lookups, and
the rule that derives every expected answer from the rows, so `FixtureContractTests` fails if a row, a lookup
or an expectation stops following from what the file states:

| Query | Should find | Why it also tests the rule |
|---|---|---|
| `Estrada Monumental 221, 9000 Funchal` | `ESTR MONUMENTAL 221` | 1,094 rows share the street |
| `ER 222 221` (or `Estrada Regional 222 221`) | `ER 222 221` | `ER`→`estrada regional` |
| `Estrada São João 108` | `ESTR S JOÃO 108` | `S`→`sao` and the accent fold |
