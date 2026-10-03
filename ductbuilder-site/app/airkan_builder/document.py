"""FreeCAD document and checked export. Imported only inside FreeCAD."""
from __future__ import annotations
import errno
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from .geometry import build_geometry, serializable
from .kernel import Kernel
from .rules import CAT, InputError, VERSION, resolve


def prop(obj,kind,name,value,group='Airkan',readonly=True):
    if name not in obj.PropertiesList:obj.addProperty(kind,name,group)
    setattr(obj,name,value)
    if readonly:obj.setEditorMode(name,1)


def create_document(params,show_references=True,progress=None):
    import FreeCAD as App
    import Part
    result=build_geometry(params,progress=progress)
    doc=App.newDocument('Airkan_Component')
    doc.Label=result['filename_stem']
    try:
        doc.openTransaction('Airkan BOM-component')
        root=doc.addObject('App::Part','AirkanComponent');root.Label=result['filename_stem']
        prop(root,'App::PropertyString','BuilderSchema',result['schema'])
        prop(root,'App::PropertyString','GroupPrefix',result['parameters']['prefix'])
        prop(root,'App::PropertyString','Family',params['family'])
        prop(root,'App::PropertyString','CatalogueCode',str(result['order']['catalogue_family_code']))
        prop(root,'App::PropertyString','CatalogueLabel',result['order']['catalogue_label'])
        prop(root,'App::PropertyString','ModelDetail',result['detail'])
        prop(root,'App::PropertyInteger','BOMQuantity',1)
        prop(root,'App::PropertyBool','BOMCountChildren',False)
        prop(root,'App::PropertyString','BOMItemKey',result['filename_stem'])
        prop(root,'App::PropertyString','ParametersJSON',json.dumps(result['parameters'],ensure_ascii=False,sort_keys=True))
        prop(root,'App::PropertyString','SourceReferencesJSON',json.dumps(result['source_references'],ensure_ascii=False))
        prop(root,'App::PropertyString','JoiningDatumsJSON',json.dumps(result['join_datums']))
        prop(root,'App::PropertyString','Warnings','\n'.join(result['warnings']))
        if 'pricing_status' in result['order']:
            prop(root,'App::PropertyString','PricingStatus',result['order']['pricing_status'])
        if 'unit_price_eur' in result['order']:
            prop(root,'App::PropertyString','CataloguePriceEUR','%.2f'%result['order']['unit_price_eur'])
        prop(root,'App::PropertyString','Regenerate','Airkan_Builder: Uit actief model -> wijzigen -> nieuw model bouwen. Geen live FeaturePython-afhankelijkheid.')
        prop(root,'App::PropertyString','WeightStatus','NOT_CALCULATED: simplified/reconstructed geometry is not a weight certificate')
        objects=[];groups={}
        for j,p in enumerate(result['parts']):
            if p['single_body']:
                obj=doc.addObject('PartDesign::Body','Body_'+str(j+1))
                root.addObject(obj)
                feature=doc.addObject('PartDesign::Feature','Geometry_'+str(j+1));obj.addObject(feature)
                feature.Shape=p['shape'];feature.Label='Geometrie';obj.Tip=feature
                if App.GuiUp:
                    feature.Visibility=True
                    if hasattr(obj.ViewObject,'DisplayModeBody'):obj.ViewObject.DisplayModeBody='Tip'
            else:
                group_name=p['role']
                if group_name not in groups:
                    group=doc.addObject('App::Part','Frame_'+group_name);root.addObject(group);group.Label=group_name+' - intern kaderdetail'
                    prop(group,'App::PropertyBool','BOMExclude',True);groups[group_name]=group
                obj=doc.addObject('Part::Feature','FrameDetail_'+str(j+1));groups[group_name].addObject(obj);obj.Shape=p['shape']
            obj.Label=p['name']+' | '+str(p['code']);objects.append(obj)
            prop(obj,'App::PropertyBool','BOMExclude',True)
            prop(obj,'App::PropertyString','GeometryRole',p['role'])
            if App.GuiUp:
                obj.ViewObject.ShapeColor=(.76,.79,.82)
                obj.ViewObject.LineColor=(.18,.20,.23)
                obj.ViewObject.DisplayMode='Flat Lines'
        refs=doc.addObject('App::Part','Aansluitreferenties');root.addObject(refs)
        refs.Label='Aansluitreferenties - niet in fysieke STEP';prop(refs,'App::PropertyBool','BOMExclude',True)
        for d in result['join_datums']:
            obj=doc.addObject('Part::Feature',d['name']);refs.addObject(obj);obj.Label=d['name']
            point=App.Vector(*d['point_mm'])
            # Actual point plus axes, never a physical dummy solid.
            axes=[Part.Vertex(point)]
            for key in ('x_axis','z_axis'):
                vec=App.Vector(*d[key]);axes.append(Part.makeLine(point,point+vec*25))
            obj.Shape=Part.makeCompound(axes)
            prop(obj,'App::PropertyVector','PointMM',point)
            prop(obj,'App::PropertyVector','XAxis',App.Vector(*d['x_axis']))
            prop(obj,'App::PropertyVector','ZAxis',App.Vector(*d['z_axis']))
            prop(obj,'App::PropertyString','DatumKind',d['kind'])
            prop(obj,'App::PropertyBool','BOMExclude',True)
            if App.GuiUp:obj.ViewObject.PointSize=5;obj.ViewObject.LineColor=(.10,.60,.75)
        doc.recompute()
        if App.GuiUp:
            refs.Visibility=bool(show_references)
            for obj in objects:obj.Visibility=True
        doc.commitTransaction()
        result['validation']['freecad_document_created']=True
        return doc,root,objects,result
    except Exception:
        doc.abortTransaction()
        App.closeDocument(doc.Name)
        raise


