const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8787').replace(/\/$/, '');
const SESSION_KEY = 'dropdroid-session-user';

const loginForm = document.querySelector('#login-form');
const createForm = document.querySelector('#create-form');
const scheduleForm = document.querySelector('#schedule-form');
const logoutButton = document.querySelector('#logout-btn');
const scheduleList = document.querySelector('#schedule-list');
const eventFeed = document.querySelector('#event-feed');
const welcomeText = document.querySelector('#welcome-text');
const loginPanel = document.querySelector('#login-panel');
const createPanel = document.querySelector('#create-panel');
const authModeButtons = document.querySelectorAll('[data-auth-mode]');
const systemNotice = document.querySelector('#system-notice') || document.querySelector('#firebase-notice');
const systemMessage = document.querySelector('#system-message') || document.querySelector('#firebase-message');
const frontFeed = document.querySelector('#front-feed');
const frontDetectionTitle = document.querySelector('#front-detection-title');
const frontDetectionDetail = document.querySelector('#front-detection-detail');
const detectedObject = document.querySelector('#detected-object');
const detectedClassification = document.querySelector('#detected-classification');
const detectionConfidence = document.querySelector('#detection-confidence');
const notificationStatus = document.querySelector('#notification-status');
const simulateButton = document.querySelector('#simulate-btn');
const pathname = window.location.pathname.toLowerCase();
const isAuthPage = pathname.endsWith('auth.html');
const isDashboardPage = pathname.endsWith('dashboard.html');
const isHomePage = pathname === '/' || pathname.endsWith('index.html');
let cachedSchedules = [];

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function showMessage(container, text, type) {
  if (!container) {
    return;
  }

  const oldToast = container.querySelector('.toast');
  oldToast?.remove();

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = text;
  container.appendChild(toast);
}

function showSystemNotice(message) {
  if (!systemNotice || !systemMessage) {
    return;
  }

  systemNotice.classList.remove('hidden');
  systemMessage.textContent = message;
}

function hideSystemNotice() {
  systemNotice?.classList.add('hidden');
}

function getSession() {
  try {
    return JSON.parse(localStorage.getItem(SESSION_KEY) || 'null');
  } catch {
    return null;
  }
}

function setSession(user) {
  localStorage.setItem(SESSION_KEY, JSON.stringify(user));
}

function clearSession() {
  localStorage.removeItem(SESSION_KEY);
}

async function request(endpoint, options = {}) {
  try {
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
      },
      ...options,
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(data.error || data.message || 'Request failed.');
    }

    hideSystemNotice();
    return data;
  } catch (error) {
    showSystemNotice('Start the backend with `npm run server` to enable Firebase sync and email notifications.');
    throw error;
  }
}

function setAuthMode(mode) {
  if (!loginPanel || !createPanel || !authModeButtons.length) {
    return;
  }

  const selectedMode = mode === 'create' ? 'create' : 'login';
  loginPanel.classList.toggle('hidden', selectedMode !== 'login');
  createPanel.classList.toggle('hidden', selectedMode !== 'create');

  authModeButtons.forEach((button) => {
    button.classList.toggle('active', button.dataset.authMode === selectedMode);
  });
}

function sortByCreatedDesc(items = []) {
  return [...items].sort((left, right) => {
    const leftTime = left?.createdAt ? new Date(left.createdAt).getTime() : 0;
    const rightTime = right?.createdAt ? new Date(right.createdAt).getTime() : 0;
    return rightTime - leftTime;
  });
}

function renderSchedules(items = []) {
  if (!scheduleList) {
    return;
  }

  if (!items.length) {
    scheduleList.innerHTML = '<div class="empty-state">No pickup scheduled yet.</div>';
    return;
  }

  scheduleList.innerHTML = sortByCreatedDesc(items)
    .map(
      (item) => `
        <article class="schedule-item">
          <div class="schedule-top">
            <span class="schedule-id">${escapeHtml(item.orderId)}</span>
            <span class="schedule-vendor">${escapeHtml(item.vendor)}</span>
          </div>
          <div class="schedule-meta">Sender: ${escapeHtml(item.senderEmail || 'Not provided')}</div>
          <div class="schedule-meta">Date: ${escapeHtml(item.pickupDate)}</div>
          <div class="schedule-meta">Time: ${escapeHtml(item.pickupTime)}</div>
          <div class="schedule-meta">Classification: ${escapeHtml(item.classification || 'Awaiting detection')}</div>
          <div class="schedule-meta">Notification: ${escapeHtml(item.notificationStatus || 'Pending')}</div>
        </article>
      `,
    )
    .join('');
}

