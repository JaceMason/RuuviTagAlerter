import asyncio
import os
import shutil
import time

from datetime import datetime

import RuuviPoller as ruuvi
from EmailHandler import GmailSender

programStartTime = time.time()
scriptDir = os.path.dirname(os.path.realpath(__file__))

#User config. For now, you need to manually edit these. TODO: Put these into a local file.
#-------------------------------
pollEvery_thMinute = 10 #Example: 10 = Poll at 3:00, 3:10, 3:20, 3:30, etc. Not well tested.

# Thresholds in Fahrenheit that will prompt the script to send an email alert
tempThreshUpperF = 110
tempThreshLowerF = 35

tagFirstTimeoutMin = 5 # Notify when tag has not checked since script start after x minutes
tagTimeoutTimeMin = 30 # Notify when tag has not checked in after x minutes

emailDelayTimeSec = 60 * 60 * 3 #Temperature alert emails can be sent only once every 3 hours. (total, not per tag)
timeoutEmailDelayTimeSec = 60 * 60 * 24 #Timeout emails can be sent only once every 24 hours per RuuviTag
#-------------------------------
emailer = GmailSender(authorizeOnStart=True, debugOnly=False)

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

lastEmailTime = float('-inf')
lastTimeoutEmailDict = {}
for mac in macToName.keys():
    lastTimeoutEmailDict[mac] = float('-inf')

emailListLoc = scriptDir+"/EmailList.txt"
emailList = []
try:
    with open(emailListLoc, 'r') as emailFile:
        emailList = [line.strip() for line in emailFile]
except:
    pass
if emailList == []:
    print(f"Please add emails to the following file if you would like to use the email alert feature.\n{emailListLoc}")

def check_and_send_temperature_alert(sensorName:str, temperatureF:float):
    if temperatureF > tempThreshUpperF:
        thresholdOfMsg = f"upper threshold of {tempThreshUpperF:.2f}F.\n"
    elif temperatureF < tempThreshLowerF:
        thresholdOfMsg = f"lower threshold of {tempThreshLowerF:.2f}F.\n"
    else:
        return #No alert needed, all is well!

    global lastEmailTime
    if time.time() >= lastEmailTime + emailDelayTimeSec:
        message = f"The greenhouse sensor '{sensorName}' is currently at {temperatureF:.2f}F and has exceeded the "
        message += thresholdOfMsg
        message += f"\nThis message will repeat every {emailDelayTimeSec/60/60} hours until it is resolved.\nSave those plants, good luck!\n\n-The Greenhouse Monitor"
        for email in emailList:
            status = emailer.send_message(email, "Automatic Greenhouse Temperature Alert", message)
            if status != None:
                lastEmailTime = time.time()

def send_timeout_alert(mac, lastCheckinTime, sensorName:str):
    if time.time() >=  lastTimeoutEmailDict[mac] + timeoutEmailDelayTimeSec:
        message = f"The greenhouse sensor '{sensorName}' has not sent a signal in {lastCheckinTime:.2f} minutes. Verify it is still within range and the battery is good.\n"
        message += f"This message will repeat in {(timeoutEmailDelayTimeSec/60/60):.2f} hours if it is not resolved.\n"
        message += "\n-The Greenhouse Monitor"
        for email in emailList:
            status = emailer.send_message(email, "Automatic Greenhouse Timeout Alert", message)
            if status != None:
                lastTimeoutEmailDict[mac] = time.time()

def handle_tag_data(tagData):
    for mac in whitelist:
        if mac not in tagData:
            print(f"{macToName[mac]}({mac}) did not collect data")
            continue

        data = tagData[mac]
        data.data.pop("acceleration")
        data.data.pop("acceleration_x")
        data.data.pop("acceleration_y")
        data.data.pop("acceleration_z")
        data.data.pop("tx_power")
        data.data.pop("movement_counter")
        data.data.pop("data_format")
        tempF = data.data['temperature'] * 1.8 + 32 #'merica!
        data.data['temperature'] = tempF

        check_and_send_temperature_alert(macToName[mac], tempF)

        #Save to CSV file
        last2Mac = "".join(mac.split(":")[-2:])
        filepath = f"{scriptDir}/{macToName[mac]}({last2Mac})_data.csv"
        #TODO Error handling
        dataToWrite = ""
        if not os.path.isfile(filepath):
            dataToWrite = "time,timestamp," + ",".join(data.data.keys()) + "\n"
        readableTime = datetime.fromtimestamp(data.timestamp).strftime('%Y-%m-%d %H:%M:%S')
        dataToWrite += readableTime + "," + str(data.timestamp) + "," + ",".join([str(val) for val in data.data.values()]) + "\n"
        with open(filepath, 'a+') as dataFile:
            dataFile.write(dataToWrite)
        print(f"{macToName[mac]} was {data.data['temperature']:.2f}F on {readableTime}")

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