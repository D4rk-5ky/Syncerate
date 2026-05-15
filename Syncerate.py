#!/usr/bin/python3

# Import argument parser for python arguments
import argparse

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

import shlex

# For sending a message over MQTT
import paho.mqtt.publish as publish

logger = logging.getLogger("syncerate")

EXIT_OK = 0
EXIT_LIST_ERROR = 1
EXIT_SCRIPT_ERROR = 2
EXIT_WARNING = 4
EXIT_PASSWORD_DENIED = 5
EXIT_CONNECTION_TIMEOUT = 6
EXIT_CONNECTION_REFUSED = 7
EXIT_DATASET_MISSING = 8
EXIT_REPEATED_PATTERN = 9
EXIT_MQTT_ERROR = 10
EXIT_SYSTEM_ACTION_ERROR = 11
	
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

def send_mqtt_messages():
    broker_address = config.get('Syncerate Config', 'broker_address')
    broker_port = config.getint('Syncerate Config', 'broker_port')

    mqtt_username = config.get('Syncerate Config', 'mqtt_username', fallback='').strip()
    mqtt_password = config.get('Syncerate Config', 'mqtt_password', fallback='')

    auth = None
    if mqtt_username:
        auth = {
            "username": mqtt_username,
            "password": mqtt_password,
        }

    messages = []

    if Use_HomeAssistant == "YES":
        messages.append({
            "topic": config.get('Syncerate Config', 'HomeAssistant_Available'),
            "payload": "online",
            "retain": True,
            "qos": 0,
        })

    messages.append({
        "topic": config.get('Syncerate Config', 'mqtt_topic'),
        "payload": config.get('Syncerate Config', 'mqtt_message'),
        "retain": True,
        "qos": 0,
    })

    try:
        publish.multiple(
            messages,
            hostname=broker_address,
            port=broker_port,
            auth=auth,
        )
        logger.info("MQTT message(s) published successfully")

    except Exception:
        logger.exception("Failed publishing MQTT message(s)")

        if MailOption.upper() != "NO":
            MailTo(None, None, EXIT_MQTT_ERROR)

        sys.exit(EXIT_MQTT_ERROR)

# This is for the send mail function
# In case one needs to be notified of errors
#
# FIx and make sure to make it possible to send error message even if .out file is not created yet
def MailTo(Exit_Code=None, SynCoidFail=None, MQTT_Fail=None):
	if MailOption.upper() == "NO":
		return
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

		try:
			subprocess.run(SystemOption, shell=True, check=False)
		except Exception:
			logger.exception("Failed running SystemAction")

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

		try:
			subprocess.run(SystemOption, shell=True, check=False)
		except Exception:
			logger.exception("Failed running SystemAction")

def successfull_run(MQTT=None, SendMail=None, PerformSystemAction=None):

	logger.info('')
	logger.info('----------')
	logger.info('')
	logger.info('The Script ended successfully')
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
				"The Script ended successfully",
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
		send_mqtt_messages()

	if SendMail:
		# Decide if there is an option to send mail
		if not MailOption.upper() == "NO":
			MailTo(0)

	if PerformSystemAction:
		# Decide if there is a shutdown action for the system on successfull comletion
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
	MailTo(EXIT_LIST_ERROR)
	sys.exit(EXIT_LIST_ERROR)

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

# This is for the command after the script has successfully run
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
def get_logger(enable_file_logging=True):
    log = logging.getLogger("syncerate")
    log.setLevel(logging.INFO)
    log.handlers.clear()
    log.propagate = False

    log_formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')

    # Terminal output
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(log_formatter)
    stream_handler.setLevel(logging.INFO)
    log.addHandler(stream_handler)

    if enable_file_logging:
        os.makedirs(LogDestination, exist_ok=True)

        # Full log file
        info_handler = logging.FileHandler(
            LogDestination + "Syncerate-" + time_now + ".log",
            mode="w"
        )
        info_handler.setFormatter(log_formatter)
        info_handler.setLevel(logging.INFO)
        log.addHandler(info_handler)

        # Error-only file
        err_handler = logging.FileHandler(
            LogDestination + "Syncerate-" + time_now + ".err",
            mode="w"
        )
        err_handler.setFormatter(log_formatter)
        err_handler.setLevel(logging.ERROR)
        log.addHandler(err_handler)

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

