"""Dutch, data-driven FreeCAD dialog. Parameter snapshots need no custom workbench."""
from __future__ import annotations
import json
import os
import traceback
from pathlib import Path
from .rules import FAMILIES, CAT, DEFAULT_PREFIX, defaults, resolve, InputError, VERSION, ui_choice_label, ui_field_label, ui_field_note
from .pricing import rectangular_priced_thicknesses
from .kernel import frame_api


def main(on_ready=None):
    import FreeCAD as App
    import FreeCADGui as Gui
    from .document import create_document,create_imported_step_document,export_document,parameters_from_document,bom_from_document
    if not App.GuiUp:raise RuntimeError('Voer Airkan_Builder.FCMacro uit BINNEN de FreeCAD-GUI.')
    W,C=frame_api()['qt_modules']()
    try:from PySide import QtGui
    except ImportError:
        try:from PySide2 import QtGui
        except ImportError:from PySide6 import QtGui
    settings=App.ParamGet('User parameter:BaseApp/Preferences/Macros/AirkanBuilderV3')
    home=str(Path(__file__).resolve().parents[1])

    class Dialog(W.QDialog):
        def __init__(self):
            super().__init__(Gui.getMainWindow())
            self.busy=False;self.widgets={};self.last=None
            self.setWindowTitle('Airkan v'+VERSION+' - FreeCAD BOM / kanaalbouwer')
            self.resize(880,800)
            layout=W.QVBoxLayout(self)
            intro=W.QLabel('Vrije binnenmaten in mm. A = X, B = Y; bij bochten ligt A in het XZ-bochtvlak.\n'
                            'E30/H30 t/m 1250 mm; A40/H40 zodra een aansluitmaat >1250 mm.\n'
                            'Een bestelonderdeel = een BOM-regel. Vereenvoudigde producten = een Body.')
            intro.setWordWrap(True);layout.addWidget(intro)
            self.family=W.QComboBox()
            for key,spec in FAMILIES.items():
                suffix='' if spec['status']=='IMPLEMENTED' else ' [alleen bronregister]'
                self.family.addItem(spec['label']+suffix,key)
            layout.addWidget(self.family)
            prefixrow=W.QHBoxLayout();layout.addLayout(prefixrow)
            prefixlabel=W.QLabel('Groepsprefix:');prefixlabel.setMinimumWidth(110);prefixrow.addWidget(prefixlabel)
            self.prefix=W.QLineEdit(settings.GetString('GroupPrefix',DEFAULT_PREFIX))
            self.prefix.setToolTip('Groepsnummer voor bestandsnaam en BOM-identiteit, bijvoorbeeld G01 of AHU2-03. AIRKAN is niet toegestaan.')
            self.prefix.textChanged.connect(self.refresh);prefixrow.addWidget(self.prefix,1)
            self.tabs=W.QTabWidget();layout.addWidget(self.tabs,1)
            self.scroll=W.QScrollArea();self.scroll.setWidgetResizable(True);self.tabs.addTab(self.scroll,'Parameters')
            sourcepage=W.QWidget();sl=W.QVBoxLayout(sourcepage)
            self.sources=W.QTextBrowser();sl.addWidget(self.sources)
            self.source_dir=W.QLineEdit(settings.GetString('SourceFolder',str(Path(home)/'sources')))
            sl.addWidget(W.QLabel('Map met jouw oorspronkelijke bron-PDFs:'));sl.addWidget(self.source_dir)
            row=W.QHBoxLayout();sl.addLayout(row)
            select=W.QPushButton('Bronmap kiezen');select.clicked.connect(self.choose_source);row.addWidget(select)
            self.open_pdf=W.QPushButton('Primaire bron-PDF openen');self.open_pdf.clicked.connect(self.open_source);row.addWidget(self.open_pdf)
            self.tabs.addTab(sourcepage,'Bronnen en beperkingen')
            self.note=W.QLabel();self.note.setWordWrap(True);layout.addWidget(self.note)
            self.status=W.QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
            pathrow=W.QHBoxLayout();layout.addLayout(pathrow)
            pathrow.addWidget(W.QLabel('Uitvoermap:'))
            defaultout='D:/steps' if os.name=='nt' else str(Path.home()/'Airkan_steps')
            self.output=W.QLineEdit(settings.GetString('OutputFolder',defaultout));pathrow.addWidget(self.output,1)
            choose=W.QPushButton('Map...');choose.clicked.connect(self.choose_output);pathrow.addWidget(choose)
            self.refs=W.QCheckBox('Aansluitreferenties tonen (niet als metaal in STEP)');self.refs.setChecked(True);layout.addWidget(self.refs)
            loadrow=W.QHBoxLayout();layout.addLayout(loadrow)
            for text,slot in [('JSON laden',self.load_json),('Uit actief model',self.load_active),('BOM uit actief document',self.save_bom)]:
                button=W.QPushButton(text);button.clicked.connect(slot);loadrow.addWidget(button)
            buttons=W.QHBoxLayout();layout.addLayout(buttons)
            self.build_button=W.QPushButton('Alleen model bouwen');self.build_button.clicked.connect(lambda:self.build(False));buttons.addWidget(self.build_button)
            self.export_button=W.QPushButton('Bouwen + STEP / FCStd / JSON');self.export_button.clicked.connect(lambda:self.build(True));buttons.addWidget(self.export_button)
            close=W.QPushButton('Sluiten');close.clicked.connect(self.reject);buttons.addWidget(close)
            self.family.currentIndexChanged.connect(self.set_family)
            self.output.textChanged.connect(self.refresh)
            self.set_family()
        def message(self,title,text):W.QMessageBox.information(self,title,text)
        def family_id(self):return self.family.currentData()
        def set_family(self,*unused):
            if self.busy:return
            spec=FAMILIES[self.family_id()]
            self.widgets={};self.field_labels={};self.field_displays={};panel=W.QWidget();form=W.QFormLayout(panel)
            background=self.scroll.viewport().palette().color(QtGui.QPalette.Base)
            label_color='#f2f2f2' if background.lightness()<128 else '#202020'
            for f in spec['fields']:
                thicknesses=rectangular_priced_thicknesses(self.family_id(),defaults(self.family_id()).get('material')) if f['key']=='t_mm' else ()
                if thicknesses:
                    w=W.QComboBox();w.addItems(['%g'%value for value in thicknesses]);w.setCurrentIndex(-1);w.currentTextChanged.connect(self.refresh)
                    display=w
                elif f['kind']=='choice':
                    w=W.QComboBox()
                    for choice in f['choices']:w.addItem(ui_choice_label(f['key'],choice),choice)
                    w.setCurrentIndex(w.findData(f['default']));w.currentTextChanged.connect(self.refresh)
                    display=w
                elif f['kind'] in ('text','file'):
                    w=W.QLineEdit(str(f['default']));w.textChanged.connect(self.refresh);display=w
                    if f['kind']=='file':
                        display=W.QWidget();row=W.QHBoxLayout(display);row.setContentsMargins(0,0,0,0);row.addWidget(w,1)
                        choose=W.QPushButton('Kiezen...');choose.clicked.connect(lambda unused=False,key=f['key']:self.choose_parameter_file(key));row.addWidget(choose)
                else:
                    w=W.QDoubleSpinBox();w.setDecimals(3)
                    # Keep zero as a VISIBLE unfilled sentinel, not silently .001.
                    w.setRange(min(0,f['minimum']),f['maximum']);w.setValue(f['default']);w.setSuffix(' '+f['unit'])
                    w.setKeyboardTracking(False);w.valueChanged.connect(self.refresh);display=w
                note=ui_field_note(f);w.setToolTip(note);self.widgets[f['key']]=w;self.field_displays[f['key']]=display
                label=W.QLabel(ui_field_label(f));self.field_labels[f['key']]=label;label.setToolTip(note);label.setWordWrap(True)
                label.setMinimumWidth(190);label.setStyleSheet('color: '+label_color+';');form.addRow(label,display)
            if 't_mm' in self.widgets and 'material' in self.widgets and rectangular_priced_thicknesses(self.family_id(),defaults(self.family_id()).get('material')):
                self.widgets['material'].currentTextChanged.connect(self.refresh_thickness_choices)
                self.refresh_thickness_choices()
            old=self.scroll.takeWidget()
            if old:old.deleteLater()
            self.scroll.setWidget(panel)
            text=spec['detail']+'\n'+spec['notes']+'\n\n'
            for r in spec['sources']:
                src=CAT['sources'][r['source_id']]
                text+='PDF: '+src['filename']+'\nPDF-pagina: '+str(r['pdf_page'])+'; cataloguspagina: '+str(r['catalogue_page'])+'\nSHA256: '+src['sha256']+'\n\n'
            self.open_pdf.setEnabled(bool(spec['sources']))
            text+='Bestandsnamen zijn projectnamen; familiecode en bestelvelden zijn apart opgeslagen.\n'
            text+='Kanaalplaatdikte, profielplaatdikte, inschuifdiepte in het kader en radiale passing zijn verschillende grootheden.\n'
            text+='Bronregister-types zijn zichtbaar maar bewust niet als fictief onderdeel bouwbaar.'
            for field_key in ('thickness_mode','insertion_mode'):
                if field_key in self.widgets:self.widgets[field_key].currentIndexChanged.connect(self.refresh_field_visibility)
            self.sources.setPlainText(text);self.note.setText(spec['notes']);self.refresh_field_visibility();self.refresh()
        def collect(self):
            out={'family':self.family_id(),'prefix':self.prefix.text()}
            for f in FAMILIES[self.family_id()]['fields']:
                w=self.widgets[f['key']]
                if f['kind']=='choice':out[f['key']]=w.currentData()
                elif f['key']=='t_mm' and isinstance(w,W.QComboBox):out[f['key']]=float(w.currentText()) if w.currentText() else 0.0
                elif f['kind'] in ('text','file'):out[f['key']]=w.text()
                else:out[f['key']]=w.value()
            return out
        def refresh_thickness_choices(self,*unused):
            thickness=self.widgets.get('t_mm');material=self.widgets.get('material')
            if not isinstance(thickness,W.QComboBox) or not isinstance(material,W.QComboBox):return
            choices=['%g'%value for value in rectangular_priced_thicknesses(self.family_id(),material.currentText())]
            if not choices:return
            current=thickness.currentText();thickness.blockSignals(True);thickness.clear();thickness.addItems(choices)
            if current in choices:thickness.setCurrentText(current)
            else:thickness.setCurrentIndex(-1)
            thickness.blockSignals(False);self.refresh()
        def refresh_field_visibility(self,*unused):
            def visible(key,value):
                if key in self.field_labels:self.field_labels[key].setVisible(value);self.field_displays[key].setVisible(value)
            thickness_mode=self.widgets.get('thickness_mode')
            if isinstance(thickness_mode,W.QComboBox):
                automatic=thickness_mode.currentData()=='AIRKAN_BC'
                visible('t_mm',not automatic);visible('airkan_a_mm',False)
            insertion_mode=self.widgets.get('insertion_mode')
            if isinstance(insertion_mode,W.QComboBox):visible('insertion_mm',insertion_mode.currentData()=='HANDMATIGE_INSTEEK')
        def refresh(self,*unused):
            if self.busy:return
            try:
                data=resolve(self.collect())
                text='Bestand: '+data['filename_stem']+'\n'
                if data['warnings']:text+='Modelopmerking: '+data['warnings'][0]
                self.status.setText(text);self.status.setStyleSheet('')
                self.build_button.setEnabled(True);self.export_button.setEnabled(bool(self.output.text().strip()))
            except Exception as e:
                self.status.setText(str(e));self.status.setStyleSheet('color: #b45823;')
                self.build_button.setEnabled(False);self.export_button.setEnabled(False)
        def choose_output(self):
            if self.busy:return
            path=W.QFileDialog.getExistingDirectory(self,'Uitvoermap',self.output.text())
            if path:self.output.setText(path)
        def choose_parameter_file(self,key):
            if self.busy:return
            current=Path(self.widgets[key].text()).expanduser()
            initial=str(current.parent) if current.parent.is_dir() else self.output.text()
            path,_=W.QFileDialog.getOpenFileName(self,'STEP-bestand kiezen',initial,'STEP (*.step *.stp)')
            if path:self.widgets[key].setText(path)
        def choose_source(self):
            if self.busy:return
            path=W.QFileDialog.getExistingDirectory(self,'Map met Airkan bron-PDFs',self.source_dir.text())
            if path:self.source_dir.setText(path);settings.SetString('SourceFolder',path)
        def open_source(self):
            spec=FAMILIES[self.family_id()]
            if not spec['sources']:
                self.message('Geen Airkan-bron','Dit is een extern inkoopdeel. Gebruik het ingevulde leveranciersdocument als bron.')
                return
            r=spec['sources'][0];name=CAT['sources'][r['source_id']]['filename']
            path=Path(self.source_dir.text())/name
            if not path.is_file():self.message('Bron-PDF ontbreekt','Plaats '+name+' in de gekozen bronmap of selecteer de juiste bronmap.');return
            url=C.QUrl.fromLocalFile(str(path));url.setFragment('page='+str(r['pdf_page']))
            QtGui.QDesktopServices.openUrl(url)
        def apply_params(self,data):
            raw=data.get('parameters',data) if isinstance(data,dict) else None
            if not isinstance(raw,dict) or raw.get('family') not in FAMILIES:raise InputError('Geen Airkan v3 parameterbestand.')
            allowed=set(defaults(raw['family']))
            if set(raw)-allowed:raise InputError('Onbekende JSON-invoervelden; geen bestanden of scripts uitgevoerd.')
            # Validate before applying: Qt must not silently clamp invalid loaded dimensions.
            raw=resolve(raw)['params']
            self.family.setCurrentIndex(self.family.findData(raw['family']))
            self.prefix.setText(raw['prefix'])
            # set_family not triggered when the same type is selected; widgets already exist.
            for key,value in raw.items():
                if key=='family':continue
                w=self.widgets.get(key)
                if w is None:continue
                if isinstance(w,W.QComboBox):
                    field=next(field for field in FAMILIES[raw['family']]['fields'] if field['key']==key)
                    index=w.findData(value) if field['kind']=='choice' else w.findText(str(value))
                    if index<0:
                        if key=='t_mm' and raw.get('thickness_mode')=='AIRKAN_BC':w.setCurrentIndex(-1);continue
                        raise InputError('Onbekende keuze voor '+key)
                    w.setCurrentIndex(index)
                elif isinstance(w,W.QLineEdit):w.setText(str(value))
                else:w.setValue(float(value))
            self.refresh_field_visibility();self.refresh()
        def load_json(self):
            if self.busy:return
            path,_=W.QFileDialog.getOpenFileName(self,'Airkan parameters laden',self.output.text(),'JSON (*.json)')
            if not path:return
            try:self.apply_params(json.loads(Path(path).read_text(encoding='utf-8')))
            except Exception as e:W.QMessageBox.warning(self,'JSON niet geladen',str(e))
        def load_active(self):
            if self.busy:return
            try:self.apply_params(parameters_from_document(App.ActiveDocument,Gui.Selection.getSelection()))
            except Exception as e:W.QMessageBox.warning(self,'Geen parameters',str(e))
        def save_bom(self):
            if self.busy:return
            try:
                if App.ActiveDocument is None:raise InputError('Geen actief document.')
                data=bom_from_document(App.ActiveDocument)
                if not data:raise InputError('Geen Airkan v3 BOM-roots in actief document.')
                path,_=W.QFileDialog.getSaveFileName(self,'BOM bewaren',str(Path(self.output.text())/'Airkan_BOM.json'),'JSON (*.json)')
                if not path:return
                Path(path).write_text(json.dumps({'schema':'airkan-bom-v3','items':data},ensure_ascii=False,indent=2),encoding='utf-8')
                self.message('BOM opgeslagen',str(len(data))+' artikelregels; interne kaders/onderdelen niet dubbel geteld.\n'+path)
            except Exception as e:W.QMessageBox.warning(self,'BOM niet opgeslagen',str(e))
        def reject(self):
            if self.busy:return
            super().reject()
        def build(self,save):
            if self.busy:return
            try:params=self.collect();resolve(params);settings.SetString('GroupPrefix',params['prefix'].strip())
            except Exception as e:W.QMessageBox.warning(self,'Controleer invoer',str(e));return
            self.busy=True;self.build_button.setEnabled(False);self.export_button.setEnabled(False);self.family.setEnabled(False);self.tabs.setEnabled(False)
            progress=W.QProgressDialog('Opbouwen...',None,0,0,self);progress.setCancelButton(None);progress.setMinimumDuration(0);progress.show()
            def update(text):
                progress.setLabelText(text);App.Console.PrintMessage('Airkan: '+text+'\n');W.QApplication.processEvents()
            try:
                if params['family'] in ('CM','BUY'):doc,root,objects,result=create_imported_step_document(params,update)
                else:doc,root,objects,result=create_document(params,self.refs.isChecked(),update)
                Gui.activeDocument().activeView().viewAxonometric();Gui.activeDocument().activeView().fitAll()
                self.last=(doc,root,objects,result)
                if save:
                    update('STEP exporteren, opnieuw inlezen en FCStd/JSON bewaren')
                    paths=export_document(doc,root,objects,result,self.output.text())
                    settings.SetString('OutputFolder',self.output.text());message='Opgeslagen:\n'+'\n'.join(paths.values())
                else:message='Model gebouwd in nieuw document; nog niet opgeslagen.'
                message+='\n\nBOM: 1 artikel. Fysieke solids: '+str(result['validation']['valid_solids'])
                if result['warnings']:message+='\n\nOpmerkingen:\n'+'\n'.join(result['warnings'])
                progress.close();self.message('Airkan - gereed',message)
            except Exception as e:
                trace=traceback.format_exc();App.Console.PrintError(trace+'\n');progress.close()
                W.QMessageBox.critical(self,'Airkan - bouw/export gestopt',str(e)+'\n\nBestaande bestanden zijn niet overschreven. Details in Report view.')
            finally:
                progress.close();self.busy=False;self.family.setEnabled(True);self.tabs.setEnabled(True);self.refresh()
    dialog=Dialog()
    if on_ready is not None:on_ready(dialog,W,C)
    execute=getattr(dialog,'exec',None) or dialog.exec_
    return execute()
