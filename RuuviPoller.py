import asyncio
from datetime import datetime
from dataclasses import dataclass
from ruuvitag_sensor.ruuvi import RuuviTagSensor

@dataclass
class RuuviData:
    timestamp:int
    data:dict

#Tag whitelist
lastTagCheckIn = {}
activeTagData:dict[str, RuuviData] = {}
tagDataSem = asyncio.Semaphore()
async def polltags(whitelist):
    while(1):
        generator = RuuviTagSensor.get_data_async(macs=whitelist)
        try:
            generator = RuuviTagSensor.get_data_async(macs=whitelist)
            async for found_data in generator: #TODO: Need a way to gracefully break out of this. anext half worked.
                mac = found_data[0]
                timestamp = datetime.timestamp(datetime.now())
                async with tagDataSem:
                    #Always overwrite the old data because we only care about the latest.
                    activeTagData[mac] = RuuviData(timestamp, found_data[1])
                    lastTagCheckIn[mac] = timestamp
        except StopAsyncIteration:
            del(generator) #This doesn't actually stop the previous subprocess.
            print("ERROR: Generator terminated unexpectedly.")

async def minutes_since_last_checkin(mac:str)->float|None:
    async with tagDataSem:
        if mac in lastTagCheckIn:
            return((datetime.timestamp(datetime.now()) - lastTagCheckIn[mac])/60)
        else:
            None

async def getLatestData()->dict[str, RuuviData]:
    async with tagDataSem:
        tagData = activeTagData.copy()
        activeTagData.clear()

    return tagData
