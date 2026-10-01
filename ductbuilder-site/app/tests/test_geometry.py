"""Real OCC geometry + STEP roundtrips. Developer test: CadQuery is required.
Not needed in FreeCAD. Run: python tests/test_geometry.py --out <test-folder>.
"""
import argparse
import json
import platform
import sys
import time
import traceback
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from airkan_builder.rules import defaults,InputError,VERSION,FAMILIES
from airkan_builder.geometry import build_geometry,serializable
from airkan_builder.kernel import Kernel,dot,ry

BASE_OVERRIDES={
 'FRAME':{},'BU':{'t_mm':.95},'BEND_RECT':{'t_mm':.95},'REDUCER_RECT':{'t_mm':.95},'VER':{'t_mm':.95},
 'RECT_ROUND':{'t_mm':.95,'straight_out_mm':50},'TEE_RECT':{'t_mm':.95},'TAKEOFF_RECT':{'t_mm':.95},'S':{},
 'BEND_ROUND':{'t_mm':.95},'REG':{},'SL_RECT':{},'FLEX_ROUND':{'length_mm':110,'outer_diameter_mm':906},
 'CONNECTOR_ROUND':{'length_mm':200,'actual_id_mm':897,'actual_od_mm':899},
 'FLANGE_ROUND':{},'COVER_ROUND':{'length_mm':50,'actual_od_mm':904},'INSPECTION':{},'SUPPORT_PL':{},
 'HOOD':{'outer_diameter_mm':1400,'length_mm':650},'ROOF':{'base_x_mm':1250,'base_y_mm':1250,'length_mm':500,'actual_bore_mm':906},
 'GRILLE_FIRE':{}}

def cases():
    rows=[]
    def add(name,family,overrides=None,step=False,error=None):
        rows.append(dict(name=name,parameters={**defaults(family),**BASE_OVERRIDES[family],**(overrides or {})},step=step,expected_error=error))
    for f in BASE_OVERRIDES:add('base_'+f,f,step=f in ('FRAME','BU','BEND_RECT','RECT_ROUND','TEE_RECT','BEND_ROUND','REG','FLANGE_ROUND'))
    for angle in (15,37.5,90,125):
        for turn in ('LINKS','RECHTS'):add('bend_%s_%s'%(angle,turn),'BEND_RECT',dict(angle_deg=angle,turn=turn),step=angle in (37.5,125))
    add('bend_A40','BEND_RECT',dict(a_mm=1300),True)
    add('frame_threshold_E30','FRAME',dict(a_mm=1250),True)
    add('frame_threshold_A_A40','FRAME',dict(a_mm=1250.001),True)
    add('frame_threshold_B_A40','FRAME',dict(b_mm=1250.001),True)
    add('mixed_end_profiles','REDUCER_RECT',dict(c_mm=1300),True)
    add('bu_entry_length','BU',dict(length_basis='PROFIELINVOER'),True)
    add('bu_without_frames','BU',dict(frames='GEEN'),True)
    for variant in ('R1','RC1','R','RC','R2','RC2'):add('reducer_'+variant,'REDUCER_RECT',dict(variant=variant))
    add('rect_round_VRA','RECT_ROUND',dict(variant='VRA',offset_x_mm=100),True)
    add('rect_round_VRAA','RECT_ROUND',dict(variant='VRAA',offset_x_mm=100,offset_y_mm=75),True)
    add('rect_round_no_stub','RECT_ROUND',dict(straight_out_mm=0),True)
    for variant in ('P.BI','P.45'):add('takeoff_'+variant,'TAKEOFF_RECT',dict(variant=variant),True)
    for variant,segments in [('B15X',2),('B3X',3),('BS4X',3),('B6X',4),('BS9X',5)]:add('round_'+variant,'BEND_ROUND',dict(variant=variant,segments=segments),True)
    add('round_d500','BEND_ROUND',dict(diameter_mm=500),True)
    for d in (80,150,1500):add('flange_'+str(d),'FLANGE_ROUND',dict(diameter_mm=d),True)
    add('flange_250_explicit_override','FLANGE_ROUND',dict(diameter_mm=250,pitch_override_mm=286),True)
    add('reg_200_1200','REG',dict(a_mm=200,b_mm=1200,variant='REGH'),True)
    add('sl_A40','SL_RECT',dict(a_mm=1300),True)
    for variant in ('DF','DG','DFG','DH'):add('cover_'+variant,'COVER_ROUND',dict(variant=variant),True)
    add('cover_DFP','COVER_ROUND',dict(variant='DFP',drain_id_mm=20,drain_od_mm=25,drain_length_mm=40),True)
    add('inspection_IS235','INSPECTION',dict(variant='IS235',outer_a_mm=235),True)
    add('inspection_ISK','INSPECTION',dict(variant='ISK',outer_a_mm=400,outer_b_mm=300),True)
    add('support_PL300','SUPPORT_PL',dict(variant='PL300'),True)
    add('roof_DD30','ROOF',dict(variant='DD30'),True)
    add('invalid_seated_plate','BU',dict(insertion_mode='HANDMATIGE_INSTEEK',insertion_mm=1),error='Materiaaloverlap')
    add('invalid_minimum_H40','FRAME',dict(a_mm=1300,b_mm=150),error='opposite inserts would overlap')
    add('invalid_length','BU',dict(length_mm=40),error='L is too short')
    add('invalid_round_radius','BEND_ROUND',dict(radius_mm=450),error='Centreline radius')
    add('invalid_flange_250','FLANGE_ROUND',dict(diameter_mm=250),error='pitch circle')
    add('invalid_T_shoulder','TEE_RECT',dict(length_mm=1000,branch_z_mm=500),error='Schouderradius')
    return rows


