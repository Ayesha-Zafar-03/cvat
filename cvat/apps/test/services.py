import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models import Count

from cvat.apps.engine.models import LabeledShape

logger = logging.getLogger(__name__)


def compute_counts(task_id):
    """
    Per class (label) for one task:
      images      = number of distinct frames containing at least one shape of that class
      annotations = total number of shapes of that class

    Only LabeledShape is counted (tracks and tags are not).
    """
    rows = (
        LabeledShape.objects.filter(job__segment__task_id=task_id)
        .values("label__name")
        .annotate(images=Count("frame", distinct=True), annotations=Count("id"))
        .order_by("label__name")
    )
    class_counts = {
        r["label__name"]: {"images": r["images"], "annotations": r["annotations"]}
        for r in rows
    }
    return {
        "task_id": task_id,
        "class_counts": class_counts,
        "total_annotations": sum(v["annotations"] for v in class_counts.values()),
    }


def push_class_counts(task_id):
    """
    Recompute the class-wise counts for a task and broadcast them to every
    connected dashboard. Safe to call from anywhere: failures are logged and
    never propagated, so analytics can never break annotation saving.
    """
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(
            f"class_counts_{task_id}",
            {"type": "class_count_update", "data": compute_counts(task_id)},
        )
    except Exception:
        logger.exception("class-count push failed for task %s", task_id)
