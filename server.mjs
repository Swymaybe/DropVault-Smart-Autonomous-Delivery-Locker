import cors from 'cors';
import dotenv from 'dotenv';
import express from 'express';
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import nodemailer from 'nodemailer';
import { cert, getApps, initializeApp } from 'firebase-admin/app';
import { FieldValue, getFirestore } from 'firebase-admin/firestore';

dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const PORT = Number(process.env.PORT || 8787);
const firebaseServiceAccountPath = path.resolve(
  __dirname,
  process.env.FIREBASE_SERVICE_ACCOUNT_PATH || './firebase_key.json',
);

const app = express();
const streamClients = new Set();
const DEMO_USER = {
  uid: 'user_dropdroid_com',
  name: 'DropDroid User',
  email: 'user@dropdroid.com',
  password: 'drop1234',
};

app.use(cors());
app.use(express.json());

let db = null;
let firebaseReady = false;
let firebaseInitMessage = 'Firebase not initialised.';

try {
  if (!fs.existsSync(firebaseServiceAccountPath)) {
    throw new Error(`Service account file was not found at ${firebaseServiceAccountPath}`);
  }

  const serviceAccount = JSON.parse(fs.readFileSync(firebaseServiceAccountPath, 'utf8'));
  const adminApp = getApps().length
    ? getApps()[0]
    : initializeApp({ credential: cert(serviceAccount) });

  db = getFirestore(adminApp);
  firebaseReady = true;
  firebaseInitMessage = `Connected to Firebase project ${serviceAccount.project_id}.`;
} catch (error) {
  firebaseInitMessage = error instanceof Error ? error.message : 'Firebase connection failed.';
}

let transporter = null;

function getMailer() {
  if (transporter) {
    return transporter;
  }

  const { SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS } = process.env;
  const placeholderUser = String(SMTP_USER || '').trim().toLowerCase() === 'your_email@example.com';
  const placeholderPass = String(SMTP_PASS || '').trim().toLowerCase() === 'your_app_password';

  if (!SMTP_HOST || !SMTP_PORT || !SMTP_USER || !SMTP_PASS || placeholderUser || placeholderPass) {
    return null;
  }

  transporter = nodemailer.createTransport({
    host: SMTP_HOST,
    port: Number(SMTP_PORT),
    secure: Number(SMTP_PORT) === 465,
    auth: {
      user: SMTP_USER,
      pass: SMTP_PASS,
    },
  });

  return transporter;
}

function makeSafeId(value) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '_');
}

function hashPassword(password) {
  return createHash('sha256').update(password).digest('hex');
}

function toIsoDate(value) {
  if (!value) {
    return null;
  }

  if (typeof value?.toDate === 'function') {
    return value.toDate().toISOString();
  }

  if (typeof value === 'string') {
    return value;
  }

  return null;
}

function normaliseDoc(doc) {
  const data = doc.data();
  return {
    id: doc.id,
    ...data,
    createdAt: toIsoDate(data.createdAt),
    updatedAt: toIsoDate(data.updatedAt),
    lastDetectedAt: toIsoDate(data.lastDetectedAt),
  };
}

function sortByCreatedDesc(items) {
  return [...items].sort((left, right) => {
    const leftValue = left.createdAt ? new Date(left.createdAt).getTime() : 0;
    const rightValue = right.createdAt ? new Date(right.createdAt).getTime() : 0;
    return rightValue - leftValue;
  });
}

function broadcast(eventName, payload) {
  const message = `event: ${eventName}\ndata: ${JSON.stringify(payload)}\n\n`;

  for (const client of streamClients) {
    client.write(message);
  }
}

function classifyParcel(vendor, objectLabel) {
  const label = String(objectLabel || 'parcel').toLowerCase();
  const fallbackSource = String(vendor || 'delivery').trim() || 'delivery';

  let source = fallbackSource;
  if (label.includes('amazon')) {
    source = 'Amazon';
  } else if (label.includes('zomato')) {
    source = 'Zomato';
  } else if (label.includes('blinkit')) {
    source = 'Blinkit';
  }

  if (label.includes('food') || source === 'Zomato') {
    return `${source} food parcel verified`;
  }

  if (label.includes('grocery') || source === 'Blinkit') {
    return `${source} grocery parcel verified`;
  }

  return `${source} parcel verified`;
}

const localStorePath = path.resolve(__dirname, 'dropdroid-local-store.json');
const localStore = fs.existsSync(localStorePath)
  ? JSON.parse(fs.readFileSync(localStorePath, 'utf8'))
  : {
      users: [],
      schedules: [],
      parcelEvents: [],
    };

