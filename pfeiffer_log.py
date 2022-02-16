"""
Readout voltage from channel A of PicoScope 2204
Requires keyboard module (pip install keyboard) to be able to terminate the program with a key/key combination

@author: Ilya Radko
"""
from ps2000 import ps2000
from time import sleep
from datetime import datetime as dt
from threading import Thread
import keyboard as kbd
import numpy as np


# Log file name (will be saved in the current working directory)
logfile = 'pressure.log'
# Define how many log data points to collect and how often
n_cycles = 100000   # Number of voltage readouts
loopdelay = 30      # Delay between voltage readouts in seconds
# Each readout is averaged over several readouts with small delay
n_avg = 5           # Number of readouts to average over
avgdelay = 1        # Delay between readouts for averaging

# Init variables
time = []     # Save time here
volt = []     # Save voltage here
do_measurement = True  # Keep doing measurement?
loop_count = 1 # Loop counter


# This thread will wait for Ctrl+Alt+q sequence to quit
def readkey_thread():
    global do_measurement
    # kbd.wait('ctrl+alt+q')
    # print("\033[91m" + "Terminating after next readout..." + "\033[0m")
    # do_measurement = False
    while do_measurement:
        kbd.read_key()
        if kbd.is_pressed('ctrl+alt+q'):
            print("\033[91m" + "Stopping..." + "\033[0m")
            do_measurement = False
        # else:
        #     sleep(1)


# Convert voltage to pressure in mbar
def v2mbar(V):
    # Values from Preiffer manual
    a = 1.667
    b = 11.46
    # Values from Yannik's calibration
    #a = 1.674
    #b = 11.46
    return 10**(a*V-b)


# Main loop
scope = ps2000()
handle = scope.open()
if handle > 0:
    try:
        scope.setChannel(channel=0, state=1, Vmax=6)  # Channel A, max 20V
        scope.setChannel(channel=1, state=0, Vmax=6)  # Channel B, max 20V
        scope.setTrigger(source=None)  # Disable trigger (source = None)
        scope.setSampling(no_of_samples=10, extra_ADC_bits=4)

        # Create a thread that will wait for Esc key to finish measurements
        Thread(target=readkey_thread, daemon=True).start()
        print(f'Reading data from pressure gauge every {loopdelay} sec. Logs will be saved to {logfile}')
        print("\033[92m" + "Press Ctrl+Alt+q to finish" + "\033[0m")
        start = dt.now()

        while do_measurement:
            # Make several readouts and average
            V_list = []
            for i in range(n_avg):
                v1 = scope.getVoltage()
                if v1 == 0:
                    print("Error getting voltage. Skipping this iteration.")
                    continue
                V_list.append(v1[0]) # Save value from channel A
                sleep(avgdelay)
            voltage = np.mean(V_list) # Average over n_avg readouts
            now = dt.now()
            mbar = v2mbar(voltage) # Convert voltage to mbar
            print(f"{now}:   {voltage:.3f} V    {mbar:.3e} mbar")
            # Save time in timestamps (seconds since 01.01.1970)
            time.append(dt.timestamp(now))
            volt.append(voltage)
            loop_count += 1
            if loop_count > n_cycles:
                break
            # Sleep, but check regularly if exit is requested
            for i in range(round(loopdelay)):
                sleep(1)
                if not do_measurement:
                    break
        np.savetxt(logfile, np.transpose((time, volt)), fmt=('%10.0f','%10.6f'), header=f'{start}')
    finally:
        scope.close()


