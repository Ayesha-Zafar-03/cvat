from django.urls import path
from . import views

urlpatterns = [
    path('tasks/<int:task_id>/class-counts/', views.class_wise_counts, name='class-wise-counts'),
]