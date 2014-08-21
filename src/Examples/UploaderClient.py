'''
Copyright (c) <2012> Tarek Galal <tare2.galal@gmail.com>

Permission is hereby granted, free of charge, to any person obtaining a copy of this 
software and associated documentation files (the "Software"), to deal in the Software 
without restriction, including without limitation the rights to use, copy, modify, 
merge, publish, distribute, sublicense, and/or sell copies of the Software, and to 
permit persons to whom the Software is furnished to do so, subject to the following 
conditions:

The above copyright notice and this permission notice shall be included in all 
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, 
INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR 
A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT 
HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF 
CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE 
OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
'''
from Yowsup.connectionmanager import YowsupConnectionManager
import time, datetime, sys

from Yowsup.Media.downloader import MediaDownloader
from Yowsup.Media.uploader import MediaUploader
from sys import stdout
import os
import hashlib 
import base64
from PIL import Image

import StringIO

size = 100,100

if sys.version_info >= (3, 0):
	raw_input = input

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
