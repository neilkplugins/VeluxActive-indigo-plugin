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
        # Check if bridge ID is set, if not update it
        if 'bridge' not in device.pluginProps:
            try:
                newProps = device.pluginProps
                newProps['bridge'] = self.getBridge(device.pluginProps['home_id'],device.pluginProps['blind_id'])
                device.replacePluginPropsOnServer(newProps)
            except:
                self.debugLog("Blind ID Not yet Set")
                return
        # Check access token freshness and refresh if needed
        if not self.token_check_valid():
            self.refresh_token()
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
        self.debugLog("Home ID is "+ device.pluginProps['home_id'])
        self.debugLog("Blind ID is "+ device.pluginProps['blind_id'])
        self.debugLog("Bridge ID is " + device.pluginProps['bridge'])


        response_json = self.get_home_data(device.pluginProps['home_id'])

        for modules in response_json['body']['home']['modules']:
            if modules['id']==device.pluginProps['blind_id']:
                self.debugLog("Found blind "+ device.pluginProps['blind_id'])
                self.debugLog("Position is "+str(modules['current_position']))
                self.debugLog("Target Position is "+str(modules['target_position']))
                if modules['target_position'] != modules['current_position']:
                    device.setErrorStateOnServer('Moving')
                else:
                    device.updateStateOnServer(key='brightnessLevel', value=modules['current_position'])
                    device.setErrorStateOnServer('')


        return

    def getBridge(self, home_id, blind_id):
        self.debugLog("Getting bridgeID via API for "+blind_id)

        url = 'https://app.velux-active.com/api/homestatus'

        data = {
            'access_token': self.pluginPrefs['access_token'],
            'home_id': home_id

        }
        try:
            response = requests.post(url, data=data)
            response.raise_for_status()
        except requests.exceptions.HTTPError as err:
            self.debugLog("HTTP Error when getting home information from Velux")
        except Exception as err:
            self.debugLog("Other error when getting home information Velux")

        if response.status_code == 200:
            self.debugLog("Got response")
        else:
            self.debugLog('Error getting home ID:' + response.text)
            return module_list

        response_json = response.json()
        for modules in response_json['body']['home']['modules']:
            #self.debugLog(modules)
            if modules['id'] == blind_id:
                bridge=modules['bridge']
                self.debugLog("Bridge is "+ modules['bridge'])
        return bridge


    def token_check_valid(self):
        # Check if the access token needs to be refreshed, default expiry is 3 hours
        time_now_with_buffer = datetime.now() + timedelta(minutes=5)
        expiry_time = datetime.strptime(self.pluginPrefs['access_token_expires'], '%Y-%m-%d %H:%M:%S.%f')
        if expiry_time > time_now_with_buffer:
            self.debugLog("Time remaining on token is " + str((expiry_time - time_now_with_buffer)))
            return True
        else:
            self.debugLog("Refresh AccessToken Now - 5 Minutes or less remaining valid")
            return False
        return


    def refresh_token(self):
        expiry_time = datetime.strptime(self.pluginPrefs['access_token_expires'], '%Y-%m-%d %H:%M:%S.%f')
        if expiry_time < datetime.now():
            self.debugLog("Token has already expired - Re-Autenticating")
            self.reAutheticate()
            return
        self.debugLog("Refreshing Access token")
        url = "https://app.velux-active.com/oauth2/token"

        payload = {
            'grant_type': 'refresh_token',
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'refresh_token': self.pluginPrefs['refresh_token']
        }
        now = datetime.now()
        try:
            response = requests.request("POST", url, data=payload)
            response.raise_for_status()
        except requests.exceptions.HTTPError as err:
            self.debugLog("HTTP Error when refreshing token")
        except Exception as err:
            self.debugLog("Other error when refreshing token")
        elapsed = now + response.elapsed

        response_json = response.json()
        if response.status_code != 200:
            self.errorLog("Failed to Refresh Authentication Token, Check Password and Account Name")
            return False
        else:
            self.pluginPrefs['access_token'] = response_json['access_token']
            self.pluginPrefs['access_token_expires'] = str(elapsed + timedelta(seconds=10800))
            self.debugLog("Access Token is " + self.pluginPrefs['access_token'])
            self.debugLog("Access Token Expiry is " + str(self.pluginPrefs['access_token_expires']))
            return True


    def get_home_data(self, home_id):
        stored_home_status = json.loads(self.pluginPrefs['stored_home_status'])
        stored_update_time = datetime.strptime(stored_home_status[home_id][0], '%Y-%m-%d %H:%M:%S.%f')
        time_now_plus_refresh = datetime.now()
        difference_in_seconds = (time_now_plus_refresh-stored_update_time).seconds
        self.debugLog("difference is "+str(difference_in_seconds))
        if home_id in stored_home_status:
            if difference_in_seconds < int(self.pluginPrefs['refresh_frequency']):
                self.debugLog("No need to refresh API data")
                #return the stored home status json, don't make a new api call as this is still fresh
                return stored_home_status[home_id][1]
            else:
                self.debugLog("Making new API call")

        url = 'https://app.velux-active.com/api/homestatus'

        data = {
            'access_token': self.pluginPrefs['access_token'],
            'home_id': home_id
        }
        self.debugLog(data)
        now = datetime.now()

        try:
            response = requests.post(url, data=data)
            response.raise_for_status()
        except requests.exceptions.HTTPError as err:
            self.debugLog("HTTP Error when getting homestatus information from Velux")
        except Exception as err:
            self.debugLog("Other error when getting homestatus information Velux")

        if response.status_code == 200:
            self.debugLog("Got Velux homestatus update for home" + home_id)
        else:
            self.debugLog('Error getting home status:' + response.text)
            return
        elapsed = now + response.elapsed
        response_json = response.json()

        stored_home_status = { home_id: [str(elapsed), response_json]}
        self.pluginPrefs['stored_home_status']=json.dumps(stored_home_status)


        return response_json




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


        access_token_expires = str(elapsed + timedelta(seconds=10800))
        valuesDict['access_token']=response_json['access_token']
        valuesDict['refresh_token']=response_json['refresh_token']
        valuesDict['access_token']=response_json['access_token']
        valuesDict['access_token_expires']=access_token_expires



        self.debugLog("Access Token is " + response_json['access_token'])
        self.debugLog("Refresh Token is " + response_json['refresh_token'])
        self.debugLog("Expiry is " + str(access_token_expires))


        indigo.server.log("Showing Velux Active Token Status after Config")
        indigo.server.log("Access Token is " + self.pluginPrefs['access_token'])
        indigo.server.log("Refresh Token is " + self.pluginPrefs['refresh_token'])
        indigo.server.log("Expiry is " + str(access_token_expires))
        self.debugLog("Exit Dict")
        self.debugLog(valuesDict)
        return (True, valuesDict)

    def validateDeviceConfigUi(self, valuesDict, typeId, devId):
        self.debugLog("Validating prefs")
        self.debugLog(valuesDict)
        return True



    def getHomeID(self, valuesDict, type_id="", dev_id="",target=""):
        self.debugLog("Getting homeID via API")
        home_list = []
        url = 'https://app.velux-active.com/api/gethomedata'

        data = {
            'access_token': self.pluginPrefs['access_token']
        }
        #self.debugLog(data)
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

    def home_menu_changed(self, valuesDict, typeId, devId):
        self.debugLog("Menu changed")
        self.debugLog(valuesDict)# do whatever you need to here
        #   typeId is the device type specified in the Devices.xml
        #   devId is the device ID - 0 if it's a new device
        
        return valuesDict


    def getBlindID(self, valuesDict, type_id="", dev_id="",target=""):
        self.debugLog("Getting blindID via API ################################################################")
        self.debugLog(type_id)
        self.debugLog("waaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        module_list = []
        if 'home_id' not in type_id:
            self.debugLog("Oh bollocks - no home ID passed to me")
            self.debugLog(type_id)
            return module_list

        url = 'https://app.velux-active.com/api/homestatus'

        data = {
            'access_token': self.pluginPrefs['access_token'],
            'home_id': type_id['home_id']
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
            self.debugLog(modules)
            if modules['type']=='NXO':
                module_list.append(modules['id'])
        return module_list



        response_json = response.json()
        self.debugLog("Modules")
        self.debugLog(response_json['body']['home']['modules'])
        for modules in response_json['body']['home']['modules']:
            self.debugLog(modules)
            if modules['blind_id']==blind_id:
                bridge=modules['bridge']
                self.debugLog("Bridge is "+ modules['bridge'])
        return bridge

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

    def reAutheticate(self):
        url = "https://app.velux-active.com/oauth2/token"
        data = {
            'grant_type': 'password',
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'username': self.pluginPrefs['velux_account'],
            'password': self.pluginPrefs['velux_password'],
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
            self.errorLog("Failed to ReAuthenticate with Velux Servers, Check Password and Account Name")
            return

        self.pluginPrefs['access_token'] = response_json['access_token']
        self.pluginPrefs['refresh_token'] = response_json['refresh_token']

        access_token_expires = str(elapsed + timedelta(seconds=10800))

        self.pluginPrefs['access_token_expires'] = access_token_expires

        self.debugLog("Access Token is " + response_json['access_token'])
        self.debugLog("Refresh Token is " + response_json['refresh_token'])
        self.debugLog("Expiry is " + str(access_token_expires))

        return

    def set_position(self, device, position):
        url = "https://app.velux-active.com/syncapi/v1/setstate"

        payload = json.dumps({
            "home": {
                "id": device.pluginProps['home_id'],
                "modules": [
                    {
                        "bridge": device.pluginProps['bridge'],
                        "id": device.pluginProps['blind_id'],
                        "target_position": position
                    }
                ]
            }
        })

        headers = {'Authorization': "Bearer {}".format(self.pluginPrefs['access_token']), 'Content-Type': 'application/json'}
        response = requests.request("POST", url, headers=headers, data=payload)

        self.debugLog(response.text)
        if response.status_code != 200:
            self.errorLog("Failed to Set Postion - API Error")
            return False
        else:
            return True


    ########################################
    # Relay / Dimmer Action callback
    ######################
    def actionControlDevice(self, action, dev):
        ###### TURN ON ######
        if action.deviceAction == indigo.kDeviceAction.TurnOn:
            send_success =self.set_position(dev,100)

            if send_success:
                # If success then log that the command was successfully sent.
                self.logger.info(f"sent \"{dev.name}\" on")

                # And then tell the Indigo Server to update the state.
                #dev.updateStateOnServer("onOffState", True)
                dev.setErrorStateOnServer('Moving')
            else:
                # Else log failure but do NOT update state on Indigo Server.
                self.logger.error(f"send \"{dev.name}\" on failed")

        ###### TURN OFF ######
        elif action.deviceAction == indigo.kDeviceAction.TurnOff:


            send_success = self.set_position(dev,0)

            if send_success:
                # If success then log that the command was successfully sent.
                self.logger.info(f"sent \"{dev.name}\" off")

                # And then tell the Indigo Server to update the state:
                #dev.updateStateOnServer("onOffState", False)
                dev.setErrorStateOnServer('Moving')

            else:
                # Else log failure but do NOT update state on Indigo Server.
                self.logger.error(f"send \"{dev.name}\" off failed")



        ###### TOGGLE ######
        elif action.deviceAction == indigo.kDeviceAction.Toggle:
            # Command hardware module (dev) to toggle here:
            # ** IMPLEMENT ME **
            new_on_state = not dev.onState
            self.debugLog(new_on_state)
            if new_on_state:
                send_success=self.set_position(dev, 100)
            else:
                send_success=self.set_position(dev, 0)


            if send_success:
                # If success then log that the command was successfully sent.
                self.logger.info(f"sent \"{dev.name}\" toggle")

                # And then tell the Indigo Server to update the state:
                dev.updateStateOnServer("onOffState", new_on_state)
            else:
                # Else log failure but do NOT update state on Indigo Server.
                self.logger.error(f"send \"{dev.name}\" toggle failed")

        ###### SET BRIGHTNESS ######
        elif action.deviceAction == indigo.kDeviceAction.SetBrightness:
            # Command hardware module (dev) to set brightness here:
            new_brightness = action.actionValue


            send_success = self.set_position(dev,new_brightness)

            if send_success:
                # If success then log that the command was successfully sent.
                self.logger.info(f"sent \"{dev.name}\" set brightness to {new_brightness}")

                # And then tell the Indigo Server to update the state:
                #dev.updateStateOnServer("brightnessLevel", new_brightness)
                dev.setErrorStateOnServer('Moving')

            else:
                # Else log failure but do NOT update state on Indigo Server.
                self.logger.error(f"send \"{dev.name}\" set brightness to {new_brightness} failed")

        ###### BRIGHTEN BY ######
        elif action.deviceAction == indigo.kDeviceAction.BrightenBy:
            # Command hardware module (dev) to do a relative brighten here:
            # ** IMPLEMENT ME **
            new_brightness = min(dev.brightness + action.actionValue, 100)
            send_success = self.set_position(dev,new_brightness)

            if send_success:
                # If success then log that the command was successfully sent.
                self.logger.info(f"sent \"{dev.name}\" brighten to {new_brightness}")

                # And then tell the Indigo Server to update the state:
                #dev.updateStateOnServer("brightnessLevel", new_brightness)
                dev.setErrorStateOnServer('Moving')

            else:
                # Else log failure but do NOT update state on Indigo Server.
                self.logger.error(f"send \"{dev.name}\" brighten to {new_brightness} failed")

        ###### DIM BY ######
        elif action.deviceAction == indigo.kDeviceAction.DimBy:
            # Command hardware module (dev) to do a relative dim here:
            # ** IMPLEMENT ME **
            new_brightness = max(dev.brightness - action.actionValue, 0)
            send_success = self.set_position(dev,new_brightness)

            if send_success:
                # If success then log that the command was successfully sent.
                self.logger.info(f"sent \"{dev.name}\" dim to {new_brightness}")

                # And then tell the Indigo Server to update the state:
                dev.updateStateOnServer("brightnessLevel", new_brightness)
            else:
                # Else log failure but do NOT update state on Indigo Server.
                self.logger.error(f"send \"{dev.name}\" dim to {new_brightness} failed")

    ########################################
    # General Action callback
    ######################
    def actionControlUniversal(self, action, dev):
        ###### BEEP ######
        if action.deviceAction == indigo.kUniversalAction.Beep:
            # Beep the hardware module (dev) here:
            # ** IMPLEMENT ME **
            self.logger.info(f"sent \"{dev.name}\" beep request not implemented")

        ###### ENERGY UPDATE ######
        elif action.deviceAction == indigo.kUniversalAction.EnergyUpdate:
            # Request hardware module (dev) for its most recent meter data here:
            # ** IMPLEMENT ME **
            self.logger.info(f"sent \"{dev.name}\" energy update request not implemented")

        ###### ENERGY RESET ######
        elif action.deviceAction == indigo.kUniversalAction.EnergyReset:
            # Request that the hardware module (dev) reset its accumulative energy usage data here:
            # ** IMPLEMENT ME **
            self.logger.info(f"sent \"{dev.name}\" energy reset request not implemented")

        ###### STATUS REQUEST ######
        elif action.deviceAction == indigo.kUniversalAction.RequestStatus:
            # Query hardware module (dev) for its current status here:
            # ** IMPLEMENT ME **
            self.logger.info(f"sent \"{dev.name}\" status request not implemented")