def check_result(r,k):
    p=r['parameters'];val=r['validation']
    assert val['clashes']==[]
    if r['detail']=='BOM_SIMPLIFIED':assert val['valid_solids']==1 and val['partdesign_body_count']==1
    assert r['bom']['quantity']==1 and r['bom']['count_children'] is False and r['bom']['mass_kg'] is None
    if p['family']=='REG':
        assert val['bounds_mm']==[-30.,-30.,0.,p['a_mm']+30,p['b_mm']+30,120.]
        assert r['geometry']['lamellae_modeled'] is False
    if p['family']=='BEND_RECT':
        geo=r['geometry'];out=r['join_datums'][-1]
        assert geo['tangent_axis_axial_offset_mm']==0
        assert geo['centerline_radius_mm']==p['radius_mm']+p['a_mm']/2
        signed=p['angle_deg']*(1 if p['turn']=='RECHTS' else -1)
        assert dot(out['z_axis'],ry((0,0,1),signed))>.999999
        assert dot(ry((0,0,1),r['frames'][0]['rotation_y_deg']),r['join_datums'][0]['z_axis'])<-.999999
        assert dot(ry((0,0,1),r['frames'][1]['rotation_y_deg']),out['z_axis'])<-.999999
    if p['family']=='BU':
        expected=p['length_mm'] if p['length_basis']=='FLENSVLAKKEN' else p['length_mm']+2*(27 if max(p['a_mm'],p['b_mm'])<=1250 else 36)
        assert abs(r['geometry']['flange_to_flange_mm']-expected)<1e-7
        sheet_area_m2=sum(k.area(part['shape']) for part in r['parts'] if part['single_body'])/2000000.0
        all_parts_area_m2=sum(k.area(part['shape']) for part in r['parts'])/2000000.0
        assert abs(r['order']['one_sided_price_area_m2']-sheet_area_m2)<1e-9
        surcharge_frames=sum(1 for frame in r['frames'] if max(frame['inside_mm'])<2000)
        assert r['order']['requested_nonstandard_frame_count']==surcharge_frames
        assert 'unit_price_eur' not in r['order']
        assert 'base_sheet_price_eur' not in r['order']
        if r['frames']:assert all_parts_area_m2>sheet_area_m2
    if p['family']=='BEND_ROUND':assert r['geometry']['swept_torus'] is False
    if p['family']=='GRILLE_FIRE':
        assert val['bounds_mm']==[0.,0.,0.,p['b_mm'],p['h_mm'],p['depth_mm']]
        assert r['order']['unit_price_eur']==47.40
    json.dumps(serializable(r),allow_nan=False)


