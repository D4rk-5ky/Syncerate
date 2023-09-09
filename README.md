# Syncerate

This is a Python3 script that use's

[Jim Salter's](https://github.com/jimsalterjrs) : [Sanoid/Syncoid](https://github.com/jimsalterjrs/sanoid)  
Thanks to the podcast [2.5 Admins](https://2.5admins.com/) now a part of  [Jupiter Broadcasting](https://www.jupiterbroadcasting.com/)

It iterate's through a list of ZFS datasets to be send/received with Syncoid.  
Making it easy to backup several ZFS datasets.  

----

# Reason for the script.

Me and a friend started in 2020 making use of ZFS on both PI's and homemade server's based on our old hardware.  
It didn't take long to find [Jim Salter's](https://github.com/jimsalterjrs) : [Sanoid/Syncoid](https://github.com/jimsalterjrs/sanoid) and making sure to setup a proper snapshot configuration.

When it came to backing up from one location to another Syncoid is a great option well written and really useful.  
We just wanted to be able to send all the dataset's we had and its snapshots without having to redo the command's again.  

So my friend and i started dreaming of a script to automate this.  
That could go through a list of our dataset's and pull/send them in succession.  
And the idea for this script was born.

Now it is important to notice that <span style="color:red">i am not a programmer</span> and this has been a learning process for me.  
I started creating this script by scouring the internet for pieces of code here and there, that i could understand and then rewrite for my purpose.  
And ended up spending too mush time and not enough progress. 

Luckily enough ChatGPT came out, and with that i was able to ask more specifically for the code, that i needed and it would answer me with some great options.  
Of cource this still takes quite some time to make ChatGPT understand every part of what i need.  
Including when the code didn't actually work 100% all of the time.  

At this point in time, the script i working for our own need, and i will proberly not be adding any new features or maintain it.  
However i would love for someone else to fork my project, enhancing or othervise make it better, for everyone to enjouy (including us)
If you would like to contribute directly to this project, make sure to checkout `Syncerate-Next`, edit it and then make a pull request.

----

### Disclaimer: Use this at your own risk. I am not liable for any loss or damage occurred while you use this script. No batteries included.  

----

### It has included options like

1. Go over a list of ZFS Dataset's and Send/Receive them to a Remote/Local ZFS POOL
2. Logs <span style="color:cyan">(Optional)</span>
3. Send Mail on error or succesfull run <span style="color:cyan">(Optional)</span>
4. Shutdown the system when done or perform a script <span style="color:cyan">(Optional)</span>
5. Use MQTT to send a message in case that is needed. <span style="color:cyan">(Optional)</span>  
    - We use it to send an MQTT message to HomeAssistant.  
    Then it will send a signal to an ESP32 with ESPHome.  
    That is connected to the GPIO's of a PI4 to safely shutdown.  
    Then it will take the power from the Switch when there haven't been a ping for 3 minutes  

----

### 1. How to use this script.

1. To begin using this script, clone this repo to your desired location.  
	``cd /your/script/location``  
	`git clone https://github.com/D4rk-5ky/Syncerate Syncerate`

2. [Then make a list of Source datasets.](#21-lets-make-the-sources-list-first)  
  [And a list of Destination datasets.](#22-then-the-destination-list-is-a-little-more-loose)  

3. [Then we start editing the Syncerate.cfg file](#3-editing-the-synceratecfg)

4. [Create an MQTT message (If so desired)](#4-mqtt-with-homeassistant)

5. [Execute the script](#5-executing-the-script)

----

### 2.1 Lets make the sources list first.

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
The script does not have the ability to create dataset's by it self, but Syncoid will create the dataset you send, at the location your choose (Docker-Syncerate-Test in this example).

So i would prepare the dataset i wanted to send/receive the dataset's to with a command similar to

`zfs create BackUp/Docker-Syncerate-Test`

lets create a list for the destination

```
BackUp/Docker-Syncerate-Test/Archivy
BackUp/Docker-Syncerate-Test/DataSet With Spaces
BackUp/Docker-Syncerate-Test/Grafana
BackUp/Docker-Syncerate-Test/HedgeDoc
BackUp/Docker-Syncerate-Test/Heimdall
BackUp/Docker-Syncerate-Test/Home-Assistant
BackUp/Docker-Syncerate-Test/Joplin
BackUp/Docker-Syncerate-Test/Kavita
BackUp/Docker-Syncerate-Test/Media
BackUp/Docker-Syncerate-Test/Mosquitto
BackUp/Docker-Syncerate-Test/NextCloud
BackUp/Docker-Syncerate-Test/Podcasts
BackUp/Docker-Syncerate-Test/Portainer
BackUp/Docker-Syncerate-Test/SyncThing
BackUp/Docker-Syncerate-Test/Vikunja
BackUp/Docker-Syncerate-Test/WallaBag
BackUp/Docker-Syncerate-Test/WatchTower
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
Or add the required ZFS permission for you user.  

### Dont remove `SourceDataset` and `DestDataSet` they are hardcoded variables in the script <span style="color:red">NOT to be renamed</span> 
### Since when looping over the datasets in the source/dest files, these hardcoded variables will be changed to the corresponding datasets from the lists in the each files. 
### (Etc. the executed command with Storage/Wallabag in the source list and BackUp/Docker-Syncerate-Test/WallaBag in the destination list, would end up looking like this) 

`SyncoidCommand=syncoid <UserName>@<IP>:Storage/Wallabag BackUp/Docker-Syncerate-Test/WallaBag --compress none --sshcipher chacha20-poly1305@openssh.com --sshport <Port> --sshkey <DestToSSHKey> --no-privilege-elevation`

### Next if you have a password, either for SSH or a keyfile insert it here.  
  - `PassWord=No` <span style="color:cyan">(If you dont have a password)</span>  
  - `PassWord=Ask` <span style="color:cyan">(the script will stop and ask for a password to be typed in the terminal and will automaticaly input the password when needed. It will not be saved to logs or mail, but it is still written to the terminal while running the script)</span>  
  - `PassWord=<password>` <span style="color:cyan">(insert your actual password. the script will automaticaly input the password when needed, and will not be saved to logs or mail, but is still in the cfg file and written to the terminal while running the script) </span>  

### If you wish to receive a mail on Succes/Failure. Insert a mail here.  
  - `Mail=No` <span style="color:cyan">(Optional - No if you dont want mail)</span>  
  - `Mail=<example@mail.com>` <span style="color:cyan">(Example)</span>  
  - please note this need a mail service like `postfix` and the `mail` command available and setup to send a mail.  


### If you wish to have logs enabled (Generally a good idea for debugging) then insert a location here  
  - `LogDetination=No` <span style="color:cyan">(Optional - No if not needed)</span>  
  - `LogDetination=</Dest/to/log/folder>` <span style="color:cyan">(The destination to the log folder)</span>  
  This will create a `.log`, an `.out` and in case of error an `.err` file.  
  These files will be attached to the email if `Mail=` is enabled  

### The script is able to perform a command like Shutdown, Reboot or execute a script after a succesfull run  
  - `SystemAction=No` <span style="color:cyan">(Optional - No if not needed)</span>  
  - `SystemAction=shutdown -P now` <span style="color:cyan">(Example: Shutting down Ubuntu)</span>  
  In case of an error this command wont be executed, so one can track down the issue instead of just believing that it did what whas intended.  

### The script can send a message over MQTT
  - `Use_MQTT=Yes` <span style="color:cyan">(Optional - Write No if not needed)</span>  
  - `broker_address=<IP>` <span style="color:cyan">(Your MQTT broker IP or hostname)</span>  
  - `broker_port=<Port>` <span style="color:cyan">(Your MQTT broker port)</span>  
  - `mqtt_username=<UserName>` (<span style="color:red">This is required if Use_MQTT=Yes,</span>, <span style="color:cyan">i have not made anonymous acces to MQTT possible</span>)  
  - `mqtt_password=<PassWord>` (<span style="color:red">This is required if Use_MQTT=Yes,</span>, <span style="color:cyan">i have not made anonymous acces to MQTT possible</span>)  
  - `mqtt_topic=<Topic to post to>` <span style="color:cyan">(Topic to send message to)</span>  
  - `mqtt_message=<Message>` <span style="color:cyan">(Message to be send to the topic)</span>  
  This could be usefull, in case that you would lik a message to be send by help of MQTT.

### This next part, is in case the message is for the HomeAssistant's MQTT integration  
  - `Use_HomeAssistant=Yes` <span style="color:cyan">(Optional - Write No if not needed)</span>  
  - `HomeAssistant_Available=home-assistant/Syncerate/available` <span style="color:cyan">(required by Homeassistant to make the Topic available)</span>  
  We use this to send an MQTT message to HomeAssistant to activate an automation to safely shutdown a RPI4.  
    
----

### 4. MQTT with HomeAssistant

In case you want to use MQTT with Homeasistant.  
You can benefit from using my example yaml configuration file located here: `config/HomeAssistant-Configuration-For-MQTT.yaml`

This should be inserted in configuration.yaml similar to

```
# Configure a default setup of Home Assistant (frontend, api, etc)
default_config:

# Text to speech
tts:
  - platform: google_translate

mqtt:
  binary_sensor:
  - name: "Syncerate test"
    state_topic: "home-assistant/syncerate/command"
    payload_on: "ON"
    availability:
      - topic: "home-assistant/syncerate/available"
        payload_available: "online"
        payload_not_available: "offline"
    qos: 0
    value_template: "{{ value_json.state }}"

group: !include groups.yaml
automation: !include automations.yaml
script: !include scripts.yaml
scene: !include scenes.yaml
```

Note, that Mosquitto need to be set to persistence in the MQTT config for the HomeAssistant MQTT entity to work.  
And when done it is important to set the HomeAsssistant Entity to OFF, to make sure the automation does not repeat itself.  

![HomeAssistant Automation - 1](config/HomeAssistant%20Automation%20-%201.png)

![HomeAssistant Automation - 2 png](config/HomeAssistant%20Automation%20-%202.png)

-----

### 5. Executing the script

Make sure the Python3 script is executable

`chown +x ./Syncerate-py`

When configured the script is very easily executed like this: 

`Syncerate.py -c ./config/Syncerate.cfg`

----

### I sincerely hope you will find this useful.

This is my first contribution to the opensource community on github.  
I spend a lot of time to make this script work for us, and i share it on github in hopes that it can help you too.

Feel free to fork, inhance and improve the script in any way you may like  

Best regards,  
Darkyere & Skynet



