import os

# SVM Models
MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
COMPANY_SVM_MODEL = os.path.join(MODELS_DIR, "company_svm.pkl")
PARCEL_SVM_MODEL = os.path.join(MODELS_DIR, "parcel_svm.pkl")
LOGO_SVM_MODEL = os.path.join(MODELS_DIR, "logo_svm.pkl")

# Motion Config (MOG2)
MOG2_HISTORY = 500
MOG2_VAR_THRESHOLD = 50
MIN_MOTION_AREA = 1000

# Person Detection (HOG)
HOG_WIN_STRIDE = (8, 8)
HOG_PADDING = (16, 16)
HOG_SCALE = 1.05

# Company Classification (LBP + HSV)
LBP_RADIUS = 3
LBP_N_POINTS = 8 * LBP_RADIUS
HSV_BINS = (16, 16) # Hue, Saturation

# Parcel Detection
DELIVERY_ZONE_RECT = (150, 250, 300, 200) # (x, y, w, h)
MIN_PARCEL_AREA = 2500
MAX_PARCEL_AREA = 40000
MIN_ASPECT_RATIO = 0.5   # Width / Height
MAX_ASPECT_RATIO = 2.0


# Theft Detection
THEFT_IOU_THRESHOLD = 0.5

# Cloud Database (Firebase)
FIREBASE_DB_URL = "https://dropdroid-87d9b-default-rtdb.firebaseio.com/"
FIREBASE_KEY_PATH = os.path.join(os.path.dirname(__file__), "firebase_key.json")

# Website / backend bridge
DROPDROID_API_BASE = os.getenv("DROPDROID_API_BASE", "http://localhost:8787")
DEFAULT_USER_EMAIL = os.getenv("DROPDROID_USER_EMAIL", "user@dropdroid.com")
ACTIVE_SCHEDULE_ID = os.getenv("DROPDROID_ACTIVE_SCHEDULE_ID", "").strip()