function persistLocalStore() {
  fs.writeFileSync(localStorePath, JSON.stringify(localStore, null, 2));
}

function useLocalFallback(message) {
  firebaseReady = false;
  db = null;
  firebaseInitMessage = `Firebase unavailable, using local fallback. ${message}`;
}

async function runWithStore(firebaseTask, fallbackTask) {
  if (firebaseReady && db) {
    try {
      return await firebaseTask();
    } catch (error) {
      useLocalFallback(error instanceof Error ? error.message : 'Firebase request failed.');
    }
  }

  return fallbackTask();
}

function ensureLocalDemoUser() {
  const hasDemoUser = localStore.users.some((user) => user.email === DEMO_USER.email);

  if (!hasDemoUser) {
    localStore.users.push({
      uid: DEMO_USER.uid,
      name: DEMO_USER.name,
      email: DEMO_USER.email,
      passwordHash: hashPassword(DEMO_USER.password),
      createdAt: new Date().toISOString(),
    });
    persistLocalStore();
  }
}

async function seedDemoUser() {
  ensureLocalDemoUser();

  await runWithStore(
    async () => {
      const demoRef = db.collection('users').doc(DEMO_USER.uid);
      const demoSnapshot = await demoRef.get();

      if (!demoSnapshot.exists) {
        await demoRef.set({
          uid: DEMO_USER.uid,
          name: DEMO_USER.name,
          email: DEMO_USER.email,
          passwordHash: hashPassword(DEMO_USER.password),
          createdAt: FieldValue.serverTimestamp(),
        });
      }
    },
    async () => null,
  );
}

async function loadLiveEvents(limit = 8) {
  return runWithStore(
    async () => {
      const snapshot = await db.collection('parcelEvents').get();
      return sortByCreatedDesc(snapshot.docs.map(normaliseDoc)).slice(0, limit);
    },
    async () => sortByCreatedDesc(localStore.parcelEvents).slice(0, limit),
  );
}

async function findUserByEmail(email) {
  const safeEmail = String(email || '').trim().toLowerCase();
  const userId = makeSafeId(safeEmail);

  return runWithStore(
    async () => {
      const snapshot = await db.collection('users').doc(userId).get();
      return snapshot.exists ? snapshot.data() : null;
    },
    async () => localStore.users.find((item) => item.email === safeEmail) || null,
  );
}

async function createUserRecord({ name, email, password }) {
  const safeEmail = email.trim().toLowerCase();
  const userId = makeSafeId(safeEmail);
  const record = {
    uid: userId,
    name,
    email: safeEmail,
    passwordHash: hashPassword(password),
    createdAt: new Date().toISOString(),
  };

  await runWithStore(
    async () => {
      await db.collection('users').doc(userId).set({
        ...record,
        createdAt: FieldValue.serverTimestamp(),
      });
    },
    async () => {
      localStore.users.push(record);
      persistLocalStore();
    },
  );

  return {
    uid: userId,
    name,
    email: safeEmail,
  };
}

async function getDashboardData(email) {
  const safeEmail = String(email || '').trim().toLowerCase();

  return runWithStore(
    async () => {
      const scheduleSnapshot = await db.collection('schedules').where('userEmail', '==', safeEmail).get();
      const eventSnapshot = await db.collection('parcelEvents').where('userEmail', '==', safeEmail).get();

      return {
        schedules: sortByCreatedDesc(scheduleSnapshot.docs.map(normaliseDoc)),
        events: sortByCreatedDesc(eventSnapshot.docs.map(normaliseDoc)).slice(0, 12),
      };
    },
    async () => ({
      schedules: sortByCreatedDesc(localStore.schedules.filter((item) => item.userEmail === safeEmail)),
      events: sortByCreatedDesc(localStore.parcelEvents.filter((item) => item.userEmail === safeEmail)).slice(0, 12),
    }),
  );
}

async function createScheduleRecord(payload) {
  const baseRecord = {
    userEmail: payload.userEmail,
    orderId: payload.orderId,
    pickupDate: payload.pickupDate,
    pickupTime: payload.pickupTime,
    vendor: payload.vendor,
    senderEmail: payload.senderEmail,
    status: 'Scheduled',
    latestObjectLabel: 'Waiting for parcel scan',
    classification: 'Awaiting detection',
    notificationStatus: 'Pending',
  };

  return runWithStore(
    async () => {
      const reference = await db.collection('schedules').add({
        ...baseRecord,
        createdAt: FieldValue.serverTimestamp(),
        updatedAt: FieldValue.serverTimestamp(),
      });

      return {
        id: reference.id,
        ...baseRecord,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };
    },
    async () => {
      const savedSchedule = {
        id: `local-schedule-${Date.now()}`,
        ...baseRecord,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };

      localStore.schedules.push(savedSchedule);
      persistLocalStore();
      return savedSchedule;
    },
  );
}

