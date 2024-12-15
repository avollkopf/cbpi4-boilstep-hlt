import asyncio

from cbpi.api import parameters, Property, action
from cbpi.api.step import StepResult, CBPiStep
from cbpi.api.timer import Timer
from datetime import datetime
import time
from voluptuous.schema_builder import message
from cbpi.api.dataclasses import NotificationAction, NotificationType
from cbpi.api.dataclasses import Kettle, Props
from cbpi.api import *
import logging
from socket import timeout
from typing import KeysView
from cbpi.api.config import ConfigType
from cbpi.api.base import CBPiBase
import numpy as np
import warnings

@parameters([Property.Number(label="Timer", description="Time in Minutes", configurable=True), 
             Property.Number(label="Temp", description="Boil temperature", configurable=True),
             Property.Sensor(label="Sensor",description="Boil Kettle Temperature Sensor"),
             Property.Kettle(label="Kettle",description="Boil Kettle"),
             Property.Kettle(label="Kettle2",description="Optional 2nd Kettle to heat up during Boil"),
             Property.Sensor(label="Sensor2",description="Temp Sensor of optional Kettle"),
             Property.Number(label="Temp2", description="Target Temp for optional kettle", configurable=True),
             Property.Select(label="LidAlert",options=["Yes","No"], description="Trigger Alert to remove lid if temp is close to boil"),
             Property.Select(label="AutoMode",options=["Yes","No"], description="Switch Kettlelogic automatically on and off -> Yes"),
             Property.Select("First_Wort", options=["Yes","No"], description="First Wort Hop alert if set to Yes"),
             Property.Text("First_Wort_text", configurable = True, description="First Wort Hop alert text"),
             Property.Number("Hop_1", configurable = True, description="First Hop alert (minutes before finish)"),
             Property.Text("Hop_1_text", configurable = True, description="First Hop alert text"),
             Property.Number("Hop_2", configurable=True, description="Second Hop alert (minutes before finish)"),
             Property.Text("Hop_2_text", configurable = True, description="Second Hop alert text"),
             Property.Number("Hop_3", configurable=True, description="Third Hop alert (minutes before finish)"),
             Property.Text("Hop_3_text", configurable = True, description="Third Hop alert text"),
             Property.Number("Hop_4", configurable=True, description="Fourth Hop alert (minutes before finish)"),
             Property.Text("Hop_4_text", configurable = True, description="Fourth Hop alert text"),
             Property.Number("Hop_5", configurable=True, description="Fifth Hop alert (minutes before finish)"),
             Property.Text("Hop_5_text", configurable = True, description="Fifth Hop alert text"),
             Property.Number("Hop_6", configurable=True, description="Sixth Hop alert (minutes before finish)"),
             Property.Text("Hop_6_text", configurable = True, description="Sixth Hop alert text")])
