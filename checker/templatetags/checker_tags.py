from django import template

register = template.Library()


@register.filter
def sym_label(value):
    """Convert snake_case to Title Case."""
    return str(value).replace('_', ' ').title() if value else ""


@register.filter
def split(value, separator=","):
    """Split string by separator."""
    return str(value).split(separator) if value else []


@register.filter
def join_list(value, separator=", "):
    """Join list into string."""
    return separator.join(map(str, value)) if value else ""


@register.filter
def startswith(value, prefix):
    """Check if string starts with prefix."""
    return str(value).startswith(str(prefix)) if value else False


@register.filter
def endswith(value, suffix):
    """Check if string ends with suffix."""
    return str(value).endswith(str(suffix)) if value else False


@register.filter
def truncate_chars(value, length=30):
    """Truncate text with ellipsis."""
    value = str(value)
    return value[:int(length)] + "..." if len(value) > int(length) else value


@register.filter
def capitalize_words(value):
    """Capitalize each word."""
    return str(value).title() if value else ""


@register.filter
def is_list(value):
    """Check if object is a list."""
    return isinstance(value, list)
