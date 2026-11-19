from django.urls import path

from collection_completion import views

app_name = "collection_completion"

urlpatterns = [
    path("", views.completion_list, name="list"),
    path("create/", views.completion_create, name="create"),
    path("confirm/", views.completion_confirm, name="confirm"),
    path("<int:pk>/", views.completion_report, name="report"),
]
