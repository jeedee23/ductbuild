"""Run ONLY inside FreeCAD: native document, one-Body and export/reopen checks."""
from pathlib import Path
import json
import traceback
from datetime import datetime
from .rules import defaults,VERSION
from .kernel import frame_api
from .document import create_document,export_document,bom_from_document


def main():
    import FreeCAD as App
    import FreeCADGui as Gui
    if not App.GuiUp:raise RuntimeError('Voer deze zelftest binnen FreeCAD GUI uit.')
    W,C=frame_api()['qt_modules']()
    folder=W.QFileDialog.getExistingDirectory(Gui.getMainWindow(),'Kies map voor NIEUWE Airkan-zelftestbestanden')
    if not folder:return
    out=Path(folder)/('Airkan_Zelftest_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'));out.mkdir()
    report={'schema':'airkan-native-selftest-v3','version':VERSION,'freecad_version':App.Version(),'cases':[]}
    cases=[('REG',{}),('FRAME',{}),('FRAME',{'a_mm':1300}),('BU',{'t_mm':.95}),
           ('BEND_RECT',{'t_mm':.95,'angle_deg':37.5,'turn':'LINKS'}),
           ('RECT_ROUND',{'t_mm':.95,'straight_out_mm':50}),('BEND_ROUND',{'t_mm':.95}),
           ('FLANGE_ROUND',{}),('SL_RECT',{'a_mm':1300})]
    old=App.ActiveDocument.Name if App.ActiveDocument else None
    progress=W.QProgressDialog('Native controle...',None,0,len(cases),Gui.getMainWindow());progress.setCancelButton(None);progress.show()
    try:
        for index,(family,overrides) in enumerate(cases):
            params={**defaults(family),**overrides};row={'family':family,'parameters':params,'passed':False};doc=None;reopened=None
            progress.setValue(index);progress.setLabelText(family);W.QApplication.processEvents()
            try:
                doc,root,objects,result=create_document(params,show_references=False)
                bodies=[o for o in doc.Objects if o.TypeId=='PartDesign::Body']
                if len(bodies)!=result['validation']['partdesign_body_count']:raise RuntimeError('Onjuist aantal PartDesign::Body-objecten.')
                if result['detail']=='BOM_SIMPLIFIED' and len(bodies)!=1:raise RuntimeError('Vereenvoudigd model is niet precies een Body.')
                for obj in objects:
                    if not obj.Shape.isValid() or len(obj.Shape.Solids)!=1:raise RuntimeError('Document bevat geen geldige fysieke een-solid-objecten.')
                if len(bom_from_document(doc))!=1:raise RuntimeError('BOM telt intern detail dubbel.')
                paths=export_document(doc,root,objects,result,str(out))
                App.closeDocument(doc.Name);doc=None
                reopened=App.openDocument(paths['freecad'])
                roots=[o for o in reopened.Objects if getattr(o,'BuilderSchema','')=='airkan-component-v3']
                if len(roots)!=1:raise RuntimeError('FCStd-heropening mist de onderdeelroot.')
                if json.loads(roots[0].ParametersJSON)!=result['parameters']:raise RuntimeError('Parameters gewijzigd na FCStd-heropening.')
                if len([o for o in reopened.Objects if o.TypeId=='PartDesign::Body'])!=len(bodies):raise RuntimeError('Body-aantal gewijzigd na FCStd-heropening.')
                row.update(passed=True,files=paths,body_count=len(bodies),solid_count=result['validation']['valid_solids'],step_reread='PASS',fcstd_reopen='PASS')
            except Exception as exc:row.update(error=str(exc),traceback=traceback.format_exc())
            finally:
                for opened in (doc,reopened):
                    if opened:
                        try:App.closeDocument(opened.Name)
                        except Exception:pass
            report['cases'].append(row)
            (out/'Zelftest_resultaat.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        report['summary']={'passed':sum(r['passed'] for r in report['cases']),'total':len(cases)}
        (out/'Zelftest_resultaat.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        progress.close();W.QMessageBox.information(Gui.getMainWindow(),'Airkan zelftest','Geslaagd: %s / %s\n\nResultaten:\n%s'%(report['summary']['passed'],len(cases),out))
    finally:
        progress.close()
        if old and old in App.listDocuments():App.setActiveDocument(old)
    return report
