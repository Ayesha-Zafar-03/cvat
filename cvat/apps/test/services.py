from django.db.models import Count

from cvat.apps.engine.models import LabeledShape


def compute_counts(task_id):
    """
    Per class (label) for one task:
      images      = number of distinct frames containing at least one shape of that class
      annotations = total number of shapes of that class
    Only LabeledShape is counted (tracks and tags are not).
    """
    rows = (
        LabeledShape.objects
        .filter(job__segment__task_id=task_id)
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