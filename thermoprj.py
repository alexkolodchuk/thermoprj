import pyvisa
import numpy as np
from time import sleep
from sys import argv
from PyQt5.QtWidgets import QMainWindow, QApplication
from PyQt5.QtCore import Qt
from PyQt5.uic import loadUi
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

# В этих переменных будут храниться адреса устройств
THERMO_ADDRESS = 'Температурный контроллер ТС322'
VOLTAGE_ADDRESS = 'Вольтметр 34401a'


rm = pyvisa.ResourceManager()
app: QApplication = None
    
class Project(QMainWindow):
    '''
    Главное окно программы.
    '''
    def __init__(self):
        super().__init__()
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
            # Подключение устройств
            #try:
            voltage = rm.open_resource(VOLTAGE_ADDRESS)
            print('thermo:', THERMO_ADDRESS.encode())
            print('voltage:', VOLTAGE_ADDRESS)
            thermo = rm.open_resource(THERMO_ADDRESS)
            print(1)
            thermo.baud_rate = 9600
            thermo.data_bits = 8
            print(1)
            thermo.stop_bits = 1
            thermo.parity = None
            print(1)
            #except (pyvisa.errors.VisaIOError, AttributeError):
                #self.print('[Ошибка] Неверно указаны адреса инструментов. \
#Настройте их в "Настройка устройств".')
                #self.ui.startButton.setChecked(False)
                #return
            
            self.ui.startButton.setText('Стоп') # Переключение кнопки
            
            # Сохранение заданных параметров
            current_now: float = self.ui.current.value()
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
                temps = np.arange(min_temp, max_temp, temp_step)
            except ZeroDivisionError:
                self.print('[Ошибка] Деление на 0.')
                self.ui.startButton.setChecked(False)
                return
            eps = 0.1
            volt_sp = np.array([])
            temp_sp = np.array([])
            resistance_sp = np.array([])
            
            # Создание пустого графика
            self.graph, = self.canvas.axes.plot(temp_sp, resistance_sp)
            
            self.drawing = True
            for i in temps:
                # 1. Задать целевую температуру на термоконтроллер
                # 2. Подождать, пока она не установится
                # 3. Замерить напряжение на вольтметре
                # 4. Вычислить сопротивление
                if not self.drawing:
                    break
                print(1)
                thermo.write(f'pid[1]:temp:target {i:3.3f}')
                
                temp_now = thermo.query('measure[1]:temp?')
                while abs(temp_now - i) >= eps:
                    sleep(0.1)
                    temp_now = thermo.query('measure[1]:temp?')
                volts = voltage.query('read?')
                temp_sp = np.append(temp_sp, temp_now)
                volt_sp = np.append(volt_sp, volts)
                resistance = volts / current_now
                resistance_sp = np.append(resistance_sp, resistance)
                self.print(f'[ДАННЫЕ] {volts:.3f} В, {temp_now:.3f} °К, {resistance:.3f} Ом')
                
                # Рисование графика
                self.graph.set_data(temp_sp, resistance_sp)
                self.canvas.draw()
                self.canvas.flush_events()
                xsize = max(temp_sp)-min(temp_sp)
                self.canvas.axes.set_xlim(min(temp_sp)-xsize*0.1, max(temp_sp)+xsize*0.1)
                ysize = max(resistance_sp)-min(resistance_sp)
                self.canvas.axes.set_ylim(min(resistance_sp)-ysize*0.1, max(resistance_sp)+ysize*0.1)
            
            self.ui.startButton.setText('Запуск')
            self.ui.startButton.setChecked(False)
            self.drawing = False
        
        else: # Остановка
            self.ui.startButton.setText('Запуск')
            self.drawing = False
        
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