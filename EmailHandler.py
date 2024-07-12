import base64
import os

from email.mime.text import MIMEText

import GAPIHelper


scriptDir = os.path.dirname(os.path.realpath(__file__))

emailListPath = scriptDir+"/EmailList.txt"
emailList = []
try:
    with open(emailListPath, 'r') as emailFile:
        emailList = [line.strip() for line in emailFile]
except:
    pass
if emailList == []:
    print(f"Please add emails to the following file if you would like to use the email alert feature.\n{os.path.normpath(emailListPath)}")

@GAPIHelper.authorize
def create_message(rxEmails:list[str], subject, messageText):
    userinfo = GAPIHelper.infoService.userinfo().get().execute()
    txEmail = userinfo.get('email')
    message = MIMEText(messageText)
    message['to'] = ", ".join(rxEmails)
    message['from'] = txEmail
    message['subject'] = subject
    return {'raw': base64.urlsafe_b64encode(message.as_bytes('utf-8')).decode()}

@GAPIHelper.authorize
def send_message(subject:str, messageText:str, rxEmails:list[str] = None, debugOnly:bool = False):
    if rxEmails == None:
        rxEmails = emailList
    rawMessage = create_message(rxEmails, subject, messageText)
    try:
        if debugOnly:
            print("I am not actually going to send that email. I am in debug only mode!")
            return 0

        message = (GAPIHelper.gmailService.users().messages().send(userId='me', body=rawMessage).execute())
        return message['id']
    except Exception as error:
        print(error)
        return None