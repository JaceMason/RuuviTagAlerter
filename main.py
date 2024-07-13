import asyncio
import os
import shutil
import time

from datetime import datetime

import EmailHandler
import GAPIHelper
import ConfigManager as config
import RuuviPoller as ruuvi
from DataHandler import DataHandler

programStartTime = time.time()
scriptDir = os.path.dirname(os.path.realpath(__file__))

#User config. For now, you need to manually edit these. TODO: Put these into a local file.
#-------------------------------
pollEvery_thMinute = 10 #Example: 10 = Poll at 3:00, 3:10, 3:20, 3:30, etc. Not well tested.

emailAlertTimeoutHr = 5 # Send an email every x hours until the temperature goes back within bounds.

tagFirstTimeoutMin = 5 # Notify when tag has not checked since script start after x minutes
tagTimeoutTimeMin = 30 # Notify when tag has not checked in after x minutes

timeoutEmailDelayTimeSec = 60 * 60 * 24 #Timeout emails can be sent only once every 24 hours per RuuviTag

debugMode = False #Set this if you want to ensure that you are not actually sending emails while testing
#-------------------------------

EmailHandler.debugOnly = debugMode
GAPIHelper.get_authorization()
if not GAPIHelper.is_authorized():
    print("All permissions are needed to properly run at the moment. (Maybe later we can feature piece meal!)")
    exit()

config.load_local_file()

#TODO: Consider combining into a class
lastTimeoutEmailDict = {}
ruuviTagDataHandler:dict[str, DataHandler] = {}
for mac, cfg in config.tagConfigs.items():
    lastTimeoutEmailDict[mac] = float('-inf')
    ruuviTagDataHandler[mac] = DataHandler(mac, emailAlertTimeoutHr)

def send_timeout_alert(mac, lastCheckinTime, sensorName:str):
    if time.time() >=  lastTimeoutEmailDict[mac] + timeoutEmailDelayTimeSec:
        message = f"The greenhouse sensor '{sensorName}' has not sent a signal in {lastCheckinTime:.2f} minutes. Verify it is still within range and the battery is good.\n"
        message += f"This message will repeat in {(timeoutEmailDelayTimeSec/60/60):.2f} hours if it is not resolved.\n"
        message += "\n-The Greenhouse Monitor"
        status = EmailHandler.send_message("Automatic Greenhouse Timeout Alert", message, rxEmails=None, debugOnly=debugMode)
        if status != None:
            lastTimeoutEmailDict[mac] = time.time()

def handle_tag_data(tagData):
    recentMacs = list(tagData.keys())
    config.get_latest_config(recentMacs)
    for mac, cfg in config.tagConfigs.items():
        if not cfg.enabled:
            continue
        if mac not in tagData:
            print(f"{cfg.name}({mac}) did not collect data")
            continue
        ruuviTagDataHandler[mac].handle_data(tagData[mac], cfg)

async def check_tag_timeout():
    for mac, cfg in config.tagConfigs.items():
        if not cfg.enabled:
            continue
        lastCheckin = await(ruuvi.minutes_since_last_checkin(mac))
        if lastCheckin != None:
            if lastCheckin > tagTimeoutTimeMin:
                print(f"{cfg.name} has not sent a signal in {lastCheckin:.2f} minutes. Verify that it is in range and the battery is still good.")
                send_timeout_alert(mac, lastCheckin, cfg.name)
                
        else:
            #TODO: Handle case where the tag has not checked in at all.
            runtimeMins = (time.time() - programStartTime)/60
            if runtimeMins > tagFirstTimeoutMin:
                print(f"{cfg.name} has yet to send any signal. Verify that it is in range and the battery is not dead.")
                print(f"The monitor has been up for {runtimeMins:.2f} minute(s)")


async def main():
    #TODO: need to find a way to gracefully stop this task while it is stuck waiting for the generator
    task = asyncio.create_task(ruuvi.polltags([]))

    while True:
        #Get latest tag data at the start of every 10th minute (Based on system clock)
        timeDiff = pollEvery_thMinute*60 - int(time.time()) % (pollEvery_thMinute*60)
        print(f"Next poll in {timeDiff/60:.2f}minutes [{timeDiff}seconds]")
        await asyncio.sleep(timeDiff)

        tagData = await ruuvi.getLatestData()
        handle_tag_data(tagData)
        await check_tag_timeout()
        

if __name__ == "__main__":
    asyncio.run(main())