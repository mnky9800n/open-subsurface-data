# Open Subsurface Data on AWS

Open 3D post-stack seismic volumes from public archives, in one public S3 bucket, with the tables that say
what each file is and how to read it.

**Status (25 October 2026): not yet launched.** The bucket name, its region and the Registry of Open Data page
are set at launch. Until then, `<bucket>` below stands for the bucket name.

## What is in it

We downloaded each survey from its source archive, checked every file against the CRC32 stored in the source
zip, recorded its SHA-256 and unpacked it. The files are kept exactly as the sources shipped them: no format
conversion, no edits, the same names and folders as inside the zip. Beside them we put what we learned while
reading the headers, so that a user can open each volume correctly the first time.

Release 0.1 has three parts and the index tables (the full list, with checksums, is
`metadata/releases/0.1/files.csv` in the bucket and [`docs/starter_release.csv`](starter_release.csv) here).

| Part | Source | Surveys | SEG-Y files | Files | Size |
|---|---|---:|---:|---:|---:|
| `sarig-3d` | SARIG, South Australia: every 3D survey we hold | 117 | 117 | 709 | 583.2 GB |
| `namss-pacific-alaska` | USGS NAMSS: every survey offshore southern California and in the Beaufort Sea | 19 | 20 | 278 | 24.6 GB |
| `namss-gulf-psdm` | USGS NAMSS: 20 Gulf of Mexico surveys (see below) | 20 | 25 | 262 | 300.9 GB |
| `index` | the index tables of this repository (`data/`) | | | 13 | 0.01 GB |
| Total | | 156 | 162 | 1,262 | 908.7 GB |

The 20 Gulf of Mexico surveys are the ones whose volumes are all depth migrated, all marked `include = yes` in
the index, all open in segyio with full geometry, and that have at least 40 exploration wells spudded after the
survey year inside the survey outline. Together they hold 685 such wells. The rule is in
`tools/starter_release.py`.

Sizes are decimal (1 GB = 10^9 bytes). Later releases add more NAMSS surveys and other open sources; files
already in the bucket do not change.

## Reading the bucket

The bucket allows anonymous reads. No AWS account is needed.

    aws s3 ls --no-sign-request s3://<bucket>/
    aws s3 ls --no-sign-request s3://<bucket>/data/original/source=namss/
    aws s3 cp --no-sign-request s3://<bucket>/metadata/releases/0.1/files.csv .

From Python, with `s3fs`:

    import s3fs
    fs = s3fs.S3FileSystem(anon=True)
    fs.ls("<bucket>/data/original/source=sarig")

If you compute on AWS, work in the bucket's region and read straight from S3. The tutorial notebook,
[`notebooks/get-to-know-a-dataset.ipynb`](../notebooks/get-to-know-a-dataset.ipynb), lists the bucket, reads
the index, opens a SEG-Y volume with segyio and plots it.

## Layout

The layout follows the AWS onboarding handbook (Appendix A): a README at the top, `data/`, `metadata/` and
`docs/` prefixes, one prefix per kind of data, and Hive-style `key=value` partitions.

    s3://<bucket>/
      README.txt                                   this document
      data/
        original/                                  the sources' files, byte for byte
          source=namss/survey=<survey_id>/<paths as inside the NAMSS zip>
          source=sarig/survey=<survey_id>/<paths as inside the SARIG zip>
      metadata/
        index/                                     the index tables (data/ in this repository)
        surveys/source=<source>/survey=<survey_id>/metadata.json
        releases/<release>/files.csv               every object in a release, with checksums
      docs/                                        documentation and the tutorial notebook

Everything under `data/original/` came from a source archive. Everything under `metadata/` was written by us.
A survey folder holds the SEG-Y volume (or volumes) and the side files that came in the same zip: processing
reports (PDF), navigation (ESRI shapefiles, text), notes and images. Some side files have spaces in their names,
as the source wrote them; quote the keys. Thirteen NAMSS surveys offshore California ship their navigation as
a small zip inside the survey zip; those are kept as zips.

Survey IDs are the sources' own: NAMSS IDs such as `B-55d-99-LA` (survey, year, area) and SARIG resource IDs
such as `mesac681`.

## Formats

### SEG-Y

The seismic is SEG-Y, revision 0 or 1. Of the 162 SEG-Y files in release 0.1, 154 store IBM floating point.
These files seldom follow the standard for trace headers. In 140 of the 157 volumes in release 0.1, the inline
and crossline numbers are not at bytes 189 and 193, and segyio opens only 70 of them with full geometry.
Coordinates use bytes 73/77 or 181/185 with different scalars, text headers name byte positions that do not
work, and the coordinate system is named in free text if at all. NAMSS depth volumes
store the depth step times 1000 in the sample interval field, which readers that treat the field as signed
get wrong when it is above 32,767. Read the survey's `metadata.json` before opening a volume.

### metadata.json

One per survey, at `metadata/surveys/source=<source>/survey=<survey_id>/metadata.json`. It was written when the
survey was unpacked, from a scan of every trace header.

| Key | Meaning |
|---|---|
| `survey_id`, `source`, `survey_name`, `location`, `year` | Identity, as the source catalog gives it |
| `license`, `terms_url`, `landing_page`, `archive_url` | The source's terms, its survey page and the zip we unpacked |
| `catalogue_crs`, `crs_in_side_files` | Coordinate system named by the catalog and by the side files |
| `volumes` | One entry per SEG-Y volume, keyed by volume name (below) |
| `updated`, `tools` | When the file was written, and with which tool versions |

For each volume:

