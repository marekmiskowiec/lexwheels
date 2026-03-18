from pathlib import Path
import hashlib
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import pandas as pd
import requests

# Environment settings:
pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', None)
pd.set_option('display.max_seq_items', None)
pd.set_option('display.max_colwidth', 500)
pd.set_option('expand_frame_repr', True)

URL = 'https://hotwheels.fandom.com/wiki/List_of_2022_Hot_Wheels'
API_URL = 'https://hotwheels.fandom.com/api.php'
PAGE_TITLE = 'List_of_2022_Hot_Wheels'
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BRAND = 'Hot Wheels'
CATEGORY = 'Mainline'
YEAR = 2022
OUTPUT_FILE = PROJECT_ROOT / 'data' / 'catalog' / 'hot-wheels' / 'mainline' / '2022.json'
IMAGE_DIR = PROJECT_ROOT / 'images'
REQUEST_TIMEOUT = 15
HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/122.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}


def slugify(value: str) -> str:
    normalized = re.sub(r'[^a-zA-Z0-9]+', '_', value.strip())
    return normalized.strip('_').lower() or 'item'


def fetch_page_html(url: str) -> str:
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else 'unknown'
        print(f'HTTP error while fetching the URL: {status_code}')
        if status_code == 403:
            print('The server rejected the request. This usually means anti-bot protection blocked the scraper.')
        raise SystemExit(1) from exc
    except requests.RequestException as exc:
        print(f"Failed to fetch the URL: {exc}")
        raise SystemExit(1) from exc

    return response.text


def fetch_page_via_api() -> str:
    params = {
        'action': 'parse',
        'page': PAGE_TITLE,
        'prop': 'text',
        'format': 'json',
        'formatversion': '2',
    }

    try:
        response = requests.get(
            API_URL,
            params=params,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        print(f'Failed to fetch page through the API: {exc}')
        raise SystemExit(1) from exc
    except ValueError as exc:
        print('The API returned an invalid JSON response.')
        raise SystemExit(1) from exc

    parse_data = payload.get('parse')
    html = parse_data.get('text') if parse_data else None
    if not html:
        print('The API response did not contain page HTML.')
        raise SystemExit(1)

    return html


def extract_photo_url(cell, base_url: str) -> str | None:
    photo_tag = cell.find('a')
    image_tag = photo_tag.find('img') if photo_tag else None
    alt_text = image_tag.get('alt', '').strip().lower() if image_tag else ''

    if not photo_tag or not image_tag or alt_text == 'image not available':
        return None

    href = photo_tag.get('href')
    return urljoin(base_url, href) if href else None


def build_image_path(row_data: dict, image_url: str) -> Path:
    parsed = urlparse(image_url)
    suffix = Path(parsed.path).suffix.lower() or '.jpg'
    if suffix not in {'.jpg', '.jpeg', '.png', '.webp', '.gif'}:
        suffix = '.jpg'

    stem = '_'.join(filter(None, [
        row_data.get('Number'),
        row_data.get('Model Name'),
    ]))
    url_hash = hashlib.md5(image_url.encode('utf-8')).hexdigest()[:10]
    filename = f'{slugify(stem)}_{url_hash}{suffix}'
    return IMAGE_DIR / filename


def download_image(image_url: str, destination: Path) -> str | None:
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        response = requests.get(image_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f'Failed to download image {image_url}: {exc}')
        return None

    destination.write_bytes(response.content)
    return destination.relative_to(PROJECT_ROOT).as_posix()


def attach_local_images(rows: list[dict]) -> list[dict]:
    for row in rows:
        image_url = row.get('Photo')
        row['Local Photo'] = None

        if not image_url:
            continue

        image_path = build_image_path(row, image_url)
        if not image_path.exists():
            local_path = download_image(image_url, image_path)
            row['Local Photo'] = local_path
            continue

        row['Local Photo'] = image_path.relative_to(PROJECT_ROOT).as_posix()

    return rows


def parse_rows(table, base_url: str) -> list[dict]:
    body = table.find('tbody') or table
    rows = []

    for row in body.find_all('tr'):
        columns = row.find_all('td')
        if not columns:
            continue

        rows.append({
            'Brand': BRAND,
            'Category': CATEGORY,
            'Year': YEAR,
            'Toy': columns[0].get_text(strip=True) if len(columns) > 0 else None,
            'Number': columns[1].get_text(strip=True) if len(columns) > 1 else None,
            'Model Name': columns[2].get_text(strip=True) if len(columns) > 2 else None,
            'Series': columns[3].get_text(strip=True) if len(columns) > 3 else None,
            'Series Number': columns[4].get_text(strip=True) if len(columns) > 4 else None,
            'Photo': extract_photo_url(columns[5], base_url) if len(columns) > 5 else None
        })

    return rows


def main() -> None:
    try:
        html = fetch_page_html(URL)
    except SystemExit:
        print('Falling back to the MediaWiki API.')
        html = fetch_page_via_api()

    soup = BeautifulSoup(html, 'html.parser')

    table = soup.find('table', class_='sortable wikitable')
    if not table:
        print("No table found with the class 'sortable wikitable'.")
        raise SystemExit(1)

    rows = parse_rows(table, URL)
    rows = attach_local_images(rows)
    df = pd.DataFrame(rows)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_json(OUTPUT_FILE, orient='records', force_ascii=False, indent=2)
    print(f"Data saved to {OUTPUT_FILE}")


if __name__ == '__main__':
    main()
