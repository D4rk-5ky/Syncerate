#!/usr/bin/python3

# Import argument parser for python arguments
import argparse
from asyncio.log import logger

# Import variables from a .conf file
import configparser
#from distutils.log import error, info

# This is for exit codes
import sys

# This is for getting the password hidden
from getpass import getpass

# pexpect to wait for a sentence and enter a password when prompted
import pexpect

# Python3 logfile module, for creating a process and error log
import logging

# Datetime module for loggin
import datetime

# This is to check if the file error file is empty or not
# And for the Mail option, if choosen
import os

#  if there is an unexpected error in the program, traceback.print_exc() will work
import traceback

# This code is for using popen to send a mail with postfix
import subprocess

# This is to make python sleep for a time to make sure mail is sent
import time

# For sending a message over MQTT
import paho.mqtt.client as mqtt

def mqtt_connect(client, userdata, flags, rc, mqtt_topic, mqtt_message):
    try:
        if rc == 0:
            logger.info('')
            logger.info('----------')
            logger.info('')
            logger.info('Publishing Topic and Message to MQTT')

            # Publish the message after connecting
            client.publish(mqtt_topic, mqtt_message, retain=True)

            # Disconnect from the MQTT broker
            client.disconnect()
        
        else:
            raise Exception('Failed publishing message to MQTT')
    
    except Exception as e:
        # Handle the exception and capture the error message
        error_message = str(e)
        logger.error('')
        logger.error('----------')
        logger.error('')
        logger.error('MQTT Error message: ' + error_message)
        die(None, None, None, None, rc)
	
