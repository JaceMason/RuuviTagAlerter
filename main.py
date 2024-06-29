import asyncio
import os
import time

from datetime import datetime

import RuuviPoller as ruuvi

programStartTime = time.time()
scriptDir = os.path.dirname(os.path.realpath(__file__))

#Tag whitelist
macToName = {
    "E0:A0:D5:C6:6C:C3":"Front",
}
whitelist = list(macToName.keys())

tagTimeoutTime = 30 # Minutes
tagFirstTimeout = 5 # Minutes

def handle_tag_data(tagData):
    for mac in whitelist:
        if mac not in tagData:
            print(f"{macToName[mac]}({mac}) did not collect data")
            continue

        data = tagData[mac]
        data.data['temperature'] = data.data['temperature'] * 1.8 + 32 #'merica!

        last2Mac = "".join(mac.split(":")[-2:])
        filepath = f"{scriptDir}/{macToName[mac]}({last2Mac})_data.csv"
        #TODO Error handling
        dataToWrite = ""
        if not os.path.isfile(filepath):
            dataToWrite = "timestamp,"+ ",".join(data.data.keys()) + "\n"

        dataToWrite += str(data.timestamp) + "," + ",".join([str(val) for val in data.data.values()]) + "\n"
        file = open(filepath, 'a+')
        file.write(dataToWrite)
        file.close()
        print(f"{macToName[mac]} was {data.data['temperature']:.2f}F on {datetime.fromtimestamp(data.timestamp).strftime('%Y-%m-%d at %H:%M')}")

async def check_tag_timeout():
    for mac, name in macToName.items():
        lastCheckin = await(ruuvi.minutes_since_last_checkin(mac))
        if lastCheckin != None:
            if lastCheckin > tagTimeoutTime:
                #TODO: Handle timeout
                print(f"{name} has not sent a signal in {lastCheckin:2f} minute(s). Verify that it is in range and the battery is still good.")
                
        else:
            #TODO: Handle case where the tag has not checked in at all.
            runtimeMins = (time.time() - programStartTime)/60
            if runtimeMins > tagFirstTimeout:
                print(f"{name} has yet to send any signal. Verify that it is in range and the battery is not dead.")
                print(f"The monitor has been up for {runtimeMins:2f} minute(s)")


async def main():
    #TODO: need to find a way to gracefully stop this task while it is stuck waiting for the generator
    task = asyncio.create_task(ruuvi.polltags(whitelist))

    while True:
        #Get latest tag data at the start of every 10th minute (Based on system clock)
        timeDiff = 600 - int(time.time()) % 600
        print(f"Next poll in {timeDiff/60:.2f}minutes [{timeDiff}seconds]")
        await asyncio.sleep(timeDiff)

        tagData = await ruuvi.getLatestData()
        handle_tag_data(tagData)
        await check_tag_timeout()
        

if __name__ == "__main__":
    asyncio.run(main())