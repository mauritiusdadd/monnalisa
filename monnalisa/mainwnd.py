"""
${HEADER}
"""

import os
import json
import logging

from PyQt5 import QtWidgets, uic
import xyz


ACTION_MSG_DICT = {
    'home': 'Homing printer',
    'load': 'Loading filament',
    'unload': 'Unloading filament',
}


class MainWindow(QtWidgets.QMainWindow):
    """
    The main window of the application
    """
    def __init__(self):
        super().__init__()
        uic.loadUi('mainwnd.ui', self)
        self.printer = xyz.XYZPrinter()
        self.printer.message_callback = self.printercallback

        self.actions = {}

        guilogger = xyz.GuiLogger()
        guilogger.edit = self.textEditLog
        guilogger.setLevel(logging.DEBUG)
        logging.getLogger().addHandler(guilogger)

        self.pushButtonPortOpen.clicked.connect(self.getportfile)
        self.pushButtonConnect.clicked.connect(self.connectprinter)
        self.pushButtonHome.clicked.connect(self.printer.home)
        self.pushButtonLoad.clicked.connect(self.printer.loadfilemanet)
        self.pushButtonUnload.clicked.connect(self.printer.unloadfilemanet)
        self.checkBoxDebug.toggled.connect(self.setloglevel)

        self.show()
        self.statusBar.showMessage("No printer connected")

    def closeEvent(self, event):
        self.printer.stop()

    def setloglevel(self, debug):
        if debug:
            logging.getLogger().setLevel(logging.DEBUG)
        else:
            logging.getLogger().setLevel(logging.INFO)

    def parsestatus(self, key, val):
        val = val.strip()
        if key == 'd':
            if val == '0,0,0':
                try:
                    self.actions.pop('print')
                except KeyError:
                    return
                else:
                    if not self.actions:
                        self.busy(False)
                return
            ptime = val.split(',')
            print_perc = float(ptime[0])
            print_elapsed = float(ptime[1])
            print_remain = float(ptime[2])
            msg = f"Printing: {print_elapsed}m elapsed, {print_remain}m left"

            self.actions['print'] = print_perc
            self.busy(True, pbar=True)
            self.progressBar.setValue(print_perc)
            self.statusBar.showMessage(msg)

        elif key == 'f':
            # remaininf filament
            flen = val.split(',')
            n_extruders = int(flen[0])
            if n_extruders > 0:
                self.groupBoxE1.setEnabled(True)
                self.groupBoxE2.setEnabled(False)

                self.doubleSpinBoxE1Fil.setValue(float(flen[1])/1000.0)

                if n_extruders >= 2:
                    self.groupBoxE2.setEnabled(True)
                    self.doubleSpinBoxE2Fil.setValue(float(flen[2])/1000.0)
            else:
                self.groupBoxE2.setEnabled(False)
                self.groupBoxE1.setEnabled(False)

        elif key == 'k':
            mats = val.split(',')
            try:
                e1mat = xyz.filamentmaterial(mats[0])
            except IndexError:
                e1mat = -1
            else:
                try:
                    e2mat = xyz.filamentmaterial(mats[1])
                except IndexError:
                    e2mat = -1

            self.labelE1Material.setText(e1mat)
            self.labelE2Material.setText(e2mat)

        elif key == 't':
            # extruder temperature
            temps = val.split(',')
            n_extruders = int(temps[0])

            if n_extruders > 0:
                self.spinBoxE1Temp.setValue(int(temps[1]))
                self.spinBoxE1Target.setValue(int(temps[2]))

                if n_extruders >= 2:
                    self.spinBoxE1Temp.setValue(int(temps[3]))
                    self.spinBoxE1Target.setValue(int(temps[4]))
            else:
                self.groupBoxE2.setEnabled(False)
                self.groupBoxE1.setEnabled(False)

        elif key == 'w':
            # filament information

            filament = val.split(',')
            n_filaments = int(filament[0])

            if n_filaments > 0:
                self.widgetE1Color.setEnabled(True)
                self.widgetE2Color.setEnabled(False)

                f1id = filament[1]
                f1color = xyz.filamentcolor(f1id[4])
                f1len = xyz.filamentlen(f1id[5])
                self.doubleSpinBoxE1Mlen.setValue(f1len)
                self.widgetE1Color.setStyleSheet(
                    f"background-color: {f1color}"
                )

                if n_filaments >= 2:
                    self.widgetE2Color.setEnabled(True)
                    f2id = filament[2]
                    f2color = xyz.filamentcolor(f2id[4])
                    f2len = xyz.filamentlen(f2id[5])
                    self.doubleSpinBoxE2Mlen.setValue(f2len)
                    self.widgetE2Color.setStyleSheet(
                        f"background-color: {f2color}"
                    )

            else:
                self.widgetE1Color.setEnabled(False)
                self.widgetE2Color.setEnabled(False)

    def printercallback(self, msg):
        sep = msg.find(b':')
        if sep < 0:
            return

        action = msg[:sep].decode()
        json_data = msg[sep+1:]
        if action not in self.printer.ACTIONS:
            return self.parsestatus(action, json_data.decode())

        logging.debug(msg)
        try:
            stat = json.loads(json_data)
        except json.decoder.JSONDecodeError:
            print(msg)
        except ValueError:
            print(msg)
        else:
            status_msg = f'{ACTION_MSG_DICT[action]}: '
            if stat['stat'] == 'start':
                self.actions[action] = 'started'
                self.busy(True)
                status_msg += 'started'
            elif stat['stat'] == 'complete':
                try:
                    self.actions.pop(action)
                except KeyError:
                    pass
                self.busy(False)
                status_msg += 'done'

            if status_msg:
                self.statusBar.showMessage(status_msg)

    def printfile(self):
        raise(NotImplementedError)

    def cancelcurrentaction(self):
        for action in list(self.actions.keys()):
            self.printer.sendaction(action, 'cancel')
        self.printer.print('cancel')

    def busy(self, val, pbar=False):
        try:
            self.pushButtonAction.clicked.disconnect()
        except TypeError:
            pass

        if val:
            if not pbar:
                self.progressBar.setMaximum(0)
            self.pushButtonAction.setText('Cancel')
            self.pushButtonAction.clicked.connect(self.cancelcurrentaction)
        else:
            self.progressBar.setMaximum(100)
            self.pushButtonAction.setText('Print')
            self.pushButtonAction.clicked.connect(self.printfile)

    def getportfile(self):
        f = QtWidgets.QFileDialog()
        url, ext = f.getOpenFileName()
        if not os.path.exists(url):
            return None
        self.lineEditPortUrl.setText(url)

    def connectprinter(self, checked):
        if self.printer.port and self.printer.port.is_open:
            self.printer.disconnect()
            self.pushButtonConnect.setText('Connect')
            self.pushButtonPortOpen.setEnabled(True)
            self.lineEditPortUrl.setEnabled(True)
            self.comboBoxBaud.setEnabled(True)
            self.groupBoxOp.setEnabled(False)
            self.groupBoxHm.setEnabled(False)
            self.groupBoxPr.setEnabled(False)
            self.groupBoxEx.setEnabled(False)
            self.statusBar.showMessage("No printer connected")
        else:
            port_url = self.lineEditPortUrl.text()
            baud = float(self.comboBoxBaud.currentText())
            if self.printer.connect(port_url, baud, timeout=1):
                self.pushButtonConnect.setText('Disconnect')
                self.pushButtonPortOpen.setEnabled(False)
                self.lineEditPortUrl.setEnabled(False)
                self.comboBoxBaud.setEnabled(False)
                self.groupBoxOp.setEnabled(True)
                self.groupBoxHm.setEnabled(True)
                self.groupBoxPr.setEnabled(True)
                self.groupBoxEx.setEnabled(True)
                self.statusBar.showMessage(
                    f"Printer connected on: {port_url}"
                )
