# A detailed map of La Paz department (`BO-L`): how it is built and what it holds

A worked example in Bolivia for the region map builder proposed in pull request #80, after its Bangkok example and
the Santiago example in #393, built with that tool unchanged. It maps the department of La Paz with the box from
[REGIONS-BO.md](REGIONS-BO.md), to test that box against a real build.

**A prototype dependency.** The builder is a prototype from pull request #80, which is still open. It is not in the
main branch. This map was built and checked with #80 at commit
[`a453274`](https://github.com/AngryAnt3201/lastbook/blob/a453274353b2816b4ccb0114310024ea54c970b2) (AngryAnt3201/lastbook, branch `map/bangkok-th-10`). The files used, at that commit:

- [`tools/build_region_map.py`](https://github.com/AngryAnt3201/lastbook/blob/a453274353b2816b4ccb0114310024ea54c970b2/tools/build_region_map.py), the builder
- [`tools/check_region_map.py`](https://github.com/AngryAnt3201/lastbook/blob/a453274353b2816b4ccb0114310024ea54c970b2/tools/check_region_map.py), the checker
- [`tools/test_build_region_map.py`](https://github.com/AngryAnt3201/lastbook/blob/a453274353b2816b4ccb0114310024ea54c970b2/tools/test_build_region_map.py), its tests
- [`docs/MAP-TH-10.md`](https://github.com/AngryAnt3201/lastbook/blob/a453274353b2816b4ccb0114310024ea54c970b2/docs/MAP-TH-10.md), the Bangkok example and the builder's notes

If #80 changes, or is merged in another form, the build and the checks here need to be run again.

It adds no code and no app change. The map is not downloaded by setup and is not in any pack.

## Why La Paz

REGIONS-BO.md proposes one region for the whole country, `BO`, with the nine departments as the alternative. This
map tests the alternative on one department. La Paz was chosen over Santa Cruz, the other large city:

- **Size.** La Paz is 128,255 km² by REGIONS-BO.md's figures; Santa Cruz is 368,779 km², a third of the country,
  and its box holds 22% Brazil. A department map is meant to be the small option.
- **One metropolitan area.** La Paz and El Alto, the seat of government and the largest urban area of the
  Altiplano, lie well inside the department, as REGIONS-BO.md notes, so the cut does not split a city.
- **It tests the hard parts of the box.** The box crosses Lake Titicaca and the Peruvian border, takes in a piece of
  Chile, and runs from the Altiplano down to the Amazon lowlands.

## The id and the box

- **Id.** `BO-L` is the department's ISO 3166-2 code, as REGIONS-BO.md gives it (one letter after the hyphen). The
  id is the maintainers' to change.
- **Box.** `-69.80, -18.20, -66.58, -11.69` (west, south, east, north): REGIONS-BO.md's COD-AB box with the 0.15°
  margin. Unpadded, the COD-AB box is `-69.6452, -18.0469, -66.7321, -11.8497`. OpenStreetMap's own boundary for the
  department (relation 400473, tagged `ISO3166-2=BO-L`, `admin_level=4`, in this extract) spans
  `-69.6450, -18.0442, -66.7324, -11.8478`, so the two agree to within 0.003°, and the padded box clips nothing of
  the department.
- **What the rectangle holds.** REGIONS-BO.md measures the box as 79.5% Bolivia, 19.0% Peru and 1.5% Chile. The
  Bolivian part also takes in the north of Oruro, with the city of Oruro, and the west of Beni, with Rurrenabaque and
  San Borja. Measured against OpenStreetMap's department polygon: 85.9% of help points (9,742 of 11,339), 82.4% of
  building outlines, 83.0% of roads and 69.0% of place labels are inside the department.
- **The Peruvian and Chilean parts are blank.** Geofabrik's Bolivia extract ends near the border, so no help point
  lies west of -69.50 and the app is told the map ends there. Lake Titicaca is drawn whole, on both sides of the
  border, because it is one water area that crosses the box. A few features that cross the box edge are kept whole
  (86 reach more than 0.05° past it; the furthest reaches -70.04).

## Build it

The build machine needs Python 3.11 or later and pyosmium. Nothing else is installed, and the tool downloads nothing.
Geofabrik offers Bolivia only as one country file (about 175 MB), so the department is cut from it by the box. Sizes
on this page are in MB, where 1 MB is 1,000,000 bytes.

There are two ways to build it. **Reproduce the recorded build** rebuilds this map from the same dated source file, with
#80 at the same commit, and checks the result against the checksums recorded under "The build this was checked with"
below. **A fresh build** makes the same map from today's data; its checksums and counts will differ.

The builder and checker are not in the main branch. Both ways start by taking them from #80 at the exact commit this
map was built with, into a checkout of this repository, without merging #80.

### Reproduce the recorded build

Run from the top of a checkout of this repository.

```bash
# 0. The prototype builder and checker from pull request #80 (still open), at commit a453274.
git fetch https://github.com/AngryAnt3201/lastbook.git a453274353b2816b4ccb0114310024ea54c970b2
git checkout FETCH_HEAD -- tools/build_region_map.py tools/check_region_map.py tools/test_build_region_map.py

# 1. The dated source this map was built from: Geofabrik's Bolivia extract with data up to 20 November 2026
#    (OpenStreetMap, ODbL 1.0), 175,175,057 bytes. Check it against Geofabrik's MD5 and the recorded SHA-256.
curl -LO https://download.geofabrik.de/south-america/bolivia/bolivia-261120.osm.pbf
curl -LO https://download.geofabrik.de/south-america/bolivia/bolivia-261120.osm.pbf.md5 && md5sum -c bolivia-261120.osm.pbf.md5
echo "de4b37089c5b31d37205a6ac3ae497c533c8c7df6911626a336e63034ac14c63  bolivia-261120.osm.pbf" | sha256sum -c

# 2. A build environment with the pyosmium version the recorded build used.
python3 -m venv derived/buildenv && derived/buildenv/bin/pip install osmium==4.3.2

# 3. Build. The box is BO-L's COD-AB box with the 0.15 degree margin, from REGIONS-BO.md.
#    Write --bbox=... with "=": the box starts with a minus sign, which argparse would otherwise read as an option.
derived/buildenv/bin/python tools/build_region_map.py bolivia-261120.osm.pbf \
    --id BO-L --name "La Paz" --bbox=-69.80,-18.20,-66.58,-11.69 --out derived/regions

# 4. Compare the five files with the recorded checksums. Every line should say OK.
(cd derived/regions/BO-L && sha256sum -c <<'EOF'
7ab010bd1c1854e0f84a7ddaed33d7a4b91c7993e4417cafae734c009f515127  derived/geo/national.sqlite
319ffec7ddd992142419bbde4dc3b53c8d05f779f96ca639e5a35a7872092c85  derived/geo/map.sqlite
b9ac19a406d6d3279e894f11cccc2a14a47b342e7c562b8f27c1527502a70343  derived/geo/places.sqlite
a99feb4a93464dc04a3fd142763c0c70eb5f89773f800383fad37aca523e3192  derived/geo/national-status.json
4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945  derived/geo/socal-cells.json
EOF
)

# 5. Check the files, then check that the engine can use them with every connection blocked.
python3 tools/check_region_map.py derived/regions/BO-L
python3 tools/check_region_map.py derived/regions/BO-L --engine \
    --find "El Alto" --find Sopocachi --find "Hospital de Clínicas" --find Copacabana --find Coroico \
    --find Charaña --find charana --find "hospital de clinicas" --near=-16.4955,-68.1336
```

The recorded build was made with Python 3.12.4 and SQLite 3.45.3 on Linux. Whether another SQLite version or platform
gives the same bytes was not tested; if step 4 fails there but step 5 passes and the counts in
`derived/regions/BO-L.build.json` match the tables below, the difference is most likely in how the files were written,
not in what they hold.

**If the dated file is no longer offered.** Geofabrik keeps only recent daily files. On 23 November 2026 its [Bolivia
folder](https://download.geofabrik.de/south-america/bolivia/) listed daily files for 12 to 22 November only, then the
first of each month back to September 2026, then 1 January of each year back to 2014. The folder page does not say how
long each is kept, so expect `bolivia-261120.osm.pbf` to drop out of that list within a few weeks. No other copy of the
file has been verified for this page. When it is gone, the recorded checksums cannot be reproduced: make a fresh build
(below), check it, and compare its counts with the tables below rather than its checksums. Anyone who kept a copy of the
file can still use it here: step 1's two checks tell whether it is the same file.

### A fresh build

From the latest data, which Geofabrik replaces every day. Run step 0 and step 2 above first. The builder will not
write over a map it has already built, so this build goes to its own folder.

```bash
# 1. The source: Geofabrik's latest Bolivia extract (OpenStreetMap, ODbL 1.0). About 175 MB.
curl -LO https://download.geofabrik.de/south-america/bolivia/bolivia-latest.osm.pbf
curl -LO https://download.geofabrik.de/south-america/bolivia/bolivia-latest.osm.pbf.md5 && md5sum -c bolivia-latest.osm.pbf.md5

# 2. Build, with the same options.
derived/buildenv/bin/python tools/build_region_map.py bolivia-latest.osm.pbf \
    --id BO-L --name "La Paz" --bbox=-69.80,-18.20,-66.58,-11.69 --out derived/regions-latest

# 3. Check the files, then check that the engine can use them with every connection blocked.
python3 tools/check_region_map.py derived/regions-latest/BO-L
python3 tools/check_region_map.py derived/regions-latest/BO-L --engine \
    --find "El Alto" --find Sopocachi --find "Hospital de Clínicas" --find Copacabana --find Coroico \
    --find Charaña --find charana --find "hospital de clinicas" --near=-16.4955,-68.1336
```

The checksums will not match the recorded ones, and the counts in `derived/regions-latest/BO-L.build.json` will move as
OpenStreetMap is edited. As a guide: a fresh build on 23 November 2026, from data up to 22 November, passed every check,
and every count was within 0.5% of the tables below (rivers and streams +0.45%, the rest +0.05% or less: 24,131 rivers,
162,839 roads, 5,959 places, 11,341 help points). Larger gaps after a longer time are normal; a layer that drops sharply
or a check that fails is worth a look.

### Look at it in the app

To look at it in the app's interface, give the engine a data folder that holds the map and an empty library:

```bash
mkdir -p /path/to/LaPazData/library-data && echo '[]' > /path/to/LaPazData/library-data/catalog.json
cp -R derived/regions/BO-L/derived derived/regions/BO-L/map-set.json /path/to/LaPazData/
python3 server.py --data /path/to/LaPazData --port 8890
# then open the address it prints, choose Map, and go to:  #/map?lat=-16.4955&lon=-68.1336&z=16
```

Geofabrik's Bolivia files sit under `south-america/bolivia/`; the older `south-america/bolivia-...` addresses
redirect there. The dated file is the same one REGIONS-BO.md was written from.

## The build this was checked with

| | |
|---|---|
| Source file | `bolivia-261120.osm.pbf` (from `https://download.geofabrik.de/south-america/bolivia/bolivia-261120.osm.pbf`), 175,175,057 bytes (175.2 MB). Served with `Last-Modified` 21 Nov 2026 01:11:23 GMT when downloaded, and 20 Nov 2026 23:32:40 GMT on 23 Nov, with the same size and MD5: check the file by its checksums, not by that date |
| Source SHA-256 | `de4b37089c5b31d37205a6ac3ae497c533c8c7df6911626a336e63034ac14c63` |
| Source MD5 (matches Geofabrik's `.md5`) | `a142ed996037a4005a68196ad154f036` |
| OpenStreetMap data up to | 2026-11-20T21:21:21Z (from the file's header) |
| Built on | 23 November 2026, Ubuntu 24.04.5 (Linux 7.0), Python 3.12.4, SQLite 3.45.3, pyosmium 4.3.2 from PyPI |
| Build time | 107 seconds, reading the whole country and keeping the box; peak memory 1.35 GB |
| Box | -69.80, -18.20, -66.58, -11.69 (west, south, east, north) |

| File | Bytes | SHA-256 |
|---|---|---|
| `derived/geo/national.sqlite` | 97,746,944 | `7ab010bd1c1854e0f84a7ddaed33d7a4b91c7993e4417cafae734c009f515127` |
| `derived/geo/map.sqlite` | 36,864 | `319ffec7ddd992142419bbde4dc3b53c8d05f779f96ca639e5a35a7872092c85` |
| `derived/geo/places.sqlite` | 1,847,296 | `b9ac19a406d6d3279e894f11cccc2a14a47b342e7c562b8f27c1527502a70343` |
| `derived/geo/national-status.json` | 59 | `a99feb4a93464dc04a3fd142763c0c70eb5f89773f800383fad37aca523e3192` |
| `derived/geo/socal-cells.json` | 2 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |

The map set is 99,631,165 bytes in all (99.6 MB). The files hold no build time, so the same extract and options give the
same bytes: a second build on the same machine (102 seconds) gave identical checksums for all five files. Running
"Reproduce the recorded build" above as written, on 23 November 2026 with the file downloaded again from Geofabrik, gave
the same five checksums again. Whether another SQLite version or platform gives the same bytes was not tested.

What the map holds:

| Layer | Features | | Layer | Features |
|---|---|---|---|---|
| Roads | 162,826 (28,223 with a name or number) | | Land use and parks | 19,672 |
| Building outlines | 103,171 | | Water areas | 8,881 |
| Rivers, streams and drains | 24,024 | | Wetland | 932 |
| Place labels | 5,956 | | Beaches | 46 |
| Railways | 212 | | Sea | none (the department is landlocked) |

Help points: 11,339 in 39 classes, 8,111 of them with a name. The largest: schools 2,461, parks 2,453, convenience
stores 1,148, pharmacies 1,033, communication towers 403, dentists 402, car repair 319, toilets 311, hospitals 278,
clinics 268, police 249. Emergency services: fire stations 11, police 249, hospitals 278, shelters 202, drinking
water 16, springs 30, water towers 69. The full list is in `BO-L.build.json`.

Inside the department itself (OpenStreetMap's polygon): hospitals 228, clinics 245, doctors 73, pharmacies 996, fire
stations 8, police 200, fuel 151, supermarkets 208, schools 1,893, shelters 185, drinking water 16.

The place finder has 14,067 rows: 5,956 places (8 cities, 12 towns, 23 suburbs, 14 quarters, 1,870 villages, 528
neighbourhoods, 3,413 hamlets, 88 localities) and 8,111 named help points. 109 rows carry a second name (`name:en`).

## What was checked, and how

The checker, `tools/check_region_map.py` from #80 at `a453274`, passed all 37 file checks and all 15 engine checks
on the build above. With `--engine`, every connection blocked and an empty library:

- **Map display.** Tiles at zoom 10, 13 and 16 around the Plaza Murillo: 2,017 roads in the zoom-10 tile, 301
  building outlines in the zoom-16 tile.
- **Pins.** 73 pin groups around the Plaza Murillo.
- **Nearest help.** A pharmacy at 0.04 km, a hospital (CIMFA Central - CNS) at 0.06 km, police at 0.09 km.
- **Place search, with and without accents.** "El Alto", "Sopocachi", "Copacabana" and "Coroico" find the city, the
  quarter and the towns; "Hospital de Clínicas" finds the hospital. "charana" and "hospital de clinicas", typed
  without ñ or accent, find Charaña and the Hospital de Clínicas: the place finder's index folds accents.
- **What the app is told.** 39 kinds, within -69.5, -18.19, -66.58, -11.69.

`tools/test_build_region_map.py` (from #80 at `a453274`): 9 tests pass with pyosmium.

**Lake Titicaca.** The lake is one water area in OpenStreetMap and is drawn whole at every zoom, including its
Peruvian half, with the Copacabana peninsula as land. The builder found no coastline, as expected, and
drew no sea.

It was also opened through `python3 server.py`, which serves the same `web/` interface the desktop app shows, in
headless Chrome with light and dark colour schemes. The map drew at city and street zooms and over the lake, and the
"Nearest to the map center" list filled in. The map itself has no dark style yet, as for the US maps: in dark mode
the interface around it turns dark and the map stays light.

**Not checked:** the packaged desktop app, Windows and macOS, and installing through setup (no installer or manifest
entry is part of this).

## What is and is not in it

**In it**

- Streets and paths of every class `tools/build_map.py` draws, with the same zoom rules, from the steep streets of
  La Paz and the grid of El Alto to the tracks of the Yungas and the lowlands.
- Lake Titicaca and the smaller Altiplano lakes, rivers and streams, wetland.
- Land use, parks, building outlines.
- Place labels and help points in the classes the engine already names (`HELP` in `server.py`).

**Not in it**

- **Addresses.** The tool does not build addresses, and `tools/build_addresses.py` is US-only. REGIONS-BO.md found
  no open address list for Bolivia. Roads are not in the place finder.
- **Terrain, contours and the 3D view**, **crops** and the **water and dam inventory**. In this department terrain
  matters most of all: La Paz lies in a canyon below El Alto, about 400 m higher (general knowledge), and the box runs
  from snow peaks to lowland forest.
- **The cable cars.** The builder reads no `aerialway` tags. The whole extract has 15 `aerialway=gondola` ways; La
  Paz and El Alto's cable-car network is a main way to cross the city (general knowledge), and it is not on the map.
- **Government lists.** No open national lists of health facilities, fire stations or shelters were found
  (REGIONS-BO.md). Every point here is from OpenStreetMap.
- **Emergency points the tool does not read.** In the box, OpenStreetMap has 6 `emergency=assembly_point`, 38
  `amenity=social_facility` (12 group homes, 4 shelters for people in need) and 123 features with a `healthcare=*`
  tag but not tagged as a hospital, clinic, doctor, dentist or pharmacy (36 laboratories, 53 `healthcare=yes`). The tool's classes do not include them. No ambulance station or
  defibrillator is mapped in the box.
- **Shelters as an emergency plan.** The 202 "shelter" points are OpenStreetMap structures. Of those in the box with
  a `shelter_type`, most are weather shelters and picnic shelters; many have no type at all. Bus shelters are left
  out. None is tagged as an emergency shelter.
- **Anything outside the box or outside the extract.** West of the border the map is blank, except Lake Titicaca.

**Known limits**

- **Hospital rows are mostly not hospitals.** Of the 278 rows, 68 have "hospital" in the name and 106 are named as a
  health centre or post ("Centro de Salud", "Puesto de Salud" and the like). OpenStreetMap tags many first-level
  health centres in Bolivia as `amenity=hospital`, so "nearest hospital" often names a place without an emergency
  ward. 14 have no name.
- **Fire stations are few.** 11 in the box, 8 in the department. This follows what OpenStreetMap has mapped, not
  what exists.
- **Every place's detail line says "La Paz"**, the `--name` given, including Oruro, Caracollo, Rurrenabaque, San
  Borja and Santos Reyes, which are in other departments. 7 of the 20 city and town labels are outside the
  department's polygon; Desaguadero's label is one of them, on the border.
- **Duplicates.** 333 named help points lie within 50 m of another with the same class and name, mostly where a
  place is mapped as a point and as an outline.
- **Completeness follows OpenStreetMap.** 3,228 help points have no name. Nothing was compared against an official
  count.
- **The page header's date** ("what was mapped by 25 Oct 2026") is fixed text for the US map; this map's date is in
  `meta` (`data_as_of`) and is not shown yet. The home view and the "US" button still point at the United States, and
  the map's credit line still lists the US sources (Microsoft buildings, USGS, USDA and others), though every row
  here is from OpenStreetMap.
- **Miles.** The "Nearest" list gives longer distances in miles (for example "5.7 mi"), and the scale bar shows miles
  beside kilometres, as for the US maps.
- **Tile size.** A zoom-10 tile over La Paz and El Alto (10/318/559) is 282,364 bytes (0.28 MB), with 2,017 roads;
  the zoom-13 tile (13/2545/4476) is 513,050 bytes (0.51 MB), with 3,780 roads.

## Licence and attribution

All data in this map is from OpenStreetMap, © OpenStreetMap contributors, under the Open Database License 1.0, taken
from Geofabrik's Bolivia extract. A database built from it, which this map is, is offered under the ODbL as well. The
credit and the date of the data are written into `meta` in `national.sqlite` and `map.sqlite`, and into
`BO-L.build.json`. No COD-AB data is in the map: the COD-AB layer was only used, in REGIONS-BO.md, to choose the box.
