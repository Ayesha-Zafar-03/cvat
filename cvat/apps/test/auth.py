import logging
from types import SimpleNamespace

from django.http import QueryDict
from django.utils.functional import SimpleLazyObject

from cvat.apps.engine.models import Task
from cvat.apps.engine.permissions import TaskPermission
from cvat.apps.iam.middleware import get_organization
from cvat.apps.iam.permissions import get_iam_context

logger = logging.getLogger(__name__)


def can_user_view_task(user, task_id):
    """
    Enforce CVAT's object-level permissions for a task (OPA policy agent).

    CVAT routes every request through its IAM layer, where permissions for a
    task are evaluated with the ``view`` scope of ``TaskPermission``. We reuse
    the exact same code path for the analytics REST API and for the WebSocket
    consumer, so the analytics module can never expose a task the user has no
    access to.
    """
    if user is None or not user.is_authenticated:
        return False

    task = Task.objects.filter(pk=task_id).first()
    if task is None:
        return False

    # Build a lightweight request shim that carries only the attributes CVAT's
    # IAM helpers need (user, iam_context, empty org query params).
    request = SimpleNamespace(
        user=user,
        GET=QueryDict(""),
        headers={},
        META={},
    )
    request.iam_context = SimpleLazyObject(lambda: get_organization(request))

    try:
        iam_context = get_iam_context(request, task)
        perm = TaskPermission.create_scope_view(None, task, iam_context=iam_context)
        return perm.check_access().allow
    except Exception:
        logger.exception(
            "Permission check failed for task %s and user %s",
            task_id,
            getattr(user, "id", None),
        )
        return False
