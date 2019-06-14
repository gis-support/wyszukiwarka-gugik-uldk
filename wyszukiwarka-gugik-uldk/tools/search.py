import csv
import os
import random
import threading
import time
from urllib.request import urlopen

from PyQt5.QtCore import QObject, QThread, QVariant, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem
from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsCoordinateTransformContext, QgsFeature, QgsField,
                       QgsFillSymbol, QgsGeometry, QgsPoint, QgsPointXY,
                       QgsProject, QgsVectorLayer)
from qgis.gui import QgsMapToolEmitPoint, QgsMessageBarItem

from .exceptions import RequestException
from .uldk_api import ULDKSearchPoint, ULDKSearchTeryt, ULDKSearchParcel

PLOTS_LAYER_DEFAULT_FIELDS = [
    QgsField("wojewodztwo", QVariant.String),
    QgsField("powiat", QVariant.String),
    QgsField("gmina", QVariant.String),
    QgsField("obreb", QVariant.String),
    QgsField("arkusz", QVariant.String),
    QgsField("nr_dzialki", QVariant.String),
    QgsField("teryt", QVariant.String),
    QgsField("pow_m2", QVariant.String),
]


def make_plots_layer(name, epsg, custom_properties, additional_fields = [], base_fields = PLOTS_LAYER_DEFAULT_FIELDS ):
    fields = base_fields + additional_fields
    layer = QgsVectorLayer("Polygon?crs=EPSG:{}".format(epsg), name, "memory")
    layer.startEditing()
    for prop, value in custom_properties.items():
        layer.setCustomProperty(prop, value)
    layer.dataProvider().addAttributes(fields)
    layer.commitChanges()
    return layer

class Listener:

    def __init__(self):
        pass

    def update(self, *args, **kwargs):
        pass

class Notifier:

    def __init__(self, listeners = None):
        self.listeners = listeners or set()
    
    def register(self, listener):
        """Rejestruje obiekt listener jako obserwator zdarzenia"""
        self.listeners.add(listener)

    def notify(self, *args, **kwargs):
        """Powiadamia wszystkich obserwatorów"""
        for listener in self.listeners:
            listener.update(*args, **kwargs)


class PointCRS:
    """Wrapper dla QgsPoint w celu zachowania CRS"""

    def __init__(self, point, crs):
        self.point = QgsPoint(point)
        self.crs = crs

    @classmethod
    def transform(cls, source, destination_crs):
        """Przelicza PointCRS do docelowego układu współrzędnych"""
        transformation = QgsCoordinateTransform(source.crs, destination_crs, QgsCoordinateTransformContext())
        point = transformation.transform(QgsPointXY(source.point))
        crs = destination_crs

        return cls(point, crs)


class PointGetter(QgsMapToolEmitPoint, Notifier):
    
    def __init__(self, parent, listeners = None):
        self.parent = parent
        self.iface = parent.iface
        self.canvas = parent.canvas
        super(QgsMapToolEmitPoint, self).__init__(self.canvas)
        super(Notifier, listeners)
        
        self.canvasClicked.connect(self.notify)

    def notify(self, point):
        
        point_crs = PointCRS(point, self.canvas.mapSettings().destinationCrs())
        super().notify(self, point_crs)

class PlotGetter(QgsMapToolEmitPoint, Notifier):
    def __init__(self, parent, listeners = None):
        self.parent = parent
        self.iface = parent.iface
        self.canvas = parent.canvas
        super(QgsMapToolEmitPoint, self).__init__(self.canvas)
        super(Notifier, listeners)
        self.canvasClicked.connect(self.notify)
        self.listeners = listeners or set()

    def notify(self, point):
        point_crs = PointCRS(point, self.canvas.mapSettings().destinationCrs())

        srid = point_crs.crs.postgisSrid()
        if srid != 2180:
            crs_2180 = QgsCoordinateReferenceSystem()
            crs_2180.createFromSrid(2180)
            point_crs = PointCRS.transform(point_crs, crs_2180)
            srid = 2180

        x = point_crs.point.x()
        y = point_crs.point.y()
        uldk_search = ULDKSearchPoint(
            "dzialka",
            ("geom_wkt", "wojewodztwo", "powiat", "gmina", "obreb","numer","teryt"),
            x,y, srid)
        try:
            result = uldk_search.search()[0]
        except RequestException as e:
            self.parent.iface.messageBar().pushCritical("Wtyczka ULDK","Nie znaleziono działki - odpowiedź serwera: '{}'".format(e))
            return

        super().notify(self, result)
    
    def toggle(self, enabled):
        if enabled:
            self.canvas.unsetMapTool(self)
        else:
            self.canvas.setMapTool(self)

