
import asyncio
import functools
import concurrent.futures
import time

from enum import IntEnum

from bluepy.btle import BTLEException
import eq3bt as eq3
from .connection import BTLEConnection

from .. import utils
from .. import fhem

class Mode(IntEnum):
    """ Thermostat modes. """
    Unknown = -1
    Closed = 0
    Open = 1
    Auto = 2
    Manual = 3
    Away = 4
    Boost = 5

# TODO set schedules
# TODO set windowOpen, windowOpenTime, eco/comfortTemperature

class eq3bt:

    def __init__(self, logger):
        self.logger = logger
        self.set_list_conf = {
            "on": {},
            "off": {},
            "desiredTemperature": {"args": ["target_temp"], "format": "slider,4.5,0.5,29.5,1"},
            "updateStatus": {},
            "boost": {"args": ["target_state"], "format": "on,off"},
            "mode": {"args": ["target_mode"], "format": "manual,automatic"},
            "eco": {},
            "comfort": {},
            "childlock": {"args": ["target_state"], "format": "on,off"}
        }
        self._last_update = 0
        return

    # FHEM FUNCTION
    async def Define(self, hash, args, argsh):
        self.hash = hash
        mac = args[3]
        self.hash["MAC"] = mac
        self.logger.info(f"Define: eq3bt {mac}")
        self.thermostat = FhemThermostat(self.logger, mac)
        self._presence_task = asyncio.create_task(self.check_online())
        return ""

    # FHEM FUNCTION
    async def Undefine(self, hash, args, argsh):
        self._presence_task.cancel()
        return
    
    async def check_online(self):
        while True:
            if time.time() - self._last_update > (60 * 30):
                await fhem.readingsSingleUpdate(self.hash, "presence", "offline", 1)
                await fhem.readingsSingleUpdate(self.hash, "state", "offline", 1)
            await self.update_all()
            await asyncio.sleep(300)

    # FHEM FUNCTION
    async def Set(self, hash, args, argsh):
        return await utils.handle_set(self.set_list_conf, self, hash, args, argsh)

    async def update_all(self):
        self.logger.debug("start update_all")
        with concurrent.futures.ThreadPoolExecutor() as pool:
            await asyncio.get_event_loop().run_in_executor(
                pool, functools.partial(self.thermostat.update_all))
        await self.update_all_readings()

    async def update_all_readings(self):
        await self.update_readings()
        await self.update_id_readings()
        await self.update_schedule_readings()
    
    async def update_readings(self):
        self._last_update = time.time()
        await fhem.readingsBeginUpdate(self.hash)
        await fhem.readingsBulkUpdateIfChanged(self.hash, "battery", self.thermostat.battery)
        await fhem.readingsBulkUpdateIfChanged(self.hash, "boost", self.thermostat.boost)
        await fhem.readingsBulkUpdateIfChanged(self.hash, "childlock", self.thermostat.locked)
        await fhem.readingsBulkUpdateIfChanged(self.hash, "desiredTemperature", self.thermostat.target_temperature)
        await fhem.readingsBulkUpdateIfChanged(self.hash, "ecoTemperature", self.thermostat.eco_temperature)
        await fhem.readingsBulkUpdateIfChanged(self.hash, "temperatureOffset", self.thermostat.temperature_offset)
        await fhem.readingsBulkUpdateIfChanged(self.hash, "comfortTemperature", self.thermostat.comfort_temperature)
        await fhem.readingsBulkUpdateIfChanged(self.hash, "mode", self.thermostat.mode)
        await fhem.readingsBulkUpdateIfChanged(self.hash, "state", self.thermostat.state)
        await fhem.readingsBulkUpdateIfChanged(self.hash, "completeState", self.thermostat.mode_readable)
        await fhem.readingsBulkUpdateIfChanged(self.hash, "valvePosition", self.thermostat.valve_state)
        await fhem.readingsBulkUpdateIfChanged(self.hash, "awayEnd", self.thermostat.away_end)
        await fhem.readingsBulkUpdateIfChanged(self.hash, "windowOpen", self.thermostat.window_open)
        await fhem.readingsBulkUpdateIfChanged(self.hash, "windowOpenTemperature", self.thermostat.window_open_temperature)
        await fhem.readingsBulkUpdateIfChanged(self.hash, "windowOpenTime", self.thermostat.window_open_time)
        await fhem.readingsBulkUpdateIfChanged(self.hash, "presence", "online")
        await fhem.readingsEndUpdate(self.hash, 1)

    async def update_id_readings(self):
        await fhem.readingsBeginUpdate(self.hash)
        await fhem.readingsBulkUpdateIfChanged(self.hash, "firmware", self.thermostat.firmware_version)
        await fhem.readingsBulkUpdateIfChanged(self.hash, "serialNumber", self.thermostat.device_serial)
        await fhem.readingsEndUpdate(self.hash, 1)

    async def update_schedule_readings(self):
        await fhem.readingsBeginUpdate(self.hash)
        for day in self.thermostat.schedule.keys():
            reading = f"schedule_{day}_1"
            if self.thermostat.schedule[day].base_temp == 0 or isinstance(self.thermostat.schedule[day].next_change_at, int):
                await fhem.readingsBulkUpdateIfChanged(self.hash, reading, "-")
                last_change = "00:00"
            else:
                await fhem.readingsBulkUpdateIfChanged(self.hash, reading, f"00:00 - {self.thermostat.schedule[day].next_change_at.strftime('%H:%M')}: {self.thermostat.schedule[day].base_temp}")
                last_change = self.thermostat.schedule[day].next_change_at.strftime('%H:%M')
            last_schedule = False
            for h in range(0,6):
                reading = f"schedule_{day}_{h+2}"
                if h == 6 or self.thermostat.schedule[day].hours[h].target_temp == 0 or isinstance(self.thermostat.schedule[day].hours[h].next_change_at, int) or last_schedule:
                    if last_schedule:
                        await fhem.readingsBulkUpdateIfChanged(self.hash, reading, "-")
                    else:
                        value = f"{last_change} - 00:00: {self.thermostat.schedule[day].base_temp}"
                        await fhem.readingsBulkUpdateIfChanged(self.hash, reading, value)
                    last_schedule = True
                else:
                    value = f"{last_change} - {self.thermostat.schedule[day].hours[h].next_change_at.strftime('%H:%M')}: {self.thermostat.schedule[day].hours[h].target_temp}"
                    last_change = self.thermostat.schedule[day].hours[h].next_change_at.strftime('%H:%M')
                    await fhem.readingsBulkUpdateIfChanged(self.hash, reading, value)
        await fhem.readingsEndUpdate(self.hash, 1)
    
    async def set_and_update(self, fct):
        await utils.run_blocking(fct)
        await self.update_readings()


    # SET Functions BEGIN
    async def set_on(self):
        asyncio.create_task(self.set_and_update(functools.partial(self.thermostat.activate_comfort)))
    
    async def set_off(self):
        asyncio.create_task(self.set_and_update(functools.partial(self.thermostat.set_target_temperature, 4.5)))
    
    async def set_desiredTemperature(self, params):
        temp = float(params["target_temp"])
        asyncio.create_task(self.set_and_update(functools.partial(self.thermostat.set_target_temperature, temp)))
    
    async def set_updateStatus(self):
        asyncio.create_task(self.update_all())
    
    async def set_boost(self, params):
        asyncio.create_task(self.set_and_update(functools.partial(self.thermostat.boost, params["target_state"] == "on")))
    
    async def set_mode(self, params):
        target_mode = params["target_mode"]
        if target_mode == "automatic":
            target_mode = eq3.Mode.Auto
        else:
            target_mode = eq3.Mode.Manual
        asyncio.create_task(self.set_and_update(functools.partial(self.thermostat.mode, target_mode)))
    
    async def set_eco(self):
        asyncio.create_task(self.set_and_update(functools.partial(self.thermostat.activate_eco)))
    
    async def set_comfort(self):
        asyncio.create_task(self.set_and_update(functools.partial(self.thermostat.activate_comfort)))
    
    async def set_childlock(self, params):
        asyncio.create_task(self.set_and_update(functools.partial(self.thermostat.locked, params["target_state"] == "on")))
    # SET Functions END

class FhemThermostat(eq3.Thermostat):

    def __init__(self,logger, mac):
        self.logger = logger
        super(FhemThermostat, self).__init__(mac, BTLEConnection)
    
    def update_all(self):
        super().update()
        super().query_id()
        for day in range(0, 6):
            super().query_schedule(day)

    def set_target_temperature(self, temp):
        self.target_temperature = temp
    
    @property
    def mode(self):
        if self._mode == Mode.Boost:
            return "boost"
        elif self._mode == Mode.Away:
            return "away"
        elif self._mode == Mode.Closed:
            return "manual"
        elif self._mode == Mode.Open:
            return "manual"
        elif self._mode == Mode.Manual:
            return "manual"
        elif self._mode == Mode.Auto:
            return "automatic"

    @property
    def state(self):
        if self._mode == Mode.Boost:
            return "boost"
        elif self._mode == Mode.Away:
            return "away"
        elif self._mode == Mode.Closed:
            return "off"
        elif self._mode == Mode.Open:
            return "on"
        elif self._mode == Mode.Manual:
            return "manual"
        elif self._mode == Mode.Auto:
            return "automatic"

    @property
    def battery(self):
        if self.low_battery:
            return "low"
        return "ok"