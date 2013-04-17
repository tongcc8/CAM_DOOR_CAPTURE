from SimpleCV import Camera, Display
import RPi.GPIO as GPIO
from time import sleep, time
from threading import Thread, Event
import sys
import datetime
import os

#constants area
threshold = 5.0		#threshold to determine if a motion is detected
scan_period = 0.5	#camera scanning period for motion detection (in sec)
photo_period = 0.2	#photo-taking period when detected (in sec)
photo_quantity = 5	#number of photos taken
passcode = "2813"	#pass code for valid access
pass_timeout = 60	#time limit for entering pass code
reactive_timeout = 60 # waiting time for reactivating the system 
pin_do = 11			#pinout for door open alert
pin_ua1 = 9  		#pinout for unauthorized entry alert
pin_ua2 = 22
pin_rsbtn = 10      #pinout for alarm reset button
col = (25, 7, 23)    #pinouts for keypad
row = (8, 15, 18, 24)
desire_path = "/srv/ftp/"	#the path where photos will be stored
pass_valid = False
al_on = False
sys_start = False
#keypad lookup table
keypad_lookup = {
    '011111111111': '1',
    '101111111111': '4',
    '110111111111': '7',
    '111011111111': '*',
    '111101111111': '2',
    '111110111111': '5',
    '111111011111': '8',
    '111111101111': '0',
    '111111110111': '3',
    '111111111011': '6',
    '111111111101': '9',
    '111111111110': '#',
    '111111111111': 'n' #representing no input
    }

#functions area
def NewExceptHook(type, value, traceback):  #Adding GPIO cleanup for force closing
    if type == KeyboardInterrupt:
        GPIO.cleanup()
        exit("\nExiting.")
    else:
        OriginalExceptHook(type, value, traceback)

def init_key(r, c): #function for initializing keypad layouts
    #setting rows be input
    for i in range(len(r)):
        GPIO.setup(r[i], GPIO.IN, pull_up_down = GPIO.PUD_UP)

    #setting columns be output
    for j in range(len(c)):
        GPIO.setup(c[j], GPIO.OUT)
        GPIO.output(c[j], GPIO.HIGH)

def rec_key(r, c, lkup):    #function for recording keypad input
    bitcode = ""
    for a in range(len(c)):
        GPIO.output(c[a], GPIO.LOW)
        sleep(0.01)
        for b in range(len(r)):
            if GPIO.input(r[b]):
                bitcode += '1'
            else:
                bitcode += '0'
        GPIO.output(c[a], GPIO.HIGH)
    return lkup.get(bitcode)

def ensure_dir(f):	#function for ensuring there is folder ready for storing photos
    d = os.path.dirname(os.path.join(f))
    if not os.path.exists(d):
		os.makedirs(d)

def pass_input(in_stop):	#function for pass code verification
    global pass_valid
    global al_on
    in_pass = ''
    keypre = 'n'
    while not (pass_valid or in_stop.is_set()):
        print("Please enter the pass code: ")
        key_finish = False
        passl = []
        while not (key_finish or in_stop.is_set()):
            keyout = rec_key(r = row, c = col, lkup = keypad_lookup)
            if (keyout != None) and (keyout != 'n') and (keyout != keypre):
                t_beep = Thread(target = beep)
                t_beep.daemon = True
                t_beep.start()
                if keyout == '#':
                    print("")
                    in_pass = ''.join(passl)
                    passl = []
                    key_finish = True
                else:
                    #showing keypad input like typing on keyboard in terminal
                    sys.stdout.write(keyout)
                    sys.stdout.flush()
                    
                    passl.append(keyout)
            keypre = keyout
            in_stop.wait(0.05)  #same as sleep(), but can also listen to killing signal
        key_finish = False
        if in_pass == passcode:
            pass_valid = True
            in_stop.set()
        else:
		    print("Pass code incorrect")
		    in_pass = ''

