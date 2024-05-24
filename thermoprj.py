#!/usr/bin/env python
# -*- encoding: UTF8 -*-

# This file is part of thermoprj.
#
# thermoprj is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# thermoprj is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with thermoprj. If not, see <https://www.gnu.org/licenses/>.

import pyvisa, threading, datetime
import numpy as np
from time import sleep
from sys import argv
from PyQt5.QtWidgets import QMainWindow, QApplication
from PyQt5.QtCore import pyqtSignal, pyqtSlot
from PyQt5.uic import loadUi
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

# Это - дефолтные названия устройств (то, что они возвращают на *IDN?)
# В случае отсутствия файла настроек эти данные загружаются туда
DEFAULT_THERMO_NAME = 'Cryotel,Model\s311\sTemperature\sController,SN00135,2.7.4\r\n'
DEFAULT_VOLTAGE_NAME = 'Prist,V7-78/1,TW00011505,03.07-01-04'

SETTINGS_FILENAME = 'thermoprj_settings.txt'
DATA_FILENAME = 'thermoprj_data.csv'
FSTRING_FOR_DATETIME = '%Y/%m/%d-%H:%M:%S.%f'

rm = pyvisa.ResourceManager()
app: QApplication = None
    
# Работа с файлом настроек
def retrieve_settings() -> dict:
    try:
        with open(SETTINGS_FILENAME, encoding='utf-8') as f:
            text = f.read().split('\n')
            return {'thermo': text[0], 'voltage': text[1]}
    except (FileNotFoundError, KeyError, IndexError, UnicodeDecodeError):
        with open(SETTINGS_FILENAME, mode='w', encoding='utf-8') as f:
            f.write(DEFAULT_THERMO_NAME+'\n'+DEFAULT_VOLTAGE_NAME)
        return {'thermo': DEFAULT_THERMO_NAME, 'voltage': DEFAULT_VOLTAGE_NAME}
    
def save_settings(settings: dict) -> None:
    with open(SETTINGS_FILENAME, mode='w', encoding='utf-8') as f:
        f.write(settings['thermo']+'\n'+settings['voltage'])

class Project(QMainWindow):
    '''
    Главное окно программы.
    '''
    signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.file = open(DATA_FILENAME, mode='a+', encoding='utf-8')
        
        self.ui = loadUi('thermoprj.ui', self)
        self.ui.settingsButton.clicked.connect(self.open_settings_window)
        self.ui.startButton.toggled.connect(self.start_or_stop)
        
        # Создание и добавление виджетов Matplotlib
        self.canvas = MplCanvas()
        self.ui.graphLayout.addWidget(self.canvas)
        self.ui.graphLayout.addWidget(NavigationToolbar(self.canvas, self))
        
        # Флаг для кнопки "Старт"
        self.drawing = False
    
    def print(self, string: object) -> None:
        '''Имплементация отладочного вывода.'''
        print(string)
        self.ui.output.setText(string)
    
    def open_settings_window(self) -> None:
        settings = SettingsWindow(self)
        settings.show()
        self.ui.settingsButton.setEnabled(False)
        
    def write_to_file(self, time: datetime.datetime, data) -> None:
        '''Добавление полученного вывода к файлу.'''
        self.file.write(time.strftime(FSTRING_FOR_DATETIME)+';'+';'.join(data)+'\n')

    def start_or_stop(self, checked: bool) -> None:
        '''Включение/выключение отрисовки графика ρ(Т).'''
        if checked:
            self.start()
        else:  # Остановка
            self.ui.startButton.setText('Запуск')
            self.drawing = False

    @pyqtSlot()
    def start(self):
        # Подключение сигнала к слоту
        try:
            print('Подключение к графику...')
            self.signal.connect(self.updating_graph)
        except Exception as e:
            print(e)
            return

        # Подключение всех устройств и сопоставление их ответов на *IDN? с заданными названиями
        self.thermo = None
        self.voltage = None
        
        print('Получение устройств...')
        resources = rm.list_resources()
        settings = retrieve_settings()
        
        try:
            for r in resources:
                device = rm.open_resource(r)
                answer = device.query('*IDN?')
                if answer == settings['thermo']:
                    self.thermo = device
                elif answer == settings['voltage']:
                    self.voltage = device
                else:
                    device.close()
        except pyvisa.errors.VisaIOError:
            self.print('VISA не найдена на компьютере')
            self.ui.startButton.setChecked(False)
            return
        
        # Обработка ошибок, связанных с поиском устройств
        if self.thermo == None:
            self.print('Термоконтроллер не найден')
            self.ui.startButton.setChecked(False)
            return
        if self.voltage == None:
            self.print('Вольтметр не найден')
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
        self.graph, = self.canvas.axes.plot(self.temp_sp, self.resistance_sp, marker='o')

        self.drawing = True
        print('Запуск измерений...')
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

            self.signal.emit()
            sleep(2)

        self.ui.startButton.setText('Запуск')
        self.ui.startButton.setChecked(False)
        self.drawing = False

    def updating_graph(self):
        temp_now = float(self.thermo.query('meas:temp?'))
        volts = float(self.voltage.query('read?'))*1000
        self.write_to_file(datetime.datetime.now(), (temp_now, volts))
        self.temp_sp = np.append(self.temp_sp, temp_now)
        self.volt_sp = np.append(self.volt_sp, volts)
        resistance = volts / self.current_now
        self.resistance_sp = np.append(self.resistance_sp, resistance)
        self.print(f'[ДАННЫЕ] {volts:.3f} В, {temp_now:.3f} °К, {resistance:.3f} Ом')

        # Рисование графика
        self.graph.set_data(self.temp_sp, self.resistance_sp)
        self.canvas.draw()
        self.canvas.flush_events()
        xsize = max(max(self.temp_sp) - min(self.temp_sp), 0.0001)
        self.canvas.axes.set_xlim(min(self.temp_sp) - xsize * 0.1, max(self.temp_sp) + xsize * 0.1)
        ysize = max(max(self.resistance_sp) - min(self.resistance_sp), 0.0001)
        self.canvas.axes.set_ylim(min(self.resistance_sp) - ysize * 0.1, max(self.resistance_sp) + ysize * 0.1)

    def __del__(self):
        self.print('Закрытие файла с данными...')
        self.drawing = False
        self.file.close()


class MplCanvas(FigureCanvasQTAgg):
    '''Собственный холст Matplotlib.'''
    def __init__(self):
        fig = Figure()
        self.axes = fig.add_subplot(111)
        super().__init__(fig)


class SettingsWindow(QMainWindow):
    '''Окно настройки устройств.'''
    def __init__(self, mainWindow: Project):
        super().__init__()
        self.ui = loadUi('settings.ui', self)
        self.ui.saveButton.clicked.connect(self.save_settings)
                
        self.settings: dict = retrieve_settings()
        self.ui.thermo.setText(self.settings['thermo'])
        self.ui.voltage.setText(self.settings['voltage'])
        
        self.mainWindow = mainWindow
        self.mainWindow.print('Настройки загружены')
        
    def save_settings(self):
        self.settings['thermo'] = self.ui.thermo.text()
        self.settings['voltage'] = self.ui.voltage.text()
        save_settings(self.settings)
        self.mainWindow.ui.settingsButton.setEnabled(True)
        self.close()

if __name__ == '__main__':
    app = QApplication(argv)
    window = Project()
    window.show()
    exit(app.exec_())

# Cryotel,Model\s311\sTemperature\sController,SN00135,2.7.4\r\n
# Prist,V7-78/1,TW00011505,03.07-01-04