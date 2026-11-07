import cv2
import numpy as np
import config

try:
    from skimage.feature import hog as skimage_hog
except ModuleNotFoundError:
    skimage_hog = None

class MotionDetector:
    def __init__(self):
        # MOG2 is excellent for background subtraction
        self.back_sub = cv2.createBackgroundSubtractorMOG2(
            history=config.MOG2_HISTORY, 
            varThreshold=config.MOG2_VAR_THRESHOLD, 
            detectShadows=True
        )

    def get_motion_rois(self, frame):
        """
        Returns bounding boxes (x, y, w, h) of moving objects.
        This provides a massive speedup by restricting where HOG runs.
        """
        fg_mask = self.back_sub.apply(frame)
        
        # Shadows are usually marked as 127. Let's threshold to only get true foreground (255)
        _, fg_mask = cv2.threshold(fg_mask, 254, 255, cv2.THRESH_BINARY)
        
        # Clean up the mask via morphological open/close
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel)
        
        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        rois = []
        for contour in contours:
            if cv2.contourArea(contour) > config.MIN_MOTION_AREA:
                rois.append(cv2.boundingRect(contour))
                
        return rois

def bb_intersection_over_union(boxA, boxB):
    """Computes IOU between two bounding boxes."""
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[0] + boxA[2], boxB[0] + boxB[2])
    yB = min(boxA[1] + boxA[3], boxB[1] + boxB[3])

    interArea = max(0, xB - xA) * max(0, yB - yA)

    boxAArea = boxA[2] * boxA[3]
    boxBArea = boxB[2] * boxB[3]

    iou = interArea / float(boxAArea + boxBArea - interArea)
    return iou

def _compute_hog_features(gray_image):
    """Compute HOG features using scikit-image when available, else OpenCV."""
    if skimage_hog is not None:
        return skimage_hog(
            gray_image,
            orientations=9,
            pixels_per_cell=(8, 8),
            cells_per_block=(2, 2),
            transform_sqrt=True,
            block_norm="L2-Hys",
        )

    descriptor = cv2.HOGDescriptor(
        _winSize=(128, 128),
        _blockSize=(16, 16),
        _blockStride=(8, 8),
        _cellSize=(8, 8),
        _nbins=9,
    )
    return descriptor.compute(gray_image).flatten()


def extract_hog_features_for_sklearn(image_roi, target_size=(128, 128)):
    """
    Extracts a flattened HOG feature array suitable for sklearn SVM training.
    Used for custom logo detection and parcel box verification models.
    """
    image_roi = cv2.resize(image_roi, target_size)
    if len(image_roi.shape) == 3:
        image_roi = cv2.cvtColor(image_roi, cv2.COLOR_BGR2GRAY)

    features = _compute_hog_features(image_roi)
    return features


def extract_color_histogram(image_roi, bins=16):
    """
    Extracts a 1D Hue Histogram to better distinguish Red (Zomato) vs Orange (Swiggy).
    Uses only Hue (0-180) to ignore lighting/brightness variations.
    """
    hsv = cv2.cvtColor(image_roi, cv2.COLOR_BGR2HSV)
    # Hue range is 0-180. 180 / 16 = 11.25 per bin.
    hist = cv2.calcHist([hsv], [0], None, [bins], [0, 180])
    cv2.normalize(hist, hist)
    return hist.flatten()

def extract_combined_features(image_roi, target_size=(128, 128), include_color=True):
    """
    Unified feature extractor: HOG (Shape) + Hue Histogram (Color).
    Specifically handles Red/Orange distinction better than mean averages.
    """
    image_roi = cv2.resize(image_roi, target_size)
    
    # 1. Shape Feature: HOG
    gray = cv2.cvtColor(image_roi, cv2.COLOR_BGR2GRAY)
    hog_feat = _compute_hog_features(gray)
    
    if not include_color:
        return hog_feat
        
    # 2. Color Feature: 16-bin Hue Histogram
    # Focus on the center to avoid background/desk color confusion
    h, w = image_roi.shape[:2]
    center_roi = image_roi[int(h*0.2):int(h*0.8), int(w*0.2):int(w*0.8)]
    color_feat = extract_color_histogram(center_roi, bins=16)
    
    # Concatenate HOG (8100) + Color (16)
    return np.hstack([hog_feat, color_feat])

def extract_parcel_features(image_roi, target_size=(128, 128)):
    """
    Legacy wrapper for Parcel SVM (HOG + Hue Histogram).
    """
    return extract_combined_features(image_roi, target_size, include_color=True)
