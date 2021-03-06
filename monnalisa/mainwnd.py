"""
${LICENSE_HEADER}
"""

import os
import json
import logging
import io
import base64
import zlib

from PyQt5 import QtWidgets, uic
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QPixmap
from . import xyz


ACTION_MSG_DICT = {
    'home': 'Homing printer',
    'load': 'Loading filament',
    'unload': 'Unloading filament',
    'upload': 'Sendig file to the printer...',
    'image': 'Incoming image...',
    'calibratejr': 'Calibrating printer head',
}


class MainWindow(QtWidgets.QMainWindow):
    """
    The main window of the application
    """
    processPrinterMessage = pyqtSignal(bytes)

    def __init__(self):
        super().__init__()
        ui_path = os.path.join(os.path.dirname(xyz.__file__),
                               'ui', 'mainwnd.ui')
        uic.loadUi(ui_path, self)
        self.open_dialog = QtWidgets.QFileDialog()
        self.printer = xyz.XYZPrinter()
        self.printer.message_callback = self.printercallback

        self.actions = {}
        self._image = {
            'id': b'',
            'data': io.BytesIO(),
        }
        self.processPrinterMessage.connect(self.processmessage)

        guilogger = xyz.GuiLogger()
        guilogger.edit = self.textEditLog
        guilogger.setLevel(logging.DEBUG)
        logging.getLogger().addHandler(guilogger)

        self.pushButtonPause.hide()
        self.labelRemoteImage.hide()

        self.pushButtonPause.clicked.connect(self.pauseprint)
        self.pushButtonPortOpen.clicked.connect(self.getportfile)
        self.pushButtonConnect.clicked.connect(self.connectprinter)
        self.pushButtonHome.clicked.connect(self.printer.home)
        self.pushButtonLoad.clicked.connect(self.printer.loadfilemanet)
        self.pushButtonUnload.clicked.connect(self.printer.unloadfilemanet)
        self.pushButtonCalib.clicked.connect(self.printer.calibrationinit)
        self.pushButtonAction.clicked.connect(self.printfile)
        self.pushButtonJog.clicked.connect(self.dojog)
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
                        self.pushButtonPause.hide()
                        self._print_status = 'ready'
                return
            ptime = val.split(',')
            self.pushButtonPause.show()
            print_perc = float(ptime[0])
            print_elapsed = float(ptime[1])
            print_remain = float(ptime[2])
            msg = f"Printing: {print_elapsed}m elapsed, {print_remain}m left"

            self.actions['print'] = print_perc
            self.busy(True, pbar=True)
            self.progressBar.setValue(print_perc)
            self.statusBar.showMessage(msg)

        elif key == 'f':
            # remaining filament
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

        elif key == 'n':
            self.printer.name = val
            self.labelPrinterName.setText(val)

        elif key == 'o':
            opts = val.split(',')
            for option in opts:
                if option[0] == 'p':  # p -> block_size
                    b_size = int(option[1:])
                    self.printer.block_size = b_size*1024 if b_size > 0 else 0
                    logging.debug("Setting printer block size %d",
                                  self.printer.block_size)
                elif option[0] == 't':
                    pass
                elif option[0] == 'c':
                    pass
                elif option[0] == 'a':
                    if option[1] == '+':
                        self.printer.autoleveling = True
                    else:
                        self.printer.autoleveling = False
        elif key == 'p':
            self.printer.setid(val)
            self.labelPrinterId.setText(f"({val})")
            self.checkBoxZipped.setChecked(self.printer.zipped)
            self.radioButton3wV2.setChecked(self.printer.version == 2)

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
        self.processPrinterMessage.emit(msg)

    def processmessage(self, msg):
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
        except (json.decoder.JSONDecodeError, ValueError) as exc:
            if action == 'calibratejr':
                stat = {None: []}
                json_data = json_data.decode().strip('{}\n\t ')
                for item in json_data.split(','):
                    try:
                        key, val = item.split(':')
                        key = key.strip('"\'').strip()
                        val = val.strip('"\'').strip()
                        stat[key] = val
                    except ValueError:
                        stat[None].append(item)
            else:
                logging.error(exc)
                return
        if stat:
            status_msg = f'{ACTION_MSG_DICT[action]}: '
            if action == 'image':
                self.printer.sendAck(b'image')
                try:
                    if stat['id'] != self._image['id']:
                        self._image['data'].close()
                        self._image['data'] = io.BytesIO()
                        self._image['id'] = stat['id']
                    self._image['data'].seek(stat['offset'])
                    self._image['data'].write(stat['data'].encode())
                    self._image['shape'] = stat['shape']
                except KeyError:
                    logging.debug("New image received")
                    self.showimage()
            elif action == 'calibratejr':
                if stat['stat'] == 'pressdetector':
                    msg = QtWidgets.QMessageBox.information(
                        None, "Calibration",
                        "Lower the calibration detenctor and then press ok",
                        QtWidgets.QMessageBox.Ok
                    )
                    self.printer.calibrationrun()
                    self.busy(True)
                elif stat['stat'] == 'ok':
                    msg = QtWidgets.QMessageBox.information(
                        None, "Calibration",
                        "Raise the calibration detenctor and then press ok",
                        QtWidgets.QMessageBox.Ok
                    )
                    self.printer.calibrationdone()
                self.busy(False)

            elif stat['stat'] == 'start':
                self.actions[action] = 'started'
                self.busy(True, pbar=action != 'uploading')
                status_msg += 'started'
            elif stat['stat'] == 'uploading':
                self.progressBar.setValue(stat['progress'])
            elif stat['stat'] == 'complete':
                try:
                    self.actions.pop(action)
                except KeyError:
                    pass
                self.progressBar.setValue(0)
                self.busy(False)
                status_msg += 'done'

            if status_msg:
                self.statusBar.showMessage(status_msg)

    def showimage(self):
        fio = self._image['data']
        fio.seek(0)
        try:
            data = zlib.decompress(base64.b64decode(fio.read()))
        except zlib.error:
            logging.error('Incoming image data is corrutped!')
            return
        height, width = self._image['shape'][:2]
        pix = QPixmap(width, height)
        pix.loadFromData(data)
        self.labelRemoteImage.setPixmap(pix)
        self.labelRemoteImage.show()

    def dojog(self):
        axis = self.comboBoxAxis.currentText().lower()
        jog = self.doubleSpinBoxJog.value()
        self.printer.jog(axis, jog)

    def pauseprint(self):
        if self.printer.getprintstatus() == 'paused':
            if self.printer.print('resume'):
                self.printer._print_status = 'printing'
        elif self.printer.getprintstatus() == 'printing':
            if self.printer.print('pause'):
                self.printer._print_status = 'paused'

    def printfile(self):
        url, ext = self.open_dialog.getOpenFileName()
        if not os.path.exists(url):
            return None
        self.printer.sendFile(url)
        self.pushButtonPause.show()

    def cancelcurrentaction(self):
        self.printer.print('cancel')
        for action in list(self.actions.keys()):
            self.printer.sendaction(action, 'cancel')

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
        url, ext = self.open_dialog.getOpenFileName()
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
            if self.printer.connect(port_url, baud, timeout=3):
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