| Key | Meaning |
|---|---|
| `manifest` | Our selection flags: `include` (`yes` for a checked migrated stack, `decide` when it needs a look), `role` (`primary` or `additional`), `stack_type`, `domain` (`time`, `depth` or empty), `flags` |
| `files` | Each SEG-Y file of the volume: `path` inside the survey folder, `bytes`, `crc32` (from the zip), `sha256`, `archive_member` |
| `opened_with_segyio` | `true` when segyio 1.9 opened every file with full geometry using `header_bytes` |
| `inline_range`, `crossline_range` | `min`, `max`, `step`, and whether they came from segyio or from the trace scan |
| `samples`, `sample_interval` | Samples per trace; the interval in the binary header, the trace headers and as segyio reads it |
| `header_bytes` | `inline` and `crossline` byte positions, and `coordinates` (`x_byte`, `y_byte`, `scalar_byte`, scalar values, x and y ranges) |
| `crs` | Text-header lines that name a datum, projection or zone |
| `problems` | Every departure from the SEG-Y standard the scan found |
| `file_headers` | Per file: the text header and its encoding, binary header fields, trace count, counts of trace-header values, the byte pairs tried for inline and crossline, the segyio result, and text-header lines on processing |

To open a volume with segyio:

    hb = meta["volumes"][name]["header_bytes"]
    segyio.open(path, iline=hb["inline"], xline=hb["crossline"])

When `opened_with_segyio` is `false`, the grid has gaps or repeats; open with `ignore_geometry=True` and use the
ranges in the metadata.

### Index tables

CSV (UTF-8, comma separated, one header row) and one GeoJSON file, in `metadata/index/` in the bucket and
[`data/`](../data) in this repository. The data dictionary is [`data/README.md`](../data/README.md).

| File | One row per |
|---|---|
| `sources.csv` | source: access, fees, license, redistribution, credit line, DOI |
| `files.csv` | source archive: URL, size, checksum, regions, surveys |
| `seismic/volumes.csv` | 3D volume: survey, region, year, stack type, domain, role, include, size |
| `seismic/members.csv` | file inside a source zip: size, CRC32, SHA-256 |
| `seismic/headers.csv` | volume: header layout, ranges, coordinate bytes, fixes, problems |
| `seismic/grids.csv` | Gulf volume: fitted inline/crossline to x/y transform, coordinate system, fit quality |
| `seismic/footprints.geojson` | survey outline or grid corners |
| `wells/gulf_exploration_wells.csv` | Gulf exploration well: BOEM header fields, outcome, field size, surveys over it |
| `wells/gulf_well_volume_ties.csv` | well and volume: the well's position in the volume's inline/crossline grid |
| `wells/boem_frs_raw_logs.csv` | BOEM digital log file for those wells |
| `cores/lily_holes.csv` | hole in the LILY ocean drilling database, with its position |

Longitudes and latitudes are NAD27 for NAMSS and BOEM. Depths in the well tables are in feet, as BOEM gives
them. The index also lists data that are not in the bucket (the rest of NAMSS, the BOEM well logs, LILY);
`files.csv` gives their source URLs, and the `osd` tool in this repository fetches them from the sources.

### Release file list

`metadata/releases/<release>/files.csv` has one row per object: `release`, `part`, `source`, `survey_id`,
`region`, `kind` (`segy`, `side`, `metadata` or `index`), `corpus_path` (where the file sat in our copy),
`s3_key`, `bytes`, `crc32` (from the source zip), `sha256`, `source_url` (the zip it came from) and `license`.
Use it to select files by region or kind and to check what you downloaded.

## Checking files

Every source file has its size, the CRC32 from the source zip and the SHA-256 of our unpacked copy in the
release file list and in `metadata.json`. To check a download:

    shasum -a 256 <file>        # compare with sha256 in files.csv

Anyone who downloads the same zip from the source and unpacks it gets the same bytes.

## Licenses and credit

Each file keeps its source's terms. From `data/sources.csv`:

| Source | License or terms | Credit |
|---|---|---|
| USGS NAMSS | Public domain ("no restrictions on usage or publication"); DataCite lists CC0 1.0 for the DOI | Triezenberg, P.J., Hart, P.E., and Childs, J.R., 2016, National Archive of Marine Seismic Surveys (NAMSS), U.S. Geological Survey data release, https://doi.org/10.5066/F7930R7P |
| SARIG | CC BY 4.0 (CKAN license_id; the disclaimer file inside each zip says CC BY 3.0 AU) | Department for Energy and Mining, Government of South Australia (SARIG); keep the disclaimer file with redistributed copies |

The index tables and the per-survey metadata are CC BY 4.0 ([`data/LICENSE.md`](../data/LICENSE.md)). The
NAMSS surveys were shot under BOEM permits and released after the 25-year proprietary term.

## Caveats

- Volumes marked `include = decide` need a look before use; the reason is in `flags`. Release 0.1 holds three
  of them, two offshore California and one in the Beaufort Sea.
- A volume that segyio does not open with full geometry has gaps, a non-rectangular outline or repeated
  inline numbers. Its ranges in `metadata.json` come from the trace scan.
- The well outcomes are a lower bound. A well counts as a discovery only when BOEM's sands atlas names it as
  the discovery well of a sand.
- Well positions in the volume grids cover only the volumes whose coordinates we could fit
  (`seismic/grids.csv`).
- SARIG survey extents in `footprints.geojson` are the catalog's bounding boxes, and they are often coarse.

## Citation

Aiken, J. M. (2026). Open Subsurface Data, release 0.1. Veles Labs. (DOI to come.)

Cite each source you use as well, with the credit line above.

## Contact

John M. Aiken, Veles Labs, john@veleslabs.ai. Questions and problems: https://github.com/mnky9800n/open-subsurface-data/issues
