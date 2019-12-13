from PyQt5 import QtWidgets
import sys
from . import mainwnd
import logging

def main():
    logging.getLogger().setLevel(logging.INFO)
    app = QtWidgets.QApplication(sys.argv)
    ui = mainwnd.MainWindow()
    app.exec_()

if __name__ == '__main__':
    main()
