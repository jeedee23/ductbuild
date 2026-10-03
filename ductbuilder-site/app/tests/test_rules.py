"""Run with ordinary Python: python -m unittest discover -s tests -p test_rules.py."""
import json
import math
from pathlib import Path
import re
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import airkan_builder.document as document
from airkan_builder.rules import CAT,FAMILIES,InputError,bc_thickness,defaults,profile_for,resolve
from airkan_builder.document import _reserve,parameters_from_document,bom_from_document


def params(family,**kw):
    return dict(defaults(family),**kw)

class RulesTests(unittest.TestCase):
    def test_profile_threshold(self):
        for a,b,expected in [(1000,800,'E30'),(1250,1250,'E30'),(1250.001,800,'A40'),(800,1250.001,'A40')]:
            with self.subTest(a=a,b=b):self.assertEqual(profile_for(a,b),expected)
    def test_table_values(self):
        for a,t in [(200,.75),(500,.75),(501,.95),(1250,.95),(1251,.95),(1500,.95),(1501,1.2),(1999,1.2),(2000,1.2),(2200,1.2)]:
            with self.subTest(a=a):self.assertEqual(bc_thickness(a)[0],t)
    def test_source_gaps_not_invented(self):
        for a in [150,199,500.5,1250.5,1500.5]:
            with self.subTest(a=a),self.assertRaises(InputError):bc_thickness(a)
    def test_2000_count_ambiguity(self):self.assertIsNone(bc_thickness(2000)[1])
    def test_auto_thickness_uses_largest_rectangular_side(self):
        r=resolve(params('BU',a_mm=1640,b_mm=1020,thickness_mode='AIRKAN_BC',airkan_a_mm=500))
        self.assertEqual(r['derived']['profile'],'A40')
        self.assertEqual(r['derived']['automatic_thickness_basis_mm'],1640)
        self.assertEqual(r['derived']['t_mm'],1.2)
        self.assertEqual(r['params']['airkan_a_mm'],0)
        self.assertEqual(r['params']['t_mm'],1.2)
        reducer=resolve(params('REDUCER_RECT',a_mm=1000,b_mm=800,c_mm=1800,d_mm=700,thickness_mode='AIRKAN_BC'))
        self.assertEqual(reducer['derived']['automatic_thickness_basis_mm'],1800)
        self.assertEqual(reducer['derived']['t_mm'],1.2)
    def test_material_restriction(self):
        with self.assertRaises(InputError):resolve(params('BU',thickness_mode='AIRKAN_BC',airkan_a_mm=1000,material='INOX304'))
    def test_manual_thickness_required(self):
        with self.assertRaises(InputError):resolve(defaults('BU'))
    def test_rectangular_thickness_requires_a_priced_material_cell(self):
        self.assertEqual(resolve(params('BU',material='GALVA',t_mm=1.5))['derived']['t_mm'],1.5)
        self.assertEqual(resolve(params('BU',material='ALMG3',t_mm=1.2))['derived']['t_mm'],1.2)
        self.assertEqual(resolve(params('BU',material='INOX304',t_mm=.95))['derived']['t_mm'],.95)
        with self.assertRaisesRegex(InputError,'no catalogue price'):
            resolve(params('BU',material='ALMG3',t_mm=1.5))
        with self.assertRaisesRegex(InputError,'no catalogue price'):
            resolve(params('BU',material='INOX316',t_mm=1.2))
    def test_s_thickness_and_id(self):
        for diameter,t in [(100,.4),(500,.7),(800,.8),(900,1),(1250,1.2)]:
            with self.subTest(diameter=diameter):self.assertEqual(resolve(params('S',diameter_mm=diameter))['derived']['t_mm'],t)
    def test_old_segment_codes_not_used(self):
        self.assertEqual(set(CAT['round_bend_angles']),{'BS9X','B6X','BS4X','B3X','B15X'})
        with self.assertRaises(InputError):resolve(params('BEND_ROUND',variant='BS6X',t_mm=1))
    def test_round_radius(self):
        self.assertEqual(resolve(params('BEND_ROUND',diameter_mm=500,t_mm=1))['derived']['radius_mm'],500)
        self.assertEqual(resolve(params('BEND_ROUND',diameter_mm=900,t_mm=1))['derived']['radius_mm'],675)
        with self.assertRaises(InputError):resolve(params('BEND_ROUND',diameter_mm=80,t_mm=.6))
    def test_segment_integer(self):
        with self.assertRaises(InputError):resolve(params('BEND_ROUND',segments=3.5,t_mm=1))
    def test_bend_angle_limits(self):
        for th in [15,90,125]:resolve(params('BEND_RECT',t_mm=.95,angle_deg=th))
        for th in [14.99,125.01]:
            with self.subTest(th=th),self.assertRaises(InputError):resolve(params('BEND_RECT',t_mm=.95,angle_deg=th))
    def test_radius_sheet_limit(self):
        with self.assertRaises(InputError):resolve(params('BEND_RECT',t_mm=.95,radius_mm=.95))
    def test_reference_insertion(self):
        with self.assertRaises(InputError):resolve(params('BU',t_mm=.95,insertion_mm=1))
    def test_nonfinite_rejected(self):
        for v in [float('nan'),float('inf'),float('-inf'),True,'xxx']:
            with self.subTest(v=v),self.assertRaises(InputError):resolve(params('BU',t_mm=.95,a_mm=v))
    def test_unknown_family(self):
        with self.assertRaises(InputError):resolve({'family':'FAKE'})
    def test_unknown_parameter(self):
        with self.assertRaises(InputError):resolve(params('REG',execute='something'))
    def test_source_only_are_blocked(self):
        source_only=set()
        for family,spec in FAMILIES.items():
            if spec['status']!='IMPLEMENTED':
                source_only.add(family)
                with self.subTest(family=family),self.assertRaises(InputError):resolve(defaults(family))
        self.assertEqual(source_only,{'SUPPORT_AT','COMPOSITE'})
    def test_promoted_source_family_contracts(self):
        ap=resolve(params('AP_APA_PSA',variant='APA',position='A'))
        self.assertEqual(ap['derived']['asymmetry_mm'],75)
        self.assertEqual(ap['order']['pricing_status'],'CATALOGUE_PRICE')
        self.assertEqual(ap['order']['unit_price_eur'],46.96)
        psa=resolve(params('AP_APA_PSA',variant='PSA',position='A'))
        self.assertEqual(psa['derived']['asymmetry_mm'],75)
        pr=resolve(params('PR_PRA',position='P',offset_mm=10))
        self.assertEqual(pr['derived']['asymmetry_mm'],10)
        self.assertEqual(pr['order']['pricing_status'],'ON_REQUEST')
        centred_pr=resolve(params('PR_PRA'))
        self.assertEqual(centred_pr['derived']['catalogue_variant'],'PR')
        self.assertEqual(centred_pr['order']['unit_price_eur'],31.23)
        talpha=resolve(defaults('TEE_SPECIAL'))
        self.assertEqual(talpha['derived']['k2_minimum_vertical_clearance_mm'],100)
        self.assertTrue(talpha['derived']['e_source_derived'])
        self.assertTrue(talpha['derived']['f_source_derived'])
        self.assertGreaterEqual(talpha['derived']['k2_vertical_clearance_mm'],100)
        self.assertEqual(talpha['order']['pricing_status'],'ON_REQUEST')
        tasymm=resolve(params('TEE_SPECIAL',variant='TASYMM',a_mm=300,b_mm=200,c_mm=400,d_mm=200,length_mm=1000,branch_length_mm=300))
        self.assertEqual(tasymm['derived']['geometry_basis'],'TASYMM_SOURCE_PROFILE')
        self.assertEqual(tasymm['order']['catalogue_label'],'TASYMM - 300x200 / 200x200 - K2 300')
        with self.assertRaises(InputError):resolve(params('AP_APA_PSA',variant='AP',position='A'))
        with self.assertRaises(InputError):resolve(params('PR_PRA',position='P',offset_mm=50))
    def test_register_label_H_B(self):
        r=resolve(params('REG',a_mm=1000,b_mm=800,variant='REGH'))
        self.assertEqual(r['order']['catalogue_label'],'REGH 800 - 1000')
    def test_register_boundaries(self):
        resolve(params('REG',a_mm=200,b_mm=1200))
        for a in [199,1201]:
            with self.subTest(a=a),self.assertRaises(InputError):resolve(params('REG',a_mm=a))
    def test_grille_official_codes_and_prices(self):
        tables=CAT['fire_grille_prices_eur_each']
        self.assertEqual(sum(price is not None for table in tables.values() for row in table['rows_by_b_mm'].values() for price in row),266)
        cases=[
            ('GE60',100,100,47.40),
            ('GE60K',400,800,457.03),
            ('GE60XL',200,900,461.25),
        ]
        for variant,h,b,price in cases:
            with self.subTest(variant=variant,h=h,b=b):
                result=resolve(params('GRILLE_FIRE',variant=variant,h_mm=h,b_mm=b,depth_mm=50))
                self.assertEqual(result['order']['catalogue_family_code'],variant)
                self.assertEqual(result['order']['unit_price_eur'],price)
                self.assertEqual(result['order']['catalogue_label'],'%s - %g - %g'%(variant,h,b))
        with self.assertRaises(InputError):
            resolve(params('GRILLE_FIRE',variant='GE60XL',h_mm=200,b_mm=200,depth_mm=50))
    def test_custom_made_step_contract(self):
        result=resolve(params('CM',description='Plenum maatwerk',source_step='C:/models/plenum.step',material='GALVA',thickness_mm=1.2,area_rate_eur_per_m2=33.8))
        self.assertEqual(result['order']['catalogue_family_code'],'CM')
        self.assertEqual(result['derived']['pricing_method'],'STEP_ALL_FACES_DIVIDED_BY_TWO')
        self.assertEqual(result['derived']['area_rate_eur_per_m2'],33.8)
    def test_buy_contract_is_fully_user_supplied(self):
        with self.assertRaises(InputError):
            resolve(defaults('BUY'))
        supplied=dict(defaults('BUY'),supplier='Renson',article_code='411/900',description='Buitenrooster',
                      source_step='C:/models/buitenrooster.step',a_mm=900,b_mm=900,airflow_role='AANZUIG',
                      price_status='ON_REQUEST',unit_price_eur=0,price_source='Leverancierspagina 2026-09-24')
        result=resolve(supplied)
        self.assertEqual(result['order']['catalogue_family_code'],'BUY')
        self.assertEqual(result['order']['catalogue_label'],'BUY - Renson - 411/900 - Buitenrooster')
        self.assertEqual(result['order']['pricing_status'],'ON_REQUEST')
        self.assertNotIn('unit_price_eur',result['order'])
        confirmed=resolve(dict(supplied,price_status='BEVESTIGD',unit_price_eur=321.45,price_source='Offerte R-123'))
        self.assertEqual(confirmed['order']['unit_price_eur'],321.45)
        with self.assertRaises(InputError):
            resolve(dict(supplied,price_status='BEVESTIGD',unit_price_eur=0))
    def test_unsafe_flange_row_not_silently_fixed(self):
        with self.assertRaises(InputError):resolve(params('FLANGE_ROUND',diameter_mm=250))
        r=resolve(params('FLANGE_ROUND',diameter_mm=250,pitch_override_mm=286))
        self.assertEqual(r['derived']['flange']['pitch_mm'],286)
        self.assertTrue(any('project correction' in w for w in r['warnings']))
    def test_reducer_variant_constraints(self):
        for variant,e,f in [('R',0,100),('R1',0,200),('R2',0,0),('RC',100,100),('RC1',100,200),('RC2',100,0)]:
            with self.subTest(variant=variant):
                d=resolve(params('REDUCER_RECT',variant=variant,t_mm=.95))['derived'];self.assertEqual((d['e_mm'],d['f_mm']),(e,f))
    def test_round_transition_variants(self):
        for variant,x,y in [('VR',0,0),('VRA',100,0),('VRA',0,100),('VRAA',100,100)]:
            resolve(params('RECT_ROUND',t_mm=.95,variant=variant,offset_x_mm=x,offset_y_mm=y,straight_out_mm=50))
        for variant,x,y in [('VR',1,0),('VRA',0,0),('VRAA',1,0)]:
            with self.subTest(variant=variant),self.assertRaises(InputError):resolve(params('RECT_ROUND',t_mm=.95,variant=variant,offset_x_mm=x,offset_y_mm=y,straight_out_mm=50))
    def test_missing_catalogue_dimensions_block_build(self):
        for family in ['FLEX_ROUND','CONNECTOR_ROUND','COVER_ROUND','HOOD','ROOF']:
            p=params(family)
            if 't_mm' in p:p['t_mm']=1
            with self.subTest(family=family),self.assertRaises(InputError):resolve(p)
    def test_drain_dimensions_required(self):
        with self.assertRaises(InputError):resolve(params('COVER_ROUND',variant='DFP',actual_od_mm=904,length_mm=50))
    def test_deterministic_noncolliding_safe_name(self):
        p=params('BU',t_mm=.95);a=resolve(p)['filename_stem'];b=resolve(dict(reversed(list(p.items()))))['filename_stem']
        self.assertEqual(a,b);self.assertRegex(a,r'^[A-Za-z0-9_-]+$')
        for change in [{'t_mm':1.2},{'b_mm':800.001},{'length_basis':'PROFIELINVOER'}]:
            self.assertNotEqual(a,resolve(dict(p,**change))['filename_stem'])
    def test_group_prefix_distinguishes_duplicate_geometry(self):
        p=params('BU',t_mm=.95,prefix='G01')
        first=resolve(p)['filename_stem'];second=resolve(dict(p,prefix='G02'))['filename_stem']
        self.assertTrue(first.startswith('G01_BU_'));self.assertTrue(second.startswith('G02_BU_'))
        self.assertNotEqual(first,second)
    def test_group_prefix_validation(self):
        for prefix in ('','AIRKAN','groep 1','-G01','G/01','x'*33):
            with self.subTest(prefix=prefix),self.assertRaises(InputError):resolve(params('REG',prefix=prefix))
        self.assertEqual(resolve({'family':'REG'})['params']['prefix'],'GROEP-01')
    def test_all_families_have_traceable_sources(self):
        for family,spec in FAMILIES.items():
            for r in spec['sources']:
                src=CAT['sources'][r['source_id']]
                self.assertTrue(src['filename'].endswith('.pdf'))
                self.assertRegex(src['sha256'],r'^[a-f0-9]{64}$')
                self.assertGreaterEqual(r['pdf_page'],1)
    def test_file_reservation_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            a,la=_reserve(folder,'test');b,lb=_reserve(folder,'test')
            self.assertNotEqual(a,b);self.assertTrue(la.exists());self.assertTrue(lb.exists())
            Path(str(a)+'.step').write_text('original');la.unlink();lb.unlink()
            c,lc=_reserve(folder,'test');self.assertNotEqual(a,c);self.assertEqual(Path(str(a)+'.step').read_text(),'original');lc.unlink()
    def test_file_reservation_rejects_non_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            blocked=Path(folder)/'not-a-directory';blocked.write_text('original')
            with self.assertRaises((FileExistsError,NotADirectoryError)):_reserve(blocked,'test')
            self.assertEqual(blocked.read_text(),'original')
    def test_file_reservation_creates_missing_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'new'/'nested'
            stem,lock=_reserve(output,'test')
            self.assertEqual(stem,output/'test');self.assertTrue(lock.is_file())
            lock.unlink()
    def test_file_reservation_rejects_unwritable_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(document.os,'open',side_effect=PermissionError('access denied')):
                with self.assertRaisesRegex(InputError,'Uitvoermap is niet schrijfbaar'):_reserve(folder,'test')
            self.assertEqual(list(Path(folder).iterdir()),[])
    def test_export_failure_marks_partial_outputs(self):
        class Shape:
            Solids=[object()]
            Volume=10.0
            def isValid(self):return True
        class Kernel:
            def bounds(self,shape):return [0,0,0,1,1,1]
        class Root:
            def __init__(self):self.PropertiesList=[]
            def addProperty(self,kind,name,group):self.PropertiesList.append(name)
            def setEditorMode(self,name,mode):pass
        class Doc:
            def recompute(self):pass
            def saveAs(self,path):Path(path).write_text('partial FCStd')
        part=types.ModuleType('Part');part.read=lambda path:Shape()
        importer=types.ModuleType('Import');importer.export=lambda objects,path:Path(path).write_text('STEP')
        result={'filename_stem':'G01_TEST','validation':{'valid_solids':1,'bounds_mm':[0,0,0,1,1,1],'total_shape_volume_mm3':10.0}}
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(sys.modules,{'Part':part,'Import':importer}),patch.object(document,'Kernel',return_value=Kernel()),patch.object(document,'serializable',side_effect=RuntimeError('forced JSON failure')):
                with self.assertRaisesRegex(RuntimeError,'forced JSON failure'):
                    document.export_document(Doc(),Root(),[object()],result,folder)
            stem=Path(folder)/'G01_TEST'
            for suffix in ('.step','.FCStd','.json','.lock'):
                self.assertFalse(Path(str(stem)+suffix).exists())
            self.assertTrue(Path(str(stem)+'.FCStd.FAILED').is_file())
            self.assertEqual(list(Path(folder).glob('.airkan_*')),[])
            self.assertEqual(list(Path(folder).glob('*.tmp')),[])
    def test_bom_aggregates_duplicate_roots_only(self):
        class Obj:pass
        def root(quantity):
            obj=Obj();obj.BuilderSchema='airkan-component-v3';obj.BOMItemKey='same-item';obj.Label='Same item'
            obj.CatalogueCode='REG';obj.CatalogueLabel='REG 800 - 1000';obj.ModelDetail='BOM_SIMPLIFIED'
            obj.BOMQuantity=quantity;obj.ParametersJSON=json.dumps({'family':'REG','prefix':'G01','a_mm':1000,'b_mm':800,'variant':'REG'})
            return obj
        internal=Obj();internal.BuilderSchema='';internal.BOMQuantity=99
        doc=Obj();doc.Objects=[root(1),internal,root(2)]
        items=bom_from_document(doc)
        self.assertEqual(len(items),1);self.assertEqual(items[0]['quantity'],3);self.assertEqual(items[0]['group_prefix'],'G01')

if __name__=='__main__':unittest.main(verbosity=2)
