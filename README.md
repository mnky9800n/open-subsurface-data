# Open Subsurface Data

An index of open subsurface data and a tool, `osd`, that fetches it from the original archives.

The index covers 3D post-stack seismic volumes from the USGS National Archive of Marine Seismic Surveys
(NAMSS) and from SARIG (South Australia), and Gulf of Mexico exploration wells tied to the NAMSS surveys:
where each well sits, whether it found pay, how much the field holds, and which digital logs BOEM holds for
it. It also lists the scientific ocean drilling data on Zenodo: downhole logs for 712 DSDP, ODP and IODP
holes from LDEO LogDB, and the IODP community's expedition data and reports. This repository holds the
index, a few derived tables and the tool.

We are also putting a checked copy of the seismic in one public S3 bucket, with the files exactly as the
sources shipped them and a summary of each volume's headers beside them. That copy is not live yet. What it
holds and how to read it: [`docs/dataset.md`](docs/dataset.md). A tutorial notebook:
[`notebooks/get-to-know-a-dataset.ipynb`](notebooks/get-to-know-a-dataset.ipynb). The list of files in the
first release: [`docs/starter_release.csv`](docs/starter_release.csv).

Status: index version 0.1.0, built 18 October 2026. The Zenodo DOI and the bucket address are still to come.

## What is in the index

<!-- counts: 18 October 2026; the Zenodo rows 30 October 2026 -->
| Part | Count | Size |
|---|---:|---:|
| NAMSS 3D volumes, include = yes / decide | 1,225 / 106 | 31.8 / 0.6 TB of SEG-Y; 19.8 TB of zips for the yes set |
| SARIG 3D volumes, include = yes / decide | 125 / 42 | 0.6 / 1.1 TB of SEG-Y |
| All volumes, in 1,137 surveys | 1,498 | 34.1 TB of SEG-Y, 21.3 TB of zips |
| Volumes with header summaries (our reference copy so far) | 245, from 201 surveys | 1.4 TB |
| Gulf volumes with a fitted inline/crossline grid (good / check) | 62 / 35 of 118 | |
| Gulf exploration wells (original holes, type E) | 15,136, of which 14,639 inside a NAMSS outline | |
| ... drilled after the first survey over them | 4,895, of which 1,233 (25%) found booked pay | |
| ... placed inside the grid of a volume we hold | 1,943 wells (1,037 drilled after the survey, 239 discoveries) | |
| BOEM digital log files for the 4,895 wells | 8,482 files, 348 GB (8,031 files and 33 GB under 100 MB each) | |
| Gulf well tables, check-shots, paleo, sands atlas, open logs | 45 files | 0.2 GB |
| Downhole logs from LDEO LogDB on Zenodo (DSDP, ODP, IODP) | 712 holes, 1,424 files | 196 GB |
| IODP community on Zenodo: expedition data, ODP and DSDP volumes | 3,416 records, 18,022 files | 2.8 TB |
| Other open sources listed (not yet per file) | NLOG, NOPIMS, WAPIMS, GEUS | about 35 TB of 3D by our counts |

Run `uv run osd sources` for the current numbers.

## Quick start

