import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from cvat.apps.engine.models import LabeledShape

from .services import compute_counts

logger = logging.getLogger(__name__)


def _push_update(task_id):
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(
            f'class_counts_{task_id}',
            {'type': 'class_count_update', 'data': compute_counts(task_id)},
        )
    except Exception:
        # Analytics must never break annotation saving.
        logger.exception("class-count push failed for task %s", task_id)


def _schedule_push(instance):
    try:
        task_id = instance.job.segment.task_id
    except Exception:
        logger.exception("could not resolve task for shape %s", getattr(instance, "pk", None))
        return
    # Push only after the transaction commits so clients never see uncommitted or rolled-back data.
    transaction.on_commit(lambda: _push_update(task_id))


@receiver(post_save, sender=LabeledShape)
def on_shape_saved(sender, instance, **kwargs):
    _schedule_push(instance)


@receiver(post_delete, sender=LabeledShape)
def on_shape_deleted(sender, instance, **kwargs):
    _schedule_push(instance)