class BoilStepHLT(CBPiStep):

    @action("Start Timer", [])
    async def start_timer(self):
        if self.timer.is_running is not True:
            self.cbpi.notify(self.name, 'Timer started', NotificationType.INFO)
            self.timer.start()
            self.timer.is_running = True
        else:
            self.cbpi.notify(self.name, 'Timer is already running', NotificationType.WARNING)

    @action("Add 5 Minutes to Timer", [])
    async def add_timer(self):
        if self.timer.is_running == True:
            self.cbpi.notify(self.name, '5 Minutes added', NotificationType.INFO)
            await self.timer.add(300)       
        else:
            self.cbpi.notify(self.name, 'Timer must be running to add time', NotificationType.WARNING)

    async def on_timer_done(self,timer):
        self.summary = ""
        self.kettle.target_temp = 0
        if self.AutoMode == True:
            await self.setAutoMode(False)
        self.cbpi.notify(self.name, 'Boiling completed', NotificationType.SUCCESS)
        await self.next()

    async def on_timer_update(self,timer, seconds):
        self.summary = Timer.format_time(seconds)
        self.remaining_seconds = seconds
        await self.push_update()

    async def on_start(self):

        self.lid_temp = 95 if self.get_config_value("TEMP_UNIT", "C") == "C" else 203
        self.lid_flag = True if self.props.get("LidAlert", "No") == "Yes" else False
        self.AutoMode = True if self.props.get("AutoMode", "No") == "Yes" else False
        self.AutoTimer = True if self.cbpi.config.get("BoilAutoTimer", "No") == "Yes" else False
        self.first_wort_hop_flag = False 
        self.first_wort_hop=self.props.get("First_Wort", "No")
        self.first_wort_hop_text=self.props.get("First_Wort_text", None)
        self.hops_added=["","","","","",""]
        self.remaining_seconds = None
        self.temparray=np.array([])
        #self.dwelltime=int(self.props.get("DwellTime", 0))*60
        self.dwelltime=5*60 #tested with 5 minutes -> not exactly 5 min due to accuracy of asyncio.sleep
        self.deviationlimit=0.3 # derived from a test
        logging.warning(self.AutoTimer)

        self.kettle=self.get_kettle(self.props.get("Kettle", None))
        if self.kettle is not None:
            self.kettle.target_temp = float(self.props.get("Temp", 0))

        
        self.kettle2=self.get_kettle(self.props.get("Kettle2", None))
        if self.kettle2 is not None:
            self.kettle2.target_temp = float(self.props.get("Temp2", 0))

        if self.cbpi.kettle is not None and self.timer is None:
            self.timer = Timer(int(self.props.get("Timer", 0)) *60 ,on_update=self.on_timer_update, on_done=self.on_timer_done)

        elif self.cbpi.kettle is not None:
            try:
                if self.timer.is_running == True:
                    self.timer.start()
            except:
                pass

        self.summary = "Waiting for Target Temp"
        if self.AutoMode == True:
            await self.setAutoMode(True)
        await self.push_update()

    async def check_hop_timer(self, number, value, text):
        if value is not None and self.hops_added[number-1] is not True:
            if self.remaining_seconds != None and self.remaining_seconds <= (int(value) * 60 + 1):
                self.hops_added[number-1]= True
                if text is not None and text != "":
                    self.cbpi.notify('Hop Alert', "Please add %s (%s)" % (text, number), NotificationType.INFO)
                else:
                    self.cbpi.notify('Hop Alert', "Please add Hop %s" % number, NotificationType.INFO)

    async def on_stop(self):
        await self.timer.stop()
        self.summary = ""
        self.kettle.target_temp = 0
        self.kettle2.target_temp = 0
        if self.AutoMode == True:
            await self.setAutoMode(False)
        await self.push_update()

    async def reset(self):
        self.timer = Timer(int(self.props.get("Timer", 0)) *60 ,on_update=self.on_timer_update, on_done=self.on_timer_done)

    async def run(self):
        if self.first_wort_hop_flag == False and self.first_wort_hop == "Yes":
            self.first_wort_hop_flag = True
            if self.first_wort_hop_text is not None and self.first_wort_hop_text != "":
                self.cbpi.notify('First Wort Hop Addition!', 'Please add %s for first wort' % self.first_wort_hop_text, NotificationType.INFO)
            else:
                self.cbpi.notify('First Wort Hop Addition!', 'Please add hops for first wort', NotificationType.INFO)

        while self.running == True:
            await asyncio.sleep(1)
            sensor_value = self.get_sensor_value(self.props.get("Sensor", None)).get("value")
            self.temparray = np.append(self.temparray,sensor_value)
            if self.temparray.size > self.dwelltime:
                self.temparray =np.delete(self.temparray,0)
                deviation= np.std(self.temparray)
                if (sensor_value >= self.lid_temp) and (deviation <= self.deviationlimit) and (self.AutoTimer is True) and (self.timer.is_running is not True):
                    self.timer.start()
                    self.timer.is_running = True
                    estimated_completion_time = datetime.fromtimestamp(time.time()+ (int(self.props.get("Timer", 0)))*60)
                    self.cbpi.notify(self.name, 'Timer started automatically. Estimated completion: {}'.format(estimated_completion_time.strftime("%H:%M")), NotificationType.INFO)            
                logging.info("Current: "+str(sensor_value)+" | Dev: " + str(deviation))
            if self.lid_flag == True and sensor_value >= self.lid_temp:
                self.cbpi.notify("Please remove lid!", "Reached temp close to boiling", NotificationType.INFO)
                self.lid_flag = False

            if sensor_value >= float(self.props.get("Temp", 0)) and self.timer.is_running is not True:
                self.timer.start()
                self.timer.is_running = True
                estimated_completion_time = datetime.fromtimestamp(time.time()+ (int(self.props.get("Timer", 0)))*60)
                self.cbpi.notify(self.name, 'Timer started. Estimated completion: {}'.format(estimated_completion_time.strftime("%H:%M")), NotificationType.INFO)
            else:
                for x in range(1, 6):
                    await self.check_hop_timer(x, self.props.get("Hop_%s" % x, None), self.props.get("Hop_%s_text" % x, None))

        return StepResult.DONE

    async def setAutoMode(self, auto_state):
        try:
            if (self.kettle.instance is None or self.kettle.instance.state == False) and (auto_state is True):
                await self.cbpi.kettle.toggle(self.kettle.id)
            elif (self.kettle.instance.state == True) and (auto_state is False):
                await self.cbpi.kettle.stop(self.kettle.id)
            await self.push_update()

        except Exception as e:
            logging.error("Failed to switch on KettleLogic {} {}".format(self.kettle.id, e))
        
        try:
            if (self.kettle2.instance is None or self.kettle2.instance.state == False) and (auto_state is True):
                await self.cbpi.kettle.toggle(self.kettle2.id)
            elif (self.kettle2.instance.state == True) and (auto_state is False):
                await self.cbpi.kettle.stop(self.kettle2.id)
            await self.push_update()

        except Exception as e:
            logging.error("Failed to switch on KettleLogic {} {}".format(self.kettle.id, e))        




def setup(cbpi):
    '''
    This method is called by the server during startup 
    Here you need to register your plugins at the server

    :param cbpi: the cbpi core 
    :return: 
    '''

    cbpi.plugin.register("BoilStep-HLT", BoilStepHLT)
