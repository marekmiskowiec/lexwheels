import unittest

from main import merge_rows


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


if __name__ == '__main__':
    unittest.main()
