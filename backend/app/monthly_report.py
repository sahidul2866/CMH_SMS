"""MRI patient-state report. Categories are snapshots, never inferred for legacy rows."""
from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta, timezone
from io import BytesIO
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, Side
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import require_permission
from .database import get_db
from .models import AuditEvent, LookupOption, QueueToken, User
from .schemas import ReportClassification, TokenRead

COLUMNS = [
    ('serving_officer', 'SERVING', "OFFR’S + AFNS"),
    ('serving_cadet', 'SERVING', 'OFF / NURSING CADET'),
    ('serving_jco_or', 'SERVING', 'JCO’S / OR / RECT'),
    ('serving_nce', 'SERVING', 'NCE'),
    ('serving_civil', 'SERVING', 'ALL CIV ENTD'),
    ('retired_officer', 'RETD (MIL)', 'OFFR’S / OFFR’S FAMILY'),
    ('retired_or', 'RETD (MIL)', 'OR’S'),
    ('family_officer', 'FAMILY', 'OFFR’S'),
    ('family_jco_or_nce', 'FAMILY', 'JCO’S / OR’S & NCE'),
    ('family_civil', 'FAMILY', 'ALL CIV ENTD'),
    ('re', '', 'RE'), ('cne', '', 'CNE'),
]
GROUPS = [('officer', 'Officers / AFNS'), ('cadet', 'Officer / Nursing cadet'),
          ('jco', 'JCO'), ('or', 'OR / Recruit'), ('nce', 'NCE')]
CLASSIFICATION_LOOKUPS = {
    'beneficiary_type': [('self', 'Self'), ('family', 'Family')],
    'service_status': [('serving', 'Serving'), ('retired', 'Retired')],
    'entitlement': [('military', 'Military'), ('civil', 'Civil entitled'), ('re', 'RE'), ('cne', 'CNE')],
    'family_relationship': [('spouse', 'Spouse'), ('child', 'Child'), ('parent', 'Parent'), ('other', 'Other dependent')],
}
RANK_GROUPS = dict.fromkeys(['brigadier_general', 'colonel', 'lieutenant_colonel', 'major', 'captain', 'lieutenant', 'officer'], 'officer')
RANK_GROUPS.update(warrant_officer='jco', jco='jco', sergeant='or', corporal='or', shoinik='or', soldier='or')
router = APIRouter(prefix='/api/v1', tags=['Monthly MRI summary'])


def classify(db: Session, payload) -> str | None:
    """Resolve only documented combinations. Unknown combinations stay visible for review."""
    values = {}
    for field in CLASSIFICATION_LOOKUPS:
        value = getattr(payload, field, None)
        if not value:
            values[field] = None
            continue
        option = db.scalar(select(LookupOption).where(LookupOption.category == field, LookupOption.value == value, LookupOption.is_active.is_(True)))
        if not option:
            raise HTTPException(422, f'Unknown or inactive {field.replace("_", " ")}')
        values[field] = (option.metadata_json or {}).get('report_code', value)
    if values['entitlement'] in ('re', 'cne'):
        return values['entitlement']
    person = values['beneficiary_type']
    if person not in ('self', 'family'):
        return None
    if person == 'family' and not values['family_relationship']:
        raise HTTPException(422, 'Select the family relationship')
    if values['entitlement'] == 'civil':
        return 'family_civil' if person == 'family' else 'serving_civil'
    if values['entitlement'] != 'military':
        return None
    rank = payload.sponsor_rank if person == 'family' else getattr(payload, 'rank', None)
    option = db.scalar(select(LookupOption).where(LookupOption.category == 'rank_relationship', LookupOption.value == rank, LookupOption.is_active.is_(True))) if rank else None
    if person == 'family' and not option:
        raise HTTPException(422, 'Select an active sponsor rank for a military family patient')
    group = (option.metadata_json or {}).get('report_group') if option else None
    status = values['service_status']
    if status == 'retired':
        if group == 'officer':
            return 'retired_officer'
        if person == 'self' and group == 'or':
            return 'retired_or'
        return None  # The supplied sheet does not establish other retired-family mappings.
    if status != 'serving':
        return None
    if person == 'family':
        return 'family_officer' if group == 'officer' else 'family_jco_or_nce' if group in ('jco', 'or', 'nce') else None
    return {'officer': 'serving_officer', 'cadet': 'serving_cadet', 'jco': 'serving_jco_or', 'or': 'serving_jco_or', 'nce': 'serving_nce'}.get(group)


