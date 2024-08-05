import google.auth.exceptions as g_exception
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

import csv
import os
import time

from enum import Enum
from io import StringIO

import Log

class obj(Enum):
    folder = "application/vnd.google-apps.folder"
    sheet = "application/vnd.google-apps.spreadsheet"
    text = "text/plain"

scriptDir = os.path.dirname(os.path.realpath(__file__))
defaultAppTokenLoc = f"{scriptDir}/AppToken.json"
defaultUserTokenLoc = f"{scriptDir}/UserToken.json"
appScope = ['openid', 'https://www.googleapis.com/auth/gmail.send', 'https://www.googleapis.com/auth/userinfo.email', 'https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']


appTokenLoc = defaultAppTokenLoc
userTokenLoc = defaultUserTokenLoc

userToken = Credentials(None)

driveService = None
sheetsService = None
infoService = None
gmailService = None

def change_app_token_location(path):
    global appTokenLoc
    appTokenLoc = path

def change_user_token_location(path):
    global userTokenLoc
    userTokenLoc = path

def is_authorized():
    return userToken.valid

def authorize(func):
    def wrapper(*args, **kwargs):
        funcReturn = None
        if get_authorization():
            funcReturn = func(*args, **kwargs)
        else:
            print(f"Authorization failed. Unable to call {func.__name__}.")

        return funcReturn
    return wrapper

def generate_token_via_user():
    global userToken
    try:
        # TODO, I think we can put this message up on the oauth consent thingy
        print("WARNING: THIS APP DOES NOT ENCRYPT OR MAKE ANY EFFORT TO PROTECT YOUR CREDENTIALS. USE AT YOUR OWN RISK.")
        userToken = InstalledAppFlow.from_client_secrets_file(appTokenLoc, appScope).run_local_server(port=0)
    except:
        userToken = Credentials(None)
        return
    try:
        with open(userTokenLoc, 'w') as tokenFile:
            tokenFile.write(userToken.to_json())
    except:
        Log.log(f"Unable to save user credentials. Ensure that {os.path.normpath(userTokenLoc)} is not open elsewhere. You will need to sign in again next restart.")

def load_token_from_file():
    global userToken
    if os.path.exists(userTokenLoc):
        try:
            userToken = Credentials.from_authorized_user_file(userTokenLoc, appScope)
        except:
            Log.log(f"Unable to open existing user credentials. Ensure that this script has read/write permissions for {userTokenLoc}")

def get_authorization():
    if userToken.valid:
        return True

    load_token_from_file()
    if userToken.valid:
        return create_resources()

    if userToken.expired and userToken.refresh_token:
        try:
            userToken.refresh(Request())
        except g_exception.RefreshError:
            pass

        if userToken.valid:
            return create_resources()

    generate_token_via_user()
    if userToken.valid:
        return create_resources()
    else:
        return False

def create_resources():
    global driveService
    global sheetsService
    global infoService
    global gmailService
    try:
        driveService = build('drive', 'v3', credentials=userToken)
        sheetsService = build('sheets', 'v4', credentials=userToken)
        infoService = build('oauth2', 'v2', credentials=userToken)
        gmailService = build('gmail', 'v1', credentials=userToken)
    except Exception as e:
        Log.log("create_resources: %" % str(e))
        return False
    return True

@authorize
def find_object(objType:obj, objName:str, parentFolderId:str, makeIfNone:bool=True):
    objectId = 0
    query = f"name = '{objName}' and mimeType = '{objType.value}' and '{parentFolderId}' in parents and trashed = false"
    try:
        response = driveService.files().list(q=query, fields="files(id, name)").execute()
    except Exception as e:
        Log.log("find_object: %s" % str(e))
        return 0
    respFiles = response.get('files', [])
    if respFiles:
        objectId = respFiles[0]['id']
    elif makeIfNone: #Create the object instead
        metadata = {'name': objName, 'mimeType': f'{objType.value}', 'parents': [parentFolderId]}
        try:
            response = driveService.files().create(body=metadata, fields='id').execute()
        except Exception as e:
            Log.log("find_object: %s" % str(e))
            return 0
        if 'id' in response:
            objectId = response['id']
    return objectId

#Data should be a comma seperated list (For example "A,B,C")
@authorize
def write_to_sheet(fileId, lineNum, data):
    cellRange = f"Sheet1!A{lineNum}"
    listifiedData = list(csv.reader(StringIO(data)))
    toWrite = {'values': listifiedData}
    try:
        response = sheetsService.spreadsheets().values().update(
            spreadsheetId=fileId, range=cellRange,
            valueInputOption='USER_ENTERED', body=toWrite).execute()
    except Exception as e:
        Log.log("write_to_sheet: %s" % str(e))
        return 0
    if 'updatedCells' in response:
        return fileId
    else:
        return 0

@authorize
def get_full_sheet(fileId, sheetName):
    cellRange = sheetName
    try:
        response = sheetsService.spreadsheets().values().get(spreadsheetId=fileId, range=cellRange).execute()
    except Exception as e:
        Log.log("get_full_sheet: %s" % str(e))
        return None
    return response.get("values", [[]])

#If fileId is '0', it will find/make the file. This function will return the fileId for the file it wrote to. 0 if failed
@authorize
def append_to_sheet(headerLine, dataLine, fileId, folderName, fileName):
    #Figure out how many lines are in the file (and check if it exists)
    nextLineNum = 1
    cellRange = "Sheet1!A:A"
    # We really don't want to spam Google's API a billion times, so prevent any infinite looping
    retriesLeft = 5
    while retriesLeft > 0:
        try:
            response = sheetsService.spreadsheets().values().get(spreadsheetId=fileId, range=cellRange).execute()
            if 'values' in response:
                nextLineNum = len(response['values']) + 1
            break
        except Exception as e:
            if type(e) == HttpError and e.resp.status == 404:
                folderId = find_object(obj.folder, folderName, 'root')
                if folderId:
                    fileId = find_object(obj.sheet, fileName, folderId)
            else:
                Log.log("write_to_sheet: %s" % str(e))

            if retriesLeft == 0:
                return 0

        retriesLeft -= 1
        time.sleep(2)


    if not fileId:
        return 0
    if nextLineNum == 1:
        result = write_to_sheet(fileId, nextLineNum, headerLine)
        if not result:
            return 0
        nextLineNum += 1

    #Actually write our data to the file, finally.
    return write_to_sheet(fileId, nextLineNum, dataLine)

def upload_text_file(pathToText:str):
    baseName = os.path.basename(pathToText)
    fileId = find_object(obj.text, baseName, 'root')

    if fileId == 0:
        return False

    metadata = {'name': baseName}
    media = MediaFileUpload(pathToText)
    try:
        driveService.files().update(fileId=fileId, body=metadata, media_body=media).execute()
    except Exception as e:
        Log.log("upload_text_file: %s" % str(e))
        return False
    return True
