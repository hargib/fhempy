
import asyncio
import site
import subprocess
import socket

from .. import fhem, utils

class esphome:

    def __init__(self, logger):
        self.logger = logger
        self.proc = None
        self._set_list = {
            "start": {},
            "stop": {},
            "restart": {}
        }
        self._attr_list = {
            "disable": { "default": "0", "options": "0,1"}
        }
        return

    # FHEM FUNCTION
    async def Define(self, hash, args, argsh):
        self.hash = hash

        await utils.handle_define_attr(self._attr_list, self, hash)

        if self._attr_disable == "1":
            return

        await self.start_process()

        if await fhem.AttrVal(self.hash["NAME"], "room", "") == "":
            await fhem.CommandAttr(self.hash, hash["NAME"] + " room ESPHome")
            asyncio.create_task(self.create_weblink())

        return ""

    async def start_process(self):
        self._esphomeargs = [site.getuserbase() + "/bin/esphome", "esphome_config/", "dashboard"]

        try:
            self.proc = subprocess.Popen(self._esphomeargs)
        except:
            try:
                self._esphomeargs = ["esphome", "esphome_config/", "dashboard"]
                self.proc = subprocess.Popen(self._esphomeargs)
            except:
                return "Failed to execute esphome"

        await fhem.readingsSingleUpdate(self.hash, "state", "running", 1)

    async def stop_process(self):
        if self.proc:
            self.proc.terminate()
            self.proc = None
        await fhem.readingsSingleUpdate(self.hash, "state", "stopped", 1)

    async def create_weblink(self):
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        await fhem.CommandDefine(self.hash, "esphome_dashboard weblink iframe http://" + local_ip + ":6052/")
        await fhem.CommandAttr(self.hash, "esphome_dashboard htmlattr width='900' height='700' frameborder='0' marginheight='0' marginwidth='0'")
        await fhem.CommandAttr(self.hash, "esphome_dashboard room ESPHome")

    # FHEM FUNCTION
    async def Undefine(self, hash):
        self.proc.terminate()
        return

    async def Attr(self, hash, args, argsh):
        return await utils.handle_attr(self._attr_list, self, hash, args, argsh)

    async def set_attr_disable(self, hash):
        if self._attr_disable == "0":
            await self.start_process()
        else:
            await self.stop_process()

    async def Set(self, hash, args, argsh):
        return await utils.handle_set(self._set_list, self, hash, args, argsh)

    async def set_start(self, hash):
        await self.stop_process()
        await self.start_process()
        return ""

    async def set_stop(self, hash):
        await self.stop_process()
        return ""

    async def set_restart(self, hash):
        return await self.set_start(hash)