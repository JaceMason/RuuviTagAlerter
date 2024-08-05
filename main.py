import asyncio
import os
import time
import signal

import EmailHandler
import GAPIHelper
import Log

import ConfigManager as config
import RuuviPoller as ruuvi
from DataHandler import DataHandler

#For better termination when run as a service
signal.signal(signal.SIGTERM, lambda num, frame:exit())

programStartTime = time.time()
scriptDir = os.path.dirname(os.path.realpath(__file__))

#User config. For now, you need to manually edit these. TODO: Put these into a local file.
#-------------------------------
pollEvery_thMinute = 5 #Example: 10 = Poll at 3:00, 3:10, 3:20, 3:30, etc. Not well tested.

emailAlertTimeoutHr = 5 # Send an email every x hours until the temperature goes back within bounds.

tagTimeoutTimeMin = 30 # Notify when tag has not checked in after x minutes

timeoutEmailDelayTimeSec = 60 * 60 * 24 #Timeout emails can be sent only once every 24 hours per RuuviTag

uploadErrorLogIntervalSec = 60 * 60 #Put the error log into drives once every hour

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

def send_timeout_alert(mac, lastCheckinTimeMin:float, sensorName:str, neverCheckedIn:bool):
    if time.time() <  lastTimeoutEmailDict[mac] + timeoutEmailDelayTimeSec:
        return #Prevent email spam when the tag hasn't checked in

    message = ""
    if neverCheckedIn:
        message = f"The greenhouse monitor has been on for {lastCheckinTimeMin:.2f} minutes, but the sensor '{sensorName}' has not sent a signal yet. Verify it is still within range and the battery is good.\n"
    else:
        message = f"The greenhouse sensor '{sensorName}' has not sent a signal in {lastCheckinTimeMin:.2f} minutes. Verify it is still within range and the battery is good.\n"

    message += f"This message will repeat in {(timeoutEmailDelayTimeSec/60/60):.2f} hours if it is not resolved.\n"
    print(message)
    message += "\n-The Greenhouse Monitor"
    status = EmailHandler.send_message("Automatic Greenhouse Timeout Alert", message, rxEmails=None)
    if status != None:
        lastTimeoutEmailDict[mac] = time.time()

def handle_tag_data(tagData):
    recentMacs = list(tagData.keys())
    config.get_latest_config(recentMacs)
    for mac in recentMacs:
        ruuviTagDataHandler.setdefault(mac, DataHandler(mac, emailAlertTimeoutHr))

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

        neverCheckedIn = False

        lastCheckin = await(ruuvi.minutes_since_last_checkin(mac))
        if lastCheckin == None:
            neverCheckedIn = True
            lastCheckin = (time.time() - programStartTime)/60

        if lastCheckin > tagTimeoutTimeMin:
            send_timeout_alert(mac, lastCheckin, cfg.name, neverCheckedIn)

async def main():
    #TODO: need to find a way to gracefully stop this task while it is stuck waiting for the generator
    task = asyncio.create_task(ruuvi.polltags([]))
    asyncio.gather(task) #Let's us see exceptions instead of it failing silently. (Does not stop anything yet)
    nextErrorLogUpload = time.time() + uploadErrorLogIntervalSec

    failcount = 0
    while True:
        #Get latest tag data at the start of every 10th minute (Based on system clock)
        timeDiff = pollEvery_thMinute*60 - int(time.time()) % (pollEvery_thMinute*60)
        print(f"Next poll in {timeDiff/60:.2f}minutes [{timeDiff}seconds]")
        await asyncio.sleep(timeDiff)

        try:
            tagData = await ruuvi.getLatestData()
            handle_tag_data(tagData)
            await check_tag_timeout()
            failcount = 0
        except Exception as e:
            failcount += 1
            Log.log(str(e))

        if time.time() > nextErrorLogUpload:
            if Log.push_log_to_drive():
                nextErrorLogUpload = time.time() + uploadErrorLogIntervalSec

        #Bit of backoff. Don't ever want to terminate the program, but don't want to be spamming the network
        if failcount > 1:
            await asyncio.sleep(60 * 10 * min(failcount, 6))


if __name__ == "__main__":
    asyncio.run(main())
