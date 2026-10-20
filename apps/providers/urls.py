from django.urls import path

from . import views

app_name = "providers"

urlpatterns = [
    path("providers/", views.providers_view, name="list"),
    path("providers/seed/", views.provider_seed, name="seed"),
    path("providers/<uuid:provider_id>/", views.provider_detail, name="detail"),
    path("providers/<uuid:provider_id>/test/", views.provider_test, name="test"),
]
