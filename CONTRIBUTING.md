# Contributing

The index is meant to grow. If you know open subsurface data that is not in it, or you find a mistake in
it, please add it. Open an issue first, so we can agree on how a new source fits before you do the work.

## What can go in

- Data that anyone can download from the people who publish it. A source behind an account, a request form
  or a terms click-through can still be listed (`access` and `fetch_support` in `data/sources.csv` say
  so), but `osd` never signs in, never accepts terms and never handles a password.
- Sources whose license or terms are written down somewhere we can link to. Record them as the source
  states them, with the date you read them.
- Nothing from members-only repositories. Diskos is listed in `sources.csv` for comparison, and nothing in
  the index comes from it.
- The index, never the data. A pull request must not add SEG-Y, logs, core data or any other copy of a
  source's files: they stay where they are published and `osd` fetches them from there. Small tables we
  derive from public data (such as `data/cores/lily_holes.csv`) are fine, together with the script in
  `tools/` that makes them.

## Adding a source

1. Open an issue. Link the landing page and the terms, and say what the source holds, roughly how big it
   is, and how its files are downloaded (direct links, an API, a request, an account).
2. In the pull request:
   - Add a row to `data/sources.csv` with every column filled in (the columns are described in
     `data/README.md`). Set `checked` to the day you read the terms.
   - Add one or more entries to `data/citations.bib`, with `osd_source` set to the new `source_id`. Use the
     source's own suggested citation where it has one, and check any DOI on DataCite or Crossref.
   - If `osd` can download the files, add the file list. `data/files.csv` is written by
     `tools/build_index.py`, so don't edit it by hand. Write a function in `tools/` that returns the rows
     (`file_id`, `url`, `bytes`, `checksum`, `local_path`, `license` and the rest, see `data/README.md`)
     and call it from `build_index.py`, as `lily_rows` does for LILY. Use the checksum the source
     publishes (an MD5, an ETag) or the SHA-256 of your own download.
   - Register the source in `src/osd/adapters/__init__.py`. `Direct()` is enough when a file's size and
     checksum are all there is to check. Write a new adapter only when the files need more, such as the
     zip member checks that NAMSS and SARIG use.
3. Before you open the pull request, run these and paste the output into it:

        uv run osd sources
        uv run osd list --source <source_id>
        uv run osd fetch --file <a small file_id> --dest /tmp/osd-test
        uv run osd cite --dest /tmp/osd-test

## Fixing the index

A wrong license, a dead link, a checksum that no longer matches, a survey in the wrong region: open an
issue with the `file_id` or row, what is wrong, and a link that shows it. `sources.csv` and
`citations.bib` are written by hand, so a pull request can fix them directly. The other tables are built by
`tools/build_index.py`, so for those the issue is enough and we rebuild them.

## Code

Bug fixes and new commands are welcome. `osd` uses only the Python standard library and curl, so please
keep new dependencies out of it, or make them optional the way `deflate64` is.

## The S3 copy

The public bucket follows the index. A new source can go into a later release of the bucket when its
license allows copies to be passed on (the `redistribution` column).

## License

Code you contribute is under the MIT license, and additions to `data/` are under CC BY 4.0, the same as the
rest of the repository.
