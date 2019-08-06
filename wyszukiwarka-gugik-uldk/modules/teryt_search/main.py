import os

from .res.resources import *

from PyQt5 import QtGui, QtWidgets, uic
from PyQt5.QtCore import pyqtSignal, Qt, QThread
from PyQt5.QtGui import QKeySequence, QPixmap

from qgis.core import QgsSettings, QgsNetworkAccessManager
from qgis.gui import QgsMessageBarItem
from urllib.request import urlopen
FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), "main_base.ui"
))

class UI(QtWidgets.QFrame, FORM_CLASS):

    icon_info_path = ':/plugins/csv_import/info.png'

    def __init__(self, target_layout, parent = None):
        super().__init__(parent)

        self.setupUi(self)
        
        self.label_info_full_id.setPixmap(QPixmap(self.icon_info_path))
        self.label_info_full_id.setToolTip(("Możesz pominąć wypełnianie powyższych pól\n"
            "i ręcznie wpisać kod TERYT działki."))
        self.label_info_sheet.setPixmap(QPixmap(self.icon_info_path))
        self.label_info_sheet.setToolTip(("W bazie danych może istnieć kilka działek o takim samym kodzie TERYT,\n"
            "każda na innym arkuszu.\n"
            "W takiej sytuacji możesz wybrać z tej listy działkę której szukasz."))
        target_layout.layout().addWidget(self)
    
