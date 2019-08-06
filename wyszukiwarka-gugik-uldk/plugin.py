import json
import locale
import operator
import os
import sys
import time
from collections import OrderedDict
from urllib.request import urlopen

from PyQt5.QtCore import (QCoreApplication, QSettings, Qt, QTranslator,
                          QVariant, qVersion)
from PyQt5.QtGui import *
from PyQt5.QtWidgets import QAction, QShortcut
from qgis.core import *
from qgis.gui import QgsMessageBar

from .modules.csv_import.main import CSVImport
from .modules.map_point_search.main import MapPointSearch
from .modules.teryt_search.main import TerytSearch
from .plugin_dockwidget import wyszukiwarkaDzialekDockWidget
from .resources import resources
from .tools import uldk_api
from .tools.resultcollector import (ResultCollectorMultiple,
                                    ResultCollectorSingle)

PLUGIN_NAME = "Wyszukiwarka działek ewidencyjnych (GUGiK ULDK)"

class Plugin:
    
    folder = os.path.dirname(os.path.abspath(__file__))
    
    path_logo = ':/plugins/plugin/logo_thumb.png'

    def __init__(self, iface):

        self.iface = iface
        self.canvas = self.iface.mapCanvas()
        self.plugin_dir = os.path.dirname(__file__)
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'wyszukiwarkaDzialek_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)

            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(self.translator)

        self.dockwidget = None
        self.toolbar_buttons = {}
        self.menu = self.tr(PLUGIN_NAME)
        self.toolbar = self.iface.addToolBar(PLUGIN_NAME)
        self.toolbar.setObjectName(PLUGIN_NAME)

        self.pluginIsActive = False

        self.teryt_search_result_collector = ResultCollectorSingle(self)
        self.map_point_search_result_collector = self.teryt_search_result_collector
        
        self.project = QgsProject.instance()
        self.wms_layer = None
        self.module_csv_import = None
        self.module_teryt_search = None
        self.module_map_point_search = MapPointSearch(self, uldk_api, self.teryt_search_result_collector)

    def tr(self, message):
        return QCoreApplication.translate('wyszukiwarkaDzialek', message)


    def add_action(
        self,
        name,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None,
        checkable=False):

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)
        action.setCheckable(checkable)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.toolbar_buttons[name] = action

        return action

    def initGui(self):

        base_directory = ':/plugins/plugin/'
        self.add_action(
            "main",
            os.path.join(base_directory, "logo_thumb.png"),
            text=self.tr(PLUGIN_NAME),
            callback=self.run,
            parent=self.iface.mainWindow())

        action_map_point_search = self.add_action(
            "plot_getter",
            self.module_map_point_search.get_icon(),
            text = "Identifykacja ULDK",
            callback = lambda state : self.module_map_point_search.toggle(not state),
            parent = self.iface.mainWindow(),
            checkable = True
        )    
        self.module_map_point_search.deactivated.connect(lambda: action_map_point_search.setChecked(False))

    def onClosePlugin(self):
        self.dockwidget.closingPlugin.disconnect(self.onClosePlugin)
        self.pluginIsActive = False

    def unload(self):
        for action in self.toolbar_buttons.values():
            self.iface.removePluginMenu(
                self.tr(PLUGIN_NAME),
                action)
            self.iface.removeToolBarIcon(action)
        del self.toolbar

    def run(self):
        try:
            urlopen("http://google.com")
        except:
            self.iface.messageBar().pushWarning("Wtyczka ULDK", "Brak połączenia z Internetem!")

        if not self.pluginIsActive:
            self.pluginIsActive = True
            if self.dockwidget == None:
                self.dockwidget = wyszukiwarkaDzialekDockWidget()

            self.dockwidget.closingPlugin.connect(self.onClosePlugin)
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dockwidget)
            self.dockwidget.show()

            if self.module_teryt_search is None:
                self.module_teryt_search = TerytSearch(self,
                    self.dockwidget.tab_teryt_search_layout,
                    uldk_api, 
                    self.teryt_search_result_collector)

            if self.module_csv_import is None:
                result_collector_factory = lambda parent, target_layer: ResultCollectorMultiple(self, target_layer)
                self.module_csv_import = CSVImport(self,
                    self.dockwidget.tab_import_csv_layout, 
                    uldk_api, 
                    result_collector_factory,
                    ResultCollectorMultiple.default_layer_factory)

        self.dockwidget.button_wms.clicked.connect(lambda : self.addWMS())
        self.project.layersRemoved.connect( lambda layers : self.dockwidget.button_wms.setEnabled(True) if filter(lambda layer: layer.customProperty("ULDK") == "wms_layer", layers) else lambda : None)
    def addWMS(self):

        url = ("contextualWMSLegend=0&"
                "crs=EPSG:2180&"
                "dpiMode=7&"
                "featureCount=10&"
                "format=image/png&"
                "layers=dzialki&layers=numery_dzialek&"
                "styles=&styles=&"
                "version=1.1.1&"
                "url=http://integracja.gugik.gov.pl/cgi-bin/KrajowaIntegracjaEwidencjiGruntow")
        layer = QgsRasterLayer(url, 'Działki ULDK', 'wms')
        layer.setCustomProperty("ULDK", "wms_layer")
        self.wms_layer = layer
        self.project.addMapLayer(self.wms_layer)
        self.dockwidget.button_wms.setEnabled(False)
