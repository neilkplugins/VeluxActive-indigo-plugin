#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# Copyright (c) 2020 neilk
#
# Based on the sample dimmer plugin
# Velux Active integration based on the documentation at https://github.com/nougad/velux-cli/blob/master/velux-protocol.md
# Plugin is provided on an as is basis, use at your own risk and it is not supported or endorsed by Velux or any of their affiliates

################################################################################
# Imports
################################################################################
import indigo
import requests
import json
# import time
from datetime import datetime, timedelta, date

################################################################################
# Globals
################################################################################

# Note these were not reverse engineered, but obtained in the public domain albeit not published by Velux, use at your own risk
CLIENT_ID = '5931426da127d981e76bdd3f'
CLIENT_SECRET = '6ae2d89d15e767ae5c56b456b452d319'


############################
# API Functions
#############################





################################################################################
class Plugin(indigo.PluginBase):
    ########################################
    # Class properties
    ########################################

    ########################################
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        super(Plugin, self).__init__(pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
        self.debug = pluginPrefs.get("showDebugInfo", False)
        self.deviceList = []

    ########################################
    def deviceStartComm(self, device):
        self.debugLog("Starting device: " + device.name)

        device.stateListOrDisplayStateIdChanged()

        if device.id not in self.deviceList:
            self.update(device)
            self.deviceList.append(device.id)

    ########################################
    def deviceStopComm(self, device):
        self.debugLog("Stopping device: " + device.name)
        if device.id in self.deviceList:
            self.deviceList.remove(device.id)

    ########################################
    def runConcurrentThread(self):
        self.debugLog("Starting concurrent thread")
        try:
            pollingFreq = int(self.pluginPrefs['pollingFrequency'])
        except:
            pollingFreq = 15

        try:
            while True:

                self.sleep(1 * pollingFreq)
                for deviceId in self.deviceList:
                    # call the update method with the device instance
                    self.update(indigo.devices[deviceId])
        except self.StopThread:
            pass

    ########################################
    def update(self, device):
        device.stateListOrDisplayStateIdChanged()
        self.debugLog("Updating Velux Device "+device.name)
        # Check access token freshness and refresh if needed
        if not token_check_valid(self):
            refresh_token(self)
        # Update address field for UI if it has changed or is blank
        if 'address' in device.pluginProps:
            if device.pluginProps['address'] != device.pluginProps['blind_id']:
                newProps = device.pluginProps
                newProps['address'] = device.pluginProps['blind_id']
                device.replacePluginPropsOnServer(newProps)
        else:
            newProps = device.pluginProps
            newProps['address'] = device.pluginProps['blind_id']
            device.replacePluginPropsOnServer(newProps)
        self.debugLog("Getting device state")
        self.debugLog("Access Token is "+ self.pluginPrefs['access_token'])
        self.debugLog("Home ID is "+ device.pluginProps['home_id'])
        self.debugLog("Blind ID is "+ device.pluginProps['blind_id'])


        url = 'https://app.velux-active.com/api/homestatus'

        data = {
            'access_token': self.pluginPrefs['access_token'],
            'home_id': device.pluginProps['home_id']
        }
        self.debugLog(data)
        try:
            response = requests.post(url, data=data)
            response.raise_for_status()
        except requests.exceptions.HTTPError as err:
            self.debugLog("HTTP Error when getting device information from Velux")
        except Exception as err:
            self.debugLog("Other error when getting device information Velux")

        if response.status_code == 200:
            self.debugLog("Got Velux device update for "+device.name)
        else:
            self.debugLog('Error getting device status:' + response.text)
            return
        response_json = response.json()

        for modules in response_json['body']['home']['modules']:
            if modules['id']==device.pluginProps['blind_id']:
                self.debugLog("Found blind "+ device.pluginProps['blind_id'])
                self.debugLog("Position is "+str(modules['current_position']))
                device.updateStateOnServer(key='brightnessLevel', value=modules['current_position'])

        return
        #
        #
        #         device_states = []
        #
        #
        #         except Exception as e:
        #             self.errorLog("Failed to complete updates for Velux device " + device.name)
        #             self.debugLog(e)
        #             self.debugLog(payload_json)
        #             device.setErrorStateOnServer('API Error')
        #
        # return



    ########################################
    # UI Validate, Plugin Preferences
    ########################################
    def validatePrefsConfigUi(self, valuesDict):
        self.debugLog("Validating Config")
        self.debugLog(valuesDict)
        self.debugLog("Initial Dict")
        if not (valuesDict['velux_account']):
             self.errorLog("Account Email Cannot Be Empty")
             errorsDict = indigo.Dict()
             errorsDict['velux_account'] = "Velux Account Cannot Be Empty"
             return False, valuesDict, errorsDict
        if not (valuesDict['velux_password']):
            self.errorLog("Password Cannot Be Empty")
            errorsDict = indigo.Dict()
            errorsDict['velux_password'] = "Password Cannot Be Empty"
            return False, valuesDict, errorsDict
        url = "https://app.velux-active.com/oauth2/token"
        data = {
            'grant_type': 'password',
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'username': valuesDict['velux_account'],
            'password': valuesDict['velux_password'],
            'user_prefix': 'velux'
        }
        self.debugLog(data)
        now = datetime.now()
        try:
            response = requests.post(url, data=data)
            response.raise_for_status()
        except requests.exceptions.HTTPError as err:
            self.debugLog("HTTP Error when authenticating to Velux")
        except Exception as err:
            self.debugLog("Other error when authenticating to Velux")
        self.debugLog(response)
        response_json = response.json()
        elapsed = now + response.elapsed
        self.debugLog(response_json)



        if response.status_code != 200:
            self.errorLog("Failed to Authenticate with Velux Servers, Check Password and Account Name")
            errorsDict = indigo.Dict()
            errorsDict['velux_password'] = "Failed to Authenticate with Velux Servers, Check Password and Account Name"
            return (False, valuesDict, errorsDict)

        self.pluginPrefs['access_token'] = response_json['access_token']
        self.pluginPrefs['refresh_token'] = response_json['refresh_token']
        self.pluginPrefs['access_token_expires'] = str(elapsed + timedelta(seconds=10800))
        indigo.server.savePluginPrefs

        self.debugLog("Access Token is " + response_json['access_token'])
        self.debugLog("Refresh Token is " + response_json['refresh_token'])
        self.debugLog("Expiry is " + str(self.pluginPrefs['access_token_expires']))


        indigo.server.log("Showing Velux Active Token Status after Config")
        indigo.server.log("Access Token is " + self.pluginPrefs['access_token'])
        indigo.server.log("Refresh Token is " + self.pluginPrefs['refresh_token'])
        indigo.server.log("Expiry is " + str(self.pluginPrefs['access_token_expires']))
        self.debugLog("Exit Dict")
        self.debugLog(valuesDict)
        return (True, valuesDict)



    def getHomeID(self, filter="", valuesDict=None, typeId="", targetId=0):
        self.debugLog("Getting homeID via API")
        home_list = []
        home_array = []
        url = 'https://app.velux-active.com/api/gethomedata'

        data = {
            'access_token': self.pluginPrefs['access_token']
        }
        self.debugLog(data)
        try:
            response = requests.post(url, data=data)
            response.raise_for_status()
        except requests.exceptions.HTTPError as err:
            self.debugLog("HTTP Error when getting home information from Velux")
        except Exception as err:
            self.debugLog("Other error when getting home information Velux")

        if response.status_code == 200:
            self.debugLog(response.text)
        else:
            self.debugLog('Error getting home ID:' + response.text)
            return home_list
        response_json = response.json()
        for homes in response_json['body']['homes']:
            home_list.append((homes['id'],homes['name']))
        self.debugLog(home_list)
        return home_list

    def getBlindID(self, filter="", valuesDict=None, typeId="", targetId=0):
        self.debugLog("Getting homeID via API")
        self.debugLog("Access Token is "+ self.pluginPrefs['access_token'])

        module_list = []
        url = 'https://app.velux-active.com/api/homestatus'

        data = {
            'access_token': self.pluginPrefs['access_token'],
            'home_id': '641d7c1e5ff3394e2e07bb15'

        }
        try:
            response = requests.post(url, data=data)
            response.raise_for_status()
        except requests.exceptions.HTTPError as err:
            self.debugLog("HTTP Error when getting home information from Velux")
        except Exception as err:
            self.debugLog("Other error when getting home information Velux")

        if response.status_code == 200:
            self.debugLog(response.text)
        else:
            self.debugLog('Error getting home ID:' + response.text)
            return module_list

        response_json = response.json()
        self.debugLog("Modules")
        self.debugLog(response_json['body']['home']['modules'])
        self.debugLog("iterated")
        for modules in response_json['body']['home']['modules']:
            #module_list.append(home['id'])
            self.debugLog(modules)
            if modules['type']=='NXO':
                module_list.append(modules['id'])
        return module_list

    def logDumpTokens(self):
        indigo.server.log("Showing Velux Active Token Status")
        indigo.server.log("Access Token is " + self.pluginPrefs['access_token'])
        indigo.server.log("Refresh Token is " + self.pluginPrefs['refresh_token'])
        indigo.server.log("Expiry is " + str(self.pluginPrefs['access_token_expires']))
        indigo.server.log("Showing Velux Preferences")
        prefs_dict = self.pluginPrefs
        for entries in prefs_dict.items():
            indigo.server.log(str(entries))

        return

def token_check_valid(self):
    # Check if the access token needs to be refreshed, default expiry is 3 hours
    time_now = datetime.now() + timedelta(minutes=5)
    expiry_time = datetime.strptime(self.pluginPrefs['access_token_expires'], '%Y-%m-%d %H:%M:%S.%f')
    if expiry_time > time_now:
        self.debugLog("Time remaining on token is " + str((expiry_time - time_now)))
        return True
    else:
        self.debugLog("Refresh AccessToken Now - 5 Minutes or less remaining valid")
        return False
    return

def refresh_token(self):
    self.debugLog("Refreshing Access token")
    url = "https://app.velux-active.com/oauth2/token"

    payload = {
    'grant_type': 'refresh_token',
    'client_id': CLIENT_ID,
    'client_secret': CLIENT_SECRET,
    'refresh_token': self.pluginPrefs['refresh_token']
    }
    headers = {
        'Content-Type': 'application/json'
    }
    now = datetime.now()
    try:
        response = requests.request("POST", url, headers=headers, data=payload)
        response.raise_for_status()
    except requests.exceptions.HTTPError as err:
        self.debugLog("HTTP Error when refreshing token")
    except Exception as err:
        self.debugLog("Other error when refreshing token")
    elapsed = now + response.elapsed

    response_json = response.json()
    if response.status_code != 200:
        self.errorLog("Failed to Refresh Authentication Token, Check Password and Account Name")
        errorsDict = indigo.Dict()
        errorsDict['bright_password'] = "Failed to Refresh Authentication Token, Check Password and Account Name"
        return False
    else:
        self.pluginPrefs['access_token'] = response_json['access_token']
        self.pluginPrefs['access_token_expires'] = str(elapsed + timedelta(seconds=10800))
        self.debugLog("Access Token is " + self.pluginPrefs['token'])
        self.debugLog("Access Token Expiry is " + str(self.pluginPrefs['access_token_expires']))
        return True
