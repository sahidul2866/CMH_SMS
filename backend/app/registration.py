"""Shared registration requirements for reception and appointment check-in."""
from fastapi import HTTPException

from .models import AppSetting

FIELDS = {
    'patient_name': 'Name', 'patient_source': 'Patient source',
    'service_number': 'Service No./BA', 'age': 'Age', 'unit': 'Unit',
    'mri_area': 'Area of body for MRI', 'contrast': 'Contrast', 'film': 'Film', 'report': 'Report',
}


def requirements(db):
    setting = db.get(AppSetting, 'registration_fields')
    return {'fields': FIELDS, 'required': setting.value['required'] if setting else ['patient_name']}


def validate_registration(db, payload):
    missing = [FIELDS[key] for key in requirements(db)['required']
               if getattr(payload, key, None) is None or str(getattr(payload, key)).strip() == '']
    if missing:
        raise HTTPException(422, 'Required fields: ' + ', '.join(missing))