def read_dataset_list(path):
    with open(path, "r", encoding="utf-8") as f:
        return [
            line.strip()
            for line in f
            if line.strip() and not line.strip().startswith("#")
        ]

def parse_destination_line(line):
	"""
	Parse one destination-list line.

	Supported formats:

	Storage/Docker

	Storage/Docker: --recvoptions="o recordsize=1M o compression=zstd-9"

	Important:
	- We split on ': ' using rsplit()
	- This avoids breaking remote destinations like:
	  root@10.0.0.2:Storage/Docker
	"""

	if ": " not in line:
		return line, []

	destination_dataset, extra_args_text = line.rsplit(": ", 1)

	destination_dataset = destination_dataset.strip()
	extra_args_text = extra_args_text.strip()

	if not extra_args_text:
		return destination_dataset, []

	try:
		extra_args = shlex.split(extra_args_text)
	except ValueError as e:
		raise ValueError(
			f"Could not parse extra arguments for destination line:\n"
			f"{line}\n"
			f"shlex error: {e}"
		) from e

	return destination_dataset, extra_args


def parse_destination_list(destination_lines):
	"""
	Return two lists:

	1. Destination datasets only
	2. Extra arguments per destination

	Example:

	Input:
	Storage/Docker: --recvoptions="o recordsize=1M o compression=zstd-9"

	Output:
	DestDatasets:
	["Storage/Docker"]

	DestExtraArgs:
	[["--recvoptions=o recordsize=1M o compression=zstd-9"]]
	"""

	dest_datasets = []
	dest_extra_args = []

	for line in destination_lines:
		destination_dataset, extra_args = parse_destination_line(line)

		dest_datasets.append(destination_dataset)
		dest_extra_args.append(extra_args)

	return dest_datasets, dest_extra_args

# Import the Source file to a Python3 list
SourceLines = read_dataset_list(config.get('Syncerate Config', 'SourceListPath'))

logger.info('Items in the Source list    :   %s', SourceLines)
logger.info('Number of items in the Source list    :   %i', len(SourceLines))
logger.info('')

# Import the Destination file to a Python3 list
DestLinesRaw = read_dataset_list(config.get('Syncerate Config', 'DestListPath'))

try:
	DestLines, DestExtraArgs = parse_destination_list(DestLinesRaw)
except ValueError as e:
	logger.error("%s", e)
	MailTo(EXIT_LIST_ERROR)
	sys.exit(EXIT_LIST_ERROR)

logger.info('Raw items in the Destination list    :   %s', DestLinesRaw)
logger.info('Parsed Destination datasets          :   %s', DestLines)
logger.info('Parsed Destination extra args        :   %s', DestExtraArgs)
logger.info('Number of items in the Destination list    :   %i', len(DestLines))
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
PassWord = None

PassWordOption = config.get('Syncerate Config', 'PassWord')

if PassWordOption.upper() == 'ASK':
	PassWord = getpass('PLz. insert a desiret password if needed :    ')
	logger.info('')
	logger.info('----------')
	logger.info('')
	logger.info('The Password has been manualy added, not written to log')
	logger.info('')

elif PassWordOption.upper() == 'NO':
	logger.info('')
	logger.info('----------')
	logger.info('')
	logger.info('No password is in use')

else:
	PassWord = PassWordOption
	logger.info('')
	logger.info('----------')
	logger.info('')
	logger.info('Password is in the config file, not written to log')

# Get the Syncoid command to be altered
SyncoidCommand=config.get('Syncerate Config', 'SyncoidCommand')