class ChainedCombobox:
    """Wraper dla QT.Combobox przechowujący referencję do logicznie następnego QT.Combobox"""

    def __init__(self, level, c, next_chained = None, on_activated_action = None):
        self.level = level
        self.c = c
        self.next_chained = next_chained
        self.on_activated_action = on_activated_action or self.fill_next
        self.c.activated.connect(self.on_activated)

    def clear(self):
        self.c.clear()
        if self.next_chained:
            self.next_chained.clear()

    def on_activated(self):
        if self.c.currentText() != "":
            self.on_activated_action()
        else:
            self.next_chained.clear()

    def fill_next(self):
        if self.next_chained and self.c.currentText():
            self.__fill_combobox(
                self.next_chained,
                    SearchTerytForm.get_administratives(
                        self.next_chained.level,
                        self.c.currentText().split(" | ")[1]
                    )
            )

    def __fill_combobox(self, target, items):
        items = [""] + items
        target.clear()
        target.c.addItems(items)


class SearchForm(Notifier):

    def __init__(self, parent, combobox_sheet, listeners = None):
        self.parent = parent
        self.iface = parent.iface
        self.canvas = self.iface.mapCanvas()
        self.combobox_sheet = combobox_sheet
        self.combobox_sheet.activated.connect( self.__search_from_sheet )
        self.listeners = listeners or set()
        self.message_bar_item = None

    def register(self, listener):
        self.listeners.add(listener)

    def notify(self, search_result):
        for listener in self.listeners:
            listener.update(self, search_result)
        

    def search(self, uldk_search, clear_combobox_sheet = True):
        if clear_combobox_sheet:
            self.combobox_sheet.clear()
            self.combobox_sheet.setEnabled(False)
        try:
            result = uldk_search.search()
        except RequestException as e:
            self.parent.iface.messageBar().pushCritical("Wtyczka ULDK","Nie znaleziono działki - odpowiedź serwera: '{}'".format(e))
            return

        if len(result) > 1:
            self.combobox_sheet.setEnabled(True)
            self.combobox_sheet.clear()
            self.combobox_sheet.addItems( result )
            self.message_bar_item = QgsMessageBarItem("Wtyczka ULDK", "Wybrana działka znajduje się na różnych arkuszach map. Wybierz z listy jedną z nich.")
            self.iface.messageBar().pushWidget(self.message_bar_item)
        else:
            uldk_search = ULDKSearchParcel("dzialka",
             ("geom_wkt", "wojewodztwo", "powiat", "gmina", "obreb","numer","teryt"), result[0])
            result = uldk_search.search()

            if self.message_bar_item:
                self.iface.messageBar().popWidget(self.message_bar_item)
                self.message_bar_item = None
            
            self.notify(result[0])

    def __search_from_sheet(self):
        """Pobiera z Comboboxa arkuszy wybrany teryt i na jego podstawie przekazuje dalej wyszukiwanie działki"""
        teryt = self.combobox_sheet.currentText()
        if teryt:
            uldk_search = ULDKSearchParcel("dzialka", ("teryt"), teryt)
            self.search(uldk_search, False)
    


