from datetime import datetime


def _timestamp():
    return datetime.now().strftime('%I:%M %p')


def notify_parcel_secured(company='Unknown', parcel_type='Parcel', ocr_text=''):
    message = f"[{_timestamp()}] Parcel secured: {company} / {parcel_type}"
    if ocr_text:
        message += f" | Label: {ocr_text}"
    print(message)
    return message


def notify_theft_alert(company='Unknown', parcel_type='Parcel'):
    message = f"[{_timestamp()}] THEFT ALERT: {company} / {parcel_type} removed without authorization"
    print(message)
    return message
