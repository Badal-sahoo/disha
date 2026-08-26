from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    """Ops-room lists are small. 200 is enough to never paginate in practice,
    and the ?page_size= escape hatch exists for the timeline."""
    page_size = 200
    page_size_query_param = "page_size"
    max_page_size = 1000
