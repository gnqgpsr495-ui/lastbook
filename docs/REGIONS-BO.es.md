# Mapas detallados para Bolivia: una propuesta

> Versión en español de [REGIONS-BO.md](REGIONS-BO.md). Si las dos difieren, vale la versión en inglés, que es la que se
> discute en el repositorio.

Esta es una propuesta para discutir, no una decisión. Responde, para Bolivia, las preguntas que [MAPS.md](MAPS.md) pide
contestar antes de que la cobertura vaya más allá de Estados Unidos: qué fuente abierta reemplaza a cada lista federal,
con qué licencia, qué es un "estado" en el país y cómo se escriben las direcciones. Sigue la forma de
[REGIONS-PY.md](REGIONS-PY.md), [REGIONS-AR.md](REGIONS-AR.md) y [REGIONS-CL-DPA2023.md](REGIONS-CL-DPA2023.md) y busca
alimentar la misma discusión de diseño (issues #23, #25 y #31). La versión legible por máquina es
[regions-bo-proposed.json](regions-bo-proposed.json).

Nada de esto cambia la app, el motor ni una compilación. Ningún código lee el JSON, y nada de esto se distribuye: las
compilaciones empaquetan solo `web/` y `content/`.

**Cómo se verificó.** La investigación se hizo el 21 y el 22 de noviembre de 2026. Cada dato lleva una de estas marcas:

- **abierta**: se abrió y se leyó la página, el archivo o la respuesta de la API;
- **calculada**: la cifra se calculó aquí a partir de un archivo descargado (se nombran el archivo y el método);
- **solo búsqueda**: el dato se vio en un resultado de búsqueda, pero no se abrió la página;
- **conocimiento general**: dicho de memoria, sin abrir ninguna fuente; necesita la revisión de alguien del país;
- **sin verificar**: no se pudo llegar a la página o leerla; la fila dice qué falta.

"No se encontró" quiere decir que no se encontró buscando en la web. Varios sitios del gobierno boliviano no
respondieron desde aquí el 21 de noviembre de 2026: GeoBolivia (`geo.gob.bo`) y el Instituto Geográfico Militar
(`igm.gob.bo`, `igmbolivia.gob.bo`) no contestaron, y Defensa Civil (`defensacivil.gob.bo`) devolvió HTTP 403. Lo que
contienen figura en "Qué se verificó y qué no".

## Qué es una región

Bolivia tiene nueve departamentos. La propuesta es **una sola región para todo el país**, con el código `BO`, como
REGIONS-PY.md propone para Paraguay y REGIONS-LK.md para Sri Lanka, con los nueve departamentos como alternativa si se
quieren regiones más chicas.

Por qué una sola región:

- **Tamaño de la descarga.** El extracto de Geofabrik de todo el país pesa 167 MB (abierta), algo más que los 147 MB de
  Paraguay, que REGIONS-PY.md propone como una sola región, y la mitad de los 352 MB de Chile.
- **Los departamentos son muy desiguales.** Santa Cruz tiene 368.779 km² y Tarija 37.259 km² (`area_sqkm` del COD-AB,
  abajo): Santa Cruz sola es un tercio del país y casi todo Paraguay (399.603 km² en la misma familia de datos, según
  REGIONS-PY.md). Dividir por departamentos da un mapa muy grande y varios chicos.
- **Cómo se mueve la gente** (conocimiento general). El eje carretero La Paz – Oruro – Cochabamba – Santa Cruz cruza
  cuatro departamentos, y los departamentos del Altiplano (La Paz, Oruro, Potosí) comparten una misma meseta. Quien
  viaja por ese eje necesitaría varios mapas departamentales.

Aquí el argumento a favor de los departamentos es más fuerte que en Paraguay: cada una de las ciudades más grandes queda
bien dentro de su propio departamento (La Paz y El Alto en La Paz, Santa Cruz de la Sierra en Santa Cruz, Cochabamba en
Cochabamba; conocimiento general), así que un mapa departamental no partiría un área metropolitana en dos. Si los
mantenedores prefieren departamentos, los rectángulos están abajo.

### Códigos

- **`BO` para todo el país.** Un `BO` solo no está en `STATE_CODES` (`engine/address_search.py`), así que no choca con
  ningún código de estado de EE. UU., la misma verificación que REGIONS-PY.md hizo para `PY`.
- **ISO 3166-2:BO para los departamentos**: una letra después del guion (`BO-L` La Paz, `BO-S` Santa Cruz, etc.), no un
  número como en Paraguay o Chile. La forma con guion evita cualquier choque con `STATE_CODES`; [MAPS.md](MAPS.md)
  señala que el manifiesto ya acepta ids de mapa como `DE-BE`.
- **De dónde salen los códigos.** El sitio de ISO (`iso.org/obp`) devolvió HTTP 403, así que los códigos **no se
  verificaron contra ISO**. Se abrieron otras cuatro fuentes y todas dan los mismos nueve códigos para los mismos
  departamentos. Debian, UN/LOCODE y Natural Earth llaman a `BO-B` "El Beni"; geoBoundaries y el COD-AB de OCHA dicen
  "Beni". Las cuatro fuentes:
  - el paquete `iso-codes` de Debian, versión 4.16.0 (`iso_3166-2.json`, que sigue la ISO 3166-2);
  - la lista de subdivisiones de UN/LOCODE, leída a través del espejo `datasets/un-locode` en GitHub
    (`data/subdivision-codes.csv`, actualizado desde UNECE el 16 de octubre de 2026). Las páginas de UNECE mostraron un
    desafío de Cloudflare;
  - el campo `iso_3166_2` de Natural Earth 5.1.1 admin-1;
  - el campo `shapeISO` del archivo BOL ADM1 de geoBoundaries.
- **Ojo con el orden.** Los p-codes de OCHA numeran los departamentos de `BO01` a `BO09` en un orden distinto al de las
  letras ISO (`BO01` es Chuquisaca, `BO-H`; `BO02` es La Paz, `BO-L`). Todo lo que una los dos debe unir por nombre, no
  por posición.

### Rectángulos

Los rectángulos se calcularon con el conjunto común de límites administrativos de OCHA (COD-AB) para Bolivia,
`bol_admin0.geojson` y `bol_admin1.geojson` de `bol_admin_boundaries.geojson.zip` (versión `v02`, `valid_on` 16 de
septiembre de 2024, archivos modificados el 13 de mayo de 2026; descargados y calculados el 21 de noviembre de 2026).
Cada rectángulo es la extensión de todos los vértices de la unidad, menos/más 0,15° y redondeado hacia afuera a 0,01°
(hacia abajo al oeste y al sur, hacia arriba al este y al norte), el mismo margen que `map_sets.state` usa para los
estados de EE. UU. (`derived/packs/pack-spec.json`: "box = ZCTA centroids in profiles.sqlite, plus or minus 0.15
degrees"). Siete departamentos son un solo polígono; La Paz tiene 27 partes (incluye islas del lago Titicaca;
conocimiento general) y Oruro dos. Todas las partes cuentan para el rectángulo.

| Código | Nombre | Rectángulo (oeste, sur, este, norte) | Con margen de 0,15° | Superficie (km², `area_sqkm`) |
|---|---|---|---|---|
| `BO` | Bolivia | -69.6452, -22.9066, -57.4544, -9.6696 | -69.80, -23.06, -57.30, -9.51 | 1.081.700 |

La superficie del COD-AB es el atributo del propio conjunto. La superficie oficial de Bolivia suele darse como 1.098.581
km² (conocimiento general); la diferencia no se investigó. El polígono de recorte de Geofabrik (`bolivia.poly`, abierta,
161 vértices) da un rectángulo más holgado, -69.6568, -22.9255, -57.4348, -9.6387, como se espera de un polígono trazado
alrededor de la frontera.

| Código ISO | p-code COD-AB | Nombre | Rectángulo (oeste, sur, este, norte) | Con margen de 0,15° | Superficie (km², `area_sqkm`) |
|---|---|---|---|---|---|
| `BO-H` | BO01 | Chuquisaca | -65.6956, -21.5173, -62.1794, -18.3470 | -65.85, -21.67, -62.02, -18.19 | 50.945 |
| `BO-L` | BO02 | La Paz | -69.6452, -18.0469, -66.7321, -11.8497 | -69.80, -18.20, -66.58, -11.69 | 128.255 |
| `BO-C` | BO03 | Cochabamba | -67.0057, -18.6818, -64.2341, -15.7799 | -67.16, -18.84, -64.08, -15.62 | 54.450 |
| `BO-O` | BO04 | Oruro | -69.1423, -19.8867, -66.0861, -17.3239 | -69.30, -20.04, -65.93, -17.17 | 52.194 |
| `BO-P` | BO05 | Potosí | -68.7739, -22.9066, -64.7144, -17.8071 | -68.93, -23.06, -64.56, -17.65 | 119.207 |
| `BO-T` | BO06 | Tarija | -65.4199, -22.8828, -62.2607, -20.8858 | -65.57, -23.04, -62.11, -20.73 | 37.259 |
| `BO-S` | BO07 | Santa Cruz | -64.8424, -20.4732, -57.4544, -13.4757 | -65.00, -20.63, -57.30, -13.32 | 368.779 |
| `BO-B` | BO08 | Beni (ISO: El Beni) | -67.5622, -16.4917, -61.5279, -10.3812 | -67.72, -16.65, -61.37, -10.23 | 206.875 |
| `BO-N` | BO09 | Pando | -69.5747, -12.4984, -65.2868, -9.6696 | -69.73, -12.65, -65.13, -9.51 | 63.737 |

**Lagos y salares.** El conjunto de OCHA advierte que los niveles 2 y 3 (provincias y municipios) dejan siete cuerpos de
agua como huecos, entre ellos el Salar de Uyuni, el Salar de Coipasa, el lago Titicaca, el lago Poopó y el lago Uru Uru,
mientras que los niveles 0 y 1 los encierran (abierta, ficha de HDX). Los rectángulos de arriba salen de los niveles 0 y
1, así que incluyen esos cuerpos de agua. Un rectángulo tomado de una provincia o municipio podría cortarse en la orilla
de un lago.

**Límites no resueltos.** La Ley 339 de 2013 (abierta, en Lexivox) distingue "límites precisos" de "límites imprecisos",
aquellos "que no han sido definidos en la norma o que habiéndolo sido, carecen de coordenadas", y deja la demarcación al
IGM caso por caso. Por eso los límites departamentales de cualquier conjunto de datos son aproximados en algunos tramos,
como dicen REGIONS-AR.md y REGIONS-CL-DPA2023.md de sus propios límites internos. Un rectángulo es solo un corte para
una descarga; no debe leerse como una afirmación sobre dónde termina un departamento.

### Comparaciones

| Fuente | Licencia | Resultado | Marca |
|---|---|---|---|
| geoBoundaries gbOpen BOL ADM0 y ADM1 (fuente "GeoBolivia, Derived from ADM3 layer", año representado 2015, generado el 12 de diciembre de 2023) | "Public Domain" según geoBoundaries | Todos los rectángulos son iguales a los del COD-AB con cuatro decimales (sin redondear, las extensiones difieren en menos de 0,000001°). Los dos archivos parecen compartir la misma geometría, así que **no es una verificación independiente** (una inferencia a partir de la coincidencia; no se rastreó el origen de ninguno de los dos). Los mismos nueve códigos ISO. | abierta, calculada |
| Natural Earth 5.1.1, admin-0 y admin-1 a 10 m | Dominio público (página de términos abierta) | Líneas distintas y generalizadas. La mayor diferencia en un borde es 0,0914° (borde oeste de Tarija, unos 9 km); el rectángulo del país difiere como mucho en 0,0213° (borde oeste). **Todos los rectángulos departamentales de Natural Earth caben dentro del rectángulo con margen del COD-AB**, así que el margen absorbe la diferencia. | abierta, calculada |
| `bolivia.poly` de Geofabrik | ODbL (con el extracto) | Más holgado que el COD-AB en los cuatro lados, entre 0,01° y 0,03°. | abierta, calculada |

Mayor diferencia en un borde entre Natural Earth y el COD-AB, por departamento (calculada; los kilómetros son
aproximados, a la latitud media del departamento): Chuquisaca 3,3 km, La Paz 6,1 km, Cochabamba 8,9 km, Oruro 8,5 km,
Potosí 5,3 km, Tarija 9,4 km, Santa Cruz 3,7 km, Beni 7,1 km, Pando 1,1 km.

### Vecinos dentro de los rectángulos

Un rectángulo alrededor de Bolivia contiene mucho de sus vecinos. Las proporciones de abajo se calcularon muestreando
cada rectángulo con margen en una grilla de 0,02° y buscando cada punto en los polígonos admin-1 a 10 m de Natural Earth
(calculada; Natural Earth está generalizado, así que son aproximadas). Son proporciones del rectángulo, no de la
superficie en km².

| Rectángulo | Bolivia | Otros países dentro del rectángulo (unidades más grandes) |
|---|---|---|
| `BO` | 54,5 % | Brasil 26,8 % (Mato Grosso, Rondônia, Acre, Mato Grosso do Sul), Paraguay 9,4 % (Alto Paraguay, Boquerón, Presidente Hayes), Chile 4,1 % (Antofagasta, Tarapacá, Arica y Parinacota), Argentina 2,6 % (Salta, Jujuy), Perú 2,5 % (Puno, Madre de Dios) |
| `BO-H` Chuquisaca | 97,2 % | Paraguay 2,8 % (Boquerón) |
| `BO-L` La Paz | 79,5 % | Perú 19,0 % (Puno, Madre de Dios), Chile 1,5 % (Arica y Parinacota) |
| `BO-C` Cochabamba | 100 % | ninguno |
| `BO-O` Oruro | 90,2 % | Chile 9,8 % (Tarapacá, Arica y Parinacota) |
| `BO-P` Potosí | 79,2 % | Chile 10,9 % (Antofagasta, Tarapacá), Argentina 9,9 % (Jujuy, Salta) |
| `BO-T` Tarija | 56,1 % | Argentina 36,5 % (Salta, Jujuy, Formosa), Paraguay 7,4 % (Boquerón) |
| `BO-S` Santa Cruz | 69,9 % | Brasil 22,0 % (Mato Grosso, Mato Grosso do Sul, Rondônia), Paraguay 8,1 % (Alto Paraguay, Boquerón) |
| `BO-B` Beni | 75,6 % | Brasil 24,4 % (Rondônia) |
| `BO-N` Pando | 61,3 % | Brasil 31,3 % (Acre, Rondônia, Amazonas), Perú 7,4 % (Madre de Dios) |

La parte boliviana de cada rectángulo departamental incluye también departamentos bolivianos vecinos; esa división no se
calculó. El mismo solapamiento aparece desde el otro lado: REGIONS-PY.md señala que el rectángulo de Paraguay incluye
partes del sureste de Bolivia, y REGIONS-CL-DPA2023.md que los rectángulos de las regiones del norte de Chile incluyen
territorio boliviano.

Como en Paraguay, el extracto de Geofabrik ya viene cortado unos kilómetros fuera de la frontera, así que una primera
compilación hecha con él casi no tiene nada de los vecinos. Varias ciudades tienen una gemela del otro lado
(conocimiento general): Desaguadero a ambos lados de la frontera con Perú junto al Titicaca, Puerto Quijarro y Corumbá
(Brasil), Guayaramerín y Guajará-Mirim (Brasil), Cobija y Brasiléia (Brasil), Villazón y La Quiaca (Argentina), Yacuiba
y Salvador Mazza (Argentina). El lago Titicaca se comparte con Perú (conocimiento general). La sugerencia, como para
Paraguay, es usar la frontera como borde de una primera compilación y decidir después si se agrega una franja tomada de
los extractos vecinos.

## Fuentes, capa por capa

OpenStreetMap es la base de una primera compilación, como en Paraguay. El COD-AB de OCHA da las unidades administrativas
hasta los municipios. No se encontraron listas nacionales abiertas de establecimientos de salud, estaciones de bomberos
ni albergues, y Overture no tiene direcciones bolivianas.

| Capa (archivo) | Fuente en EE. UU. hoy | Propuesta para Bolivia | Publicador | Licencia | Marca |
|---|---|---|---|---|---|
| Calles, agua, suelo (mapa base) | Extracto de OSM | Extracto de OSM `bolivia-latest.osm.pbf` (167 MB según Geofabrik; el fechado `bolivia-261120.osm.pbf` pesa 175.175.057 bytes, unos 167 MiB; el `-free.shp.zip` pesa 396 MB y el `-free.gpkg.zip` 405 MB) | Colaboradores de OSM vía Geofabrik | ODbL 1.0 | abierta |
| Puntos de interés (`poi`) | OSM | OSM (conteos abajo) | Colaboradores de OSM | ODbL 1.0 | calculada |
| Lugares (`places.sqlite`) | GNIS, gazetteers del censo, OSM | COD-AB de OCHA, niveles 1 a 3 (9 departamentos, 112 provincias, 339 municipios) y su archivo `adminpoints`; lugares con nombre de OSM | OCHA, fuente "Ministerio de Desarrollo Rural y Tierras"; colaboradores de OSM | CC BY-IGO; ODbL 1.0 | abierta (ficha de HDX); calculada (cantidad de unidades, del GeoJSON) |
| Relieve (`terrain.sqlite`) | USGS 3DEP | Copernicus DEM GLO-30, como se propone para Guyana | ESA / Airbus | Licencia Copernicus WorldDEM-30 | como en REGIONS.md; cobertura de teselas de Bolivia sin verificar |
| Agua (`water.sqlite`) | NHD | Cursos y cuerpos de agua de OSM | Colaboradores de OSM | ODbL 1.0 | sin verificar más allá de OSM |
| Represas | NID | OSM `waterway=dam` y `water=reservoir`; no se encontró un inventario abierto de represas | Colaboradores de OSM | ODbL 1.0 | calculada |
| Cultivos (`crops.sqlite`) | USDA Cropland Data Layer | No se estudió en esta propuesta. ESA WorldCover (CC BY 4.0) es la alternativa que nombran otras propuestas | | | sin verificar |
| Edificios (`buildings.sqlite`) | Huellas de Microsoft para EE. UU., alturas de OSM | Google Open Buildings v3 ("BOL Bolivia" está en su lista de países, que según Google está "subject to change"); Microsoft Global ML Building Footprints (238 teselas de Bolivia en el `dataset-links.csv` del 12 de noviembre de 2026) | Google; Microsoft | CC BY 4.0 u ODbL 1.0, a elección del usuario (Google); CDLA Permissive 2.0 (Microsoft) | abierta; cobertura y calidad sin medir |
| Direcciones (`addresses/<code>.sqlite`) | Direcciones de Overture | **No se encontró ninguna.** El tema de direcciones de Overture (versión 2026-11-18.0) lista 41 países y Bolivia no está entre ellos. Solo quedan las etiquetas `addr:*` de OSM (conteos abajo) | | | abierta |

### Puntos de ayuda y de recursos

Los conteos se hicieron con pyosmium sobre el extracto fechado de Geofabrik `bolivia-261120.osm.pbf` (175.175.057 bytes,
con un MD5 igual a la suma publicada por Geofabrik; datos hasta el 20 de noviembre de 2026, 21:21 UTC). Cada conteo
incluye nodos, vías y relaciones con la etiqueta; "con nombre" es cuántos de ellos tienen además `name`.

| Tipo | Etiqueta OSM | Cantidad (con nombre) | Otra fuente | Marca |
|---|---|---|---|---|
| Hospitales | `amenity=hospital` | 907 (855); 455 con `emergency=yes`, 9 con `emergency=no`, 442 sin etiqueta `emergency` | Fichas de salud de HDX, ver abajo | calculada |
| Clínicas y consultorios | `amenity=clinic`, `amenity=doctors` | 851: 649 clínicas (615), 202 consultorios (182) | ídem | calculada |
| Farmacias | `amenity=pharmacy` | 2.627 (2.297) | no se encontró | calculada |
| Estaciones de bomberos | `amenity=fire_station` | 43 (41) | no se encontró | calculada |
| Policía | `amenity=police` | 593 (514) | no se encontró | calculada |
| Agua potable | `amenity=drinking_water`, `man_made=water_tap`, `amenity=water_point` | 159 (88, 63, 8) | no se encontró | calculada |
| Pozos, torres de agua y tanques | `man_made=water_well`, `water_tower`, `storage_tank` | 1.599 (75 pozos, 591 torres, 933 tanques; contenido sin verificar) | no se encontró | calculada |
| Embalses y represas | `water=reservoir`, `waterway=dam` | 4.402 embalses (sin contar `landuse=reservoir`), 1.081 represas | no se encontró | calculada |
| Combustible | `amenity=fuel` | 714 (670) | no se encontró | calculada |
| Bases de ambulancias | `emergency=ambulance_station` | 8 (6) | no se encontró | calculada |
| Refugios y puntos de encuentro | `amenity=shelter`, `social_facility=shelter`, `emergency=assembly_point` | 941 (922, 9, 10) | no se encontró | calculada |
| Escuelas | `amenity=school` | 9.806 (9.091) | no se encontró | calculada |

Notas:

- **Una cantidad de filas no es una cantidad de lugares.** Como REGIONS-PY.md encontró para Paraguay, OSM suele tener un
  mismo hospital como punto y otra vez como sus edificios. Los conteos son cotas superiores; para Bolivia no se
  agruparon por distancia.
- **Estaciones de bomberos.** OSM tiene 43. No se verificó qué tan completo es eso: no se encontró una lista publicada
  de ubicaciones de estaciones con la cual comparar.
- **"Shelter" en OSM.** `amenity=shelter` marca techos pequeños, no albergues de emergencia. De los 922 de Bolivia, por
  `shelter_type` (calculada): 185 refugio contra el clima, 171 sin tipo, 163 parada de transporte público, 147 glorieta,
  138 refugio de picnic, 73 refugio del sol y 45 con otros valores o valores mal escritos. No deben dibujarse como
  albergues de emergencia.
- **Etiquetas de salud.** 849 objetos tienen `healthcare=hospital` y 47 `healthcare=centre`; se solapan con los conteos
  de `amenity` y no se depuraron duplicados.

Otras fuentes de puntos de ayuda:

- **Salud.** No se encontró como descarga la lista de establecimientos del Ministerio de Salud. HDX tiene tres fichas de
  salud de Bolivia (abiertas mediante la API de HDX): `hotosm_bol_health_facilities` (HOT, de OSM, ODbL, actualizada el
  16 de noviembre de 2026), `bolivia-healthsites` (healthsites.io, de OSM, ODbL, actualizada el 29 de septiembre de
  2026) y `bolivia-health` (fuente "Ministerio de Salud y Deportes", licencia "Other", última actualización el 16 de
  agosto de 2018). Las dos primeras son datos de OSM que ya están en el extracto. La tercera es vieja y sus términos no
  son claros; no debería usarse sin preguntar. El sistema de información en salud del Ministerio
  (`snis.minsalud.gob.bo`) no se verificó.
- **Bomberos, policía y albergues.** No se encontró ninguna lista nacional abierta. En Bolivia los bomberos son parte de
  la Policía Boliviana (solo búsqueda).

### Amenazas

- **SENAMHI** (Servicio Nacional de Meteorología e Hidrología), `senamhi.gob.bo`, abierta. La página principal enlaza a
  "Alertas Hidrologicas", "Manchas de Inundacion ACRE", "Focos de Calor", "Monitor de Sequias" y "Aviso Meteorologico
  para la Emision de Alerta", y a "Contacto y Solicitud de Datos". Su enlace "Términos y condiciones de uso" no lleva a
  ningún lado (`#`), y todas las páginas abiertas terminan con "© Copyright 2026 | Derechos Reservados SENAMHI". **No se
  encontró una licencia abierta**, así que, según la regla que usa REGIONS-AR.md ("a dataset with no stated licence is
  treated here as not yet usable"), estos datos necesitan el permiso de SENAMHI. Las páginas de alertas se dibujan con
  JavaScript y sus datos no se leyeron.
- **Defensa Civil (VIDECI)**, `defensacivil.gob.bo`: HTTP 403, **sin verificar**.
- **Cuáles son las amenazas** (conocimiento general, para que lo confirme alguien de Bolivia): inundaciones en las
  tierras bajas de Beni, Pando y Santa Cruz; incendios forestales y de pastizales, a menudo por chaqueo, en Santa Cruz y
  Beni; mazamorras y deslizamientos en La Paz; sequía, heladas y granizo en el Altiplano. La altura es por sí misma un
  riesgo para la salud en La Paz, El Alto, Oruro y Potosí; hoy ninguna guía lo trata, y eso sería una tarea de contenido
  aparte.

## Licencias y atribución

- **CC BY-IGO** (COD-AB de OCHA, abierta mediante la API de HDX). Hay que citar a OCHA y a su fuente, el Ministerio de
  Desarrollo Rural y Tierras.
- **ODbL 1.0** (OSM, y las dos fichas de salud de HDX hechas con OSM): como en el mapa de EE. UU.
- **CC BY 4.0 u ODbL 1.0** (Google Open Buildings): el usuario elige una (abierta).
- **CDLA Permissive 2.0** (huellas de Microsoft descargadas de su lista de conjuntos): un paquete que las comparta debe
  poner a disposición el texto de la licencia junto con ellas, como señala REGIONS-CL-DPA2023.md.
- **geoBoundaries** registra sus archivos de Bolivia como "Public Domain; free use and access to information", citando
  una ficha de metadatos de GeoBolivia que no se pudo abrir. Aquí se usa solo para comparar.
- **Natural Earth**: dominio público (términos abiertos). Aquí se usa solo para comparar.
- **INE Bolivia** (Instituto Nacional de Estadística). Sus términos de uso (abiertos; "Términos y condiciones de uso
  (TCU) del portal del Censo 2024", última actualización el 25 de agosto de 2025) no son una licencia abierta. Dicen:
  "No se permite utilizar los datos con fines comerciales sin autorización previa del INE o sin respetar la fuente y
  contexto originales", y "Toda reproducción o redistribución debe mencionar la fuente completa en la siguiente forma:
  Fuente: Instituto Nacional de Estadística." También dicen: "El INE no tiene competencias en materia de límites de
  unidades territoriales." Si la cláusula comercial obligaría a un paquete gratuito que otro podría revender es la misma
  pregunta que REGIONS-AR.md plantea para el IGN de Argentina. No se propone ninguna capa del INE.
- **SENAMHI**: todos los derechos reservados (arriba).
- **Copernicus WorldDEM-30**: como en REGIONS.md.

### Publicar un mapa de Bolivia: una pregunta abierta

Chile tiene la regla de leyenda de DIFROL (REGIONS-CL-DPA2023.md); para Bolivia **no se encontró una regla parecida,
pero la búsqueda fue incompleta**, así que queda como pregunta para los mantenedores, no como respuesta.

- **Límites internos.** La Ley 339 de 2013 (abierta en Lexivox, una copia no oficial) dice en el art. 23: "La
  cartografía oficial es aquella elaborada por el Instituto Geográfico Militar"; el art. 16 dice que el IGM demarca las
  unidades pero "no define la delimitación de unidades territoriales". Nada de lo leído exige que un mapa privado lleve
  una leyenda o sea aprobado. El DS 5050 de 2023 (abierto en Lexivox en una pasada anterior el mismo día) aprueba la
  capa de límites a cargo del Viceministerio de Autonomías y envía los límites al IGM para su demarcación; tampoco se
  vio nada sobre mapas privados.
- **Los términos del propio IGM** no se pudieron leer: sus sitios no respondieron.
- **La frontera con Chile y la demanda marítima.** Bolivia mantiene una reivindicación de acceso al Pacífico
  (conocimiento general); la Corte Internacional de Justicia resolvió en 2018 que Chile no tiene obligación de
  negociarla (conocimiento general, sin verificar). Una búsqueda en la web no encontró ninguna norma boliviana que
  obligue a que un mapa publicado muestre el antiguo departamento del Litoral o la reivindicación (solo búsqueda). La
  oficina que llevaba la demanda, la Dirección Estratégica de Reivindicación Marítima, Silala y Recursos Hídricos
  Internacionales, se cerró por el DS 5376 del 16 de abril de 2025 (abierto en Lexivox).
- **Qué dibuja Lastbook hoy.** El mapa base mundial ya dibuja los contornos de los países (`web/world-context.json`) y
  cita a Natural Earth (`MAP_CREDIT` en `packaging/build_packs.py`). Un paquete de Bolivia hecho con OSM dibujaría la
  frontera tal como la tiene OSM. Si eso necesita algún texto en la app, para Bolivia o para Chile, lo deciden los
  mantenedores.

## Números de emergencia

La tabla de números corresponde al [issue #261](https://github.com/Immortal-Protocols/lastbook/issues/261), no a esta
propuesta de mapas, y en #235 la revisión del dueño pidió que un número que significa cosas distintas en distintos
países quede fuera de la búsqueda global de guías. Esta sección solo registra lo encontrado, para que el mapa y la tabla
de números coincidan después. **Aquí no se propone ningún número para la app.**

| Servicio | Número | Qué se encontró | Estado |
|---|---|---|---|
| Policía (Radio Patrullas) | 110 | El sitio de la Policía Boliviana (`policia.bo`, abierto el 21 de noviembre de 2026) muestra "BOL 110" con un enlace `tel:110` y "110 - Radio Patrullas" en su pie de página. Un folleto sin fecha de la Defensoría del Pueblo también lista "Radio Patrullas 110" (abierto en una pasada anterior el mismo día). | Las fuentes bolivianas coinciden |
| Bomberos | 119 | La misma página de `policia.bo` muestra "BOMBEROS 119" y "119 - Bomberos", pero en el mismo bloque da también **119 para la FELCC** (investigación criminal), mientras que su pie de página da "122 - FELCC". | **Conflicto en la página oficial**; abierto |
| Ambulancia | 118, 165, 167, 168 | No se encontró una fuente nacional actual. Los candidatos vienen de avisos de viaje extranjeros, páginas municipales y un informe boliviano de 2019 (encontrados en una pasada anterior el mismo día; no se volvieron a abrir); ver #261 cuando se trate Bolivia allí. | **Sin verificar**; abierto |

En estas fuentes, Bolivia no tiene un número único para todos los servicios. La ATT (el regulador de telecomunicaciones)
sería la fuente decisiva para el plan de numeración; en su sitio no se encontró una lista de números cortos de
emergencia (pasada anterior).

## Cómo se escriben las direcciones

No se verificó contra ninguna fuente postal o municipal boliviana. Esta parte necesita la revisión de alguien de
Bolivia.

- **Orden** (conocimiento general). Calle, luego número, luego la zona o el barrio y la ciudad: "Calle X Nº 123, Zona Y,
  La Paz". Como en Argentina y Paraguay, el número va después de la calle, al revés del orden que espera
  `engine/address_search.py`. Muchas casas no tienen número ("s/n").
- **Códigos postales** (conocimiento general, sin verificar): no se usan en la vida diaria. `engine/address_search.py`
  lee un código postal solo como cinco dígitos, así que esto no debería importar, pero no se probó.
- **Sin direcciones de Overture** (abierta, arriba). La búsqueda de direcciones dependería solo de las etiquetas
  `addr:*` de OSM. En el extracto de arriba, 10.527 objetos tienen `addr:housenumber` y 56.144 `addr:street`
  (calculada). De los 10.475 números de casa que se pudieron ubicar (nodos, y vías por su primer nodo), 4.581 están en
  La Paz, 2.939 en Cochabamba, 2.282 en Santa Cruz y 629 en los otros seis departamentos juntos (44 caen justo fuera del
  contorno del COD-AB). Es muy poco para buscar direcciones en todo el país.
- **Tildes.** `normalize()` en `engine/address_search.py` conserva solo `a-z`, `0-9` y espacios, así que "Potosí" se
  convierte en `potos` y "Calle Ñuflo de Chávez Nº 123" en `calle uflo de ch vez n 123` (probado el 22 de noviembre de
  2026), el mismo problema que describen REGIONS-PY.md y REGIONS-DE.md. Hace falta plegar los acentos de los dos lados;
  #79 propone que cada índice declare su propia regla.

Así que un primer mapa boliviano probablemente saldría como "mapa de calles, lugares y puntos de ayuda" sin búsqueda de
direcciones, como se sugirió para Paraguay y Sri Lanka.

## Idioma

El castellano es el idioma principal de mapas y carteles; la constitución también reconoce muchos idiomas indígenas,
entre ellos el quechua, el aymara y el guaraní (conocimiento general). En el extracto, 143 objetos tienen `name:qu`, 125
`name:ay` y 25 `name:gn` (calculada). Qué nombre muestra el mapa cuando difieren es parte de la pregunta de idioma de
los issues #3 y #54.

## Todavía sin decidir

Cada punto necesita una decisión de los mantenedores antes de cambiar código.

1. **Códigos en la instalación.** Si `BO` sirve como `id` del manifiesto, en `map-set.json` y en `Lastbook-Map-BO.zip`
   y, si se quieren departamentos, si sirven códigos de una letra con guion como `BO-L`.
2. **Una región o nueve.** Todo el país (lo propuesto) o cada departamento.
3. **La regla del rectángulo.** Si la frontera es el borde de una primera compilación, y si más adelante se agrega una
   franja para las ciudades gemelas y el lago Titicaca.
4. **Publicar la frontera.** Si un paquete que dibuja las fronteras de Bolivia, en particular la frontera con Chile,
   necesita algún texto, y si alguien debería consultar al IGM.
5. **Búsqueda de direcciones.** No hay fuente abierta de direcciones aparte de OSM; el número va después de la calle;
   "s/n"; plegar acentos antes de comparar. Sin más datos, un primer mapa sale sin búsqueda de direcciones.
6. **Puntos de ayuda sin fuente abierta**: establecimientos de salud, estaciones de bomberos y albergues. Si conviene
   pedir al Ministerio de Salud su lista con una licencia abierta, y si OSM alcanza para una primera compilación.
7. **Capas de amenazas.** SENAMHI no declara una licencia abierta; si conviene pedírsela, y si Defensa Civil publica
   algo.
8. **Números de emergencia**: quedan para #261; el conflicto del 119 y el número de ambulancia necesitan primero una
   fuente boliviana.
9. **Las capas que solo existen para California.** Como el punto 7 de REGIONS.md.

## Qué se verificó y qué no

- **Abierto el 21 de noviembre de 2026:** la ficha del COD-AB de OCHA para Bolivia mediante la API de HDX (licencia,
  fuente, fechas, advertencia, archivos); los metadatos de geoBoundaries para BOL ADM0 y ADM1; los términos de uso de
  Natural Earth; la página de Bolivia de Geofabrik y `bolivia.poly`; la guía de direcciones de Overture (versión
  2026-11-18.0); la página de Google Open Buildings; el README de las huellas de Microsoft y su `dataset-links.csv` del
  12 de noviembre de 2026; las tres fichas de salud de Bolivia en HDX; los términos de uso del INE; la página principal
  de SENAMHI y tres de sus subpáginas; `policia.bo`; la Ley 339 y el DS 5376 en Lexivox; el archivo de `iso-codes`
  4.16.0 de Debian; la lista de subdivisiones de `datasets/un-locode`; el issue #261 (sin entrada para Bolivia).
- **Abierto en una pasada anterior el mismo día** y no vuelto a abrir: el DS 5050 en Lexivox; el folleto de la
  Defensoría del Pueblo.
- **Descargado y calculado el 21 y el 22 de noviembre de 2026:** el GeoJSON del COD-AB (rectángulos del país y de los
  departamentos, superficies de `area_sqkm`, cantidad de unidades 9 / 112 / 339); el GeoJSON BOL ADM0 y ADM1 de
  geoBoundaries; Natural Earth 5.1.1 admin-0 y admin-1 a 10 m (rectángulos, y las proporciones de vecinos en una grilla
  de 0,02°); `bolivia.poly` de Geofabrik (extensión); `bolivia-261120.osm.pbf` de Geofabrik (los conteos de OSM, con
  pyosmium; números de casa repartidos por departamento del COD-AB).
- **Solo búsqueda:** que los bomberos son parte de la Policía Boliviana; que ninguna norma boliviana obliga a que los
  mapas muestren la demanda marítima.
- **Conocimiento general**, para que lo confirme alguien de Bolivia: la superficie oficial, dónde están las ciudades
  principales, el eje carretero, las ciudades gemelas, las amenazas, el orden de las direcciones y los códigos postales,
  los idiomas, la demanda marítima y el fallo de la CIJ de 2018.
- **Sin verificar:** el sitio de ISO (HTTP 403); las páginas de UN/LOCODE de UNECE (desafío de Cloudflare); GeoBolivia y
  el IGM (sin respuesta); Defensa Civil (HTTP 403); el sistema de información en salud del Ministerio; el plan de
  numeración de la ATT; las teselas bolivianas del DEM de Copernicus; fuentes de cultivos y cobertura del suelo; la
  cobertura y calidad de los edificios; cualquier número nacional de ambulancia.
