import random

from PyQt5.QtCore import QVariant
from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsCoordinateTransformContext, QgsFeature, QgsField,
                       QgsFillSymbol, QgsGeometry, QgsPoint, QgsPointXY,
                       QgsProject, QgsVectorLayer)
from qgis.gui import QgsMapToolEmitPoint, QgsMessageBarItem

from .exceptions import RequestException
from .uldk_api import ULDKSearchPoint, ULDKSearchTeryt


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
        x = point_crs.point.x()
        y = point_crs.point.y()
        srid = point_crs.crs.postgisSrid()
        uldk_search = ULDKSearchPoint(
            "dzialka",
            ("geom_wkt", "wojewodztwo", "powiat", "gmina", "obreb","numer","teryt"),
            x,y, srid)
        result = uldk_search.search()[0]
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
            try:
                self.__fill_combobox(
                    self.next_chained,
                        SearchTerytForm.get_administratives(
                            self.next_chained.level,
                            self.c.currentText().split(" | ")[1]
                        )
                )
            except RequestException as e:
                self.parent.iface.messageBar().pushCritical("Wtyczka ULDK","Błąd pobierania listy jednostek - odpowiedź serwera: '{}'".format(e))

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
            uldk_search = ULDKSearchTeryt("dzialka",
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
            uldk_search = ULDKSearchTeryt("dzialka", ("teryt"), teryt)
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
        except RequestException as e:   
                self.parent.iface.messageBar().pushCritical("Wtyczka ULDK","Błąd pobierania listy jednostek - odpowiedź serwera: '{}'".format(e))
        self.combobox_province.c.addItems([""] + wojewodztwa)
        
        self.lineedit_teryt = lineedit_teryt
        self.lineedit_full_id = lineedit_full_id

        self.button_search = button_search

        self.lineedit_teryt.textChanged.connect( lambda x : self.lineedit_full_id.setText( ".".join(filter(lambda x : x != "", [self.combobox_precinct.c.currentText().split(" | ")[-1] , x]))))
        self.lineedit_full_id.textChanged.connect( lambda x : self.button_search.setEnabled( self.is_plot_id_valid(x) ) )
        self.button_search.clicked.connect( lambda : self.search(self.lineedit_full_id.text()))

    def search(self, teryt):
        uldk_search = ULDKSearchTeryt("dzialka", ("teryt"), teryt)
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


class ResultCollector(Listener):

    def __init__(self, parent, layer_name, layer_epsg):
        super().__init__()
        self.parent = parent
        self.iface = parent.iface
        self.canvas = parent.canvas
        self.layer_name = layer_name
        self.layer_epsg = layer_epsg
        self.layer = None

    def __create_layer(self):
        layer = QgsVectorLayer("Polygon?crs=EPSG:" + str(self.layer_epsg), self.layer_name, "memory")
        layer.willBeDeleted.connect( self.__delete_layer)
        layer.startEditing()
        layer.setCustomProperty("ULDK", "plots_layer")
        layer.dataProvider().addAttributes([
            QgsField("wojewodztwo", QVariant.String),
            QgsField("powiat", QVariant.String),
            QgsField("gmina", QVariant.String),
            QgsField("obreb", QVariant.String),
            QgsField("arkusz", QVariant.String),
            QgsField("nr_dzialki", QVariant.String),
            QgsField("teryt", QVariant.String),
            QgsField("pow_m2", QVariant.String),
        ])
        layer.commitChanges()
        self.layer = layer

    def __delete_layer(self):
        self.layer = None

    def update(self, notifier, result):
        if self.layer is None:
            self.__create_layer()
            QgsProject.instance().addMapLayer(self.layer)
        self.__add_feature(result)
        

    def __add_feature(self, result):
        
        def get_sheet(teryt):
            split = teryt.split(".")
            if len(split) == 4:
                return split[2]
            else:
                return None

        geom_wkt, province, county, municipality, precinct, plot_id, teryt = \
            result.split("|")

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
        self.layer.startEditing()
        self.layer.dataProvider().addFeature(feature)
        self.layer.commitChanges()
        self.layer.updateExtents()
        self.iface.messageBar().pushSuccess("Wtyczka ULDK", "Zaaktualizowano warstwę '{}'".format(self.layer_name))

