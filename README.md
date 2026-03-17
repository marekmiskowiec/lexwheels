# LexWheels

Python scraper and simple web preview for the Hot Wheels 2022 list from Fandom.

## Project Structure

```text
lexwheels/
  data/
    hot_wheels_data.json
  images/
  scraper/
    main.py
    requirements.txt
  web/
    index.html
```

- `scraper/` contains the Python scraper.
- `data/` contains the generated JSON dataset.
- `images/` contains locally downloaded model images.
- `web/` contains the static HTML preview.

## What The Scraper Saves

Each record in `data/hot_wheels_data.json` includes:

- `Toy`
- `Number`
- `Model Name`
- `Series`
- `Series Number`
- `Photo`
- `Local Photo`

`Photo` is the original remote image URL.

`Local Photo` is the relative path to the downloaded local image in `images/`.

## Requirements

Install dependencies from:

```bash
pip install -r scraper/requirements.txt
```

## Run The Scraper

From the project root:

```bash
python3 scraper/main.py
```

The scraper:

- fetches the Hot Wheels page,
- falls back to the MediaWiki API if the normal page returns `403`,
- parses the table,
- downloads images locally,
- writes the output JSON to `data/hot_wheels_data.json`.

## Run The Web Preview

Start a simple local server in the project root:

```bash
python3 -m http.server
```

Then open:

```text
http://localhost:8000/web/index.html
```

The preview page loads data from `data/hot_wheels_data.json` and displays the models in a searchable table with local images.

## Notes

- Fandom may block direct frontend requests with `403`, which is why the scraper includes API fallback logic.
- Images are stored locally so the preview does not depend on external hotlinked assets.
- The current dataset is based on the 2022 Hot Wheels list page.

## Next Steps

If this project grows into a collector web app, a good next direction is:

- move model data into a database,
- add users and collections,
- keep the scraper as a separate data-ingestion part inside the same repo.