You need [uv](https://docs.astral.sh/uv/) and curl.

    git clone <this repository> open-subsurface-data
    cd open-subsurface-data
    uv run osd sources                                   # what is in the index
    uv run osd list --source namss --region gulf-of-mexico
    uv run osd estimate --source sarig --dest /data/osd  # disk needed against free space
    uv run osd fetch --survey B-88a-93-LA --dest /tmp/osd-test   # one small archive, 8.5 MB

Fetching resumes where it stopped. Every file is checked against the index: its size, the server's ETag
(NAMSS), its SHA-256 (well files) and the size and CRC32 of each zip member (SARIG, and NAMSS members we
have checked). Fetched files are made read-only and never changed. Add `--extract` to unpack the selected
SEG-Y volumes next to the zips, with each member's CRC32 checked as it is written.

    uv run osd verify --dest /data/osd           # check again later
    uv run osd verify --dest /data/osd --deep    # also read every zip member

Some SARIG zips use Deflate64. Run those with `uv run --extra deflate64 osd ...`.

## Commands

| Command | What it does |
|---|---|
| `osd sources` | Sources, access, license and how `osd` reaches each one. |
| `osd list [filters]` | Files a selection would fetch. `--volumes` lists the seismic volumes instead. |
| `osd estimate [filters] --dest DIR` | Download size, what is still missing at DIR, unpacked size with `--extract`, and whether it fits. |
| `osd fetch [filters] --dest DIR` | Download, resume, verify; writes `MANIFEST.tsv`, `ATTRIBUTION.md` and `CITATION.bib` at DIR. |
| `osd verify --dest DIR` | Check fetched files again. |
| `osd cite --dest DIR` | BibTeX for this repository and every source with files at DIR. `--source` adds sources you got another way; `--out` writes a file. |
| `osd frs plan --out DIR` | BOEM well logs: write lists of file IDs and the steps to request them. |
| `osd frs check --plan DIR --request N ZIP` | Match what BOEM sent against a list. Read only. |

Filters: `--source`, `--region` (gulf-of-mexico, pacific, alaska, south-australia), `--survey`, `--file`,
`--kind` (seismic, wells) and `--include` (yes by default; decide; all). Naming a survey or file overrides
`--include`.

## BOEM well logs need an account

BOEM's File Request System is free, but it needs a Login.gov account. `osd` never signs in and never sees a
password. `osd frs plan` writes `request_NNN.txt` files of public file IDs, each under BOEM's 25 GB limit,
and a `HOW_TO_REQUEST.md` with the steps. You upload the lists yourself; BOEM emails a link within a day.

## Claude skill

`skills/open-subsurface-data/SKILL.md` lets Claude run the tool for you: it asks which sources, regions and
how much disk, estimates, fetches, verifies and reports. Copy the folder into `~/.claude/skills/` or point
your agent at it.

## Index tables

All in `data/`, CSV unless noted, UTF-8.

| File | One row per | Main columns |
|---|---|---|
| `sources.csv` | source | access, fees, license, redistribution, credit line, DOI, how to get it |
| `citations.bib` | BibTeX entry | one or more per source, linked by `osd_source`; read by `osd cite` |
| `files.csv` | downloadable file | URL, bytes, checksum, regions, surveys, include, local path |
| `seismic/volumes.csv` | 3D volume | survey, region, year, stack type, domain, role, include, flags, members, size, file |
| `seismic/members.csv` | zip member | bytes, CRC32, SHA-256 where known, where the record came from |
| `seismic/headers.csv` | volume in our reference copy | header bytes, inline and crossline ranges, samples, sample interval, coordinates, CRS text, header fixes, problems |
| `seismic/grids.csv` | Gulf volume | fitted inline/crossline to x/y transform, CRS, fit error, quality |
| `seismic/footprints.geojson` | survey or volume | NAMSS outlines, grid corners from trace headers, SARIG catalog extents |
| `wells/gulf_exploration_wells.csv` | exploration well | BOEM header fields, outcome, field size, surveys over it, check-shot and paleo flags, BOEM log counts |
| `wells/gulf_well_volume_ties.csv` | well and volume | well position in the volume's x/y and inline/crossline grid, inside or outside |
| `wells/boem_frs_raw_logs.csv` | BOEM digital log file | file ID, API, size, run and release dates |

`include` comes from our selection. `yes` is a checked migrated full stack. `decide` needs a look (old
stacks the catalog does not call migrated, extracted line sets, SARIG Cooper Basin 2D-cubed volumes).
`role` is `primary` for one full stack per survey and `additional` for partial stacks and second
migrations. NAMSS sizes per volume are rounded in the NAMSS catalog; archive sizes are exact.

## Licenses

- Code (`src/`, `tools/`, `skills/`): MIT, see `LICENSE`. MIT is short, widely understood, and lets anyone
  reuse the fetch code inside other tools, including commercial ones. A patent grant (Apache-2.0) adds
  little for a downloader.
- Index tables (`data/`): CC BY 4.0, see `data/LICENSE.md`.
- The data themselves keep their sources' terms: NAMSS public domain; SARIG CC BY 4.0; BOEM public
  information; NETL EDX and LDEO per data set; LogDB on Zenodo CC0;
  the IODP records on Zenodo per record. `osd fetch` writes the credit lines to `ATTRIBUTION.md`.

## Rebuilding the index

The index is built from the corpus crawl (`seismic-corpus`), outputs from our reference copy of the data
(`tools/build_index_lambda.py`, `tools/frs_subset_lambda.py`), the Gulf well work and the Zenodo file lists
in `tools/` (`tools/zenodo_community.py` writes them). See the docstring of `tools/build_index.py`. Nothing in the index comes from Diskos or any members-only repository.

## Citation

Cite this repository and each source you use. `osd cite` writes the BibTeX for both:

    uv run osd cite --dest /data/osd --out references.bib        # the sources of everything fetched there
    uv run osd cite --source boem-frs,lily                        # sources you got another way

`osd fetch` also writes `CITATION.bib` next to the files. The entries come from `data/citations.bib`. Web
sources without a DOI get the day you fetched them. `CITATION.cff` is an example citation for the repository
alone. The Zenodo DOI is still to come.

## Contributing

To add a source or fix the index, see [`CONTRIBUTING.md`](CONTRIBUTING.md).

Contact: John M. Aiken, Veles Labs, john@veleslabs.ai
