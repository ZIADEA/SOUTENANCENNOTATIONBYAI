from django import template

register = template.Library()


@register.filter
def get_item(d, key):
    """Permet d['key'] dans un template Django."""
    if not d:
        return ''
    try:
        return d.get(key, '')
    except AttributeError:
        return ''
