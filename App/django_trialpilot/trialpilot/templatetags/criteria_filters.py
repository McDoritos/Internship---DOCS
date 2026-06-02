from django import template

register = template.Library()

@register.filter
def filter_cohort(criteria, cohort):
    return [c for c in criteria if c.cohort == cohort]