def _file_sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda:source.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def create_imported_step_document(params,progress=None):
    """Import a user-supplied CM or BUY STEP unchanged with auditable metadata."""
    import FreeCAD as App
    import Part
    data=resolve(params);p=data['params']
    family=p['family']
    if family not in ('CM','BUY'):raise InputError('STEP-import is alleen voor de CM- en BUY-families.')
    source=Path(p['source_step']).expanduser().resolve()
    if not source.is_file():raise InputError(family+' STEP file does not exist: '+str(source))
    if progress:progress(family+' STEP inlezen en meten')
    source_hash=_file_sha256(source)
    shape=Part.read(str(source))
    need_valid=getattr(shape,'isValid',lambda:False)()
    if not need_valid:raise InputError(family+' STEP does not contain a valid Shape.')
    solid_count=len(shape.Solids)
    if solid_count<1:raise InputError(family+' STEP must contain at least one solid.')
    area_mm2=float(shape.Area);volume_mm3=float(shape.Volume)
    if area_mm2<=0:raise InputError(family+' STEP has no measurable surface area.')
    if _file_sha256(source)!=source_hash:raise InputError(family+' STEP wijzigde tijdens het inlezen; probeer opnieuw.')
    all_faces_area_m2=area_mm2/1000000.0
    data['derived'].update(source_step_sha256=source_hash,surface_area_mm2=area_mm2,
                           fusion_all_faces_area_m2=all_faces_area_m2)
    if family=='CM':
        one_sided_area_m2=all_faces_area_m2/2.0
        data['derived'].update(one_sided_price_area_m2=one_sided_area_m2)
        data['order'].update(area_rate_eur_per_m2=p['area_rate_eur_per_m2'],
                             fusion_all_faces_area_m2=all_faces_area_m2,one_sided_price_area_m2=one_sided_area_m2,
                             calculation='Total is calculated on demand from surface_area_mm2 / 1000000 / 2 and the current rate.',
                             pricing_status='AREA_MEASURED')
    data['order']['source_step_sha256']=source_hash
    description=re.sub(r'[^A-Za-z0-9_-]+','_',p['description']).strip('_')[:40] or 'custom'
    data['filename_stem']=p['prefix']+'_'+family+'_'+description+'_'+source_hash[:12]
    bounds=Kernel().bounds(shape)
    source_references=[{**reference,**CAT['sources'][reference['source_id']]} for reference in data['family_spec']['sources']]
    bom={'quantity':1,'article':data['order']['catalogue_label'],'count_children':False,'mass_kg':None,
         'status':data['order']['pricing_status']}
    if 'unit_price_eur' in data['order']:bom['unit_price_eur']=data['order']['unit_price_eur']
    result={'schema':'airkan-component-v3','version':VERSION,'rules_sha256':data['rules_sha256'],'units':'mm',
            'parameters':p,'derived':data['derived'],'filename_stem':data['filename_stem'],'order':data['order'],
            'detail':data['family_spec']['detail'],'warnings':data['warnings'],'source_references':source_references,
            'source_notes':data['family_spec']['notes'],'parts':[{'name':family+'_geimporteerde_STEP','shape':shape,'code':family,'role':'imported_step','single_body':False}],
            'shape':shape,'join_datums':[],'frames':[],
            'geometry':{'source_step':str(source),'source_step_sha256':source_hash,'import_mode':'UNCHANGED_USER_SUPPLIED_STEP'},
            'bom':bom,
            'validation':{'backend':'freecad_step_import','valid_solids':solid_count,'physical_objects':1,'partdesign_body_count':0,
                          'bounds_mm':bounds,'total_shape_volume_mm3':volume_mm3,'total_shape_area_mm2':area_mm2,
                          'source_step_sha256':source_hash,'clashes':[],'exact_intersection_checks':0,
                          'air_and_hole_sample_checks':0,'right_handed_ports':0,
                          'not_tested':['fabrication tolerances','material identity','sheet thickness','quotation scope']}}
    doc=App.newDocument('Allshield_'+family+'_Component');doc.Label=data['filename_stem']
    try:
        doc.openTransaction('Allshield '+family+' STEP import')
        root=doc.addObject('App::Part','AirkanComponent');root.Label=data['filename_stem']
        prop(root,'App::PropertyString','BuilderSchema',result['schema'])
        prop(root,'App::PropertyString','GroupPrefix',p['prefix'])
        prop(root,'App::PropertyString','Family',family)
        prop(root,'App::PropertyString','CatalogueCode',family)
        prop(root,'App::PropertyString','CatalogueLabel',data['order']['catalogue_label'])
        prop(root,'App::PropertyString','ModelDetail',result['detail'])
        prop(root,'App::PropertyInteger','BOMQuantity',1)
        prop(root,'App::PropertyBool','BOMCountChildren',False)
        prop(root,'App::PropertyString','BOMItemKey',data['filename_stem'])
        prop(root,'App::PropertyString','ParametersJSON',json.dumps(p,ensure_ascii=False,sort_keys=True))
        prop(root,'App::PropertyString','SourceReferencesJSON',json.dumps(source_references,ensure_ascii=False))
        prop(root,'App::PropertyString','JoiningDatumsJSON','[]')
        prop(root,'App::PropertyString','Warnings','\n'.join(data['warnings']))
        prop(root,'App::PropertyString','SourceStepSHA256',source_hash)
        if family=='CM':
            prop(root,'App::PropertyString','MeasuredAreaM2','%.6f'%one_sided_area_m2)
            prop(root,'App::PropertyString','AreaRateEURPerM2','%.2f'%p['area_rate_eur_per_m2'])
        else:
            prop(root,'App::PropertyString','Supplier',p['supplier'])
            prop(root,'App::PropertyString','ArticleCode',p['article_code'])
            prop(root,'App::PropertyString','PricingStatus',p['price_status'])
        obj=doc.addObject('Part::Feature',family+'_Imported_STEP');root.addObject(obj);obj.Label=p['description'];obj.Shape=shape
        prop(obj,'App::PropertyBool','BOMExclude',True)
        prop(obj,'App::PropertyString','GeometryRole','imported_step')
        if App.GuiUp:
            obj.ViewObject.ShapeColor=(.72,.76,.78);obj.ViewObject.LineColor=(.18,.20,.23);obj.ViewObject.DisplayMode='Flat Lines'
        doc.recompute();doc.commitTransaction();result['validation']['freecad_document_created']=True
        return doc,root,[obj],result
    except Exception:
        doc.abortTransaction();App.closeDocument(doc.Name);raise


