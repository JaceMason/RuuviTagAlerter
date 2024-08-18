import os
import time
from datetime import datetime

import EmailHandler
import GAPIHelper

from ConfigManager import RuuviConfig
from RuuviPoller import RuuviData

scriptDir = os.path.dirname(os.path.realpath(__file__))
dataFolderName = "data"

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
    def __init__(self, mac:str, emailAlertTimeoutHour:float):
        self.shortmac = "(" + ''.join(mac.split(":")[-2:]) + ")"

        self.emailDelayTimeSec = 60 * 60 * emailAlertTimeoutHour
        self.lastEmailTime = float('-inf')

        self.fileId = 0

    def check_and_send_temperature_alert(self, temperatureF:float, config:RuuviConfig):
        if temperatureF > config.upperThresholdF:
            thresholdOfMsg = f"upper threshold of {config.upperThresholdF:.2f}F.\n"
        elif temperatureF < config.lowerThresholdF:
            thresholdOfMsg = f"lower threshold of {config.lowerThresholdF:.2f}F.\n"
        else:
            return #No alert needed, all is well!

        if time.time() >= self.lastEmailTime + self.emailDelayTimeSec:
            message = f"The greenhouse sensor '{config.name} {self.shortmac}' is currently at {temperatureF:.2f}F and has exceeded the "
            message += thresholdOfMsg
            message += f"\nThis message will repeat every {self.emailDelayTimeSec/60/60} hours until it is resolved.\nSave those plants, good luck!"
            print(message)
            message += "\n\n-The Greenhouse Monitor"
            status = EmailHandler.send_message("Automatic Greenhouse Temperature Alert", message, rxEmails=None)
            if status != None:
                self.lastEmailTime = time.time()

    def handle_data(self, data:RuuviData, config:RuuviConfig):
        for header in unwantedHeaders:
            data.data.pop(header)

        data.data["temperature"] = data.data['temperature'] * 1.8 + 32 #'merica!
        self.check_and_send_temperature_alert(data.data["temperature"], config)

        readableTime = datetime.fromtimestamp(data.timestamp).strftime('%Y-%m-%d %H:%M:%S')

        #Save to CSV file
        sensorId = config.name + self.shortmac
        dataFolderPath = f"{scriptDir}/{dataFolderName}/"
        filepath = f"{dataFolderPath}{sensorId}_data.csv"
        #TODO Error handling
        headerLine = "time,timestamp," + ",".join(data.data.keys()) + "\n"
        dataLine = readableTime + "," + str(data.timestamp) + "," + ",".join([str(val) for val in data.data.values()]) + "\n"

        os.makedirs(dataFolderPath, exist_ok=True)
        newLocalFileData = ""
        if not os.path.isfile(filepath):
            newLocalFileData = headerLine
        newLocalFileData += dataLine
        with open(filepath, 'a+') as dataFile:
            dataFile.write(newLocalFileData)

        print(f"{sensorId} was {data.data['temperature']:.2f}F on {readableTime}")
        self.fileId = GAPIHelper.append_to_sheet_make_if_dne(headerLine, dataLine, self.fileId, dataFolderName, sensorId)
