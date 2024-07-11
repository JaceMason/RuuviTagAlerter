import asyncio
import os
import shutil
import time

from datetime import datetime

import RuuviPoller as ruuvi
import EmailHandler
from DataHandler import DataHandler
import GAPIHelper

programStartTime = time.time()
scriptDir = os.path.dirname(os.path.realpath(__file__))

#User config. For now, you need to manually edit these. TODO: Put these into a local file.
#-------------------------------
pollEvery_thMinute = 5 #Example: 10 = Poll at 3:00, 3:10, 3:20, 3:30, etc. Not well tested.

# Thresholds in Fahrenheit that will prompt the script to send an email alert
lowerThresholdF = 35
upperThresholdF = 82

emailAlertTimeoutHr = 5 # Send an email every x hours until the temperature goes back within bounds.

tagFirstTimeoutMin = 5 # Notify when tag has not checked since script start after x minutes
tagTimeoutTimeMin = 30 # Notify when tag has not checked in after x minutes

timeoutEmailDelayTimeSec = 60 * 60 * 24 #Timeout emails can be sent only once every 24 hours per RuuviTag

debugMode = False #Set this if you want to ensure that you are not actually sending emails while testing
#-------------------------------

GAPIHelper.get_authorization()
if not GAPIHelper.is_authorized():
    print("All permissions are needed to properly run at the moment. (Maybe later we can feature piece meal!)")
    exit()

#Tag whitelist from file. User will need to manually edit this once it is created via template
tagMacFileTemplateLoc = scriptDir + "/RuuviTagMacs_template.csv"
tagMacFileLoc = scriptDir + "/RuuviTagMacs.csv"
macToName = {}
#TODO Error handling for unable to open (Maybe make a generic function because it looks like I am doing this sort of line read thing a lot)
if not os.path.exists(tagMacFileLoc):
    shutil.copy(tagMacFileTemplateLoc, tagMacFileLoc)
    print(f"Template file copied. Please add your RuuviTag Macs to the following file and run this script again:\n{os.path.normpath(tagMacFileLoc)}")
    exit()
with open(tagMacFileLoc, 'r') as macFile:
    macList = [line.strip().split(',') for line in macFile]
    #We skip the first line of the file because it is a csv header
    if macList[1][1] == "REPLACEWITHTAGNAME1":
        print(f"You need to edit the tag file name located at {os.path.normpath(tagMacFileLoc)}")
        exit()
    for mac, name in macList[1:]:
        macToName[mac] = name

whitelist = list(macToName.keys())

#TODO: Consider combining into a class
lastTimeoutEmailDict = {}
ruuviTagDataHandler:dict[str, DataHandler] = {}
for mac, name in macToName.items():
    lastTimeoutEmailDict[mac] = float('-inf')
    ruuviTagDataHandler[mac] = DataHandler(mac, name, upperThresholdF, lowerThresholdF, emailAlertTimeoutHr, debugOnly = debugMode)

def send_timeout_alert(mac, lastCheckinTime, sensorName:str):
    if time.time() >=  lastTimeoutEmailDict[mac] + timeoutEmailDelayTimeSec:
        message = f"The greenhouse sensor '{sensorName}' has not sent a signal in {lastCheckinTime:.2f} minutes. Verify it is still within range and the battery is good.\n"
        message += f"This message will repeat in {(timeoutEmailDelayTimeSec/60/60):.2f} hours if it is not resolved.\n"
        message += "\n-The Greenhouse Monitor"
        status = EmailHandler.send_message("Automatic Greenhouse Timeout Alert", message, rxEmails=None, debugOnly=debugMode)
        if status != None:
            lastTimeoutEmailDict[mac] = time.time()

def handle_tag_data(tagData):
    for mac in whitelist:
        if mac not in tagData:
            print(f"{macToName[mac]}({mac}) did not collect data")
            continue
        ruuviTagDataHandler[mac].handle_data(tagData[mac])

async def check_tag_timeout():
    for mac, name in macToName.items():
        lastCheckin = await(ruuvi.minutes_since_last_checkin(mac))
        if lastCheckin != None:
            if lastCheckin > tagTimeoutTimeMin:
                print(f"{name} has not sent a signal in {lastCheckin:.2f} minutes. Verify that it is in range and the battery is still good.")
                send_timeout_alert(mac, lastCheckin, name)
                
        else:
            #TODO: Handle case where the tag has not checked in at all.
            runtimeMins = (time.time() - programStartTime)/60
            if runtimeMins > tagFirstTimeoutMin:
                print(f"{name} has yet to send any signal. Verify that it is in range and the battery is not dead.")
                print(f"The monitor has been up for {runtimeMins:.2f} minute(s)")


async def main():
    #TODO: need to find a way to gracefully stop this task while it is stuck waiting for the generator
    task = asyncio.create_task(ruuvi.polltags(whitelist))

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