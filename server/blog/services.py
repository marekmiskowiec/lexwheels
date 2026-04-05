from dataclasses import dataclass
from datetime import date
from functools import lru_cache

from django.conf import settings
from django.utils.html import escape
from django.utils.safestring import mark_safe


BLOG_POSTS_DIR = settings.PROJECT_ROOT / 'data' / 'blog' / 'posts'


@dataclass(frozen=True)
class BlogPost:
    slug: str
    title: str
    excerpt: str
    category: str
    published_at: date
    read_time: str
    tags: tuple[str, ...]
    cover_eyebrow: str
    body_markdown: str
    body_html: str

    @property
    def published_label(self) -> str:
        return self.published_at.strftime('%d.%m.%Y')


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith('---\n'):
        raise ValueError('Blog post must start with frontmatter.')

    _, remainder = text.split('---\n', 1)
    frontmatter_text, body = remainder.split('\n---\n', 1)

    metadata: dict[str, object] = {}
    current_list_key = ''
    for raw_line in frontmatter_text.splitlines():
        if not raw_line.strip():
            continue
        if raw_line.startswith('  - ') or raw_line.startswith('- '):
            if not current_list_key:
                raise ValueError('List item without list key in frontmatter.')
            metadata.setdefault(current_list_key, [])
            metadata[current_list_key].append(raw_line.split('- ', 1)[1].strip())
            continue

        key, value = raw_line.split(':', 1)
        key = key.strip()
        value = value.strip()
        if value:
            metadata[key] = value
            current_list_key = ''
        else:
            metadata[key] = []
            current_list_key = key

    return metadata, body.strip()


def _render_markdown(markdown_text: str) -> str:
    blocks: list[str] = []
    paragraph_lines: list[str] = []
    list_items: list[str] = []
    quote_lines: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if paragraph_lines:
            content = ' '.join(line.strip() for line in paragraph_lines)
            blocks.append(f'<p>{escape(content)}</p>')
            paragraph_lines = []

    def flush_list() -> None:
        nonlocal list_items
        if list_items:
            rendered_items = ''.join(f'<li>{escape(item)}</li>' for item in list_items)
            blocks.append(f'<ul>{rendered_items}</ul>')
            list_items = []

    def flush_quote() -> None:
        nonlocal quote_lines
        if quote_lines:
            content = ' '.join(line.strip() for line in quote_lines)
            blocks.append(f'<blockquote>{escape(content)}</blockquote>')
            quote_lines = []

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if not stripped:
            flush_paragraph()
            flush_list()
            flush_quote()
            continue

        if stripped.startswith('## '):
            flush_paragraph()
            flush_list()
            flush_quote()
            blocks.append(f'<h2>{escape(stripped[3:])}</h2>')
            continue

        if stripped.startswith('# '):
            flush_paragraph()
            flush_list()
            flush_quote()
            blocks.append(f'<h1>{escape(stripped[2:])}</h1>')
            continue

        if stripped.startswith('- '):
            flush_paragraph()
            flush_quote()
            list_items.append(stripped[2:].strip())
            continue

        if stripped.startswith('> '):
            flush_paragraph()
            flush_list()
            quote_lines.append(stripped[2:].strip())
            continue

        flush_list()
        flush_quote()
        paragraph_lines.append(stripped)

    flush_paragraph()
    flush_list()
    flush_quote()

    return mark_safe('\n'.join(blocks))


def _build_post(path) -> BlogPost:
    metadata, body_markdown = _parse_frontmatter(path.read_text(encoding='utf-8'))
    return BlogPost(
        slug=path.stem,
        title=str(metadata['title']),
        excerpt=str(metadata['excerpt']),
        category=str(metadata['category']),
        published_at=date.fromisoformat(str(metadata['published_at'])),
        read_time=str(metadata['read_time']),
        tags=tuple(metadata.get('tags', [])),
        cover_eyebrow=str(metadata.get('cover_eyebrow', 'LexWheels Blog')),
        body_markdown=body_markdown,
        body_html=_render_markdown(body_markdown),
    )


@lru_cache(maxsize=1)
def load_blog_posts() -> tuple[BlogPost, ...]:
    posts = [_build_post(path) for path in BLOG_POSTS_DIR.glob('*.md')]
    return tuple(sorted(posts, key=lambda item: item.published_at, reverse=True))


def list_categories(posts: tuple[BlogPost, ...]) -> list[dict]:
    counts: dict[str, int] = {}
    for post in posts:
        counts[post.category] = counts.get(post.category, 0) + 1
    return [
        {'name': name, 'count': counts[name]}
        for name in sorted(counts)
    ]


def filter_posts(posts: tuple[BlogPost, ...], query: str = '', category: str = '') -> list[BlogPost]:
    normalized_query = query.strip().lower()
    normalized_category = category.strip()
    filtered = []
    for post in posts:
        if normalized_category and post.category != normalized_category:
            continue
        if normalized_query:
            haystack = ' '.join((
                post.title,
                post.excerpt,
                post.category,
                post.body_markdown,
                ' '.join(post.tags),
            )).lower()
            if normalized_query not in haystack:
                continue
        filtered.append(post)
    return filtered


def get_post_by_slug(slug: str) -> BlogPost | None:
    for post in load_blog_posts():
        if post.slug == slug:
            return post
    return None