def _reserve(outdir,basename):
    outdir=Path(outdir).expanduser().resolve()
    try:outdir.mkdir(parents=True,exist_ok=True)
    except OSError as exc:
        if isinstance(exc,PermissionError) or exc.errno in (errno.EACCES,errno.EROFS):
            raise InputError('Uitvoermap is niet schrijfbaar: '+str(outdir)) from exc
        raise
    for index in range(100000):
        name=basename+('_%03d'%index if index else '')
        stem=outdir/name
        if any(Path(str(stem)+e).exists() for e in ('.step','.FCStd','.json','.lock','.step.FAILED','.FCStd.FAILED','.json.FAILED')):continue
        lock=Path(str(stem)+'.lock')
        try:
            fd=os.open(str(lock),os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd)
            return stem,lock
        except FileExistsError:continue
        except OSError as exc:
            if isinstance(exc,PermissionError) or exc.errno in (errno.EACCES,errno.EROFS):
                raise InputError('Uitvoermap is niet schrijfbaar: '+str(outdir)) from exc
            raise
    raise RuntimeError('No available file name was found.')


def export_document(doc,root,objects,result,outdir):
    import Part
    if not str(outdir).strip():raise InputError('Choose an output folder.')
    if os.name!='nt' and re.match(r'^[A-Za-z]:[\\/]',str(outdir)):
        raise InputError('Windows path on a non-Windows system: choose an existing local output folder.')
    stem,lock=_reserve(outdir,result['filename_stem'])
    paths={'step':str(stem)+'.step','freecad':str(stem)+'.FCStd','parameters':str(stem)+'.json'}
    temporary=[]
    try:
        fd,stmp=tempfile.mkstemp(suffix='.step',prefix='.airkan_',dir=str(stem.parent));os.close(fd);temporary.append(stmp)
        try:
            import Import
            Import.export(objects,stmp)
        except ImportError:Part.export(objects,stmp)
        if not Path(stmp).is_file() or Path(stmp).stat().st_size==0:raise RuntimeError('Lege STEP-uitvoer.')
        shape=Part.read(stmp);k=Kernel();val=result['validation']
        if not shape.isValid() or len(shape.Solids)!=val['valid_solids']:raise RuntimeError('STEP-terugleescontrole: aantal/geldigheid solids gewijzigd.')
        if any(abs(a-b)>1e-3 for a,b in zip(k.bounds(shape),val['bounds_mm'])):raise RuntimeError('STEP-terugleescontrole: buitenmaten gewijzigd.')
        volume_reference=val.get('step_volume_reference_mm3',val['total_shape_volume_mm3'])
        volume_tolerance=val.get('step_volume_relative_tolerance',1e-5)
        if abs(shape.Volume-volume_reference)>max(.01,volume_reference*volume_tolerance):raise RuntimeError('STEP-terugleescontrole: volume gewijzigd.')
        if 'total_shape_area_mm2' in val and abs(shape.Area-val['total_shape_area_mm2'])>max(.01,val['total_shape_area_mm2']*1e-5):raise RuntimeError('STEP-terugleescontrole: oppervlak gewijzigd.')
        prop(root,'App::PropertyString','ExportValidation','STEP reread PASS; solids/bounds/volume')
        doc.recompute();doc.saveAs(paths['freecad'])
        if not Path(paths['freecad']).is_file():raise RuntimeError('FCStd is niet opgeslagen.')
        data=serializable(result);data['created_utc']=datetime.now(timezone.utc).isoformat();data['files']=paths
        data['validation']=dict(data['validation'],step_reread='PASS',freecad_saved=True,step_bounds_tolerance_mm=.001,step_volume_relative_tolerance=volume_tolerance)
        jtmp=paths['parameters']+'.tmp';temporary.append(jtmp)
        with open(jtmp,'w',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2,allow_nan=False)
        os.replace(stmp,paths['step']);os.replace(jtmp,paths['parameters'])
        return paths
    except Exception:
        for path in paths.values():
            if Path(path).exists():
                try:os.replace(path,path+'.FAILED')
                except OSError:pass
        raise
    finally:
        for path in temporary+[str(lock)]:
            try:os.unlink(path)
            except OSError:pass


