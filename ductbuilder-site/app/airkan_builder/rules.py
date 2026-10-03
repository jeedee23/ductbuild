"""Pure parameter validation; no FreeCAD import and no executable JSON."""
from __future__ import annotations
import hashlib
import json
import math
import re
from pathlib import Path
from copy import deepcopy
from .kernel import frame_api
from .pricing import PRICE_PATH, price_for_parameters, rectangular_priced_thicknesses

CATALOGUE_PATH = Path(__file__).with_name('catalogue_rules_v3.json')
CAT = json.loads(CATALOGUE_PATH.read_text(encoding='utf-8'))
FAMILIES = {f['id']: f for f in CAT['families']}
VERSION = CAT['version']
RULESET_SHA256 = hashlib.sha256(CATALOGUE_PATH.read_bytes() + PRICE_PATH.read_bytes()).hexdigest()
DEFAULT_PREFIX = 'GROEP-01'

UI_FIELD_TEXT = {
    'thickness_mode': ('Sheet thickness selection', 'Choose automatic thickness from the largest duct side or select a priced thickness manually.'),
    't_mm': ('Duct sheet thickness', 'Thickness of the duct sheet; this is not the frame-profile thickness.'),
    'airkan_a_mm': ('Legacy compatibility field', 'Not used; automatic thickness follows from the largest clear duct side.'),
    'insertion_mode': ('Sheet-to-frame connection', 'By default, the duct sheet stops at the frame. Select manual insertion only for a confirmed fit.'),
    'insertion_mm': ('Frame insertion depth\n(default 0 mm)', 'Distance the duct sheet enters the frame profile in the axial direction.'),
}

UI_CHOICE_TEXT = {
    'thickness_mode': {
        'HANDMATIG': 'Choose manually',
        'AIRKAN_BC': 'Automatically from duct dimensions',
    },
    'insertion_mode': {
        'BOM_REFERENTIE': 'Sheet stops at frame (default)',
        'HANDMATIGE_INSTEEK': 'Insert sheet into frame manually',
    },
}

class InputError(ValueError):
    pass

def n(value):
    return ('%.3f' % float(value)).rstrip('0').rstrip('.').replace('.', 'p')

def profile_for(a, b):
    return 'A40' if max(float(a), float(b)) > 1250.0 else 'E30'

def profile_depth(profile):
    return {'E30':27.0, 'A40':36.0, 'GEEN':0.0}[profile]

def derive_talpha_source_dimensions(a_mm, c_mm, d_mm, main_length_mm, g_mm, alpha_deg, frame_profile):
    try:
        frame_depth_mm = frame_api()['frame_config'](
            profile=frame_profile,
            length=c_mm,
            width=max(a_mm, c_mm, d_mm),
        )['profile_depth']
    except ValueError as error:
        raise InputError('Talpha frame dimensions are invalid: ' + str(error)) from error
    sheet_main_length_mm = main_length_mm - 2 * frame_depth_mm
    need(sheet_main_length_mm > 0, 'TALPHA main length is too short for both main-port frames.')
    main_x_origin_mm = frame_depth_mm
    right_entry_x_mm = main_length_mm - frame_depth_mm
    frame_return_x_mm = right_entry_x_mm - g_mm
    need(main_x_origin_mm < frame_return_x_mm < right_entry_x_mm, 'TALPHA G must leave room between the two main-port frames.')
    alpha_rad = math.radians(alpha_deg)
    branch_cos = math.cos(alpha_rad)
    branch_sin = math.sin(alpha_rad)
    main_top_slope = (d_mm - a_mm) / sheet_main_length_mm
    denominator = branch_sin - main_top_slope * branch_cos
    need(denominator > 1e-9, 'TALPHA alpha and the main-height taper cannot form a source profile.')
    target_z_mm = a_mm + main_top_slope * (frame_return_x_mm - main_x_origin_mm)
    x_term_mm = frame_return_x_mm - c_mm * branch_sin
    z_term_mm = target_z_mm - a_mm + main_top_slope * main_x_origin_mm + c_mm * branch_cos
    alignment_length_mm = (z_term_mm - main_top_slope * x_term_mm) / denominator
    e_mm = x_term_mm - branch_cos * alignment_length_mm
    need(main_x_origin_mm < e_mm < right_entry_x_mm, 'TALPHA E derived from L, G, C, and alpha leaves no usable main-port section.')
    minimum_return_length_mm = 100.0 / branch_sin
    return {
        'e_mm': e_mm,
        'f_mm': alignment_length_mm + minimum_return_length_mm,
        'alignment_length_mm': alignment_length_mm,
        'minimum_return_length_mm': minimum_return_length_mm,
        'frame_depth_mm': frame_depth_mm,
        'right_entry_x_mm': right_entry_x_mm,
    }

