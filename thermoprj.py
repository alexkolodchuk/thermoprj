from pyvisa import ResourceManager

rm = ResourceManager()
resources = rm.list_resources()

thermo = rm.open_resource('Температурный контроллер ТС322')
thermo = rm.open_resource('Источник тока Keysight N5700')
thermo = rm.open_resource('Вольтметр 34401a')
