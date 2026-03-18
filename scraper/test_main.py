import unittest

from bs4 import BeautifulSoup

from main import build_image_path, find_catalog_tables, merge_rows


class UpdateExistingLineTests(unittest.TestCase):
    def test_merge_rows_preserves_existing_values_when_scrape_is_empty(self):
        existing_rows = [{
            'Brand': 'Hot Wheels',
            'Category': 'Mainline',
            'Year': 2026,
            'Toy': 'ABC',
            'Number': '001',
            'Model Name': 'Test Car',
            'Series': 'Series A',
            'Series Number': '1/5',
            'Photo': 'https://example.com/old-card.jpg',
            'Local Photo': 'images/old-card.jpg',
            'Long Card Photo': 'https://example.com/old-card.jpg',
            'Long Card Local Photo': 'images/old-card.jpg',
            'Loose Photo': 'https://example.com/old-loose.jpg',
            'Loose Local Photo': 'images/old-loose.jpg',
        }]
        scraped_rows = [{
            'Brand': 'Hot Wheels',
            'Category': 'Mainline',
            'Year': 2026,
            'Toy': 'ABC',
            'Number': '001',
            'Model Name': 'Test Car',
            'Series': 'Series A',
            'Series Number': '1/5',
            'Photo': '',
            'Long Card Photo': '',
            'Loose Photo': '',
        }]

        merged = merge_rows(scraped_rows, existing_rows)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['Local Photo'], 'images/old-card.jpg')
        self.assertEqual(merged[0]['Long Card Local Photo'], 'images/old-card.jpg')
        self.assertEqual(merged[0]['Loose Local Photo'], 'images/old-loose.jpg')

    def test_merge_rows_keeps_existing_unmatched_rows(self):
        existing_rows = [{
            'Toy': 'ABC',
            'Number': '001',
            'Model Name': 'Existing Car',
            'Series': 'Series A',
            'Series Number': '1/5',
        }]
        scraped_rows = [{
            'Toy': 'DEF',
            'Number': '002',
            'Model Name': 'New Car',
            'Series': 'Series B',
            'Series Number': '2/5',
        }]

        merged = merge_rows(scraped_rows, existing_rows)

        self.assertEqual(len(merged), 2)
        self.assertEqual({row['Model Name'] for row in merged}, {'Existing Car', 'New Car'})

    def test_find_catalog_tables_can_filter_by_section_titles(self):
        soup = BeautifulSoup(
            '''
            <h3>Mix 1</h3>
            <table class="wikitable sortable">
              <tr><th>Col #</th><th>Toy #</th><th>Casting Name</th><th>Photo Loose</th><th>Photo Carded</th></tr>
              <tr><td>1/5</td><td>ABC</td><td>Car One</td><td></td><td></td></tr>
            </table>
            <h3>Premium Bundle 1</h3>
            <table class="wikitable sortable">
              <tr><th>Toy #</th><th>Casting Name</th><th>Photo Loose</th><th>Photo Boxed</th></tr>
              <tr><td>DEF</td><td>Bundle Car</td><td></td><td></td></tr>
            </table>
            ''',
            'html.parser',
        )

        tables = find_catalog_tables(soup, ['mix 1'])

        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0][1], 'Mix 1')

    def test_build_image_path_uses_set_subdirectory_when_present(self):
        row = {
            'Brand': 'Hot Wheels',
            'Category': 'Premium',
            'Year': 2025,
            'Image Set': 'Fast & Furious Premium Series',
            'Number': '1/5',
            'Model Name': 'Mazda RX-7 FD',
        }

        image_path = build_image_path(row, 'https://example.com/rx7.jpg')

        self.assertIn('images/hot-wheels/premium/2025/fast-furious-premium-series/', image_path.as_posix())


if __name__ == '__main__':
    unittest.main()
