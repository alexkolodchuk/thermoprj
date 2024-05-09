from pyvisa import ResourceManager
from time import time
import numpy as np
import matplotlib.pyplot as plt
from pyvisa.resources import Resource

rm = ResourceManager()
resources = rm.list_resources()

thermo: Resource = rm.open_resource('Температурный контроллер ТС322')
current: Resource = rm.open_resource('Источник тока Keysight N5700')
voltage: Resource = rm.open_resource('Вольтметр 34401a')

current_now = 1.0
current.write(f"SOURce:CURRent:LEVel:IMMediate:AMPLitude {current_now}")

temps = np.linspace(300, 350, 25)
eps = 0.005
volt_sp = np.array([])
temp_sp = np.array([])
resistance_sp = np.array([])
graph = plt.plot(temp_sp, resistance_sp)

for i in temps:
    temp_now = thermo.query('MEASure[n]:TEMPerature?')
    thermo.write(f'PID[n]:TEMPerature:TARGet {i:3.3f}')
    while abs(temp_now - i) >= eps:
        temp_now = thermo.query('MEASure[n]:TEMPerature?')
    volts = voltage.query('read?')
    temp_sp = np.append(temp_sp, temp_now)
    volt_sp = np.append(volt_sp, volts)
    resistance = volts / current_now
    resistance_sp = np.append(resistance_sp, resistance)
    graph.remove()
    graph = plt.plot(temp_sp, resistance_sp)


