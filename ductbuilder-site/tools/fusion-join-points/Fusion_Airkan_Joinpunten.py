# -*- coding: utf-8 -*-
"""Optional Fusion script. Native runtime not tested in the delivery environment.
Run on the separately opened, unmoved STEP component, never on the full installation.
No cloud save, file overwrite, design-mode switch, or component movement is performed.
"""
import json
import math
import traceback
from pathlib import Path


def validated_data(data):
    if not isinstance(data,dict) or data.get('schema')!='airkan-component-v3' or data.get('units')!='mm':
        raise ValueError('Selecteer het volledige export-JSON van Airkan v3, niet een invoervoorbeeld.')
    bounds=data.get('validation',{}).get('bounds_mm',[])
    if len(bounds)!=6 or not all(isinstance(x,(int,float)) and math.isfinite(x) for x in bounds):raise ValueError('Ongeldige modelgrenzen in JSON.')
    datums=data.get('join_datums',[])
    if not isinstance(datums,list) or not 1<=len(datums)<=50:raise ValueError('Geen geldige aansluitreferenties.')
    names=set()
    for d in datums:
        name=d.get('name','')
        if not name.startswith('JO_') or name in names:raise ValueError('Ongeldige of dubbele jointnaam.')
        names.add(name)
        for key in ('point_mm','x_axis','z_axis'):
            v=d.get(key,[])
            if len(v)!=3 or not all(isinstance(a,(int,float)) and math.isfinite(a) for a in v):raise ValueError('Ongeldige vector '+key)
        x,z=d['x_axis'],d['z_axis']
        if abs(sum(a*b for a,b in zip(x,z)))>1e-6 or any(abs(sum(a*a for a in v)-1)>1e-6 for v in (x,z)):
            raise ValueError('Joint-assen moeten orthonormaal zijn.')
        if abs(x[1])>1e-7 or abs(z[1])>1e-7:raise ValueError('Deze helper ondersteunt alleen de XZ-georienteerde poorten van Airkan v3.')
    return data


def run(context):
    import adsk.core
    import adsk.fusion
    app=adsk.core.Application.get();ui=app.userInterface;created=[]
    try:
        design=adsk.fusion.Design.cast(app.activeProduct)
        if design is None:raise ValueError('Open het afzonderlijke STEP-onderdeel in de Design-omgeving.')
        root=design.rootComponent
        if design.activeComponent!=root:raise ValueError('Activeer eerst de root van het afzonderlijke onderdeel.')
        dialog=ui.createFileDialog();dialog.title='Airkan v3 export-JSON bij dit STEP-onderdeel';dialog.filter='JSON (*.json)'
        if dialog.showOpen()!=adsk.core.DialogResults.DialogOK:return
        data=validated_data(json.loads(Path(dialog.filename).read_text(encoding='utf-8')))
        names={d['name'] for d in data['join_datums']}
        existing={root.jointOrigins.item(i).name for i in range(root.jointOrigins.count)}
        if names & existing:raise ValueError('Deze jointnamen bestaan al; niets gewijzigd: '+', '.join(sorted(names & existing)))
        # Bounding box is checked BEFORE adding construction entities.
        bbox=root.boundingBox
        actual=[10*v for v in (bbox.minPoint.x,bbox.minPoint.y,bbox.minPoint.z,bbox.maxPoint.x,bbox.maxPoint.y,bbox.maxPoint.z)]
        if max(abs(a-b) for a,b in zip(actual,data['validation']['bounds_mm']))>.05:
            raise ValueError('Modelgrenzen komen niet overeen (tolerantie 0,05 mm). Gebruik het juiste, ongewijzigde en niet-verplaatste afzonderlijke STEP-model.\nJSON: '+str(data['validation']['bounds_mm'])+'\nFusion: '+str(actual))
        count=root.bRepBodies.count
        for i in range(root.allOccurrences.count):count+=root.allOccurrences.item(i).bRepBodies.count
        if count!=data['validation']['valid_solids']:
            raise ValueError('Aantal bodies verschilt. Verwacht %s, gevonden %s. Geen joints toegevoegd.'%(data['validation']['valid_solids'],count))
        answer=ui.messageBox('Actief document: '+app.activeDocument.name+'\n\nVerwacht onderdeel:\n'+data['filename_stem']+
                            '\n\nAlleen doorgaan als dit HET AFZONDERLIJKE onderdeel is, op zijn oorspronkelijke positie.\n'
                            'Er komen %s native Joint Origins en verborgen constructiereferenties. Geen automatische opslag.'%len(names),
                            'Airkan - bevestig onderdeel',adsk.core.MessageBoxButtonTypes.YesNoButtonType)
        if answer!=adsk.core.DialogResults.DialogYes:return
        base=root.xZConstructionPlane;plane=base.geometry
        def xyz(v):return adsk.core.Point3D.create(v[0]/10,v[1]/10,v[2]/10)
        def alignment(v,target):return v.x*target[0]+v.y*target[1]+v.z*target[2]
        for d in data['join_datums']:
            point=xyz(d['point_mm'])
            off=(point.x-plane.origin.x)*plane.normal.x+(point.y-plane.origin.y)*plane.normal.y+(point.z-plane.origin.z)*plane.normal.z
            cp=base
            if abs(off)>1e-10:
                inp=root.constructionPlanes.createInput()
                if not inp.setByOffset(base,adsk.core.ValueInput.createByReal(off)):raise RuntimeError('Constructievlak kon niet worden gedefinieerd.')
                cp=root.constructionPlanes.add(inp);created.append(cp);cp.name=d['name']+'_plane';cp.isLightBulbOn=False
            sketch=root.sketches.add(cp);created.append(sketch);sketch.name=d['name']+'_axes'
            local=sketch.modelToSketchSpace(point)
            if abs(local.z)>1e-6:raise RuntimeError('Referentiepunt ligt niet in zijn berekende constructievlak.')
            pt=sketch.sketchPoints.add(local)
            if pt.worldGeometry.distanceTo(point)>1e-6:raise RuntimeError('Sketch-punttransformatie onjuist.')
            lines={}
            for key in ('x_axis','z_axis'):
                q=xyz([d['point_mm'][j]+25*d[key][j] for j in range(3)])
                line=sketch.sketchCurves.sketchLines.addByTwoPoints(pt,sketch.modelToSketchSpace(q));line.isConstruction=True;lines[key]=line
            geom=adsk.fusion.JointGeometry.createByPoint(pt)
            inp=root.jointOrigins.createInput(geom);inp.xAxisEntity=lines['x_axis'];inp.zAxisEntity=lines['z_axis']
            origin=root.jointOrigins.add(inp);created.append(origin);origin.name=d['name']
            if alignment(origin.primaryAxisVector,d['z_axis'])<.99999 or alignment(origin.secondaryAxisVector,d['x_axis'])<.99999:
                raise RuntimeError('Native joint-assen wijken af. Nieuwe referenties worden verwijderd; geen stilzwijgende flip.')
            sketch.isVisible=False
        ui.messageBox('Gemaakt: '+', '.join(d['name'] for d in data['join_datums'])+'\n\nSla dit onderdeel zelf op. Joint later de volledige component, niet een intern profiel.','Airkan - gereed')
    except Exception:
        errors=[]
        for obj in reversed(created):
            try:
                if obj.isValid:obj.deleteMe()
            except Exception as exc:errors.append(str(exc))
        text=traceback.format_exc()
        if errors:text+='\nVerwijderen van enkele NIEUWE referenties mislukte; controleer de boom: '+str(errors)
        ui.messageBox(text,'Airkan - gestopt')
