from django.test import SimpleTestCase
from django.urls import reverse

from .services import _render_markdown, get_featured_post, load_blog_posts


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

    def test_blog_index_uses_featured_post_from_frontmatter(self):
        response = self.client.get(reverse('blog:index'))

        self.assertContains(response, 'Aktualizacja 05.04.2026')
        self.assertContains(response, 'images.unsplash.com')

    def test_blog_detail_exposes_previous_and_next_posts(self):
        response = self.client.get(reverse('blog:detail', args=['dlaczego-katalog-powinien-byc-szybszy-niz-instagram']))

        self.assertContains(response, 'Poprzedni wpis')
        self.assertContains(response, 'Następny wpis')
        self.assertContains(response, 'Jak czytać case mixy bez chaosu')
        self.assertContains(response, 'Jak budować kolekcję, żeby się w niej nie zgubić')


class BlogMarkdownTests(SimpleTestCase):
    def test_markdown_renderer_supports_links_formatting_and_lists(self):
        html = _render_markdown(
            'To jest **ważne** i ma [link](/blog/).\n\n- element jeden\n- element dwa\n\n> Cytat'
        )

        self.assertIn('<strong>ważne</strong>', html)
        self.assertIn('<a href="/blog/">link</a>', html)
        self.assertIn('<ul><li>element jeden</li><li>element dwa</li></ul>', html)
        self.assertIn('<blockquote>Cytat</blockquote>', html)

    def test_markdown_renderer_supports_code_blocks_and_images(self):
        html = _render_markdown(
            '```python\nprint("hi")\n```\n\n![Alt text](https://example.com/test.jpg)\n\nKod `inline`'
        )

        self.assertIn('<pre><code class="language-python">print(&quot;hi&quot;)</code></pre>', html)
        self.assertIn('<img src="https://example.com/test.jpg" alt="Alt text" loading="lazy">', html)
        self.assertIn('<code>inline</code>', html)

    def test_featured_post_prefers_frontmatter_flag(self):
        featured_post = get_featured_post(load_blog_posts())

        self.assertIsNotNone(featured_post)
        self.assertEqual(featured_post.slug, 'jak-czytac-case-mixy-bez-chaosu')