# This is in case the thee pexpect/syncoid command fails
# I am not sure it will catch all errors
def die(child=None, errstr=None, error_code=None, SynCoidFail=None, MQTT_Fail=None, SynCoidFailChild=None):
    if error_code is not None:
        exit_code = int(error_code)
    elif SynCoidFail is not None:
        exit_code = int(SynCoidFail)
    elif MQTT_Fail is not None:
        exit_code = int(MQTT_Fail)
    else:
        exit_code = 1

    def safe_text(value):
        if value is None:
            return ""
        return str(value)

    logger.error('')
    logger.error('----------')
    logger.error('')

    if child:
        logger.error('This was a crash known by the script')
        logger.error('')
        logger.error('Check the logs to see what could be the problem')
        logger.error('If no logs exist, enable them to track down the problem')
        logger.error('')

        if errstr:
            logger.error(errstr)
            logger.error('')

        logger.error('This is the last part of Syncoid output:')
        logger.error(safe_text(child.before))
        logger.error('')

        logger.error('This is the warning/error:')
        logger.error(safe_text(child.after) + safe_text(child.buffer))
        logger.error('')

        logger.error('This is the script exit code: %s', exit_code)

        try:
            child.terminate(force=True)
        except Exception:
            logger.exception("Could not terminate child process cleanly")

    elif SynCoidFail is not None:
        logger.error('This was an unknown Syncoid crash')
        logger.error('Syncoid exit code: %s', exit_code)

        if SynCoidFailChild is not None:
            logger.error('')
            logger.error('This is the last part of Syncoid output:')
            logger.error(safe_text(SynCoidFailChild.before))

    elif MQTT_Fail is not None:
        logger.error('This was an MQTT error')
        logger.error('MQTT exit code: %s', exit_code)

    else:
        logger.error('This was a script error')
        logger.error('Exit code: %s', exit_code)

    logger.error('')
    logger.error('----------')
    logger.error('')

    if MailOption.upper() != "NO":
        if MQTT_Fail is not None:
            MailTo(None, None, exit_code)
        elif SynCoidFail is not None:
            MailTo(None, exit_code)
        else:
            MailTo(exit_code)

    sys.exit(exit_code)
		

# This is the function that executes the altered syncoid command
# It allso have a little error checking.
# But i am in doubt it will catch all errors

def log_command_debug(command_list):
	logger.info('')
	logger.info('Syncoid command debug:')
	logger.info('')
	logger.info('Shell-style command:')
	logger.info('%s', shlex.join(command_list))

	logger.info('')
	logger.info('Raw Python argv:')
	logger.info('%r', command_list)

	logger.info('')
	logger.info('Individual arguments:')
	logger.info('Argument count: %s', len(command_list))

	for number, argument in enumerate(command_list):
		logger.info('argv[%s] = %r', number, argument)

	logger.info('')


def escape_dataset_for_syncoid(dataset):
	"""
	Optional workaround for syncoid internals that may split dataset names
	with spaces.

	Normal:
	Storage/DataSet With Spaces

	Escaped:
	Storage/DataSet\ With\ Spaces
	"""

	escape_spaces = config.getboolean(
		'Syncerate Config',
		'EscapeSpacesForSyncoid',
		fallback=False
	)

	if not escape_spaces:
		return dataset

	return dataset.replace("\\", "\\\\").replace(" ", "\\ ")

def build_syncoid_command(command_template, source_dataset, dest_dataset, extra_args=None):
	"""
	Build a safe argv-style command list for pexpect.

	Important:
	- shlex.split() happens BEFORE replacing SourceDataSet/DestDataSet.
	- This keeps datasets with spaces as single arguments.
	- extra_args are appended at the end of the syncoid command.
	"""

	if extra_args is None:
		extra_args = []

	source_dataset = escape_dataset_for_syncoid(source_dataset)
	dest_dataset = escape_dataset_for_syncoid(dest_dataset)

	command_parts = shlex.split(command_template)

	command_parts = [
		part.replace("SourceDataSet", source_dataset).replace("DestDataSet", dest_dataset)
		for part in command_parts
	]

	command_parts.extend(extra_args)

	return command_parts

