#!/usr/bin/python3

# Import argument parser for python arguments
import argparse
from asyncio.log import logger

# Import variables from a .conf file
import configparser
from distutils.log import error, info

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
import os

#  if there is an unexpected error in the program, traceback.print_exc() will work
import traceback

# This is needed for the pexpext loop
import time

# This is for the send mail function
# In case one needs to be notified of errors
def MailTo(Exit_Code, SynCoidFail):
	if not MailOption == 'No':
		logger.info('')
		logger.info('Mail option is on')

		# check if size of file is 0
		if os.stat(LogDestination + "SynCoidIterate-" + time_now + ".err").st_size == 0:
			logger.info('')
			logger.info('Error log is empty')
		else:
			logger.error('')
			logger.error('Error log is not empty')
			logger.error('Attempting to send mail')
			logger.error('')
			if not SynCoidFail == "":
				logger.error('This was a Syncoid crash/fail')
				logger.error('')
				logger.error('The exit code from Syncoid was : %i', SynCoidFail)
				logger.error('')
				logger.error('Plz read in the logs what might have gone wrong')
				logger.error('')
				sys.exit(SynCoidFail)
			else:
				sys.exit(Exit_Code)
			#mail -s 'ERROR using syncoid in some way' "${mail}" < "$LogDestination""${error}"


# In case something is wrong with the List's
# number of items or end names in order
def missmatchinglists(Lenght, Names):
   
	if Lenght == True:
		logger.error('The number of items in each list does not match')
		logger.error('Check the terminal or .err log')
		logger.error('exiting - error code 1')
	if Names == True:
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
MailOption=(config.get('SynCoid Config', 'Mail'))

# This is for creating the Date format for the Log Files
DateTime = config.get('SynCoid Config', 'DateTime')
time_now  = datetime.datetime.now().strftime(DateTime)

# This is for the logfile creation
LogDestination=config.get('SynCoid Config', 'LogDestination')
#logging.basicConfig(filename=LogDestination + "SynCoidIterate-" + time_now + ".log", format="%(asctime)s %(levelname)s: %(message)s", filemode="a", encoding='utf-8', level=logging.DEBUG)

# This logger function will log everything including errors to ".log" and only errors to ".err"
# It is called with logger.(info/error)
def get_logger(    
		LOG_FORMAT     = '%(asctime)s %(levelname)s: %(message)s',
		LOG_NAME       = '',
		LOG_FILE_INFO  = LogDestination + "SynCoidIterate-" + time_now + ".log",
		LOG_FILE_WARNING = LogDestination + "SynCoidIterate-" + time_now + ".err",
		LOG_FILE_ERROR = LogDestination + "SynCoidIterate-" + time_now + ".err"):

	log           = logging.getLogger(LOG_NAME)
	log_formatter = logging.Formatter(LOG_FORMAT)

	# comment this to suppress console output
	stream_handler = logging.StreamHandler()
	stream_handler.setFormatter(log_formatter)
	log.addHandler(stream_handler)

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

	log.setLevel(logging.INFO)

	return log

logger = get_logger()

# Print the config file destination from the scripts argument
logger.info('Config file destination  :   %s', args.conf)
logger.info('')

# Write Date format to screen
logger.info("The Date used for Log Files  :   %s", time_now)
logger.info('')

# Examples of using the logger function
#  
#logger.info('This is an INFO message')
#logger.warning('This is a WARNING message')
#logger.error('This is an ERROR message')

# Save the importet variables to .log file
for section in config.sections():
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

logger.info('----------')

# Check if the "syncoid command" is in use
if config.get('SynCoid Config','SyncoidCommand').startswith("syncoid") == True:
	logger.info('The syncoid command is in use')
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
	logger.info('The Password has been manualy added')
	logger.info('')
	print('')
	print('This is the Password you have given  :   ', PassWord)
	print('')
elif PassWordOption == 'No':
	logger.info('')
	logger.info('No password is in use')
	logger.info('')
	print('')
	print('no password in use')
	print('')
else:
	PassWord=PassWordOption
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
	#logger.error('{0}'.format(child.before) + '{0}'.format(child.after))
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
	MailTo(integer_number,"")
	sys.exit(integer_number)

# This is the function that executes the altered syncoid command
# It allso have a little error checking.
# But i am in doubt it will catch all errors

ISREPEATED = False

def ssh_command(SynCoid_Command):

	global ISREPEATED

	logger.info('----')

	# spawn the child process
	child = pexpect.spawn(SynCoid_Command, timeout=None, encoding='utf-8')

	fout = open(LogDestination + 'SynCoidIterate-' + time_now + ".out",'a')
	child.logfile = fout

	# set a counter for the number of times a pattern has been executed
	pattern_count = {}
	pattern_count.clear()

	# set a maximum limit for the number of times a pattern can be executed
	max_pattern_executions = 3

	# set up a list of patterns to match
	patterns = [
	    'Are you sure you want to continue connecting',
	    'WARN',
	    'Permission denied',
	    'Connection timed out',
	    'Connection refused',
	    'passphrase',
		pexpect.EOF,
		'dataset does not exist',
	]

	while True:
		index = child.expect(patterns)

		# increment the pattern count for the matched pattern
		pattern_count[index] = pattern_count.get(index, 0) + 1

		# check if the pattern has been executed more than the maximum allowed number of times
		if pattern_count.get(index, 0) > max_pattern_executions:
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
			# respond to 'WARN'
			die(child, 'ERROR!  There Was a Warning. Here is what SSH said:', "4")
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
			child.sendline (PassWord)
		elif index == 6:
			# respond to pexpect.EOF
			print(child.before)
			return child
		elif index == 7:
			# respond to 'dataset does not exist'
			die(child, 'Destination dataset does not exist - Plz recheck the Source and dest list to be sure:', "8")

	return child

# This is the main() part of the script
# It is called after everything else have been imported/prepared
def main():
	global ISREPEATED

	for (h, i) in zip(SourceLines, DestLines):

		SyncoidExecute=SyncoidCommand.replace("SourceDataSet", h)
		SyncoidExecute=SyncoidExecute.replace("DestDataSet", i)

		logger.info('Ececuting the altered SynCoid Command    :   %s', SyncoidExecute)
		
		child = ssh_command(SyncoidExecute)
		
		child.close()

		if ISREPEATED == True:
			die(child, 'ERROR: The script is repeating itself', "9")

		if not child.exitstatus == 0:
			logger.error('')
			logger.error('This is the SynCoid Exit status   :   %i', child.exitstatus)
			logger.error('This is the SynCoid signal Status    :   %s', child.signalstatus)
			logger.error('')
			logger.error('----')
			logger.error('')
			MailTo(child.exitstatus, child.exitstatus)

	logger.info('')
	logger.info('----')
	logger.info('')
	logger.info('The Script ended succesfully')
	logger.info('')
	logger.info('If there is an option for it, it will send a succesfull complete message')
	logger.info('')
	logger.info('----')
	logger.info('')

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

#MailTo(100)