class SearchTerytForm(SearchForm):

    def __init__(self, parent, button_search,
        combobox_province, combobox_county, combobox_municipality, combobox_precinct, 
        lineedit_teryt, lineedit_full_id):

        self.parent = parent

        self.combobox_precinct = ChainedCombobox( "obreb", combobox_precinct,
                    on_activated_action = lambda : self.lineedit_full_id.setText( self.combobox_precinct.c.currentText().split(" | ")[-1] ) )
        self.combobox_municipality = ChainedCombobox( "gmina", combobox_municipality, self.combobox_precinct )
        self.combobox_county = ChainedCombobox( "powiat", combobox_county, self.combobox_municipality )
        self.combobox_province = ChainedCombobox( "wojewodztwo", combobox_province, self.combobox_county )
        try:
            wojewodztwa = self.get_administratives("wojewodztwo")
       
            self.combobox_province.c.addItems([""] + wojewodztwa)
            
            self.lineedit_teryt = lineedit_teryt
            self.lineedit_full_id = lineedit_full_id

            self.button_search = button_search

            self.lineedit_teryt.textChanged.connect( lambda x : self.lineedit_full_id.setText( ".".join(filter(lambda x : x != "", [self.combobox_precinct.c.currentText().split(" | ")[-1] , x]))))
            self.lineedit_full_id.textChanged.connect( lambda x : self.button_search.setEnabled( self.is_plot_id_valid(x) ) )
            self.button_search.clicked.connect( lambda : self.search(self.lineedit_full_id.text()))
        except RequestException as e:   
            self.parent.iface.messageBar().pushCritical("Wtyczka ULDK","Błąd pobierania listy jednostek - odpowiedź serwera: '{}'".format(e))

    def search(self, teryt):
        uldk_search = ULDKSearchParcel("dzialka", ("teryt"), teryt)
        self.parent.search(uldk_search)
        
    def __connect(self):
        
        self.combobox_precinct.c.activated.connect( lambda : self.lineedit_full_id.setText( self.combobox_precinct.c.currentText().split(" | ")[1]))
        
    @classmethod
    def get_administratives(cls, level, teryt = ""):
        search = ULDKSearchTeryt(level, ("nazwa", "teryt"), teryt)
        result = search.search()
        result = [ r.replace("|", " | ") for r in result ]
        return result

    @classmethod
    def is_plot_id_valid(cls, plot_id):

        if plot_id.endswith(".") or plot_id.startswith("."):
            return False
        if plot_id != plot_id.strip():
            return False
        
        return len(plot_id.split(".")) >=3


class SearchPointForm(Listener):

    def __init__(self, parent, button_search, button_get_from_map,  line_edit_x, line_edit_y):

        super().__init__()

        self.parent = parent
        self.iface = parent.iface
        self.canvas = parent.canvas

        self.line_edit_x = line_edit_x
        self.line_edit_y = line_edit_y
        self.button_get_from_map = button_get_from_map

        self.point_crs = None
        
        self.button_search = button_search
        self.button_search.clicked.connect( self.search )

    def update(self, notifier, point_crs):
        self.point_crs = point_crs
        self.__fill_line_edits()

    def __fill_line_edits(self):
        if self.point_crs:
            self.line_edit_x.setText(str( self.point_crs.point.x() ))
            self.line_edit_y.setText(str( self.point_crs.point.y() ))
            self.button_search.setEnabled(True)

    def recalculate_xy(self, destination_crs):
        """Przelicza przechowywany PointCRS do docelowego układu współrzędnych"""
        if self.point_crs:
            self.point_crs = PointCRS.transform(self.point_crs, destination_crs)
            self.__fill_line_edits()

    def search(self):
        if self.point_crs:
            x = self.point_crs.point.x()
            y = self.point_crs.point.y()
            srid = self.point_crs.crs.postgisSrid()
        uldk_search = ULDKSearchPoint("dzialka", ("teryt"), x, y, srid)
        self.parent.search(uldk_search)

