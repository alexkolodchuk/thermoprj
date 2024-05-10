import pyvisa
import numpy as np
from time import sleep
from sys import argv
from PyQt5.QtWidgets import QMainWindow, QApplication
from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt5.uic import loadUi
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import threading

# В этих переменных будут храниться адреса устройств
THERMO_ADDRESS = 'ASRL4::INSTR'
VOLTAGE_ADDRESS = 'Вольтметр 34401a'

rm = pyvisa.ResourceManager()
app: QApplication = None
    
class Project(QMainWindow):
    '''
    Главное окно программы.
    '''
    signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.file = open('data.txt', 'w')
        self.ui = loadUi('thermoprj.ui', self)
        self.ui.settingsButton.clicked.connect(self.open_settings)
        self.ui.startButton.toggled.connect(self.start_or_stop)
        
        # Создание и добавление виджетов Matplotlib
        self.canvas = MplCanvas()
        self.ui.graphLayout.addWidget(self.canvas)
        self.ui.graphLayout.addWidget(NavigationToolbar(self.canvas, self))
        
        # Флаг для кнопки "Старт"
        self.drawing = False
    
    def print(self, string):
        '''Имплементация отладочного вывода.'''
        print(string)
        self.ui.output.setText(string)
    
    def open_settings(self):
        settings = SettingsWindow()
        settings.show()

    def start_or_stop(self, checked):
        '''Включение/выключение отрисовки графика ρ(Т).'''
        if checked:
            self.start()
        else:  # Остановка
            self.ui.startButton.setText('Запуск')
            self.drawing = False

    @pyqtSlot()
    def start(self):
        try:
            print('connecting')
            self.signal.connect(self.updating_graph)
        except Exception as e:
            print(e)
            return

        # Подключение устройств
        try:
            print('connecting devices')
            self.voltage = rm.open_resource(VOLTAGE_ADDRESS)

            self.thermo = rm.open_resource(THERMO_ADDRESS)
        except (pyvisa.errors.VisaIOError, AttributeError):
            self.print('[Ошибка] Неверно указаны адреса инструментов. \
Настройте их в "Настройка устройств".')
            self.ui.startButton.setChecked(False)
            return

        self.ui.startButton.setText('Стоп') # Переключение кнопки

        # Сохранение заданных параметров
        self.current_now: float = self.ui.current.value()
        min_temp: float = self.ui.min.value()
        max_temp: float = self.ui.max.value()
        temp_step: float = self.ui.step.value()

        # Установка выходного тока
        #current.write(f"source:current:level:imm:amp {current_now:1.1f}")

        if temp_step > max_temp-min_temp:
            self.print('[Ошибка] Шаг больше отрезка.')
            self.ui.startButton.setChecked(False)
            return

        # Инициализация начальных массивов (для физических данных)
        try:
            self.temps = np.arange(min_temp, max_temp, temp_step)
        except ZeroDivisionError:
            self.print('[Ошибка] Деление на 0.')
            self.ui.startButton.setChecked(False)
            return
        self.eps = 2000
        self.volt_sp = np.array([])
        self.temp_sp = np.array([])
        self.resistance_sp = np.array([])

        # Создание пустого графика
        self.graph, = self.canvas.axes.plot(self.temp_sp, self.resistance_sp)

        self.drawing = True
        print('starting thread')
        thread = threading.Thread(target=self.iterative_measuring, daemon=True)
        thread.start()

    def iterative_measuring(self):
        for i in self.temps:
            # 1. Задать целевую температуру на термоконтроллер
            # 2. Подождать, пока она не установится
            # 3. Замерить напряжение на вольтметре
            # 4. Вычислить сопротивление
            if not self.drawing:
                break
            self.thermo.write(f'pid4:temp:targ {i:3.3f}')
            temp_now = float(self.thermo.query('meas:temp?'))
            while abs(temp_now - i) >= self.eps:
                sleep(0.5)
                temp_now = float(self.thermo.query('meas:temp?'))
                print(temp_now)

            print('emitting signal')
            self.signal.emit()
            sleep(2)

        self.ui.startButton.setText('Запуск')
        self.ui.startButton.setChecked(False)
        self.drawing = False

    def updating_graph(self):
        temp_now = float(self.thermo.query('meas:temp?'))
        volts = float(self.voltage.query('read?'))*1000
        self.temp_sp = np.append(self.temp_sp, temp_now)
        self.volt_sp = np.append(self.volt_sp, volts)
        resistance = volts / self.current_now
        self.resistance_sp = np.append(self.resistance_sp, resistance)
        self.print(f'[ДАННЫЕ] {volts:.3f} В, {temp_now:.3f} °К, {resistance:.3f} Ом')

        print('drawing')
        # Рисование графика
        self.graph.set_data(self.temp_sp, self.resistance_sp)
        self.canvas.draw()
        self.canvas.flush_events()
        xsize = max(max(self.temp_sp) - min(self.temp_sp), 0.0001)
        self.canvas.axes.set_xlim(min(self.temp_sp) - xsize * 0.1, max(self.temp_sp) + xsize * 0.1)
        ysize = max(max(self.resistance_sp) - min(self.resistance_sp), 0.0001)
        self.canvas.axes.set_ylim(min(self.resistance_sp) - ysize * 0.1, max(self.resistance_sp) + ysize * 0.1)

    def __del__(self):
        self.file.close()

class MplCanvas(FigureCanvasQTAgg):
    '''Собственный холст Matplotlib.'''
    def __init__(self):
        fig = Figure()
        self.axes = fig.add_subplot(111)
        super().__init__(fig)

class SettingsWindow(QMainWindow):
    '''Окно настройки устройств.'''
    def __init__(self):
        super().__init__()
        self.ui = loadUi('settings.ui', self)
        self.ui.updateButton.clicked.connect(self.update_lists)
        self.ui.saveButton.clicked.connect(self.save_changes)
        
    def update_lists(self):
        app.setOverrideCursor(Qt.CursorShape.BusyCursor)
        resources = list(rm.list_resources())
        if len(resources)==0: resources.append('Устройств не найдено :(')
        self.ui.resources1.clear()
        self.ui.resources1.addItems(resources)
        self.ui.resources2.clear()
        self.ui.resources2.addItems(resources)
        app.setOverrideCursor(Qt.CursorShape.ArrowCursor)
    
    def save_changes(self):
        global THERMO_ADDRESS, VOLTAGE_ADDRESS
        THERMO_ADDRESS = self.ui.resources1.currentText()
        VOLTAGE_ADDRESS = self.ui.resources2.currentText()
        self.close()

if __name__ == '__main__':
    app = QApplication(argv)
    window = Project()
    window.show()
    exit(app.exec_())

# Cryotel,Model\s311\sTemperature\sController,SN00135,2.7.4\r\n
# Prist,V7-78/1,TW00011505,03.07-01-04