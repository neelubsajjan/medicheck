from django import template

register = template.Library()


@register.filter(name='sym_label')
def sym_label(value):
    """Convert symptom snake_case to Title Case with spaces.
    e.g. 'body_ache' → 'Body Ache'
    """
    return value.replace('_', ' ').title()

@register.filter(name='split')
def split(value, arg):
    return value.split(arg)
