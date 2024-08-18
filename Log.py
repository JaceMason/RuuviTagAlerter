import os
from datetime import datetime

import GAPIHelper as gapi

# TODO maybe replace with logging library later

scriptDir = os.path.dirname(os.path.realpath(__file__))
logFilePath = scriptDir + "/ErrorLogs.txt"
maxEntries = 1000

def log(message:str):
    message = datetime.now().strftime("%m/%d/%Y, %H:%M:%S: ") + message

    print(message)
    with open(logFilePath, 'a+') as logfile:
        logfile.write(message + "\n")
        logfile.seek(0)
        lines = logfile.readlines()
        if len(lines) > maxEntries:
            logfile.truncate(0)
            lines = lines[-maxEntries:]
            logfile.writelines(lines)

def push_log_to_drive():
    gapi.upload_text_from_file(logFilePath)