def defaults(family):
    return {'family':family, 'prefix':DEFAULT_PREFIX, **{f['key']:deepcopy(f['default']) for f in FAMILIES[family]['fields']}}

def ui_field_label(field):
    return UI_FIELD_TEXT.get(field['key'], (field['label'], field.get('note', '')))[0]

def ui_field_note(field):
    return UI_FIELD_TEXT.get(field['key'], (field['label'], field.get('note', '')))[1]

def ui_choice_label(field_key, value):
    return UI_CHOICE_TEXT.get(field_key, {}).get(value, value)

def ui_choice_value(field_key, label):
    labels = UI_CHOICE_TEXT.get(field_key, {})
    return next((value for value, text in labels.items() if text == label), label)

def need(condition, message):
    if not condition:
        raise InputError(message)

def numeric(v, label):
    if isinstance(v, bool):
        raise InputError(label + ': Boolean values are not allowed.')
    try:
        value = float(v)
    except (ValueError, TypeError):
        raise InputError(label + ': enter a number.')
    need(math.isfinite(value), label + ': enter a finite number.')
    return value

def bc_thickness(a):
    # Preserve source intervals. Do not silently bridge gaps or pick a count at 2000.
    rows = [r for r in CAT['rect_bc_rows'] if a >= r['minimum'] and a <= r.get('maximum', math.inf)]
    need(bool(rows),
            "No automatic B/C thickness is available for largest clear duct side %g mm. Select 'Choose manually'." % a)
    vals = {r['value_mm'] for r in rows}
    need(len(vals) == 1, 'The table rows conflict on sheet thickness.')
    options = rows[0]['options'] if len(rows) == 1 else None
    return next(iter(vals)), options

def automatic_rectangular_size(parameters):
    dimension_keys = ('a_mm', 'b_mm', 'c_mm', 'd_mm', 'branch_a_mm')
    return max(parameters[key] for key in dimension_keys if key in parameters)