def close_child_logfile(child):
	if child is None:
		return

	logfile = getattr(child, "logfile", None)

	if logfile is None:
		return

	try:
		logfile.flush()
		logfile.close()
	except Exception:
		logger.exception("Could not close pexpect logfile cleanly")
	finally:
		child.logfile = None

def ssh_command(SynCoid_Command):

	global ISREPEATED
	global CONTINUENODESTROYSNAP
	global CONTINUENORESUME

	ISREPEATED = False
	CONTINUENODESTROYSNAP = False
	CONTINUENORESUME = False

	# Initialize modified command
	modified_command = SynCoid_Command

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
	
	child = pexpect.spawn(
		SynCoid_Command[0],
		SynCoid_Command[1:],
		timeout=None,
		encoding='utf-8'
	)

	if not LogDestination.upper() == "NO":
		fout = open(LogDestination + 'Syncerate-' + time_now + ".out",'a')
		child.logfile = fout

	# set up a list of patterns to match
	# The easiest way to force a Syncoid Error is to remove "Connection timed out" and give a wrong port number
	PATTERN_HOSTKEY = 0
	PATTERN_NO_DESTROY_SNAP = 1
	PATTERN_PERMISSION_DENIED = 2
	PATTERN_TIMEOUT = 3
	PATTERN_REFUSED = 4
	PATTERN_PASSPHRASE = 5
	PATTERN_EOF = 6
	PATTERN_WARN_SKIPPING = 7
	PATTERN_NO_RESUME = 8
	PATTERN_GENERIC_WARN = 9
	PATTERN_PASSWORD = 10

	patterns = [
		'Are you sure you want to continue connecting',
		'could not find any snapshots to destroy; check snapshot names.',
		'Permission denied',
		'Connection timed out',
		'Connection refused',
		'passphrase',
		pexpect.EOF,
		'WARN Skipping dataset',
		'used in the initial send no longer exists',
		'WARN',
		'password',
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
		if index == PATTERN_HOSTKEY:
			child.sendline('yes')

		elif index == PATTERN_NO_DESTROY_SNAP:
			logger.info('')
			logger.info('----------')
			logger.info('')
			logger.info('Syncoid wanted to delete a syncoid-created snapshot that no longer exists.')
			logger.info('This can happen when multiple hosts share the same datasets.')
			logger.info('Marking this as non-fatal and continuing until Syncoid exits.')
			logger.info('')
			CONTINUENODESTROYSNAP = True
			continue

		elif index == PATTERN_PERMISSION_DENIED:
			die(
				child=child,
				errstr='ERROR! Incorrect password or SSH permission denied.',
				error_code=EXIT_PASSWORD_DENIED
			)

		elif index == PATTERN_TIMEOUT:
			die(child, 'ERROR! Connection timed out.', 6)

		elif index == PATTERN_REFUSED:
			die(child, 'ERROR! Connection refused.', 7)

		elif index == PATTERN_PASSPHRASE:
			if not LogDestination.upper() == "NO":
				child.logfile = None

			if PassWord is None:
				die(
					child,
					'ERROR! Password/passphrase prompt appeared, but PassWord is set to NO.',
					EXIT_PASSWORD_DENIED
				)

			child.sendline(PassWord)

			if not LogDestination.upper() == "NO":
				child.logfile = fout

		elif index == PATTERN_EOF:
			close_child_logfile(child)
			return child, modified_command

		elif index == PATTERN_WARN_SKIPPING:
			die(child, 'ERROR! Syncoid skipped a dataset. Check source/destination datasets.', 8)

		elif index == PATTERN_NO_RESUME:
			CONTINUENORESUME = True

			logger.info('')
			logger.info('----------')
			logger.info('')
			logger.info('The last transfer failed and the resume snapshot no longer exists.')
			logger.info('Gonna rerun the command with --no-resume.')
			logger.info('')

			if "--no-resume" not in SynCoid_Command:
				modified_command = SynCoid_Command + ["--no-resume"]
			else:
				modified_command = SynCoid_Command
			
			logger.info('The modified command reads : %s', shlex.join(modified_command))
			logger.info('')
			logger.info('----------')
			logger.info('')
			
			close_child_logfile(child)
			return child, modified_command

		elif index == PATTERN_GENERIC_WARN:
			die(child, 'ERROR! Syncoid produced a warning.', 4)

		elif index == PATTERN_PASSWORD:
			if not LogDestination.upper() == "NO":
				child.logfile = None

			if PassWord is None:
				die(
					child,
					'ERROR! Password/passphrase prompt appeared, but PassWord is set to NO.',
					EXIT_PASSWORD_DENIED
				)

			child.sendline(PassWord)

			if not LogDestination.upper() == "NO":
				child.logfile = fout

	close_child_logfile(child)

	return child, modified_command

# This is the main() part of the script
# It is called after everything else have been imported/prepared
def main():
	global ISREPEATED
	global CONTINUENODESTROYSNAP
	global CONTINUENORESUME

	for h, i, extra_args in zip(SourceLines, DestLines, DestExtraArgs):

		SyncoidExecute = build_syncoid_command(
			SyncoidCommand,
			h,
			i,
			extra_args
		)

		logger.info('')
		logger.info('----------')
		logger.info('')

		if extra_args:
			logger.info('Extra Syncoid arguments for this destination:')
			logger.info('%s', extra_args)
			logger.info('')

		logger.info(
			'Executing the altered Syncoid Command    :   %s',
			shlex.join(SyncoidExecute)
		)
		logger.info('')

		log_command_debug(SyncoidExecute)

		# Call ssh_command and capture both the child object and the modified command
		child, modified_command = ssh_command(SyncoidExecute)
		
		if CONTINUENORESUME:
			child.close()

			logger.info(
				'Executing the modified Syncoid Command    :    %s',
				shlex.join(modified_command)
			)

			child, modified_command = ssh_command(modified_command)
			child.close()
		else:
			child.close()

		if ISREPEATED == True:
			die(child, 'ERROR: The script is repeating itself', EXIT_REPEATED_PATTERN)

		if child.exitstatus is None and child.signalstatus is not None:
			exit_code = 128 + int(child.signalstatus)

			logger.error('')
			logger.error('Syncoid was terminated by signal: %s', child.signalstatus)
			logger.error('Using exit code: %s', exit_code)

			die(
				SynCoidFail=exit_code,
				SynCoidFailChild=child
			)
			
		if child.exitstatus != 0 and CONTINUENODESTROYSNAP is True:
			logger.warning('')
			logger.warning('Syncoid exited with non-zero status %s, but CONTINUENODESTROYSNAP is True.', child.exitstatus)
			logger.warning('Ignoring this because the known no-destroy-snapshot message was seen.')
			logger.warning('')

		if child.exitstatus != 0 and CONTINUENODESTROYSNAP is False:
			exit_code = int(child.exitstatus)

			logger.error('')
			logger.error('This is the Syncoid exit status: %s', exit_code)

			die(
				SynCoidFail=exit_code,
				SynCoidFailChild=child
			)

	successfull_run(Use_MQTT, MailOption, SystemOption)

# This is the if statement that starts main() and the syncing
# It has a bit of error checking and should be able to send it by mail
# Not sure if the send mail on error works

if __name__ == '__main__':
	try:
		main()

	except Exception:
		logger.exception("Unhandled script error")

		if MailOption.upper() != "NO":
			MailTo(2)

		sys.exit(2)