def export_step_json(doc,root,objects,result,outdir,basename=None,project_item=None):
    """Export checked STEP and parameter JSON without persisting a FreeCAD document."""
    import Part
    if not str(outdir).strip():raise InputError('Choose an output folder.')
    if os.name!='nt' and re.match(r'^[A-Za-z]:[\\/]',str(outdir)):
        raise InputError('Windows path on a non-Windows system: choose an existing local output folder.')
    name=basename or result['filename_stem']
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,159}',name):
        raise InputError('Invalid STEP file name.')
    stem,lock=_reserve(outdir,name)
    paths={'step':str(stem)+'.step','parameters':str(stem)+'.json'}
    temporary=[]
    try:
        fd,stmp=tempfile.mkstemp(suffix='.step',prefix='.airkan_',dir=str(stem.parent));os.close(fd);temporary.append(stmp)
        try:
            import Import
            Import.export(objects,stmp)
        except ImportError:Part.export(objects,stmp)
        if not Path(stmp).is_file() or Path(stmp).stat().st_size==0:raise RuntimeError('Lege STEP-uitvoer.')
        shape=Part.read(stmp);k=Kernel();val=result['validation']
        if not shape.isValid() or len(shape.Solids)!=val['valid_solids']:raise RuntimeError('STEP-terugleescontrole: aantal/geldigheid solids gewijzigd.')
        if any(abs(a-b)>1e-3 for a,b in zip(k.bounds(shape),val['bounds_mm'])):raise RuntimeError('STEP-terugleescontrole: buitenmaten gewijzigd.')
        volume_reference=val.get('step_volume_reference_mm3',val['total_shape_volume_mm3'])
        volume_tolerance=val.get('step_volume_relative_tolerance',1e-5)
        if abs(shape.Volume-volume_reference)>max(.01,volume_reference*volume_tolerance):raise RuntimeError('STEP-terugleescontrole: volume gewijzigd.')
        if 'total_shape_area_mm2' in val and abs(shape.Area-val['total_shape_area_mm2'])>max(.01,val['total_shape_area_mm2']*1e-5):raise RuntimeError('STEP-terugleescontrole: oppervlak gewijzigd.')
        prop(root,'App::PropertyString','ExportValidation','STEP reread PASS; solids/bounds/volume')
        doc.recompute()
        data=serializable(result);data['created_utc']=datetime.now(timezone.utc).isoformat();data['files']=paths
        if project_item is not None:data['project_item']=project_item
        data['validation']=dict(data['validation'],step_reread='PASS',freecad_saved=False,step_bounds_tolerance_mm=.001,step_volume_relative_tolerance=volume_tolerance)
        jtmp=paths['parameters']+'.tmp';temporary.append(jtmp)
        with open(jtmp,'w',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2,allow_nan=False)
        os.replace(stmp,paths['step']);os.replace(jtmp,paths['parameters'])
        return paths
    except Exception:
        for path in paths.values():
            if Path(path).exists():
                try:os.replace(path,path+'.FAILED')
                except OSError:pass
        raise
    finally:
        for path in temporary+[str(lock)]:
            try:os.unlink(path)
            except OSError:pass


