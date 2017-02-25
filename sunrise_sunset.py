# developed by Chip Cox
#              January 2017
#

import appdaemon.appapi as appapi
import os
import json
import datetime
import stat
from utils import *
                       
class sunrise_sunset(appapi.AppDaemon):

  def initialize(self):
    self.log("SunUp Sundown setup",level="INFO")
    # initialize variables
    self.times={}
    self.times['morning']='05:00:00'
    self.times['nighttime']='22:00:00'
    self.times['timeout']='600'
    self.log("times={}".format(self.times))

    # build list of entities subject to timeout
    self.timeout_list={}
    self.timeout_list=self.build_entity_list("group.timeout_lights")
    self.log("timeout_list final={}".format(self.timeout_list),level = "INFO")

    # read actual times from config file and update HA with the saved values.
    self.filename=self.config["AppDaemon"]["app_dir"] + "/" + "sunrisesunset.cfg"
    self.load_times()
    self.log("after load times={}".format(self.times))
    self.process_current_state()

    # Setup callbacks
    self.listen_state(self.device_timeout_check, new="on", old="off")
    self.listen_state(self.device_timeout_check, entity="cover", new="open", old="closed")
    self.listen_state(self.process_input_slider, entity="input_slider")
    self.run_at_sunset(self.begin_nighttime)
    self.run_at_sunrise(self.begin_morning)

  # this is called only on startup to check the current state of lights and adjust them according to the current time.
  def process_current_state(self):
    self.log("time to process current state of lights","INFO")
    if self.sun_down():
      # after sundown to turn on carriage lights if they are off.
      self.log("after sundown state={}".format(self.get_state("switch.carriage_lights")),level="INFO")
      #handle carriage lights.  They aren't a timeout thing, but they do change at sunrise and sunset.
      if self.get_state("switch.carriage_lights")=='off':
        self.turn_on("switch.carriage_lights")
    else:
      # if the sun isn't down, it must be up so if the carriage lights are on, turn them off.
      if self.get_state("switch.carriage_lights")=='on':
        self.turn_on("switch.carriage_lights")
      elif self.get_state("light.outdoor_patio_light")=='on':
        self.turn_off("light.outdoor_patio_light")
    
    # check on the lights in the timeout list and schedule turnoff events if they are already on.
    for e in self.timeout_list:
      self.schedule_event(e)   

  # callback for sunset
  def begin_nighttime(self, kwargs):
    self.log("Sunset","INFO")
    self.turn_on("switch.carriage_lights")

  # callback for morning
  def begin_morning(self, kwargs):
    self.log("Sunrise","INFO")
    self.turn_off("switch.carriage_lights")

  # given an entity if it is between start of nighttime and start of morning, and the current state is on schedule a timeout event
  def schedule_event(self,entity):
    self.log("nighttime={} morning={} entity={}".format(self.times["nighttime"],self.times["morning"],entity))
    if self.now_is_between(self.times['nighttime'],self.times['morning']) and get_house_state(self,"input_select.house_state")=="Normal":
      # set current time, time when the event was scheduled.
      self.timeout_list[entity]=self.time()
 
      # Schedule the event to run in "timeout" seconds (timeout was read from config file")
      self.run_in(self.turn_device_off,self.times['timeout'],entity_id=entity)
      self.log("scheduled to run in {} seconds for {} timeout_list={}".format(self.times['timeout'],entity,self.timeout_list),level="INFO")

  # someone turned something on
  def device_timeout_check(self, entity, attribute, old, new, kwargs):
    # if the entity that turned on is in the timeout_list, try to schedule an event for it
    if entity in self.timeout_list:
      self.schedule_event(entity)

  # Deal with someone changing the time nighttime, morning, or the timeout value which are all input sliders.
  def process_input_slider(self, entity, attribute, old, new, kwargs):
    # is the input slider that was changed one of our starting times?
    if entity in ['input_slider.nighttime_hour','input_slider.nighttime_minutes','input_slider.morning_hour','input_slider.morning_minutes']:
      # the sliders are named carefully <tod>_<hour or minutes> this way we can compress our code a little
      # the TimeOfDay is everything from the period between the device type and the name, to the underscore in the name 
      #     we skip ahead 6 to get past the underscore in "input_slider"
      tod=entity[entity.find('.')+1:entity.find('_',6)]

      # time uom is either going to be hour or minutes
      timeuom=entity[entity.find('_',6)+1:]

      # convert new from floating point to the string representation of an integer
      timevalue=str(int(float(new)))

      # convert the current saved time value to a time structure
      newtime=self.parse_time(self.times[tod])

      if timeuom=='hour':
        # if we are dealing with hours then use the new value first and add the current minutes and 00 for seconds to it.
        self.times[tod]=timevalue+":"+str(newtime.minute)+":00"
      elif timeuom=='minutes':
        # for minutes we use the current hour and add the new minutes and 00 for seconds to it.
        self.times[tod]=str(newtime.hour)+":"+timevalue+":00"

      # write the times out to our config file
      self.save_times()

      # since we have new starting and ending times now check our current state again
      self.process_current_state()
  
    elif entity=="input_slider.timeout_value":
      # it wasn't a start or end time related slider, it was the timeout value that was adjusted
      # no fancy parsing here, just convert the new value to the string representation of an integer
      # save it and check the current state again
      self.times['timeout']=str(int(float(new)))
      self.save_times()
      self.process_current_state()
    else:
      # it was in input slider, but it wasn't one we are interested in.
      self.log("Unknown entity {}".format(entity),level="WARNING")    

  # write the times out to our configuration file
  def save_times(self):
    fout=open(self.filename,"wt")
    json.dump(self.times,fout)
    fout.close()
    #os.chmod(self.filename,stat.S_IRUSR & stat.S_IWUSR & stat.S_IRGRP & stat.S_IWGRP & stat.S_IROTH & stat.S_IWOTH)
    self.setfilemode(self.filename,"rw-rw-rw-")

  # load times fromour configuration file
  def load_times(self):
    self.log("checking on file {}".format(self.filename),level="INFO")
    if os.path.exists(self.filename):
      # file exists so open and read it
      fout=open(self.filename,"rt")
      self.times=json.load(fout)
      fout.close()
      # update HA with the values we just read
      self.updateHA()
    else:
      # file did not exist so setup an empty dictonary 
      self.times={"morning":"03:50:00","nighttime":"23:00:00","timeout":"300"}
      self.updateHA()
      self.save_times()

  # HA was restarted so when it comes up, we need to adjust the default values in HA to our values.
  def restartHA(self,event_name,data,kwargs):
    self.log("HA event {}".format(event_name),level="WARNING")
    self.updateHA()

  # adjust each of our sliders based on the values we have.
  def updateHA(self):
    self.select_value("input_slider.morning_hour",str(self.parse_time(self.times['morning']).hour))
    self.select_value("input_slider.morning_minutes",str(self.parse_time(self.times['morning']).minute))
    self.select_value("input_slider.nighttime_hour",str(self.parse_time(self.times['nighttime']).hour))
    self.select_value("input_slider.nighttime_minutes",str(self.parse_time(self.times['nighttime']).minute))
    self.select_value("input_slider.timeout_value",self.times['timeout'])

  # after all that we finally are going to turn off the lights
  def turn_device_off(self,kwargs):
    entity=kwargs["entity_id"]
    self.log("turning off {}".format(entity))
    dev, name= self.split_entity(entity)
    if dev in ["light","switch"]:
      if self.get_state(entity)=="on":
        self.log("{} timed out turning off".format(entity))
        self.turn_off(entity)
        speaktext = "Please remember to turn out the {}".format(entity)
      else:
        self.log("Entity {} already off".format(entity))
        speaktext = ""
    else:
      if self.get_state(entity)=="open":
        self.log("{} timed out closing.".format(entity))
        self.call_service("cover/close_cover",entity_id=entity)
        speaktext = "Please remember to close the garage door when you come in"
      else:
        self.log("Entity {} already closed".format(entity))
        speaktext=""
    
    if not speaktext=="":
      priority="1"
      lang = "en"
      self.fire_event("SPEAK_EVENT",text=speaktext, priority=priority,language=lang)


  # loop through the group that was passed in as entity and return a dictionary of entities
  def build_timeout_list(self,entity):
    elist={}
    for object in self.get_state(entity,attribute='all')["attributes"]["entity_id"]:
      device, entity = self.split_entity(object)
      if device=="group":
        # if the device is a group recurse back into this function to process the group.
        elist.update(self.build_timeout_list(object))
      else:
        elist[object]=self.time()
      self.log("elist={}".format(elist),level="INFO")
    return(elist)

  ######################
  #
  # build_entity_list (self, ingroup, inlist - optional: defaults to all entity types))
  #
  # build a list of all of the entities in a group or nested hierarchy of groups
  #
  # ingroup = Starting group to cascade through
  # inlist = a list of the entity types the list may contain.  Use this if you only want a list of lights and switches for example.
  #            this would then exclude any input_booleans, input_sliders, media_players, sensors, etc. - defaults to all entity types.
  #
  # returns a python list containing all the entities found that match the device types in inlist.
  ######################
  def build_entity_list(self,ingroup,inlist=['all']):
    retlist=[]
    types=[]
    typelist=[]

    # validate values passed in
    if not self.entity_exists(ingroup):
      self.log("entity {} does not exist in home assistant".format(ingroup))
      return None
    if isinstance(inlist,list):
      typelist=inlist
    else:
      self.log("inlist must be a list ['light','switch','media_player'] for example")
      return None

    # determine what types of HA entities to return
    if "all" in typelist:
      types=["all"]
    else:
      types= types + typelist
      types.append("group")            # include group so that it doesn't ignore child groups

    # check the device type to see if it is something we care about
    devtyp, devname = self.split_entity(ingroup)
    if (devtyp in types) or ("all" in types):                # do we have a valid HA entity type
      if devtyp=="group":                                    # entity is a group so iterate through it recursing back into this function.
        for entity in self.get_state(ingroup,attribute="all")["attributes"]["entity_id"]:
          newitem=self.build_entity_list(entity,typelist)    # recurse through each member of the child group we are in.
          if not newitem==None:                              # None means there was a problem with the value passed in, so don't include it in our output list
            retlist.extend(newitem)                          # all is good so concatenate our lists together
      else:
        retlist.append(ingroup)                                      # actual entity so return it as part of a list so it can be concatenated
    return retlist


  def setfilemode(self,infile,mode):
    if len(mode)<9:
      self.log("mode must bein the format of 'rwxrwxrwx'")
    else:
      result=0
      for val in mode: 
        if val in ("r","w","x"):
          result=(result << 1) | 1
        else:
          result=result << 1
      self.log("Setting file to mode {} binary {}".format(mode,bin(result)))
      os.chmod(infile,result)

  def log(self,msg,level="INFO"):
    try:
      obj,fname, line, func, context, index=inspect.getouterframes(inspect.currentframe())[1]
    except IndexError:
      self.log("Unknown - (xxx) {}".format(msg),level)
    
    super(sunrise_sunset,self).log("{} - ({}) {}".format(func,str(line),msg),level)

