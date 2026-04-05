from django.http import Http404
from django.views.generic import TemplateView

from .services import filter_posts, get_featured_post, get_post_by_slug, list_categories, load_blog_posts


class BlogListView(TemplateView):
    template_name = 'blog/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        all_posts = load_blog_posts()
        query = self.request.GET.get('q', '').strip()
        category = self.request.GET.get('category', '').strip()
        filtered_posts = filter_posts(all_posts, query=query, category=category)
        featured_post = get_featured_post(filtered_posts)
        remaining_posts = [post for post in filtered_posts if featured_post and post.slug != featured_post.slug]

        context.update({
            'posts': filtered_posts,
            'featured_post': featured_post,
            'remaining_posts': remaining_posts,
            'query': query,
            'selected_category': category,
            'category_options': list_categories(all_posts),
            'total_posts': len(all_posts),
        })
        return context


class BlogDetailView(TemplateView):
    template_name = 'blog/detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        post = get_post_by_slug(kwargs['slug'])
        if not post:
            raise Http404('Nie znaleziono wpisu.')

        all_posts = list(load_blog_posts())
        related_posts = [item for item in all_posts if item.slug != post.slug and item.category == post.category][:3]
        post_index = next((index for index, item in enumerate(all_posts) if item.slug == post.slug), -1)
        previous_post = all_posts[post_index - 1] if post_index > 0 else None
        next_post = all_posts[post_index + 1] if 0 <= post_index < len(all_posts) - 1 else None

        context.update({
            'post': post,
            'related_posts': related_posts,
            'previous_post': previous_post,
            'next_post': next_post,
        })
        return context
