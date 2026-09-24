from pathlib import Path

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from cvat.apps.engine.models import Task

from .services import compute_counts


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def class_wise_counts(request, task_id):
    """
    Class-wise counts for a task.
    GET /api/test/tasks/<task_id>/class-counts/
    Response: {"task_id": 5,
               "class_counts": {"car": {"images": 3, "annotations": 12}},
               "total_annotations": 12}
    """
    get_object_or_404(Task, pk=task_id)
    return Response(compute_counts(task_id))


def dashboard_view(request):
    html_path = Path(__file__).resolve().parent / "dashboard.html"
    return HttpResponse(
        html_path.read_text(encoding="utf-8"),
        content_type="text/html; charset=utf-8",
    )