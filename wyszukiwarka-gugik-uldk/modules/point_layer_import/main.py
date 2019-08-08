import os
from urllib.request import urlopen

from PyQt5 import QtGui, QtWidgets, uic
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QKeySequence, QPixmap
from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsCoordinateTransformContext, QgsMapLayerProxyModel,
                       QgsNetworkAccessManager, QgsSettings)
from qgis.gui import QgsMessageBarItem

from .res import resources


FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), "main_base.ui"
))

CRS_2180 = QgsCoordinateReferenceSystem()
CRS_2180.createFromSrid(2180)

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

    def __init__(self, parent, target_layout, uldk_api, result_collector_factory, layer_factory):
        self.parent = parent
        self.iface = parent.iface
        self.canvas = self.iface.mapCanvas()
        self.ui = UI(target_layout)
        self.__init_ui()

        self.uldk_api = uldk_api
        self.result_collector_factory = result_collector_factory
        self.layer_factory = layer_factory
        
    def search(self):
        layer = self.ui.layer_select.currentLayer()
        layer_crs = layer.sourceCrs()
        if layer_crs != CRS_2180:
            transformation = (QgsCoordinateTransform(layer_crs, CRS_2180, QgsCoordinateTransformContext()))
        else: transformation = None

        ULDKPoint = self.uldk_api.ULDKPoint

        uldk_points = []
        self.source_features_count = 0
        for feature in layer.getFeatures():
            point = feature.geometry().asPoint()
            if transformation:
                point = transformation.transform(point)
            uldk_point = ULDKPoint(point.x(), point.y(), 2180)
            uldk_points.append(uldk_point)
            self.source_features_count += 1
        
        uldk_search = self.uldk_api.ULDKSearchPoint(
            "dzialka",
            ("geom_wkt", "wojewodztwo", "powiat", "gmina", "obreb","numer","teryt")
        )

        layer_name = self.ui.text_edit_target_layer_name.text()
        layer = self.layer_factory(
            name = layer_name, custom_properties = {"ULDK": layer_name})

        self.result_collector = self.result_collector_factory(self.parent, layer)
        
        self.__cleanup_before_search()
        self.worker = self.uldk_api.ULDKSearchPointWorker(uldk_search, uldk_points)
        self.thread = QThread()
        self.worker.moveToThread(self.thread) 
        self.worker.found.connect(self.__handle_found)
        self.worker.found.connect(self.__progressed)
        self.worker.not_found.connect(self.__handle_not_found)
        self.worker.not_found.connect(self.__progressed)
        self.worker.found.connect(self.__progressed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.__handle_finished)
        self.worker.interrupted.connect(self.__handle_interrupted)
        self.worker.interrupted.connect(self.thread.quit)
        self.thread.started.connect(self.worker.search)

        self.thread.start()

        self.ui.label_status.setText(f"Trwa wyszukiwanie {self.source_features_count} obiektów...")
    
    def __init_ui(self):
        self.ui.button_start.clicked.connect(self.search)
        self.ui.button_cancel.clicked.connect(self.__stop)
        self.__on_layer_changed(self.ui.layer_select.currentLayer())
        self.ui.layer_select.layerChanged.connect(self.__on_layer_changed)
        self.ui.label_status.setText("")
        self.ui.label_found_count.setText("")
        self.ui.label_not_found_count.setText("")

    def __on_layer_changed(self, layer):
        if layer:
            self.ui.button_start.setEnabled(True)
            current_layer_name = layer.sourceName()
            suggested_target_layer_name = f"{current_layer_name} - Działki ULDK"
            self.ui.text_edit_target_layer_name.setText(suggested_target_layer_name)

    def __handle_found(self, uldk_response_row):
        self.uldk_received_rows.append(uldk_response_row)
        self.found_count += 1

    def __handle_not_found(self, uldk_point, exception):
        self.not_found_count += 1

    def __progressed(self):
        found_count = self.found_count
        not_found_count = self.not_found_count
        progressed_count = found_count + not_found_count
        self.ui.progress_bar.setValue(progressed_count/self.source_features_count*100)
        self.ui.label_status.setText("Przetworzono {} z {} obiektów".format(progressed_count, self.source_features_count))
        self.ui.label_found_count.setText("Znaleziono: {}".format(found_count))
        self.ui.label_not_found_count.setText("Nie znaleziono: {}".format(not_found_count))

    def __handle_finished(self):
        self.__collect_received_rows()
        form = "obiekt"
        found_count = self.found_count
        if found_count == 1:
            pass
        elif 2 <= found_count <= 4:
            form = "obiekty"
        elif 5 <= found_count <= 15:
            form = "obiektów"
        else:
            units = found_count % 10
            if units in (2,3,4):
                form = "obiekty"

        self.iface.messageBar().pushWidget(QgsMessageBarItem("Wtyczka ULDK",
            f"Import warstwy: zakończono wyszukiwanie. Zapisano {found_count} {form} do warstwy <b>{self.ui.text_edit_target_layer_name.text()}</b>"))
        self.__cleanup_after_search()

    def __handle_interrupted(self):
        self.__collect_received_rows()
        self.__cleanup_after_search()

    def __collect_received_rows(self):
        if self.uldk_received_rows:
            self.result_collector.update(self.uldk_received_rows)

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
        self.uldk_received_rows = []

    def __set_controls_enabled(self, enabled):
        self.ui.text_edit_target_layer_name.setEnabled(enabled)
        self.ui.button_start.setEnabled(enabled)
        self.ui.layer_select.setEnabled(enabled)

    def __stop(self):
        self.thread.requestInterruption()
        self.ui.button_cancel.setEnabled(False)
        self.ui.button_cancel.setText("Przerywanie...")