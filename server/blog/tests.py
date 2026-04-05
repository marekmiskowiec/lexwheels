from django.test import SimpleTestCase
from django.urls import reverse


class BlogViewTests(SimpleTestCase):
    def test_blog_index_renders_posts(self):
        response = self.client.get(reverse('blog:index'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Blog LexWheels')
        self.assertContains(response, 'Jak czytać case mixy bez chaosu')

    def test_blog_index_can_filter_by_category(self):
        response = self.client.get(reverse('blog:index'), {'category': 'Poradniki'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Jak czytać case mixy bez chaosu')
        self.assertNotContains(response, 'Dlaczego katalog powinien być szybszy niż Instagram')

    def test_blog_detail_renders_post(self):
        response = self.client.get(reverse('blog:detail', args=['jak-czytac-case-mixy-bez-chaosu']))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Jak czytać case mixy bez chaosu')
        self.assertContains(response, 'Najpierw patrz na strukturę rocznika')

    def test_blog_detail_returns_404_for_unknown_slug(self):
        response = self.client.get(reverse('blog:detail', args=['missing-post']))

        self.assertEqual(response.status_code, 404)
