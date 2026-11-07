import json
import threading
from datetime import datetime
from urllib import error, parse, request

import config


class FirebaseManager:
    """Bridge the Python vision pipeline to the DropDroid web backend API."""

    def __init__(self):
        self.api_base = config.DROPDROID_API_BASE.rstrip('/')
        self.default_user_email = config.DEFAULT_USER_EMAIL
        self.active_schedule_id = config.ACTIVE_SCHEDULE_ID
        self.is_connected = False
        self.last_error = ''
        self._check_connection()

    def _call_api(self, method, endpoint, payload=None, timeout=5):
        body = None
        headers = {}

        if payload is not None:
            body = json.dumps(payload).encode('utf-8')
            headers['Content-Type'] = 'application/json'

        req = request.Request(f"{self.api_base}{endpoint}", data=body, headers=headers, method=method)
        with request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode('utf-8'))

    def _check_connection(self):
        try:
            health = self._call_api('GET', '/api/health')
            self.is_connected = True
            mode = health.get('storageMode', 'unknown')
            print(f"[DROPDROID API] Connected ({mode})")
        except Exception as exc:
            self.is_connected = False
            self.last_error = str(exc)
            print(f"[DROPDROID API] Connection unavailable: {self.last_error}")

    def _emit_state_thread(self, state, details):
        if not self.is_connected:
            self._check_connection()
        if not self.is_connected:
            return

        try:
            self._call_api(
                'POST',
                '/api/vision/state',
                {
                    'state': state,
                    'details': details,
                    'userEmail': self.default_user_email,
                },
            )
        except Exception as exc:
            self.last_error = str(exc)
            print(f"[DROPDROID API] State update failed: {exc}")

    def update_live_state(self, state, details=''):
        threading.Thread(target=self._emit_state_thread, args=(state, details), daemon=True).start()

    def _get_active_schedule_id(self):
        if self.active_schedule_id:
            return self.active_schedule_id

        if not self.is_connected:
            self._check_connection()
        if not self.is_connected:
            return None

        try:
            dashboard = self._call_api(
                'GET',
                f"/api/dashboard?email={parse.quote(self.default_user_email)}",
            )
            schedules = dashboard.get('schedules', [])
            if not schedules:
                return None

            pending = next(
                (item for item in schedules if item.get('status') != 'Detected and classified'),
                schedules[0],
            )
            return pending.get('id')
        except Exception as exc:
            self.last_error = str(exc)
            print(f"[DROPDROID API] Could not load schedule: {exc}")
            return None

    def _push_delivery_thread(self, company, package, ocr_text, is_theft=False):
        if not self.is_connected:
            self._check_connection()
        if not self.is_connected:
            return

        if is_theft:
            self._emit_state_thread(
                'THEFT_ALERT',
                f"Unauthorized removal detected for {company} / {package} at {datetime.now().strftime('%H:%M:%S')}",
            )
            return

        schedule_id = self._get_active_schedule_id()
        if not schedule_id:
            self._emit_state_thread(
                'SCANNING_LABEL',
                f"Parcel detected for {company}, but no active schedule is available yet.",
            )
            return

        object_label = ocr_text or package or f"{company} parcel"

        try:
            self._call_api(
                'POST',
                '/api/detect',
                {
                    'scheduleId': schedule_id,
                    'objectLabel': object_label,
                },
            )
            print(f"[DROPDROID API] Detection pushed for schedule {schedule_id}")
        except Exception as exc:
            self.last_error = str(exc)
            print(f"[DROPDROID API] Detection update failed: {exc}")

    def log_delivery(self, company, package, ocr_text=''):
        threading.Thread(
            target=self._push_delivery_thread,
            args=(company, package, ocr_text, False),
            daemon=True,
        ).start()

    def log_theft(self, company, package):
        threading.Thread(
            target=self._push_delivery_thread,
            args=(company, package, 'N/A', True),
            daemon=True,
        ).start()


cloud_db = FirebaseManager()
