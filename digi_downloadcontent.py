#!/usr/bin/env python
# -*- coding: utf-8 -*-
    
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
import simplejson as json
import os
import threading
import urllib
import datetime
import psutil
from collections import OrderedDict
import itertools
from socket import timeout
import re
import time
import concurrent.futures
import gettext

pageprefix = "page-"

dataformats = {
  'txt' : ".txt",
  'alto' : ".xml"
}

request_headers = {
"""User-Agent": _("Digi aineistolataaja 2.0"),
"Referer": _("Digi aineistolataaja 2.0"),
"Connection": "keep-alive" """
}

WORKERTHREADS = 5


class DownloadContent(threading.Thread):
  def __init__(self, queue, digiResultsUrl, OCRFormat, imageFormat, saveDirectoryPath, statusText, createKeywordsGraph, setDownloadResumeItems, hitsData, totalPagesData, bindingsCsvData, bindingsData, lastBindingIndex, formatTemplates, downloadAllBindingPages, selectedTree, currentLanguage):
    global request_headers
    threading.Thread.__init__(self)
    self.queue = queue
    self.digiResultsUrl = digiResultsUrl
    self.OCRFormat = OCRFormat
    self.imageFormat = imageFormat
    self.saveDirectoryPath = saveDirectoryPath
    self.statusText = statusText
    self.createKeywordsGraph = createKeywordsGraph
    self.setDownloadResumeItems = setDownloadResumeItems
    self.totalWordFreqs = {}
    self.downloadLimitText = ""
    self.lastBindingIndex = lastBindingIndex
    self.hitsData = hitsData
    self.totalPagesData = totalPagesData
    self.bindingsCsvData = bindingsCsvData
    self.bindingsData = bindingsData
    self.orginalBindingsData = self.bindingsData
    self.bindingsDataStartIndex = self.lastBindingIndex
    self.downloadError = False
    self.containedCopyrightData = False
    self.noDownloadContent = False
    self.downloadAllBindingPages = downloadAllBindingPages
    self.directoryTree = selectedTree 
    self.downloadTimes = []

    self.formatTemplates = formatTemplates
    if self.formatTemplates:
      self.pageImageTemplate = formatTemplates[0]
      self.altoXmlTemplate = formatTemplates[1]
      self.altoTxtTemplate = formatTemplates[2]

    self.event = threading.Event()

    #get localization
    el = gettext.translation('base', localedir='translations', languages=[currentLanguage])
    el.install()
    _ = el.gettext
    #_ = gettext.gettext

    request_headers = {
    "User-Agent": _("Digi aineistolataaja 2.0"),
    "Referer": _("Digi aineistolataaja 2.0"),
    "Connection": "keep-alive" 
    }

  def run(self):
      global statusTextWidget
      statusTextWidget = self.statusText
      statusTextWidget['text'] = _("Lataus alkaa pian...")
      statusTextWidget.config(foreground="black")

      settingError = False

      if "digi.kansalliskirjasto.fi/search?" not in self.digiResultsUrl:
        statusTextWidget['text'] = _("Osoite ei sisällä digi.kansalliskirjasto.fi osoitetta!")
        statusTextWidget.config(foreground="red")
        settingError = True
      elif not self.OCRFormat and not self.imageFormat:
        statusTextWidget['text'] = _("Valitse ladattavan aineiston formaatti!")
        statusTextWidget.config(foreground="red")
        settingError = True
      elif self.bindingsDataStartIndex == -1:
        self.downloadBindings(self.digiResultsUrl, self.OCRFormat, self.imageFormat, self.saveDirectoryPath, False)
      else:
        self.bindingsData = dict(itertools.islice(self.bindingsData.items(), self.bindingsDataStartIndex, None))
        self.downloadBindings(self.digiResultsUrl, self.OCRFormat, self.imageFormat, self.saveDirectoryPath, True)

      if self.event.is_set() and not settingError:
        if not self.downloadError:
          statusTextWidget['text'] = _("Lataus keskeytetty!")
        
        if not hasattr(self, 'lastBindingsData'):
          self.lastBindingsData = []

        self.setDownloadResumeItems(self.lastBindingIndex, self.lastBindingsData, self.hitsData, self.totalPagesData, self.bindingsCsvData, self.formatTemplates)
      elif not settingError and not self.noDownloadContent:
        statusTextWidget['text'] = statusTextWidget['text'] + '\n' + _("Lataus valmis!")
      elif self.noDownloadContent:
        statusTextWidget['text'] = statusTextWidget['text'] + '\n' + _("Ei ladattavia aineistoja, voit tarkistaa saatavilla olevat aineistot työkalun käyttöohjeesta.")
      if not self.downloadError:
        self.queue.put("Finished")
      else:
        self.queue.put("Finished error")

  def formatSizeText(self, nbytes):
    suffixes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
    i = 0
    while nbytes >= 1024 and i < len(suffixes)-1:
        nbytes /= 1024.
        i += 1
    f = ('%.2f' % nbytes).rstrip('0').rstrip('.')
    return '%s %s' % (f, suffixes[i])


  def insertToStatus(self, downloadedBindings, totalBindings, downloadedData, freeDiskSpace):

    statusText = ""

    if downloadedData and freeDiskSpace:
      statusText = self.downloadLimitText + _("Ladataan hakutulosta: ") + str(self.downloadedBindings) + '/' + str(totalBindings) + '\n' + _("Ladattu: ") + str(downloadedData) + '\n' + _("Vapaa levytila: ") + freeDiskSpace
    else:
      statusText = self.downloadLimitText + _("Ladataan hakutulosta: ") + str(self.downloadedBindings) + '/' + str(totalBindings)

    if self.downloadTimes:
      averageTime = sum(self.downloadTimes) / len(self.downloadTimes)
      resultsLeft = totalBindings - downloadedBindings#currentBinding
      timeEstimate = round((resultsLeft * averageTime / 60) / WORKERTHREADS, 1)
      statusText = statusText + '\n' + _("Latauksen arvioitu kesto: ") + str(timeEstimate) + " min"


    if self.containedCopyrightData:
      statusText = statusText + '\n' + _("Aineistoon voi liittyä käytön rajoituksia.")

    if self.event.is_set():
      statusText = statusText + '\n' + _("Lataus keskeytyy, kun viimeisin hakutulos on ladattu loppuun.")

    statusTextWidget['text'] = statusText

  def bindingSearchQuery(self, digiResultsUrl):

    parameters = digiResultsUrl[digiResultsUrl.index('?'):]

    currentRows = []
    currentBindingPageCounts = {}
    hitsByYear = {}
    totalHitsByYear = {}
    result = ""
    noMoreResults = False
    isFirstSearch = True

    digiBindingSearchURL = 'https://digi.kansalliskirjasto.fi/api/dam/binding-search' + parameters

    totalResults = 0
    errorRetries = 0

    while noMoreResults == False and not self.event.is_set():
    
      req = urllib.request.Request(digiBindingSearchURL, headers=request_headers)
      try:
        response = urllib.request.urlopen(req, timeout=30)
        responseResult = response.read()
        result = json.loads(responseResult)

        self.pageImageTemplate = result["pageImageTemplate"]
        self.altoXmlTemplate = result["altoXmlTemplate"]
        self.altoTxtTemplate = result["altoTxtTemplate"]

        self.formatTemplates = []
        self.formatTemplates.append(self.pageImageTemplate)
        self.formatTemplates.append(self.altoXmlTemplate)
        self.formatTemplates.append(self.altoTxtTemplate)

        if len(result["rows"]) != 0:
          currentRows = currentRows + result["rows"]
          currentBindingPageCounts.update(result["bindingPageCounts"])
        else:
          noMoreResults = True

        if isFirstSearch == True:
          digiBindingSearchURL = 'https://digi.kansalliskirjasto.fi/api/dam/binding-search/' + result["scrollId"]
          hitsByYear = result["hitsByYear"]
          totalHitsByYear = result["totalHitsByYear"]
          isFirstSearch = False
          totalResults = result["totalResults"]

        statusTextWidget['text'] = _("Ladataan aineistojen tietoja: ") + str(len(currentRows)) + "/" + str(totalResults)

      except HTTPError as e:
        errorRetries += 1
      except ConnectionError as e:
        errorRetries += 1
      except URLError as e:
        errorRetries += 1
      except TimeoutError as e:
        errorRetries += 1
      except timeout:
        errorRetries += 1

      if errorRetries == 3:
        statusTextWidget['text'] = _("Ei yhteyttä palvelimeen!")
        statusTextWidget.config(foreground="red")
        self.downloadError = True
        self.event.set()
        return -1

    result["rows"] = currentRows
    result["currentBindingPageCounts"] = currentBindingPageCounts
    result["hitsByYear"] = hitsByYear
    result["totalHitsByYear"] = totalHitsByYear

    return result

  def downloadBindings(self, digiSearchURL, ocrFormat, imageFormat, saveDirectoryPath, isResumeDownload):

    if not isResumeDownload:
      result = self.bindingSearchQuery(digiSearchURL)

      if self.event.is_set():
        return 0

      if self.downloadError:
        return -1

      rows = result["rows"]
      bindingPageCounts = result["currentBindingPageCounts"] 

      if len(rows) == 0:
        self.noDownloadContent = True

      bindingTitles = []
      bindingIds = []
      publicationIds = []
      pvms = []
      generalTypes = []
      publishers = []
      pageNumbers = []
      hitAreas = []
      issues = []
      terms = []
      urls = []
      copyrights = []
      references = []
      searchUrls = []

      self.hitsData = {}
      self.totalPagesData = {}
      resultsTitle = ""

      if "hitsByYear" in result and result["hitsByYear"] != None:
        self.hitsData["year"] = list(result["hitsByYear"].keys())
        self.hitsData["amount"] = list(result["hitsByYear"].values())
        resultsTitle = _("Sivuja, joilla hakusanat esiintyvät")
      
      if "totalHitsByYear" in result and result["totalHitsByYear"] != None:
        self.totalPagesData["year"] = list(result["totalHitsByYear"].keys())
        self.totalPagesData["amount"] = list(result["totalHitsByYear"].values())
        resultsTitle = _("Sivuja haussa")

      self.bindingsData = OrderedDict()

      bindingCounter = 0

      for row in rows:  
        bindingId = str(row["bindingId"])
        pageCounts = bindingPageCounts[bindingId]
        currentUrl = ""

        downloadSuccess = False
        statusTextWidget['text'] = _("Valmistellaan ladattavia aineistoja: ") + str(bindingCounter + 1) + "/" + str(len(rows))

        bindingIds.append(bindingId)

        if "bindingTitle" in row and row["bindingTitle"] != None:
          bindingTitles.append(row["bindingTitle"])
        else:
          bindingTitles.append("")

        if "publicationId" in row and row["publicationId"] != None:
          publicationIds.append(row["publicationId"])
        else:
          publicationsIds.append("")

        if "date" in row and row["date"] != None:
          pvms.append(row["date"])
        else:
          pvms.append("")

        if "issue" in row and row["issue"] != None:
          issues.append(row["issue"])
        else:
          issues.append("")

        if "generalType" in row and row["generalType"] != None:
          generalTypes.append(row["generalType"])
        else:
          generalTypes.append("")

        if "publisher" in row and row["publisher"] != None:
          publishers.append(row["publisher"])
        else:
          publishers.append("")

        if "pageNumber" in row and row["pageNumber"] != None:
          pageNumbers.append(row["pageNumber"])
        else:
          pageNumbers.append("")
        
        if "textHighlights" in row: 
          if "text" in row["textHighlights"]:
            #add three '#' to separate different highlights, so that is possible to separate them from each other when using csv-file.
            hitAreas.append('###'.join(row["textHighlights"]["text"]).replace('\n\n', ' ').replace('\r', ''))
          else:
            hitAreas.append("")

        if "terms" in row and row["terms"] != None:
          terms.append(','.join(row["terms"]))
        else:
          terms.append("")

        if "url" in row and row["url"] != None:
          currentUrl = row["url"]
          urls.append(currentUrl)
        else:
          urls.append("")

        if "copyrightWarnings" in row and row["copyrightWarnings"] != None:
          copyRightStatus = row["copyrightWarnings"]

          if copyRightStatus == True:
            copyRightStatus = _("Aineistoon voi liittyä käytön rajoituksia.")
            self.containedCopyrightData = True
          else:
            copyRightStatus = _("Ei tekijänoikeutta.")

          copyrights.append(copyRightStatus)
        else:
          copyrights.append("")

        
        issn = row["publicationId"]
        bindingTitle = row["bindingTitle"]
        date = row["date"]

        if date != None:
          currentDate = datetime.datetime.strptime(date, '%Y-%m-%d')
          year = currentDate.year
          referenceDate = currentDate.strftime('%d.%m.%Y') 
        else:
          year = "year missing"
          referenceDate = ""

        baseUrl = row["baseUrl"]
        generalType = row["generalType"]
        issue = row["issue"]
        hitsByYear = result["hitsByYear"]
        pageNumber = row["pageNumber"]
        pdfUrl = row["pdfUrl"]

        data = [bindingId, issn, year, baseUrl, generalType, date, issue, hitsByYear, pageCounts, pageNumber, bindingTitle, pdfUrl]
        self.bindingsData[bindingCounter] = data

        issueText = ""

        if issue != None:
          issueText = ", nro " + str(issue)


        referenceText = bindingTitle +  ", " + referenceDate +  issueText + ", s. " + str(pageNumber) + "\n" + currentUrl + "\n" + _("Kansalliskirjaston digitaaliset aineistot")
        
        references.append(referenceText)

        #add search url to csv, so it is later possible to see what search was used
        searchUrls.append(self.digiResultsUrl)

        bindingCounter += 1
      
      
      self.bindingsCsvData = {}
      self.bindingsCsvData["bindingTitle"] = bindingTitles
      self.bindingsCsvData["bindingId"] = bindingIds
      self.bindingsCsvData["publicationId"] = publicationIds
      self.bindingsCsvData["date"] = pvms
      self.bindingsCsvData["issue"] = issues
      self.bindingsCsvData["generalType"] = generalTypes
      self.bindingsCsvData["publisher"] = publishers
      self.bindingsCsvData["pageNumber"] = pageNumbers
      self.bindingsCsvData["textHighlights"] = hitAreas
      self.bindingsCsvData["terms"] = terms
      self.bindingsCsvData["url"] = urls
      self.bindingsCsvData["copyrights"] = copyrights
      self.bindingsCsvData["searchUrls"] = searchUrls
      self.bindingsCsvData["references"] = references

      self.bindingsDataStartIndex = 0

      self.orginalBindingsData = self.bindingsData
      self.totalBindings = len(self.orginalBindingsData)
    else:
      self.totalBindings = len(self.orginalBindingsData)

    if len(self.totalPagesData["year"]) > 0 and not self.event.is_set():
      self.createKeywordsGraph(self.hitsData, self.totalPagesData, self.bindingsCsvData, isResumeDownload)

    self.currentBinding = self.bindingsDataStartIndex
    self.totalDownloadedData = 0
    self.downloadedBindings = self.totalBindings - len(self.bindingsData)

    self.downloadedBindings += 1
    
    self.futures = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERTHREADS) as executor:

      for bindingIndex, binding in enumerate(self.bindingsData):

        if not self.event.is_set():

          currentData = self.bindingsData[binding]
          bindingId = currentData[0]
          issn = currentData[1]
          year = currentData[2]
          baseUrl = currentData[3]
          generalType = currentData[4]
          bindingDate = currentData[5]
          bindingNO = currentData[6]
          hitsByYear = currentData[7]
          pageCounts = currentData[8]
          pageNumber = currentData[9]
          bindingTitle = currentData[10]
          pdfUrl = currentData[11]

          #removes special characters from title name
          pathTitle = re.sub(r'[^a-zåäöA-ZÅÄÖ0-9 ]', '', bindingTitle)

          issnPath = ""
          fullPath = ""
          
          if self.directoryTree == 0:
            issnPath = saveDirectoryPath + "/" + pathTitle[0:40]  + "_" + bindingId + "/"
            fullPath = issnPath
          elif self.directoryTree == 1:
            issnPath = saveDirectoryPath + "/" + issn + "/"
            fullPath = issnPath
          elif self.directoryTree == 2:
            issnPath = saveDirectoryPath + "/" + pathTitle[0:40]  + "_" + bindingId + "/"
            fullPath = issnPath + str(year) + "/"
          elif self.directoryTree == 3:
            issnPath = saveDirectoryPath + "/" + issn + "/"
            fullPath = issnPath + str(year) + "/"
          elif self.directoryTree == 4:
            issnPath = saveDirectoryPath + "/" + str(year) + "/"
            fullPath = issnPath + str(issn) + "/"
          elif self.directoryTree == 5:
            issnPath = saveDirectoryPath + "/" + str(year) + "/"
            fullPath = issnPath + pathTitle[0:40]  + "_" + bindingId + "/"

          if not os.path.isdir(issnPath):
            #creates own subdir
            os.mkdir(issnPath)

          ocrPath = ""
          if ocrFormat:
            ocrPath = os.path.join(fullPath, ocrFormat)

            if not os.path.exists(ocrPath):
              os.makedirs(ocrPath)

          imagePath = ""
          if imageFormat == "jpg":
            imagePath = os.path.join(fullPath, "jpg")
          elif imageFormat == "pdf":
            imagePath = os.path.join(fullPath, "pdf")
            
          if imagePath:
            if not os.path.exists(imagePath):
              os.makedirs(imagePath)

          self.currentBinding = self.currentBinding + 1
          issueName = self.createIssueName(issn, bindingDate, bindingNO, generalType)

          #startTime = time.time()
          #self.downloadBindingData(bindingId, ocrPath, imagePath, ocrFormat, imageFormat, issn, baseUrl, generalType, issueName, hitsByYear, pageCounts, pageNumber, pdfUrl)
          self.futures.append(executor.submit(self.downloadBindingData,bindingId, ocrPath, imagePath, ocrFormat, imageFormat, issn, baseUrl, generalType, issueName, hitsByYear, pageCounts, pageNumber, pdfUrl, self.currentBinding))

        else:
          self.lastBindingIndex = bindingIndex + self.bindingsDataStartIndex
          self.lastBindingsData = self.orginalBindingsData
          break

      failedDownloadIndex = -1

      for future in concurrent.futures.as_completed(self.futures):
        result = future.result()
        #sets lastBindingIndex to smallest binding index that failed to download. 
        if not result[1] and (failedDownloadIndex > result[0] or failedDownloadIndex == -1):
          self.lastBindingIndex = result[0] - 1
          failedDownloadIndex = result[0]
          self.lastBindingsData = self.orginalBindingsData
        #if there has not been failed downloads, set largest downloaded binding index to lastbindingIndex
        elif failedDownloadIndex == -1 and self.lastBindingIndex < result[0]:
          self.lastBindingIndex = result[0]
          self.lastBindingsData = self.orginalBindingsData

  def urlretrieve2(self, url, localfile):
    # Adapted from https://stackoverflow.com/a/4028894/364931
    
    try:
      req = urllib.request.Request(url, headers=request_headers)
      f = urlopen(req, timeout=30)

      # Open our local file for writing
      with open(localfile, "wb") as fl:
          fl.write(f.read())

    #handle errors
    except Exception as e:
      print(_("Ei yhteyttä palvelimeen!"))
      return 0

    if not os.path.exists(localfile):
      return 0

    return 1

  def createIssueName (self, issn, bindingDate, bindingNO, generalType):

    if bindingDate == None:
      bindingDate ="year missing"

    if generalType == "NEWSPAPER":
      return "_".join([issn, bindingDate, bindingNO])
    else:
      return "_".join([issn, bindingDate])

  def downloadData(self, baseUrl, issuename, generalType, bindingid, localdir, imagePath, dataformat, imageFormat, pageNumber, pdfUrl):

    downloadedDataSize = 0
    downloadError = False

    imageUri = baseUrl + self.pageImageTemplate.replace("{{page}}", str(pageNumber))

    if dataformat == "txt":
      contentUri  = baseUrl + self.altoTxtTemplate.replace("{{page}}", str(pageNumber))
    elif dataformat =="alto":
      contentUri  = baseUrl + self.altoXmlTemplate.replace("{{page}}", str(pageNumber))

    if dataformat:
      localname = issuename + "_" + pageprefix + str(pageNumber) + dataformats[dataformat]

      # Downloads individual XML ore text page and stores it to download folder

      if generalType != "PRINTING":

        localDataPath = localdir + '/' + bindingid+"_"+localname
        
        downloadSuccess = False
        retries = 0

        while (not downloadSuccess and retries < 4):
          res2 = self.urlretrieve2(contentUri, localDataPath)
          if res2 > 0:

            downloadedDataSize = downloadedDataSize + os.path.getsize(localDataPath)
            downloadSuccess = True

          else:
            print("ERR, couldn't download {0}".format(contentUri), True)
            print ("retries: " + str(retries))
            if retries == 3:
              downloadError = True
              self.event.set()
              statusTextWidget['text'] = _("Ei yhteyttä palvelimeen!")
              statusTextWidget.config(foreground="red")

          retries = retries + 1


    # Downloads page jpg image or bindings pdf

    if imageFormat == "jpg":

      localImageName = issuename + "_" + pageprefix + str(pageNumber) + ".jpg"
      localImageFilePath = imagePath + '/' + bindingid+"_"+localImageName

      downloadSuccess = False
      retries = 0

      while (not downloadSuccess and retries < 4):
        res2 = self.urlretrieve2(imageUri, localImageFilePath)
        if res2 > 0:
          downloadedDataSize = downloadedDataSize + os.path.getsize(localImageFilePath)
          downloadSuccess = True
        else:
          print("ERR, couldn't download {0}".format(imageUri), True)
          print ("retries: " + str(retries))
          if retries == 3:
            downloadError = True
            self.event.set()
            statusTextWidget['text'] = _("Ei yhteyttä palvelimeen!")
            statusTextWidget.config(foreground="red")
        
        retries = retries + 1

    elif imageFormat == "pdf" and pdfUrl != "":

      localImageName = issuename +  ".pdf"
      localImageFilePath = imagePath + '/' + bindingid+"_"+localImageName

      downloadSuccess = False
      retries = 0

      while (not downloadSuccess and retries < 4):
        res2 = self.urlretrieve2(pdfUrl, localImageFilePath)
        if res2 > 0:
          downloadedDataSize = downloadedDataSize + os.path.getsize(localImageFilePath)
          downloadSuccess = True
        else:
          print("ERR, couldn't download {0}".format(imageUri), True)
          print ("retries: " + str(retries))
          if retries == 3:
            downloadError = True
            self.event.set()
            statusTextWidget['text'] = _("Ei yhteyttä palvelimeen!")
            statusTextWidget.config(foreground="red")
        
        retries = retries + 1



    if not downloadError:
      freeDiskSpace = psutil.disk_usage(self.saveDirectoryPath).free
      self.totalDownloadedData = self.totalDownloadedData + downloadedDataSize
      self.insertToStatus(self.downloadedBindings, self.totalBindings, self.formatSizeText(self.totalDownloadedData), self.formatSizeText(freeDiskSpace))

    return downloadSuccess

  def downloadBindingData(self, bindingid, localdir, imagePath, dataformat, imageFormat, issn, baseUrl, generalType, issueName, hitsByYear, bindingPageCounts, pageNumber, pdfUrl, currentBinding):
    
    downloadSuccess = True

    if not self.event.is_set():

      startTime = time.time()
      

      if self.downloadAllBindingPages != "1":
        downloadSuccess = self.downloadData(baseUrl, issueName, generalType, bindingid, localdir, imagePath, dataformat, imageFormat, pageNumber, pdfUrl)
      else:

        pageCounter = 1

        while (pageCounter < bindingPageCounts + 1):

          #download pdf file only once
          if pageCounter > 1:
            pdfUrl = ""

          if not self.downloadData(baseUrl, issueName, generalType, bindingid, localdir, imagePath, dataformat, imageFormat, pageCounter, pdfUrl):
            downloadSuccess = False
          pageCounter += 1

      endTime = time.time()
      self.downloadTimes.append(endTime-startTime)

    else:
      downloadSuccess = False

    if downloadSuccess:
      freeDiskSpace = psutil.disk_usage(self.saveDirectoryPath).free
      self.insertToStatus(self.downloadedBindings, self.totalBindings, self.formatSizeText(self.totalDownloadedData), self.formatSizeText(freeDiskSpace))
      self.downloadedBindings += 1

    return [currentBinding, downloadSuccess]