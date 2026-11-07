import argparse
import time

from firebase_manager import cloud_db
from notifier_local import notify_parcel_secured


def run_simulation(company, parcel_type):
    print('Running DropDroid simulation mode...')
    flow = [
        ('APPROACH_DETECTED', 'Motion detected near the delivery vault.'),
        ('CLASSIFYING_AGENT', f'Identifying agent uniform: {company}.'),
        ('MONITORING_DROP', 'Parcel placed inside the delivery zone.'),
        ('SCANNING_LABEL', 'Scanning parcel label and verification code.'),
    ]

    for state, details in flow:
        print(f' -> {state}: {details}')
        cloud_db.update_live_state(state, details)
        time.sleep(1.0)

    ocr_text = f'{company} {parcel_type} verified'
    notify_parcel_secured(company=company, parcel_type=parcel_type, ocr_text=ocr_text)
    cloud_db.log_delivery(company=company, package=parcel_type, ocr_text=ocr_text)
    cloud_db.update_live_state('SECURED', f'{parcel_type} secured and dashboard updated.')

    # Give the background API calls a moment to complete before the one-off script exits.
    time.sleep(2.0)
    print('Simulation complete. Refresh the dashboard to see the live update.')


def discover_cameras(max_index=3):
    import cv2

    backends = [
        ('DEFAULT', None),
        ('DSHOW', cv2.CAP_DSHOW),
        ('MSMF', cv2.CAP_MSMF),
    ]
    available = []

    for index in range(max_index + 1):
        for backend_name, backend in backends:
            cap = cv2.VideoCapture(index) if backend is None else cv2.VideoCapture(index, backend)
            opened = cap.isOpened()
            ret, frame = cap.read() if opened else (False, None)
            cap.release()

            if ret and frame is not None:
                available.append((index, backend_name, frame.shape[1], frame.shape[0]))
                break

    return available


def open_camera(preferred_index=0):
    import cv2

    backends = [
        ('DSHOW', cv2.CAP_DSHOW),
        ('MSMF', cv2.CAP_MSMF),
        ('DEFAULT', None),
    ]
    candidate_indexes = [preferred_index, 0, 1, 2, 3]
    seen_indexes = set()

    for index in candidate_indexes:
        if index in seen_indexes:
            continue
        seen_indexes.add(index)

        for backend_name, backend in backends:
            cap = cv2.VideoCapture(index) if backend is None else cv2.VideoCapture(index, backend)
            if not cap.isOpened():
                cap.release()
                continue

            ret, frame = cap.read()
            if ret and frame is not None:
                print(f'Using camera {index} via {backend_name} backend ({frame.shape[1]}x{frame.shape[0]}).')
                return cap

            cap.release()

    return None


def run_camera(camera_index=0):
    import cv2
    from state_machine import SmartParcelMachine

    print('Initializing Smart Parcel Receiving System...')
    system = SmartParcelMachine()

    cap = open_camera(camera_index)

    if cap is None:
        available = discover_cameras()
        print('Error: Cannot open video source.')
        if available:
            print('Detected cameras:')
            for index, backend_name, width, height in available:
                print(f'  - camera {index} via {backend_name} ({width}x{height})')
            print('Try one explicitly, for example: `python main.py --camera-index 1`.')
        else:
            print('No working cameras were detected. Check Windows camera permissions and close other apps using the webcam.')
        print('Use `python main.py --simulate` to test the website integration without a camera.')
        return

    print('System online. Monitoring... Press q to quit.')

    while True:
        ret, frame = cap.read()
        if not ret:
            print('Video stream ended or connection lost.')
            break

        current_state = system.process_frame(frame)

        cv2.putText(
            frame,
            f'System State: {current_state}',
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2,
        )

        dx, dy, dw, dh = __import__('config').DELIVERY_ZONE_RECT
        cv2.rectangle(frame, (dx, dy), (dx + dw, dy + dh), (255, 255, 255), 2)
        cv2.putText(
            frame,
            '[ PARCEL DROP ZONE ]',
            (dx + 10, dy - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            2,
        )

        cv2.imshow('Smart Parcel Receiving Monitor', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description='DropDroid Python vision bridge')
    parser.add_argument('--simulate', action='store_true', help='Push a simulated parcel detection update')
    parser.add_argument('--company', default='Amazon', help='Company name for simulation mode')
    parser.add_argument('--parcel', default='Parcel box', help='Parcel label for simulation mode')
    parser.add_argument('--camera-index', type=int, default=0, help='Webcam index for live mode')
    parser.add_argument('--list-cameras', action='store_true', help='List available webcam indexes and exit')
    args = parser.parse_args()

    if args.list_cameras:
        cameras = discover_cameras()
        if cameras:
            print('Available cameras:')
            for index, backend_name, width, height in cameras:
                print(f'  - camera {index} via {backend_name} ({width}x{height})')
        else:
            print('No working cameras were detected.')
        return

    if args.simulate:
        run_simulation(args.company, args.parcel)
        return

    try:
        run_camera(args.camera_index)
    except ModuleNotFoundError as exc:
        print(f'Module missing: {exc}')
        print('Install the computer-vision dependencies or use `python main.py --simulate`.')


if __name__ == '__main__':
    main()
