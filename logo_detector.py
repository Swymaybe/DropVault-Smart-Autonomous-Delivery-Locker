import cv2
import pickle
import os
import config
from vision_utils import extract_combined_features

class LogoDetector:
    def __init__(self):
        self.model = None
        if os.path.exists(config.LOGO_SVM_MODEL):
            with open(config.LOGO_SVM_MODEL, 'rb') as f:
                self.model = pickle.load(f)
                
    def verify_logo(self, person_roi):
        """
        Takes the upper-half of the person (the chest) and evaluates the logo.
        Returns the company name, or None if confidence is low.
        """
        if self.model is None:
            return None
            
        # The SVM was trained on tight crops. In a real system you'd use a sliding window 
        # But for this speed optimization, we scale the chest to the target size.
        feat = extract_combined_features(person_roi, target_size=(64, 64), include_color=True)
        features = feat.reshape(1, -1)
        
        prediction = self.model.predict(features)[0]
        confidence = max(self.model.predict_proba(features)[0])
        
        if confidence > 0.6:
            return f"{prediction} ({confidence * 100:.0f}%)"
        return f"Unknown Logo ({confidence * 100:.0f}%)"
