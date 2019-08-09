import os
from urllib.request import urlopen

from PyQt5 import QtGui, QtWidgets, uic
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QKeySequence, QPixmap
from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsCoordinateTransformContext, QgsMapLayerProxyModel, QgsProject)
from qgis.gui import QgsMessageBarItem

from .res import resources
from .worker import PointLayerImportWorker


FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), "main_base.ui"
))

CRS_2180 = QgsCoordinateReferenceSystem()
CRS_2180.createFromSrid(2180)

def get_obiekty_form(count):
    form = "obiekt"
    count = count
    if count == 1:
        pass
    elif 2 <= count <= 4:
        form = "obiekty"
    elif 5 <= count <= 20:
        form = "obiektów"
    else:
        units = count % 10
        if units in (2,3,4):
            form = "obiekty"
    return form

class UI(QtWidgets.QFrame, FORM_CLASS):

    icon_info_path = ':/plugins/point_layer_import/info.png'

    def __init__(self, target_layout, parent = None):
        super().__init__(parent)

        self.setupUi(self)
        
        target_layout.layout().addWidget(self)

        self.layer_select.setFilters(QgsMapLayerProxyModel.PointLayer)

        self.label_info.setPixmap(QPixmap(self.icon_info_path))
        self.label_info.setToolTip((
            "Wyszukiwanie wielu obiektów może być czasochłonne. W tym czasie\n"
            "będziesz mógł korzystać z pozostałych funkcjonalności wtyczki,\n"
            "ale mogą one działać wolniej. Wyszukiwanie obiektów działa również\n"
            "po zamknięciu wtyczki."))
    

class PointLayerImport:

    def __init__(self, parent, target_layout, uldk_api):
        self.parent = parent
        self.iface = parent.iface
        self.canvas = self.iface.mapCanvas()
        self.ui = UI(target_layout)
        self.__init_ui()

        self.uldk_api = uldk_api
        
    def search(self):
        layer = self.ui.layer_select.currentLayer()
        self.source_features_count = layer.dataProvider().featureCount()
        target_layer_name = self.ui.text_edit_target_layer_name.text()

        selected_field_names = self.ui.combobox_fields_select.checkedItems()
        fields_to_copy = [ field for field in layer.dataProvider().fields()
                            if field.name() in selected_field_names ]

        self.__cleanup_before_search()

        self.worker = PointLayerImportWorker(self.uldk_api, layer, target_layer_name, fields_to_copy)
        self.thread = QThread()
        self.worker.moveToThread(self.thread) 
        self.worker.progressed.connect(self.__progressed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.__handle_finished)
        self.worker.interrupted.connect(self.__handle_interrupted)
        self.worker.interrupted.connect(self.thread.quit)
        self.thread.started.connect(self.worker.search)

        self.thread.start()

        count = self.source_features_count
        self.ui.label_status.setText(f"Trwa wyszukiwanie {count} {get_obiekty_form(count)}...")
    
    def __init_ui(self):
        self.ui.button_start.clicked.connect(self.search)
        self.ui.button_cancel.clicked.connect(self.__stop)
        self.__on_layer_changed(self.ui.layer_select.currentLayer())
        self.ui.layer_select.layerChanged.connect(self.__on_layer_changed)
        self.ui.label_status.setText("")
        self.ui.label_found_count.setText("")
        self.ui.label_not_found_count.setText("")

    def __on_layer_changed(self, layer):
        self.ui.combobox_fields_select.clear()
        self.ui.button_start.setEnabled(False)
        if layer:
            if layer.dataProvider().featureCount() == 0:
                self.parent.iface.messageBar().pushCritical(
                    "Wtyczka ULDK",f"Warstwa <b>{layer.sourceName()} nie zawiera żadnych obiektów.</b>")
                return
            self.ui.button_start.setEnabled(True)
            current_layer_name = layer.sourceName()
            suggested_target_layer_name = f"{current_layer_name} - Działki ULDK"
            self.ui.text_edit_target_layer_name.setText(suggested_target_layer_name)
            fields = layer.dataProvider().fields()
            self.ui.combobox_fields_select.addItems(map(lambda x: x.name(), fields))
            self.ui.button_start.setEnabled(True)
        else:
            self.ui.text_edit_target_layer_name.setText("")
            
    def __progressed(self, found, featues_omitted_count):
        if found:
            self.found_count += 1
        else:
            self.not_found_count += 1
        self.omitted_count += featues_omitted_count
        progressed_count = self.found_count + self.not_found_count + self.omitted_count
        self.ui.progress_bar.setValue(progressed_count/self.source_features_count*100)
        self.ui.label_status.setText("Przetworzono {} z {} obiektów".format(progressed_count, self.source_features_count))
        self.ui.label_found_count.setText("Znaleziono: {}".format(self.found_count))
        self.ui.label_not_found_count.setText("Nie znaleziono: {}".format(self.not_found_count))

    def __handle_finished(self, layer_found, layer_not_found):
        self.__cleanup_after_search()

        if layer_found.dataProvider().featureCount():
            QgsProject.instance().addMapLayer(layer_found)
        if layer_not_found.dataProvider().featureCount():
            QgsProject.instance().addMapLayer(layer_not_found)

        self.iface.messageBar().pushWidget(QgsMessageBarItem("Wtyczka ULDK",
            f"Import CSV: zakończono wyszukiwanie. Zapisano {self.found_count} {get_obiekty_form(self.found_count)} do warstwy <b>{self.ui.text_edit_target_layer_name.text()}</b>"))
        
    def __handle_interrupted(self, layer_found, layer_not_found):
        self.__cleanup_after_search()

        if layer_found.dataProvider().featureCount():
            QgsProject.instance().addMapLayer(layer_found)
        if layer_not_found.dataProvider().featureCount():
            QgsProject.instance().addMapLayer(layer_not_found)
        
    def __cleanup_after_search(self):
        self.__set_controls_enabled(True)
        self.ui.button_cancel.setText("Anuluj")
        self.ui.button_cancel.setEnabled(False)   
        self.ui.progress_bar.setValue(0)  

    def __cleanup_before_search(self):
        self.__set_controls_enabled(False)
        self.ui.button_cancel.setEnabled(True)
        self.ui.label_status.setText("")
        self.ui.label_found_count.setText("")
        self.ui.label_not_found_count.setText("")

        self.found_count = 0
        self.not_found_count = 0
        self.omitted_count = 0

    def __set_controls_enabled(self, enabled):
        self.ui.text_edit_target_layer_name.setEnabled(enabled)
        self.ui.button_start.setEnabled(enabled)
        self.ui.layer_select.setEnabled(enabled)

    def __stop(self):
        self.thread.requestInterruption()
        self.ui.button_cancel.setEnabled(False)
        self.ui.button_cancel.setText("Przerywanie...")