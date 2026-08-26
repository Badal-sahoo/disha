from django.urls import path

from .views import AlertListView, BroadcastView, DeviceRegisterView, PrepositionView

urlpatterns = [
    path("alerts", AlertListView.as_view(), name="alert-list"),
    path("alerts/<int:pk>/preposition", PrepositionView.as_view(), name="alert-preposition"),
    path("alerts/<int:pk>/broadcast", BroadcastView.as_view(), name="alert-broadcast"),
    path("devices", DeviceRegisterView.as_view(), name="device-register"),
]
