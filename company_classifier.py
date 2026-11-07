import cv2
import numpy as np
import pickle
import os
import config

class CompanyClassifier:
    def __init__(self):
        self.model = None
        if os.path.exists(config.COMPANY_SVM_MODEL):
            with open(config.COMPANY_SVM_MODEL, 'rb') as f:
                self.model = pickle.load(f)
                
    def extract_features(self, image_roi):
        """
        Unified feature extractor: HOG (Shape) + Hue Histogram (Color).
        Ensures consistent Red/Orange distinction across all models.
        """
        from vision_utils import extract_combined_features
        return extract_combined_features(image_roi, target_size=(128, 128), include_color=True)

    def predict(self, image_roi):
        """
        Predicts company given an ROI slice using Confidence Thresholds.
        """
        if self.model is None:
            return "UNKNOWN (Model Config Missing)"
            
        features = self.extract_features(image_roi)
        features = features.reshape(1, -1)
        
        try:
            probabilities = self.model.predict_proba(features)[0]
            max_prob_index = np.argmax(probabilities)
            prediction = self.model.classes_[max_prob_index]
            max_prob = probabilities[max_prob_index]
            
            # Enforce a strict 65% confidence threshold for HSV colors
            if max_prob >= 0.65:
                return f"{prediction} ({max_prob * 100:.0f}%)"
            else:
                return f"Unknown Uniform ({max_prob * 100:.0f}%)"
        except Exception:
            # Fallback if probability=True was missing from trained model
            return self.model.predict(features)[0]
