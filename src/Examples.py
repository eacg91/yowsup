#Este codigo incluye:
#
#	WhatsappCmdClient 	from	CmdClient.py
#	WhatsappEchoClient	from	EchoClient.py
#	WhatsappListenerClient	from	ListenerClient.py
#	WhatsappGroupListenerClient from GroupListenerClient.py
#	UploaderClient		from	UploaderClient
#

from Yowsup.connectionmanager import YowsupConnectionManager
import time, datetime, sys, os, shutil, threading, hashlib, base64
parentdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.sys.path.insert(0,parentdir)
from Yowsup.Media.downloader import MediaDownloader
from Yowsup.Media.uploader import MediaUploader
from sys import stdout

if sys.version_info >= (3, 0):
	raw_input = input

class WhatsappCmdClient:
	
	def __init__(self, phoneNumber, keepAlive = False, sendReceipts = False):
		self.sendReceipts = sendReceipts
		self.phoneNumber = phoneNumber
		self.jid = "%s@s.whatsapp.net" % phoneNumber
		
		self.sentCache = {}
		
		connectionManager = YowsupConnectionManager()
		connectionManager.setAutoPong(keepAlive)
		self.signalsInterface = connectionManager.getSignalsInterface()
		self.methodsInterface = connectionManager.getMethodsInterface()
		
		self.signalsInterface.registerListener("auth_success", self.onAuthSuccess)
		self.signalsInterface.registerListener("auth_fail", self.onAuthFailed)
		self.signalsInterface.registerListener("message_received", self.onMessageReceived)
		self.signalsInterface.registerListener("receipt_messageSent", self.onMessageSent)
		self.signalsInterface.registerListener("presence_updated", self.onPresenceUpdated)
		self.signalsInterface.registerListener("disconnected", self.onDisconnected)

		self.signalsInterface.registerListener("media_uploadRequestSuccess", self.onmedia_uploadRequestSuccess)
		self.signalsInterface.registerListener("media_uploadRequestFailed", self.onmedia_uploadRequestFailed)
		self.signalsInterface.registerListener("media_uploadRequestDuplicate", self.onmedia_uploadRequestDuplicate)
		self.path = ""
		self.gotMediaReceipt = False
		self.done = False
		
		
		self.commandMappings = {"lastseen":lambda: self.methodsInterface.call("presence_request", ( self.jid,)),
								"available": lambda: self.methodsInterface.call("presence_sendAvailable"),
								"unavailable": lambda: self.methodsInterface.call("presence_sendUnavailable")
								 }
		
		self.done = False
		#signalsInterface.registerListener("receipt_messageDelivered", lambda jid, messageId: methodsInterface.call("delivered_ack", (jid, messageId)))
	
	def login(self, username, password):
		self.username = username
		self.methodsInterface.call("auth_login", (username, password))

		while not self.done:
			time.sleep(0.5)

	def onAuthSuccess(self, username):
		print("Authed %s" % username)
		self.methodsInterface.call("ready")
		self.goInteractive(self.phoneNumber)

	def onAuthFailed(self, username, err):
		print("Auth Failed!")

	def onDisconnected(self, reason):
		print("Disconnected because %s" %reason)
		
	def onPresenceUpdated(self, jid, lastSeen):
		formattedDate = datetime.datetime.fromtimestamp(long(time.time()) - lastSeen).strftime('%d-%m-%Y %H:%M')
		self.onMessageReceived(0, jid, "LAST SEEN RESULT: %s"%formattedDate, long(time.time()), False, None, False)

	def onMessageSent(self, jid, messageId):
		formattedDate = datetime.datetime.fromtimestamp(self.sentCache[messageId][0]).strftime('%d-%m-%Y %H:%M')
		print("%s [%s]:%s"%(self.username, formattedDate, self.sentCache[messageId][1]))
		print(self.getPrompt())

	def runCommand(self, command):		
		splitstr = command.split(' ')
		if splitstr[0] == "/pic" and len(splitstr) == 2:
			self.path = splitstr[1]

			if not os.path.isfile(splitstr[1]):
				print("File %s does not exists" % splitstr[1])
				return 1


			statinfo = os.stat(self.path)
			name=os.path.basename(self.path)
			print("Sending picture %s of size %s with name %s" %(self.path, statinfo.st_size, name))
			mtype = "image"

			sha1 = hashlib.sha256()
			fp = open(self.path, 'rb')
			try:
				sha1.update(fp.read())
				hsh = base64.b64encode(sha1.digest())
				print("Sending media_requestUpload")
				self.methodsInterface.call("media_requestUpload", (hsh, mtype, os.path.getsize(self.path)))
			finally:
				fp.close()

			timeout = 100
			t = 0;
			while t < timeout and not self.gotMediaReceipt:
				time.sleep(0.5)
				t+=1

			if not self.gotMediaReceipt:
				print("MediaReceipt print timedout!")
			else:
				print("Got request MediaReceipt")

			return 1
		elif command[0] == "/":
			command = command[1:].split(' ')
			try:
				self.commandMappings[command[0]]()
				return 1
			except KeyError:
				return 0
		
		return 0
			
	def onMessageReceived(self, messageId, jid, messageContent, timestamp, wantsReceipt, pushName, isBroadcast):
		if jid[:jid.index('@')] != self.phoneNumber:
			return
		formattedDate = datetime.datetime.fromtimestamp(timestamp).strftime('%d-%m-%Y %H:%M')
		print("%s [%s]:%s"%(jid, formattedDate, messageContent))
		
		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))

		print(self.getPrompt())
	
	def goInteractive(self, jid):
		print("Starting Interactive chat with %s" % jid)
		jid = "%s@s.whatsapp.net" % jid
		print(self.getPrompt())
		while True:
			message = raw_input()
			message = message.strip()
			if not len(message):
				continue
			if not self.runCommand(message.strip()):
				msgId = self.methodsInterface.call("message_send", (jid, message))
				self.sentCache[msgId] = [int(time.time()), message]
		self.done = True
	def getPrompt(self):
		return "Enter Message or command: (/%s)" % ", /".join(self.commandMappings)

	def onImageReceived(self, messageId, jid, preview, url, size, wantsReceipt, isBroadcast):
		print("Image received: Id:%s Jid:%s Url:%s size:%s" %(messageId, jid, url, size))
		downloader = MediaDownloader(self.onDlsuccess, self.onDlerror, self.onDlprogress)
		downloader.download(url)
		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))

		timeout = 10
		t = 0;
		while t < timeout:
			time.sleep(0.5)
			t+=1

	def onDlsuccess(self, path):
		stdout.write("\n")
		stdout.flush()
		print("Image downloded to %s"%path)
		print(self.getPrompt())

	def onDlerror(self):
		stdout.write("\n")
		stdout.flush()
		print("Download Error")
		print(self.getPrompt())

	def onDlprogress(self, progress):
		stdout.write("\r Progress: %s" % progress)
		stdout.flush()

	def onmedia_uploadRequestSuccess(self,_hash, url, resumeFrom):
		print("Request Succ: hash: %s url: %s resume: %s"%(_hash, url, resumeFrom))
		self.uploadImage(url)
		self.gotMediaReceipt = True

	def onmedia_uploadRequestFailed(self,_hash):
		print("Request Fail: hash: %s"%(_hash))
		self.gotReceipt = True

	def onmedia_uploadRequestDuplicate(self,_hash, url):
			print("Request Dublicate: hash: %s url: %s "%(_hash, url))
			self.doSendImage(url)
			self.gotMediaReceipt = True

	def uploadImage(self, url):
		uploader = MediaUploader(self.jid, self.username, self.onUploadSuccess, self.onError, self.onProgressUpdated)
		uploader.upload(self.path,url)

	def onUploadSuccess(self, url):
		stdout.write("\n")
		stdout.flush()
		print("Upload Succ: url: %s "%( url))
		self.doSendImage(url)

	def onError(self):
		stdout.write("\n")
		stdout.flush()
		print("Upload Fail:")

	def onProgressUpdated(self, progress):
		stdout.write("\r Progress: %s" % progress)
		stdout.flush()

	def doSendImage(self, url):
		  print("Sending message_image")
		  statinfo = os.stat(self.path)
		  name=os.path.basename(self.path)
		  msgId = self.methodsInterface.call("message_imageSend", (self.jid, url, name,str(statinfo.st_size), "yes"))
		  self.sentCache[msgId] = [int(time.time()), self.path]

