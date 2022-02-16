"""
Python module to work with PicoScope 2204A.
Currently, the only functionality implemented is reading voltage in Block mode and Triggering.
No ETS (higher time resolution for periodic signals) functionality yet.

@author: Ilya Radko
"""

import os
from ctypes import cdll, c_int16, c_int32, byref, create_string_buffer
from time import sleep
from math import log2, ceil

class ps2000:

    # PicoScope INFO constants - used by ps2000_get_unit_info():
    PS_INFO = {
        "drv_version":  c_int16(0),     # Version number of the DLL used
        "usb_version":  c_int16(1),     # USB version used for connection (e.g., "1.1", "2.0", "3.0")
        "hw_version":   c_int16(2),     # E.g., "1"
        "model_number": c_int16(3),     # E.g., "2204A"
        "serial_number":c_int16(4),     # E.g., "IT834/502"
        "calibr_date":  c_int16(5),     # Calibration date, e.g. "06Jul20"
        "error_code":   c_int16(6),     # Current error code (see getError() for details)
        "krnl_drv_ver": c_int16(7),     # Version number of the kernel driver (low-level driver)
        "driver_path":  c_int16(8)      # Path of the currently used DLL driver
    }

    # PicoScope voltage range constants - used by getRange() and setTrigger():
    PS_RANGE = {
        "10mV":  0,
        "20mV":  1,
        "50mV":  2,
        "100mV": 3,
        "200mV": 4,
        "500mV": 5,
        "1V":    6,
        "2V":    7,
        "5V":    8,
        "10V":   9,
        "20V":   10,
        "50V":   11,
        "max_range": 12
    }

    # PicoScope measurement coupling mode
    PS_COUPLING = {
        "AC": c_int16(0),
        "DC": c_int16(1)
    }

    # ADC constant: max value returned by ADC
    PS_MAX_ADC_VALUE = 32767

    # Channel enumeration
    chDict = {0: "A", 1: "B", 2: "C", 3: "D"}

    def __init__(self):
        # Load dll from the same folder as this module
        path = os.path.dirname(os.path.realpath(__file__))
        self.dll = cdll.LoadLibrary(path + "\ps2000.dll")
        # Device variables
        self.handle = c_int16(0)  # PicoScope handle (0 = no device)
        self.info = {}  # Device info dictionary
        self.channel = [False, False, False, False]  # Channels on which measurements are taken (0: A, 1: B, 2: C, 3: D)
        self.range = [12, 12, 12, 12]    # Currently selected range on channels (Max_range, see PS_RANGE)
        self.trigger_range = 12          # Range for the trigger (seems to be the last configured range on a channel?)
        self.oversample = c_int16(0)     # Currently selected oversample (see setSampling() for details)
        self.no_of_samples = c_int32(0)  # Number of samples to collect in one block
        self.timebase = c_int16(0)       # Sampling interval on log_2 scale (see setSampling() for details)


    def open(self):
        """ Get a handle of the PS2000 device and request device info.

        @return: handle (>0), 0 (no PS device found), or -1 (found, but fails to open)
        """
        # If device is already opened, then close it first (will reset it)
        if self.handle.value > 0:
            self.close()
        # Undocumented fix to hide splash screen
        self.dll.ps2000_apply_fix(c_int32(0x1ced9168), c_int32(0x11e6))
        self.handle.value = self.dll.ps2000_open_unit()
        if self.handle.value < 0:
            print("PicoScope fails to open")
        elif self.handle.value == 0:
            print("No PicoScope device found")
        else:
            self.getDeviceInfo()
            print(f"Found PicoScope {self.info['name']}, calibrated on {self.info['calib']}")
        return self.handle.value


    def close(self):
        """ Close and release a PicoScope device.

        @return: 0 if handle is not valid
        """
        self.dll.ps2000_close_unit(self.handle)
        self.handle.value = 0
        self.info = {}
        self.channel = [False, False, False, False]  # Channels on which measurements are taken (0: A, 1: B, 2: C, 3: D)
        self.range = [12, 12, 12, 12]   # Currently selected range on channels (Max_range, see PS_RANGE)
        self.trigger_range = 12  # Range for the trigger
        self.oversample.value = 0
        self.no_of_samples.value = 0
        self.timebase.value = 0


    def getDeviceInfo(self):
        """ Request some text information about the device.
        Other information is also available, but not requested here.

        @return: nothing. Class' dictionary self.info is filled out.
        """
        buf = create_string_buffer(b'\x00' * 256)    # 256-byte buffer should be sufficient
        # Request the name of the PicoScope variant
        strlen = self.dll.ps2000_get_unit_info(self.handle, buf, c_int16(len(buf)), self.PS_INFO["model_number"])
        if strlen != 0:
            self.info['name'] = buf.value.decode("utf-8")

        # Request the device calibration date
        strlen = self.dll.ps2000_get_unit_info(self.handle, buf, c_int16(len(buf)), self.PS_INFO["calibr_date"])
        if strlen != 0:
            self.info['calib'] = buf.value.decode("utf-8")


    def getError(self):
        """ Request the status of the PicoScope and print a corresponding text message.

        @return: status code of the device (0 = OK, non-zero for error)
        """
        bufLen = 8  # 8-byte buffer should be sufficient
        buf = create_string_buffer(b'\x00' * bufLen)
        # Request the current status code of the PicoScope
        strlen = self.dll.ps2000_get_unit_info(self.handle, buf, c_int16(bufLen), self.PS_INFO["error_code"])
        # Try to convert the status code string to integer
        if strlen == 0:
            print("Could not obtain the status code of the PicoScope.")
            return
        codeStr = buf.value.decode("utf-8")
        try:
            code = int(codeStr)
        except ValueError:
            print("The returned status code is invalid.")
            return
        # Print the corresponding text message
        errCodes = {
            0: "The oscilloscope is functioning correctly.",
            1: "Attempt has been made to open more than PS2000_MAX_UNITS devices.",
            2: "Not enough memory on the host machine.",
            3: "An oscilloscope could not be found.",
            4: "Unable to download firmware.",
            5: "The oscilloscope is not responding to commands from the PC.",
            6: "The device configuration is corrupt or missing.",
            7: "The OS is not supported by this driver."
        }
        print(errCodes[code])
        return code


    def getRange(self, maxVoltage=20):
        """ Get a constant determining the optimum PicoScope working range
        depending on the maximum expected voltage.

        @param int maxVoltage: maximum expected voltage in Volts
        @return: int range constant to be used in ps2000_set_channel() and for conversion adc2mV() and mV2adc()
        """
        if   maxVoltage <= 0.010:
            return self.PS_RANGE["10mV"]
        elif maxVoltage <= 0.020:
            return self.PS_RANGE["20mV"]
        elif maxVoltage <= 0.050:
            return self.PS_RANGE["50mV"]
        elif maxVoltage <= 0.100:
            return self.PS_RANGE["100mV"]
        elif maxVoltage <= 0.200:
            return self.PS_RANGE["200mV"]
        elif maxVoltage <= 0.500:
            return self.PS_RANGE["500mV"]
        elif maxVoltage <= 1:
            return self.PS_RANGE["1V"]
        elif maxVoltage <= 2:
            return self.PS_RANGE["2V"]
        elif maxVoltage <= 5:
            return self.PS_RANGE["5V"]
        elif maxVoltage <= 10:
            return self.PS_RANGE["10V"]
        elif maxVoltage <= 20:
            return self.PS_RANGE["20V"]
        elif maxVoltage <= 50:
            return self.PS_RANGE["50V"]
        else:
            return self.PS_RANGE["max_range"]


    def adc2mV(self, rawADC, range):
        """ Convert raw ADC values to voltage (in mV) based on the current PicoScope range

        @param int rawADC: raw ADC value returned by the PicoScope.
        @param int range: currently configured range constant
        @return: list of mV values converted from rawADC values
        """
        # Get voltage range in mV based on range constant:
        ranges = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000]
        mVrange = ranges[range]
        return (rawADC * mVrange)/self.PS_MAX_ADC_VALUE


    def mV2adc(self, mV, range):
        """ Convert voltage (in mV) to raw ADC value based on the currect PicoScope range

        @param float mV: voltage in mV
        @param int range: currently configured range constant
        @return: raw ADC value converted from voltage
        """
        ranges = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000]
        mVrange = ranges[range]
        return round((mV * self.PS_MAX_ADC_VALUE)/mVrange)


    def setChannel(self, channel, state, Vmax, coupling=1):
        """ Configure a channel

        @param int channel: Channel to configure (zero-based number: 0=A, 1=B, etc.)
        @param int state: On/Off state (0=Off, 1=On)
        @param int Vmax: Maximum expected voltage in Volts. All channels must have the same Vmax!
        @param int coupling: AC/DC coupling mode (0=AC, 1=DC)
        @return: 0 on error, non-zero on success
        """
        if channel < 0 or channel > 3:
            print("Invalid channel number.")
            return 0
        if state != 0:
            self.channel[channel] = True  # Enable the channel
        # Get a voltage range constant and save it in Class attribute
        self.range[channel] = self.getRange(Vmax)
        # Trigger range seems to be the last configured range on a channel(?)
        self.trigger_range = self.range[channel]
        code = self.dll.ps2000_set_channel(self.handle, c_int16(channel), c_int16(state),
                                           c_int16(coupling), c_int16(self.range[channel]))
        if code == 0:
            print(f"Failed to set up channel {self.chDict[channel]}.")
            self.getError()

        return code


    def setTrigger(self, source, level=0, edge=0, delay=0, timeout=0):
        """ Configure triggering.
        Since ETS mode is not implemented yet, we also disable ETS here.

        @param int source: Trigger channel (None=disable trigger, 0=A, 1=B, 2=C, 3=D)
        @param int level: Threshold level, in Volts
        @param int edge: Edge direction (0=Rising, 1=Falling)
        @param int delay: Delay between trigger and data collection, in % of the requested data length
        @param int timeout: Timeout in ms to wait for trigger (0 = wait forever)
        @return: 0 on error, non-zero on success
        """
        # Convert trigger threshold level from volts to ADC counts:
        threshold = self.mV2adc(level*1000, self.trigger_range)
        if source is None:
            source = 5  # PicoScope constant to disable trigger
        code = self.dll.ps2000_set_trigger(self.handle, c_int16(source),
                                           c_int16(threshold), c_int16(edge),
                                           c_int16(delay), c_int16(timeout))
        if code == 0:
            print("Failed to set up a trigger.")
            self.getError()
        # Disable ETS mode:
        self.dll.ps2000_set_ets(self.handle, 0, 0, 0)
        return code


    def setSampling(self, no_of_samples, extra_ADC_bits, timebase=0):
        """ Set up sampling rate and amount of oversample

        @param int no_of_samples: The number of samples to be recorded in
                one block and averaged over.
        @param float extra_ADC_bits: 0..4. It is possible to increase
                the ADC resolution from 8 bits up to 12 bits. Increase of
                ADC resolution by 1 bit leads to 4x longer sampling interval:
                    oversampling_interval = sampling_interval * 4^extra_bits
                Can be any float number between 0 and 4.
        @param int timebase: Required sampling interval on log_2 scale.
                Zero value (timebase=0) sets minimum sampling interval
                (10ns for 2204A single channel and 20ns for two channels).
                Increasing timebase by 1 will double the sampling interval:
                    sampling_interval = min_interval * 2^timebase
        @return: 0 on error, non-zero on success
        """
        # Calculate oversample ratio: oversampling_interval/sampling_interval
        self.oversample.value = round(4**extra_ADC_bits)
        # Save to class attribute
        self.no_of_samples.value = no_of_samples
        # Check minimum required timebase
        enabled_channels = self.channel.count(True)  # Number of enabled channels
        if enabled_channels == 0:
            print("No enabled channels found. Enable at least one channel with setChannel().")
            return 0
        min_timebase = ceil(log2(enabled_channels))
        if timebase < min_timebase:
            print(f"Timebase value of {timebase} is too small. For {enabled_channels} enabled channels, ",
                  f"it has to be at least {min_timebase}. Setting it to the minimum required.")
            timebase = min_timebase
        self.timebase.value = timebase
        # Prepare return variables (sent as pointers)
        time_interval = c_int32()  # Effective time interval between samples
        time_units = c_int16()     # Most suitable time units (needed for other API calls)
        max_samples = c_int32()    # Maximum number of samples that can be recorded in one block
        code = self.dll.ps2000_get_timebase(self.handle, self.timebase, self.no_of_samples,
                                            byref(time_interval), byref(time_units), self.oversample,
                                            byref(max_samples))

        if code == 0:
            print("Error setting up sampling rate for measurement.")
            self.getError()
            return code

        if max_samples.value < no_of_samples:
            print(f"Not enough memory for the requested number of samples in a single block." +
                  f"Decreasing it to {max_samples.value}.")
            self.no_of_samples = max_samples

        # Debug message:
        # print(f"Recording data in blocks of {self.no_of_samples.value} samples with " +
        #       f"{time_interval.value} ns interval between samples.")
        return code


    def getVoltage(self):
        """Read out voltage as configured with setChannel(), setTrigger(), setSampling() and return
        a list of readings from all four channels in Volts

        @return: List of voltages in Volts
        TODO: processing of overflow variable
        """
        # Check if the device is still connected
        code = self.dll.ps2000PingUnit(self.handle)
        if code == 0:
            print("Could not start measurements is Block mode.")
            self.getError()
            return code
        # Start sampling in Block mode
        collection_time_ms = c_int32(0)
        code = self.dll.ps2000_run_block(self.handle, self.no_of_samples, self.timebase,
                                         self.oversample, byref(collection_time_ms))
        if code == 0:
            print("Error recording data in block mode.")
            self.getError()
            return code
        # Wait for the sampling to finish
        sleep(collection_time_ms.value/1000)    # sleep() takes time in seconds
        while self.dll.ps2000_ready(self.handle) == 0:
            sleep(0.005)  # Sleep for 5 ms
        # Getting the values
        # Prepare four buffers to read voltage from four channels
        buf = [None, None, None, None]
        for i in range(4):
            if self.channel[i]:  # Channel enabled? If so, prepare an array to receive data from PicoScope.
                buf[i] = (c_int16 * self.no_of_samples.value)()  # Last pair of brackets are to instantiate the array
        overflow = c_int16(0)  # overflow bitmask
        samples = self.dll.ps2000_get_values(self.handle, buf[0], buf[1], buf[2], buf[3],
                                             byref(overflow), self.no_of_samples)
        # Stopping block mode
        code = self.dll.ps2000_stop(self.handle)
        if code == 0:
            self.getError()
            return code
        # Processing the returned data
        overflow = overflow.value  # Convert to regular int value
        if samples == 0:
            self.getError()
            return samples
        # Averaging the returned data
        voltage = [None, None, None, None]  # Voltage read-out from four channels
        for ch in range(4):
            if self.channel[ch]:  # Channel enabled?
                total = 0
                for i in range(samples):
                    total += buf[ch][i]
                voltage[ch] = self.adc2mV(total/samples, self.range[ch])/1000  # Averaged voltage in Volts
                if (overflow >> ch) & 1 == 1:  # Overflow on this channel?
                    print(f"Warning: overflow on channel {self.chDict[ch]}")
        return voltage

