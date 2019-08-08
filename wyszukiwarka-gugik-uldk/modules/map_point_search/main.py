from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtGui import QCursor
from qgis.core import (QgsCoordinateTransform, QgsCoordinateTransformContext,
                       QgsFeature, QgsPoint, QgsCoordinateReferenceSystem)
from qgis.gui import QgsMapToolEmitPoint

from .res import resources

CRS_2180 = QgsCoordinateReferenceSystem()
CRS_2180.createFromSrid(2180)

class MapPointSearch(QgsMapToolEmitPoint):

    # search_started = pyqtSignal()
    # found = pyqtSignal(QgsFeature)
    # not_found = pyqtSignal(Exception)
    # search_finished = pyqtSignal()

    def __init__(self, parent, uldk_api, result_collector):
        self.parent = parent
        self.iface = parent.iface
        self.canvas = parent.canvas
        super(QgsMapToolEmitPoint, self).__init__(self.canvas)
        self.canvasClicked.connect(self.__search)

        self.uldk_api = uldk_api
        self.result_collector = result_collector

        self.search_in_progress = False

        self.icon_path = ':/plugins/map_point_search/intersect.png'

    def __search(self, point):
        if self.search_in_progress:
            return

        canvas_crs = self.canvas.mapSettings().destinationCrs()
        if canvas_crs != CRS_2180:
            transformation = QgsCoordinateTransform(canvas_crs, CRS_2180, QgsCoordinateTransformContext()) 
            point = transformation.transform(point)

        x = point.x()
        y = point.y()
        srid = 2180

        uldk_search = self.uldk_api.ULDKSearchPoint(
            "dzialka",
            ("geom_wkt", "wojewodztwo", "powiat", "gmina", "obreb","numer","teryt")
        )
        uldk_point = self.uldk_api.ULDKPoint(x,y,srid)
        worker = self.uldk_api.ULDKSearchPointWorker(uldk_search, (uldk_point,))
        self.worker = worker
        thread= QThread()
        self.thread = thread
        worker.moveToThread(thread)
        thread.started.connect(self.__on_search_started)
        thread.started.connect(worker.search)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(thread.deleteLater)
        worker.finished.connect(thread.quit)
        worker.finished.connect(self.__handle_finished)
        worker.found.connect(self.__handle_found)
        worker.not_found.connect(self.__handle_not_found)

        thread.start()

    def __handle_found(self, uldk_response_row):
        added_feature = self.result_collector.update(uldk_response_row)
        # self.found.emit(added_feature)

    def __handle_not_found(self, uldk_point, exception):
        self.parent.iface.messageBar().pushCritical(
            "Wtyczka ULDK",f"Nie znaleziono działki - odpowiedź serwera: '{str(exception)}'")
        # self.not_found.emit(exception)

    def __handle_finished(self):
        self.search_in_progress = False
        self.setCursor(Qt.CrossCursor)
        # self.search_finished.emit()

    def __on_search_started(self):
        self.search_in_progress = True
        self.setCursor(Qt.WaitCursor)
        # self.search_started.emit()

    def toggle(self, enabled):
        if enabled:
            self.canvas.unsetMapTool(self)
        else:
            self.canvas.setMapTool(self)

    def get_icon(self):
        return self.icon_path
