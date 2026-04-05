from dataclasses import dataclass
from datetime import date
from functools import lru_cache
import re

from django.conf import settings
from django.utils.html import escape
from django.utils.safestring import mark_safe


BLOG_POSTS_DIR = settings.PROJECT_ROOT / 'data' / 'blog' / 'posts'
INLINE_CODE_RE = re.compile(r'`([^`]+)`')
IMAGE_RE = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')
LINK_RE = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
BOLD_RE = re.compile(r'\*\*([^*]+)\*\*')
ITALIC_RE = re.compile(r'(?<!\*)\*([^*]+)\*(?!\*)')


def _normalize_link_target(raw_url: str) -> str:
    value = raw_url.strip()
    if value.startswith(('http://', 'https://', '/')):
        return value
    return '#'


def _render_inline_markdown(text: str) -> str:
    rendered = escape(text)
    code_tokens: list[str] = []

    def replace_code(match) -> str:
        code_tokens.append(f'<code>{escape(match.group(1))}</code>')
        return f'__CODE_TOKEN_{len(code_tokens) - 1}__'

    def replace_link(match) -> str:
        href = _normalize_link_target(match.group(2))
        attrs = ' target="_blank" rel="noreferrer"' if href.startswith(('http://', 'https://')) else ''
        return f'<a href="{escape(href)}"{attrs}>{escape(match.group(1))}</a>'

    rendered = INLINE_CODE_RE.sub(replace_code, rendered)
    rendered = IMAGE_RE.sub(
        lambda match: (
            f'<figure class="blog-figure"><img src="{escape(_normalize_link_target(match.group(2)))}" '
            f'alt="{escape(match.group(1))}" loading="lazy"></figure>'
        ),
        rendered,
    )
    rendered = LINK_RE.sub(replace_link, rendered)
    rendered = BOLD_RE.sub(r'<strong>\1</strong>', rendered)
    rendered = ITALIC_RE.sub(r'<em>\1</em>', rendered)

    for index, token in enumerate(code_tokens):
        rendered = rendered.replace(f'__CODE_TOKEN_{index}__', token)

    return rendered


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
    ordered_list_items: list[str] = []
    code_block_lines: list[str] = []
    code_block_language = ''
    in_code_block = False

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if paragraph_lines:
            content = ' '.join(line.strip() for line in paragraph_lines)
            blocks.append(f'<p>{_render_inline_markdown(content)}</p>')
            paragraph_lines = []

    def flush_list() -> None:
        nonlocal list_items
        if list_items:
            rendered_items = ''.join(f'<li>{_render_inline_markdown(item)}</li>' for item in list_items)
            blocks.append(f'<ul>{rendered_items}</ul>')
            list_items = []

    def flush_ordered_list() -> None:
        nonlocal ordered_list_items
        if ordered_list_items:
            rendered_items = ''.join(f'<li>{_render_inline_markdown(item)}</li>' for item in ordered_list_items)
            blocks.append(f'<ol>{rendered_items}</ol>')
            ordered_list_items = []

    def flush_quote() -> None:
        nonlocal quote_lines
        if quote_lines:
            content = ' '.join(line.strip() for line in quote_lines)
            blocks.append(f'<blockquote>{_render_inline_markdown(content)}</blockquote>')
            quote_lines = []

    def flush_code_block() -> None:
        nonlocal code_block_lines, code_block_language
        if code_block_lines:
            class_attr = f' class="language-{escape(code_block_language)}"' if code_block_language else ''
            code_html = escape('\n'.join(code_block_lines))
            blocks.append(f'<pre><code{class_attr}>{code_html}</code></pre>')
            code_block_lines = []
            code_block_language = ''

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith('```'):
            if in_code_block:
                flush_code_block()
                in_code_block = False
            else:
                flush_paragraph()
                flush_list()
                flush_ordered_list()
                flush_quote()
                code_block_language = stripped[3:].strip()
                in_code_block = True
            continue

        if in_code_block:
            code_block_lines.append(line)
            continue

        if not stripped:
            flush_paragraph()
            flush_list()
            flush_ordered_list()
            flush_quote()
            continue

        if stripped.startswith('### '):
            flush_paragraph()
            flush_list()
            flush_ordered_list()
            flush_quote()
            blocks.append(f'<h3>{escape(stripped[4:])}</h3>')
            continue

        if stripped.startswith('## '):
            flush_paragraph()
            flush_list()
            flush_ordered_list()
            flush_quote()
            blocks.append(f'<h2>{escape(stripped[3:])}</h2>')
            continue

        if stripped.startswith('# '):
            flush_paragraph()
            flush_list()
            flush_ordered_list()
            flush_quote()
            blocks.append(f'<h1>{escape(stripped[2:])}</h1>')
            continue

        if stripped.startswith('- '):
            flush_paragraph()
            flush_quote()
            flush_ordered_list()
            list_items.append(stripped[2:].strip())
            continue

        if stripped.startswith('> '):
            flush_paragraph()
            flush_list()
            flush_ordered_list()
            quote_lines.append(stripped[2:].strip())
            continue

        ordered_match = re.match(r'^\d+\.\s+(.*)$', stripped)
        if ordered_match:
            flush_paragraph()
            flush_quote()
            flush_list()
            ordered_list_items.append(ordered_match.group(1).strip())
            continue

        flush_list()
        flush_ordered_list()
        flush_quote()
        paragraph_lines.append(stripped)

    flush_paragraph()
    flush_list()
    flush_ordered_list()
    flush_quote()
    flush_code_block()

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
