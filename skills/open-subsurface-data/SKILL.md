---
name: open-subsurface-data
description: |
  Download open subsurface data (3D post-stack seismic from USGS NAMSS and SARIG, Gulf of Mexico well
  tables, check-shots, paleo tops, pay sands and open logs) from the original archives with the osd tool.
  Use when someone wants to get, size up, verify or cite this data, or wants the BOEM well logs that sit
  behind a free Login.gov account. Asks what they want and how much disk they have, estimates, fetches,
  verifies checksums and reports.
license: MIT
metadata:
  version: "0.1.0"
---

# Open subsurface data

The `osd` tool reads an index of open subsurface data and fetches files from the sources themselves. It
resumes broken downloads, checks sizes, ETags, SHA-256 and zip CRC32 values against the index, and never
changes a fetched file. Your job is to run it for the user, with their consent at each large step.

## Rules

- Never ask for, type, store or read a password, token or Login.gov credential. The BOEM File Request
  System needs the user's own Login.gov account. You only write the request lists and the steps.
- Never start a download larger than the user agreed to. Always run `estimate` first and show the result.
- Never fetch from Diskos or any members-only source. They are listed for comparison only.
- Do not edit files under the destination's `namss/`, `sarig/` and other source folders. They are the
  originals as fetched.
- Tell the user each source's license and credit line. `osd fetch` writes them to `ATTRIBUTION.md`, and the
  BibTeX to `CITATION.bib` (`osd cite --dest DIR` writes it again).

## 1. Set up

The tool needs `uv`, `curl` and Python 3.10 or later. Run the helper, which finds or clones the repository
and prints the tool version:

    bash scripts/setup.sh

If the repository is already checked out, run commands from its root with `uv run osd ...`. If `uv` is
missing, ask the user before installing it (https://docs.astral.sh/uv/getting-started/installation/).

## 2. Ask the user

Ask these in one message, with the short menu below so they can answer quickly:

1. Which data? Seismic volumes, well data, or both.
2. Which sources and regions? Show `uv run osd sources`. Regions for seismic: `gulf-of-mexico`, `pacific`,
   `alaska`, `south-australia`. Specific survey IDs are fine too (`--survey B-00-95-LA`).
3. Which volumes? `yes` (one checked full stack per survey, the default) or also `decide` (volumes that
   need a look: old stacks, extracted line sets, 2D-cubed regional volumes).
4. Where should files go, and how much disk can they spare there?
5. Do they want the SEG-Y unpacked from the zips (`--extract`)? This roughly doubles the disk needed.

Sizes for orientation (downloads, from the index): NAMSS `yes` archives 19.8 TB, of which the Gulf of
Mexico is 19.7 TB; NAMSS Pacific about 0.1 TB; SARIG `yes` 0.5 TB; Gulf well tables 0.2 GB. Unpacking the
SEG-Y adds roughly 1.6 times the zip size. Always run `estimate` for the real number.

## 3. Estimate

    uv run osd estimate --source namss --region gulf-of-mexico --dest /data/osd
    uv run osd list --source namss --region gulf-of-mexico --limit 20

Show the table. If it says DOES NOT FIT, or the total is above what the user said, offer a smaller
selection (a region, `--survey`, or `--max-gb` on fetch) and estimate again. Get a clear yes before fetching.

## 4. Fetch

    uv run osd fetch --source namss --region gulf-of-mexico --dest /data/osd --max-gb 500

- Large selections run for hours or days. Offer to run it in the background (for example in `tmux` or with
  `nohup`) and check on it later; reruns skip verified files and resume partial ones.
- SARIG zips sometimes use Deflate64. If extraction or `--deep` reports it, rerun with
  `uv run --extra deflate64 osd ...`.
- For a first test, fetch one small archive: `uv run osd fetch --survey B-88a-93-LA --dest /tmp/osd-test`
  (about 8.5 MB).

## 5. Verify

    uv run osd verify --dest /data/osd            # sizes, SHA-256, zip directories against the index
    uv run osd verify --dest /data/osd --deep     # also reads every zip member and checks its CRC32

A note that an ETag or a BOEM table checksum changed means the source published a new version. It is not a
broken download. Report it.

## 6. BOEM well logs (account needed)

    uv run osd frs plan --out /data/osd/boem-frs --wells after-survey

This writes `request_NNN.txt` lists (each under 24 GB, below BOEM's 25 GB limit), `request_files.csv` and
`HOW_TO_REQUEST.md`. Show the user `HOW_TO_REQUEST.md`. They sign in and upload each list themselves. When
BOEM's email link arrives and they have downloaded the zip, check it:

    uv run osd frs check --plan /data/osd/boem-frs --request 1 /path/to/downloaded.zip

## 7. Report

Tell the user, briefly:

- what was fetched: files, bytes, sources, the destination;
- what was verified, and any problem or changed-at-source note from the log (`<dest>/.osd/state.jsonl`);
- what was skipped and why (account needed, listed-only source, not enough disk);
- the licenses and credit lines (`<dest>/ATTRIBUTION.md`), and the BibTeX for publications (`<dest>/CITATION.bib`);
- the next step, if any (another region, the BOEM requests, `--deep` verification).
