from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import PasswordChangeDoneView, PasswordChangeView
from django.urls import reverse_lazy
from django.views.generic import TemplateView


class AccountProfileView(LoginRequiredMixin, TemplateView):
    template_name = "account/profile.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context.update(
            {
                "user_obj": user,
                "role": getattr(user, "role", None),
            }
        )
        return context


class AccountPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    template_name = "account/password_change.html"
    success_url = reverse_lazy("account:password_change_done")


class AccountPasswordChangeDoneView(LoginRequiredMixin, PasswordChangeDoneView):
    template_name = "account/password_change_done.html"
