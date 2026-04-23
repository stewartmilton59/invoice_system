from django import template

register = template.Library()

@register.filter
def sum_attribute(queryset, attr):
    """Sum a numeric attribute across a queryset"""
    total = 0
    for obj in queryset:
        value = getattr(obj, attr, 0)
        if value is not None:
            total += value
    return total

@register.filter
def div(value, divisor):
    """Divide value by divisor, return 0 if divisor is 0"""
    try:
        if divisor and divisor != 0:
            return value / divisor
        return 0
    except (TypeError, ValueError, ZeroDivisionError):
        return 0

@register.filter
def multiply(value, factor):
    """Multiply value by factor"""
    try:
        return value * factor
    except (TypeError, ValueError):
        return 0

@register.filter
def subtract(value, arg):
    """Subtract arg from value"""
    try:
        return value - arg
    except (TypeError, ValueError):
        return 0

@register.filter
def add(value, arg):
    """Add arg to value"""
    try:
        return value + arg
    except (TypeError, ValueError):
        return 0