function renderEventFeed(container, items = []) {
  if (!container) {
    return;
  }

  if (!items.length) {
    container.innerHTML = '<div class="empty-state">No live events yet.</div>';
    return;
  }

  container.innerHTML = sortByCreatedDesc(items)
    .map(
      (item) => `
        <article class="feed-item">
          <div class="feed-item-top">
            <strong>${escapeHtml(item.title || item.orderId || 'Parcel update')}</strong>
            <span>${escapeHtml(item.vendor || 'DropDroid')}</span>
          </div>
          <p>${escapeHtml(item.message || 'New parcel activity recorded.')}</p>
          <small>${escapeHtml(item.notificationStatus || item.classification || 'Live update')}</small>
        </article>
      `,
    )
    .join('');
}

function pickLatestDetectionEvent(events = [], fallbackItem = null) {
  const sortedEvents = sortByCreatedDesc(events);

  return (
    sortedEvents.find((item) => item?.type === 'parcel_detected' || item?.objectLabel) ||
    sortedEvents.find((item) => item?.type === 'system_state' || item?.classification || item?.message) ||
    fallbackItem ||
    null
  );
}

function renderLatestDetection(event) {
  const title = event?.objectLabel
    ? `${event.objectLabel} detected`
    : event?.title || 'Waiting for parcel scan';
  const detail = event
    ? event.message || `${event.classification || 'Awaiting classification'} • ${event.notificationStatus || 'Pending notification'}`
    : 'New object detection, classification, and sender notification updates will appear here.';

  if (frontDetectionTitle) {
    frontDetectionTitle.textContent = title;
  }

  if (frontDetectionDetail) {
    frontDetectionDetail.textContent = detail;
  }

  if (detectedObject) {
    detectedObject.textContent = event?.objectLabel || event?.title || 'Waiting for parcel scan';
  }

  if (detectedClassification) {
    detectedClassification.textContent = event?.classification || 'Awaiting detection';
  }

  if (detectionConfidence) {
    detectionConfidence.textContent =
      typeof event?.confidence === 'number' ? `${Math.round(event.confidence * 100)}%` : 'Pending';
  }

  if (notificationStatus) {
    notificationStatus.textContent = event?.notificationStatus || 'Pending';
  }
}

async function loadLiveFeed() {
  if (!frontFeed && !frontDetectionTitle) {
    return;
  }

  try {
    const data = await request('/api/live-feed');
    const liveEvents = data.events || [];
    renderEventFeed(frontFeed, liveEvents);
    renderLatestDetection(pickLatestDetectionEvent(liveEvents));
  } catch {
    renderEventFeed(frontFeed, []);
  }
}

async function loadDashboard() {
  const session = getSession();

  if (!session) {
    window.location.href = './auth.html?mode=login';
    return;
  }

  try {
    const data = await request(`/api/dashboard?email=${encodeURIComponent(session.email)}`);
    cachedSchedules = data.schedules || [];
    const dashboardEvents = data.events || [];
    renderSchedules(cachedSchedules);
    renderEventFeed(eventFeed, dashboardEvents);
    renderLatestDetection(pickLatestDetectionEvent(dashboardEvents, cachedSchedules[0]));

    if (simulateButton) {
      simulateButton.disabled = cachedSchedules.length === 0;
    }

    if (welcomeText) {
      welcomeText.textContent = `${session.name || session.email} connected to the DropDroid box`;
    }
  } catch {
    renderSchedules([]);
    renderEventFeed(eventFeed, []);
  }
}

function connectEventStream() {
  if (window.__dropdroidStream) {
    return;
  }

  try {
    const eventSource = new EventSource(`${API_BASE_URL}/api/stream`);
    eventSource.addEventListener('parcelUpdate', () => {
      if (isHomePage) {
        void loadLiveFeed();
      }

      if (isDashboardPage) {
        void loadDashboard();
      }
    });

    window.__dropdroidStream = eventSource;
  } catch {
    // Ignore live stream issues and rely on manual refresh.
  }
}

