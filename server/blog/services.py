import json
from dataclasses import dataclass
from datetime import date
from functools import lru_cache

from django.conf import settings


BLOG_DATA_PATH = settings.PROJECT_ROOT / 'data' / 'blog' / 'posts.json'


@dataclass(frozen=True)
class BlogPost:
    slug: str
    title: str
    excerpt: str
    category: str
    published_at: date
    read_time: str
    tags: tuple[str, ...]
    sections: tuple[dict, ...]
    cover_eyebrow: str

    @property
    def published_label(self) -> str:
        return self.published_at.strftime('%d.%m.%Y')


def _build_post(payload: dict) -> BlogPost:
    return BlogPost(
        slug=payload['slug'],
        title=payload['title'],
        excerpt=payload['excerpt'],
        category=payload['category'],
        published_at=date.fromisoformat(payload['published_at']),
        read_time=payload['read_time'],
        tags=tuple(payload.get('tags', [])),
        sections=tuple(payload.get('sections', [])),
        cover_eyebrow=payload.get('cover_eyebrow', 'LexWheels Blog'),
    )


@lru_cache(maxsize=1)
def load_blog_posts() -> tuple[BlogPost, ...]:
    payload = json.loads(BLOG_DATA_PATH.read_text(encoding='utf-8'))
    posts = [_build_post(item) for item in payload.get('posts', [])]
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
            haystack = ' '.join((post.title, post.excerpt, post.category, ' '.join(post.tags))).lower()
            if normalized_query not in haystack:
                continue
        filtered.append(post)
    return filtered


def get_post_by_slug(slug: str) -> BlogPost | None:
    for post in load_blog_posts():
        if post.slug == slug:
            return post
    return None

