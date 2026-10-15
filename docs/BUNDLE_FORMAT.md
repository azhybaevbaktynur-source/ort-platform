# Instructions for the ort-platform agent: importing ORT question bundles (.zip)

You are changing **ort-platform** so it can import question bundles produced by
**ort-digitizer**. Today the platform imports questions from a CSV only and has no way to
receive the figures (geometry drawings, graphs, tables) that many questions need. After your
change, an admin uploads one `.zip`, and the platform creates the questions, uploads their
images to storage and links every image to the right question. This must work even if the zip
or the folders inside it have been renamed.

Read this whole file before starting. Section 1 is your task list; the rest is the reference.

## 1. Your tasks, in order

1. **Review the current platform first. Do not change anything yet.** Find and note:
   - the CSV upload entry point (UI page and/or API endpoint) and the CSV parser;
   - the question model/table, and what each of the 15 CSV columns maps to;
   - how `image_url` is stored and rendered today;
   - how the platform stores files (S3 or similar), builds public URLs, and runs DB transactions;
   - how math (`$…$` LaTeX), `<u>`/`<b>` tags and multi-line passages are rendered today.
2. **Write a short plan** of what you will change, based on that review.
3. **Add zip import** following section 5, reusing the existing CSV row parsing and validation.
4. **Keep plain CSV upload working** exactly as before (section 6).
5. **Run the acceptance tests** in section 8 with the sample bundle, and report the results.

## 2. What ort-digitizer delivers

For every source PDF, ort-digitizer writes `output/<source_id>/` containing two deliverable folders:

```
output/tsoomo19/
├── upload/
│   └── tsoomo19.zip          ← THE ONLY FILE THE PLATFORM RECEIVES
└── review/                   ← for people; never uploaded
    ├── manifest.json         ┐
    ├── questions.csv         ├ identical to the zip contents
    ├── images/…              ┘
    └── review_needed.csv     ← review report (only here, never in the zip)
```