async function findScheduleById(scheduleId) {
  return runWithStore(
    async () => {
      const snapshot = await db.collection('schedules').doc(scheduleId).get();
      return snapshot.exists ? normaliseDoc(snapshot) : null;
    },
    async () => localStore.schedules.find((item) => item.id === scheduleId) || null,
  );
}

async function updateScheduleDetection(scheduleId, updatedSchedule) {
  return runWithStore(
    async () => {
      const payload = {
        ...updatedSchedule,
        lastDetectedAt: FieldValue.serverTimestamp(),
        updatedAt: FieldValue.serverTimestamp(),
      };

      await db.collection('schedules').doc(scheduleId).set(payload, { merge: true });
      const snapshot = await db.collection('schedules').doc(scheduleId).get();
      return snapshot.exists ? normaliseDoc(snapshot) : null;
    },
    async () => {
      const index = localStore.schedules.findIndex((item) => item.id === scheduleId);
      if (index === -1) {
        return null;
      }

      localStore.schedules[index] = {
        ...localStore.schedules[index],
        ...updatedSchedule,
        lastDetectedAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };

      persistLocalStore();
      return localStore.schedules[index];
    },
  );
}

async function createParcelEvent(payload) {
  const localEvent = {
    id: `local-${Date.now()}`,
    ...payload,
    createdAt: new Date().toISOString(),
  };

  const event = await runWithStore(
    async () => {
      const reference = await db.collection('parcelEvents').add({
        ...payload,
        createdAt: FieldValue.serverTimestamp(),
      });

      return {
        id: reference.id,
        ...payload,
        createdAt: new Date().toISOString(),
      };
    },
    async () => {
      localStore.parcelEvents.push(localEvent);
      persistLocalStore();
      return localEvent;
    },
  );

  broadcast('parcelUpdate', event);
  return event;
}

async function sendNotificationEmail({ senderEmail, orderId, vendor, classification, pickupDate, pickupTime }) {
  const mailer = getMailer();

  if (!senderEmail) {
    return {
      delivered: false,
      status: 'Sender email missing',
    };
  }

  if (!mailer) {
    return {
      delivered: false,
      status: 'SMTP not configured',
    };
  }

  try {
    await mailer.sendMail({
      from: process.env.SMTP_FROM || process.env.SMTP_USER,
      to: senderEmail,
      subject: `DropDroid update for order ${orderId}`,
      text: [
        `Your parcel has been detected by DropDroid.`,
        `Vendor: ${vendor}`,
        `Order ID: ${orderId}`,
        `Classification: ${classification}`,
        `Scheduled date: ${pickupDate}`,
        `Scheduled time: ${pickupTime}`,
      ].join('\n'),
    });

    return {
      delivered: true,
      status: 'Email sent',
    };
  } catch (error) {
    return {
      delivered: false,
      status: error instanceof Error ? error.message : 'Email failed',
    };
  }
}

app.get('/api/health', (_req, res) => {
  res.json({
    ok: true,
    firebaseReady,
    storageMode: firebaseReady ? 'firebase' : 'local-fallback',
    emailReady: Boolean(getMailer()),
    message: firebaseInitMessage,
  });
});

app.get('/api/stream', (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders?.();

  streamClients.add(res);
  res.write(`event: ready\ndata: ${JSON.stringify({ ok: true })}\n\n`);

  req.on('close', () => {
    streamClients.delete(res);
  });
});

app.get('/api/live-feed', async (_req, res) => {
  const events = await loadLiveEvents();

  return res.json({
    events,
    firebaseReady,
    storageMode: firebaseReady ? 'firebase' : 'local-fallback',
    emailReady: Boolean(getMailer()),
    message: firebaseInitMessage,
  });
});

app.post('/api/vision/state', async (req, res) => {
  const state = String(req.body?.state || '').trim();
  const details = String(req.body?.details || '').trim();
  const userEmail = String(req.body?.userEmail || DEMO_USER.email).trim().toLowerCase();

  if (!state) {
    return res.status(400).json({ error: 'State is required.' });
  }

  const event = await createParcelEvent({
    type: 'system_state',
    userEmail,
    vendor: 'DropDroid Vision',
    title: `System state: ${state}`,
    message: details || `DropDroid vision pipeline moved to ${state}.`,
    classification: state,
    notificationStatus: 'Live update',
  });

  return res.status(201).json({ event });
});