def run(out,resume=False):
    import cadquery
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    report={'schema':'airkan-validation-v3','version':VERSION,'started_utc':datetime.now(timezone.utc).isoformat(),
            'runtime':{'python':platform.python_version(),'cadquery':cadquery.__version__,'backend':'CadQuery / OpenCascade'},
            'native_freecad_tested':False,'native_freecad_gui_tested':False,'native_fcstd_tested':False,'native_fusion_tested':False,
            'examples_are_test_parameters_not_fabrication_data':True,'cases':[]}
    previous={}
    if resume and (out/'validation_geometry.json').exists():
        previous={x['name']:x for x in json.loads((out/'validation_geometry.json').read_text())['cases'] if x['passed']}
    k=Kernel('cadquery')
    for case in cases():
        old=previous.get(case['name'])
        if old and old['parameters']==case['parameters']:
            report['cases'].append(old);print('RESUME PASS',case['name'],flush=True);continue
        print('START',case['name'],flush=True);start=time.monotonic()
        row={**case,'passed':False}
        try:
            try:r=build_geometry(case['parameters'],backend='cadquery')
            except Exception as exc:
                if case['expected_error'] and case['expected_error'] in str(exc):row.update(passed=True,rejection=str(exc));r=None
                else:raise
            if r is not None:
                assert not case['expected_error'],'Invalid input was not rejected'
                check_result(r,k);row['validation']=r['validation']
                if case['name']=='mixed_end_profiles':assert [f['profile'] for f in r['frames']]==['E30','A40']
                if case['step']:
                    path=out/(case['name']+'.step');k.export_shape(r['shape'],path);read=k.read_shape(path)
                    assert k.valid(read) and len(k.solids(read))==r['validation']['valid_solids']
                    dx=max(abs(a-b) for a,b in zip(k.bounds(read),r['validation']['bounds_mm']))
                    dv=abs(k.volume(read)-r['validation']['total_shape_volume_mm3'])
                    assert dx<.001,(case['name'],'STEP bbox',dx)
                    assert dv<max(.01,r['validation']['total_shape_volume_mm3']*1e-5),(case['name'],'STEP volume',dv)
                    row['step_reread']={'passed':True,'bounds_max_delta_mm':dx,'volume_delta_mm3':dv,'solid_count':len(k.solids(read))}
                row['passed']=True
        except Exception as exc:row.update(error=str(exc),traceback=traceback.format_exc())
        row['seconds']=round(time.monotonic()-start,3);report['cases'].append(row)
        print('PASS' if row['passed'] else 'FAIL',case['name'],row['seconds'],row.get('error',''),flush=True)
        (out/'validation_geometry.json').write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    report['summary']={'total_cases':len(report['cases']),'passed':sum(r['passed'] for r in report['cases']),
        'step_roundtrips_passed':sum(r.get('step_reread',{}).get('passed',False) for r in report['cases']),
        'negative_cases_passed':sum(r['passed'] and bool(r.get('expected_error')) for r in report['cases']),
        'implemented_groups':len(BASE_OVERRIDES),'source_only_groups':sum(f['status']!='IMPLEMENTED' for f in FAMILIES.values())}
    report['completed_utc']=datetime.now(timezone.utc).isoformat()
    (out/'validation_geometry.json').write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    print(report['summary'],flush=True);return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',required=True);parser.add_argument('--resume',action='store_true');args=parser.parse_args()
    report=run(args.out,args.resume)
    sys.exit(0 if report['summary']['total_cases']==report['summary']['passed'] else 1)
