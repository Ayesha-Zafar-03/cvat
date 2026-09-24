import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from cvat.apps.engine.models import Job

from .services import push_class_counts

logger = logging.getLogger(__name__)


def _schedule_push(instance):
    try:
        task_id = instance.segment.task_id
    except Exception:
        logger.exception("could not resolve task for job %s", getattr(instance, "pk", None))
        return
    # Push only after the transaction commits so clients never see uncommitted
    # or rolled-back data.
    transaction.on_commit(lambda: push_class_counts(task_id))


@receiver(post_save, sender=Job)
def on_job_saved(sender, instance, **kwargs):
    # CVAT persists annotations with bulk_create() (which does not emit the
    # per-row post_save signal), so the reliable "annotations changed" event is
    # the job updated_date touch() that CVAT performs inside every annotation
    # mutation (create / update / put / delete), see TaskDataDB in
    # cvat.apps.dataset_manager.task. A post_save on Job therefore fires exactly
    # once per committed annotation change that touches the task data.
    _schedule_push(instance)
