
import asyncio
import time

from .. import fhem
from ..xiaomi_gateway3 import xiaomi_gateway3
from .. import fhem_pythonbinding as fhepy

class xiaomi_gateway3_device:

    def __init__(self, logger):
        self.logger = logger
        self.gateway = None
        self.device_details = None
        self.last_update = 0
        return

    # FHEM FUNCTION
    async def Define(self, hash, args, argsh):
        self.hash = hash

        self.gw_name = args[3]
        self.did = args[4]
        
        hash['GATEWAY'] = self.gw_name
        hash['DID'] = self.did

        await fhem.readingsSingleUpdateIfChanged(self.hash, "state", "offline", 1)

        asyncio.create_task(self.connect_gw())
        self.offline_check_task = asyncio.create_task(self.offline_check())

        return ""

    async def offline_check(self):
        while True:
            if time.time() - self.last_update > 3700:
                await fhem.readingsSingleUpdateIfChanged(self.hash, "state", "offline", 1)
            await asyncio.sleep(300)
    
    async def connect_gw(self):
        while self.gateway is None:
            self.gateway = fhepy.getFhemPyDeviceByName(self.gw_name)
            if self.gateway:
                try:
                    self.gateway.register_device(self.did, self)
                    await fhem.readingsSingleUpdateIfChanged(self.hash, "state", "online", 1)
                except:
                    self.gateway = None
                    pass
            else:
                await fhem.readingsSingleUpdateIfChanged(self.hash, "state", f"gateway {self.gw_name} not found", 1)
            await asyncio.sleep(10)

    # FHEM FUNCTION
    async def Undefine(self, hash):
        self.offline_check_task.cancel()
        return

    # FHEM FUNCTION
    async def Set(self, hash, args, argsh):
        return

    async def update(self, data):
        self.last_update = time.time()

        # first update
        if self.device_details is None:
            self.device_details = self.gateway.get_device(self.did)
            await fhem.readingsSingleUpdateIfChanged(self.hash, "model", self.device_details['model'], 1)
            await fhem.readingsSingleUpdateIfChanged(self.hash, "sid", self.device_details['sid'], 1)

        # device is online    
        await fhem.readingsSingleUpdateIfChanged(self.hash, "state", "online", 1)

        # update data
        for reading in data:
            await fhem.readingsSingleUpdateIfChanged(self.hash, reading, data[reading], 1)