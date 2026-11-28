# Detailed maps for Bolivia: a proposal

This is a proposal for discussion, not a decision. It answers, for Bolivia, the questions [MAPS.md](MAPS.md) asks before
coverage can go beyond the United States: which open source replaces each federal list, under what licence, what a
"state" is there, and how addresses are written. It follows the shape of [REGIONS-PY.md](REGIONS-PY.md),
[REGIONS-AR.md](REGIONS-AR.md) and [REGIONS-CL-DPA2023.md](REGIONS-CL-DPA2023.md) and is meant to feed the same design
discussion (issues #23, #25 and #31). The machine-readable version is
[regions-bo-proposed.json](regions-bo-proposed.json), and a Spanish translation is [REGIONS-BO.es.md](REGIONS-BO.es.md).

Nothing here changes the app, the engine or a build. No code reads the JSON, and nothing here ships: builds package
`web/` and `content/` only.

**How things were checked.** Research was done on 21 and 22 November 2026. Each fact carries one of these marks:

- **opened**: the page, file or API response itself was opened and read;
- **computed**: the figure was computed here from a downloaded file (the file and method are named);
- **search only**: the fact was seen in a search result, but the page itself was not opened;
- **general knowledge**: stated from memory, with no source opened; it needs a local reader's check;
- **not checked**: the page could not be reached or read; the row says what is missing.

"None found" means none found by web search. Several Bolivian government sites could not be reached from here on 21
November 2026: GeoBolivia (`geo.gob.bo`) and the Instituto Geográfico Militar (`igm.gob.bo`, `igmbolivia.gob.bo`) gave
no answer, and Defensa Civil (`defensacivil.gob.bo`) returned HTTP 403. What they hold is listed under "What was
checked, and what was not".

## What a region is

Bolivia has nine departments. The proposal is **one region for the whole country**, code `BO`, as REGIONS-PY.md proposes
for Paraguay and REGIONS-LK.md for Sri Lanka, with the nine departments as the alternative if finer regions are wanted.

Why one region:

- **Size of the download.** Geofabrik's whole-country extract is 167 MB (opened), a little more than Paraguay's 147 MB,
  which REGIONS-PY.md proposes as one region, and half of Chile's 352 MB.
- **The departments are very unequal.** Santa Cruz is 368,779 km² and Tarija 37,259 km² (COD-AB `area_sqkm`, below):
  Santa Cruz alone is a third of the country and close to the whole of Paraguay (399,603 km² in the same dataset family,
  from REGIONS-PY.md). A department split gives one very large map and several small ones.
- **How people move** (general knowledge). The main road corridor La Paz – Oruro – Cochabamba – Santa Cruz crosses four
  departments, and the Altiplano departments (La Paz, Oruro, Potosí) share one high plateau. Someone travelling along it
  would need several department maps.

The case for departments is stronger here than in Paraguay: each of the largest cities lies well inside its own
department (La Paz and El Alto in La Paz, Santa Cruz de la Sierra in Santa Cruz, Cochabamba in Cochabamba; general
knowledge), so a department map would not cut a metropolitan area in two. If the maintainers prefer departments, the
boxes are listed below.

### Codes

- **`BO` for the whole country.** A bare `BO` is not in `STATE_CODES` (`engine/address_search.py`), so it collides with
  no US state code, the same check REGIONS-PY.md made for `PY`.
- **ISO 3166-2:BO for the departments**: one letter after the hyphen (`BO-L` La Paz, `BO-S` Santa Cruz and so on), not a
  number as in Paraguay or Chile. The hyphenated form avoids any clash with `STATE_CODES`; [MAPS.md](MAPS.md) notes the
  manifest already accepts map ids such as `DE-BE`.
- **Where the codes come from.** The ISO site itself (`iso.org/obp`) returned HTTP 403, so the codes are **not checked
  against ISO**. Four other sources were opened and all give the same nine codes for the same departments. Debian,
  UN/LOCODE and Natural Earth name `BO-B` "El Beni"; geoBoundaries and OCHA's COD-AB say "Beni". The four sources:
  - Debian's `iso-codes` package, version 4.16.0 (`iso_3166-2.json`, which follows ISO 3166-2);
  - the UN/LOCODE subdivision list, read through the `datasets/un-locode` mirror on GitHub
    (`data/subdivision-codes.csv`, refreshed from UNECE on 16 October 2026). UNECE's own pages showed a Cloudflare
    challenge;
  - the `iso_3166_2` field of Natural Earth 5.1.1 admin-1;
  - the `shapeISO` field of geoBoundaries' BOL ADM1 file.
- **Watch the order.** OCHA's p-codes number the departments `BO01` to `BO09` in a different order from the ISO letters
  (`BO01` is Chuquisaca, `BO-H`; `BO02` is La Paz, `BO-L`). Anything joining the two must join by name, not by position.

### Boxes

The boxes were computed from OCHA's Common Operational Dataset of administrative boundaries (COD-AB) for Bolivia,
`bol_admin0.geojson` and `bol_admin1.geojson` from `bol_admin_boundaries.geojson.zip` (version `v02`, `valid_on` 16
September 2024, files last modified 13 May 2026; downloaded and computed on 21 November 2026). Each box is the extent of
every vertex of the unit, then minus/plus 0.15° and rounded outward to 0.01° (floor for west and south, ceiling for east
and north), the same margin `map_sets.state` uses for US states (`derived/packs/pack-spec.json`: "box = ZCTA centroids
in profiles.sqlite, plus or minus 0.15 degrees"). Seven departments are a single polygon; La Paz has 27 parts (it takes
in islands in Lake Titicaca; general knowledge) and Oruro two. Every part counts toward the box.

| Code | Name | Box (west, south, east, north) | Box with 0.15° margin | Area (km², `area_sqkm`) |
|---|---|---|---|---|
| `BO` | Bolivia | -69.6452, -22.9066, -57.4544, -9.6696 | -69.80, -23.06, -57.30, -9.51 | 1,081,700 |

The COD-AB area is the dataset's own attribute. Bolivia's official area is usually given as 1,098,581 km² (general
knowledge); the difference was not investigated. Geofabrik's clipping polygon (`bolivia.poly`, opened, 161 vertices)
gives a looser box, -69.6568, -22.9255, -57.4348, -9.6387, as expected for a polygon drawn around the border.

| ISO code | COD-AB p-code | Name | Box (west, south, east, north) | Box with 0.15° margin | Area (km², `area_sqkm`) |
|---|---|---|---|---|---|
| `BO-H` | BO01 | Chuquisaca | -65.6956, -21.5173, -62.1794, -18.3470 | -65.85, -21.67, -62.02, -18.19 | 50,945 |
| `BO-L` | BO02 | La Paz | -69.6452, -18.0469, -66.7321, -11.8497 | -69.80, -18.20, -66.58, -11.69 | 128,255 |
| `BO-C` | BO03 | Cochabamba | -67.0057, -18.6818, -64.2341, -15.7799 | -67.16, -18.84, -64.08, -15.62 | 54,450 |
| `BO-O` | BO04 | Oruro | -69.1423, -19.8867, -66.0861, -17.3239 | -69.30, -20.04, -65.93, -17.17 | 52,194 |
| `BO-P` | BO05 | Potosí | -68.7739, -22.9066, -64.7144, -17.8071 | -68.93, -23.06, -64.56, -17.65 | 119,207 |
| `BO-T` | BO06 | Tarija | -65.4199, -22.8828, -62.2607, -20.8858 | -65.57, -23.04, -62.11, -20.73 | 37,259 |
| `BO-S` | BO07 | Santa Cruz | -64.8424, -20.4732, -57.4544, -13.4757 | -65.00, -20.63, -57.30, -13.32 | 368,779 |
| `BO-B` | BO08 | Beni (ISO: El Beni) | -67.5622, -16.4917, -61.5279, -10.3812 | -67.72, -16.65, -61.37, -10.23 | 206,875 |
| `BO-N` | BO09 | Pando | -69.5747, -12.4984, -65.2868, -9.6696 | -69.73, -12.65, -65.13, -9.51 | 63,737 |

**Lakes and salt flats.** OCHA's dataset notes that levels 2 and 3 (provinces and municipalities) leave seven water
features as holes, among them the Salar de Uyuni, the Salar de Coipasa, Lago Titicaca, Lago Poopó and Lago Uru Uru,
while levels 0 and 1 enclose them (opened, HDX record). The boxes above come from levels 0 and 1, so they include these
features. A box taken from a province or municipality could stop at a lake shore.

**Boundaries that are not settled.** Ley 339 of 2013 (opened, on Lexivox) distinguishes "límites precisos" from "límites
imprecisos", those "que no han sido definidos en la norma o que habiéndolo sido, carecen de coordenadas", and sends
demarcation to the IGM case by case. So department lines in any dataset are approximate in places, as REGIONS-AR.md and
REGIONS-CL-DPA2023.md say of their own internal limits. A box is only a cut for a download; it should not be read as a
statement about where a department ends.

### Cross-checks

| Source | Licence | Result | Mark |
|---|---|---|---|
| geoBoundaries gbOpen BOL ADM0 and ADM1 (source "GeoBolivia, Derived from ADM3 layer", year represented 2015, built 12 December 2023) | "Public Domain" as geoBoundaries records it | Every box is the same as COD-AB's to four decimals (unrounded, the extents differ by less than 0.000001°). The two files appear to share the same underlying geometry, so this is **not an independent check** (an inference from the match; the provenance of either file was not traced). Same nine ISO codes. | opened, computed |
| Natural Earth 5.1.1, 10 m admin-0 and admin-1 | Public domain (terms page opened) | Different, generalised lines. The largest difference on any edge is 0.0914° (Tarija's west edge, about 9 km); the country box differs by at most 0.0213° (west edge). **Every Natural Earth department box lies inside the COD-AB box with margin**, so the margin absorbs the difference. | opened, computed |
| Geofabrik `bolivia.poly` | ODbL (with the extract) | Looser than COD-AB on all four sides, by 0.01° to 0.03°. | opened, computed |

Largest edge difference between Natural Earth and COD-AB, per department (computed; kilometres are rough, at the
department's middle latitude): Chuquisaca 3.3 km, La Paz 6.1 km, Cochabamba 8.9 km, Oruro 8.5 km, Potosí 5.3 km, Tarija
9.4 km, Santa Cruz 3.7 km, Beni 7.1 km, Pando 1.1 km.

### Neighbours inside the boxes

A rectangle around Bolivia holds a lot of its neighbours. The shares below were computed by sampling each box with
margin on a 0.02° grid and looking up each point in Natural Earth's 10 m admin-1 polygons (computed; Natural Earth is
generalised, so treat these as approximate). They are shares of the box, not of the area in km².

| Box | Bolivia | Other countries in the box (largest units) |
|---|---|---|
| `BO` | 54.5% | Brazil 26.8% (Mato Grosso, Rondônia, Acre, Mato Grosso do Sul), Paraguay 9.4% (Alto Paraguay, Boquerón, Presidente Hayes), Chile 4.1% (Antofagasta, Tarapacá, Arica y Parinacota), Argentina 2.6% (Salta, Jujuy), Peru 2.5% (Puno, Madre de Dios) |
| `BO-H` Chuquisaca | 97.2% | Paraguay 2.8% (Boquerón) |
| `BO-L` La Paz | 79.5% | Peru 19.0% (Puno, Madre de Dios), Chile 1.5% (Arica y Parinacota) |
| `BO-C` Cochabamba | 100% | none |
| `BO-O` Oruro | 90.2% | Chile 9.8% (Tarapacá, Arica y Parinacota) |
| `BO-P` Potosí | 79.2% | Chile 10.9% (Antofagasta, Tarapacá), Argentina 9.9% (Jujuy, Salta) |
| `BO-T` Tarija | 56.1% | Argentina 36.5% (Salta, Jujuy, Formosa), Paraguay 7.4% (Boquerón) |
| `BO-S` Santa Cruz | 69.9% | Brazil 22.0% (Mato Grosso, Mato Grosso do Sul, Rondônia), Paraguay 8.1% (Alto Paraguay, Boquerón) |
| `BO-B` Beni | 75.6% | Brazil 24.4% (Rondônia) |
| `BO-N` Pando | 61.3% | Brazil 31.3% (Acre, Rondônia, Amazonas), Peru 7.4% (Madre de Dios) |

The Bolivian share of each department box also includes neighbouring Bolivian departments; that split was not computed.
The same overlap appears from the other side: REGIONS-PY.md notes that Paraguay's box takes in parts of south-east
Bolivia, and REGIONS-CL-DPA2023.md that Chile's northern region boxes take in Bolivian territory.

As for Paraguay, Geofabrik's extract is already cut a few kilometres outside the border, so a first build from it holds
almost nothing of the neighbours. Several towns have a twin across the border (general knowledge): Desaguadero on both
sides of the Peruvian border at Lake Titicaca, Puerto Quijarro and Corumbá (Brazil), Guayaramerín and Guajará-Mirim
(Brazil), Cobija and Brasiléia (Brazil), Villazón and La Quiaca (Argentina), Yacuiba and Salvador Mazza (Argentina).
Lake Titicaca itself is shared with Peru (general knowledge). The suggestion, as for Paraguay, is to keep the border as
the edge of a first build and decide later whether to add a band from the neighbours' extracts.

## Sources, layer by layer

OpenStreetMap is the backbone for a first build, as for Paraguay. OCHA's COD-AB gives the administrative units down to
municipalities. No open national lists of health facilities, fire stations or shelters were found, and Overture has no
Bolivian addresses.

| Layer (file) | US source today | Proposed for Bolivia | Publisher | Licence | Mark |
|---|---|---|---|---|---|
| Roads, water, land (base map) | OSM extract | OSM extract `bolivia-latest.osm.pbf` (167 MB as Geofabrik shows it; the dated `bolivia-261120.osm.pbf` is 175,175,057 bytes, about 167 MiB; the `-free.shp.zip` is 396 MB and the `-free.gpkg.zip` 405 MB) | OSM contributors via Geofabrik | ODbL 1.0 | opened |
| Points of interest (`poi`) | OSM | OSM (counts below) | OSM contributors | ODbL 1.0 | computed |
| Places (`places.sqlite`) | GNIS, Census gazetteers, OSM | OCHA COD-AB levels 1 to 3 (9 departments, 112 provinces, 339 municipalities) and its `adminpoints` file; OSM named places | OCHA, source "Ministerio de Desarrollo Rural y Tierras"; OSM contributors | CC BY-IGO; ODbL 1.0 | opened (HDX record); computed (unit counts from the GeoJSON) |
| Terrain (`terrain.sqlite`) | USGS 3DEP | Copernicus DEM GLO-30, as proposed for Guyana | ESA / Airbus | Copernicus WorldDEM-30 licence | as in REGIONS.md; Bolivia tile coverage not checked |
| Water (`water.sqlite`) | NHD | OSM waterways and water areas | OSM contributors | ODbL 1.0 | not checked beyond OSM |
| Dams | NID | OSM `waterway=dam` and `water=reservoir`; no open dam inventory found | OSM contributors | ODbL 1.0 | computed |
| Crops (`crops.sqlite`) | USDA Cropland Data Layer | Not studied in this proposal. ESA WorldCover (CC BY 4.0) is the fallback other proposals name | | | not checked |
| Buildings (`buildings.sqlite`) | Microsoft US footprints, OSM heights | Google Open Buildings v3 ("BOL Bolivia" is in its country list, which it says is "subject to change"); Microsoft Global ML Building Footprints (238 Bolivia tiles in `dataset-links.csv` of 12 November 2026) | Google; Microsoft | CC BY 4.0 or ODbL 1.0, at the user's choice (Google); CDLA Permissive 2.0 (Microsoft) | opened; coverage and quality not measured |
| Addresses (`addresses/<code>.sqlite`) | Overture addresses | **None found.** Overture's address theme (release 2026-11-18.0) lists 41 countries, and Bolivia is not among them. Only OSM `addr:*` tags remain (counts below) | | | opened |

### Help and resource points

Counts were made with pyosmium over Geofabrik's dated extract `bolivia-261120.osm.pbf` (175,175,057 bytes, MD5 matching
Geofabrik's published checksum; data up to 20 November 2026 21:21 UTC). Each count includes nodes, ways and relations
carrying the tag; "named" is how many of them also have a `name`.

| Kind | OSM tag | Count (named) | Other source | Mark |
|---|---|---|---|---|
| Hospitals | `amenity=hospital` | 907 (855); 455 of them tagged `emergency=yes`, 9 `emergency=no`, 442 with no `emergency` tag | HDX health records, see below | computed |
| Clinics and doctors | `amenity=clinic`, `amenity=doctors` | 851: 649 clinics (615), 202 doctors (182) | as above | computed |
| Pharmacies | `amenity=pharmacy` | 2,627 (2,297) | none found | computed |
| Fire stations | `amenity=fire_station` | 43 (41) | none found | computed |
| Police | `amenity=police` | 593 (514) | none found | computed |
| Drinking water | `amenity=drinking_water`, `man_made=water_tap`, `amenity=water_point` | 159 (88, 63, 8) | none found | computed |
| Wells, water towers and tanks | `man_made=water_well`, `water_tower`, `storage_tank` | 1,599 (75 wells, 591 towers, 933 tanks, contents not checked) | none found | computed |
| Reservoirs and dams | `water=reservoir`, `waterway=dam` | 4,402 reservoirs (`landuse=reservoir` not counted), 1,081 dams | none found | computed |
| Fuel | `amenity=fuel` | 714 (670) | none found | computed |
| Ambulance stations | `emergency=ambulance_station` | 8 (6) | none found | computed |
| Shelters and assembly points | `amenity=shelter`, `social_facility=shelter`, `emergency=assembly_point` | 941 (922, 9, 10) | none found | computed |
| Schools | `amenity=school` | 9,806 (9,091) | none found | computed |

Notes:

- **A count of rows is not a count of places.** As REGIONS-PY.md found for Paraguay, OSM often has one hospital as a
  point and again as its buildings. The counts above are upper bounds; no grouping by distance was done for Bolivia.
- **Fire stations.** OSM has 43. How complete that is was not checked: no published list of fire station locations was
  found to compare with.
- **"Shelter" in OSM.** `amenity=shelter` marks small roofs, not emergency shelters. Of the 922 in Bolivia, by
  `shelter_type` (computed): 185 weather shelter, 171 with no type, 163 public transport, 147 gazebo, 138 picnic
  shelter, 73 sun shelter, and 45 with other or malformed values. They should not be drawn as emergency shelters.
- **Health tags.** 849 objects carry `healthcare=hospital` and 47 `healthcare=centre`; these overlap with the `amenity`
  counts and were not de-duplicated.

Other sources for help points:

- **Health.** The Ministry of Health's own facility list was not found as a download. HDX has three Bolivian health
  records (opened through HDX's API): `hotosm_bol_health_facilities` (HOT, from OSM, ODbL, updated 16 November 2026),
  `bolivia-healthsites` (healthsites.io, from OSM, ODbL, updated 29 September 2026), and `bolivia-health` (source
  "Ministerio de Salud y Deportes", licence "Other", last updated 16 August 2018). The first two are OSM data already in
  the extract. The third is old and its terms are unclear; it should not be used without asking. The Ministry's health
  information system (`snis.minsalud.gob.bo`) was not checked.
- **Fire, police and shelters.** No open national list was found. In Bolivia the fire service is part of the Policía
  Boliviana (search only).

### Hazards

- **SENAMHI** (Servicio Nacional de Meteorología e Hidrología), `senamhi.gob.bo`, opened. The home page links to
  "Alertas Hidrologicas", "Manchas de Inundacion ACRE", "Focos de Calor", "Monitor de Sequias" and "Aviso Meteorologico
  para la Emision de Alerta", and to "Contacto y Solicitud de Datos". Its "Términos y condiciones de uso" link points
  nowhere (`#`), and every page opened ends with "© Copyright 2026 | Derechos Reservados SENAMHI". **No open licence was
  found**, so under the rule REGIONS-AR.md uses ("a dataset with no stated licence is treated here as not yet usable")
  these need SENAMHI's permission. The alert pages are drawn by JavaScript and their data were not read.
- **Defensa Civil (VIDECI)**, `defensacivil.gob.bo`: HTTP 403, **not checked**.
- **What the hazards are** (general knowledge, for a Bolivian reader to confirm): floods in the lowlands of Beni, Pando
  and Santa Cruz; forest and grass fires, often from land clearing (*chaqueo*), in Santa Cruz and Beni; mudflows
  (*mazamorras*) and landslides in La Paz; drought, frost and hail on the Altiplano. High altitude is a health hazard in
  itself in La Paz, El Alto, Oruro and Potosí; no guide covers it today, and that would be a separate content task.

## Licence notes and attribution

- **CC BY-IGO** (OCHA's COD-AB, opened through HDX's API). Credit OCHA and its source, the Ministerio de Desarrollo
  Rural y Tierras.
- **ODbL 1.0** (OSM, and the two OSM-based health records on HDX): as for the US map.
- **CC BY 4.0 or ODbL 1.0** (Google Open Buildings): the user picks one (opened).
- **CDLA Permissive 2.0** (Microsoft footprints downloaded from its dataset list): a pack that shares them must make the
  text of the licence available with them, as REGIONS-CL-DPA2023.md notes.
- **geoBoundaries** records its Bolivia files as "Public Domain; free use and access to information", citing a
  GeoBolivia metadata record that could not be reached. Used here only as a cross-check.
- **Natural Earth**: public domain (terms opened). Used here only as a cross-check.
- **INE Bolivia** (Instituto Nacional de Estadística). Its terms of use (opened; "Términos y condiciones de uso (TCU)
  del portal del Censo 2024", last updated 25 August 2025) are not an open licence. They say: "No se permite utilizar
  los datos con fines comerciales sin autorización previa del INE o sin respetar la fuente y contexto originales", and
  "Toda reproducción o redistribución debe mencionar la fuente completa en la siguiente forma: Fuente: Instituto
  Nacional de Estadística." They also say "El INE no tiene competencias en materia de límites de unidades
  territoriales." Whether the commercial clause would bind a free pack that someone else could resell is the same
  question REGIONS-AR.md raises for IGN Argentina. No INE layer is proposed here.
- **SENAMHI**: all rights reserved (above).
- **Copernicus WorldDEM-30**: as in REGIONS.md.

### Publishing a map of Bolivia: an open question

Chile has DIFROL's legend rule (REGIONS-CL-DPA2023.md); for Bolivia **no comparable rule was found, but the search was
incomplete**, so this is left as a question for the maintainers, not an answer.

- **Internal limits.** Ley 339 of 2013 (opened on Lexivox, an unofficial copy) says in Art. 23: "La cartografía oficial
  es aquella elaborada por el Instituto Geográfico Militar"; Art. 16 says the IGM demarcates units but "no define la
  delimitación de unidades territoriales". Nothing read in it requires a private map to carry a legend or be approved.
  DS 5050 of 2023 (opened on Lexivox in an earlier pass the same day) approves the boundary layer held by the
  Viceministerio de Autonomías and sends limits to the IGM for demarcation; nothing in it about private maps was seen
  either.
- **The IGM's own terms** could not be read: its sites did not answer.
- **The border with Chile and the sea claim.** Bolivia keeps a claim to access to the Pacific (general knowledge); the
  International Court of Justice ruled in 2018 that Chile has no obligation to negotiate it (general knowledge, not
  checked). A web search found no Bolivian rule that a published map must show the former Litoral department or the
  claim (search only). The office that led the claim, the Dirección Estratégica de Reivindicación Marítima, Silala y
  Recursos Hídricos Internacionales, was closed by DS 5376 of 16 April 2025 (opened on Lexivox).
- **What Lastbook draws today.** The world base map already draws country outlines (`web/world-context.json`) and
  credits Natural Earth (`MAP_CREDIT` in `packaging/build_packs.py`). A Bolivia pack built from OSM would draw the
  border as OSM has it. Whether that needs any wording in the app, for Bolivia or for Chile, is for the maintainers.

## Emergency numbers

The number table belongs to [issue #261](https://github.com/Immortal-Protocols/lastbook/issues/261), not to this map
proposal, and in #235 the owner's review asked that a bare number that means different things in different countries
stay out of global guide search. This section only records what was found, so that the map and the number table agree
later. **No number here is proposed for the app.**

| Service | Number | What was found | Status |
|---|---|---|---|
| Police (Radio Patrullas) | 110 | The Policía Boliviana's site (`policia.bo`, opened 21 November 2026) shows "BOL 110" with a `tel:110` link and "110 - Radio Patrullas" in its footer. An undated Defensoría del Pueblo leaflet also lists "Radio Patrullas 110" (opened in an earlier pass the same day). | Bolivian sources agree |
| Fire (Bomberos) | 119 | The same `policia.bo` page shows "BOMBEROS 119" and "119 - Bomberos", but in the same block it also gives **119 for the FELCC** (crime investigation), while its footer gives "122 - FELCC". | **Conflict on the official page**; open |
| Ambulance | 118, 165, 167, 168 | No current national source found. Candidates come from foreign travel advice, municipal pages and a 2019 Bolivian report (found in an earlier research pass the same day; not reopened); see #261 when Bolivia is taken up there. | **Not verified**; open |

Bolivia has no single number for every service in these sources. The ATT (the telecoms regulator) would be the decisive
source for the numbering plan; no list of emergency short codes was found on its site (earlier research pass).

## How addresses are written

Not checked against any Bolivian postal or municipal source. This part needs a Bolivian reader's review.

- **Order** (general knowledge). Street, then number, then the zone or neighbourhood (*zona*, *barrio*) and the city:
  "Calle X Nº 123, Zona Y, La Paz". As in Argentina and Paraguay, the number comes after the street, the opposite of the
  order `engine/address_search.py` expects. Many homes have no number ("s/n").
- **Postal codes** (general knowledge, not checked): not in everyday use. `engine/address_search.py` reads a postcode
  only as five digits, so this should not matter, but it was not tested.
- **No Overture addresses** (opened, above). Address search would rely on OSM `addr:*` tags alone. In the extract above,
  10,527 objects carry `addr:housenumber` and 56,144 `addr:street` (computed). Of the 10,475 house numbers that could be
  placed (nodes, and ways by their first node), 4,581 are in La Paz, 2,939 in Cochabamba, 2,282 in Santa Cruz and 629 in
  the other six departments together (44 fall just outside COD-AB's outline). That is far too few for address search
  across the country.
- **Accents.** `normalize()` in `engine/address_search.py` keeps only `a-z`, `0-9` and spaces, so "Potosí" becomes
  `potos` and "Calle Ñuflo de Chávez Nº 123" becomes `calle uflo de ch vez n 123` (tested 22 November 2026), the same
  problem REGIONS-PY.md and REGIONS-DE.md describe. Folding is needed on both sides;
  #79 proposes that each index declares its own rule.

So a first Bolivian map would most likely ship as "street map, places and help points" without address search, as
suggested for Paraguay and Sri Lanka.

## Language

Spanish is the main language of maps and signs; the constitution also recognises many indigenous languages, among them
Quechua, Aymara and Guaraní (general knowledge). In the extract, 143 objects carry `name:qu`, 125 `name:ay` and 25
`name:gn` (computed). Which name the map shows where they differ is part of the language question in issues #3 and #54.

## Still undecided

Each of these needs the maintainers' decision before any code changes.

1. **Codes in setup.** Whether `BO` is acceptable as a manifest `id`, in `map-set.json` and in `Lastbook-Map-BO.zip`,
   and, if departments are wanted, whether one-letter hyphenated codes such as `BO-L` are.
2. **One region or nine.** The whole country (proposed) or each department.
3. **The box rule.** Whether the border is the edge of a first build, and whether a band is added later for the twin
   towns and Lake Titicaca.
4. **Publishing the border.** Whether a pack that draws Bolivia's borders, and in particular the border with Chile,
   needs any wording, and whether someone should ask the IGM.
5. **Address search.** No open address source beyond OSM; number after the street; "s/n"; folding accents before
   matching. Without more data, a first map ships without address search.
6. **Help points with no open source**: health facilities, fire stations and shelters. Whether to ask the Ministry of
   Health for its list under an open licence, and whether OSM alone is enough for a first build.
7. **Hazard layers.** SENAMHI states no open licence; whether to ask it, and whether Defensa Civil publishes anything.
8. **Emergency numbers**: left to #261; the 119 conflict and the ambulance number need a Bolivian source first.
9. **The California-only layers.** As REGIONS.md item 7.

## What was checked, and what was not

- **Opened on 21 November 2026:** OCHA's COD-AB record for Bolivia through HDX's API (licence, source, dates, caveat,
  files); geoBoundaries' metadata for BOL ADM0 and ADM1; Natural Earth's terms of use; Geofabrik's Bolivia page and
  `bolivia.poly`; Overture's addresses guide (release 2026-11-18.0); Google's Open Buildings page; Microsoft's footprint
  README and its `dataset-links.csv` of 12 November 2026; HDX's three Bolivian health records; INE's terms of use;
  SENAMHI's home page and three of its sub-pages; `policia.bo`; Ley 339 and DS 5376 on Lexivox; Debian's `iso-codes`
  4.16.0 file; the `datasets/un-locode` subdivision list; issue #261 (no Bolivian entry).
- **Opened in an earlier research pass the same day** and not reopened: DS 5050 on Lexivox; the Defensoría del Pueblo
  leaflet.
- **Downloaded and computed on 21 and 22 November 2026:** the COD-AB GeoJSON (country and department boxes, areas from
  `area_sqkm`, unit counts 9 / 112 / 339); geoBoundaries' BOL ADM0 and ADM1 GeoJSON; Natural Earth 5.1.1 10 m admin-0
  and admin-1 (boxes, and the neighbour shares on a 0.02° grid); Geofabrik's `bolivia.poly` (extent); Geofabrik's
  `bolivia-261120.osm.pbf` (the OSM counts, with pyosmium; house numbers split by COD-AB department).
- **Search only:** that the fire service is part of the Policía Boliviana; that no Bolivian rule requires maps to show
  the sea claim.
- **General knowledge**, for a Bolivian reader to confirm: the official area, where the main cities lie, the road
  corridor, the twin towns, the hazards, the address order and postal codes, the languages, the sea claim and the 2018
  ICJ ruling.
- **Not checked:** the ISO site (HTTP 403); UNECE's own UN/LOCODE pages (Cloudflare challenge); GeoBolivia and the IGM
  (no answer); Defensa Civil (HTTP 403); the Ministry of Health's information system; the ATT numbering plan; the
  Copernicus DEM's Bolivian tiles; crop and land cover sources; building coverage and quality; any national ambulance
  number.