def pass_veri():    #function for killing pass_input when condition is matched, and manage the result
    global pass_valid
    global al_on
    pass_valid = False
    t_input_stop = Event()
    t_input = Thread(target = pass_input, args = (t_input_stop,))
    t_input.daemon = True					#enable killing raw_input
    t_input.start()
    t_input_stop.wait(pass_timeout)
    if not t_input_stop.is_set():
        t_input_stop.set()
    GPIO.output(pin_do, GPIO.LOW)
    
    if pass_valid:
        print("Valid. System paused.")
        t_input_stop.clear()
        pass_valid = False
        cont = False
        t_beep = Thread(target = beep)
        t_beep.daemon = True
        t_beep.start()
        keypre = 'n'
        print("When leave, press * twice to re-activate the system...")
        keyq = list("nn")
        timec = datetime.datetime.now()
        while not cont:
            keyout = rec_key(r = row, c = col, lkup = keypad_lookup)
            if (keyout != None) and (keyout != 'n') and (keyout != keypre):
                t_beep = Thread(target = beep)
                t_beep.daemon = True
                t_beep.start()
                timep = timec
                timec = datetime.datetime.now()
                td = timec - timep
                tds = float(td.seconds) + float(td.microseconds) / float(1000000)
                #print(tds)
                keyq[0] = keyq[1]
                keyq[1] = keyout
                if ((''.join(keyq) == "**") and (tds < 0.8)):
                    cont = True
                    keyq = list("nn")
                    print("1 minute before system reset...")
                    sleep(reactive_timeout)    #wait staff to retreat
            keypre = keyout
            sleep(0.05)
        
    else:
        print("Warning: unauthorized entry")
        GPIO.output(pin_ua1, GPIO.HIGH)
        #GPIO.output(pin_ua2, GPIO.HIGH)
        al_on = True
        sleep(5)

def init_alert():   #function for initilizing the pins for alarm
    GPIO.setup(pin_do, GPIO.OUT)
    GPIO.setup(pin_ua1, GPIO.OUT)
    GPIO.setup(pin_ua2, GPIO.OUT)
    
    GPIO.output(pin_do, GPIO.LOW)	
    GPIO.output(pin_ua1, GPIO.LOW)
    GPIO.output(pin_ua2, GPIO.LOW)
    
    GPIO.setup(pin_rsbtn, GPIO.IN, pull_up_down = GPIO.PUD_DOWN)
    
def button_reset(): #function to reset the alarms
    while True:
        if GPIO.input(pin_rsbtn):
            GPIO.output(pin_do, GPIO.LOW)
            GPIO.output(pin_ua1, GPIO.LOW)
            #GPIO.output(pin_ua2, GPIO.LOW)
            al_on = False
        sleep(0.05)

def beep(): #generating a beep sound
    GPIO.output(pin_ua2,GPIO.HIGH)
    sleep(0.05)
    GPIO.output(pin_ua2,GPIO.LOW)

#main thread
OriginalExceptHook = sys.excepthook
sys.excepthook = NewExceptHook
init_time = time()
ensure_dir(desire_path)
GPIO.setmode(GPIO.BCM)
init_alert()
t_reset = Thread(target = button_reset)
t_reset.daemon = True
t_reset.start()
keyout = 'n'
keypre = 'n'
init_key(r = row, c = col)
cam = Camera(camera_index = 0, prop_set={'width': 320, 'height': 240}, threaded = False)	#camera config


print("Press * twice to activate the system...")
keyq = list("nn")
timec = datetime.datetime.now()
while not sys_start:
    keyout = rec_key(r = row, c = col, lkup = keypad_lookup)
    if (keyout != None) and (keyout != 'n') and (keyout != keypre):
        t_beep = Thread(target = beep)
        t_beep.daemon = True
        t_beep.start()
        timep = timec
        timec = datetime.datetime.now()
        td = timec - timep
        tds = float(td.seconds) + float(td.microseconds) / float(1000000)
        #print(tds)
        keyq[0] = keyq[1]
        keyq[1] = keyout
        if ((''.join(keyq) == "**") and (tds < 0.8)):
            sys_start = True
            keyq = list("nn")
            print("1 minute before system start...")
            sleep(reactive_timeout)    #wait staff to retreat
    keypre = keyout
    sleep(0.05)

print("System started.")
current = cam.getImage()

while True:
    sleep(scan_period)
    previous = current			#image queueing
    current = cam.getImage()
    diff = current - previous
    matrix = diff.getNumpy()
    mean =matrix.mean()
    #print(mean)
	
    if mean >= threshold and (time() - init_time) > 5 :		#ignore first 5 secs, when the camera is not stable
        now = datetime.datetime.now()	#get the detection time
        logtime = now.strftime("%Y%b%d%H%M%S")
        print("Door opened")
        GPIO.output(pin_do, GPIO.HIGH)
        #print("Motion detected at " + logtime)
        for i in range(5):	#take 5photos for each detecton
            current.save(desire_path + logtime + "_" + str(i) + ".jpg")
            current = cam.getImage()
            #current.show()
            sleep(photo_period)
        pass_veri()


        print("System reset")
        current = cam.getImage()		#refreshing image for motion detection
        
        
    else:
            #current.show()
            pass
		
