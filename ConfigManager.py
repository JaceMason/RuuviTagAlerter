import os
from dataclasses import dataclass

import GAPIHelper as gapi

scriptDir = os.path.dirname(os.path.realpath(__file__))

@dataclass
class RuuviConfig:
    #We don't need to hold the Mac because that is our dict key.
    name:str = ""
    lowerThresholdF:float = float("-inf")
    upperThresholdF:float = float("inf")
    disable:bool = True

    def __init__(self, name=None, lowerF=None, upperF=None, disabled=None):
        if(disabled==None): #discount default constructor.
            return
        self.name = name
        self.lowerThresholdF = lowerF
        self.upperThresholdF = upperF
        self.disable = disabled

    def stringify(self, mac):
        return f"{mac},{self.name},{self.lowerThresholdF},{self.upperThresholdF},{self.disable}\n"

configFileHeaders = "Mac,Name,Lower_Threshold_F,Upper_Threshold_F,Disable\n"
configFileName = "RuuviConfig.csv"

tagConfigs = {}
firstTimeStart = True

def get_config_csv():
    csvString = configFileHeaders
    for mac in tagConfigs:
        csvString += tagConfigs[mac].stringify(mac)
    return csvString

def write_local_config(csvString):
    global firstTimeStart
    try:
        with open(scriptDir + "/" + configFileName, 'w') as localConfig:
            localConfig.write(csvString)
            firstTimeStart = False
    except:
        pass

def get_latest_config(tagList):
    global tagConfigs
    for tag in tagList:
        tagConfigs.setdefault(tag, RuuviConfig())

    parentFolderId = gapi.find_object_make_if_none("folder", "config", "root")
    sheetId = gapi.find_object_make_if_none("spreadsheet", "RuuviConfig", parentFolderId)
    latestConfig = gapi.get_full_sheet(sheetId, "sheet1")
    if latestConfig == None:
        print("Something went wrong while getting the latest config")
        return

    #Latest config is built up from the web first (taking priority), then anything local is added which should be just completely new tags.
    #The result is saved off in program memory, locally, and online
    configFromOnline = {}
    for row in latestConfig[1:]:
        mac = row[0]
        configFromOnline[mac] = RuuviConfig(row[1], row[2], row[3], row[4])

    configToUpload = configFromOnline.copy()
    for tag in tagConfigs:
        if tag not in configToUpload:
            configToUpload[tag] = tagConfigs[tag]

    tagConfigs = configToUpload
    if configToUpload == configFromOnline:
        if firstTimeStart:
            #This fixes an edge case where if you start up and your config never changes, your local file will never write.
            #I also didn't want to write to the local file every time because it is likely an SD card and technically has limited writes.
            write_local_config(get_config_csv())
        return

    csvString = get_config_csv()

    write_local_config(csvString)
    gapi.write_to_sheet(sheetId, 1, csvString)