def month_rows(db, month, basis):
    try:
        start = date.fromisoformat(month + '-01')
    except ValueError:
        raise HTTPException(422, 'Month must use YYYY-MM')
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    stmt = select(QueueToken)
    if basis == 'completed':
        zone = ZoneInfo('Asia/Dhaka')
        def utc_boundary(day):
            return datetime.combine(day, time.min, zone).astimezone(timezone.utc).replace(tzinfo=None)
        stmt = stmt.where(QueueToken.status == 'completed', QueueToken.completed_at >= utc_boundary(start), QueueToken.completed_at < utc_boundary(end))
    else:
        stmt = stmt.where(QueueToken.token_date >= start, QueueToken.token_date < end)
    records = list(db.scalars(stmt.order_by(QueueToken.token_date, QueueToken.sequence)))
    return start, end, records


def record_day(token, basis):
    if basis == 'completed':
        return token.completed_at.replace(tzinfo=timezone.utc).astimezone(ZoneInfo('Asia/Dhaka')).date()
    return token.token_date


def summary(db, month, basis):
    start, end, records = month_rows(db, month, basis)
    keys = [c[0] for c in COLUMNS] + ['unclassified']
    days = { (start + timedelta(days=i)).isoformat(): dict.fromkeys(keys, 0) for i in range((end-start).days)}
    for token in records:
        key = token.summary_category if token.summary_category in keys else 'unclassified'
        days[record_day(token, basis).isoformat()][key] += 1
    rows = [{'date': day, 'counts': counts, 'total': sum(counts.values())} for day, counts in days.items()]
    totals = {key: sum(row['counts'][key] for row in rows) for key in keys}
    return {'month': month, 'basis': basis, 'columns': [{'key': key, 'group': group, 'label': label} for key, group, label in COLUMNS], 'rows': rows, 'totals': totals, 'total': len(records)}


@router.get('/reports/mri-summary')
def get_summary(month: str = Query(pattern=r'^\d{4}-\d{2}$'), basis: Literal['registrations', 'completed'] = 'registrations', db: Session = Depends(get_db), _user: User = Depends(require_permission('reports.view'))):
    return summary(db, month, basis)


@router.get('/reports/mri-summary/patients', response_model=list[TokenRead])
def summary_patients(month: str = Query(pattern=r'^\d{4}-\d{2}$'), basis: Literal['registrations', 'completed'] = 'registrations', day: date | None = None, category: str | None = None, db: Session = Depends(get_db), _user: User = Depends(require_permission('reports.view'))):
    _, _, records = month_rows(db, month, basis)
    keys = {c[0] for c in COLUMNS}
    return [token for token in records if (not day or record_day(token, basis) == day) and (not category or (token.summary_category if token.summary_category in keys else 'unclassified') == category)]


class ClassificationCorrection(ReportClassification):
    rank: str | None = None


@router.patch('/tokens/{token_id}/classification', response_model=TokenRead)
def correct_classification(token_id: str, payload: ClassificationCorrection, db: Session = Depends(get_db), user: User = Depends(require_permission('queue.serial.create'))):
    token = db.scalar(select(QueueToken).where(QueueToken.id == token_id).with_for_update())
    if not token:
        raise HTTPException(404, 'Patient not found')
    category = classify(db, payload)
    before = {key: getattr(token, key) for key in payload.model_fields_set}
    before['summary_category'] = token.summary_category
    for key, value in payload.model_dump().items():
        setattr(token, key, value)
    token.summary_category = category
    db.add(AuditEvent(action='token.classification_updated', actor=user.username, token_id=token.id, detail={'before': before, 'after': {**payload.model_dump(), 'summary_category': category}}))
    db.commit()
    return token


