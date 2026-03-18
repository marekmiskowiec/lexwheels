import argparse
import json
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

API_URL = 'https://hotwheels.fandom.com/api.php'
PROJECT_ROOT = Path(__file__).resolve().parent.parent
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


def build_page_title(brand: str, year: int, line: str) -> str:
    if brand == 'Hot Wheels' and line == 'Mainline':
        return f'List_of_{year}_Hot_Wheels'
    raise ValueError(f'Unsupported page mapping for brand={brand!r}, line={line!r}')


def build_dataset_path(brand: str, line: str, year: int, set_name: str = '') -> Path:
    base_path = (
        PROJECT_ROOT
        / 'data'
        / 'catalog'
        / slugify(brand).replace('_', '-')
        / slugify(line).replace('_', '-')
    )
    if set_name:
        return base_path / str(year) / f"{slugify(set_name).replace('_', '-')}.json"
    return base_path / f'{year}.json'


def build_image_dir(brand: str, line: str, year: int, set_name: str = '') -> Path:
    base_dir = (
        IMAGE_DIR
        / slugify(brand).replace('_', '-')
        / slugify(line).replace('_', '-')
        / str(year)
    )
    if set_name:
        return base_dir / slugify(set_name).replace('_', '-')
    return base_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Scrape Hot Wheels catalog data into structured JSON datasets.')
    parser.add_argument('--brand', default='Hot Wheels', help='Brand label stored in the dataset.')
    parser.add_argument('--line', default='Mainline', help='Line/category label stored in the dataset.')
    parser.add_argument('--year', type=int, default=2022, help='Dataset year and fandom page year.')
    parser.add_argument('--url', help='Override the source page URL.')
    parser.add_argument('--page-title', help='Override the MediaWiki page title.')
    parser.add_argument('--output', help='Override the destination JSON path.')
    parser.add_argument('--set-name', help='Optional set name used for nested dataset paths like <line>/<year>/<set>.json.')
    parser.add_argument(
        '--include-section',
        action='append',
        default=[],
        help='Only parse tables that belong to matching section titles. Can be repeated.',
    )
    parser.add_argument(
        '--update-existing-line',
        action='store_true',
        help='Merge the new scrape into the existing dataset file instead of overwriting it.',
    )
    parser.add_argument('--skip-image-downloads', action='store_true', help='Do not download local images, keep only remote URLs.')
    return parser.parse_args()


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


