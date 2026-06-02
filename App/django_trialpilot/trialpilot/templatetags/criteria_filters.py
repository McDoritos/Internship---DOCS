from django import template

register = template.Library()

@register.filter
def filter_cohort(criteria, cohort):
    return [c for c in criteria if c.cohort == cohort]

@register.filter
def filter_logic_cohort(logic_queryset, cohort_id):

    if cohort_id is None:
        return [
            logic for logic in logic_queryset
            if logic.criterion.cohort is None
        ]

    return [
        logic for logic in logic_queryset
        if logic.criterion.cohort_id == cohort_id
    ]

@register.filter
def filter_logic_type(logic_queryset, criterion_type):

    return [
        logic for logic in logic_queryset
        if logic.criterion.type == criterion_type
    ]

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)