class TerytSearch:

    def __init__(self, parent, target_layout, uldk_api, result_collector):
        self.parent = parent
        self.iface = parent.iface
        self.canvas = self.iface.mapCanvas()
        self.ui = UI(target_layout)

        self.uldk_api = uldk_api
        self.result_collector = result_collector

        self.message_bar_item = None
        self.__init_ui()

        self.uldk_search = uldk_api.ULDKSearchParcel("dzialka",
             ("geom_wkt", "wojewodztwo", "powiat", "gmina", "obreb","numer","teryt"))
        
    def search(self, teryt):
        self.ui.button_search.setEnabled(False)
        self.ui.button_search.setText("Wyszukiwanie...")

        self.uldk_search_worker = self.uldk_api.ULDKSearchWorker(self.uldk_search, [teryt])
        self.thread = QThread()
        self.uldk_search_worker.moveToThread(self.thread)
        
        self.uldk_search_worker.found.connect(self.__handle_found)
        self.uldk_search_worker.not_found.connect(self.__handle_not_found)
        self.uldk_search_worker.finished.connect(self.__handle_finished)
        self.uldk_search_worker.finished.connect(self.thread.quit)

        self.uldk_search_worker.finished.connect(self.uldk_search_worker.deleteLater)
        self.uldk_search_worker.finished.connect(self.thread.deleteLater)

        self.thread.started.connect(self.uldk_search_worker.search)
        self.thread.start()

    def is_plot_id_valid(cls, plot_id):

        if plot_id.endswith(".") or plot_id.startswith("."):
            return False
        if plot_id != plot_id.strip():
            return False
        
        return len(plot_id.split(".")) >=3

    def get_administratives(self, level, teryt = ""):
        search = self.uldk_api.ULDKSearchTeryt(level, ("nazwa", "teryt"))
        result = search.search(teryt)
        result = [ r.replace("|", " | ") for r in result ]
        return result

    def parse_combobox_current_text(self, source):
        text = source.currentText()
        return text.split(" | ")[1] if text else ""

    def fill_combobox_province(self):
        provinces = self.get_administratives("wojewodztwo")
        self.ui.combobox_province.clear()
        self.ui.combobox_province.addItems([""] + provinces)
    
    def fill_combobox_county(self, province_teryt):
        counties = self.get_administratives("powiat", province_teryt) if province_teryt else []
        self.ui.combobox_county.clear()
        self.ui.combobox_county.addItems([""] + counties)

    def fill_combobox_municipality(self, county_teryt):
        municipalities = self.get_administratives("gmina", county_teryt) if county_teryt else []
        self.ui.combobox_municipality.clear()
        self.ui.combobox_municipality.addItems([""] + municipalities)

    def fill_combobox_precinct(self, municipality_teryt):
        precincts = self.get_administratives("obreb", municipality_teryt) if municipality_teryt else []
        self.ui.combobox_precinct.clear()
        self.ui.combobox_precinct.addItems([""] + precincts)

    def fill_lineedit_full_teryt(self):
        current_plot_id = self.ui.lineedit_plot_id.text()
        current_precinct = self.ui.combobox_precinct.currentText()
        if current_plot_id and current_precinct:
            current_precinct = current_precinct.split(" | ")[1]
            self.ui.lineedit_full_teryt.setText(f"{current_precinct}.{current_plot_id}")

    def __init_ui(self):
        
        self.ui.combobox_province.currentIndexChanged.connect(
            lambda i: self.fill_combobox_county(
                    self.parse_combobox_current_text(self.ui.combobox_province)
                ) if i else self.ui.combobox_county.setCurrentIndex(0)
            )
        self.ui.combobox_county.currentIndexChanged.connect(
            lambda i: self.fill_combobox_municipality(
                    self.parse_combobox_current_text(self.ui.combobox_county)
                ) if i else self.ui.combobox_municipality.setCurrentIndex(0)
            )
        self.ui.combobox_municipality.currentIndexChanged.connect(
            lambda i: self.fill_combobox_precinct(
                    self.parse_combobox_current_text(self.ui.combobox_municipality)
                ) if i else self.ui.combobox_precinct.setCurrentIndex(0)
            )
        self.ui.combobox_precinct.currentTextChanged.connect(
            self.fill_lineedit_full_teryt
        )
        self.ui.lineedit_plot_id.textChanged.connect(
            self.fill_lineedit_full_teryt
        )
        self.ui.lineedit_full_teryt.textChanged.connect(
            lambda text: self.ui.button_search.setEnabled(
                self.is_plot_id_valid(text)
            )
        )
        self.ui.button_search.setShortcut(QKeySequence(Qt.Key_Return))
        self.ui.combobox_sheet.activated.connect(self.__search_from_sheet)
        self.ui.button_search.clicked.connect(lambda: self.search(self.ui.lineedit_full_teryt.text()))

        self.fill_combobox_province()

    def __search_from_sheet(self):
        self.ui.combobox_sheet.setEnabled(False)
        self.search(self.ui.combobox_sheet.currentData())

    def __handle_finished(self):
        self.ui.button_search.setEnabled(True)
        self.ui.button_search.setText("Szukaj")
        self.ui.button_search.setShortcut(QKeySequence(Qt.Key_Return))

    def __handle_found(self, uldk_response_rows):
        if len(uldk_response_rows) > 1:
            self.ui.combobox_sheet.setEnabled(True)
            self.ui.combobox_sheet.clear()
            for row in uldk_response_rows:
                row = row.split("|")
                sheet_name = row[-3]
                sheet_teryt = row[-1]

                self.ui.combobox_sheet.addItem(sheet_name, sheet_teryt)
            self.message_bar_item = QgsMessageBarItem("Wtyczka ULDK", "Wybrana działka znajduje się na różnych arkuszach map. Wybierz z listy jedną z nich.")
            self.iface.messageBar().pushWidget(self.message_bar_item)
        else:
            result = uldk_response_rows[0]
            
            added_feature = self.result_collector.update(result)
            self.result_collector.zoom_to_feature(added_feature)

            if self.message_bar_item:
                self.iface.messageBar().popWidget(self.message_bar_item)
                self.message_bar_item = None

            self.iface.messageBar().pushSuccess("Wtyczka ULDK", "Zaaktualizowano warstwę '{}'"
                                            .format(self.result_collector.layer.sourceName()))
    
    def __handle_not_found(self, teryt, exception):
        self.parent.iface.messageBar().pushCritical("Wtyczka ULDK","Nie znaleziono działki - odpowiedź serwera: '{}'".format(exception))



