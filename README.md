# SynCoid-Iterate

This is a Python3 script to use 

[Jim Salter's](https://github.com/jimsalterjrs) : [Sanoid/Syncoid](https://github.com/jimsalterjrs/sanoid) 

To Send/Recieve Dataset's in list's

To make backing up ZFS DataSet's easy

----

### It has included options like

1. Go over a list of ZFS Dataset's and Send/Receive them to a Remote/Local ZFS POOL
2. Logs
3. Send Mail on error or succesfull run
4. Shutdown the system when done
5. Use MQTT to send a message in case that is needed.
	(I use it to send an MQTT message to HomeAssistant and then it wil safely shutdown a PI4 and take the power from the Switch)
	
----

# How to use this script.

1. To start with clone this repo to your desired location.

2. Then start with make a list of Source datasets.
	
3. And then then make a list of Destination datasets

5. Then we start editing the SynCoid-Iterate.cfg file
	
----

2.
### lets make the sources list first.


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

3.
### Then the destination list is a little more loose.
You can decide yourself where you wish to safe the Dataets on the receiving end.

To make make sure the datasets goes to the right places i have choosen to compare the last part of the Datasets name to ensure they are transferred to the right location.

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

Now remember that the ledaing dataset i have choosen to save under needs to be created manually.
The script can only create the dataset it receive not something that doesnt exist.

So i would prepare that with
`zfs create Storage/Docker-SyncoidTest`

----

4.
use the text editor of your choice and go though the file one step at a time

### Choose the location for the Source list (Required)

`SourceListPath=/dest/to/sourcelist

### Choose the lcation for the Destination list (Required)

`DestListPath=/dest/to/destinationlist

### The desired Syncoid command yo use
Thanks to Jim salter there is a lot of options to use with Syncoid
Best to read up on it on Syncoids Wiki
This is merely meant as a guidance

Plz. note that `SourceDataset` and `DestDataSet` is required, since when looping over the datasetøs these will be changed to the corresponding datasets.

`SyncoidCommand=syncoid <UserName>@<IP>:SourceDataSet DestDataSet --compress none --sshcipher chacha20-poly1305@openssh.com --sshport <Port> --sshkey <DestToSSHKey> --no-privilege-elevation`

### Next if u have a password either for SSH or a kyfile insert it here. (Optional - Write No if not needed)

`PassWord=<PassWord>`
	
### If you wish to receive a mail on Scces/Fail insert a mail here. (Optional - Write No if not needed)
please note this needs something like `postfix` and the `mail` command available and setup beside this scipt

`Mail=<HereIs@Mail.com>`

### If you wish to have logs enabled (Generally a good idea) then insert a location here (Optional - Write No if not needed)
This will create a `.log`, a `.out` and in case of error a `.err` file.
These will be send in case Mail is enabled

`LogDetination=</Dest/to/log/folder>`
