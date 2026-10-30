# Data dictionary

All tables are CSV (UTF-8, comma separated, one header row). Lists inside a cell are separated by `;`.
Empty means unknown or not applicable. License: CC BY 4.0 (see `LICENSE.md`); the data the index points to
keep their sources' terms.

## sources.csv

One row per source.

| Column | Meaning |
|---|---|
| source_id | Short id used by the tool (`namss`, `sarig`, `boem-data-center`, ...) |
| name, provider, country, data | What the source is and what it holds |
| access | `open` (no account, no click-through), `terms` (click-through), `account`, `membership` |
| fetch_support | `direct` (the tool downloads), `request-list` (the tool writes requests you submit), `listed` (described only) |
| fees | Fees for released data, as the source states them |
| license, license_url | License or terms, and where they are stated |
| redistribution | Whether copies may be passed on |
| attribution | The credit line to use |
| doi | The source's own DOI, if any |
| landing_page, terms_url | Home page and terms page |
| how_to_get | The route to the data |
| counts, size | What the source holds (our counts unless the source's own) |
| checked | Date the terms were read |
| notes | Caveats |

## citations.bib

BibTeX, one or more entries per source. Each entry has an `osd_source` field with the source_id it belongs
to; `osd cite` and `osd fetch` use it to pick the entries for the sources you used, and leave it out of the
`.bib` file they write. Use the source's own suggested citation where it has one.

## files.csv

One row per file the tool can download.

| Column | Meaning |
|---|---|
| file_id | Id used by `osd --file` (`namss:<survey>`, `sarig:<resource>/<name>`, `boem:<name>`, `edx:<name>`, `ldeo:<hole>/<name>`) |
| source | source_id |
| kind | `seismic`, `wells` or `cores` (LILY) |
| dataset | Short description |
| url | Direct download URL at the source |
| bytes | Size at the source when indexed |
| checksum | `etag:<ETag>` (NAMSS, checked against the server), `sha256:<hex>` (our download), `md5:<hex>` (as Zenodo gives it, LILY), `members:crc32` (each zip member's CRC32 is in `seismic/members.csv`), or empty |
| stable | `no` when the source republishes the file under the same URL (BOEM tables) |
| regions | `gulf-of-mexico`, `pacific`, `alaska`, `south-australia`, `atlantic` |
| surveys | Survey ids the file holds |
| include | Include flags of the volumes in the file |
| local_path | Where `osd fetch` puts the file under `--dest` |
| license | The source's license |

## seismic/volumes.csv

One row per 3D post-stack volume (a SEG-Y file, or a set of files split by line range).

| Column | Meaning |
|---|---|
| source, survey_id, survey_name | Source and survey |
| volume | Volume name (file name without extension, or the common prefix of a split set) |
| region, location, year | Region code, the catalog's location text, acquisition year |
| stack_type, domain | Stack and migration as named by the catalog; `time`, `depth` or empty |
| role | `primary` (one full stack per survey) or `additional` (partial stacks, second migrations) |
| include | `yes` (checked migrated stack) or `decide` (needs a look; reason in `flags`) |
| flags | Why a volume is `decide`, and other notes |
| members | Zip member path(s) of the volume; `Data/x.zip` means a nested zip unpacked in full |
| file_count | Number of SEG-Y files |
| volume_bytes, volume_bytes_exact | SEG-Y size; `no` when rounded from the NAMSS catalog |
| file_id | The archive in `files.csv` |
| license, landing_page, doi | Terms, survey page, source DOI |
| on_reference_mirror | `yes` when the volume is in our reference copy and in `headers.csv` |

## seismic/members.csv

One row per zip member.

| Column | Meaning |
|---|---|
| file_id | Archive |
| member | Path inside the zip; `outer.zip!inner/path` for a member of a nested zip |
| kind | `segy`, `side` (small non-SEG-Y files: navigation, notes, images) or `other` |
| bytes, crc32 | Size and CRC32 |
| sha256 | SHA-256 of the unpacked member, from our reference copy |
| record | Where the values come from: `zip index` (central directory read over HTTP), `reference mirror` (our unpacked copy), `catalog listing, rounded` (NAMSS page; size rounded, no CRC) |

## seismic/headers.csv

One row per volume in our reference copy, from a scan of every trace header while unpacking.

| Column | Meaning |
|---|---|
| source, survey_id, volume, files, bytes, traces | Identity and size |
| opened_with_segyio | `True` when segyio 1.9 opened every file with full geometry |
| inline_byte, crossline_byte | Trace-header bytes that hold inline and crossline numbers |
| inline_min/max/step, crossline_min/max/step | Grid ranges |
| samples, sample_interval_binary, sample_interval_traces | Samples per trace and the interval in the binary and trace headers (microseconds for time data; NAMSS depth volumes store the depth step times 1000) |
| format_code, endianness, segy_revision, ext_text_headers | Binary header facts |
| x_byte, y_byte, coordinate_scalar, x_min/max, y_min/max | Where coordinates are, the byte-71 scalar, and the scaled ranges |
| crs_text_header | Text-header lines naming a datum, projection or zone |
| crs_catalog | Datum, projection and units from the NAMSS catalog |
| processing_text_header | Text-header lines on processing (migration, stack, filters) |
| header_fixes | What a reader must set or distrust |
| problems, n_problems | Every departure from the standard that the scan found |

## seismic/grids.csv

One row per Gulf of Mexico volume in our reference copy that has wells inside its survey outline.

| Column | Meaning |
|---|---|
| survey_id, volume | Volume |
| status | `fitted`, or why not |
| quality | `good` (at least 95% of sampled traces inside the outline and RMS misfit under 50 units), `check` (at least 50% inside) or `unresolved` |
| crs | Coordinate system chosen for the headers |
| crs_named_in_text_header | `True` when the text header alone pointed to one system |
| frac_traces_inside_outline | Share of sampled traces inside the NAMSS outline (grown by 5%) |
| fit_rms, fit_max | RMS and largest misfit of the affine fit, in coordinate units |
| n_traces_sampled | Trace headers read |
| x0, x_per_inline, x_per_crossline, y0, y_per_inline, y_per_crossline | x = x0 + x_per_inline * inline + x_per_crossline * crossline, and the same for y |

## seismic/footprints.geojson

Polygons with properties `source`, `survey_id`, `footprint` (`NAMSS navigation outline`, `trace-header grid
corners`, or `SARIG catalog extent`), `datum` and, for grids, `volume` and `quality`.

## wells/gulf_exploration_wells.csv

One row per exploratory original hole (BOEM type E, API sidetrack code 00) in the Gulf of Mexico.

| Column | Meaning |
|---|---|
| api ... bot_area_block | BOEM borehole table fields: API number, well name, operator code, field code, spud and TD dates (YYYYMMDD), type, status code, kelly bushing height, measured depth, true vertical depth, water depth (feet), surface and bottom-hole longitude and latitude (NAD27; BOEM writes `################` when missing), area and block |
| spud_year | Year of spud |
| setting | `shelf` (water under 1,000 ft) or `deep` |
| discovery | `True` when the 10-digit API is the discovery well of a sand in the BOEM 2023 sands atlas |
| field_discovery | `True` when the well found its field's first sand |
| field_mmboe | Original recoverable reserves of that field, million barrels of oil equivalent (field discoveries only) |
| in_namss, surveys, first_survey_year | Whether the well is inside a NAMSS 3D outline, which ones, and the earliest acquisition year |
| after_survey | `True` when spudded after the first survey over it was shot |
| has_checkshot, has_paleo | BOEM velocity survey or paleo report exists for the well |
| frs_raw_logs, frs_raw_bytes, frs_raw_logs_le_100mb | Digital log files in the BOEM File Request System inventory for the well |
| volumes_tied | Volumes in our reference copy whose grid contains the well |

## wells/gulf_well_volume_ties.csv

One row per well and volume, for volumes with a `good` or `check` grid fit.

| Column | Meaning |
|---|---|
| api, survey_id, volume, crs, grid_quality | Well, volume, coordinate system, fit quality |
| surface_x, surface_y, surface_inline, surface_crossline, surface_inside_grid | Surface location in the volume's coordinates and grid |
| bottom_x, bottom_y, bottom_inline, bottom_crossline, bottom_inside_grid | Bottom-hole location, the same way |

## wells/boem_frs_raw_logs.csv

One row per digital log file ("Raw Log Samples") in the public BOEM FRS inventory for the wells above.

| Column | Meaning |
|---|---|
| doc_id | FRS file ID, as uploaded in a request |
| api, api10 | Well API number, full and 10-digit |
| doc_type, file_ext | Document type and extension as BOEM lists them |
| run_date, releasable_date, created_date | Dates from the inventory |
| bytes | File size |

## cores/lily_holes.csv

One row per hole with data in the LILY database (https://doi.org/10.5281/zenodo.8408297). Built by `tools/lily_holes.py` from the LILY files.

| Column | Meaning |
|---|---|
| exp, site, hole | IODP expedition, site and hole, as in the LILY data files |
| latitude, longitude | Decimal degrees, from LILY's core summary (`2_CoreSUMM.zip`); no datum is stated there |
| water_depth_m | Water depth in meters below sea level, from the same core |
| program | Drilling program as the core summary gives it (IODP-1 or IODP-2) |
| position_from | `hole`: the hole's first core with a position; `site`: no core of the hole has one, so another hole at the same site |
| datasets | LILY data sets (file name prefixes, such as GRA or MAD) with at least one row for the hole |
