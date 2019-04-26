# -*- coding: utf-8 -*-
"""
/***************************************************************************
 wyszukiwarkaDzialek
                                 A QGIS plugin
 desc
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2018-07-05
        git sha              : $Format:%H$
        copyright            : (C) 2018 by umcs
        email                : mail@mail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
import json
import locale
import operator
import os.path
import time
from collections import OrderedDict
from urllib.request import urlopen

import requests
from PyQt5.QtCore import (QCoreApplication, QSettings, Qt, QTranslator,
                          QVariant, qVersion)
from PyQt5.QtGui import *
from PyQt5.QtWidgets import QAction
from qgis.core import *
from qgis.gui import QgsMessageBar

# Import the code for the DockWidget
from .plugin_dockwidget import wyszukiwarkaDzialekDockWidget
from .resources import *
from .tools.exceptions import *
from .tools.search import (PointGetter, SearchForm, SearchPointForm,
                           SearchTerytForm, ResultCollector, PlotGetter)
from .tools.uldk_api import ULDKSearchPoint, ULDKSearchTeryt


class wyszukiwarkaDzialek:
    
    folder = os.path.dirname(os.path.abspath(__file__))
    
    path_logo = ':/plugins/plugin/logo_thumb.png'

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        self.canvas = self.iface.mapCanvas()
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)

        # initialize locale
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

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&Wyszukiwarka działek ewidencyjnych (GUGiK ULDK) - beta')
        self.toolbar = self.iface.addToolBar(u'Wyszukiwarka działek ewidencyjnych (GUGiK ULDK) - beta')
        self.toolbar.setObjectName(u'Wyszukiwarka działek ewidencyjnych (GUGiK ULDK) - beta')

        #print "** INITIALIZING wyszukiwarkaDzialek"

        self.pluginIsActive = False
        self.dockwidget = None
        self.point_getter = None
        self.plot_getter = PlotGetter(self)
        self.result_collector = ResultCollector(self, "Wyniki wyszukiwania ULDK", 2180)
        self.plot_getter.register(self.result_collector)
        self.search_form = None
        self.search_point_form = None
        self.project = QgsProject.instance()
        self.wms_layer = None

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('wyszukiwarkaDzialek', message)


    def add_action(
        self,
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
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

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

        self.actions.append(action)

        return action


    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        base_directory = ':/plugins/plugin/'
        self.add_action(
            os.path.join(base_directory, "logo_thumb.png"),
            text=self.tr(u'Wyszukiwarka działek ewidencyjnych (GUGiK ULDK) - beta'),
            callback=self.run,
            parent=self.iface.mainWindow())
        
        self.add_action(
            os.path.join(base_directory, "intersect.png"),
            text = "Identifykacja ULDK",
            callback = lambda state : self.plot_getter.toggle(not state),
            parent = self.iface.mainWindow(),
            checkable = True
        )    
    #--------------------------------------------------------------------------

    def onClosePlugin(self):
        """Cleanup necessary items here when plugin dockwidget is closed"""

        #print "** CLOSING wyszukiwarkaDzialek"

        # disconnects
        self.dockwidget.closingPlugin.disconnect(self.onClosePlugin)
        
        # remove this statement if dockwidget is to remain
        # for reuse if plugin is reopened
        # Commented next statement since it causes QGIS crashe
        # when closing the docked window:
        self.dockwidget = None
        self.search_form = None
        self.search_point_form = None
        self.pluginIsActive = False
        self.project.layersRemoved.disconnect()

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""

        #print "** UNLOAD wyszukiwarkaDzialek"

        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&Wyszukiwarka działek ewidencyjnych (GUGiK ULDK) - beta'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar

    #--------------------------------------------------------------------------

    def run(self):
        
        try:
            urlopen("http://google.com")
        except:
            self.iface.messageBar().pushWarning("Wtyczka ULDK", "Brak połączenia z Internetem!")

        if not self.pluginIsActive:
            self.pluginIsActive = True

            #print "** STARTING wyszukiwarkaDzialek"

            # dockwidget may not exist if:
            #    first run of plugin
            #    removed on close (see self.onClosePlugin method)
            if self.dockwidget == None:
                # Create the dockwidget (after translation) and keep reference
                self.dockwidget = wyszukiwarkaDzialekDockWidget()

            # connect to provide cleanup on closing of dockwidget
            self.dockwidget.closingPlugin.connect(self.onClosePlugin)

            # show the dockwidget
            # TODO: fix to allow choice of dock location
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dockwidget)

            self.dockwidget.show()

            self.dockwidget.label_info_full_id.setPixmap(QPixmap(':/plugins/plugin/info.png'))
            self.dockwidget.label_info_full_id.setToolTip("Możesz pominąć wypełnianie powyższych pól\ni ręcznie wpisać kod TERYT działki.")
            self.dockwidget.label_info_sheet.setPixmap(QPixmap(':/plugins/plugin/info.png'))
            self.dockwidget.label_info_sheet.setToolTip("W bazie danych może istnieć kilka działek o takim samym kodzie TERYT, każda na innym arkuszu.\nW takiej sytuacji możesz wybrać z tej listy działkę której szukasz.")
            
            self.search_form = SearchForm(
                self,
                self.dockwidget.combobox_sheet
            )
            self.search_form.register(self.result_collector)
            self.teryt_search_form = SearchTerytForm(
                self.search_form,
                self.dockwidget.button_search,
                self.dockwidget.combobox_province,
                self.dockwidget.combobox_county,
                self.dockwidget.combobox_municipality,
                self.dockwidget.combobox_precinct,
                self.dockwidget.lineedit_teryt,
                self.dockwidget.lineedit_full_id     
            )
        
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
        layer = QgsRasterLayer(url, 'Dzialki ULDK', 'wms')
        layer.setCustomProperty("ULDK", "wms_layer")
        self.wms_layer = layer
        self.project.addMapLayer(self.wms_layer)
        self.dockwidget.button_wms.setEnabled(False)