(Other files in `output/<source_id>/` are the digitizer's working files. Ignore them.)

- **`upload/<source_id>.zip`** is what an admin uploads to the platform.
- **`review/`** is for a human reviewer: the same content, unzipped so it can be opened directly,
  plus `review_needed.csv`. That file lists every question whose source had a defect, and for
  each one says what the digitizer fixed (those questions ARE in `questions.csv`) or why it was
  held back (those are NOT in `questions.csv`). The platform does not import `review_needed.csv`.
  If someone zips the `review/` folder by mistake, the importer must still work and must skip
  `review_needed.csv`. Its header is different from the question CSV, so the discovery rule in
  section 5 already ignores it.

Sample for testing: `output/tsoomo19/upload/tsoomo19.zip` in the ort-digitizer repository
(150 questions, 14 images, Russian main test). If you work in another repository, ask the user
to copy that zip and this file into it.

## 3. Inside the zip

```
tsoomo19.zip                  ← file name is arbitrary; never rely on it
├── manifest.json             ← describes everything below (format version 1)
├── questions.csv             ← the 15 platform columns, one row per question
└── images/
    ├── tsoomo19_math_1_q03.png
    └── …
```

Image file names are `<source_id>_<section>_q<NN>.png`: unique per source, always PNG today.
`image_url` in the CSV holds the **bare file name**, not a folder path. This is deliberate: the
importer finds the image by name wherever it sits in the zip, so renamed folders do not break
the links.

Real uploads will not always be this tidy. People rename the zip, re-zip the folder (adding a
wrapper folder), zip on macOS (adding `__MACOSX/` and `._*` files), or put several sources
into one zip. The importer must handle all of these.

### 3.1 questions.csv

- UTF-8 without BOM, comma-separated, RFC 4180 quoting. Fields contain newlines (reading
  passages), commas and quotes, so use a real CSV parser, never line splitting.
- The header is exactly:
  `section,topic,difficulty,stem,column_a,column_b,option_a,option_b,option_c,option_d,option_e,correct_option,passage_text,image_url,explanation`
- One row is one question. Row order is the official test order.

| Column | Content |
|---|---|
| `section` | `math_1`, `math_2`, `analogies`, `reading`, `grammar`, or a subject test: `biology`, `chemistry`, `physics`, `math_subject`, `history`, `english`, `kyrgyz_lang_lit`, `russian_lang_lit` |
| `topic` | exact string from the official topic classifier (Russian or Kyrgyz list) |
| `difficulty` | `easy` / `medium` / `hard` |
| `stem` | question text; may be empty for `math_1` |
| `column_a`, `column_b` | only for `math_1` (quantity comparison); empty otherwise |
| `option_a`…`option_e` | answer options; all empty for `math_1`. `option_e` is empty when the question has 4 options (verbal sections always, some `math_2`) |
| `correct_option` | Latin `A`–`E`. For `math_1`: A = column A is larger, B = column B is larger, C = equal, D = cannot be determined |
| `passage_text` | reading passage, identical in every row of the same passage; empty otherwise |
| `image_url` | bare image file name (e.g. `tsoomo19_math_1_q03.png`) or empty |
| `explanation` | worked explanation, never empty |

The platform must render this content:
- math: LaTeX between `$…$` with single backslashes (`$\frac{3}{4}$`, `$35^\circ$`). Render with KaTeX or MathJax.
- `<u>…</u>` and `<b>…</b>` (grammar questions depend on underlining). Render these two tags and escape all other HTML.
- passages keep their printed line breaks, and every 5th line starts with `[5] `, `[10] `, …
  (questions cite line numbers). Show the line breaks.

### 3.2 manifest.json

```json
{
  "format": "ort-question-bundle",
  "format_version": 1,
  "source_id": "tsoomo19",
  "source_file": "input/ЦООМО19.pdf",
  "language": "ru",
  "created_at": "2026-10-12T03:44:17+00:00",
  "questions_file": "questions.csv",
  "images_dir": "images",
  "question_count": 150,
  "sections": {"math_1": 30, "math_2": 30, "analogies": 30, "reading": 30, "grammar": 30},
  "questions": [
    {"row": 3, "external_id": "tsoomo19:math_1:3", "section": "math_1", "q_num": "3",
     "source_page": 2, "image": "tsoomo19_math_1_q03.png", "fixed": false}
  ],
  "images": [
    {"file": "tsoomo19_math_1_q03.png", "path": "images/tsoomo19_math_1_q03.png",
     "mime": "image/png", "bytes": 2787, "sha256": "bcaca2e7…", "width": 420, "height": 75,
     "used_by_rows": [3]}
  ]
}
```

| Field | Meaning |
|---|---|
| `questions_file`, `images_dir` | paths relative to the folder that contains `manifest.json` (the **bundle root**), not to the zip root |
| `questions[].row` | 1-based data row in `questions.csv` (header not counted) |
| `questions[].external_id` | `<source_id>:<section>:<q_num>`, stable across rebuilds of the same source. Use it to make re-imports update questions instead of duplicating them |
| `questions[].image` | the image this row uses, or `null` (same value as the row's `image_url`) |
| `questions[].fixed` | the digitizer corrected a defect in the source question. Informational; store it if there is a natural place |
| `images[].sha256` | verify the file, and use it as the storage key (deduplication) |
| `images[].used_by_rows` | rows that use this image (an image may be shared) |

Ignore unknown extra fields. Refuse `format_version` greater than 1 with a clear message.
Bundles from ort-digitizer always contain a manifest. Zips made by hand may not, so section 5
has a fallback for that case.

## 4. Admin flow (what the user sees)

1. The admin chooses a `.zip` (or a `.csv`, as today) on the import page.
2. The platform validates everything and shows a **preview**: source ID, questions per section,
   images found, and every error or warning. Nothing is saved yet.
3. If there are errors, the import is blocked and the full list is shown (row number, column, message).
4. If it is clean, the admin confirms. The platform uploads the images and creates or updates
   the questions in one transaction, then shows the result: questions created/updated per
   section, and images uploaded or reused.
5. Re-uploading a corrected zip of the same source updates the existing questions (matched by
   `external_id`) instead of creating duplicates.

If the platform has no preview step today, it is fine to validate and import in one request,
as long as nothing is saved when any error exists.

## 5. Import algorithm

1. **Open the zip safely.**
   - Reject entries with absolute paths or `..` (zip slip).
   - Cap total uncompressed size and file count (suggested: 200 MB, 5,000 files).
   - Skip `__MACOSX/`, `._*`, `.DS_Store`, `Thumbs.db`.
2. **Find the bundle roots.**
   - Every folder, at any depth, containing a `manifest.json` with `"format": "ort-question-bundle"` is a bundle root.
   - If there is no manifest, every folder containing a `.csv` whose header equals the 15
     columns is a bundle root, and that CSV (any file name) is its questions file. CSVs with
     any other header, such as `review_needed.csv`, are ignored.
   - A zip may contain several bundle roots (several sources in one batch). Import each one.
   - No bundle root at all → error «no questions.csv / manifest.json found».
3. **Parse and validate the questions** with the existing CSV validation, plus:
   - the header must match exactly;
   - `correct_option` must be allowed for the section (`math_1`: A–D; 4-option rows: A–D; 5-option rows: A–E);
   - with a manifest: the row count must equal `question_count`, and row N's `section` and
     `image_url` must match `questions[N-1]`.
4. **Resolve every non-empty `image_url`** to a file in the zip:
   1. take the base name (accept `x.png`, `images/x.png`, or a path/URL ending in `x.png`);
   2. look in `<bundle root>/<images_dir>/` (from the manifest), or `<bundle root>/images/`;
   3. then in `<bundle root>/`;
   4. then anywhere in the zip, matching the base name case-insensitively;
   5. several matches with different content, or no match → error on that row.

   Then check each found image: if the manifest lists it, its `sha256` must match; it must
   decode as an image (png/jpg/webp); and its size must be under a cap (suggested 10 MB).
   Images in the zip that no row uses → warning, not error.
5. **Validate everything before writing anything.** Collect all errors across all bundles and
   report them together. If any error exists, save nothing.
6. **Upload the images** under a content-addressed key such as
   `question-images/<sha256>.<ext>`. Identical files share one key and are uploaded once, and
   an image from another source with the same name can never overwrite it. Skip the upload if
   the key already exists.
7. **Create or update the questions in one transaction**, replacing `image_url` with the
   storage URL from step 6.
   - With a manifest: upsert by `external_id` (add a unique column for it if the table has
     none). Questions of the same `source_id` that are missing from the new bundle are left
     alone; report them as a warning, never delete them silently.
   - Without a manifest: plain insert, as with CSV upload today.
   - If storage upload succeeded but the DB transaction fails, the orphaned images are
     harmless (content-addressed). No cleanup is required.
8. **Report** the results as described in section 4.

## 6. Backward compatibility

- Uploading a plain `.csv` works as today.
- In a plain CSV, a non-empty `image_url` that is not an `http(s)` URL means the image file is
  missing. Report «image not included — upload the zip bundle» instead of saving a broken link.
- An `image_url` that is already an `http(s)` URL is kept as it is, in both CSV and zip imports.

## 7. Things not to do

- Do not rely on the zip's file name or folder names.
- Do not import `review_needed.csv` or any CSV whose header is not the 15 columns.
- Do not store images under their original file names in a shared folder (collisions between sources).
- Do not save partial imports.
- Do not change the meaning of the 15 columns. If the platform needs a new field, take it from
  `manifest.json` rather than adding a CSV column, because ort-digitizer and other tools write
  this exact CSV.

## 8. Acceptance tests

Use `output/tsoomo19/upload/tsoomo19.zip`:

1. Upload as is → 150 questions (30 per section) and 14 images; math_1 q3 shows the number-line picture.
2. Rename the zip to `batch final (2).zip` → same result.
3. Unzip, rename the folder to `whatever`, zip the folder (adds a wrapper folder) → same result.
4. Compress it with macOS Finder (adds `__MACOSX/`) → same result, no junk imported.
5. Zip the `review/` folder instead (contains `review_needed.csv`) → same 150 questions; `review_needed.csv` ignored.
6. Delete `manifest.json`, rename `questions.csv` to `ort.csv` and `images/` to `pics/` → same questions and images (fallback discovery).
7. Change one `image_url` to `images/tsoomo19_math_1_q03.png` → still resolves.
8. Delete one image → import refused; the error names the row and the missing file; nothing saved.
9. Upload the same zip twice → still 150 questions (upsert by `external_id`) and 14 stored images.
10. Put two bundle folders in one zip (e.g. `tsoomo19/` and a copy with a different `source_id`) → both imported.
11. Upload a plain `questions.csv` → works as before.
12. Open a reading question and a grammar question with `<u>` → line breaks, `[5]` markers, underline and LaTeX render correctly.