class Worker(QObject):

    found = pyqtSignal(str)
    not_found = pyqtSignal(str, str)
    progressed = pyqtSignal(int, int, int)
    finished = pyqtSignal()
    interrupted = pyqtSignal()
    def __init__(self, teryt_ids):
        super().__init__()  
        self.teryt_ids = teryt_ids

    @pyqtSlot()
    def request(self):
        count = len(self.teryt_ids)
        found_count = 0
        not_found_count = 0
        for i, teryt in enumerate(self.teryt_ids, start=1):
            if QThread.currentThread().isInterruptionRequested():
                self.interrupted.emit()
                return

            uldk_search = ULDKSearchParcel("dzialka",
                ("geom_wkt", "wojewodztwo", "powiat", "gmina", "obreb","numer","teryt"), teryt)
            try:
                result = uldk_search.search()[0]
                found_count += 1
                self.found.emit(result)
            except Exception as e:  
                not_found_count += 1
                self.not_found.emit(teryt, str(e))
            self.progressed.emit(count, found_count, not_found_count)
        self.finished.emit()

class ImportCSVForm(SearchForm):
    
    def __init__(self, parent, combobox_teryt_column, file_select,
                 layer_name, button_start, button_cancel, progress_bar,
                 table_errors, label_status, label_found_count, label_not_found_count):
        self.parent = parent
        self.iface = parent.iface
        
        self.combobox_teryt_column = combobox_teryt_column
        self.file_select = file_select
        self.layer_name = layer_name
        self.button_start = button_start
        self.button_cancel = button_cancel
        self.progress_bar = progress_bar
        self.file_select.fileChanged.connect(self.on_file_changed)
        self.table_errors = table_errors
        self.label_status = label_status
        self.label_found_count = label_found_count
        self.label_not_found_count = label_not_found_count

        self.file_path = None

        self.__init_gui()

    def __init_gui(self):
        self.button_start.clicked.connect(self.start_import)
        self.label_status.setText("")
        self.label_found_count.setText("")
        self.label_not_found_count.setText("")

        self.__init_table()

    def on_file_changed(self, path):
        if path:
            self.button_start.setEnabled(True)
        self.file_path = path
        self.fill_column_select()
        self.layer_name.setText(os.path.splitext(os.path.relpath(path))[0])


    def fill_column_select(self):
        with open(self.file_path) as f:
            csv_read = csv.DictReader(f)
            columns = csv_read.fieldnames
        self.combobox_teryt_column.clear()
        self.combobox_teryt_column.addItems(columns)
    
    def start_import(self):
        def found(result):
            feature = ResultCollector.uldk_response_to_qgs_feature(result)
            features.append(feature)

        def not_found(teryt, error):
            row = self.table_errors.rowCount()
            self.table_errors.insertRow(row)
            self.table_errors.setItem(row, 0, QTableWidgetItem(teryt))
            self.table_errors.setItem(row, 1, QTableWidgetItem(error))

        def progressed(count, found_count, not_found_count):
            progressed_count = found_count + not_found_count
            self.progress_bar.setValue(progressed_count/count*100)
            self.label_status.setText("Przetworzono {} z {} obiektów".format(progressed_count, count))
            self.label_found_count.setText("Znaleziono: {}".format(found_count))
            self.label_not_found_count.setText("Nie znaleziono: {}".format(not_found_count))

        def finished():
            if features:
                result_collector.add_features(features)
            self.iface.messageBar().pushWidget(QgsMessageBarItem("Wtyczka ULDK",
                                        "Import CSV: zakończono wyszukiwanie"))
            cleanup()

        def interrupted():
            if features:
                result_collector.add_features(features)
            cleanup()

        def cleanup():
            self.worker.deleteLater()
            self.button_cancel.setText("Anuluj")
            self.button_cancel.setEnabled(False)
            self.set_controls_enabled(True)   
            self.progress_bar.setValue(0)   

        def stop():
            self.thread.requestInterruption()
            self.button_cancel.setEnabled(False)
            self.button_cancel.setText("Przerywanie...")

        self.table_errors.setRowCount(0)
        self.label_status.setText("")
        self.label_found_count.setText("")
        self.label_not_found_count.setText("")
        layer_name = self.layer_name.text()
        layer = make_plots_layer(layer_name, 2180, {"ULDK": "csv '{}'".format(layer_name)})
        result_collector = ResultCollectorMultiple(self.parent, layer)

        features = []

        teryt_ids = []
        with open(self.file_path) as f:
            csv_read = csv.DictReader(f)
            teryt_column = self.combobox_teryt_column.currentText()
            for row in csv_read:
                teryt = row[teryt_column]
                teryt_ids.append(teryt)
        
        self.worker = Worker(teryt_ids)
        self.thread = QThread()
        self.worker.moveToThread(self.thread) 
        self.worker.found.connect(found)
        self.worker.not_found.connect(not_found)
        self.worker.progressed.connect(progressed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(finished)
        self.worker.interrupted.connect(interrupted)
        self.worker.interrupted.connect(self.thread.quit)
        self.thread.started.connect(self.worker.request)
        self.set_controls_enabled(False)
        self.button_cancel.setEnabled(True)
        self.button_cancel.clicked.connect(stop)
        self.thread.start()
        self.label_status.setText("Trwa wyszukiwanie {} obiektów...".format(len(teryt_ids)))

    def set_controls_enabled(self, enabled):
        self.layer_name.setEnabled(enabled)
        self.button_start.setEnabled(enabled)
        self.file_select.setEnabled(enabled)
        self.combobox_teryt_column.setEnabled(enabled)

    def __init_table(self):
        table = self.table_errors
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(("TERYT", "Treść błędu"))
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        teryt_column_size = table.width()/3
        header.resizeSection(0, teryt_column_size)


class ResultCollector(Listener):

    @classmethod
    def uldk_response_to_qgs_feature(cls, response_row):
        def get_sheet(teryt):
            split = teryt.split(".")
            if len(split) == 4:
                return split[2]
            else:
                return None

        geom_wkt, province, county, municipality, precinct, plot_id, teryt = \
            response_row.split("|")

        sheet = get_sheet(teryt)
        
        ewkt = geom_wkt.split(";")
        if len(ewkt) == 2:
            geom_wkt = ewkt[1]

        geometry = QgsGeometry.fromWkt(geom_wkt)
        area = geometry.area()

        if not geometry.isGeosValid():
            raise InvalidGeomException("Nie udało się przetworzyć geometrii działki")

        feature = QgsFeature()
        feature.setGeometry(geometry)
        feature.setAttributes(
            [province, county, municipality, precinct, sheet, plot_id, teryt, area]
            )

        return feature

    def __init__(self, parent, layer_factory):
        super().__init__()
        self.parent = parent
        self.iface = parent.iface
        self.canvas = parent.canvas
        self.layer_factory = layer_factory
        self.layer = None

    def __create_layer(self):
        layer = self.layer_factory()
        layer.willBeDeleted.connect(self.__delete_layer)
        self.layer = layer

    def __delete_layer(self):
        self.layer = None

    def update(self, notifier, result):
        if self.layer is None:
            self.__create_layer()
            QgsProject.instance().addMapLayer(self.layer)
        feature = self.uldk_response_to_qgs_feature(result)
        added_feature = self.__add_feature(feature)
        self.layer.updateExtents()
        self.iface.messageBar().pushSuccess("Wtyczka ULDK", "Zaaktualizowano warstwę '{}'".format(self.layer.sourceName()))
        if isinstance(notifier, SearchForm):
            self.canvas.setExtent(added_feature.geometry().boundingBox())

    def __add_feature(self, feature):
        
        self.layer.startEditing()
        self.layer.dataProvider().addFeature(feature)
        self.layer.commitChanges()

        return feature


class ResultCollectorMultiple:

    def __init__(self, parent, layer):
        self.parent = parent
        self.iface = parent.iface
        self.canvas = parent.canvas
        self.layer = layer
    
    def add_features(self, features):
        self.layer.startEditing()
        self.layer.dataProvider().addFeatures(features)
        self.layer.commitChanges()
        self.layer.updateExtents()
        QgsProject.instance().addMapLayer(self.layer)
