# Syncerate

This is a Python3 script to use 

[Jim Salter's](https://github.com/jimsalterjrs) : [Sanoid/Syncoid](https://github.com/jimsalterjrs/sanoid) 

To iterate though a list of Datasets to be send/recived with Syncoid.  
Making it easy to backup several ZFS datasets.  

----

# Reason for the script.

Me and a friend started in 2020 making use of ZFS on both PI's and homemade server's based on our old hardware.  
It didn't take long to find [Jim Salter's](https://github.com/jimsalterjrs) : [Sanoid/Syncoid](https://github.com/jimsalterjrs/sanoid) and making sure to setup a proper snapshot configuration.

When it came to backing up from one location to another Syncoid is a great option well written and really useful.  
Unfortunately the one dataset at a time, got real cumbersome rand time consuming.

So my friend and i started dreaming of a script for automating this teadius manual task.  
That could go through a list of our dataset's and pull/send them in succession.  
And the idea for this script was born.

Now it is important to notice that !!!i am not a programmer!!! and this has been a learning process for me. 
I started creating this script by scouring the internet for pieces of code here and there, that i could understand and then rewrite for my purpose.  
And ended up spending too mush time not enough progress. 

Luckily enough ChatGPT came out, and with that i was able to ask more specifically for the code, that i needed and it would answer me with some great options.  
Of cource this still take quite some time to make ChatGPT understand every part of what i need.  
Including when the code didn't actually work 100% all of the time.  

At this point in time, the script i working for our need, and i will proberly not be adding any new features or maintain.  
However i would love for someone else to fork my project, enhancing or othervise make it better, for everyerone to enjouy (including us)

----

### It has included options like

1. Go over a list of ZFS Dataset's and Send/Receive them to a Remote/Local ZFS POOL
2. Logs
3. Send Mail on error or succesfull run
4. Shutdown the system when done
5. Use MQTT to send a message in case that is needed.  
    - We use it to send an MQTT message to HomeAssistant.  
    Then it will send a signal to an ESP32 with ESPHome.  
    That is connected to the GPIO's of a PI4 to safely shutdown.  
    Then it will take the power from the Switch when there haven't been a ping for 3 minutes  

----

### 1. How to use this script.

1. To begin using this script, clone this repo to your desired location.  
	``cd /your/script/location``  
	`git clone https://github.com/D4rk-5ky/Syncerate Syncerate`

2. [Then make a list of Source datasets.](#21-lets-make-the-sources-list-first) [And a list of Destination datasets.](#22-then-the-destination-list-is-a-little-more-loose)  

3. [Then we start editing the Syncerate.cfg file](#3-editing-the-synceratecfg)

4. [Create an MQTT message (If so desired)](#4-mqtt-with-homeassistant)

5. [Execute the script](#5-executing-the-script)

----

### 2.1 lets make the sources list first.

Source example is located in the config folder in the git clone

The easy way to get a list for the sources is to use the command

```
zfs list -o name

Storage/Archivy
Storage/DataSet With Spaces
Storage/Grafana
Storage/HedgeDoc
Storage/Heimdall
Storage/Home-Assistant
Storage/Joplin
Storage/Kavita
Storage/Media
Storage/Mosquitto
Storage/NextCloud
Storage/Podcasts
Storage/Portainer
Storage/SyncThing
Storage/Vikunja
Storage/WallaBag
Storage/WatchTower
```

Use whatever text editor such as Nano or Vim to make a file with the desired source datasets.

----

### 2.2  Then the destination list is a little more loose.
You can decide yourself where you wish to safe the Datasets on the receiving end.

Destination example is located in the config folder in the git clone

To check that the datasets goes to the right places, the script compares the last part of the Dataset's name's from source and destination file.  
To ensure they are transferred to the right location.  
If the end names does not match the script will pass an error (terminal, log-file, and email if configured)  

The zpool your send the datasets to, can be any name you like (BackUp in this example)
But if you want the dataset on the receving end, to be inside another dataset (Docker-SyncoidTest in this example).  
You will have to manually create that dataset yourself.
The script does not have the ability to create datasets it self, but Syncoid will create the dataset you send. At the location your choose (Docker-SyncoidTest in this example).

So i would prepare that with

`zfs create BackUp/Docker-SyncoidTest`

lets create a list for the destination

```
BackUp/Docker-SyncoidTest/Archivy
BackUp/Docker-SyncoidTest/DataSet With Spaces
BackUp/Docker-SyncoidTest/Grafana
BackUp/Docker-SyncoidTest/HedgeDoc
BackUp/Docker-SyncoidTest/Heimdall
BackUp/Docker-SyncoidTest/Home-Assistant
BackUp/Docker-SyncoidTest/Joplin
BackUp/Docker-SyncoidTest/Kavita
BackUp/Docker-SyncoidTest/Media
BackUp/Docker-SyncoidTest/Mosquitto
BackUp/Docker-SyncoidTest/NextCloud
BackUp/Docker-SyncoidTest/Podcasts
BackUp/Docker-SyncoidTest/Portainer
BackUp/Docker-SyncoidTest/SyncThing
BackUp/Docker-SyncoidTest/Vikunja
BackUp/Docker-SyncoidTest/WallaBag
BackUp/Docker-SyncoidTest/WatchTower
```

Use the text editor of your choice (such as Nano or Vim) to make a file with the desired destination datasets.

----

### 3. Editing the Syncerate.cfg

An example .cfg file is located under the config folder in the git clone.

### Config overview

| Config Option                                                         | Required                                                                   | What is needed                                                                                                                                     |
|:--------------------------------------------------------------------- | -------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| SourceListPath=                                                       | Yes                                                                        | A list of dataset's to be transferred from Source                                                                                                  |
| DestListPath=                                                         | Yes                                                                        | A list of dataset's to be saved to Destination                                                                                                     |
| SyncoidCommand=                                                       | Yes                                                                        | A Syncoid command string containing your usual syncoild comand arguments (note that SourseDataset and DistDataset is needed)                                                                                    |
| PassWord=                                                             | Optional                                                                   | A Password for ssh can be written in the .cfg-file, asked in the terminal or disabled with no                                                                      |
| DateTime=                                                             | Yes                                                                        | The format that the logs will be saved in                                                                                                          |
| LogDestination=                                                       | Optional                                                                   | A destination folder to save the logs to                                                                                                           |
| SystemAction=                                                         | Optional                                                                   | A command like systemctl poweroff, shutdown -P now or even reboot (disable with no)                                                                                 |
| Use_MQTT=                                                             | Optional                                                                   | An MQTT broker like Mosquitto (disable with no)                                                                                                                     |
| broker_address=                                                       | Required if "Use_MQTT" "Yes"                                               | The MQTT broker hostname or IP                                                                                                                     |
| broker_port=                                                          | Required if "Use_MQTT" "Yes"                                               | The MQTT broker port number                                                                                                                        |
| mqtt_username=                                                        | Required if "Use_MQTT" "Yes"                                               | The MQTT username (note!!! mqtt in this script only work with username and password not anonymous)                                                                                                                                 |
| mqtt_password=                                                        | Required if "Use_MQTT" "Yes"                                               | The MQTT password                                                                                                                                  |
| mqtt_topic=                                                           | Required if "Use_MQTT" "Yes"                                               | The MQTT Topic that should receive the message                                                                                                     |
| mqtt_message=                                                       | Required if "Use_MQTT" "Yes"                                               | The MQTT message                                                                                                                                   |
| Use_HomeAssistant=                                                 | Optional for HomeAssistant Requires "Use_MQTT" "Yes" and this set to "Yes" | HomeAssistant configured with MQTT and a manual MQTT entry in configuration.yaml with an MQTT broker like Mosquitto tha has a persistence database |
| HomeAssistant_Available= | Required if Use_HomeAssistant=Yes                                          | The location to make the manual HomeAssitant entity online/available                                                                               |

Use the text editor of your choice and go though the file one step at a time

----

# This is the .cfg examples i have made

### Choose the location for the Source list (Required)

`SourceListPath=/dest/to/sourcelist`

### Choose the location for the Destination list (Required)

`DestListPath=/dest/to/destinationlist`

### The desired Syncoid command yo use
Thanks to [Jim Salter's](https://github.com/jimsalterjrs) there is a lot of options to use with [Syncoid](https://github.com/jimsalterjrs/sanoid/wiki/Syncoid)  
Best to read up on it on the [Syncoid Wiki](https://github.com/jimsalterjrs/sanoid/wiki/Syncoid)

This is merely meant as a guidance

And might look something like this

```
### To receive
SyncoidCommand="syncoid <UserName>@<IP/HostName>:SourceDataSet DestDataSet --compress none --sshcipher chacha20-poly1305@openssh.com --sshport <Port> --sshkey "/home/<UserName>/.ssh/KeyFile"

### To send
SyncoidCommand="syncoid SourceDataSet <UserName>@<IP/HostName>:DestDataSet --compress none --sshcipher chacha20-poly1305@openssh.com --sshport <Port> --sshkey "/home/<UserName>/.ssh/KeyFile"
```

Remember you either need to be root on the Sending/Receiving end.  
Or add the required ZFS permission for you user

### dont remove `SourceDataset` and `DestDataSet` they are hardcoded variables in the script (!!!NOT to be renamed!!!)    
### Since when looping over the datasets in the source/dest files, these hardcoded variables will be changed to the corresponding datasets from the lists in the each files. 
### (fx Storage/Wallabag, BackUp/SynCoid-Test/Wallabag ... etc.) 

`SyncoidCommand=syncoid <UserName>@<IP>:SourceDataSet DestDataSet --compress none --sshcipher chacha20-poly1305@openssh.com --sshport <Port> --sshkey <DestToSSHKey> --no-privilege-elevation`

### Next if you have a password, either for SSH or a keyfile insert it here. 
  - `PassWord=No` (if you dont have a password)
  - `PassWord=Ask` (the script will stop and ask for a password to be typed in terminal and will automaticaly input the password when needed. It will not be saved to logs or mail, but it is still written to the terminal while running the script))
  - `PassWord=<password>` (insert your actual password. the script will automaticaly input the password when needed, and will not be saved to logs or mail, but is still in the cfg file and written to the terminal while running the script)
	
### If you wish to receive a mail on Succes/Failure. Insert a mail here. 
  - `Mail=No` (if you dont want mail)
  - please note this needs something like `postfix` and the `mail` command available and setup beside this script

`Mail=<example@mail.com>`

### If you wish to have logs enabled (Generally a good idea) then insert a location here 
  - `LogDetination=No` (If not needed)
  - `LogDetination=</Dest/to/log/folder>` (The destination to the log folder)
  - This will create a `.log`, a `.out` and in case of error a `.err` file.
  - These files will be attached to the email if `Mail=` is enabled

### The script is also able to perform an action like Shutdown or Reboot after a succesfull run 
  - `SystemAction=No` (No if not needed)
  - In case of an error this command wont be executed, so one can track down the issue instead of just believing it had done its job.

`SystemAction=shutdown -P now`

### The script can also send a message over MQTT
  - `Use_MQTT=Yes` (Optional - Write No if not needed)
  - `broker_address=<IP>` (Your MQTT broker IP or hostname)
  - `broker_port=<Port>` (Your MQTT broker port)
  - `mqtt_username=<UserName>` (This is required, i have not made anonymous acces to MQTT possible)
  - `mqtt_password=<PassWord>` (This is required, i have not made anonymous acces to MQTT possible)
  - `mqtt_topic=<Topic to post to>` (Topic to send message to)
  - `mqtt_message=ON` (Message to be send to the topic)
  - This may be usefull, in case one would like an action performed after the backup is complete by the help of MQTT.

### This next part, is in case the message is for HomeAssistant's MQTT integration
  - `Use_HomeAssistant=Yes` (Optional - Write No if not needed)
  - `HomeAssistant_Available=home-assistant/Syncerate/available` (required by Homeassistant to make the Topic available)
    - We use it to send an MQTT message to HomeAssistant.
    - Then it will send a signal to an ESP32 with ESPHome.
    - That is connected to the GPIO's of a PI4 to safely shutdown.
    - Then it will take the power from the Switch when there havent been a ping for 3 minutes


----

### 4. MQTT with HomeAssistant

In case that HomeAssistant is the use case of MQTT
One could use the yaml entity that is located under `config/HomeAssistant-Configuration-For-MQTT.yaml`

This should be inserted in configuration.yaml similar to

```
# Configure a default setup of Home Assistant (frontend, api, etc)
default_config:

# Text to speech
tts:
  - platform: google_translate

mqtt:
  binary_sensor:
  - name: "Syncoid Iterate"
    state_topic: "home-assistant/Syncerate/command"
    payload_on: "ON"
    availability:
      - topic: "home-assistant/Syncerate/available"
        payload_available: "online"
        payload_not_available: "offline"
    qos: 0
    #device_class: opening
    value_template: "{{ value_json.state }}"

group: !include groups.yaml
automation: !include automations.yaml
script: !include scripts.yaml
scene: !include scenes.yaml
```

Note, that Mosquitto needs a persistence database for the HomeAssistant entity to work.  
And that one also needs to make sure, to set the entity to `OFF` when done.

Or what ever action is performed when HomeAssistant receives the MQTT state will be triggered every time.

![HomeAssistant Automation - 1](config/HomeAssistant%20Automation%20-%201.png)

![HomeAssistant Automation - 2 png](config/HomeAssistant%20Automation%20-%202.png)

![HomeAssistant Automation - 3](config/HomeAssistant%20Automation%20-%203.png)

-----

### 5. Executing the script

Make sure the Python3 script is executable

`chown +x ./Syncerate-py`

The script is very easily executed like this when configured

`Syncerate.py -c ./config/Syncerate.cfg`

----

### I sincerely hope you will find this useful.

This is my first real way of trying to share something i have done.  
Simply because i spend so much time on it, and made it work.  

So i made this public on Github.  
In hope others would find a use for it.  
Or make it even better.  

Best regards,  
Darkyere & Skynet