function initAuthPage() {
  const requestedMode = new URLSearchParams(window.location.search).get('mode') || 'login';
  setAuthMode(requestedMode);

  authModeButtons.forEach((button) => {
    button.addEventListener('click', () => {
      const mode = button.dataset.authMode || 'login';
      setAuthMode(mode);

      const url = new URL(window.location.href);
      url.searchParams.set('mode', mode);
      window.history.replaceState({}, '', url);
    });
  });

  const activeSession = getSession();
  if (activeSession) {
    window.location.href = './dashboard.html';
    return;
  }

  loginForm?.addEventListener('submit', async (event) => {
    event.preventDefault();

    const formData = new FormData(loginForm);
    const email = String(formData.get('email') || '').trim().toLowerCase();
    const password = String(formData.get('password') || '').trim();

    try {
      const data = await request('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      });

      setSession(data.user);
      showMessage(loginForm.parentElement, 'Login successful. Redirecting...', 'success');
      window.setTimeout(() => {
        window.location.href = './dashboard.html';
      }, 300);
    } catch (error) {
      showMessage(loginForm.parentElement, error.message, 'error');
    }
  });

  createForm?.addEventListener('submit', async (event) => {
    event.preventDefault();

    const formData = new FormData(createForm);
    const name = String(formData.get('name') || '').trim();
    const email = String(formData.get('email') || '').trim().toLowerCase();
    const password = String(formData.get('password') || '').trim();

    try {
      const data = await request('/api/auth/register', {
        method: 'POST',
        body: JSON.stringify({ name, email, password }),
      });

      setSession(data.user);
      createForm.reset();
      showMessage(createForm.parentElement, 'Account created. Redirecting...', 'success');
      window.setTimeout(() => {
        window.location.href = './dashboard.html';
      }, 300);
    } catch (error) {
      showMessage(createForm.parentElement, error.message, 'error');
    }
  });
}

function initDashboardPage() {
  const session = getSession();

  if (!session) {
    window.location.href = './auth.html?mode=login';
    return;
  }

  void loadDashboard();
  connectEventStream();

  scheduleForm?.addEventListener('submit', async (event) => {
    event.preventDefault();

    const formData = new FormData(scheduleForm);
    const payload = {
      userEmail: session.email,
      orderId: String(formData.get('orderId') || '').trim(),
      senderEmail: String(formData.get('senderEmail') || '').trim().toLowerCase(),
      pickupDate: String(formData.get('pickupDate') || '').trim(),
      pickupTime: String(formData.get('pickupTime') || '').trim(),
      vendor: String(formData.get('vendor') || '').trim(),
    };

    try {
      await request('/api/schedules', {
        method: 'POST',
        body: JSON.stringify(payload),
      });

      scheduleForm.reset();
      const vendorField = document.querySelector('#vendor');
      if (vendorField) {
        vendorField.value = 'Amazon';
      }

      showMessage(scheduleForm.parentElement, 'Pickup added to the Firebase dashboard.', 'success');
      await loadDashboard();
      await loadLiveFeed();
    } catch (error) {
      showMessage(scheduleForm.parentElement, error.message, 'error');
    }
  });

  simulateButton?.addEventListener('click', async () => {
    if (!cachedSchedules.length) {
      showMessage(simulateButton.parentElement, 'Create a schedule before simulating a parcel scan.', 'error');
      return;
    }

    simulateButton.disabled = true;

    try {
      await request('/api/detect', {
        method: 'POST',
        body: JSON.stringify({ scheduleId: cachedSchedules[0].id }),
      });

      showMessage(simulateButton.parentElement, 'Parcel detected, classified, and dashboard updated.', 'success');
      await loadDashboard();
      await loadLiveFeed();
    } catch (error) {
      showMessage(simulateButton.parentElement, error.message, 'error');
    } finally {
      simulateButton.disabled = cachedSchedules.length === 0;
    }
  });

  logoutButton?.addEventListener('click', () => {
    clearSession();
    window.location.href = './auth.html?mode=login';
  });
}

if (isHomePage) {
  void loadLiveFeed();
  connectEventStream();
}

if (isAuthPage) {
  initAuthPage();
}

if (isDashboardPage) {
  initDashboardPage();
}
