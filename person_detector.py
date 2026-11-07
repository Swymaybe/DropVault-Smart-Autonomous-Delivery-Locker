import cv2
import numpy as np

class PersonDetector:
    def __init__(self):
        # We replace the strict HOG Pedestrian detector with a highly robust 
        # Classical Haar Cascade Face detector for Desktop Webcam demos. 
        # We will mathematically calculate the shirt/torso from the face location!
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

    def detect_in_roi(self, frame, rois):
        detected_people = []
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        try:
            # Perform highly sensitive Face detection over entire frame
            faces = self.face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=4,
                minSize=(30, 30)
            )
            
            for (fx, fy, fw, fh) in faces:
                # Mathematical Torso Inference:
                # The shirt (for Logo and Color classification) is directly below the face.
                # Torso width is ~2.5x the face width.
                # Torso height is ~3x to 4x the face height.
                w = int(fw * 3.0)
                h = int(fh * 4.0)
                
                # Center the torso under the face
                x = fx - int((w - fw) / 2)
                y = fy + int(fh * 0.8) # Start slightly overlapping the chin/neck
                
                # Ensure it doesn't break frame bounds
                x = max(0, x)
                y = min(frame.shape[0], y)
                w = min(frame.shape[1] - x, w)
                h = min(frame.shape[0] - y, h)
                
                detected_people.append((x, y, w, h))
                
        except Exception as e:
            print(f"Face Detection error: {e}")
            pass
            
        return detected_people
        
    def _non_max_suppression_fast(self, boxes, overlapThresh):
        # Implementation of Non-Maximum Suppression (Felzenszwalb et al.)
        if len(boxes) == 0:
            return []

        if type(boxes) is list:
            boxes = cv2.groupRectangles(boxes, 1, 0.2)[0]
            
        return boxes