# This is is for the send mail part
def send_mail(subject, body, recipient, attachment_files=None):
	mail_command = ['mail', '-s', subject, recipient]

	if attachment_files:
		for file in attachment_files:
			mail_command.extend(['--attach', file])

	process = subprocess.Popen(mail_command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
	_, stderr_output = process.communicate(input=body.encode())

	mail_exit_code = process.returncode
	return mail_exit_code, stderr_output.decode().strip()

# This is for the send mail function
# In case one needs to be notified of errors
#
# FIx and make sure to make it possible to send error message even if .out file is not created yet
def MailTo(Exit_Code=None, SynCoidFail=None, MQTT_Fail=None):
	# Define recipient
	recipient = (config.get('Syncerate Config', 'Mail'))

	logger.info('')
	logger.info('----------')
	logger.info('')
	logger.info('There is an option to send a mail')

	if Exit_Code == 0:

		if LogDestination.upper() != "NO":

			# Define subject
			subject = "Successful Syncerate.py run - No errors found (Attaching logs)"

			# Define message body and attached files
			attachment_files = [f"{LogDestination}Syncerate-{time_now}.{ext}" for ext in ["log", "out"]]
			
			# Open the attachment file and execute the mail command using subprocess
			with open(LogDestination + 'Syncerate-' + time_now + ".log", 'r') as log_file:
				log_contents = log_file.read()
				body = "----------\n\n.log file\n\n----------\n\n" + log_contents + "\n\n----------"
				mail_exit_code, stderr_output = send_mail(subject, body, recipient, attachment_files)
				
		else:

			# Define subject and message body
			subject_and_body = "Successful Syncerate.py run - No errors found (Logs Disabled)"
			mail_exit_code, stderr_output = send_mail(subject_and_body, subject_and_body, recipient)
		
		if mail_exit_code == 0:
			WasMailSent(0, "")
		else:
			WasMailSent(mail_exit_code, stderr_output)

	elif SynCoidFail:
		
		if LogDestination.upper() != "NO":
			# Define subject
			subject = "Error running Syncerate.py - Syncoid error occurred (Attaching logs)"

			# Define message body and attached files
			if os.path.isfile(LogDestination + "Syncerate-" + time_now + ".out"):
				attachment_files = [f"{LogDestination}Syncerate-{time_now}.{ext}" for ext in ["log", "err", "out"]]
			else:
				attachment_files = [f"{LogDestination}Syncerate-{time_now}.{ext}" for ext in ["log", "err"]]

			# Start with an empty body
			body = ""

			# Read contents of .err file
			with open(LogDestination + 'Syncerate-' + time_now + ".err", 'r') as error_file:
				error_contents = error_file.read()
				body += "----------\n\n.err file\n\n----------\n\n" + error_contents + "\n\n"

			# Check if .out file exists and read its contents
			out_file_path = LogDestination + 'Syncerate-' + time_now + ".out"
			if os.path.isfile(out_file_path):
				with open(out_file_path, 'r') as out_file:
					out_contents = out_file.read()
					body += "----------\n\n.out file\n" + out_contents

			# Send the Mail
			mail_exit_code, stderr_output = send_mail(subject, body, recipient, attachment_files)

		else:

			# Define subject and message body
			subject_and_body = "Error running Syncerate.py - Syncoid error occurred (Logs Disabled)"
			
			# Send the Mail
			mail_exit_code, stderr_output = send_mail(subject_and_body, subject_and_body, recipient)

		if mail_exit_code == 0:
			WasMailSent(0, "")
		else:
			WasMailSent(mail_exit_code, stderr_output)

		sys.exit(SynCoidFail)

	elif not Exit_Code == 0 and not Exit_Code == None:

		if LogDestination.upper() != "NO":
			# Define subject
			subject = "Error running Syncerate.py - This was a script error (Attaching logs)"

			# Define message body and attached files
			if os.path.isfile(LogDestination + "Syncerate-" + time_now + ".out"):
				attachment_files = [f"{LogDestination}Syncerate-{time_now}.{ext}" for ext in ["log", "err", "out"]]
			else:
				attachment_files = [f"{LogDestination}Syncerate-{time_now}.{ext}" for ext in ["log", "err"]]
			
			# Start with an empty body
			body = ""

			# Read contents of .err file
			with open(LogDestination + 'Syncerate-' + time_now + ".err", 'r') as error_file:
				error_contents = error_file.read()
				body += "----------\n\n.err file\n\n----------\n\n" + error_contents + "\n\n"

			# Check if .out file exists and read its contents
			out_file_path = LogDestination + 'Syncerate-' + time_now + ".out"
			if os.path.isfile(out_file_path):
				with open(out_file_path, 'r') as out_file:
					out_contents = out_file.read()
					body += "----------\n\n.out file\n" + out_contents

			# Send the Mail
			mail_exit_code, stderr_output = send_mail(subject, body, recipient, attachment_files)

		else:

			# Define subject and message body
			subject_and_body = "Error running Syncerate.py - This was a script error (Logs Disabled)"
			
			# Send the Mail
			mail_exit_code, stderr_output = send_mail(subject_and_body, subject_and_body, recipient)

		if mail_exit_code == 0:
			WasMailSent(0, "")
		else:
			WasMailSent(mail_exit_code, stderr_output)

		sys.exit(Exit_Code)
	
	elif MQTT_Fail:

		if LogDestination.upper() != "NO":
			# Define subject
			subject = "Error sending MQTT message - (Attaching logs)"

			# Define message body and attached files
			if os.path.isfile(LogDestination + "Syncerate-" + time_now + ".out"):
				attachment_files = [f"{LogDestination}Syncerate-{time_now}.{ext}" for ext in ["log", "err", "out"]]
			else:
				attachment_files = [f"{LogDestination}Syncerate-{time_now}.{ext}" for ext in ["log", "err"]]
			
			# Start with an empty body
			body = ""

			# Read contents of .err file
			with open(LogDestination + 'Syncerate-' + time_now + ".err", 'r') as error_file:
				error_contents = error_file.read()
				body += "----------\n\n.err file\n\n----------\n\n" + error_contents + "\n\n"

			# Check if .out file exists and read its contents
			out_file_path = LogDestination + 'Syncerate-' + time_now + ".out"
			if os.path.isfile(out_file_path):
				with open(out_file_path, 'r') as out_file:
					out_contents = out_file.read()
					body += "----------\n\n.out file\n" + out_contents

			# Send the Mail
			mail_exit_code, stderr_output = send_mail(subject, body, recipient, attachment_files)

		else:

			# Define subject and message body
			subject_and_body = "Error sending MQTT message - (Logs Disabled)"
			
			# Send the Mail
			mail_exit_code, stderr_output = send_mail(subject_and_body, subject_and_body, recipient)
		
		if mail_exit_code == 0:
			WasMailSent(0, "")
		else:
			WasMailSent(mail_exit_code, stderr_output)
		
		sys.exit(MQTT_Fail)

def WasMailSent(MailExitCode, popenstderr):
	if MailExitCode == 0:
		logger.info('')
		logger.info('----------')
		logger.info('')
		logger.info('Mail was send succesfully')
	else:
		logger.error('')
		logger.error('----------')
		logger.error('')
		logger.error('There was an error sending the mail')
		logger.error('This is what popen said')
		logger.error('')
		logger.error(popenstderr)
		logger.error('')
		logger.error('----------')

def SystemAction():
	if not MailOption.upper() == "NO":
		logger.info('')
		logger.info('----------')
		logger.info('')
		logger.info('The system has an option after the script finishes')
		logger.info('')
		logger.info('The options is')
		logger.info('')
		logger.info(SystemOption)
		logger.info('')
		logger.info('Gonna sleep for 2 minutes to insure mail is sent')
		logger.info('')
		logger.info('Then execute the command	:	' + SystemOption)
		logger.info('')
		logger.info('----------')

		# Sleep before executing the desired action
		time.sleep(120)

		os.system(SystemOption)

	elif not SystemOption.upper() == "NO" and MailOption.upper() == "NO":
		logger.info('')
		logger.info('----------')
		logger.info('')
		logger.info('The system has an option after the script finishes')
		logger.info('')
		logger.info('The options is')
		logger.info('')
		logger.info(SystemOption)
		logger.info('')
		logger.info('No mail option chosen')
		logger.info('')
		logger.info('Gonna execute the command	:	' + SystemOption)
		logger.info('')
		logger.info('----------')

		os.system(SystemOption)

def succesfull_run(MQTT=None, SendMail=None, PerformSystemAction=None):

	logger.info('')
	logger.info('----------')
	logger.info('')
	logger.info('The Script ended succesfully')
	logger.info('')
	logger.info('Now going over MAIL, MQTT and System Option, if option is set in the .cfg file')
	logger.info('')
	logger.info('Errors for these can still be raised, at this point of the script')
	logger.info('')
	
	if not LogDestination.upper() == "NO":
		with open(LogDestination + 'Syncerate-' + time_now + ".out", 'a') as fout:
			lines_of_text = [
				"",
				"----------",
				"",
				"The Script ended succesfully",
				"",
				"Now going over MAIL, MQTT and System Option, if option is set in the .cfg file",
				"",
				"Errors for these can still be raised, at this point of the script",
				"",
				"----------",
				"",
			]

			for line in lines_of_text:
				fout.write(line + "\n")
	
	if MQTT == "YES":
		# Your MQTT logic here
		mqtt_topic = config.get('Syncerate Config', 'mqtt_topic')
		mqtt_message = config.get('Syncerate Config', 'mqtt_message')
		broker_address = config.get('Syncerate Config', 'broker_address')
		broker_port = config.get('Syncerate Config', 'broker_port')
		broker_port = int(broker_port)
		mqtt_username = config.get('Syncerate Config', 'mqtt_username')
		mqtt_password = config.get('Syncerate Config', 'mqtt_password')

		 # Create MQTT client instance
		client = mqtt.Client()
		client.enable_logger(logging.getLogger("paho"))
		client.username_pw_set(mqtt_username, mqtt_password)
		client.on_connect = lambda client, userdata, flags, rc: mqtt_connect(client, userdata, flags, rc, mqtt_topic, mqtt_message)

		try:
			# Attempt to connect to the MQTT broker
			client.connect(broker_address, broker_port)
		except OSError as e:
			# Handle the specific error [Errno 113] No route to host
			if e.errno == 113:
				logging.error('MQTT server is not reachable. Check IP and Port.')
				# Add your specific error handling code here
			else:
				logging.error(f'Failed to connect to MQTT broker: {str(e)}')
			die(None, None, None, None, e)

		# Optionally, send a message if HomeAssistant is an option
		if Use_HomeAssistant == "YES":
			homeassistant_topic = config.get('Syncerate Config', 'HomeAssistant_Available')
			homeassistant_message = "online"
			client.publish(homeassistant_topic, homeassistant_message, retain=True)

		# Publish a normal message
		client.publish(mqtt_topic, mqtt_message, retain=True)

		# Start the MQTT network loop
		client.loop_forever()

	if SendMail:
		# Decide if there is an option to send mail
		if not MailOption.upper() == "NO":
			MailTo(0)

	if PerformSystemAction:
		# Decide if there is a shutdown action for the system on succesfull comletion
		if not SystemOption.upper() == "NO":
			SystemAction()
	
# In case something is wrong with the List's
# number of items or end names in order
def missmatchinglists(Lenght, Names):
   
	if Lenght == True:
		logger.error('')
		logger.error('----------')
		logger.error('')
		logger.error('The number of items in each list does not match')
		logger.error('Check the terminal or .err log')
		logger.error('exiting - error code 1')
	if Names == True:
		logger.error('')
		logger.error('----------')
		logger.error('')
		logger.error('There are datasets on source and destination which ends doesnt match up')
		logger.error('Check the terminal or .err log')
		logger.error('exiting - error code 1')
	MailTo(1,"")
	sys.exit(1)

# Create the arguments to be processed
parser = argparse.ArgumentParser(description='Iterate though 2 lists of ZFS DataSets with Syncoid')
parser.add_argument('--conf', '-c', type=str, required=True,
					help='The destination for the config file')

# Save the arguments to 'args'
args = parser.parse_args()

# ----

# Time to import variables from config file
config = configparser.RawConfigParser()
config.read(args.conf)

# This is to get the mail or "No" option for mail
MailOption = (config.get('Syncerate Config', 'Mail'))

# This is for the command after the script has succesfully run
SystemOption = (config.get('Syncerate Config', 'SystemAction'))


# This is for the MQTT option
Use_MQTT = config.get('Syncerate Config', 'Use_MQTT')
Use_MQTT = Use_MQTT.upper()

# This is for the HomeAssistant MQTT option
Use_HomeAssistant = config.get('Syncerate Config', 'Use_HomeAssistant')
Use_HomeAssistant = Use_HomeAssistant.upper()

# This is for creating the Date format for the Log Files
DateTime = config.get('Syncerate Config', 'DateTime')
time_now  = datetime.datetime.now().strftime(DateTime)

# This is for the logfile creation
LogDestination=config.get('Syncerate Config', 'LogDestination')

# This is to enable or disable Loggin
if not LogDestination.upper() == "NO":
	if not LogDestination.endswith('/'):
		LogDestination = LogDestination + "/"

# This logger function will log everything including errors to ".log" and only errors to ".err"
# It is called with logger.(info/error)
def get_logger(    
		LOG_FORMAT     = '%(asctime)s %(levelname)s: %(message)s',
		LOG_NAME       = '',
		LOG_FILE_INFO  = LogDestination + "Syncerate-" + time_now + ".log",
		LOG_FILE_WARNING = LogDestination + "Syncerate-" + time_now + ".err",
		LOG_FILE_ERROR = LogDestination + "Syncerate-" + time_now + ".err",
    	enable_file_logging=True):

	log           = logging.getLogger(LOG_NAME)
	log_formatter = logging.Formatter(LOG_FORMAT)

	if enable_file_logging:
		# If log folder is missing, create it
		os.makedirs(LogDestination, exist_ok=True)

		# Set up log files
		file_handler_info = logging.FileHandler(LOG_FILE_INFO, mode='w')
		file_handler_info.setFormatter(log_formatter)
		file_handler_info.setLevel(logging.INFO)
		log.addHandler(file_handler_info)

		file_handler_warning = logging.FileHandler(LOG_FILE_WARNING, mode='w')
		file_handler_warning.setFormatter(log_formatter)
		file_handler_warning.setLevel(logging.WARNING)
		log.addHandler(file_handler_warning)

		file_handler_error = logging.FileHandler(LOG_FILE_ERROR, mode='w')
		file_handler_error.setFormatter(log_formatter)
		file_handler_error.setLevel(logging.ERROR)
		log.addHandler(file_handler_error)


	# comment this to suppress console output
	stream_handler = logging.StreamHandler(sys.stdout)
	stream_handler.setFormatter(log_formatter)
	log.addHandler(stream_handler)

	log.setLevel(logging.INFO)

	return log

if not LogDestination.upper() == "NO":
	logger = get_logger(enable_file_logging=True)
else:
	logger = get_logger(enable_file_logging=False)
	logger.info('')
	logger.info('----------')
	logger.info('Logging has beend disabled')
	logger.info('')
	logger.info('Only writing to terminal')

# Print the config file destination from the scripts argument
logger.info('')
logger.info('----------')
logger.info('')
logger.info('Config file destination  :   %s', args.conf)

# Write Date format to screen
logger.info('')
logger.info("The Date used for Log Files  :   %s", time_now)

# Examples of using the logger function
#  
#logger.info('This is an INFO message')
#logger.warning('This is a WARNING message')
#logger.error('This is an ERROR message')

# Save the importet variables to .log file
for section in config.sections():
	logger.info('')
	logger.info('----------')
	logger.info('')
	logger.info('These are the imported variables in the config file')
	logger.info('Omitting the "PassWord" since it shouldten be logged')
	logger.info('')
	logger.info(section)
	logger.info('')
	for option in config.options(section):
		value = config.get(section, option)
		if option not in ['password', 'mqtt_username', 'mqtt_password']:
			logger.info(f'{option} {value}')
			logger.info('')
		

# Check if the "syncoid command" is in use
if config.get('Syncerate Config','SyncoidCommand').startswith("syncoid") == True:
	logger.info('The syncoid command is in use')
	logger.info('')
	logger.info('----------')
	logger.info('')

# Import the Source file to a Python3 list
SourceListImport = open(config.get('Syncerate Config', 'SourceListPath'), "r")
SourceLines = SourceListImport.read().splitlines()
logger.info('Items in the Source list    :   %s', SourceLines)
logger.info('Number of items in the Source list    :   %i', (len(SourceLines)))
SourceListImport.close()
print('')
logger.info('')

# Import the Destination file to a Python3 list
DestListImport = open(config.get('Syncerate Config', 'DestListPath'), "r")
DestLines = DestListImport.read().splitlines()
logger.info('Items in the Destiantion list    %s:   ', DestLines)
logger.info('Number of items in the Source list    :   %i', len(DestLines))
DestListImport.close()
print('')
logger.info('')

# Compare the number of items in the two list's
if len(SourceLines) == len(DestLines):
	logger.info('The Source and Dest files has the same number of items')
	logger.info('')
else:
	missmatchinglists(Lenght=True, Names=False)

# Iterate through SourceLines and DestLine List's at the same time
# And compare if the end of the datasets matches
ListsChecksOut = True
for (i, h) in zip(SourceLines, DestLines):
	if i.rpartition("/")[-1] == h.rpartition("/")[-1]:
		logger.info('The end of this Source and Destination Datasets matches:')
		logger.info('Source :   %s', i)
		logger.info('Dest   :   %s', h)
		logger.info('')
	else:
		logger.error('The end of this Source and Destination Datasets end does not match:')
		logger.error('Source :   %s', i)
		logger.error('Dest   :   %s', h)
		logger.error('')
		ListsChecksOut = False

if ListsChecksOut == True:
	logger.info('All datasets ends matches')
	logger.info('continuing')
else:
	missmatchinglists(Lenght=False, Names=True)

# Get the choice for a password from the config
PassWordOption=(config.get('Syncerate Config', 'PassWord'))

if PassWordOption.upper() == 'ASK':
	PassWord = getpass('PLz. insert a desiret password if needed :    ')
	logger.info('')
	logger.info('----------')
	logger.info('')
	logger.info('The Password has been manualy added, not written to log')
	logger.info('')
	print('')
	print('This is the Password you have given  :   ', PassWord)
	print('')
elif PassWordOption.upper() == 'NO':
	logger.info('')
	logger.info('----------')
	logger.info('')
	logger.info('No password is in use')
else:
	PassWord=PassWordOption
	logger.info('')
	logger.info('----------')
	logger.info('')
	logger.info('Password is in the config file, not written to log')
	print('')
	print('This is the password in the config file  :   ', PassWord)
	print('')

# Get the Syncoid command to be altered
SyncoidCommand=config.get('Syncerate Config', 'SyncoidCommand')

# This is in case the thee pexpect/syncoid command fails
# I am not sure it will catch all errors
def die(child=None, errstr=None, error_code=None, SynCoidFail=None, MQTT_Fail=None, SynCoidFailChild=None):

	if child:
		logger.error('')
		logger.error('This was a crash known by the script')
		logger.error('')
		logger.error('Check the logs to see what could be the problem')
		logger.error('If not logs exist, enable them to track down the problem')
		logger.error('')
		logger.error(errstr)
		logger.error('')
		logger.error('This is the last part of Syncoid output   : ' + child.before)
		logger.error('This is the warning/error   :   ' + child.after + child.buffer)
		logger.error('')
		logger.error('This is the script exit code : ' + error_code)
		logger.error('')
		child.terminate()

		# I had problems that the exit code given to "die" function was "str", i couldten send "int" to "die" function instead but i could convert "str" to "int"
		# This was understood from https://medium.com/@anupkumarray/working-with-exit-codes-between-python-shell-scripts-177931204291
		integer_number = int(error_code)

		# Send a mail related to script error
		if not MailOption.upper() == "NO":
			MailTo(error_code)
		else:
			# Exit the script with the SynCoid exit status
			sys.exit(integer_number)

	elif SynCoidFail:
		logger.error('')
		logger.error('This was an unknown crash')
		logger.error('')
		logger.error('Check the logs to see what could be the problem')
		logger.error('If non existing enable them, to track down the problem')
		logger.error('')
		logger.error('This is the last part of Syncoid output   : ' + "\n" + SynCoidFailChild.before)
		logger.error('')

		if not MailOption.upper() == "NO":
			MailTo(None, SynCoidFail)
		else:
			sys.exit(SynCoidFail)

	elif MQTT_Fail:
		logger.error('')
		logger.error('This was an MQTT error')
		logger.error('')
		logger.error('Check the logs to see what could be the problem')
		logger.error('If non existing enable them, to track down the problem')
		logger.error('')
		logger.error('This is the MQTT exit code   : %s', MQTT_Fail)
		logger.error('')

		if not MailOption.upper() == "NO":
			MailTo(None, None, MQTT_Fail)
		else:
			sys.exit(MQTT_Fail)
		

# This is the function that executes the altered syncoid command
# It allso have a little error checking.
# But i am in doubt it will catch all errors

ISREPEATED = False
CONTINUENODESTROYSNAP = False

def ssh_command(SynCoid_Command):

	global ISREPEATED
	global CONTINUENODESTROYSNAP

	CONTINUENODESTROYSNAP = False
	CONTINUENORESUME = False

	# spawn the child process
	if not LogDestination.upper() == "NO":
		with open(LogDestination + 'Syncerate-' + time_now + ".out", 'a') as fout:
			lines_of_text = [
				"",
				"----------",
				"",
			]

			for line in lines_of_text:
				fout.write(line + "\n")
	
	child = pexpect.spawn(SynCoid_Command, timeout=None, encoding='utf-8')

	if not LogDestination.upper() == "NO":
		fout = open(LogDestination + 'Syncerate-' + time_now + ".out",'a')
		child.logfile = fout

	# set up a list of patterns to match
	# The easiest way to force a Syncoid Error is to remove "Connection timed out" and give a wrong port number
	patterns = [
	    'Are you sure you want to continue connecting',
	    'could not find any snapshots to destroy; check snapshot names.',
	    'Permission denied',
	    'Connection timed out',
	    'Connection refused',
	    'passphrase',
		pexpect.EOF,
		'WARN Skipping dataset',
		'WARN',
		'WARN: resetting partially receive state because the snapshot source no longer exists',
	]

	# MAc times a pattern must repeat
	max_pattern_executions = 5
	# increment the pattern count for the matched pattern to zero before loop begins
	pattern_count = {i: 0 for i in range(len(patterns))}

	while True:
		index = child.expect(patterns)
		pattern_count[index] += 1

		# check if the pattern has been executed more than the maximum allowed number of times
		if pattern_count[index] > max_pattern_executions:
			logger.error('')
			logger.error(f"Pattern '{patterns[index]}' has been executed more than {max_pattern_executions} times.")
			logger.error('')
			ISREPEATED = True
			break

		# execute code based on the matched pattern
		if index == 0:
			# SSH does not have the public key. Just accept it.
			# respond to 'Are you sure you want to continue connecting'
			child.sendline ('yes')
		elif index == 1:
			logger.info('')
			logger.info('----------')
			logger.info('')
			logger.info('Syncoid wanted to delete a syncoid created snapshot on Source that is no longer available')
			logger.info('')
			logger.info('Going the continue the script,')
			logger.info('since this a normal error when having multiple host/server sharing the same datasets')
			CONTINUENODESTROYSNAP = True
			return child
		elif index == 2:
			# respond to 'Permission denied'
			die(child, 'ERROR!  Incorrect password. Here is what SSH said:', "5")
			break
		elif index == 3:
			# respond to 'Connection timed out'
			die(child, 'ERROR!  Connection Timeout. Here is what SSH said:', "6")
			break
		elif index == 4:
			# respond to 'Connection refused'
			die(child, 'ERROR!  Connection refused. Here is what SSH said:', "7")
			break
		elif index == 5:
			# respond to 'passphrase'
			if not LogDestination.upper() == "NO":
				child.logfile = None
			child.sendline (PassWord)
			if not LogDestination.upper() == "NO":
				child.logfile = fout
		elif index == 6:
			# respond to pexpect.EOF
			return child
		elif index == 7:
			# respond to 'dataset does not exist'
			die(child, 'Destination dataset does not exist - Plz recheck the Source and dest list to be sure:', "8")
			break
		elif index == 8:
			# respond to 'WARN'
			die(child, 'ERROR!  There Was a Warning. Here is what SSH said:', "4")
			break
		elif index == 9:
			# respond to 'WARN: resetting partially receive state because the snapshot source no longer exists'
			CONTINUENORESUME = True
			logger.info('')
			logger.info('----------')
			logger.info('')
			logger.info('The last transfer of a dataset failed and there is no matching snapshots between sender and receiver,')
			logger.info('This is most likely due to the fact that the origional snapshot used for the transfer is missing and cant resume without that snapshot')
			logger.info('')
			logger.info('Gonna rerun the command with --no-resume to make Syncoid continue from the last matching snapshot')
			logger.info('')
			SynCoid_Command = SynCoid_Command + " --no-resume"

	return child

# This is the main() part of the script
# It is called after everything else have been imported/prepared
def main():
	global ISREPEATED
	global CONTINUENODESTROYSNAP

	KNOWNERROR = False

	for (h, i) in zip(SourceLines, DestLines):
		
		if not h.startswith('"') or not h.endswith('"'):
			# Add quotes where they are missing
			if not h.startswith('"'):
				h = '"' + h
			if not h.endswith('"'):
				h += '"'

		if not i.startswith('"') or not i.endswith('"'):
			# Add quotes where they are missing
			if not i.startswith('"'):
				i = '"' + i
			if not i.endswith('"'):
				i += '"'

		SyncoidExecute=SyncoidCommand.replace("SourceDataSet", h)
		SyncoidExecute=SyncoidExecute.replace("DestDataSet", i)
		
		logger.info('')
		logger.info('----------')
		logger.info('')
		logger.info('Ececuting the altered SynCoid Command    :   %s', SyncoidExecute)
		
		child = ssh_command(SyncoidExecute)
		
		child.close()

		if ISREPEATED == True:
			die(child, 'ERROR: The script is repeating itself', "9")

		if ((not child.exitstatus == 0) and (CONTINUENODESTROYSNAP == False)):
			logger.error('')

			if child.exitstatus is None:
				logger.error('This is the SynCoid Exit status   :   %s', child.exitstatus)
			else:
				logger.error('This is the SynCoid Exit status   :   %i', child.exitstatus)
				ExitStatusAsInteger = int(child.exitstatus)
				die(None, None, None, ExitStatusAsInteger, None, child)

			if child.signalstatus is None:
				logger.error('This is the SynCoid signal Status    :   %s', child.signalstatus)
			else:
				logger.error('This is the SynCoid signal Status    :   %i', child.signalstatus)

		#if CONTINUENORESUME == True:
		#		logger.info('')
		#	logger.info('----------')
		#	logger.info('')
		#	logger.info('The last transfer of a dataset failed and there is no matching snapshots between sender and receiver,')
		#	logger.info('This is most likely due to the fact that the origional snapshot used for the transfer is missing and cant resume without that snapshot')
		#	logger.info('')
		#	logger.info('Gonna rerun the command with --no-resume to make Syncoid continue from the last matching snapshot')
		#	logger.info('')
		#	CONTINUENORESUME == False
		#	SyncoidExecute = SyncoidExecute + " --no-resume"


	
	succesfull_run(Use_MQTT, MailOption, SystemOption)

# This is the if statement that starts main() and the syncing
# It has a bit of error checking and should be able to send it by mail
# Not sure if the send mail on error works

if __name__ == '__main__':
	try:
		main()
	except Exception as e:
		logger.error('')
		logger.error(str(e))
		logger.error('')
		logger.error(traceback.print_exc())
		logger.error('')
		MailTo(2,"")
		sys.exit(2)
