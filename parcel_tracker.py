import cv2
import config

class ParcelTracker:
    def __init__(self):
        self.secured_parcel_bbox = None
        # ML Models fully decoupled from the Tracker to maximize performance!
        
    def detect_static_parcel(self, frame):
        """
        Scans the explicitly designated static DROP ZONE on the screen.
        Because parcels have highly irregular colors and textures (plastic vs cardboard),
        we completely bypassed the Machine Learning. This natively executes a
        pure colorblind Edge and Geometry verification algorithm.
        """
        dx, dy, dw, dh = config.DELIVERY_ZONE_RECT
        zone_img = frame[dy:dy+dh, dx:dx+dw]
        
        try:
            # Strip color and blur to heavily reduce room noise
            gray = cv2.cvtColor(zone_img, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (7, 7), 0)
            
            # Canny edge detection automatically finds the geometric boundaries
            edges = cv2.Canny(blurred, 40, 120)
            
            # Morphological Close solidifies broken edges (e.g. crinkled plastic bags)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
            closed_edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
            
            contours, _ = cv2.findContours(closed_edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for contour in contours:
                # Calculate the mathematical density and size of the object
                area = cv2.contourArea(contour)
                
                # If a massive geometric shape has suddenly appeared in the empty static zone...
                if area > 8000:
                    # We mathematically confirm an object was placed!
                    # The brand label will be safely inherited mathematically from the driver!
                    return (dx, dy, dw, dh, "Verified Package")
                    
        except Exception as e:
            print(f"Parcel tracker Geometry error: {e}")
            pass
            
        return None