class Events(object):
    def getEventBindings(self):
        bindings = {}
        for methodname in dir(self):
            method = getattr(self, methodname)
            if hasattr(method, '_events'):
                bindings[method] = method._events
        return bindings

    @staticmethod
    def bind(event):
        def wrapper(func):
            if not hasattr(func, '_events'):
                func._events = []
            func._events.append(event)
            return func
        return wrapper

class WhatsappEchoClient:
	
	def __init__(self, target, message, waitForReceipt=False):
		
		self.jids = []
		
		if '-' in target:
			self.jids = ["%s@g.us" % target]
		else:
			self.jids = ["%s@s.whatsapp.net" % t for t in target.split(',')]

		self.message = message
		self.waitForReceipt = waitForReceipt
		
		connectionManager = YowsupConnectionManager()
		self.signalsInterface = connectionManager.getSignalsInterface()
		self.methodsInterface = connectionManager.getMethodsInterface()
		
		self.signalsInterface.registerListener("auth_success", self.onAuthSuccess)
		self.signalsInterface.registerListener("auth_fail", self.onAuthFailed)
		if waitForReceipt:
			self.signalsInterface.registerListener("receipt_messageSent", self.onMessageSent)
			self.gotReceipt = False
		self.signalsInterface.registerListener("disconnected", self.onDisconnected)

		self.done = False
	
	def login(self, username, password):
		self.username = username
		self.methodsInterface.call("auth_login", (username, password))

		while not self.done:
			time.sleep(0.5)

	def onAuthSuccess(self, username):
		print("Authed %s" % username)

		if self.waitForReceipt:
			self.methodsInterface.call("ready")
		
		
		if len(self.jids) > 1:
			self.methodsInterface.call("message_broadcast", (self.jids, self.message))
		else:
			self.methodsInterface.call("message_send", (self.jids[0], self.message))
		print("Sent message")
		if self.waitForReceipt:
			timeout = 5
			t = 0;
			while t < timeout and not self.gotReceipt:
				time.sleep(0.5)
				t+=1

			if not self.gotReceipt:
				print("print timedout!")
			else:
				print("Got sent receipt")

		self.done = True

	def onAuthFailed(self, username, err):
		print("Auth Failed!")

	def onDisconnected(self, reason):
		print("Disconnected because %s" %reason)

	def onMessageSent(self, jid, messageId):
		self.gotReceipt = True

