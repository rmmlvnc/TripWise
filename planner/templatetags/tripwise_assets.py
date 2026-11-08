"""Content-versioned assets prevent outdated browser styles after an update."""
import hashlib
from pathlib import Path
from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def versioned_static(name):
    url = static(name)
    source = finders.find(name)
    if source:
        digest = hashlib.sha256(Path(source).read_bytes()).hexdigest()[:12]
        return f"{url}{'&' if '?' in url else '?'}v={digest}"
    return url