def fetch_page_via_api(page_title: str) -> str:
    params = {
        'action': 'parse',
        'page': page_title,
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


def extract_headers(table) -> list[str]:
    body = table.find('tbody') or table
    header_row = body.find('tr')
    if not header_row:
        return []
    return [th.get_text(' ', strip=True) for th in header_row.find_all('th')]


def is_supported_catalog_headers(headers: list[str]) -> bool:
    header_set = set(headers)
    return (
        {'Toy', 'Number', 'Model Name'}.issubset(header_set)
        or {'Series #', 'Toy #', 'Casting Name'}.issubset(header_set)
        or {'Col #', 'Toy #', 'Casting Name'}.issubset(header_set)
        or {'Toy #', 'Col.#', 'Mix', 'Model Name'}.issubset(header_set)
    )


def get_table_section_title(table) -> str:
    prev = table
    while prev:
        prev = prev.find_previous(['h2', 'h3', 'h4'])
        if not prev:
            break
        text = prev.get_text(' ', strip=True)
        if text:
            return re.sub(r'\s*\[\s*\]\s*$', '', text).strip()
    return ''


def find_catalog_tables(soup, include_sections: list[str] | None = None) -> list[tuple[object, str]]:
    include_sections = [section.strip().lower() for section in (include_sections or []) if section.strip()]
    matches = []
    for table in soup.find_all('table'):
        headers = extract_headers(table)
        if not is_supported_catalog_headers(headers):
            continue
        section_title = get_table_section_title(table)
        if include_sections and not any(section in section_title.lower() for section in include_sections):
            continue
        matches.append((table, section_title))
    return matches


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
    return build_image_dir(
        str(row_data.get('Brand', 'Hot Wheels')),
        str(row_data.get('Category', 'Mainline')),
        int(row_data.get('Year') or 0),
        str(row_data.get('Image Set', '') or ''),
    ) / filename


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


def build_row_key(row: dict) -> str:
    parts = [
        str(row.get('Toy', '') or '').strip(),
        str(row.get('Number', '') or '').strip(),
        str(row.get('Model Name', '') or '').strip(),
        str(row.get('Series', '') or '').strip(),
        str(row.get('Series Number', '') or '').strip(),
    ]
    return '|'.join(parts)


def read_existing_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return []
    return payload if isinstance(payload, list) else []


def merge_rows(scraped_rows: list[dict], existing_rows: list[dict]) -> list[dict]:
    existing_by_key = {build_row_key(row): row for row in existing_rows}
    merged_rows = []
    used_keys = set()

    for row in scraped_rows:
        key = build_row_key(row)
        existing_row = existing_by_key.get(key, {})
        merged_row = dict(existing_row)
        for field, value in row.items():
            if value not in (None, ''):
                merged_row[field] = value
            else:
                merged_row.setdefault(field, value)
        merged_rows.append(merged_row)
        used_keys.add(key)

    for key, row in existing_by_key.items():
        if key not in used_keys:
            merged_rows.append(row)

    return merged_rows


def attach_local_images(rows: list[dict], download_images: bool = True) -> list[dict]:
    for row in rows:
        default_image_url = row.get('Photo')
        carded_image_url = row.get('Carded Photo') or default_image_url
        loose_image_url = row.get('Loose Photo') or default_image_url
        category = str(row.get('Category') or '').strip().lower()
        short_card_image_url = carded_image_url if category not in {'premium', 'semi premium', 'xl'} else None
        row['Photo'] = default_image_url
        row['Local Photo'] = row.get('Local Photo')
        row['Short Card Photo'] = short_card_image_url
        row['Long Card Photo'] = carded_image_url
        row['Loose Photo'] = loose_image_url
        row['Short Card Local Photo'] = row.get('Short Card Local Photo')
        row['Long Card Local Photo'] = row.get('Long Card Local Photo')
        row['Loose Local Photo'] = row.get('Loose Local Photo')

        if not download_images:
            continue

        packaging_sources = (
            ('Short Card Local Photo', short_card_image_url),
            ('Long Card Local Photo', carded_image_url),
            ('Loose Local Photo', loose_image_url),
        )
        downloaded_paths = {}
        for local_key, image_url in packaging_sources:
            if not image_url:
                continue
            existing_local_path = row.get(local_key)
            if existing_local_path and (PROJECT_ROOT / existing_local_path).exists():
                continue
            if image_url not in downloaded_paths:
                image_path = build_image_path(row, image_url)
                if image_path.exists():
                    downloaded_paths[image_url] = image_path.relative_to(PROJECT_ROOT).as_posix()
                else:
                    downloaded_paths[image_url] = download_image(image_url, image_path)
            row[local_key] = downloaded_paths[image_url]

        row['Local Photo'] = row.get('Short Card Local Photo') or row.get('Loose Local Photo')

    return rows


def parse_rows(
    table,
    base_url: str,
    brand: str,
    category: str,
    year: int,
    series_label: str = '',
    image_set_label: str = '',
) -> list[dict]:
    body = table.find('tbody') or table
    headers = extract_headers(table)
    header_index = {header: idx for idx, header in enumerate(headers)}
    rows = []

    for row in body.find_all('tr')[1:]:
        columns = row.find_all('td')
        if not columns:
            continue

        if {'Toy', 'Number', 'Model Name'}.issubset(set(headers)):
            rows.append({
                'Brand': brand,
                'Category': category,
                'Year': year,
                'Image Set': image_set_label,
                'Toy': columns[header_index['Toy']].get_text(strip=True) if 'Toy' in header_index else None,
                'Number': columns[header_index['Number']].get_text(strip=True) if 'Number' in header_index else None,
                'Model Name': columns[header_index['Model Name']].get_text(strip=True) if 'Model Name' in header_index else None,
                'Series': columns[header_index['Series']].get_text(strip=True) if 'Series' in header_index else series_label,
                'Series Number': columns[header_index['Series Number']].get_text(strip=True) if 'Series Number' in header_index else '',
                'Photo': extract_photo_url(columns[header_index['Photo']], base_url) if 'Photo' in header_index else None,
            })
            continue

        if {'Toy #', 'Casting Name'}.issubset(set(headers)) and ('Series #' in header_index or 'Col #' in header_index or 'Col.#' in header_index):
            carded_header = 'Photo Carded' if 'Photo Carded' in header_index else 'Photo Card' if 'Photo Card' in header_index else None
            loose_header = 'Photo Loose' if 'Photo Loose' in header_index else 'Photo Open' if 'Photo Open' in header_index else None
            carded_photo = extract_photo_url(columns[header_index[carded_header]], base_url) if carded_header else None
            loose_photo = extract_photo_url(columns[header_index[loose_header]], base_url) if loose_header else None
            collection_number_header = 'Series #' if 'Series #' in header_index else 'Col #' if 'Col #' in header_index else 'Col.#'
            rows.append({
                'Brand': brand,
                'Category': category,
                'Year': year,
                'Image Set': image_set_label,
                'Toy': columns[header_index['Toy #']].get_text(strip=True) if 'Toy #' in header_index else None,
                'Number': columns[header_index[collection_number_header]].get_text(strip=True) if collection_number_header in header_index else None,
                'Model Name': columns[header_index['Casting Name']].get_text(strip=True) if 'Casting Name' in header_index else None,
                'Series': series_label or category,
                'Series Number': columns[header_index[collection_number_header]].get_text(strip=True) if collection_number_header in header_index else '',
                'Photo': carded_photo or loose_photo,
                'Carded Photo': carded_photo,
                'Loose Photo': loose_photo,
            })
            continue

        if {'Toy #', 'Col.#', 'Mix', 'Model Name'}.issubset(set(headers)):
            carded_photo = extract_photo_url(columns[header_index['Photo Card']], base_url) if 'Photo Card' in header_index else None
            loose_photo = extract_photo_url(columns[header_index['Photo Open']], base_url) if 'Photo Open' in header_index else None
            rows.append({
                'Brand': brand,
                'Category': category,
                'Year': year,
                'Image Set': image_set_label,
                'Toy': columns[header_index['Toy #']].get_text(strip=True),
                'Number': columns[header_index['Col.#']].get_text(strip=True),
                'Model Name': columns[header_index['Model Name']].get_text(strip=True),
                'Series': series_label or category,
                'Series Number': columns[header_index['Col.#']].get_text(strip=True),
                'Photo': carded_photo or loose_photo,
                'Carded Photo': carded_photo,
                'Loose Photo': loose_photo,
            })

    return rows


def main() -> None:
    args = parse_args()
    page_title = args.page_title or build_page_title(args.brand, args.year, args.line)
    url = args.url or f'https://hotwheels.fandom.com/wiki/{page_title}'
    output_file = Path(args.output) if args.output else build_dataset_path(args.brand, args.line, args.year, args.set_name or '')

    try:
        html = fetch_page_html(url)
    except SystemExit:
        print('Falling back to the MediaWiki API.')
        html = fetch_page_via_api(page_title)

    soup = BeautifulSoup(html, 'html.parser')

    table_matches = find_catalog_tables(soup, include_sections=args.include_section)
    if not table_matches:
        print('No supported catalog table found on the page.')
        raise SystemExit(1)

    rows = []
    for table, section_title in table_matches:
        effective_series_label = args.set_name or section_title
        if args.set_name and section_title:
            effective_series_label = f'{args.set_name} - {section_title}'
        rows.extend(
            parse_rows(
                table,
                url,
                args.brand,
                args.line,
                args.year,
                effective_series_label,
                args.set_name or '',
            )
        )
    if args.update_existing_line:
        rows = merge_rows(rows, read_existing_rows(output_file))
    rows = attach_local_images(rows, download_images=not args.skip_image_downloads)
    df = pd.DataFrame(rows)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    df.to_json(output_file, orient='records', force_ascii=False, indent=2)
    print(f'Data saved to {output_file}')


if __name__ == '__main__':
    main()
