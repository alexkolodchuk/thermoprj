from pyvisa import ResourceManager
from time import time
import numpy as np
import matplotlib.pyplot as plt


rm = ResourceManager()
resources = rm.list_resources()

thermo = rm.open_resource('Температурный контроллер ТС322')
current = rm.open_resource('Источник тока Keysight N5700')
voltage = rm.open_resource('Вольтметр 34401a')

current_now = 1.0
current.write(f"SOURce:CURRent:LEVel:IMMediate:AMPLitude {current_now}")

temps = np.linspace(300.000, 350.000, 25)
eps = 0.005
volt_sp = []
temp_sp = []
resistance_sp = []
graph = plt.plot(temp_sp, resistance_sp)
for i in temps:
    temp_now = thermo.query('MEASure[n]:TEMPerature?')
    thermo.write(f'PID[n]:TEMPerature:TARGet {i}')
    while abs(temp_now - i) >= eps:
        temp_now = (thermo.query('MEASure[n]:TEMPerature?'))
    volts = voltage.query('read?')
    temp_sp.append(temp_now)
    volt_sp.append(volts)
    resistance = volts / current_now
    resistance_sp.append(resistance)
    graph.remove()
    graph = plt.plot(temp_sp, resistance_sp)


