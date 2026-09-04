from django.core.paginator import Paginator


DEFAULT_PAGE_SIZE = 25


class PaginatedMaterialListMixin:
    """Add regular server-side pagination to custom Material list templates."""

    paginate_by = DEFAULT_PAGE_SIZE

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        paginator = Paginator(self.object_list, self.paginate_by)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        page_start = page_obj.start_index() - 1
        datatable_config = context.get("datatable_config")
        if isinstance(datatable_config, dict):
            datatable_config["displayStart"] = max(page_start, 0)
        if "data" in context:
            context["data"] = self.get_table_data(max(page_start, 0), self.paginate_by)
        context.update(
            {
                "object_list": page_obj.object_list,
                "page_obj": page_obj,
                "paginator": paginator,
                "is_paginated": paginator.num_pages > 1,
            }
        )
        return context


class PaginatedModelViewSetMixin:
    """Forward page size from a Material viewset to its list view."""

    paginate_by = DEFAULT_PAGE_SIZE

    def get_list_view_kwargs(self, **kwargs):
        kwargs.setdefault("paginate_by", self.paginate_by)
        return super().get_list_view_kwargs(**kwargs)
