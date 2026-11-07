import time
from vision_utils import MotionDetector, bb_intersection_over_union
from person_detector import PersonDetector
from company_classifier import CompanyClassifier
from parcel_tracker import ParcelTracker
from label_reader import LabelReader
from logo_detector import LogoDetector
from notifier_local import notify_parcel_secured, notify_theft_alert
from firebase_manager import cloud_db
import config
import cv2

class State:
    IDLE = 'IDLE'
    APPROACH = 'APPROACH_DETECTED'
    VERIFY_AGENT = 'CLASSIFYING_AGENT'
    DROP = 'MONITORING_DROP'
    SCAN_LABEL = 'SCANNING_LABEL'
    SECURED = 'SECURED'
    THEFT_ALERT = 'THEFT_ALERT'

class SmartParcelMachine:
    def __init__(self):
        self.state = State.IDLE
        
        # Modules
        self.motion = MotionDetector()
        self.person_detector = PersonDetector()
        self.classifier = CompanyClassifier()
        self.logo_detector = LogoDetector()  # New explicit Logo SVM
        self.tracker = ParcelTracker()
        self.reader = LabelReader()
        
        self.active_person_bbox = None
        self.agent_identity = None
        self.parcel_bbox = None
        self.parcel_type = None
        self.current_motion_rois = []
        
        # Stability counter: SVM must confirm a parcel for N consecutive frames.
        # Lowered to make live demos more responsive on slower webcams/laptops.
        self.parcel_confirm_count = 0
        self.PARCEL_CONFIRM_THRESHOLD = 8
        
        # OCR: capture several frames and pick the sharpest one.
        self.best_ocr_frame = None
        self.best_ocr_sharpness = 0
        self.ocr_scan_attempts = 0
        self.OCR_COLLECT_FRAMES = 12
        
        # Timers
        self.state_enter_time = time.time()

    def _reset(self):
        """Resets the state machine for the next delivery demo."""
        self.active_person_bbox = None
        self.agent_identity = None
        self.parcel_bbox = None
        self.parcel_type = None
        self.current_motion_rois = []
        self.parcel_confirm_count = 0
        self.best_ocr_frame = None
        self.best_ocr_sharpness = 0
        self.ocr_scan_attempts = 0
        self._transition(State.IDLE)

    def process_frame(self, frame):
        """State Machine evaluation per frame."""
        
        if self.state == State.IDLE:
            rois = self.motion.get_motion_rois(frame)
            self.current_motion_rois = rois
            if len(rois) > 0:
                self._transition(State.APPROACH)

        elif self.state == State.APPROACH:
            rois = self.motion.get_motion_rois(frame)
            self.current_motion_rois = rois
            people = self.person_detector.detect_in_roi(frame, rois)
            if len(people) > 0:
                self.active_person_bbox = people[0] # Pick primary person
                self._transition(State.VERIFY_AGENT)
            elif time.time() - self.state_enter_time > 5:
                # Timeout, motion was just wind/animals
                self._transition(State.IDLE)

        elif self.state == State.VERIFY_AGENT:
            x, y, w, h = self.active_person_bbox
            # Extract upper 50% for classification
            upper_body_roi = frame[y:y+int(h/2), x:x+w]
            
            # Cascade Model verification: Try explicit Logo SVM first!
            detected_logo = self.logo_detector.verify_logo(upper_body_roi)
            if detected_logo is not None and not detected_logo.startswith("Unknown"):
                self.agent_identity = detected_logo
                print(f"Agent Extracted from EXPLICIT LOGO SVM: {self.agent_identity}")
                self._transition(State.DROP)
            else:
                detected_uniform = self.classifier.predict(upper_body_roi)
                if not detected_uniform.startswith("Unknown"):
                    self.agent_identity = detected_uniform
                    print(f"Agent Extracted from UNIFORM TEXTURE SVM: {self.agent_identity}")
                    self._transition(State.DROP)
                else:
                    print("Agent uniform unknown! Delivery tracker aborted.")
                    self._reset()

        elif self.state == State.DROP:
            # Look for a static parcel placed within the Designated Drop Zone HUD
            # We require PARCEL_CONFIRM_THRESHOLD consecutive SVM confirmations 
            # before locking, preventing single-frame background false positives!
            parcel_data = self.tracker.detect_static_parcel(frame)
            if parcel_data is not None:
                self.parcel_confirm_count += 1
                self.parcel_bbox = parcel_data[:4]
                
                # SMART OVERRIDE: Inherit the brand identity from the highly-accurate Agent Tracker!
                if self.agent_identity and not self.agent_identity.startswith("Unknown"):
                    brand = self.agent_identity.split(" ")[0] # extract 'Swiggy' from 'Swiggy (89%)'
                    self.parcel_type = f"{brand} Package"
                else:
                    self.parcel_type = parcel_data[4]
                    
                if self.parcel_confirm_count >= self.PARCEL_CONFIRM_THRESHOLD:
                    print(f"Static Parcel CONFIRMED in Drop Zone ({self.parcel_confirm_count} frames)! SVM Class: {self.parcel_type}")
                    self.parcel_confirm_count = 0
                    self._transition(State.SCAN_LABEL)
                else:
                    print(f"Drop Zone: parcel seen ({self.parcel_confirm_count}/{self.PARCEL_CONFIRM_THRESHOLD}) - {self.parcel_type}")
            else:
                # Object left the zone or SVM confidence dropped, reset counter
                if self.parcel_confirm_count > 0:
                    print(f"Drop Zone lost. Counter reset.")
                self.parcel_confirm_count = 0
                if time.time() - self.state_enter_time > 30.0:
                    print("Agent departed without dropping a recognized box into the zone. Resetting.")
                    self._reset()

        elif self.state == State.SCAN_LABEL:
            x, y, w, h = self.parcel_bbox
            parcel_img = frame[y:y+h, x:x+w]
            
            # First try barcode scan
            codes = self.reader.scan_for_codes(parcel_img)
            if len(codes) > 0:
                print(f"Parcel Secured! Barcode Verified: {codes[0]}")
                self._transition(State.SECURED)
                return self.state
            
            # Collect frames and pick the sharpest one for OCR
            import cv2 as _cv2
            gray_check = _cv2.cvtColor(parcel_img, _cv2.COLOR_BGR2GRAY)
            sharpness = _cv2.Laplacian(gray_check, _cv2.CV_64F).var()
            
            if sharpness > self.best_ocr_sharpness:
                self.best_ocr_sharpness = sharpness
                self.best_ocr_frame = parcel_img.copy()
            
            self.ocr_scan_attempts += 1
            print(f"OCR collecting frame {self.ocr_scan_attempts}/{self.OCR_COLLECT_FRAMES} (sharpness: {sharpness:.1f}, best: {self.best_ocr_sharpness:.1f})")
            
            # After collecting enough frames, run OCR on sharpest
            if self.ocr_scan_attempts >= self.OCR_COLLECT_FRAMES:
                text = self.reader.secondary_ocr_scan(self.best_ocr_frame)
                print(f"Parcel Secured! OCR Verified: {text}")
                notify_parcel_secured(
                    company=self.agent_identity or "Unknown",
                    parcel_type=self.parcel_type or "Unknown Package",
                    ocr_text=text
                )
                cloud_db.log_delivery(
                    company=self.agent_identity or "Unknown",
                    package=self.parcel_type or "Unknown Package",
                    ocr_text=text
                )
                self._transition(State.SECURED)
            elif time.time() - self.state_enter_time > 10:
                print("Timeout Scanning. Marking Secured Without ID.")
                cloud_db.log_delivery(
                    company=self.agent_identity or "Unknown",
                    package=self.parcel_type or "Unknown Package",
                    ocr_text="Timeout/Unreadable"
                )
                self._transition(State.SECURED)

        elif self.state == State.SECURED:
            # Auto-reset after 15 seconds so we can demo again
            if time.time() - self.state_enter_time > 15:
                print("--- Delivery secured. Resetting for next delivery ---")
                self._reset()
                return
            
            # Theft Detection Logic - Add a 3 second grace period so the driver can move their hand away!
            if time.time() - self.state_enter_time > 3.0:
                rois = self.motion.get_motion_rois(frame)
                theft_imminent = False
                for r in rois:
                    iou = bb_intersection_over_union(r, self.parcel_bbox)
                    if iou > config.THEFT_IOU_THRESHOLD:
                        theft_imminent = True
                
                if theft_imminent:
                    print("SIREN! UNAUTHORIZED REMOVAL DETECTED!")
                    notify_theft_alert(
                        company=self.agent_identity or "Unknown",
                        parcel_type=self.parcel_type or "Unknown Package"
                    )
                    cloud_db.log_theft(
                        company=self.agent_identity or "Unknown",
                        package=self.parcel_type or "Unknown Package"
                    )
                    self._transition(State.THEFT_ALERT)
        
        elif self.state == State.THEFT_ALERT:
            # Reset after 5 seconds alarm so system can detect next delivery
            if time.time() - self.state_enter_time > 5:
                print("--- Alarm ended. System resetting for next delivery ---")
                self._reset()

        return self.state

    def _transition(self, new_state):
        print(f"System State -> {new_state}")
        self.state = new_state
        self.state_enter_time = time.time()
        
        # PUSH TO CLOUD: Sync the Dashboard exactly with the local state machine!
        agent = self.agent_identity or "Waiting for Agent..."
        pkg = self.parcel_type or "Waiting for Drop..."
        cloud_db.update_live_state(new_state, f"Agent: {agent} | Box: {pkg}")
