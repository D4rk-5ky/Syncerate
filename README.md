# Syncerate

This is a Python3 script to use 

[Jim Salter's](https://github.com/jimsalterjrs) : [Sanoid/Syncoid](https://github.com/jimsalterjrs/sanoid) 

To Send/Recieve Dataset's in list's

To make backing up ZFS DataSet's easy

----

# Reason for the script.

Me and a friend started in 2020 making use of ZFS on both PI's and homemade server's based on our old hardware.
It didn't take long to find [Jim Salter's](https://github.com/jimsalterjrs) : [Sanoid/Syncoid](https://github.com/jimsalterjrs/sanoid) and making sure to setup a proper snapshot configuration.

When it came to backing up from one location to another Syncoid is a great option well written and really useful.
Unfortunately the one dataset at a time, got us a little bored to say the least over the years.

So my friend started talking about it would be great with a script that could go over a list of our dataset's and pull/send them in succession.
And the idea for this script was made.

Now it is important to notice that i am not a programmer.
I started creating this code by scouring the internet for a pice of code here and there, that i could understand and rewrite it for my purpose in the script.
To be honest this can take a long time since u have to figure out a search query that will find some code reasembling what you want done.
And then having to rewrite it afterwards for ones own purpose.

Luckily enough ChatGPT came out and with that i was able to ask more specifically for the code that i needed and it would answer me with some great options.
Of cource this still take quite some time to make ChatGPT understand every part of what i need.
Including when the code didn't actually work a 100%

If anyone would like to fork this and make a better version i would be glad someone had seen the potential in my little Python3 script and a way to improve it.

----

### It has included options like

1. Go over a list of ZFS Dataset's and Send/Receive them to a Remote/Local ZFS POOL
2. Logs
3. Send Mail on error or succesfull run
4. Shutdown the system when done
5. Use MQTT to send a message in case that is needed.
	
	(We use it to send an MQTT message to HomeAssistant and then it will send a signal to an ESP32 with ESPHome connected to the GPIO's of a PI4 to safely shutdown and take the power from the Switch when there havent been a ping for 3 minutes)

----

# How to use this script.

1. To start with clone this repo to your desired location.
	``cd /your/script/location``
	`git clone https://github.com/D4rk-5ky/Syncerate Syncerate`

2. Then make a list of Source datasets.
	And make a list of Destination datasets

3. Then we start editing the Syncerate.cfg file

4. Create an MQTT message (If so desired)

5. Execute the script

----

### 2. lets make the sources list first.


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

### 2.  Then the destination list is a little more loose.
You can decide yourself where you wish to safe the Dataets on the receiving end.

To make make sure the datasets goes to the right places i have choosen to compare the last part of the Datasets name to ensure they are transferred to the right location.

Now notice that the leading dataset i have chosen to save under needs to be created manually.
The script can only create the dataset's taht it is receiving not something that doesn't exist.

So i would prepare that with

`zfs create Storage/Docker-SyncoidTest`

lets create a list for the destination

```
Storage/Docker-SyncoidTest/Archivy
Storage/Docker-SyncoidTest/DataSet With Spaces
Storage/Docker-SyncoidTest/Grafana
Storage/Docker-SyncoidTest/HedgeDoc
Storage/Docker-SyncoidTest/Heimdall
Storage/Docker-SyncoidTest/Home-Assistant
Storage/Docker-SyncoidTest/Joplin
Storage/Docker-SyncoidTest/Kavita
Storage/Docker-SyncoidTest/Media
Storage/Docker-SyncoidTest/Mosquitto
Storage/Docker-SyncoidTest/NextCloud
Storage/Docker-SyncoidTest/Podcasts
Storage/Docker-SyncoidTest/Portainer
Storage/Docker-SyncoidTest/SyncThing
Storage/Docker-SyncoidTest/Vikunja
Storage/Docker-SyncoidTest/WallaBag
Storage/Docker-SyncoidTest/WatchTower
```

Use whatever text editor such as Nano or Vim to make a file with the desired destination datasets.

----

### 3. Editing the Syncerate.cfg

### Config overview

| Config Option                                                         | Required                                                                   | What is needed                                                                                                                                     |
|:--------------------------------------------------------------------- | -------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| SourceListPath=                                                       | Yes                                                                        | A list of dataset's to be transferred from Source                                                                                                  |
| DestListPath=                                                         | Yes                                                                        | A list of dataset's to be saved to Destination                                                                                                     |
| SyncoidCommand=                                                       | Yes                                                                        | A Syncoid command string set like you would usually use Syncoid                                                                                    |
| PassWord=                                                             | Optional                                                                   | A Password can be written directly, asked in the terminal or disabled with no                                                                      |
| DateTime=                                                             | Yes                                                                        | The format that the logs will be saved in                                                                                                          |
| LogDestination=                                                       | Optional                                                                   | A destination folder to save the logs to                                                                                                           |
| SystemAction=                                                         | Optional                                                                   | A command like systemctl poweroff, shutdown -P now or even reboot                                                                                  |
| Use_MQTT=                                                             | Ootional                                                                   | An MQTT broker like Mosquitto                                                                                                                      |
| broker_address=                                                       | Required if "Use_MQTT" "Yes"                                               | The MQTT broker hostname or IP                                                                                                                     |
| broker_port=                                                          | Required if "Use_MQTT" "Yes"                                               | The MQTT broker port number                                                                                                                        |
| mqtt_username=                                                        | Required if "Use_MQTT" "Yes"                                               | The MQTT username                                                                                                                                  |
| mqtt_password=                                                        | Required if "Use_MQTT" "Yes"                                               | The MQTT password                                                                                                                                  |
| mqtt_topic=                                                           | Required if "Use_MQTT" "Yes"                                               | The MQTT Topic that should receive the message                                                                                                     |
| mqtt_message=ON                                                       | Required if "Use_MQTT" "Yes"                                               | The MQTT message                                                                                                                                   |
| Use_HomeAssistant=Yes                                                 | Optional for HomeAssistant Requires "Use_MQTT" "Yes" and this set to "Yes" | HomeAssistant configured with MQTT and a manual MQTT entry in configuration.yaml with an MQTT broker like Mosquitto tha has a persistence database |
| HomeAssistant_Available=homeassistant/syncoid-switch/switch/available | Required if Use_HomeAssistant=Yes                                          | The location to make the manual HomeAssitant entity online/available                                                                               |

Use the text editor of your choice and go though the file one step at a time

### Choose the location for the Source list (Required)

`SourceListPath=/dest/to/sourcelist`

### Choose the location for the Destination list (Required)

`DestListPath=/dest/to/destinationlist`

### The desired Syncoid command yo use
Thanks to Jim salter there is a lot of options to use with [Syncoid](https://github.com/jimsalterjrs/sanoid/wiki/Syncoid)
Best to read up on it on the [Syncoid](https://github.com/jimsalterjrs/sanoid/wiki/Syncoid) Wiki

This is merely meant as a guidance

And Should Look like this

```
SyncoidCommand="syncoid <UserName>@<IP/HostName>:SourceDataSet DestDataSet --compress none --sshcipher chacha20-poly1305@openssh.com --sshport <Port> --sshkey "/home/<UserName>/.ssh/KeyFile\"
SyncoidCommand="syncoid SourceDataSet <UserName>@<IP/HostName>:DestDataSet --compress none --sshcipher chacha20-poly1305@openssh.com --sshport <Port> --sshkey "/home/<UserName>/.ssh/KeyFile\"
```

Remember you either need to be root on the Sending/Receiving end
Or add the required ZFS permission for you user

### Plz. note that `SourceDataset` and `DestDataSet` is required, since when looping over the datasets these will be changed to the corresponding datasets.

`SyncoidCommand=syncoid <UserName>@<IP>:SourceDataSet DestDataSet --compress none --sshcipher chacha20-poly1305@openssh.com --sshport <Port> --sshkey <DestToSSHKey> --no-privilege-elevation`

### Next if u have a password either for SSH or a keyfile insert it here. (Optional - Write No if not needed or Ask for getting a terminal input for the password)

`PassWord=<PassWord>`
	
### If you wish to receive an mail on Succes/Fail insert a mail here. (Optional - Write No if not needed)
please note this needs something like `postfix` and the `mail` command available and setup beside this scipt

`Mail=<HereIs@Mail.com>`

### If you wish to have logs enabled (Generally a good idea) then insert a location here (Optional - Write No if not needed)
This will create a `.log`, a `.out` and in case of error a `.err` file.
These will be send in case Mail is enabled

`LogDetination=</Dest/to/log/folder>`

### The script is also able to perform a action like Shutdown or Reboot after a succesfull run (Optional - Write No if not needed)
In case of an error this wont be performed so one can track down the issue instead of just believing that it had done its job.

`SystemAction=shutdown -P now`

### The script can also send a message over MQTT
This may be usefull in case one would like an action performed after the backup is complete.

```
se_MQTT=yes
broker_address=<IP>
broker_port=1883
mqtt_username=<UsernName>
mqtt_password=<PassWord>
mqtt_topic=home-assistant/Syncerate/command
mqtt_message=ON
```

### This next part is in case the message is for HomeAssistant's MQTT integration
(We use it to send an MQTT message to HomeAssistant and then it will send a signal to an ESP32 with ESPHome connected to the GPIO's of a PI4 to safely shutdown and take the power from the Switch when there haven't been a ping for 3 minutes)

```
Use_HomeAssistant=Yes
HomeAssistant_Available=home-assistant/Syncerate/available
```

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

Note that Mosquitto needs a persistence database for the HomeAssistant entity to work
And that one also needs to make sure, to set the entity to `OFF` when done.

Or what ever action is performed when HomeAssistant receives the MQTT state will be triggered every time.

![HomeAssistant Automation - 1](config/HomeAssistant%20Automation%20-%201.png)

![HomeAssistant Automation - 2 png](config/HomeAssistant%20Automation%20-%202.png)

![HomeAssistant Automation - 3](config/HomeAssistant%20Automation%20-%203.png)

-----

5. ### Executing the script

Make sure the Python3 script is executable

`chown +x ./Syncerate-py`

The script is very easily executed when configured

`Syncerate.py -c ./config/Syncerate.cfg`

----

# I sincerely hope some people will find this useful

This is my first real way of trying to share something i have done.
Simply because i spend so much time on it, and made it work.

So i made this public on Github.
In hope others would find a use for it.
Or make it even better.

Best regards,
Darkyere & Skynet

