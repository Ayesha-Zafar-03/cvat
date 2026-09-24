# CVAT Class-Wise Analytics - Real Time Dashboard

Extension of [CVAT](https://github.com/cvat-ai/cvat) that adds a class-wise
annotation analytics REST API and a real-time dashboard with WebSocket-based
live updates.

- Branch: `dev-test01` (submission for the Full Stack Web Developer evaluation)
- Scope: Django backend (`cvat/apps/test`), Dashboard page, Django Channels WebSocket
- Core integration: proxies CVAT's IAM (OPA) object-level permissions and hooks
  the annotation write pipeline so no CVAT internals are modified.

---

## 1. CVAT Architecture (as used by this feature)

CVAT is a full-stack computer-vision annotation platform:

- **`cvat/apps/engine`** - core domain models (`Task`, `Job`, `Segment`,
  `Label`, and the annotation rows `LabeledShape`, `LabeledTrack`,
  `LabeledImage`) plus the REST API (`/api/tasks`, `/api/jobs`) and the IAM
  permission classes (`TaskPermission`, ...).
- **`cvat/apps/dataset_manager`** - the annotation layer. It converts between
  the REST payloads (intermediate representation `AnnotationIR`) and the
  database. CVAT intentionally writes annotation rows with `bulk_create()` for
  performance, so per-row Django `post_save` signals are **not** emitted on the
  normal annotation save path.
- **`cvat/apps/events`** - CVAT's own analytics/event system; it is notified on
  every annotation change.
- **`cvat/apps/iam`** - policy enforcement. Every request is authorized against
  an Open Policy Agent (`OPA`) sidecar using per-object scopes (e.g.
  `TaskPermission.Scopes.VIEW`).
- **`cvat-ui` (React)** - the main annotation UI.
- **Redis** - caching, task queues (RQ) and, in this feature, the Django
  Channels channel layer.

The feature adds a new Django application `cvat/apps/test` which plugs into this
architecture without modifying CVAT internals.

---

## 2. What Was Implemented

```
cvat/apps/test/
├── apps.py          # Django AppConfig, loads signals on ready()
├── auth.py          # CVAT/OPA object-level permission helper (API + WebSocket)
├── consumers.py     # Django Channels WebSocket consumer (live class counts)
├── dashboard.html   # Dashboard page (Chart.js bar chart, WS client)
├── routing.py       # WebSocket route: ws/test/tasks/<id>/class-counts/
├── services.py      # Aggregation logic (class-wise counts) + broadcast helper
├── signals.py       # "annotations changed" hook -> schedules a live push
├── urls.py          # REST routes + dashboard page route
└── views.py         # REST API endpoint + dashboard page view
```

Integration points outside the app (small, non-intrusive):

- `cvat/urls.py` - mounted the REST routes under `/api/test/`.
- `cvat/asgi.py` - wrapped the Django ASGI handler in a Channels
  `ProtocolTypeRouter` so WebSockets are handled by Channels while HTTP
  (including the VS Code remote debugger) keeps working.
- `cvat/settings/base.py` - registered the app and configured a Redis-based
  `CHANNEL_LAYERS`.
- `docker-compose.yml` - Traefik now also forwards the `/ws/` prefix.
- `cvat/requirements/*` - added `channels` and `channels-redis`.

---

## 3. REST API Design

### 3.1 Endpoint

| Method | URL                                        | Auth        |
| ------ | ------------------------------------------ | ----------- |
| GET    | `/api/test/tasks/<task_id>/class-counts/`  | session/OTP |

- Returns `404` when the task does not exist.
- Returns `401` when not authenticated.
- Returns `403` when the user has no access to the task (OPA object-level check).
- Content-Type: `application/vnd.cvat+json; version=2.0` (CVAT API versioning).

Sample response:

```json
{
  "task_id": 5,
  "class_counts": {
    "car": { "images": 3, "annotations": 12 },
    "pedestrian": { "images": 2, "annotations": 7 }
  },
  "total_annotations": 19
}
```

### 3.2 Semantics

- `images` - number of distinct frames (of a task) that contain at least one
  shape of the class. Computed with `COUNT(DISTINCT frame)`.
- `annotations` - total number of shapes of that class (`LabeledShape` rows).
- `total_annotations` - sum over all classes.

The aggregate is produced in a single indexed SQL query
(`services.compute_counts`), so it stays cheap even for large tasks. Only
`LabeledShape` (boxes, polygons, polylines, points, skeletons) is counted;
`LabeledTrack` and `LabeledImage` (image-level tags) are intentionally not
included - the metric reflects **frame-level class presence**, which is what
image analyzers consume.

### 3.3 Dashboard page

`GET /api/test/dashboard/` serves a self-contained HTML page (Chart.js from
CDN, no frontend build step). The user picks a task id; the page fetches the
initial snapshot from the REST API and then opens the WebSocket for live
updates.

---

## 4. Data Flow

### 4.1 Initial load (HTTP)

```
Browser
  |  GET /api/test/tasks/5/class-counts/
  v
cvat.apps.test.views.class_wise_counts
  |  can_user_view_task(request.user, 5)   -> TaskPermission (OPA) check
  v
cvat.apps.test.services.compute_counts(5)  -> one SQL aggregation
  |  { task_id, class_counts, total_annotations }
  v
Browser renders Chart.js bar chart + "Total annotations"
```

### 4.2 Live updates (WebSocket)

```
CVAT UI / direct API call edits annotations (draw a box, edit, delete)
  |  PATCH /api/tasks/5/annotations  (transaction.atomic)
  v
cvat/apps/dataset_manager  -> _delete()/_create() use bulk_create()
  |  CVAT touches the Job row (TaskDataDB._set_updated_date -> job.save())
  v
signals.on_job_saved (post_save on Job)   [fires once per mutation]
  |  transaction.on_commit(...)
  v
services.push_class_counts(task_id)  -> compute_counts() at commit time
  |  channel_layer.group_send("class_counts_5", data)
  v
Channels Redis channel layer
  v
ClassCountConsumer.class_count_update    (all connected dashboards for task 5)
  |  JSON -> { task_id, class_counts, total_annotations }
  v
Browser chart.update()  (reflects the new counts immediately)
```

Because the recompute is executed **after** the transaction commits, clients
never observe partial or rolled-back state, and a failure to notify can never
corrupt or break annotation saving (all exceptions are swallowed and logged).

---

## 5. WebSocket Implementation

- **Server**: Django Channels (`channels` / `channels-redis`).
  `cvat/asgi.py` routes `websocket` connections through
  `AuthMiddlewareStack` into `cvat.apps.test.routing.websocket_urlpatterns`.

- **Route**:
  `ws://<host>/ws/test/tasks/<task_id>/class-counts/` (regex
  `(?P<task_id>\d+)`).

- **Consumer** (`consumers.py`):
  1. Rejects unauthenticated connections (`4401`) and connections to tasks the
     user may not view (`4403`, same OPA check as the REST API).
  2. Joins a per-task Channels group (`class_counts_<task_id>`) so a broadcast
     is delivered to every dashboard watching that task.
  3. On `class_count_update` events, serializes and sends the payload to the
     browser.

- **Triggers** (`signals.py`): CVAT writes annotations with `bulk_create()` so
  Django does not emit per-row signals on the normal path. The reliable, single
  "annotations changed" signal is the `Job` row `touch()` that CVAT performs at
  the end of every task/job annotation mutation. A `post_save` receiver on
  `Job` schedules the recompute + broadcast via `transaction.on_commit`.
  This covers create / update / put / delete of tags, shapes, tracks and
  intervals, at both task and job level, including imports and automatic
  annotation.

- **Client** (`dashboard.html`): `WebSocket` with automatic reconnection
  (3 s retry), protocol detection (`ws`/`wss`), and a guard that prevents
  multiple overlapping reconnect loops when the task is switched.

---

## 6. Stability & UI Responsiveness

- **Connection issues**: the client reconnects with a bounded 3 s backoff and
  shows a clear `Disconnected - retrying...` status. A stale socket is closed
  before a new one is opened so old `onclose` handlers cannot start a second
  reconnect loop.
- **Backend resilience**: the broadcast is wrapped in a try/except and logged.
  A Redis outage therefore degrades to "no live updates" instead of failing
  annotation saves.
- **Transaction safety**: pushes are scheduled with `transaction.on_commit`,
  so a rolled-back edit never reaches the dashboards.
- **UI**: the chart is responsive (`maintainAspectRatio: false`,
  `min-height`), a `"No annotations in this task yet."` empty state is shown,
  and the total counter updates with every push.

---

## 7. Security

- The REST endpoint requires an authenticated user and is gated by CVAT's own
  object-level permission system (`TaskPermission` scope `view`, evaluated by
  OPA) - not just `IsAuthenticated`. This keeps private/organizational tasks
  private.
- The WebSocket consumer applies the same OPA check on connect.
- Sessions are validated by Django's session middleware inside
  `AuthMiddlewareStack` (CSRF is not required for WebSockets, authentication is
  done via the session cookie).

---

## 8. Challenges Faced & Solutions

1. **Annotation writes do not emit Django signals.**
   CVAT saves annotations with `bulk_create()` for performance, so the first
   implementation (signals on `LabeledShape`) only fired on deletes and missed
   newly drawn shapes. **Solution:** hook the `Job` `post_save`, which CVAT
   touches on every committed annotation mutation, and recompute counts at
   `transaction.on_commit` time.

2. **Avoiding race/stale reads between the REST snapshot and the WebSocket.**
   If an edit lands between the HTTP fetch and WS connect, the chart would be
   one update behind. **Solution:** the server always recomputes from the
   database before broadcasting, and any update that arrives after connect is
   pushed, so the chart self-heals on the next mutation.

3. **Reconnecting WebSockets produced overlapping loops.**
   The naive `onclose -> setTimeout(connect)` created duplicate sockets when
   switching tasks. **Solution:** a `closeSocket()` helper clears the retry
   timer and detaches `onclose`/`onerror` before closing the old socket.

4. **Not breaking CVAT with a new app.**
   The whole feature must be optional and non-invasive. **Solution:** analytics
   failures are caught and logged, the channel layer reuses the existing Redis,
   and no CVAT domain code is touched - the integration is limited to URL
   wiring, settings and the ASGI entry point. Traefik only gained a `/ws/` path
   prefix.

5. **Object-level permissions for a non-viewset endpoint.**
   CVAT's DRF viewsets derive permissions from the IAM stack; a plain function
   view does not. **Solution:** a small `auth.py` helper that builds an IAM
   context and evaluates the exact same `TaskPermission` the TaskViewSet uses
   for `retrieve` (scope `view`), so the analytics API behaves like any other
   task-scoped CVAT endpoint (sandbox and organizational tasks included).

---

## 9. Running & Verifying

1. Start the stack (`docker compose up -d`), with Redis and OPA included.
   The channel layer uses the same in-memory Redis as CVAT.
2. Log in, create a task, and annotate frames with labels.
3. `pip install`/migrate are not needed - the new app has no models.
4. Open `http://localhost:8080/api/test/dashboard/`, enter the task id and click
   *Load*: the chart renders the initial counts.
5. Draw / edit / delete an annotation in CVAT and watch the chart update live.

Screenshots:

| Screenshot | Description |
| --- | --- |
| `../../../screenshots/04-dashboard-overview.png` | Dashboard initial state |
| `../../../screenshots/05-annotations-view.png` | Annotated task overview |
| `../../../screenshots/01-dashboard-before-live-update.png` | Before a live update |
| `../../../screenshots/02-dashboard-after-live-update.png` | After a live update |
| `../../../screenshots/03-realtime-label-added.png` | A label added in real time |