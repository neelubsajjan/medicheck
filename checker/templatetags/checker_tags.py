from django import template

register = template.Library()


@register.filter(name='sym_label')
def sym_label(value):
    """
    Convert symptom names from snake_case to Title Case.

    Example:
    'body_ache' -> 'Body Ache'
    """
    if not value:
        return ""
    return value.replace('_', ' ').title()


@register.filter(name='split')
def split(value, arg):
    """
    Split a string using the given separator.
    """
    if not value:
        return []
    return value.split(arg)