def parameters_from_document(doc,selection=None):
    if doc is None:raise InputError('There is no active document.')
    candidates=[]
    if selection:
        pending=list(selection);visited=set()
        while pending:
            obj=pending.pop()
            token=id(obj)
            if token in visited:continue
            visited.add(token)
            if getattr(obj,'BuilderSchema','')=='airkan-component-v3':
                if obj not in candidates:candidates.append(obj)
            else:pending.extend(getattr(obj,'InList',[]))
    else:candidates=[obj for obj in doc.Objects if getattr(obj,'BuilderSchema','')=='airkan-component-v3']
    if not candidates:raise InputError('No Airkan v3 component was found in the selection or active document.')
    if len(candidates)!=1:raise InputError('Selecteer precies een AirkanComponent in de boom.')
    return json.loads(candidates[0].ParametersJSON)


def bom_from_document(doc):
    """Exactly one item per Airkan root; NEVER count internal bodies/rails/corners."""
    items={}
    for obj in doc.Objects:
        if getattr(obj,'BuilderSchema','')!='airkan-component-v3':continue
        key=obj.BOMItemKey
        if key not in items:
            parameters=json.loads(obj.ParametersJSON)
            items[key]={'item_key':key,'label':obj.Label,'catalogue_code':obj.CatalogueCode,'catalogue_label':obj.CatalogueLabel,
                        'group_prefix':getattr(obj,'GroupPrefix',parameters.get('prefix','')),
                        'model_detail':obj.ModelDetail,'quantity':0,'parameters':parameters,'mass_kg':None}
        items[key]['quantity']+=int(obj.BOMQuantity)
    return list(items.values())