@router.get('/reports/mri-summary.{format}')
def export_summary(format: Literal['xlsx', 'pdf'], month: str = Query(pattern=r'^\d{4}-\d{2}$'), basis: Literal['registrations', 'completed'] = 'registrations', db: Session = Depends(get_db), _user: User = Depends(require_permission('reports.view'))):
    report = summary(db, month, basis)
    keys = [c[0] for c in COLUMNS]
    review = report['totals']['unclassified'] > 0
    if review:
        keys += ['unclassified']
    title = f'PATIENT STATE {calendar.month_abbr[int(month[5:])].upper()} {month[:4]}'
    note = ('Registrations (including cancelled registrations)' if basis == 'registrations' else 'Completed MRIs by completion date (Asia/Dhaka)')
    if review:
        note += ' | Needs review: included in total, pending classification'
    first = ['DATE', 'SERVING', '', '', '', '', 'RETD (MIL)', '', 'FAMILY', '', '', 'RE', 'CNE'] + (['NEEDS REVIEW'] if review else []) + ['TOTAL']
    second = [''] + [c[2] for c in COLUMNS[:10]] + ['', ''] + ([''] if review else []) + ['']
    data = [first, second]
    for row in report['rows']:
        data.append([date.fromisoformat(row['date']).strftime('%d.%m.%y')] + [row['counts'][key] for key in keys] + [row['total']])
    data.append(['TOTAL'] + [report['totals'][key] for key in keys] + [report['total']])
    spans = [(1, 5), (6, 7), (8, 10)]
    out = BytesIO()
    if format == 'xlsx':
        book = Workbook()
        sheet = book.active
        sheet.title = 'MRI monthly summary'
        for text in ['DEPARTMENT OF RADIOLOGY & IMAGING', 'CMH DHAKA', title, 'MRI CENTRE', note]:
            sheet.append([text])
            sheet.merge_cells(start_row=sheet.max_row, start_column=1, end_row=sheet.max_row, end_column=len(first))
        for row in data:
            sheet.append(row)
        for left, right in spans:
            sheet.merge_cells(start_row=6, start_column=left+1, end_row=6, end_column=right+1)
        for col in [0, 11, 12] + ([13] if review else []) + [len(first)-1]:
            sheet.merge_cells(start_row=6, start_column=col+1, end_row=7, end_column=col+1)
        from openpyxl.utils import get_column_letter
        for col in range(1, len(first)+1):
            sheet.column_dimensions[get_column_letter(col)].width = 14 if col == 1 else 12
        for row in sheet:
            for cell in row:
                cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
                cell.font = Font(name='Arial', size=10, bold=cell.row <= 7 or cell.row == sheet.max_row)
                if cell.row >= 6:
                    cell.border = Border(*( [Side(style='thin', color='808080')] * 4 ))
                if isinstance(cell.value, str):
                    cell.data_type = 's'
        sheet.row_dimensions[7].height = 45
        sheet.row_dimensions[5].height = 30
        sheet.freeze_panes = 'B8'
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.page_setup.orientation = 'landscape'
        sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
        sheet.page_setup.fitToWidth = sheet.page_setup.fitToHeight = 1
        sheet.print_title_rows = '1:7'
        book.save(out)
        media = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    else:
        styles = getSampleStyleSheet()
        styles['Normal'].fontSize = 6
        styles['Normal'].leading = 8
        styles['Normal'].alignment = 1
        for i in (0, 1):
            data[i] = [Paragraph(str(value).replace('’', "'"), styles['Normal']) for value in data[i]]
        table = Table(data, colWidths=[55] + [(785-55)/(len(first)-1)]*(len(first)-1), repeatRows=2)
        commands = [('GRID', (0,0), (-1,-1), .4, colors.grey), ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('FONTSIZE', (0,0), (-1,-1), 7), ('TOPPADDING', (0,0), (-1,-1), 3), ('BOTTOMPADDING', (0,0), (-1,-1), 3), ('BACKGROUND', (0,0), (-1,1), colors.HexColor('#edf2ef')), ('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold')]
        commands += [('SPAN', (left,0), (right,0)) for left,right in spans]
        commands += [('SPAN',(col,0),(col,1)) for col in [0,11,12] + ([13] if review else []) + [len(first)-1]]
        table.setStyle(TableStyle(commands))
        SimpleDocTemplate(out, pagesize=landscape(A4), leftMargin=25, rightMargin=25, topMargin=15, bottomMargin=15).build([Paragraph('DEPARTMENT OF RADIOLOGY & IMAGING<br/>CMH DHAKA<br/>' + title + '<br/>MRI CENTRE', styles['Normal']), Paragraph(note, styles['Normal']), table])
        media = 'application/pdf'
    return Response(out.getvalue(), media_type=media, headers={'Content-Disposition': f'attachment; filename="mri-summary-{month}-{basis}.{format}"'})