class WhatsappListenerClient:
	
	def __init__(self, keepAlive = False, sendReceipts = False):
		self.sendReceipts = sendReceipts
		
		connectionManager = YowsupConnectionManager()
		connectionManager.setAutoPong(keepAlive)

		self.signalsInterface = connectionManager.getSignalsInterface()
		self.methodsInterface = connectionManager.getMethodsInterface()
		
		self.signalsInterface.registerListener("message_received", self.onMessageReceived)
		self.signalsInterface.registerListener("auth_success", self.onAuthSuccess)
		self.signalsInterface.registerListener("auth_fail", self.onAuthFailed)
		self.signalsInterface.registerListener("disconnected", self.onDisconnected)
		
		self.cm = connectionManager
	
	def login(self, username, password):
		self.username = username
		self.methodsInterface.call("auth_login", (username, password))
		
		
		while True:
			raw_input()	

	def onAuthSuccess(self, username):
		print("Authed %s" % username)
		self.methodsInterface.call("ready")

	def onAuthFailed(self, username, err):
		print("Auth Failed!")

	def onDisconnected(self, reason):
		print("Disconnected because %s" %reason)

	def onMessageReceived(self, messageId, jid, messageContent, timestamp, wantsReceipt, pushName, isBroadCast):
		formattedDate = datetime.datetime.fromtimestamp(timestamp).strftime('%d-%m-%Y %H:%M')
		print("%s [%s]:%s"%(jid, formattedDate, messageContent))

		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))
	
