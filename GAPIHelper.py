from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

import os

scriptDir = os.path.dirname(os.path.realpath(__file__))
defaultAppTokenLoc = f"{scriptDir}/AppToken.json"
defaultUserTokenLoc = f"{scriptDir}/UserToken.json"
appScope = ['openid', 'https://www.googleapis.com/auth/gmail.send', 'https://www.googleapis.com/auth/userinfo.email']

appTokenLoc = defaultAppTokenLoc
userTokenLoc = defaultUserTokenLoc

userToken = Credentials(None)

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
        print(f"Unable to save user credentials. Ensure that {os.path.normpath(userTokenLoc)} is not open elsewhere. You will need to sign in again next restart.")

def load_token_from_file():
    global userToken
    if os.path.exists(userTokenLoc):
        try:
            userToken = Credentials.from_authorized_user_file(userTokenLoc, appScope)
        except:
            print(f"Unable to open existing user credentials. Ensure that this script has read/write permissions for {userTokenLoc}")

def get_authorization():
    if userToken.valid:
        return True

    load_token_from_file()
    if userToken.valid:
        return True

    if userToken.expired and userToken.refresh_token:
        userToken.refresh(Request())
        if userToken.valid:
            return True

    generate_token_via_user()
    if userToken.valid:
        return True
    else:
        return False