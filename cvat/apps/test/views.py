from collections import Counter

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from cvat.apps.engine.models import LabeledShape


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def class_wise_counts(request, task_id):
    """
    Returns the count of annotated shapes per class (label) for a given task.
    Example: GET /api/test/tasks/5/class-counts/
    Response: {"task_id": 5, "class_counts": {"car": 12, "person": 34}}
    """
    shapes = LabeledShape.objects.filter(
        job__segment__task_id=task_id
    ).select_related('label')

    counts = Counter(shape.label.name for shape in shapes)

    return Response({
        "task_id": task_id,
        "class_counts": dict(counts),
        "total_annotations": sum(counts.values()),
    })
from django.http import HttpResponse
from pathlib import Path


def dashboard_view(request):
    html_path = Path(__file__).resolve().parent / "dashboard.html"
    return HttpResponse(html_path.read_text(), content_type="text/html")