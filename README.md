## Logging Pfeiffer Vacuum turbopump pressure with PicoScope 2000 ##

Real time monitoring and logging of pressure instide a Pfeiffer Vacuum turbopump (used specifically with HiCube 80 station). The pressure is monitored by reading analog voltage tapped manually from the pressure gauge.

Voltage is read using PicoScope 2000 series USB oscilloscope. I did not find a Python library to work with PicoScope devices, so I had to write my own `ps2000.py`. The library can be used independently for any kind of project.

