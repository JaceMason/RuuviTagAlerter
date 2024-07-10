import os
import time
from datetime import datetime

import GAPIHelper

import EmailHandler
from RuuviPoller import RuuviData

scriptDir = os.path.dirname(os.path.realpath(__file__))

unwantedHeaders = [
        "acceleration",
        "acceleration_x",
        "acceleration_y",
        "acceleration_z",
        "tx_power",
        "movement_counter",
        "data_format",
]

class DataHandler:
    def __init__(self, mac:str, sensorName:str, upperThresholdF:float, lowerThresholdF:float, emailAlertTimeoutHour:float, debugOnly:bool):
        self.sensorId = sensorName + "(" + ''.join(mac.split(":")[-2:]) + ")"
        self.tempThreshLowerF = lowerThresholdF
        self.tempThreshUpperF = upperThresholdF

        self.emailDelayTimeSec = 60 * 60 * emailAlertTimeoutHour
        self.lastEmailTime = float('-inf')

        self.fileId = 0

        self.debugOnly = debugOnly

    def set_thresholds(self, lowerF, upperF):
        self.tempThreshLowerF = lowerF
        self.tempThreshUpperF = upperF

    def check_and_send_temperature_alert(self, temperatureF:float):
        if temperatureF > self.tempThreshUpperF:
            thresholdOfMsg = f"upper threshold of {self.tempThreshUpperF:.2f}F.\n"
        elif temperatureF < self.tempThreshLowerF:
            thresholdOfMsg = f"lower threshold of {self.tempThreshLowerF:.2f}F.\n"
        else:
            return #No alert needed, all is well!

        if time.time() >= self.lastEmailTime + self.emailDelayTimeSec:
            message = f"The greenhouse sensor '{self.sensorId}' is currently at {temperatureF:.2f}F and has exceeded the "
            message += thresholdOfMsg
            message += f"\nThis message will repeat every {self.emailDelayTimeSec/60/60} hours until it is resolved.\nSave those plants, good luck!\n\n-The Greenhouse Monitor"
            status = EmailHandler.send_message("Automatic Greenhouse Temperature Alert", message, rxEmails=None, debugOnly=self.debugOnly)
            if status != None:
                self.lastEmailTime = time.time()

    def handle_data(self, data:RuuviData):
        for header in unwantedHeaders:
            data.data.pop(header)

        data.data["temperature"] = data.data['temperature'] * 1.8 + 32 #'merica!
        self.check_and_send_temperature_alert(data.data["temperature"])

        readableTime = datetime.fromtimestamp(data.timestamp).strftime('%Y-%m-%d %H:%M:%S')

        #Save to CSV file
        filepath = f"{scriptDir}/{self.sensorId}_data.csv"
        #TODO Error handling
        headerLine = "time,timestamp," + ",".join(data.data.keys()) + "\n"
        dataLine = readableTime + "," + str(data.timestamp) + "," + ",".join([str(val) for val in data.data.values()]) + "\n"

        newLocalFileData = ""
        if not os.path.isfile(filepath):
            newLocalFileData = headerLine
        newLocalFileData += dataLine
        with open(filepath, 'a+') as dataFile:
            dataFile.write(newLocalFileData)

        print(f"{self.sensorId} was {data.data['temperature']:.2f}F on {readableTime}")
        self.fileId = GAPIHelper.append_to_sheet(headerLine, dataLine, self.fileId, 'data', self.sensorId)