class PictureDownloader(Events):
    def __init__(self, connectionManager, contacts):
        super(PictureDownloader, self).__init__()
        self._pictureRequestsLock = threading.RLock()
        self._pictureRequests = {}
        self.signalsInterface = connectionManager.getSignalsInterface()
        self.methodsInterface = connectionManager.getMethodsInterface()
        for method, events in self.getEventBindings().iteritems():
            for event in events:
                self.signalsInterface.registerListener(event, method)

    def close(self):
        with self._pictureRequestsLock:
            for jid in self._pictureRequests.keys():
                self._removeRequest(jid)

    def _removeRequest(self, jid):
        with self._pictureRequestsLock:
            if jid in self._pictureRequests:
                request = self._pictureRequests[jid]
                if 'timer' in request:
                    try:
                        request['timer'].cancel()
                        request['timer'].join()
                    except:
                        pass
                if 'timeout' in request:
                    try:
                        request['timeout'].cancel()
                        request['timeout'].join()
                    except:
                        pass
                del self._pictureRequests[jid]

    @Events.bind('contact_gotProfilePictureId')
    def onProfilePictureId(self, jid, pictureId):
        Contacts.instance().setContactPictureId(jid, pictureId)
        pictureFilename = Contacts.instance().getContactPicture(jid)
        if not os.path.isfile(pictureFilename):
            #print 'onProfilePictureId(): queuing picture request for %s: %s' % (jid, pictureId)
            self._requestPicture(jid)

    def _requestPicture(self, jid):
        with self._pictureRequestsLock:
            if 'timeout' not in self._pictureRequests.get(jid, {}):
                delay = 0.2 * len(self._pictureRequests)
                #print 'onProfilePictureId(): requesting new picture for "%s" in %4.2fs' % (Contacts.instance().getName(jid), delay)
                request = self._pictureRequests.get(jid, {'numTimeouts': 0})
                request['timer'] = threading.Timer(delay, lambda: self.methodsInterface.call('picture_get', (jid,)))
                request['timeout'] = threading.Timer(delay + 2.0 + 0.5 * request['numTimeouts'], lambda: self._requestPictureTimeout(jid))
                self._pictureRequests[jid] = request
                request['timer'].start()
                request['timeout'].start()

    @Events.bind('contact_gotProfilePicture')
    def onProfilePicture(self, jid, filename):
        self._removeRequest(jid)
        #print 'onProfilePicture(): %s %s' % (jid, filename)
        pictureFilename = Contacts.instance().getContactPicture(jid)
        if pictureFilename is not None:
            #print 'onProfilePicture(): moving pic for "%s" pic to %s' % (Contacts.instance().getName(jid), pictureFilename)
            shutil.move(filename, pictureFilename)
        else:
            print 'onProfilePicture(): received picture for "%s" without requesting it' % (Contacts.instance().getName(jid))

    def _requestPictureTimeout(self, jid):
        with self._pictureRequestsLock:
            if jid in self._pictureRequests:
                numTimeouts = self._pictureRequests[jid]['numTimeouts'] + 1
                if numTimeouts >= 5:
                    print '_requestPictureTimeout(): pic request for "%s" timed out %d times, giving up' % (Contacts.instance().getName(jid), numTimeouts)
                    self._removeRequest(jid)
                    return
                self._pictureRequests[jid]['numTimeouts'] = numTimeouts
                del self._pictureRequests[jid]['timeout']
                # queue picture again
                self._requestPicture(jid)

