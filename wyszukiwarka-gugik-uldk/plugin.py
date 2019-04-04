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
from PyQt5.QtCore import QSettings, QTranslator, qVersion, QCoreApplication, Qt, QVariant

from PyQt5.QtWidgets import QAction
from qgis.core import *
from qgis.gui import QgsMessageBar

from PyQt5.QtGui import *
# Initialize Qt resources from file resources.py
from .resources import *

# Import the code for the DockWidget
from .plugin_dockwidget import wyszukiwarkaDzialekDockWidget
import os.path
import json
import operator
import locale

import requests
import time
from urllib.request import urlopen
from collections import OrderedDict

try: 
    from .uldk_api import ULDK_API as uldk_api
except ImportError:
    from uldk_api import ULDK_API as uldk_api
try:
    from .exceptions import *
except ImportError:
    from exceptions import *
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
        # TODO: We are going to let the user set this up in a future iteration
        self.toolbar = self.iface.addToolBar(u'wyszukiwarkaDzialek')
        self.toolbar.setObjectName(u'wyszukiwarkaDzialek')

        #print "** INITIALIZING wyszukiwarkaDzialek"

        self.pluginIsActive = False
        self.dockwidget = None
        


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
        parent=None):
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

        icon_path = ':/plugins/plugin/logo_thumb.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Wyszukiwarka działek ewidencyjnych (GUGiK ULDK) - beta'),
            callback=self.run,
            parent=self.iface.mainWindow())

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

        self.pluginIsActive = False


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
            # self.dockwidget.labelLogo.setPixmap(QPixmap(self.path_logo))
            # self.dockwidget.labelLogo.setScaledContents(True)

            self.dockwidget.show()

            self.dockwidget.comBoxWoj.activated.connect(self.fillComBoxPow)
            self.dockwidget.comBoxPow.activated.connect(self.fillComBoxGmi)
            self.dockwidget.comBoxGmi.activated.connect(self.fillComBoxObr)
            self.dockwidget.comBoxObr.activated.connect(self.SetCurrentID)

            self.dockwidget.texEdDzi.textChanged.connect(self.SetCurrentID)

            self.dockwidget.comBoxWoj.activated.connect(self.argumentsFilled)
            self.dockwidget.comBoxPow.activated.connect(self.argumentsFilled)
            self.dockwidget.comBoxGmi.activated.connect(self.argumentsFilled)
            self.dockwidget.labelCurrentID.textChanged.connect(self.argumentsFilled)

            self.dockwidget.btnSearch.clicked.connect(self.search_dzialka)
            self.dockwidget.btnWMS.clicked.connect(self.addWMS)

            self.fillComBoxWoj()

            self.dockwidget.label_info.setPixmap(QPixmap(':/plugins/plugin/info.png'))
            self.dockwidget.label_arkusz.hide()
            self.dockwidget.combobox_arkusz.hide()

            self.dockwidget.label_select_by_coords.hide()
            self.dockwidget.frame_select_by_coords.hide()

    def hide_arkusz_section(self):
        self.dockwidget.combobox_arkusz.clear()
        self.dockwidget.label_arkusz.hide()
        self.dockwidget.combobox_arkusz.hide()

    def SetCurrentID(self):
        obr_id = obr_id = self.dockwidget.comBoxObr.currentText().split(" | ")[1]
        dzi_id = self.dockwidget.texEdDzi.text()
        identyfikator = "{}.{}".format(obr_id,dzi_id)
        self.dockwidget.labelCurrentID.setText(identyfikator)
        self.hide_arkusz_section() #TODO przenieść w sensowne miejsce


    
    def argumentsFilled(self):
        enabled = (self.dockwidget.comBoxWoj.currentText() != "" and
                self.dockwidget.comBoxPow.currentText() != "" and
                self.dockwidget.comBoxGmi.currentText() != "" and
                self.dockwidget.comBoxObr.currentText() != "" and
                self.dockwidget.texEdDzi.text() != "") or self.dockwidget.labelCurrentID.text() != ""
        self.dockwidget.btnSearch.setEnabled(enabled)

    def fillComBox(self, target, content_list, in_separator = "|", out_separator = " | ", clear = True, first_element_empty = True):
        if clear:
            target.clear()
        content_format = []
        if first_element_empty:
            content_format.append("")
        for e in content_list:
            spl = e.split( in_separator )
            try:
                content_format.append("{}{sep}{}".format( spl[0], spl[1], sep = out_separator ))
            except:
                continue
        target.addItems(content_format)

    def fillComBoxWoj(self):
        wojewodztwa =  self.get_wojewodztwa()
        self.fillComBox(self.dockwidget.comBoxWoj, wojewodztwa)
        self.hide_arkusz_section()

    def fillComBoxPow(self):
        self.dockwidget.comBoxGmi.clear()
        self.dockwidget.comBoxObr.clear()

        woj = self.dockwidget.comBoxWoj.currentText()
        if woj == "":
            return
        woj_teryt = woj.split(" | ")[1]

        powiaty = self.get_powiaty(woj_teryt)
        self.fillComBox(self.dockwidget.comBoxPow, powiaty)
        self.hide_arkusz_section()

    def fillComBoxGmi(self):
        self.dockwidget.comBoxObr.clear()

        pow = self.dockwidget.comBoxPow.currentText()
        if pow == "":
            return
        pow_teryt = pow.split(" | ")[1]
        gminy = self.get_gminy(pow_teryt)
        self.fillComBox(self.dockwidget.comBoxGmi, gminy)
        self.hide_arkusz_section()

    def fillComBoxObr(self):
        self.dockwidget.comBoxObr.clear() 
        gmi = self.dockwidget.comBoxGmi.currentText()
        if gmi == "":
            return
        gmi_teryt = gmi.split(" | ")[1]
        obreby = self.get_obreby(gmi_teryt)
        self.fillComBox(self.dockwidget.comBoxObr, obreby)
        self.hide_arkusz_section()
        

    #def fill_combobox_arkusze(self):

    def search_dzialka(self):
        teryt = self.dockwidget.labelCurrentID.text()
        dzialka_numer = teryt.split(".")[-1]
        if dzialka_numer == "":
            self.iface.messageBar().pushWarning("Wtyczka ULDK","Podaj numer działki")
            return
        
        self.add_dzialka_layer(teryt)


    def add_dzialka_layer(self, teryt):

        try:
            dzialki = self.get_dzialka(teryt)
        except RequestException as e:
            return
        if len(dzialki) == 1:
            dzialka = dzialki[0]
            ewkt = dzialka.split("|")[1]
            try:
                layer = self.WKT_to_QgsVectorlayer(ewkt, layer_name = "dzialka_" + teryt)
            except InvalidGeomException as e:
                self.iface.messageBar().pushCritical("",str(e))
            QgsProject.instance().addMapLayer(layer)

            #styl
            myRenderer  = layer.renderer()
            mySymbol1 = QgsFillSymbol.createSimple({'color':'white', 'color_border':'red','width_border':'2'})
            myRenderer.setSymbol(mySymbol1)
            layer.setOpacity(0.35)
            layer.triggerRepaint()
            self.iface.zoomToActiveLayer()
        else:
            def get_dzialka_arkusz():
                teryt = self.dockwidget.combobox_arkusz.currentText()
                self.add_dzialka_layer(teryt)
            ids = [dzialka.split("|")[0] for dzialka in dzialki]

            self.dockwidget.combobox_arkusz.show()
            self.dockwidget.label_arkusz.show()
            self.dockwidget.combobox_arkusz.clear()
            self.dockwidget.combobox_arkusz.addItems(ids)
            teryt = self.dockwidget.combobox_arkusz.currentText()
            self.dockwidget.combobox_arkusz.activated.connect( get_dzialka_arkusz )
            self.iface.messageBar().pushMessage("Wtyczka ULDK", "Wybrana działka znajduje się na różnych arkuszach. Wybierz jeden z nowej listy.", level = 0, duration = 15)
        

    def get_wojewodztwa(self):
        """Pobranie wszystkich województw w kraju"""
        url = uldk_api.format_url(obiekt = "wojewodztwo", wynik = ["nazwa","teryt"])
        try:
            wojewodztwa = uldk_api.send_request(url)
        except RequestException as e:
            self.iface.messageBar().pushCritical("","Błąd pobierania listy województw - odpowiedź serwera: '{}'".format(str(e)))
            return []
        return wojewodztwa
        
    def get_powiaty(self, teryt = ""):
        """Pobranie wszystkich powiatów w kraju, lub dla województwa o podanym teryt"""
        url = uldk_api.format_url(obiekt = "powiat", wynik = ["nazwa","teryt"], filter_ = teryt)
        try:
            powiaty = uldk_api.send_request(url)
        except RequestException as e:
            self.iface.messageBar().pushCritical("","Błąd pobierania listy powiatów - odpowiedź serwera: '{}'".format(str(e)))
            return []
        return powiaty

    def get_gminy(self, teryt = ""):
        """Pobranie wszystkich gmin w kraju, lub dla powiatu o podanym teryt"""
        url = uldk_api.format_url(obiekt = "gmina", wynik = ["nazwa","teryt"], filter_ = teryt)
        try:
            gminy = uldk_api.send_request(url)
        except RequestException as e:
            self.iface.messageBar().pushCritical("","Błąd pobierania listy gmin - odpowiedź serwera: '{}'".format(str(e)))
            return []
        return gminy

    def get_obreby(self, teryt):
        """Pobranie obrębów dla danego terytu gminy"""
        url = uldk_api.format_url(obiekt = "obreb", wynik = ["nazwa","teryt"], filter_ = teryt)
        try:
            obreby = uldk_api.send_request(url)
        except RequestException as e:
            teryt = teryt.split("_")[0]
            url = uldk_api.format_url(obiekt = "obreb", wynik = ["nazwa","teryt"], filter_ = teryt)
            try:
                obreby = uldk_api.send_request(url)
            except RequestException as e:
                self.iface.messageBar().pushCritical("","Błąd pobierania listy obrębów - odpowiedź serwera: '{}'".format(str(e)))
                return []
        return obreby

    def get_dzialka(self, id, format_ = "teryt,geom_wkt"):
        """Pobranie działki o danym id"""

        url = uldk_api.format_url(obiekt = "dzialka", wynik = format_, filter_ = id)
        try:
            result = uldk_api.send_request(url)
        except RequestException as e:
            self.iface.messageBar().pushCritical("","Błąd pobierania działki - odpowiedź serwera: '{}'".format(str(e)))
            raise e
 
        return result


    def WKT_to_QgsVectorlayer(self, wkt, epsg = "2180", layer_name = "warstwa_wynikowa"):

        ewkt = wkt.split(";")
        
        if len(ewkt) == 2:
            epsg = ewkt[0].split("=")[1]
            wkt = ewkt[1]

        geom = QgsGeometry.fromWkt(wkt)
        if not geom.isGeosValid():
            raise InvalidGeomException("Nie udało się przetworzyć geometrii działki")
        layer = QgsVectorLayer("Polygon?crs=EPSG:" + epsg, layer_name, "memory")
        layer.startEditing()
        layer.dataProvider().addAttributes([QgsField("pow_mkw", QVariant.String)])
        feat = QgsFeature()
        feat.setGeometry(geom)
        area = geom.area()
        feat.setAttributes([area])
        layer.dataProvider().addFeature(feat)
        layer.commitChanges()

        return layer

    def addWMS(self):
        if not QgsProject.instance().mapLayersByName(
                'Dzialki ULDK'):
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
            QgsProject.instance().addMapLayer(layer)
        else:
            pass