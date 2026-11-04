from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from app.registration import requirements, normalize_settings, validate_registration
from app.schemas import TokenCreate


def legacy_db():
    db = Mock()
    db.get.side_effect = lambda model, key: SimpleNamespace(value={
        'required': ['patient_name'], 'enabled': ['patient_name'],
    }) if key == 'registration_fields' else None
    return db


def test_legacy_settings_keep_mri_enabled_and_required():
    config = requirements(legacy_db())
    assert 'mri_area' in config['enabled']
    assert 'mri_area' in config['required']
    saved = normalize_settings({'required': ['patient_name'], 'enabled': ['patient_name']}, config)
    assert 'mri_area' in saved['enabled']
    assert 'mri_area' in saved['required']


@pytest.mark.parametrize('area', [None, '', '   '])
def test_registration_rejects_empty_mri_area(area):
    with pytest.raises(HTTPException) as error:
        validate_registration(legacy_db(), TokenCreate(patient_name='Test patient', mri_area=area))
    assert error.value.status_code == 422
    assert 'Area of body for MRI' in error.value.detail


def test_registration_accepts_mri_area():
    result = validate_registration(legacy_db(), TokenCreate(patient_name='Test patient', mri_area='Brain'))
    assert result.mri_area == 'Brain'