def resolve(raw):
    need(isinstance(raw, dict), 'Parameters must be a JSON object.')
    family = raw.get('family')
    need(family in FAMILIES, 'Unknown family: ' + str(family))
    spec = FAMILIES[family]
    need(spec['status'] == 'IMPLEMENTED', str(family) + ' is registered as source data only and is not implemented.')
    p = defaults(family)
    unknown = set(raw) - set(p)
    need(not unknown, 'Unknown parameters: ' + ', '.join(sorted(unknown)))
    p.update(raw)
    need(isinstance(p['prefix'], str), 'Group prefix: enter text.')
    p['prefix'] = p['prefix'].strip()
    need(bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,31}', p['prefix'])),
            'Group prefix: use 1-32 letters, digits, _ or -; start with a letter or digit.')
    need(p['prefix'].upper() != 'AIRKAN', 'AIRKAN cannot be used as the group prefix.')
    for field in spec['fields']:
        key = field['key']; val = p[key]
        if field['kind'] == 'choice':
            need(val in field['choices'], field['key'] + ': invalid selection.')
        elif field['kind'] in ('text', 'file'):
            need(isinstance(val, str) and bool(val.strip()), field['key'] + ': enter text.')
            val = val.strip(); p[key] = val
            if field['kind'] == 'file':
                need(Path(val).suffix.lower() in ('.step', '.stp'), field['key'] + ': choose a .step or .stp file.')
        else:
            val = numeric(val, field['key']); p[key] = val
            need(field['minimum'] <= val <= field['maximum'],
                 '%s: expected %g through %g %s (0 may mean "not specified yet").' %
                 (field['key'], field['minimum'], field['maximum'], field['unit']))
    warnings = []
    derived = {}
    if 'frames' in p:
        derived['profile'] = profile_for(p['a_mm'], p['b_mm']) if p['frames'] == 'PROJECT_AUTO' else 'GEEN'
        if p.get('insertion_mode') == 'BOM_REFERENTIE':
            need(p.get('insertion_mm', 0) == 0, 'BOM_REFERENTIE requires insertion_mm=0; otherwise select HANDMATIGE_INSTEEK.')
            warnings.append('The sheet stops at the profile entry: final axial and radial engagement have not been confirmed. This is not a fully inserted fabrication model.')
        else:
            need(p['frames'] != 'GEEN' or p.get('insertion_mm',0) == 0, 'Frame insertion is not allowed without a frame.')
            need(p.get('insertion_mm',0) < profile_depth(derived['profile']) or derived['profile']=='GEEN', 'Insertion must remain smaller than the profile depth.')
            warnings.append('Manual frame insertion depth; fit is not certified. Material overlap blocks the build.')
    if 't_mm' in p:
        mode = p.get('thickness_mode', 'HANDMATIG')
        if mode == 'AIRKAN_BC':
            need(p['material'] == 'GALVA' and p['airtightness_class'] in ('B','C'), 'This B/C source table is defined only for GALVA class B/C.')
            selection_size = automatic_rectangular_size(p)
            t, options = bc_thickness(selection_size)
            p['airkan_a_mm'] = 0.0
            p['t_mm'] = t
            derived['t_mm'] = t
            derived['automatic_thickness_basis_mm'] = selection_size
            derived['catalogue_construction_options'] = options
            if options is None:
                warnings.append('A=2000: thickness is unambiguously 1.2; source ranges overlap for reinforcements/profiles. No automatic quantities.')
        elif mode == 'S_STANDAARD':
            need(p['material'] == 'GALVA', 'The S thickness table in this source applies to GALVA; select manually for other materials.')
            key = n(p['diameter_mm'])
            need(key in CAT['s_standard_thickness'], 'Diameter is not in the S source table; select a manual sheet thickness for custom work.')
            derived['t_mm'] = CAT['s_standard_thickness'][key]
        else:
            need(p['t_mm'] > 0, 'Sheet thickness is not specified: enter t > 0. Profile thickness is not duct-sheet thickness.')
            derived['t_mm'] = p['t_mm']
        priced_thicknesses = rectangular_priced_thicknesses(family, p.get('material'))
        if priced_thicknesses:
            need(derived['t_mm'] in priced_thicknesses,
                 'Sheet thickness has no catalogue price for %s. Select %s mm.' %
                 (p['material'], ', '.join(('%g' % value).replace('.', ',') for value in priced_thicknesses)))
        if family == 'S':
            options = CAT['s_permitted_thickness'].get(n(p['diameter_mm']), [])
            if p['material'] != 'GALVA' or derived['t_mm'] not in options:
                warnings.append('The S diameter/material/thickness combination is custom, not a confirmed table combination.')
    if spec['detail'] == 'BOM_SIMPLIFIED':
        warnings.append('Simplified BOM model: one Body. Do not use its volume for weight, pressure loss or fabrication.')
    if family == 'REG':
        need(200 <= p['a_mm'] <= 1200 and 200 <= p['b_mm'] <= 1200, 'REG source range: both clear dimensions must be 200-1200 mm; other sizes are on request.')
        if p['a_mm'] % 100 or p['b_mm'] % 100:
            warnings.append('The REG intermediate size is not listed as a stock size in the price table; confirm availability.')
        warnings.append('Blades, output shaft, hand lever and actuator are omitted; their external clearance is not included.')
    if family in ('BU','BEND_RECT','REDUCER_RECT','VER','RECT_ROUND','TEE_RECT','TAKEOFF_RECT'):
        need(min(p['a_mm'],p['b_mm']) >= 150, 'Rectangular duct: minimum side is 150 mm.')
    if family == 'BEND_RECT':
        need(p['radius_mm'] > derived['t_mm'], 'Inside radius must be greater than sheet thickness.')
        derived['angle_deg'] = p['angle_deg'] * (1 if p['turn'] == 'RECHTS' else -1)
        derived['radius_basis'] = 'FREE_AIR_INNER_WALL; explicit project interpretation'
        warnings.append('Bend: A is in the XZ bend plane and B is perpendicular; 50 mm sections start at the profile entry. The axis is in the tangent plane, not at two unconfirmed global offsets.')
    if family == 'BEND_ROUND':
        d = p['diameter_mm']; r = p['radius_mm']
        if not r:
            if 100 <= d <= 630: r=d
            elif 710 <= d <= 1500: r=.75*d
            else: raise InputError('There is no explicit radius rule for this diameter; enter the centreline radius manually.')
        need(r > d/2 + derived['t_mm'], 'Centreline radius is too small for the outside wall.')
        need(p['segments'] == int(p['segments']), 'The number of segments must be an integer.')
        derived.update(radius_mm=r, angle_deg=CAT['round_bend_angles'][p['variant']])
        warnings.append('Segment count and extra straight ends are project choices. Connection fit and rubber grooves are not modelled.')
    if family == 'REDUCER_RECT':
        a,b,c,d = (p[k] for k in ('a_mm','b_mm','c_mm','d_mm'))
        need(min(c,d)>=150, 'Transition outlet: minimum side is 150 mm.')
        v=p['variant']; e=p['e_mm']; f=p['f_mm']
        if v in ('R','R1','R2'): e=0
        if v in ('R1','RC1'): f=b-d
        if v in ('R2','RC2'): f=0
        derived.update(e_mm=e,f_mm=f)
        if e != p['e_mm'] or f != p['f_mm']:
            warnings.append('Variant conditions applied: effective E=%g, F=%g mm; these values are recorded in the output parameters.'%(e,f))
    if family == 'RECT_ROUND':
        x,y=p['offset_x_mm'],p['offset_y_mm']; v=p['variant']
        need(v != 'VR' or (x==0 and y==0), 'VR is symmetrical: both offsets must be 0.')
        need(v != 'VRA' or ((x==0) != (y==0)), 'VRA: exactly one offset axis must be non-zero.')
        need(v != 'VRAA' or (x!=0 and y!=0), 'VRAA: both offset axes must be non-zero.')
        warnings.append('Smooth loft; section offset rather than normal sheet thickness on sloped surfaces. No flat pattern.')
    if family == 'FLANGE_ROUND':
        row = deepcopy(CAT['flanges'].get(n(p['diameter_mm'])))
        need(row is not None, 'No F flange row is available for this diameter.')
        if p['pitch_override_mm']: row['pitch_mm']=p['pitch_override_mm']; warnings.append('The pitch circle is an explicit project correction, not the original source value.')
        bore,od,k,w = row['bore_mm'],row['bore_mm']+2*row['strip_width_mm'],row['pitch_mm'],row['slot_width_mm']
        need(bore < k-w and k+w < od, 'The pitch circle does not fit within the flange ring. For diameter 250 the source states 586 mm; a confirmed correction is required.')
        derived['flange']=row
    if family in ('FLEX_ROUND','CONNECTOR_ROUND'):
        if family == 'FLEX_ROUND': need(p['outer_diameter_mm']>p['diameter_mm'], 'The outer casing must be larger than the clear nominal diameter.')
        else: need(p['actual_od_mm']>p['actual_id_mm'], 'Actual OD must be greater than actual ID.')
    if family == 'COVER_ROUND':
        need(p['actual_od_mm'] > 2*p['visual_wall_mm'], 'Outside dimension is too small for the visual wall.')
        if p['variant']=='DFP':
            need(0<p['drain_id_mm']<p['drain_od_mm']<p['actual_od_mm'] and p['drain_length_mm']>0, 'DFP: confirmed drain ID, OD and projection are required.')
    if family == 'INSPECTION':
        a,b=p['outer_a_mm'],p['outer_b_mm']; v=p['variant']
        if v=='ISR' and not a and not b:
            sizes=CAT['isr'].get(n(p['size_a_mm'])+'x'+n(p['size_b_mm']))
            need(sizes is not None, 'ISR order size is not in the source; enter confirmed outside dimensions.')
            a,b=sizes
        need(a>0 and (b>0 or v=='IS235'), 'Inspection-hatch outside dimensions are missing.')
        derived.update(outer_a_mm=a,outer_b_mm=(a if v=='IS235' else b))
    if family == 'SL_RECT':
        prof=profile_for(p['a_mm'],p['b_mm']); dep=profile_depth(prof)
        need(p['length_mm'] > 2*dep, 'Installation length is too small for two simplified frame depths.')
        derived['profile']=prof
    if family == 'HOOD':
        need(p['outer_diameter_mm']>=p['diameter_mm'], 'The hood casing cannot be smaller than the connection.')
        warnings.append('Conservative CLOSED hood envelope; external clearance only, not an airflow model.')
    if family == 'ROOF':
        need(min(p['base_x_mm'],p['base_y_mm'])>p['actual_bore_mm'], 'Base dimensions must be larger than the actual passage opening.')
        derived['roof_angle_deg'] = {'DD':0,'DD15':15,'DD30':30,'DD45':45,'DD60':60,'SO':0}[p['variant']]
        warnings.append('The roof piece is a hollow clearance envelope; roof angle is a mounting reference only. This is not a sheet-metal or waterproofing model.')
    if family == 'GRILLE_FIRE':
        need(p['h_mm'].is_integer() and p['b_mm'].is_integer(), 'Grille size must occur exactly in the catalogue table; interpolation is not allowed.')
        h = int(p['h_mm']); b = int(p['b_mm']); table = CAT['fire_grille_prices_eur_each'][p['variant']]
        need(h in table['h_mm'] and str(b) in table['rows_by_b_mm'], '%s H%s B%s is not in the catalogue table.' % (p['variant'], n(h), n(b)))
        price = table['rows_by_b_mm'][str(b)][table['h_mm'].index(h)]
        need(price is not None, '%s H%s B%s is not available in the catalogue table.' % (p['variant'], n(h), n(b)))
        derived.update(geometry_basis='PURCHASED_COORDINATION_ENVELOPE', depth_mm=p['depth_mm'], unit_price_eur=price)
        warnings.append('Purchased fire grille: solid wall only; not for mechanical ventilation, outdoor installation or water contact. Coordination depth is project input.')
    if family == 'CM':
        derived.update(geometry_basis='USER_SUPPLIED_STEP', pricing_method='STEP_ALL_FACES_DIVIDED_BY_TWO', area_rate_eur_per_m2=p['area_rate_eur_per_m2'])
        warnings.append('CM pricing is a preliminary comparison using all STEP faces divided by two; it is not an item price or quotation.')
    if family == 'BUY':
        need(p['airflow_role'] != 'KIES', 'BUY: select Intake or Exhaust.')
        need(p['price_status'] != 'KIES', 'BUY: select On request or Confirmed.')
        need(p['price_status'] != 'ON_REQUEST' or p['unit_price_eur'] == 0, 'BUY ON_REQUEST requires a unit price of 0.')
        need(p['price_status'] != 'BEVESTIGD' or p['unit_price_eur'] > 0, 'BUY BEVESTIGD requires a positive unit price.')
        derived.update(geometry_basis='USER_SUPPLIED_STEP', connection_a_mm=p['a_mm'], connection_b_mm=p['b_mm'])
        warnings.append('External purchased component: STEP and connection dimensions are user input; geometry is not interpreted as an Airkan item.')
    if family == 'AP_APA_PSA':
        variant = p['variant']
        d1, d2 = p['d1_mm'], p['d2_mm']
        need(d1 > d2, 'D1 must be greater than D2.')
        maximum_offset = d2 / 2 if variant == 'PSA' else (d1 - d2) / 2
        if variant == 'AP':
            need(p['position'] == 'S', 'AP is the symmetric construction; use APA for an offset branch.')
            asymmetry_mm, position = 0.0, 'S'
        elif p['position'] == 'S':
            asymmetry_mm, position = 0.0, 'S'
        elif p['position'] == 'A':
            need(maximum_offset > 0, 'A requires the host diameter to be larger than the branch diameter.')
            asymmetry_mm, position = maximum_offset, 'A'
        else:
            need(0 <= p['offset_mm'] < maximum_offset, 'P offset must be non-negative and less than the right-tangent offset (%g mm).' % maximum_offset)
            asymmetry_mm, position = p['offset_mm'], 'P'
        derived.update(asymmetry_mm=asymmetry_mm, asymmetry_mode=position, maximum_asymmetry_mm=maximum_offset,
                       geometry_basis=('PSA_DEVELOPED_SADDLE' if variant == 'PSA' else 'APA_CONICAL_SADDLE'),
                       wall_thickness_mm=1.0)
        warnings.append('D1 is a Boolean host cutter and is not exported. Listed nominal D1/D2 combinations use the exact Airkan AP/APA/PSA price matrix; all other combinations remain on request.')
    if family == 'PR_PRA':
        d1, b, l = p['d1_mm'], p['b_mm'], p['l_mm']
        need(d1 > b, 'The review-approved PR/PRA scope requires B to be smaller than D1.')
        need(b > 2 and l > 2, 'B and L must each exceed 2 mm to create the hollow branch.')
        maximum_offset = (d1 - b) / 2
        if p['position'] == 'S':
            asymmetry_mm, position = 0.0, 'S'
        elif p['position'] == 'A':
            need(maximum_offset > 0, 'A requires D1 to be greater than B.')
            asymmetry_mm, position = maximum_offset, 'A'
        else:
            need(0 <= p['offset_mm'] < maximum_offset, 'P offset must be non-negative and less than the right-tangent offset (%g mm).' % maximum_offset)
            asymmetry_mm, position = p['offset_mm'], 'P'
        catalogue_variant = {'S': 'PR', 'A': 'PRA'}.get(position)
        price_frame_option = {'NO_FRAME': 'NO_FRAME', 'E20': 'E20_OR_E30', 'E30': 'E20_OR_E30', 'A40': 'A40'}[p['frame_profile']]
        if p['frame_profile'] != 'NO_FRAME':
            try:
                frame_api()['frame_config'](
                    profile=p['frame_profile'],
                    length=b,
                    width=l,
                )
            except ValueError as error:
                raise InputError('PR/PRA frame dimensions are invalid: ' + str(error)) from error
        derived.update(asymmetry_mm=asymmetry_mm, asymmetry_mode=position, maximum_asymmetry_mm=maximum_offset,
                       geometry_basis='RECTANGULAR_BRANCH_ON_ROUND_HOST', wall_thickness_mm=1.0,
                       branch_projection_above_host_crown_mm=100.0, catalogue_variant=catalogue_variant,
                       price_frame_option=price_frame_option)
        warnings.append('D1 is a Boolean host cutter and is not exported. Exact matrix pricing applies to S/PR and A/PRA; intermediate P remains on request.')
    if family == 'TEE_SPECIAL':
        need(p['length_mm'] > 2, 'Special-tee L is too short for the main-port frames.')
        if p['variant'] == 'TALPHA':
            talpha = derive_talpha_source_dimensions(
                p['a_mm'], p['c_mm'], p['d_mm'], p['length_mm'], p['g_mm'], p['alpha_deg'], p['frame_profile']
            )
            if p['e_mm'] > 0:
                need(abs(p['e_mm'] - talpha['e_mm']) <= 1.0, 'TALPHA E must satisfy the source L/G/C/alpha closure; use %g mm or zero to derive it.' % talpha['e_mm'])
                e_mm = p['e_mm']
            else:
                e_mm = talpha['e_mm']
            f_mm = p['f_mm'] if p['f_mm'] > 0 else talpha['f_mm'] + 1e-6
            k2_vertical_clearance_mm = (f_mm - talpha['alignment_length_mm']) * math.sin(math.radians(p['alpha_deg']))
            need(k2_vertical_clearance_mm >= 100.0, 'TALPHA F must be at least %g mm to keep K2 at least 100 mm above G.' % talpha['f_mm'])
            derived.update({
                **talpha,
                'geometry_basis': 'TALPHA_SOURCE_PROFILE',
                'wall_thickness_mm': 1.0,
                'k2_minimum_vertical_clearance_mm': 100.0,
                'e_mm': e_mm,
                'f_mm': f_mm,
                'e_source_derived': p['e_mm'] == 0,
                'f_source_derived': p['f_mm'] == 0,
                'k2_vertical_clearance_mm': k2_vertical_clearance_mm,
            })
            warnings.append('Talpha is the approved special-tee geometry. Catalogue page 157 has no special-tee price rule; price is on request.')
        else:
            try:
                frame_depth_mm = frame_api()['frame_config'](
                    profile=p['frame_profile'],
                    length=p['b_mm'],
                    width=max(p['a_mm'], p['c_mm'], p['d_mm']),
                )['profile_depth']
            except ValueError as error:
                raise InputError('TASYMM frame dimensions are invalid: ' + str(error)) from error
            need(p['branch_length_mm'] > frame_depth_mm,
                 'TASYMM K2 length must exceed the selected frame entry depth.')
            derived.update(
                geometry_basis='TASYMM_SOURCE_PROFILE',
                wall_thickness_mm=1.0,
                branch_length_mm=p['branch_length_mm'],
            )
            warnings.append('TASYMM is the approved special-tee geometry. Catalogue page 157 has no special-tee price rule; price is on request.')
    if family == 'FRAME': derived['profile']=profile_for(p['a_mm'],p['b_mm'])
    if family == 'TEE_RECT': warnings.append('Limited project tee; no automatic Airkan Talpha or unequal side sections.')
    code = {'FRAME':derived.get('profile','FRAME'),'BEND_RECT':'B90' if p.get('angle_deg')==90 else 'Balpha','REDUCER_RECT':p.get('variant'),'RECT_ROUND':p.get('variant'),'BEND_ROUND':p.get('variant'),'REG':p.get('variant'),'SL_RECT':'SL.'+derived.get('profile',''), 'FLEX_ROUND':p.get('variant'),'CONNECTOR_ROUND':p.get('variant'),'FLANGE_ROUND':'F','COVER_ROUND':p.get('variant'),'INSPECTION':p.get('variant'),'SUPPORT_PL':p.get('variant'),'HOOD':p.get('variant'),'ROOF':p.get('variant'),'TAKEOFF_RECT':p.get('variant'),'TEE_RECT':'T_PROJECT','GRILLE_FIRE':p.get('variant')}.get(family, family)
    tags=[]
    if family=='REG': tags += ['H'+n(p['b_mm']),'B'+n(p['a_mm'])]
    elif 'a_mm' in p: tags += [n(p['a_mm'])+'x'+n(p['b_mm'])]
    if family=='REDUCER_RECT': tags += ['TO',n(p['c_mm'])+'x'+n(p['d_mm']),'E'+n(derived['e_mm']),'F'+n(derived['f_mm'])]
    if family=='VER':tags += ['DX'+n(p['offset_x_mm']),'DY'+n(p['offset_y_mm'])]
    if family=='TEE_RECT':tags += ['BR'+n(p['branch_a_mm'])+'x'+n(p['b_mm']),'Z'+n(p['branch_z_mm'])]
    if family=='AP_APA_PSA':tags += [p['variant'],'D1'+n(p['d1_mm']),'D2'+n(p['d2_mm']),derived['asymmetry_mode']]
    if family=='PR_PRA':tags += ['D1'+n(p['d1_mm']),'B'+n(p['b_mm'])+'x'+n(p['l_mm']),derived['asymmetry_mode']]
    if family=='TEE_SPECIAL':
        tags += [p['variant'],'A'+n(p['a_mm']),'B'+n(p['b_mm']),'C'+n(p['c_mm']),'D'+n(p['d_mm']),'L'+n(p['length_mm'])]
        tags += (['ALPHA'+n(p['alpha_deg'])] if p['variant']=='TALPHA' else ['K2'+n(p['branch_length_mm'])])
    if 'diameter_mm' in p: tags += ['D'+n(p['diameter_mm'])]
    if 'length_mm' in p: tags += ['L'+n(p['length_mm'])]
    if family=='BEND_RECT': tags += ['ANG'+n(p['angle_deg']),'R'+n(p['radius_mm']),'S'+n(p['straight_in_mm'])+'-'+n(p['straight_out_mm']),p['turn']]
    if family=='BEND_ROUND': tags += ['R'+n(derived['radius_mm']),'SEG'+n(p['segments'])]
    if family=='INSPECTION':tags += [n(p['size_a_mm'])+'x'+n(p['size_b_mm']),'OUT'+n(derived['outer_a_mm'])+'x'+n(derived['outer_b_mm'])]
    if family=='ROOF':tags += ['BASE'+n(p['base_x_mm'])+'x'+n(p['base_y_mm'])]
    if family=='GRILLE_FIRE':tags += ['H'+n(p['h_mm']),'B'+n(p['b_mm']),'Z'+n(p['depth_mm'])]
    if family=='BUY':tags += [p['article_code'],n(p['a_mm'])+'x'+n(p['b_mm'])]
    if family in ('HOOD','FLEX_ROUND'):tags += ['OD'+n(p['outer_diameter_mm'])]
    if 'profile' in derived and derived['profile']!='GEEN':tags += [derived['profile']]
    if 't_mm' in derived:tags += ['t'+n(derived['t_mm'])]
    payload=json.dumps({'version':VERSION,'rules_sha256':RULESET_SHA256,'params':p},sort_keys=True,ensure_ascii=True,separators=(',',':'))
    digest=hashlib.sha256(payload.encode()).hexdigest()[:10]
    stem=p['prefix']+'_'+str(code).replace('.','-')+'_'+'_'.join(tags)+'_'+digest
    stem=re.sub(r'_+','_',re.sub(r'[^A-Za-z0-9_\-]','_',stem))
    order={'catalogue_family_code':('Bα' if family=='BEND_RECT' and p['angle_deg']!=90 else code),'parameters':p.copy(),'effective_geometry':derived.copy(),'status':spec['naming_status']}
    if family=='S':order['catalogue_label']='S - %g'%p['diameter_mm'];order['length_mm']=p['length_mm']
    elif family=='REG':order['catalogue_label']='%s %g - %g'%(p['variant'],p['b_mm'],p['a_mm'])
    elif family=='GRILLE_FIRE':
        order.update(catalogue_label='%s - %g - %g'%(p['variant'],p['h_mm'],p['b_mm']),unit_price_eur=derived['unit_price_eur'],currency='EUR',pricing_status='CATALOGUE_PRICE',price_basis='AIRKAN_CATALOGUE_EUR_EACH',price_source_id='fire_grille')
    elif family=='CM':
        order.update(catalogue_label='CM - '+p['description'],pricing_status='PENDING_STEP_MEASUREMENT',price_basis='STEP_ALL_FACES_DIVIDED_BY_TWO_X_RATE',currency='EUR')
    elif family=='BUY':
        order.update(catalogue_label='BUY - %s - %s - %s'%(p['supplier'],p['article_code'],p['description']),supplier=p['supplier'],article_code=p['article_code'])
    elif family=='AP_APA_PSA':
        order.update(catalogue_label='%s - D1 %g - D2 %g - %s' % (p['variant'], p['d1_mm'], p['d2_mm'], derived['asymmetry_mode']))
    elif family=='PR_PRA':
        order.update(catalogue_label='PR/PRA - D1 %g - B %gx%g - %s' % (p['d1_mm'], p['b_mm'], p['l_mm'], derived['asymmetry_mode']))
    elif family=='TEE_SPECIAL':
        if p['variant'] == 'TALPHA':
            order.update(catalogue_label='Talpha - %gx%g / %gx%g - alpha %g' % (p['a_mm'], p['b_mm'], p['d_mm'], p['b_mm'], p['alpha_deg']))
        else:
            order.update(catalogue_label='TASYMM - %gx%g / %gx%g - K2 %g' % (p['a_mm'], p['b_mm'], p['d_mm'], p['b_mm'], p['branch_length_mm']))
    elif family=='FLANGE_ROUND':order['catalogue_label']='F - %g'%p['diameter_mm']
    else:order['catalogue_label']=str(order['catalogue_family_code'])
    order.update(price_for_parameters(p, derived))
    return {'rules_sha256':RULESET_SHA256,'params':p,'derived':derived,'family_spec':spec,'warnings':warnings,'filename_stem':stem,'order':order}
