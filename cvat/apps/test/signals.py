from collections import Counter
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from cvat.apps.engine.models import LabeledShape


def _push_update(task_id):
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    shapes = LabeledShape.objects.filter(
        job__segment__task_id=task_id
    ).select_related('label')
    counts = Counter(shape.label.name for shape in shapes)
    async_to_sync(channel_layer.group_send)(
        f'class_counts_{task_id}',
        {
            'type': 'class_count_update',
            'data': {
                'task_id': task_id,
                'class_counts': dict(counts),
                'total_annotations': sum(counts.values()),
            }
        }
    )


@receiver(post_save, sender=LabeledShape)
def on_shape_saved(sender, instance, **kwargs):
    task_id = instance.job.segment.task_id
    _push_update(task_id)


@receiver(post_delete, sender=LabeledShape)
def on_shape_deleted(sender, instance, **kwargs):
    task_id = instance.job.segment.task_id
    _push_update(task_id)