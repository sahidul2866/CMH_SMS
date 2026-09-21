"""Database-backed registration field definitions and server-side input policy."""
from datetime import date
import math
import re

from fastapi import HTTPException
from .models import AppSetting

FIELDS = {
    'patient_name': 'Name', 'patient_phone': 'Contact number', 'patient_source': 'Patient source',
    'service_number': 'Service No./BA', 'age': 'Age', 'unit': 'Unit',
    'mri_area': 'Area of body for MRI', 'contrast': 'Contrast', 'film': 'Film', 'report': 'Report',
    'rank': 'Designation / Rank', 'priority': 'Patient priority',
    'beneficiary_type': 'Patient type', 'entitlement': 'Entitlement', 'service_status': 'Service status',
    'sponsor_rank': 'Sponsor rank', 'family_relationship': 'Family relationship',
}


def requirements(db):
    setting = db.get(AppSetting, 'registration_fields')
    value = setting.value if setting else {}
    return {'fields': FIELDS, 'required': value.get('required', ['patient_name', 'family_relationship', 'sponsor_rank']),
            'enabled': value.get('enabled', list(FIELDS)), 'custom': value.get('custom', [])}


def normalize_settings(value, previous):
    required = value.get('required')
    enabled = value.get('enabled', previous['enabled'])
    for items in [required, enabled]:
        if not isinstance(items, list) or any(not isinstance(key, str) or key not in FIELDS for key in items):
            raise HTTPException(422, 'Select supported registration fields')
    if 'patient_name' not in required or 'patient_name' not in enabled:
        raise HTTPException(422, 'Patient name must remain enabled and required')
    if not set(required) <= set(enabled):
        raise HTTPException(422, 'A disabled field cannot be required')
    custom = value.get('custom', previous['custom'])
    if not isinstance(custom, list) or len(custom) > 50:
        raise HTTPException(422, 'Use at most 50 custom fields')
    old = {field['key']: field for field in previous['custom']}
    result, keys = [], set()
    for field in custom:
        if not isinstance(field, dict):
            raise HTTPException(422, 'Invalid custom field')
        key, label, kind = field.get('key'), field.get('label'), field.get('type')
        if not isinstance(key, str) or not re.fullmatch(r'custom_[a-z0-9_]{1,60}', key) or key in keys:
            raise HTTPException(422, 'Custom field keys must be unique and start with custom_')
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= 100 or kind not in ['text', 'number', 'date', 'select']:
            raise HTTPException(422, 'Provide a label and supported custom field type')
        if key in old and kind != old[key]['type']:
            raise HTTPException(422, 'Saved field types cannot change; disable the field and add another')
        active, mandatory = field.get('enabled', True), field.get('required', False)
        if not isinstance(active, bool) or not isinstance(mandatory, bool) or mandatory and not active:
            raise HTTPException(422, 'Custom fields need valid enabled/required settings')
        options = field.get('options', [])
        if not isinstance(options, list) or len(options) > 100 or any(not isinstance(v, str) or not 1 <= len(v.strip()) <= 100 for v in options):
            raise HTTPException(422, 'Use at most 100 non-empty dropdown choices')
        options = list(dict.fromkeys(v.strip() for v in options))
        if kind == 'select' and not options:
            raise HTTPException(422, 'Dropdown fields need choices')
        keys.add(key)
        result.append(dict(key=key, label=label.strip(), type=kind, enabled=active, required=mandatory, options=options if kind == 'select' else []))
    if not set(old) <= keys:
        raise HTTPException(422, 'Disable saved custom fields instead of deleting them to preserve history')
    return {'required': sorted(set(required)), 'enabled': sorted(set(enabled)), 'custom': result}


def applicable(db, payload, key):
    from .models import LookupOption
    from sqlalchemy import select
    def code(field):
        value = getattr(payload, field, None)
        option = db.scalar(select(LookupOption).where(LookupOption.category == field, LookupOption.value == value)) if value else None
        return (option.metadata_json or {}).get('report_code', value) if option else value
    family, military = code('beneficiary_type') == 'family', code('entitlement') == 'military'
    return {'rank': not family, 'service_status': military, 'family_relationship': family,
            'sponsor_rank': family and military}.get(key, True)


def blank(value):
    return value is None or isinstance(value, str) and not value.strip()


def validate_registration(db, payload, existing=None, check_required=True):
    config = requirements(db)
    enabled = set(config['enabled'])
    updates = {}
    for key in FIELDS:
        if key not in type(payload).model_fields or key in enabled:
            continue
        if key in payload.model_fields_set and not blank(getattr(payload, key)):
            raise HTTPException(422, f'{FIELDS[key]} is disabled and cannot accept input')
        updates[key] = getattr(existing, key) if existing else type(payload).model_fields[key].default
    payload = payload.model_copy(update=updates)
    missing = [FIELDS[key] for key in config['required'] if key in enabled and key in type(payload).model_fields
               and applicable(db, payload, key) and blank(getattr(payload, key))]
    if missing and check_required:
        raise HTTPException(422, 'Required fields: ' + ', '.join(missing))
    if 'custom_fields' not in type(payload).model_fields:
        return payload
    definitions = {field['key']: field for field in config['custom']}
    supplied = payload.custom_fields
    if set(supplied) - set(definitions):
        raise HTTPException(422, 'Unknown custom field')
    values = dict(getattr(existing, 'custom_fields', {}) or {})
    for key, field in definitions.items():
        value = supplied.get(key)
        if not field['enabled']:
            if not blank(value):
                raise HTTPException(422, f"{field['label']} is disabled and cannot accept input")
            continue
        if blank(value):
            if field['required']:
                raise HTTPException(422, f"Required field: {field['label']}")
            values.pop(key, None)
            continue
        valid = False
        if field['type'] == 'number':
            try:
                valid = type(value) in (int, float) and math.isfinite(value)
            except OverflowError:
                valid = False
        elif isinstance(value, str):
            value = value.strip()
            valid = len(value) <= 2000
            if field['type'] == 'select':
                valid = value in field['options']
            elif field['type'] == 'date':
                try:
                    valid = date.fromisoformat(value).isoformat() == value
                except ValueError:
                    valid = False
        if not valid:
            raise HTTPException(422, f"Invalid value for {field['label']}")
        values[key] = value
    return payload.model_copy(update={'custom_fields': values})