app.post('/api/auth/register', async (req, res) => {
  const name = String(req.body?.name || '').trim();
  const email = String(req.body?.email || '').trim().toLowerCase();
  const password = String(req.body?.password || '').trim();

  if (!name || !email || !password) {
    return res.status(400).json({ error: 'Please provide name, email, and password.' });
  }

  if (password.length < 6) {
    return res.status(400).json({ error: 'Password should be at least 6 characters.' });
  }

  const existingUser = await findUserByEmail(email);
  if (existingUser) {
    return res.status(409).json({ error: 'This email is already registered.' });
  }

  const user = await createUserRecord({ name, email, password });
  return res.status(201).json({ user });
});

app.post('/api/auth/login', async (req, res) => {
  const email = String(req.body?.email || '').trim().toLowerCase();
  const password = String(req.body?.password || '').trim();

  if (!email || !password) {
    return res.status(400).json({ error: 'Please provide email and password.' });
  }

  const user = await findUserByEmail(email);

  if (!user || user.passwordHash !== hashPassword(password)) {
    return res.status(401).json({ error: 'Invalid email or password.' });
  }

  return res.json({
    user: {
      uid: user.uid,
      name: user.name,
      email: user.email,
    },
  });
});

app.get('/api/dashboard', async (req, res) => {
  const email = String(req.query?.email || '').trim().toLowerCase();
  if (!email) {
    return res.status(400).json({ error: 'User email is required.' });
  }

  const { schedules, events } = await getDashboardData(email);

  return res.json({
    schedules,
    events,
    latestEvent: events[0] || null,
    storageMode: firebaseReady ? 'firebase' : 'local-fallback',
  });
});

app.post('/api/schedules', async (req, res) => {
  const userEmail = String(req.body?.userEmail || '').trim().toLowerCase();
  const orderId = String(req.body?.orderId || '').trim();
  const pickupDate = String(req.body?.pickupDate || '').trim();
  const pickupTime = String(req.body?.pickupTime || '').trim();
  const vendor = String(req.body?.vendor || '').trim();
  const senderEmail = String(req.body?.senderEmail || '').trim().toLowerCase();

  if (!userEmail || !orderId || !pickupDate || !pickupTime || !vendor || !senderEmail) {
    return res.status(400).json({ error: 'Please provide all schedule details, including sender email.' });
  }

  const savedSchedule = await createScheduleRecord({
    userEmail,
    orderId,
    pickupDate,
    pickupTime,
    vendor,
    senderEmail,
  });

  await createParcelEvent({
    type: 'schedule_created',
    userEmail,
    orderId,
    vendor,
    title: 'Pickup scheduled',
    message: `${vendor} order ${orderId} has been scheduled for ${pickupDate} at ${pickupTime}.`,
    classification: 'Awaiting detection',
    notificationStatus: 'Pending',
  });

  return res.status(201).json({ schedule: savedSchedule });
});

app.post('/api/detect', async (req, res) => {
  const scheduleId = String(req.body?.scheduleId || '').trim();
  if (!scheduleId) {
    return res.status(400).json({ error: 'Schedule id is required.' });
  }

  const schedule = await findScheduleById(scheduleId);

  if (!schedule) {
    return res.status(404).json({ error: 'Schedule was not found.' });
  }

  const objectLabel = String(req.body?.objectLabel || 'Parcel box').trim();
  const confidence = Number(req.body?.confidence || (0.9 + Math.random() * 0.08).toFixed(2));
  const classification = classifyParcel(schedule.vendor, objectLabel);
  const emailResult = await sendNotificationEmail({
    senderEmail: schedule.senderEmail,
    orderId: schedule.orderId,
    vendor: schedule.vendor,
    classification,
    pickupDate: schedule.pickupDate,
    pickupTime: schedule.pickupTime,
  });

  const updatedSchedule = await updateScheduleDetection(scheduleId, {
    latestObjectLabel: objectLabel,
    confidence,
    classification,
    status: 'Detected and classified',
    notificationStatus: emailResult.status,
  });

  const event = await createParcelEvent({
    type: 'parcel_detected',
    userEmail: schedule.userEmail,
    orderId: schedule.orderId,
    vendor: schedule.vendor,
    title: 'Parcel detected',
    message: `${objectLabel} detected and classified as ${classification}.`,
    objectLabel,
    confidence,
    classification,
    notificationStatus: emailResult.status,
  });

  return res.json({
    event,
    schedule: updatedSchedule,
  });
});

await seedDemoUser();

app.listen(PORT, () => {
  console.log(`DropDroid API running on http://localhost:${PORT}`);
  console.log(firebaseInitMessage);
});