class UploaderClient:
	def __init__(self, phoneNumber, imagePath, keepAlive = False, sendReceipts = False):
		self.sendReceipts = sendReceipts
		self.phoneNumber = phoneNumber
		self.imagePath = imagePath

		if '-' in phoneNumber:
			self.jid = "%s@g.us" % phoneNumber
		else:
			self.jid = "%s@s.whatsapp.net" % phoneNumber		
		
		self.sentCache = {}
		
		connectionManager = YowsupConnectionManager()
		connectionManager.setAutoPong(keepAlive)
		self.signalsInterface = connectionManager.getSignalsInterface()
		self.methodsInterface = connectionManager.getMethodsInterface()
		
		self.signalsInterface.registerListener("auth_success", self.onAuthSuccess)
		self.signalsInterface.registerListener("auth_fail", self.onAuthFailed)
		self.signalsInterface.registerListener("message_received", self.onMessageReceived)
		self.signalsInterface.registerListener("receipt_messageSent", self.onMessageSent)
		self.signalsInterface.registerListener("presence_updated", self.onPresenceUpdated)
		self.signalsInterface.registerListener("disconnected", self.onDisconnected)

		self.signalsInterface.registerListener("media_uploadRequestSuccess", self.onmedia_uploadRequestSuccess)
		self.signalsInterface.registerListener("media_uploadRequestFailed", self.onmedia_uploadRequestFailed)
		self.signalsInterface.registerListener("media_uploadRequestDuplicate", self.onmedia_uploadRequestDuplicate)
		self.path = ""
		self.gotMediaReceipt = False
		self.done = False
		
		
		self.commandMappings = {"lastseen":lambda: self.methodsInterface.call("presence_request", ( self.jid,)),
								"available": lambda: self.methodsInterface.call("presence_sendAvailable"),
								"unavailable": lambda: self.methodsInterface.call("presence_sendUnavailable")
								 }
		
		self.done = False
		#signalsInterface.registerListener("receipt_messageDelivered", lambda jid, messageId: methodsInterface.call("delivered_ack", (jid, messageId)))
	
	def login(self, username, password):
		self.username = username
		self.methodsInterface.call("auth_login", (username, password))

		while not self.done:
			time.sleep(0.5)

	def onAuthSuccess(self, username):
		print("Authed %s" % username)
		self.methodsInterface.call("ready")
		self.runCommand("/pic "+self.imagePath)

	def onAuthFailed(self, username, err):
		print("Auth Failed!")

	def onDisconnected(self, reason):
		print("Disconnected because %s" %reason)
		
	def onPresenceUpdated(self, jid, lastSeen):
		formattedDate = datetime.datetime.fromtimestamp(long(time.time()) - lastSeen).strftime('%d-%m-%Y %H:%M')
		self.onMessageReceived(0, jid, "LAST SEEN RESULT: %s"%formattedDate, long(time.time()), False, None, False)

	def onMessageSent(self, jid, messageId):
		formattedDate = datetime.datetime.fromtimestamp(self.sentCache[messageId][0]).strftime('%d-%m-%Y %H:%M')
		print("%s [%s]:%s"%(self.username, formattedDate, self.sentCache[messageId][1]))
		print(self.getPrompt())

	def runCommand(self, command):		
		splitstr = command.split(' ')
		if splitstr[0] == "/pic" and len(splitstr) == 2:			
			self.path = splitstr[1]
						
			if not os.path.isfile(splitstr[1]):
				print("File %s does not exists" % splitstr[1])
				return 1


			statinfo = os.stat(self.path)
			name=os.path.basename(self.path)
			print("Sending picture %s of size %s with name %s" %(self.path, statinfo.st_size, name))
			mtype = "image"

			sha1 = hashlib.sha256()
			fp = open(self.path, 'rb')
			try:
				sha1.update(fp.read())
				hsh = base64.b64encode(sha1.digest())
				print("Sending media_requestUpload")
				self.methodsInterface.call("media_requestUpload", (hsh, mtype, os.path.getsize(self.path)))
			finally:
				fp.close()

			timeout = 100
			t = 0;
			while t < timeout and not self.gotMediaReceipt:
				time.sleep(0.5)
				t+=1

			if not self.gotMediaReceipt:
				print("MediaReceipt print timedout!")
			else:
				print("Got request MediaReceipt")

			# added by sirpoot
			self.done = True
			return 1
		elif command[0] == "/":
			command = command[1:].split(' ')
			try:
				self.commandMappings[command[0]]()
				return 1
			except KeyError:
				return 0
		
		return 0
			
	def onMessageReceived(self, messageId, jid, messageContent, timestamp, wantsReceipt, pushName, isBroadcast):
		if jid[:jid.index('@')] != self.phoneNumber:
			return
		formattedDate = datetime.datetime.fromtimestamp(timestamp).strftime('%d-%m-%Y %H:%M')
		print("%s [%s]:%s"%(jid, formattedDate, messageContent))
		
		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))

		print(self.getPrompt())
	
	def goInteractive(self, jid):
		print("Starting Interactive chat with %s" % jid)
		jid = "%s@s.whatsapp.net" % jid
		print(self.getPrompt())
		while True:
			message = raw_input()
			message = message.strip()
			if not len(message):
				continue
			if not self.runCommand(message.strip()):
				msgId = self.methodsInterface.call("message_send", (jid, message))
				self.sentCache[msgId] = [int(time.time()), message]
		self.done = True
	def getPrompt(self):
		return "Enter Message or command: (/%s)" % ", /".join(self.commandMappings)

	def onImageReceived(self, messageId, jid, preview, url, size, wantsReceipt, isBroadcast):
		print("Image received: Id:%s Jid:%s Url:%s size:%s" %(messageId, jid, url, size))
		downloader = MediaDownloader(self.onDlsuccess, self.onDlerror, self.onDlprogress)
		downloader.download(url)
		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))

		timeout = 10
		t = 0;
		while t < timeout:
			time.sleep(0.5)
			t+=1

	def onDlsuccess(self, path):
		stdout.write("\n")
		stdout.flush()
		print("Image downloded to %s"%path)
		print(self.getPrompt())

	def onDlerror(self):
		stdout.write("\n")
		stdout.flush()
		print("Download Error")
		print(self.getPrompt())

	def onDlprogress(self, progress):
		stdout.write("\r Progress: %s" % progress)
		stdout.flush()

	def onmedia_uploadRequestSuccess(self,_hash, url, resumeFrom):
		print("Request Succ: hash: %s url: %s resume: %s"%(_hash, url, resumeFrom))
		self.uploadImage(url)
		self.gotMediaReceipt = True

	def onmedia_uploadRequestFailed(self,_hash):
		print("Request Fail: hash: %s"%(_hash))
		self.gotReceipt = True

	def onmedia_uploadRequestDuplicate(self,_hash, url):
			print("Request Dublicate: hash: %s url: %s "%(_hash, url))
			self.doSendImage(url)
			self.gotMediaReceipt = True

	def uploadImage(self, url):
		uploader = MediaUploader(self.jid, self.username, self.onUploadSuccess, self.onError, self.onProgressUpdated)
		uploader.upload(self.path,url)

	def onUploadSuccess(self, url):
		stdout.write("\n")
		stdout.flush()
		print("Upload Succ: url: %s "%( url))
		self.doSendImage(url)

	def onError(self):
		stdout.write("\n")
		stdout.flush()
		print("Upload Fail:")

	def onProgressUpdated(self, progress):
		stdout.write("\r Progress: %s" % progress)
		stdout.flush()

	def doSendImage(self, url):
		print("Sending message_image")
		statinfo = os.stat(self.path)
		name=os.path.basename(self.path)

		#im = Image.open("c:\\users\\poot\\desktop\\icon.png")
		#im.thumbnail(size, Image.ANTIALIAS)
		
		#msgId = self.methodsInterface.call("message_imageSend", (self.jid, url, name,str(statinfo.st_size), "yes"))
		msgId = self.methodsInterface.call("message_imageSend", (self.jid, url, name,str(statinfo.st_size), self.createThumb()))
		self.sentCache[msgId] = [int(time.time()), self.path]

	
	def createThumb(self):		
		THUMBNAIL_SIZE = 64, 64
		thumbnailFile = "thumb.jpg"

		im = Image.open(self.path)
		im.thumbnail(THUMBNAIL_SIZE, Image.ANTIALIAS)
		im.save(thumbnailFile, "JPEG")

		with open(thumbnailFile, "rb") as imageFile:
			raw = base64.b64encode(imageFile.read())

		return raw;

