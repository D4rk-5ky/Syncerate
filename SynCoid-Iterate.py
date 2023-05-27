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

def is_log_empty(log_path):
    if os.path.isfile(log_path + ".log"):
        return True
    elif os.path.isfile(log_path + ".err"):
        return os.stat(log_path + ".err").st_size == 0
    else:
        return True  # Log file and error file don't exist

# This is for the send mail function
# In case one needs to be notified of errors
def MailTo(Exit_Code, SynCoidFail):
	if not MailOption == 'No':

		if LogDestination.endswith('/'):
			LogDestinationNoSlash = LogDestination[:-1]
		elif not LogDestination == "No":
			LogDestinationNoSlash = LogDestination

		# Define recipient, subject, and message body
		recipient = (config.get('SynCoid Config', 'Mail'))
				
		log_file = LogDestination + "SynCoidIterate-" + time_now

		if is_log_empty(log_file):
			logger.info('')
			logger.info('----------')
			logger.info('')
			logger.info('Error log is empty')

			if not LogDestination == "No":

				subject = "Succesfull Syncoid-Iterate.py run - Attaching logs to confirm"

				attachment_file = LogDestination + "SynCoidIterate-" + time_now + ".log"
				attachment_files = [f"{LogDestinationNoSlash}/SynCoidIterate-{time_now}.{ext}" for ext in ["log", "out"]]

				# Build the mail command with attachments
				attachment_args = " ".join([f"--attach '{file}'" for file in attachment_files])
				mail_command = f"mail -s '{subject}' {recipient} {attachment_args} < '{attachment_file}'"
				
				# Open the attachment file and execute the mail command using subprocess
				with open(attachment_file, "rb") as f:
						p = subprocess.Popen(mail_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
						stdout, stderr = p.communicate(f.read())
						Mail_Exit_Code = p.returncode			
			
			else:

				if not SynCoidFail == "":
					logger.error('')
					logger.error('----------')
					logger.error('')
					logger.error('This was a Syncoid crash/fail')
					logger.error('')
					logger.error('The exit code from Syncoid was : %i', SynCoidFail)
					logger.error('')
					if not LogDestination == "No":
						logger.error('Plz read in the logs what might have gone wrong')
						logger.error('')
						logger.error('----------')
					else:
						logger.error('Logs Disabled, consider enabling')
						logger.error('')
						logger.error('----------')
					
					if not LogDestination == "No":

						subject = "There was an error running Syncoid-Iterate.py - this was a Syncoid error - Attaching error logs to confirm"
						attachment_file = LogDestination + "SynCoidIterate-" + time_now + ".err"
						attachment_files = [f"{LogDestinationNoSlash}/SynCoidIterate-{time_now}.{ext}" for ext in ["log", "err", "out"]]

						# Build the mail command with attachments
						attachment_args = " ".join([f"--attach '{file}'" for file in attachment_files])
						mail_command = f"mail -s '{subject}' {recipient} {attachment_args} < '{attachment_file}'"

						# Open the attachment file and execute the mail command using subprocess
						with open(attachment_file, "rb") as f:
							p = subprocess.Popen(mail_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
							stdout, stderr = p.communicate(f.read())
							Mail_Exit_Code = p.returncode	

					else:

						subject_and_body = "There was an error running Syncoid-Iterate.py - this was a Syncoid error - Note Logging disabled"

						mail_command = f"echo '{subject_and_body}' | mail -s '{subject_and_body}' {recipient}"
						p = subprocess.Popen(mail_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
						stdout, stderr = p.communicate()
						Mail_Exit_Code = p.returncode			

					sys.exit(SynCoidFail)

				else:

					logger.error('')
					logger.error('----------')
					logger.error('')
					logger.error('This was a another type of error')
					logger.error('')
					logger.error('The exit code from SynCoid-Iterate-py was was : %i', Exit_Code)
					logger.error('')
					if not LogDestination == "No":
						logger.error('Plz read in the logs what might have gone wrong')
						logger.error('')
						logger.error('----------')
					else:
						logger.error('Logs Disabled, consider enabling')
						logger.error('')
						logger.error('----------')
					
					if not LogDestination == "No":

						subject = "There was an error running Syncoid-Iterate.py run - this was an unknown error - Attaching error logs to confirm"
						attachment_file = LogDestination + "SynCoidIterate-" + time_now + ".err"
						attachment_files = [f"{LogDestinationNoSlash}/SynCoidIterate-{time_now}.{ext}" for ext in ["log", "err", "out"]]

						# Build the mail command with attachments
						attachment_args = " ".join([f"--attach '{file}'" for file in attachment_files])
						mail_command = f"mail -s '{subject}' {recipient} {attachment_args} < '{attachment_file}'"
						
						# Open the attachment file and execute the mail command using subprocess
						with open(attachment_file, "rb") as f:
							p = subprocess.Popen(mail_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
							stdout, stderr = p.communicate(f.read())
							Mail_Exit_Code = p.returncode	

					else:

						subject_and_body = "There was an error running Syncoid-Iterate.py run - this was an unknown error - Note Logging disabled"

						mail_command = f"echo '{subject_and_body}' | mail -s '{subject_and_body}' {recipient}"
						p = subprocess.Popen(mail_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
						stdout, stderr = p.communicate()
						Mail_Exit_Code = p.returncode		
						
					sys.exit(Exit_Code)

		# Print any error messages
		if Mail_Exit_Code == 0:
			WasMailSent(0, "")
		else:
			WasMailSent(Mail_Exit_Code, p.returncode,stderr.decode())

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
	if not SystemOption == "No":
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
		logger.info('Then execute the command')
		logger.info('')
		logger.info('----------')

		# Sleep before executing the desired action
		time.sleep(120)

		os.system(SystemOption)
	else:
		logger.info('')
		logger.info('----------')
		logger.info('')
		logger.info('The system was not choosen to shutdown or similar when the script finished')
		logger.info('')
		logger.info('----------')

	
# In case something is wrong with the List's
# number of items or end names in order
def missmatchinglists(Lenght, Names):
   
	if Lenght == True:
		logger.error('')
		logger.error('----------')
		logger.error('The number of items in each list does not match')
		logger.error('Check the terminal or .err log')
		logger.error('exiting - error code 1')
	if Names == True:
		logger.error('')
		logger.error('----------')
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
MailOption = (config.get('SynCoid Config', 'Mail'))

SystemOption = (config.get('SynCoid Config', 'SystemAction'))

# This is for creating the Date format for the Log Files
DateTime = config.get('SynCoid Config', 'DateTime')
time_now  = datetime.datetime.now().strftime(DateTime)

# This is for the logfile creation
LogDestination=config.get('SynCoid Config', 'LogDestination')

# This is to enable or disable Loggin
if not LogDestination == "No":
	if not LogDestination.endswith('/'):
		LogDestination = LogDestination + "/"

# This logger function will log everything including errors to ".log" and only errors to ".err"
# It is called with logger.(info/error)
def get_logger(    
		LOG_FORMAT     = '%(asctime)s %(levelname)s: %(message)s',
		LOG_NAME       = '',
		LOG_FILE_INFO  = LogDestination + "SynCoidIterate-" + time_now + ".log",
		LOG_FILE_WARNING = LogDestination + "SynCoidIterate-" + time_now + ".err",
		LOG_FILE_ERROR = LogDestination + "SynCoidIterate-" + time_now + ".err",
    	enable_file_logging=True):

	log           = logging.getLogger(LOG_NAME)
	log_formatter = logging.Formatter(LOG_FORMAT)

	if enable_file_logging:
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

if not LogDestination == "No":
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
		text = '{} {}'.format(option, config.get(section,option))
		if text.startswith("password") == False:
			logging.info(text)
			logging.info('')

# Check if the "syncoid command" is in use
if config.get('SynCoid Config','SyncoidCommand').startswith("syncoid") == True:
	logger.info('')
	logger.info('The syncoid command is in use')
	logger.info('')
	logger.info('----------')
	logger.info('')

# Import the Source file to a Python3 list
SourceListImport = open(config.get('SynCoid Config', 'SourceListPath'), "r")
SourceLines = SourceListImport.read().splitlines()
logger.info('Items in the Source list    :   %s', SourceLines)
logger.info('Number of items in the Source list    :   %i', (len(SourceLines)))
SourceListImport.close()
print('')
logger.info('')

# Import the Destination file to a Python3 list
DestListImport = open(config.get('SynCoid Config', 'DestListPath'), "r")
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
PassWordOption=(config.get('SynCoid Config', 'PassWord'))

if PassWordOption == 'Ask':
	PassWord = getpass('PLz. insert a desiret password if needed :    ')
	logger.info('')
	logger.info('----------')
	logger.info('')
	logger.info('The Password has been manualy added')
	logger.info('')
	print('')
	print('This is the Password you have given  :   ', PassWord)
	print('')
elif PassWordOption == 'No':
	logger.info('')
	logger.info('----------')
	logger.info('')
	logger.info('No password is in use')
	logger.info('')
else:
	PassWord=PassWordOption
	logger.info('')
	logger.info('----------')
	logger.info('')
	logger.info('Password is in the config file, not written to log')
	logger.info('')
	print('')
	print('This is the password in the config file  :   ', PassWord)
	print('')

# Get the Syncoid command to be altered
SyncoidCommand=config.get('SynCoid Config', 'SyncoidCommand')

# This is in case the thee pexpect/syncoid command fails
# I am not sure it will catch all errors
def die(child, errstr, error_code):
	logger.error('')
	logger.error(errstr)
	logger.error('')
	logger.error(child.before)
	logger.error('')
	logger.error('This is the warning/error   :   ' + child.after + child.buffer)
	logger.error('')
	logger.error('This is the exit code : ' + error_code)
	logger.error('')
	child.terminate()
	# I had problems that the exit code given to "die" function was "str", i couldten send "int" to "die" function instead but i could conver "str" to "int"
	# This was understood from https://medium.com/@anupkumarray/working-with-exit-codes-between-python-shell-scripts-177931204291
	integer_number = int(error_code)
	MailTo(integer_number, "")
	sys.exit(integer_number)

# This is the function that executes the altered syncoid command
# It allso have a little error checking.
# But i am in doubt it will catch all errors

ISREPEATED = False
CONTINUENODESTROYSNAP = False

def ssh_command(SynCoid_Command):

	global ISREPEATED
	global CONTINUENODESTROYSNAP

	CONTINUENODESTROYSNAP = False

	# spawn the child process
	logger.info('')
	logger.info('----------')
	logger.info('')
	child = pexpect.spawn(SynCoid_Command, timeout=None, encoding='utf-8')

	if not LogDestination == "No":
		fout = open(LogDestination + 'SynCoidIterate-' + time_now + ".out",'a')
		child.logfile = fout

	# set a counter for the number of times a pattern has been executed
	#pattern_count = {}
	#pattern_count.clear()

	# set up a list of patterns to match
	# The easiest way to force a Syncoid Error is to remove "Connection timed out" and give a wrong password
	patterns = [
	    'Are you sure you want to continue connecting',
	    'could not find any snapshots to destroy; check snapshot names.',
	    'Permission denied',
	    'Connection timed out',
	    'Connection refused',
	    'passphrase',
		pexpect.EOF,
		'dataset no longer exists',
		'WARN',
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
			logger.info('Syncoid wanted to delete a syncoid created snapshot on Source that is no longer available')
			logger.info('')
			logger.info('Going the continue the script,')
			logger.info('since this a normal error when having multiple host/server sharing the same datasets')
			logger.info('')
			logger.info('----------')
			logger.info('')
			CONTINUENODESTROYSNAP = True
			return child
		elif index == 2:
			# respond to 'Permission denied'
			die(child, 'ERROR!  Incorrect password. Here is what SSH said:', "5")
		elif index == 3:
			# respond to 'Connection timed out'
			die(child, 'ERROR!  Connection Timeout. Here is what SSH said:', "6")
		elif index == 4:
			# respond to 'Connection refused'
			die(child, 'ERROR!  Connection refused. Here is what SSH said:', "7")
		elif index == 5:
			# respond to 'passphrase'
			if not LogDestination == "No":
				child.logfile = None
			child.sendline (PassWord)
			if not LogDestination == "No":
				child.logfile = fout
		elif index == 6:
			# respond to pexpect.EOF
			# print(child.before)
			return child
		elif index == 7:
			# respond to 'dataset does not exist'
			die(child, 'Destination dataset does not exist - Plz recheck the Source and dest list to be sure:', "8")
		elif index == 8:
			# respond to 'WARN'
			die(child, 'ERROR!  There Was a Warning. Here is what SSH said:', "4")

	return child

# This is the main() part of the script
# It is called after everything else have been imported/prepared
def main():
	global ISREPEATED
	global CONTINUENODESTROYSNAP

	for (h, i) in zip(SourceLines, DestLines):

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
			logger.error('This is the SynCoid Exit status   :   %i', child.exitstatus)
			logger.error('This is the SynCoid signal Status    :   %s', child.signalstatus)
			logger.error('')
			MailTo("", child.exitstatus)

	logger.info('')
	logger.info('----------')
	logger.info('')
	logger.info('The Script ended succesfully')
	logger.info('')
	logger.info('If there is an option for it, it will send a succesfull completed mail')
	logger.info('')
	logger.info('----------')
	logger.info('')
	
	if not LogDestination == "No":
		with open(LogDestination + 'SynCoidIterate-' + time_now + ".out", 'a') as fout:
			lines_of_text = [
				"",
				"----------",
				"",
				"The Script ended succesfully",
				"",
				"If there is an option for it, it will send a succesfull completed mail",
				"",
				"----------",
				"",
				# Add more lines as needed
			]

			for line in lines_of_text:
				fout.write(line + "\n")
	
	# Send succesfull mail
	MailTo(0,"")

	# Decide if there is a shutdown action for the system on succesfull comletion
	SystemAction()

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