class WhatsappGroupListenerClient:
	
	def __init__(self, keepAlive = False, sendReceipts = False):
		self.sendReceipts = sendReceipts
		
		connectionManager = YowsupConnectionManager()
		connectionManager.setAutoPong(keepAlive)

		self.signalsInterface = connectionManager.getSignalsInterface()
		self.methodsInterface = connectionManager.getMethodsInterface()
		
		self.signalsInterface.registerListener("message_received", self.onMessageReceived)
		self.signalsInterface.registerListener("auth_success", self.onAuthSuccess)
		self.signalsInterface.registerListener("auth_fail", self.onAuthFailed)
		self.signalsInterface.registerListener("disconnected", self.onDisconnected)
		self.signalsInterface.registerListener("group_messageReceived", self.waOnGroupMessageReceived)
		
		self.cm = connectionManager
	
	def login(self, username, password):
		self.username = username
		self.methodsInterface.call("auth_login", (username, password))
		
		
		while True:
			raw_input()	

	def onAuthSuccess(self, username):
		print("Authed %s" % username)
		self.methodsInterface.call("ready")

	def onAuthFailed(self, username, err):
		print("Auth Failed!")

	def onDisconnected(self, reason):
		print("Disconnected because %s" %reason)

	def onMessageReceived(self, messageId, jid, messageContent, timestamp, wantsReceipt, pushName, isBroadCast):
		formattedDate = datetime.datetime.fromtimestamp(timestamp).strftime('%d-%m-%Y %H:%M')
		print("%s [%s]:%s"%(jid, formattedDate, messageContent))

		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))
	def waOnGroupMessageReceived(self, messageId, groupJid, author, messageContent, timestamp, wantsReceipt, pushName):		
		print "JID:", groupJid
		print "Message:", messageContent

		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (groupJid, messageId))
